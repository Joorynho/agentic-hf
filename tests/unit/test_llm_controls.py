import pytest
from types import SimpleNamespace

from src.core import llm


class _FakeClient:
    def __init__(self, text: object = "ok"):
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


class _SequenceFakeClient:
    def __init__(self, texts: list[object]):
        self.texts = list(texts)
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.texts.pop(0) if self.texts else ""
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=text))
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
    llm._llm_call_log.clear()
    for name in [
        "LLM_PROVIDER_ORDER",
        "OPENAI_MODEL",
        "OPENAI_MODEL_DEFAULT",
        "OPENAI_MODEL_STRONG",
        "OPENAI_MODEL_FRONTIER",
        "OPENAI_MODEL_PM_DECISION",
        "OPENAI_GPT5_DEFAULT_MIN_COMPLETION_TOKENS",
        "OPENAI_GPT5_STRONG_MIN_COMPLETION_TOKENS",
        "OPENAI_GPT5_FRONTIER_MIN_COMPLETION_TOKENS",
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


def test_openai_gpt5_family_uses_max_completion_tokens(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    llm.llm_chat([{"role": "user", "content": "review"}], max_tokens=321, task=llm.LLMTask.POSITION_REVIEW)

    assert fake.calls[0]["model"] == "gpt-5.2"
    assert fake.calls[0]["max_completion_tokens"] >= 321
    assert "max_tokens" not in fake.calls[0]


def test_openai_gpt5_frontier_task_uses_completion_budget_floor(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setenv("OPENAI_GPT5_FRONTIER_MIN_COMPLETION_TOKENS", "1200")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    llm.llm_chat([{"role": "user", "content": "review"}], max_tokens=100, task=llm.LLMTask.POSITION_REVIEW)

    assert fake.calls[0]["model"] == "gpt-5.2"
    assert fake.calls[0]["max_completion_tokens"] == 1200


def test_openai_legacy_chat_model_uses_max_tokens(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setenv("OPENAI_MODEL_DEFAULT", "gpt-4o-mini")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    llm.llm_chat([{"role": "user", "content": "score"}], max_tokens=123, task=llm.LLMTask.SENTIMENT)

    assert fake.calls[0]["model"] == "gpt-4o-mini"
    assert fake.calls[0]["max_tokens"] == 123
    assert "max_completion_tokens" not in fake.calls[0]


def test_extract_chat_completion_text_handles_content_parts():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=[
                        {"type": "text", "text": "hello"},
                        SimpleNamespace(text=" world"),
                    ]
                )
            )
        ]
    )

    assert llm._extract_chat_completion_text(response) == "hello world"


def test_openai_empty_200_tries_next_model_and_records_why(monkeypatch):
    fake = _SequenceFakeClient(["", "usable"])
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    result = llm.llm_chat([{"role": "user", "content": "review"}], task=llm.LLMTask.POSITION_REVIEW)

    assert result == "usable"
    assert fake.calls[0]["model"] == "gpt-5.2"
    assert fake.calls[1]["model"] == "gpt-5"
    rows = llm.get_recent_llm_calls(5)
    assert any(
        row["provider"] == "openai"
        and row["model"] == "gpt-5.2"
        and row["status"] == "empty_response"
        for row in rows
    )
    assert llm.get_last_llm_call(llm.LLMTask.POSITION_REVIEW)["model"] == "gpt-5"


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


def test_llm_health_records_successful_model_call(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setenv("MISSION_CONTROL_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setattr(llm, "_get_openai_client", lambda: fake)
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda: None)

    llm.llm_chat([{"role": "user", "content": "trade"}], task=llm.LLMTask.PM_DECISION)

    last = llm.get_last_llm_call(llm.LLMTask.PM_DECISION)
    health = llm.get_llm_health_report()
    assert last["model"] == "gpt-5"
    assert last["provider"] == "openai"
    assert last["status"] == "success"
    assert health["by_model"][0]["successes"] == 1
