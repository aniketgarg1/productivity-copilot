import os

from app.llm.openai_provider import OpenAILLM


def get_llm():
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        model_main = os.environ.get("OPENAI_MODEL_MAIN", "gpt-4.1-mini-2025-04-14")
        model_cheap = os.environ.get("OPENAI_MODEL_CHEAP", "gpt-4.1-nano-2025-04-14")
        return OpenAILLM(model_main=model_main, model_cheap=model_cheap)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")