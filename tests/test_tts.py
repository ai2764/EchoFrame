import asyncio
import shutil
import uuid
from pathlib import Path

import httpx

from app.config import Settings
from app.schemas import ChatRequest
from app.services.pipeline import TalkingAvatarPipeline
from app.services.tts import TTSClient
from tools.native_cosyvoice_tts import prep_text_for_tts, should_use_short_text_instruct


def test_native_tts_health_reports_missing_parts():
    tmp_path = make_workspace_tmp()
    try:
        settings = Settings(
            data_dir=tmp_path / "data",
            tts_backend="native",
            tts_root=tmp_path / "cosyvoice",
            tts_model_dir=tmp_path / "model",
            tts_presets_file=tmp_path / "presets.json",
        )
        ok, detail = asyncio.run(TTSClient(settings).health())
        assert not ok
        assert "missing" in detail
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_native_tts_health_uses_project_voice_presets():
    tmp_path = make_workspace_tmp()
    try:
        root = tmp_path / "cosyvoice"
        source = root / "vendor" / "cosyvoice" / "cosyvoice"
        source.mkdir(parents=True)
        model = tmp_path / "model"
        model.mkdir()
        (model / "config.yaml").write_text("{}", encoding="utf-8")
        presets = tmp_path / "presets.json"
        presets.write_text("{}", encoding="utf-8")

        settings = Settings(
            data_dir=tmp_path / "data",
            tts_backend="native",
            tts_root=root,
            tts_model_dir=model,
            tts_presets_file=presets,
        )
        ok, detail = asyncio.run(TTSClient(settings).health())
        assert ok
        assert detail == "native ready"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_pipeline_maps_gender_to_configured_voice_ids():
    tmp_path = make_workspace_tmp()
    try:
        settings = Settings(
            data_dir=tmp_path / "data",
            tts_en_female_voice_id="en_female_voice",
            tts_en_male_voice_id="en_male_voice",
            tts_zh_female_voice_id="zh_female_voice",
            tts_zh_male_voice_id="zh_male_voice",
        )
        pipeline = TalkingAvatarPipeline(settings)
        base = {"avatar_id": "av_test", "message": "hello"}

        assert pipeline._voice_id(ChatRequest(**base, voice="female"), "hello") == "en_female_voice"
        assert pipeline._voice_id(ChatRequest(**base, voice="male"), "hello") == "en_male_voice"
        assert pipeline._voice_id(ChatRequest(**base, voice="female"), "你好") == "zh_female_voice"
        assert pipeline._voice_id(ChatRequest(**base, voice="male"), "你好") == "zh_male_voice"
        assert pipeline._voice_id(ChatRequest(**base, voice_id="exact_voice", voice="female"), "你好") == "exact_voice"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_http_tts_never_trims_audio(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path / "data", tts_trim_start_seconds=0.8)
    client = TTSClient(settings)
    output = tmp_path / "voice.wav"
    response_bytes = b"raw cosyvoice audio"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, files=None):
            assert "instruct" not in files
            return httpx.Response(200, content=response_bytes)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(client._synthesize_http("你好", "", "voice", output))

    assert output.read_bytes() == response_bytes


def test_native_tts_prep_adds_terminal_punctuation():
    assert prep_text_for_tts("你好") == "你好。"
    assert prep_text_for_tts("hello") == "hello."
    assert prep_text_for_tts("你好！") == "你好！"


def test_native_tts_short_text_uses_instruct2_guard():
    ref = "大家好，这是用于展示声线的一段比较长的参考音频。"

    assert should_use_short_text_instruct("你好。", ref)
    assert not should_use_short_text_instruct("这是一段长度足够的口播文本，用来生成稳定的语音。", ref)


def make_workspace_tmp() -> Path:
    path = Path("data") / "test_tts" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path
