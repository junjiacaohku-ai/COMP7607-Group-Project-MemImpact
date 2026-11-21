import os

from dotenv import load_dotenv

REASONING_EFFORT_ENV = "MEMIMPACT_REASONING_EFFORT"
REASONING_PROVIDERS = frozenset({"ollama", "openai"})


def reasoning_effort_value(thinking: bool) -> str | None:
    """Map the project thinking flag onto reasoning_effort.

    Thinking off always requests ``none``. Thinking on uses
    ``MEMIMPACT_REASONING_EFFORT`` when set, and otherwise leaves the field
    unset so the model default applies.
    """
    if not thinking:
        return "none"
    load_dotenv()
    effort = os.environ.get(REASONING_EFFORT_ENV, "").strip()
    return effort or None


def recorded_thinking(provider: str, thinking: bool) -> tuple[bool, str | None]:
    """Return the thinking flag and effort that match the provider request.

    Qwen does not send ``reasoning_effort``. For Ollama and OpenAI, ``none``
    is recorded as thinking off, including when the env var overrides a
    thinking-on run.
    """
    if provider not in REASONING_PROVIDERS:
        return thinking, None
    effort = reasoning_effort_value(thinking)
    if effort == "none":
        return False, effort
    return True, effort
