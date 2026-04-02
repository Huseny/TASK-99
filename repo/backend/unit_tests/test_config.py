from app.core.config import Settings


def test_settings_load_required_values() -> None:
    settings = Settings(database_url="sqlite:///test.db", secret_key="abc123456789")
    settings.validate_required()
    assert settings.api_port == 8000
