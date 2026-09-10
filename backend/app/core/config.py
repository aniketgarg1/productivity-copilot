from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/copilot"
    SESSION_SECRET: str = "change-me"

    # Set to false behind HTTPS in production so cookies get the Secure flag.
    DEV_MODE: bool = True

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_PATH: str = "/auth/google/callback"
    TIMEZONE: str = "America/Phoenix"
    WORKDAY_START_HOUR: int = 9
    WORKDAY_END_HOUR: int = 18
    SLOT_PADDING_MINUTES: int = 5

    # LLM
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL_MAIN: str = "gpt-4.1-mini-2025-04-14"
    OPENAI_MODEL_CHEAP: str = "gpt-4.1-nano-2025-04-14"
    OPENAI_TRANSCRIBE_MODEL: str = "whisper-1"

    # Twilio (for daily check-in calls)
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_PHONE_NUMBER: str | None = None
    # Twilio signs every webhook request; only disable for local testing.
    TWILIO_VALIDATE_SIGNATURE: bool = True

    # Daily check-in defaults
    DAILY_CHECKIN_HOUR: int = 9
    DAILY_CHECKIN_ENABLED: bool = True

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.FRONTEND_URL.rstrip("/")}
        if self.DEV_MODE:
            origins.add("http://localhost:3000")
            origins.add("http://127.0.0.1:3000")
        return sorted(origins)

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.BACKEND_URL.rstrip('/')}/{self.GOOGLE_REDIRECT_PATH.lstrip('/')}"

    @property
    def backend_is_public(self) -> bool:
        """True when Twilio can reach BACKEND_URL (i.e. not a loopback address)."""
        host = self.BACKEND_URL.lower()
        return not any(h in host for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1"))


settings = Settings()
