import json
import subprocess
import asyncio
from functools import lru_cache

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.schemas import ChatRequest, ChatResponse, EngineActionResponse, EngineStatus, HealthResponse, ServiceStatus
from app.services.comfy import ComfyClient
from app.services.gpu import gpu_summary
from app.services.llm import LLMClient
from app.services.musetalk import MuseTalkClient
from app.services.pipeline import TalkingAvatarPipeline
from app.services.run_control import WorkflowCancelled, run_controller
from app.services.service_manager import ServiceManager
from app.services.tts import TTSClient


app = FastAPI(title="EchoFrame")


@lru_cache
def get_pipeline() -> TalkingAvatarPipeline:
    return TalkingAvatarPipeline(get_settings())


@lru_cache
def get_service_manager() -> ServiceManager:
    return ServiceManager(get_settings())


settings = get_settings()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory=str(settings.abs_data_dir)), name="media")


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@app.post("/api/avatar")
async def upload_avatar(
    image: UploadFile = File(...),
    pipeline: TalkingAvatarPipeline = Depends(get_pipeline),
):
    return await pipeline.create_avatar(image)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, pipeline: TalkingAvatarPipeline = Depends(get_pipeline)):
    try:
        return await pipeline.chat(req)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat-stream")
async def chat_stream(req: ChatRequest, pipeline: TalkingAvatarPipeline = Depends(get_pipeline)):
    async def stream():
        state = run_controller.start(asyncio.current_task())
        try:
            async for event in pipeline.chat_events(req, state):
                if event.get("type") == "stage":
                    state.record_stage(event)
                elif event.get("type") == "result":
                    state.record_result(event.get("data") or {})
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except WorkflowCancelled as exc:
            state.record_cancelled(str(exc))
            event = {"type": "cancelled", "message": str(exc)}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            state.record_cancelled("Workflow cancelled")
            raise
        except Exception as exc:
            state.record_error(str(exc))
            event = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            run_controller.finish(state)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/stop")
async def stop_workflow(s: Settings = Depends(get_settings)):
    state = run_controller.cancel_active()
    if state is None:
        return {"ok": False, "detail": "no active workflow"}
    await ComfyClient(s).interrupt_and_free()
    return {"ok": True, "run_id": state.run_id, "detail": "stop requested"}


@app.get("/api/run-status")
async def run_status():
    return run_controller.latest_status()


@app.get("/api/services", response_model=dict[str, EngineStatus])
async def services(manager: ServiceManager = Depends(get_service_manager)):
    return await manager.statuses()


@app.post("/api/services/{name}/start", response_model=EngineActionResponse)
async def start_service(name: str, manager: ServiceManager = Depends(get_service_manager)):
    return await manager.start(name)


@app.post("/api/services/{name}/stop", response_model=EngineActionResponse)
async def stop_service(name: str, manager: ServiceManager = Depends(get_service_manager)):
    return await manager.stop(name)


@app.post("/api/services/{name}/restart", response_model=EngineActionResponse)
async def restart_service(name: str, manager: ServiceManager = Depends(get_service_manager)):
    return await manager.restart(name)


@app.get("/api/services/{name}/logs")
async def service_logs(name: str, manager: ServiceManager = Depends(get_service_manager)):
    return {"name": name, "logs": manager.logs(name)}


@app.get("/api/health", response_model=HealthResponse)
async def health(s: Settings = Depends(get_settings)):
    llm_ok, llm_detail = await LLMClient(s).health()
    tts_ok, tts_detail = await TTSClient(s).health()
    comfy_ok, comfy_detail = await ComfyClient(s).health()
    muse_ok, muse_detail = MuseTalkClient(s).health()
    ffmpeg_ok, ffmpeg_detail = _ffmpeg_health(s)
    gpu_detail = gpu_summary()
    return HealthResponse(
        lm_studio=ServiceStatus(ok=llm_ok, detail=llm_detail),
        cosyvoice=ServiceStatus(ok=tts_ok, detail=tts_detail),
        comfyui=ServiceStatus(ok=comfy_ok, detail=comfy_detail),
        musetalk=ServiceStatus(ok=muse_ok, detail=muse_detail),
        ffmpeg=ServiceStatus(ok=ffmpeg_ok, detail=ffmpeg_detail),
        gpu=ServiceStatus(ok=True, detail=gpu_detail),
    )


@app.get("/api/gpu", response_model=ServiceStatus)
async def gpu_status():
    return ServiceStatus(ok=True, detail=gpu_summary())


def _ffmpeg_health(s: Settings) -> tuple[bool, str]:
    try:
        ff = subprocess.run([s.ffmpeg_bin, "-version"], capture_output=True, text=True, timeout=5)
        fp = subprocess.run([s.ffprobe_bin, "-version"], capture_output=True, text=True, timeout=5)
        if ff.returncode == 0 and fp.returncode == 0:
            return True, "ready"
        return False, (ff.stderr or fp.stderr or "ffmpeg/ffprobe failed")[:300]
    except Exception as exc:
        return False, str(exc)


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.app_host, port=s.app_port)
