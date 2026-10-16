from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings


@lru_cache
def get_llm(temperature: float | None = None, max_retries: int = 6) -> ChatGoogleGenerativeAI:
    """Gemini client. Pass temperature=0 for consistent, repeatable outputs (e.g. scoring).
    Pass a small max_retries where a quick error beats a long wait (e.g. the live co-pilot)."""
    options = {"temperature": temperature} if temperature is not None else {}
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        max_retries=max_retries,
        **options,
    )