from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://barber:barber@localhost:5410/barber_shop"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    app_base_url: str = "http://localhost:8000"
    business_open_hour: int = 9
    business_close_hour: int = 19
    min_cancel_hours: int = 2
    reminder_hours_before: int = 24


settings = Settings()
