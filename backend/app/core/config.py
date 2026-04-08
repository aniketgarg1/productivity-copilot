from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BACKEND_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/copilot"
    SESSION_SECRET: str = "change-me"

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_PATH: str = "/auth/google/callback"
    TIMEZONE: str = "America/Phoenix"
    WORKDAY_START_HOUR: int = 9
    WORKDAY_END_HOUR: int = 18
    SLOT_PADDING_MINUTES: int = 5

    # Twilio (for daily check-in calls)
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_PHONE_NUMBER: str | None = None

    # Daily check-in defaults
    DAILY_CHECKIN_HOUR: int = 9
    DAILY_CHECKIN_ENABLED: bool = True

settings = Settings()
