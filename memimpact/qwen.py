"""Deprecated compatibility shim. Prefer memimpact.providers.create_provider."""

from openai import OpenAI

from memimpact.providers.factory import create_provider


def make_qwen_client() -> OpenAI:
    return create_provider("qwen").as_openai_client()
