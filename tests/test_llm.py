import asyncio
import json

from app.config import Settings
from app.modules.llm import LLMModule
from app.services.llm import LLMClient
from app.services.model_manifest import ModelManifest


def test_blank_llm_model_uses_loaded_lm_studio_model(monkeypatch, tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        llm_model="",
        llm_load_before_request=False,
        llm_unload_after_request=False,
        llm_allow_fallback=False,
    )
    client = LLMClient(settings)
    posted = {}

    async def active_model():
        return "google/gemma-4-31b"

    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "reply": "hello",
                                    "cosyvoice_instruct": "calm",
                                    "wan_prompt": "front-facing bust shot",
                                }
                            )
                        }
                    }
                ]
            }

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            posted["url"] = url
            posted["json"] = json
            return Response()

    client.active_model = active_model
    monkeypatch.setattr("app.services.llm.httpx.AsyncClient", AsyncClient)

    plan = asyncio.run(client.plan_reply("hi"))

    assert posted["json"]["model"] == "google/gemma-4-31b"
    assert plan["reply"] == "hello"


def test_blank_llm_model_does_not_require_lms_model_download(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", llm_model="")
    check = ModelManifest(settings).check_llm()

    assert check.ok
    assert "loaded LM Studio model" in check.detail


def test_llm_reply_is_normalized_to_simplified_chinese(tmp_path):
    client = LLMClient(Settings(data_dir=tmp_path / "data"))

    plan = client._normalize(
        {
            "reply": "\u9019\u662f\u4e00\u500b\u6e2c\u8a66\u3002",
            "cosyvoice_instruct": "\u81ea\u7136\u6e05\u6670",
            "wan_prompt": "front-facing bust shot",
        }
    )

    assert plan["reply"] == "\u8fd9\u662f\u4e00\u4e2a\u6d4b\u8bd5\u3002"
    assert plan["cosyvoice_instruct"] == "\u81ea\u7136\u6e05\u6670"


def test_video_prompt_adds_visible_motion_anchor(tmp_path):
    client = LLMClient(Settings(data_dir=tmp_path / "data"))

    prompt = client._sanitize_wan_prompt("Preserve the same identity as the reference image.")

    assert "Visible but realistic motion throughout" in prompt
    assert "mouth opens and closes naturally" in prompt
    assert "lips, jaw, cheeks, and chin move in sync" in prompt
    assert "locked-off camera" in prompt
    assert "consistent head size" in prompt
    assert "not a static portrait or frozen frame" in prompt
    assert "slight camera push-in" not in prompt
    assert "mild parallax" not in prompt
    assert "subtle blinking" not in prompt
    assert "slight nodding" not in prompt


def test_video_prompt_removes_zoom_terms(tmp_path):
    client = LLMClient(Settings(data_dir=tmp_path / "data"))

    prompt = client._sanitize_wan_prompt("front-facing bust shot, camera push-in, zoom in, cropped face")

    assert "camera push-in" not in prompt
    assert "zoom in" not in prompt
    assert "cropped face" not in prompt


def test_manual_reply_uses_motion_rich_video_prompt(tmp_path):
    module = LLMModule(Settings(data_dir=tmp_path / "data"))

    plan = module._manual_plan("hello")

    assert "Visible but realistic motion throughout" in plan["wan_prompt"]
    assert "small shoulder and torso shifts" in plan["wan_prompt"]


def test_video_prompt_for_reply_adds_spoken_line(tmp_path):
    client = LLMClient(Settings(data_dir=tmp_path / "data"))

    prompt = client.video_prompt_for_reply("base talking prompt", "你好，今天我们讲一个新方案。")

    assert 'The person clearly speaks this exact line from start to finish: "你好，今天我们讲一个新方案。"' in prompt
    assert "The mouth opens and closes naturally" in prompt
