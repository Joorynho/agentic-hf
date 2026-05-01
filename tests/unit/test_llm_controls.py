import pytest

from src.core import llm


def test_has_llm_key_respects_disable_flag(monkeypatch):
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "present")
    monkeypatch.setenv("OPENAI_API_KEY", "present")

    assert llm.has_llm_key() is False


def test_llm_chat_fails_fast_when_disabled(monkeypatch):
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "present")
    monkeypatch.setenv("OPENAI_API_KEY", "present")

    with pytest.raises(RuntimeError, match="disabled"):
        llm.llm_chat([{"role": "user", "content": "hello"}])
