import asyncio
import json
import shutil

from app.config import Settings
from app.schemas import RegenerateRequest
from app.services.pipeline import TalkingAvatarPipeline


def test_regenerate_video_reuses_previous_audio_and_updates_prompt(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v")
    avatar_dir = settings.abs_data_dir / "avatars" / "av_test"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "source.png").write_bytes(b"avatar")
    previous_dir = settings.abs_data_dir / "runs" / "run_old"
    previous_dir.mkdir(parents=True)
    (previous_dir / "voice.wav").write_bytes(b"audio")
    (previous_dir / "reply.json").write_text(
        json.dumps(
            {
                "run_id": "run_old",
                "avatar_id": "av_test",
                "message": "hello",
                "mode": "fast",
                "voice_id": "voice_a",
                "resolution": 768,
                "wan_render_resolution": 224,
                "reply": "hello",
                "cosyvoice_instruct": "calm",
                "tts_instruct_sent": "",
                "wan_prompt": "front-facing bust shot, zoom in, camera push-in",
                "audio_duration": 1.0,
                "ltx_input_audio": "voice.wav",
            }
        ),
        encoding="utf-8",
    )

    pipeline = TalkingAvatarPipeline(settings)
    pipeline.media.duration = lambda _: 1.0
    tts_called = False

    async def synthesize(*args, **kwargs):
        nonlocal tts_called
        tts_called = True

    async def generate_video(**kwargs):
        assert kwargs["audio_path"].read_bytes() == b"audio"
        assert "zoom in" not in kwargs["prompt"].lower()
        assert "camera push-in" not in kwargs["prompt"].lower()
        out = kwargs["run_dir"] / "ltx_raw.mp4"
        out.write_bytes(b"video")
        return out

    pipeline.tts.synthesize = synthesize
    pipeline.video.generate_ltx_ia2v_video = generate_video
    pipeline.media.mux_audio = lambda video, audio, output: shutil.copy2(video, output)

    async def collect():
        return [
            event
            async for event in pipeline.regenerate_events(RegenerateRequest(run_id="run_old", stage="video"))
        ]

    events = asyncio.run(collect())
    result = next(event["data"] for event in events if event["type"] == "result")

    assert not tts_called
    assert result["reply"] == "hello"
    assert result["audio_duration"] == 1.0
    assert result["video_url"].endswith("/final.mp4")
