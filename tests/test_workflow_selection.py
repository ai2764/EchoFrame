import asyncio

from app.config import Settings
from app.modules.video import BaseVideoResult
from app.schemas import ChatRequest
from app.services.pipeline import TalkingAvatarPipeline


def test_chat_request_can_select_ltx_backend_when_default_is_musetalk(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        final_video_backend="musetalk",
        ltx_unload_llm_before_video=False,
        ltx_unload_tts_before_video=False,
        ltx_reload_tts_after_video=False,
    )
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
        assert kwargs["resolution"] == 512
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
                resolution=512,
            )
        )
    )

    assert response.final_video_backend == "ltx_ia2v"
    assert response.resolution == 512
    assert ltx_called
    assert not musetalk_called


def test_chat_request_can_select_ltx_q4_backend_and_keep_tts_loaded(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        final_video_backend="ltx_ia2v",
        ltx_unload_llm_before_video=False,
        ltx_unload_tts_before_video=True,
        ltx_reload_tts_after_video=True,
    )
    avatar_dir = settings.abs_data_dir / "avatars" / "av_test"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "source.png").write_bytes(b"avatar")

    pipeline = TalkingAvatarPipeline(settings)
    events = []

    async def plan(*_):
        return {
            "reply": "hello",
            "cosyvoice_instruct": "calm",
            "wan_prompt": "front-facing bust shot",
        }

    async def synthesize(**kwargs):
        events.append("tts")
        kwargs["output_path"].write_bytes(b"audio")
        return "sent"

    async def unload_tts():
        events.append("unload_tts")

    async def generate_ltx_video(**kwargs):
        events.append(("ltx", kwargs["ltx_model_format"], kwargs["unload_after"]))
        out = kwargs["run_dir"] / "ltx_raw.mp4"
        out.write_bytes(b"video")
        return out

    pipeline.llm.plan = plan
    pipeline.tts.synthesize = synthesize
    pipeline.services.unload_tts_for_ltx = unload_tts
    pipeline.media.duration = lambda _: 1.0
    pipeline.media.mux_audio = lambda video, audio, output: output.write_bytes(video.read_bytes())
    pipeline.video.generate_ltx_ia2v_video = generate_ltx_video

    response = asyncio.run(
        pipeline.chat(
            ChatRequest(
                avatar_id="av_test",
                message="hello",
                final_video_backend="ltx_ia2v_q4",
                resolution=512,
            )
        )
    )

    assert response.final_video_backend == "ltx_ia2v_q4"
    assert response.resolution == 512
    assert events == ["tts", ("ltx", "gguf", False)]


def test_chat_request_can_select_ltx_native_audio_backend_and_skip_tts(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        final_video_backend="musetalk",
        ltx_unload_llm_before_video=False,
        ltx_unload_tts_before_video=False,
        ltx_reload_tts_after_video=False,
    )
    avatar_dir = settings.abs_data_dir / "avatars" / "av_test"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "source.png").write_bytes(b"avatar")

    pipeline = TalkingAvatarPipeline(settings)

    async def plan(*_):
        return {
            "reply": "你好，今天老道给大家发福利来了!",
            "cosyvoice_instruct": "calm",
            "wan_prompt": "front-facing bust shot",
        }

    async def synthesize(**_):
        raise AssertionError("native-audio LTX should not call TTS")

    async def generate_ltx_video(**_):
        raise AssertionError("native-audio LTX should not call external-audio LTX")

    async def generate_ltx_native_audio_video(**kwargs):
        assert kwargs["duration"] >= settings.ltx_native_audio_min_seconds
        assert kwargs["resolution"] == 512
        assert "generated speech audio" in kwargs["prompt"]
        out = kwargs["run_dir"] / "ltx_native_audio.mp4"
        out.write_bytes(b"video")
        return out

    pipeline.llm.plan = plan
    pipeline.tts.synthesize = synthesize
    pipeline.video.generate_ltx_ia2v_video = generate_ltx_video
    pipeline.video.generate_ltx_native_audio_video = generate_ltx_native_audio_video
    pipeline.media.extract_audio = lambda video, audio: audio.write_bytes(b"generated audio")
    pipeline.media.duration = lambda _: 3.375

    response = asyncio.run(
        pipeline.chat(
            ChatRequest(
                avatar_id="av_test",
                message="hello",
                final_video_backend="ltx_native_audio",
                resolution=512,
            )
        )
    )

    assert response.final_video_backend == "ltx_native_audio"
    assert response.resolution == 512
    assert response.audio_duration == 3.375
    assert response.audio_url.endswith("/voice.m4a")
    assert response.video_url.endswith("/final.mp4")
    assert "tts" not in response.timings
    assert "pre_ltx_vram_release" not in response.timings
    assert "ltx_native_audio" in response.timings
    assert "native_audio_export" in response.timings


def test_ltx_releases_llm_and_tts_before_video_then_reloads_tts(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        final_video_backend="ltx_ia2v",
        ltx_unload_llm_before_video=True,
        ltx_unload_tts_before_video=True,
        ltx_reload_tts_after_video=True,
    )
    avatar_dir = settings.abs_data_dir / "avatars" / "av_test"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "source.png").write_bytes(b"avatar")

    pipeline = TalkingAvatarPipeline(settings)
    events = []

    async def plan(*_):
        return {
            "reply": "hello",
            "cosyvoice_instruct": "calm",
            "wan_prompt": "front-facing bust shot",
        }

    async def synthesize(**kwargs):
        events.append("tts")
        kwargs["output_path"].write_bytes(b"audio")
        return "sent"

    def duration(_):
        events.append("audio_probe")
        return 1.0

    async def unload_llm():
        events.append("unload_llm")

    async def unload_tts():
        events.append("unload_tts")

    async def generate_ltx_video(**kwargs):
        events.append("ltx")
        out = kwargs["run_dir"] / "ltx_raw.mp4"
        out.write_bytes(b"video")
        return out

    pipeline.llm.plan = plan
    pipeline.tts.synthesize = synthesize
    pipeline.media.duration = duration
    pipeline.media.mux_audio = lambda video, audio, output: output.write_bytes(video.read_bytes())
    pipeline.services.unload_llm_for_ltx = unload_llm
    pipeline.services.unload_tts_for_ltx = unload_tts
    pipeline.video.generate_ltx_ia2v_video = generate_ltx_video

    async def run_chat():
        preload_started = asyncio.Event()
        preload_continue = asyncio.Event()
        preload_finished = asyncio.Event()

        async def preload_tts():
            events.append("preload_tts_started")
            preload_started.set()
            await preload_continue.wait()
            events.append("preload_tts_done")
            preload_finished.set()

        pipeline.services.preload_tts_after_ltx = preload_tts
        response = await pipeline.chat(ChatRequest(avatar_id="av_test", message="hello"))

        assert response.final_video_backend == "ltx_ia2v"
        assert events[:5] == ["tts", "audio_probe", "unload_llm", "unload_tts", "ltx"]
        assert "preload_tts_done" not in events
        assert "pre_ltx_vram_release" in response.timings
        assert "post_ltx_tts_preload" not in response.timings

        await asyncio.wait_for(preload_started.wait(), timeout=1)
        preload_continue.set()
        await asyncio.wait_for(preload_finished.wait(), timeout=1)
        return response

    response = asyncio.run(run_chat())

    assert response.final_video_backend == "ltx_ia2v"
    assert events == [
        "tts",
        "audio_probe",
        "unload_llm",
        "unload_tts",
        "ltx",
        "preload_tts_started",
        "preload_tts_done",
    ]


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


def test_musetalk_wan_releases_comfy_before_tts_and_after_wan(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v")
    avatar_dir = settings.abs_data_dir / "avatars" / "av_test"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "source.png").write_bytes(b"avatar")

    pipeline = TalkingAvatarPipeline(settings)
    events = []

    async def plan(*_):
        return {
            "reply": "hello",
            "cosyvoice_instruct": "calm",
            "wan_prompt": "front-facing bust shot",
        }

    async def free_memory():
        events.append("free_comfy")

    async def synthesize(**kwargs):
        events.append("tts")
        kwargs["output_path"].write_bytes(b"audio")
        return "sent"

    def duration(_):
        events.append("audio_probe")
        return 1.0

    async def generate_base_video(**kwargs):
        events.append("wan")
        base = kwargs["run_dir"] / "base.mp4"
        base.write_bytes(b"base")
        return BaseVideoResult(base_path=base, lip_sync_input_path=base, fps=12)

    async def lip_sync(**kwargs):
        events.append("musetalk")
        out = kwargs["run_dir"] / "talk.mp4"
        out.write_bytes(b"talk")
        return out

    pipeline.llm.plan = plan
    pipeline.video.comfy.free_memory = free_memory
    pipeline.tts.synthesize = synthesize
    pipeline.media.duration = duration
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
    assert events == ["free_comfy", "tts", "audio_probe", "wan", "free_comfy", "musetalk"]
    assert "pre_wan_comfy_release" in response.timings
    assert "post_wan_comfy_release" in response.timings
