from app.core.config import Settings


def test_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "AI Career Agent"
    assert settings.environment == "local"
    assert settings.database_url.startswith("postgresql+asyncpg://")
