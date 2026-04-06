from pydantic import field_validator
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
    integration_secret_enc_key: str | None = None
    messaging_poller_enabled: bool = True
    messaging_poller_interval_seconds: int = 30
    cors_origins: list[str] = []
    bootstrap_admin_token: str | None = None

    web_api_base_url: str = "/api/v1"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors_origins(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("Wildcard CORS origins are not allowed.")
        return value

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, value: str) -> str:
        if not value or len(value) < 24:
            raise ValueError("SECRET_KEY must be at least 24 characters long.")
        lowered = value.strip().lower()
        if lowered in {"secret", "changeme", "default-secret", "development-secret", "dev-secret"}:
            raise ValueError("SECRET_KEY is too weak.")
        return value

    def validate_required(self) -> None:
        required = {
            "DATABASE_URL": self.database_url,
            "SECRET_KEY": self.secret_key,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


settings = Settings()
