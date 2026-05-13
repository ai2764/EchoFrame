from app.config import Settings
from app.services.llm import LLMClient


def test_wan_prompt_sanitizer_removes_mouth_conflicts():
    client = LLMClient(Settings(data_dir="data_test"))
    prompt = client._sanitize_wan_prompt("wide open mouth, yelling, front facing")
    assert "wide open mouth" not in prompt.lower()
    assert "yelling" not in prompt.lower()
    assert "preserve" in prompt.lower()


def test_fallback_has_required_fields():
    client = LLMClient(Settings(data_dir="data_test"))
    data = client._normalize({})
    assert data["reply"]
    assert data["cosyvoice_instruct"]
    assert data["wan_prompt"]

