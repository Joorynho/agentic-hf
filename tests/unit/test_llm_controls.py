import pytest
from types import SimpleNamespace

from src.core import llm


class _FakeClient:
    def __init__(self, text: str = "ok"):
        self.text = text
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=self.text))
            ]
        )


@pytest.fixture(autouse=True)
def reset_llm_router_state(monkeypatch):
    llm._last_success_model = None
    llm._last_success_openai_model.clear()
    llm._openrouter_exhausted = False
    llm._openrouter_reset = 0.0
    llm._openai_exhausted = False
    llm._openai_reset = 0.0
    for name in [
        "LLM_PROVIDER_ORDER",
        "OPENAI_MODEL",
        "OPENAI_MODEL_DEFAULT",
        "OPENAI_MODEL_STRONG",
        "OPENAI_MODEL_FRONTIER",
        "OPENAI_MODEL_PM_DECISION",
    ]:
        monkeypatch.delenv(name, raising=False)


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


def test_openai_default_task_uses_gpt5_mini(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    assert llm.llm_chat([{"role": "user", "content": "score"}], task=llm.LLMTask.SENTIMENT) == "ok"
    assert fake.calls[0]["model"] == "gpt-5-mini"


def test_openai_pm_decision_uses_stronger_model(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    llm.llm_chat([{"role": "user", "content": "trade"}], task=llm.LLMTask.PM_DECISION)

    assert fake.calls[0]["model"] == "gpt-5"


def test_openai_position_review_uses_frontier_model(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    llm.llm_chat([{"role": "user", "content": "review"}], task=llm.LLMTask.POSITION_REVIEW)

    assert fake.calls[0]["model"] == "gpt-5.2"


def test_task_specific_openai_override_wins(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setenv("OPENAI_MODEL_PM_DECISION", "gpt-custom-trader")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    llm.llm_chat([{"role": "user", "content": "trade"}], task=llm.LLMTask.PM_DECISION)

    assert fake.calls[0]["model"] == "gpt-custom-trader"


def test_openai_is_preferred_when_both_keys_are_available(monkeypatch):
    openai_fake = _FakeClient()
    openrouter_fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setenv("OPENROUTER_API_KEY", "present")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: openai_fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: openrouter_fake)

    llm.llm_chat([{"role": "user", "content": "hello"}])

    assert openai_fake.calls
    assert not openrouter_fake.calls
