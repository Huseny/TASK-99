from pathlib import Path

from app.core.config import Settings


def test_settings_load_required_values() -> None:
    settings = Settings(database_url="sqlite:///test.db", secret_key="1234567890abcdefghijklmnAB")
    settings.validate_required()
    assert settings.api_port == 8000


def test_settings_parse_cors_origins_from_csv() -> None:
    settings = Settings(database_url="sqlite:///test.db", secret_key="1234567890abcdefghijklmnAB", cors_origins="https://a.test, https://b.test")
    assert settings.cors_origins == ["https://a.test", "https://b.test"]


def test_settings_reject_wildcard_cors_and_weak_secret() -> None:
    try:
        Settings(database_url="sqlite:///test.db", secret_key="weak", cors_origins="*")
    except Exception as exc:
        message = str(exc)
        assert "SECRET_KEY" in message or "secret_key" in message
    else:
        raise AssertionError("Expected settings validation to fail for weak secret and wildcard CORS.")


def test_documented_default_secret_meets_validation_requirements() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env_example = (repo_root / ".env.example").read_text(encoding="utf-8")
    secret_line = next(line for line in env_example.splitlines() if line.startswith("SECRET_KEY="))
    secret_value = secret_line.split("=", 1)[1]
    docker_compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    assert secret_value in docker_compose
    settings = Settings(database_url="sqlite:///test.db", secret_key=secret_value)
    settings.validate_required()
    assert len(settings.secret_key) >= 24
