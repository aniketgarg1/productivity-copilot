from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BACKEND_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/copilot"
    SESSION_SECRET: str = "change-me"

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_PATH: str = "/auth/google/callback"


settings = Settings()
