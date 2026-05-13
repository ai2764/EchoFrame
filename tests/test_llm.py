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


def test_prompt_has_no_fixed_persona_and_matches_input_language():
    client = LLMClient(Settings(data_dir="data_test"))
    prompt = client._prompt("What is local AI?")
    assert "Chinese AI-news commentator" not in prompt
    assert "Do not add a persona" in prompt
    assert "same language as the user's input" in prompt


def test_fallback_uses_english_for_english_input():
    client = LLMClient(Settings(data_dir="data_test"))
    data = client._fallback("What is local AI?")
    assert data["reply"].startswith("I understand")
    assert data["cosyvoice_instruct"] == "calm, natural, clear"
