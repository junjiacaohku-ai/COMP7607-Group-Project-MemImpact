import os

from dotenv import load_dotenv

from memimpact.providers.base import LLMProvider
from memimpact.providers.ollama import OllamaProvider
from memimpact.providers.openai import OpenAIProvider
from memimpact.providers.qwen import QwenProvider

PROVIDER_NAMES = ("qwen", "ollama", "openai")
DEFAULT_PROVIDER = "qwen"
DEFAULT_QWEN_MODEL = "qwen3.8-flash"
DEFAULT_OLLAMA_MODEL = "qwen3.8:27b"
DEFAULT_OPENAI_MODEL = "gpt-6-luna"
PROVIDER_ENV = "MEMIMPACT_PROVIDER"
MODEL_ENV = {
    "qwen": "QWEN_MODEL",
    "ollama": "OLLAMA_MODEL",
    "openai": "OPENAI_MODEL",
}
DEFAULT_MODELS = {
    "qwen": DEFAULT_QWEN_MODEL,
    "ollama": DEFAULT_OLLAMA_MODEL,
    "openai": DEFAULT_OPENAI_MODEL,
}


def create_provider(provider: str) -> LLMProvider:
    name = provider.strip().lower()
    if name == "qwen":
        return QwenProvider()
    if name == "ollama":
        return OllamaProvider()
    if name == "openai":
        return OpenAIProvider()
    raise ValueError(
        f"Unknown provider {provider!r}. Expected one of: {', '.join(PROVIDER_NAMES)}"
    )


def resolve_provider(
    provider: str | None, *, fallback: str | None = None
) -> str:
    """Pick provider: CLI, else env if set, else fallback, else ``qwen``."""
    load_dotenv()
    if provider is not None and provider.strip():
        name = provider.strip().lower()
    elif (env := os.environ.get(PROVIDER_ENV, "").strip()):
        name = env.lower()
    elif fallback is not None and fallback.strip():
        name = fallback.strip().lower()
    else:
        name = DEFAULT_PROVIDER
    if name not in PROVIDER_NAMES:
        raise ValueError(
            f"Unknown provider {name!r}. Expected one of: {', '.join(PROVIDER_NAMES)}"
        )
    return name


def _model_env_value(provider: str) -> str | None:
    key = MODEL_ENV[provider]
    value = os.environ.get(key)
    if value is None or not value.strip():
        return None
    return value.strip()


def resolve_model(
    provider: str,
    model: str | None,
    *,
    fallback: str | None = None,
) -> str:
    """Pick a usable model name for the selected provider.

    Priority:
    1. Explicit ``model`` argument (CLI), unless it is the Qwen cloud default
       while ``provider`` is ``ollama`` or ``openai`` (treat as unset so
       env/fallback/default can win).
    2. Provider env if set: ``QWEN_MODEL``, ``OLLAMA_MODEL``, or ``OPENAI_MODEL``.
    3. ``fallback`` (e.g. experiment YAML ``model``), with the same Qwen-default
       strip for ``ollama`` / ``openai``.
    4. Built-in defaults: ``qwen3.8-flash`` / ``qwen3.8:27b`` / ``gpt-6-luna``.
    """
    load_dotenv()
    name = provider.strip().lower()
    if name not in PROVIDER_NAMES:
        raise ValueError(
            f"Unknown provider {name!r}. Expected one of: {', '.join(PROVIDER_NAMES)}"
        )

    def usable(value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        explicit = value.strip()
        if name in ("ollama", "openai") and explicit == DEFAULT_QWEN_MODEL:
            return None
        return explicit

    if (chosen := usable(model)) is not None:
        return chosen
    if (env_model := _model_env_value(name)) is not None:
        return env_model
    if (chosen := usable(fallback)) is not None:
        return chosen
    return DEFAULT_MODELS[name]
