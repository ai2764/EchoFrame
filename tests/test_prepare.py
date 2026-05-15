import asyncio

from app.config import Settings
from app.services.comfy import ComfyClient
from app.services.service_manager import ServiceManager


def test_prepare_native_audio_warms_ltx(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    manager = ServiceManager(settings)
    events = []

    async def ensure(name):
        events.append(("ensure", name))

    async def prepare_ltx(self, resolution=None):
        events.append(("ltx", resolution))

    monkeypatch.setattr(manager, "ensure", ensure)
    monkeypatch.setattr(ComfyClient, "prepare_ltx_native_audio", prepare_ltx)

    response = asyncio.run(manager.prepare_workflow("ltx_native_audio", resolution=512))

    assert response.ok
    assert response.workflow == "ltx_native_audio"
    assert events == [("ensure", "comfyui"), ("ltx", 512)]


def test_prepare_ia2v_and_wan_warm_tts(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    manager = ServiceManager(settings)
    events = []

    async def preload_tts():
        events.append("tts")

    monkeypatch.setattr(manager, "preload_tts_for_workflow", preload_tts)

    ia2v = asyncio.run(manager.prepare_workflow("ltx_ia2v", resolution=512))
    wan = asyncio.run(manager.prepare_workflow("musetalk", mode="wan_loop", resolution=320))

    assert ia2v.ok
    assert wan.ok
    assert events == ["tts", "tts"]
