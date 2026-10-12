from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings


@lru_cache
def get_llm(temperature: float | None = None) -> ChatGoogleGenerativeAI:
    """Gemini client. Pass temperature=0 for consistent, repeatable outputs (e.g. scoring)."""
    options = {"temperature": temperature} if temperature is not None else {}
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        max_retries=6,
        **options,
    )