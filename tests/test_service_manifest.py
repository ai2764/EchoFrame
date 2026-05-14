import sys
import types

import pytest

from app.config import Settings, get_settings
from app.services.gpu import _format_ai_process
from app.services.model_manifest import ModelManifest
from app.services.service_manifest import service_manifest
from app.services.service_manager import ServiceManager


def test_repo_profile_manifest_declares_external_policy(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", app_profile="repo", tts_backend="http")
    manifest = service_manifest(settings)

    assert manifest["profile"] == "repo"
    assert "external services" in manifest["policy"]
    cosyvoice = next(item for item in manifest["services"] if item["name"] == "cosyvoice")
    assert cosyvoice["default"] == settings.tts_url
    assert "External CosyVoice" in cosyvoice["repo_note"]


def test_repo_profile_disables_model_downloads(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", model_downloads_enabled=False)

    with pytest.raises(RuntimeError, match="model downloads are disabled"):
        ModelManifest(settings).download_missing()


def test_wan_manifest_requires_official_4step_loras_by_default(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        comfy_models_dir=tmp_path / "models",
        wan_profile="wan22_14b_i2v",
    )
    for folder, name in (
        ("diffusion_models", settings.wan_high_model),
        ("diffusion_models", settings.wan_low_model),
        ("text_encoders", settings.wan_clip_model),
        ("vae", settings.wan_vae_model),
    ):
        target = settings.comfy_models_dir / folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"model")

    check = ModelManifest(settings).check_wan()

    assert not check.ok
    assert "loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" in check.detail


def test_wan_manifest_uses_5b_files_when_profile_selected(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        comfy_models_dir=tmp_path / "models",
        wan_profile="wan22_5b_ti2v",
    )
    check = ModelManifest(settings).check_wan()

    assert not check.ok
    assert "diffusion_models/wan2.2_ti2v_5B_fp16.safetensors" in check.detail
    assert "vae/wan2.2_vae.safetensors" in check.detail
    assert "loras/" not in check.detail


def test_ltx_manifest_accepts_fallback_lora(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        comfy_models_dir=tmp_path / "models",
        final_video_backend="ltx_ia2v",
    )
    for folder, name in (
        ("checkpoints", settings.ltx_checkpoint),
        ("text_encoders", settings.ltx_text_encoder),
        ("latent_upscale_models", settings.ltx_upscale_model),
        ("loras", settings.ltx_lora_fallback),
    ):
        target = settings.comfy_models_dir / folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"model")

    check = ModelManifest(settings).check_ltx_ia2v()

    assert check.ok
    assert f"using fallback LoRA {settings.ltx_lora_fallback}" in check.detail


def test_ltx_fast_manifest_does_not_require_lora(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        comfy_models_dir=tmp_path / "models",
        final_video_backend="ltx_ia2v",
        ltx_profile="fast",
    )

    check = ModelManifest(settings).check_ltx_ia2v()

    assert not check.ok
    assert f"checkpoints/{settings.ltx_fast_checkpoint}" in check.detail
    assert "loras/" not in check.detail


def test_wan_download_uses_model_local_temp_dir(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path / "data",
        comfy_models_dir=tmp_path / "models",
        model_downloads_enabled=True,
        wan_profile="wan22_5b_ti2v",
    )
    seen_local_dirs = []

    def fake_hf_hub_download(repo_id, filename, local_dir):
        source = local_dir / filename
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"model")
        seen_local_dirs.append(local_dir)
        return str(source)

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=fake_hf_hub_download))

    ModelManifest(settings)._download_wan()

    assert (settings.comfy_models_dir / "diffusion_models" / settings.wan_5b_model).read_bytes() == b"model"
    assert (settings.comfy_models_dir / "text_encoders" / settings.wan_clip_model).exists()
    assert (settings.comfy_models_dir / "vae" / settings.wan_5b_vae_model).exists()
    assert seen_local_dirs
    assert all(settings.comfy_models_dir in local_dir.parents for local_dir in seen_local_dirs)
    assert not list(settings.comfy_models_dir.glob("**/.hf-downloads"))


def test_tts_download_targets_configured_model_dir(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path / "data",
        tts_backend="native",
        tts_root=tmp_path / "engines" / "cosyvoice",
        tts_model_dir=tmp_path / "models" / "cosyvoice" / "CosyVoice2-0.5B",
        tts_python="../runtime/cosyvoice-python/python.exe",
    )
    settings.tts_root.mkdir(parents=True)
    captured = {}

    def fake_run(self, cmd, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd

    monkeypatch.setattr(ModelManifest, "_run", fake_run)

    ModelManifest(settings)._download_tts()

    assert captured["cmd"][:2] == [settings.tts_python, "-c"]
    assert repr(str(settings.tts_model_dir.resolve())) in captured["cmd"][2]
    assert captured["cwd"] == settings.tts_root


def test_http_tts_is_external_not_local_install(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", tts_backend="http", tts_manage_http_service=False)
    manager = ServiceManager(settings)

    assert manager._installed("cosyvoice")
    assert not manager._startable("cosyvoice")


def test_ltx_backend_hides_musetalk_from_service_status(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", final_video_backend="ltx_ia2v")
    manifest = service_manifest(settings)
    manager = ServiceManager(settings)

    assert "musetalk" not in {item["name"] for item in manifest["services"]}
    assert "musetalk" not in manager._visible_services()


def test_gpu_process_memory_na_is_not_displayed_as_value():
    item = _format_ai_process(
        {
            "pid": "123",
            "process_name": r"C:\Users\AIBOX\AppData\Roaming\uv\python\python.exe",
            "used_memory": "",
            "used_memory_mib": None,
            "memory_available": False,
        }
    )

    assert item["label"] == "ComfyUI"
    assert item["used_memory"] == ""
    assert item["used_memory_mib"] is None
    assert item["memory_available"] is False


def test_get_settings_can_load_portable_env_file(tmp_path, monkeypatch):
    env_path = tmp_path / "portable.env"
    env_path.write_text(
        "\n".join(
            [
                "APP_PROFILE=portable",
                "APP_PORT=9876",
                "DATA_DIR=" + str(tmp_path / "portable-data"),
                "MODEL_DOWNLOADS_ENABLED=true",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ECHOFRAME_ENV_FILE", str(env_path))
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.app_profile == "portable"
        assert settings.app_port == 9876
        assert settings.model_downloads_enabled
        assert settings.abs_data_dir == (tmp_path / "portable-data").resolve()
    finally:
        get_settings.cache_clear()
