import os

from openai import OpenAI


def make_qwen_client() -> OpenAI:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not set")

    base_url = os.environ.get("DASHSCOPE_BASE_URL")
    if not base_url:
        workspace_id = os.environ.get("DASHSCOPE_WORKSPACE_ID")
        if not workspace_id:
            raise RuntimeError(
                "Set DASHSCOPE_WORKSPACE_ID or provide the full DASHSCOPE_BASE_URL"
            )
        region = os.environ.get("DASHSCOPE_REGION", "cn-beijing")
        base_url = (
            f"https://{workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1"
        )

    return OpenAI(api_key=api_key, base_url=base_url)
