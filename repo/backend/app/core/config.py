from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    database_url: str
    secret_key: str

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    bcrypt_rounds: int = 12
    session_idle_timeout: int = 28800
    session_absolute_timeout: int = 86400

    late_fee_rate: float = 0.015
    grace_period_days: int = 10
    rate_limit_rpm: int = 120
    hmac_timestamp_tolerance: int = 300
    dedup_threshold: float = 0.92

    web_api_base_url: str = "/api/v1"

    def validate_required(self) -> None:
        required = {
            "DATABASE_URL": self.database_url,
            "SECRET_KEY": self.secret_key,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


settings = Settings()
