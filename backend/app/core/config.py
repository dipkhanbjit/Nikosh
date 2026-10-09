from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Nikosh"
    app_env: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://nikosh:nikosh@localhost:5432/nikosh"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    jwt_secret_key: str = ""
    jwt_expire_minutes: int = 480
    cookie_secure: bool = False

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_cache_dir: str = ".cache/fastembed"
    kb_chunk_size: int = 800
    kb_chunk_overlap: int = 150
    kb_max_file_mb: int = 10
    tesseract_cmd: str | None = None
    telegram_bot_token: str = ""
    telegram_channel: str = ""
    google_oauth_client_file: str = "secrets/google-oauth-client.json"
    google_oauth_token_file: str = "secrets/google-oauth-token.json"
    google_form_template_id: str = ""
    company_name: str = "Nirvik Technology"
    form_check_interval_minutes: int = 5
    blogger_blog_id: str = ""
    cv_storage_dir: str = "storage/cvs"
    cv_max_file_mb: int = 10
    default_application_days: int = 21


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()