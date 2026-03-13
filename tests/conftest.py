"""Global test configuration — force rule-based mode, no network calls."""
import os


def pytest_configure(config):
    """Run before test collection/imports: disable LLM keys so all agents use rule-based fallback.

    This prevents real OpenRouter/OpenAI API calls (15-30s timeouts per model)
    from turning a 3-minute test suite into a 30-minute one.
    """
    os.environ["OPENROUTER_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""
