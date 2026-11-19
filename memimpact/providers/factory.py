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


def resolve_provider(provider: str | None) -> str:
    """Pick provider from CLI/YAML, else ``MEMIMPACT_PROVIDER``, else ``qwen``."""
    load_dotenv()
    if provider is not None and provider.strip():
        name = provider.strip().lower()
    else:
        name = os.environ.get(PROVIDER_ENV, DEFAULT_PROVIDER).strip().lower()
    if name not in PROVIDER_NAMES:
        raise ValueError(
            f"Unknown provider {name!r}. Expected one of: {', '.join(PROVIDER_NAMES)}"
        )
    return name


def resolve_model(provider: str, model: str | None) -> str:
    """Pick a usable model name for the selected provider.

    Priority:
    1. Explicit ``model`` argument (CLI / YAML), unless it is the Qwen cloud default
       while ``provider`` is ``ollama`` or ``openai`` (treat as unset so local/env
       default wins).
    2. Provider env: ``QWEN_MODEL``, ``OLLAMA_MODEL``, or ``OPENAI_MODEL``.
    3. Built-in defaults: ``qwen3.8-flash`` / ``qwen3.8:27b`` / ``gpt-6-luna``.
    """
    load_dotenv()
    name = provider.strip().lower()
    explicit = model
    if name in ("ollama", "openai") and explicit == DEFAULT_QWEN_MODEL:
        explicit = None
    if explicit is not None:
        return explicit
    if name == "ollama":
        return os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    if name == "openai":
        return os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    return os.environ.get("QWEN_MODEL", DEFAULT_QWEN_MODEL)
