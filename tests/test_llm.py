import asyncio
import json

from app.config import Settings
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
