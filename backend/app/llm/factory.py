from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLM
from app.llm.openai_provider import OpenAILLM


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    """
    Return the configured LLM client.

    Cached: building a fresh HTTP client on every request leaks connections
    and adds TLS handshakes to each call.
    """
    provider = (settings.LLM_PROVIDER or "openai").lower()

    if provider == "openai":
        return OpenAILLM(
            api_key=settings.OPENAI_API_KEY or "",
            model_main=settings.OPENAI_MODEL_MAIN,
            model_cheap=settings.OPENAI_MODEL_CHEAP,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
