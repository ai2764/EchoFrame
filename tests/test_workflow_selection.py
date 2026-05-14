import asyncio

from app.config import Settings
from app.modules.video import BaseVideoResult
from app.schemas import ChatRequest
from app.services.pipeline import TalkingAvatarPipeline


def test_chat_request_can_select_ltx_backend_when_default_is_musetalk(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="musetalk")
    avatar_dir = settings.abs_data_dir / "avatars" / "av_test"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "source.png").write_bytes(b"avatar")

    pipeline = TalkingAvatarPipeline(settings)
    async def plan(*_):
        return {
            "reply": "hello",
            "cosyvoice_instruct": "calm",
            "wan_prompt": "front-facing bust shot",
        }

    pipeline.llm.plan = plan
    pipeline.media.duration = lambda _: 1.0
    pipeline.media.mux_audio = lambda video, audio, output: output.write_bytes(video.read_bytes())
    musetalk_called = False
    ltx_called = False

    async def synthesize(**kwargs):
        kwargs["output_path"].write_bytes(b"audio")
        return "sent"

    async def generate_ltx_video(**kwargs):
        nonlocal ltx_called
        ltx_called = True
        out = kwargs["run_dir"] / "ltx_raw.mp4"
        out.write_bytes(b"video")
        return out

    async def lip_sync(**kwargs):
        nonlocal musetalk_called
        musetalk_called = True

    pipeline.tts.synthesize = synthesize
    pipeline.video.generate_ltx_ia2v_video = generate_ltx_video
    pipeline.lipsync.lip_sync = lip_sync

    response = asyncio.run(
        pipeline.chat(
            ChatRequest(
                avatar_id="av_test",
                message="hello",
                final_video_backend="ltx_ia2v",
            )
        )
    )

    assert response.final_video_backend == "ltx_ia2v"
    assert ltx_called
    assert not musetalk_called


def test_chat_request_can_select_musetalk_backend_when_default_is_ltx(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v")
    avatar_dir = settings.abs_data_dir / "avatars" / "av_test"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "source.png").write_bytes(b"avatar")

    pipeline = TalkingAvatarPipeline(settings)
    async def plan(*_):
        return {
            "reply": "hello",
            "cosyvoice_instruct": "calm",
            "wan_prompt": "front-facing bust shot",
        }

    pipeline.llm.plan = plan
    pipeline.media.duration = lambda _: 1.0
    ltx_called = False
    musetalk_called = False

    async def synthesize(**kwargs):
        kwargs["output_path"].write_bytes(b"audio")
        return "sent"

    async def generate_ltx_video(**kwargs):
        nonlocal ltx_called
        ltx_called = True

    async def generate_base_video(**kwargs):
        assert kwargs["mode"] == "wan_loop"
        base = kwargs["run_dir"] / "base.mp4"
        base.write_bytes(b"base")
        return BaseVideoResult(base_path=base, lip_sync_input_path=base, fps=12)

    async def lip_sync(**kwargs):
        nonlocal musetalk_called
        musetalk_called = True
        out = kwargs["run_dir"] / "talk.mp4"
        out.write_bytes(b"talk")
        return out

    pipeline.tts.synthesize = synthesize
    pipeline.video.generate_ltx_ia2v_video = generate_ltx_video
    pipeline.video.generate_base_video = generate_base_video
    pipeline.lipsync.lip_sync = lip_sync

    response = asyncio.run(
        pipeline.chat(
            ChatRequest(
                avatar_id="av_test",
                message="hello",
                mode="wan_loop",
                final_video_backend="musetalk",
            )
        )
    )

    assert response.final_video_backend == "musetalk"
    assert musetalk_called
    assert not ltx_called
