from app.core.config import Settings


def test_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "AI Career Agent"
    assert settings.environment == "local"
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_local_database_default_uses_compose_host_port(monkeypatch) -> None:
    from sqlalchemy.engine import make_url

    monkeypatch.delenv("AI_CAREER_AGENT_DATABASE_URL", raising=False)
    url = make_url(Settings(_env_file=None).database_url)
    assert (url.host, url.port) == ("localhost", 5432)


def test_database_environment_overrides_dotenv_and_unset_restores_it(monkeypatch, tmp_path) -> None:
    from sqlalchemy.engine import make_url

    local_url = "postgresql+asyncpg://test:test@localhost:5432/test"
    env_file = tmp_path / ".env"
    env_file.write_text(f"AI_CAREER_AGENT_DATABASE_URL={local_url}\n")
    monkeypatch.setenv(
        "AI_CAREER_AGENT_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:55432/test"
    )
    assert make_url(Settings(_env_file=env_file).database_url).port == 55432
    monkeypatch.delenv("AI_CAREER_AGENT_DATABASE_URL")
    assert Settings(_env_file=env_file).database_url == local_url


def test_docker_database_url_preserves_network_hostname(monkeypatch, tmp_path) -> None:
    from sqlalchemy.engine import make_url

    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_CAREER_AGENT_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test\n"
    )
    monkeypatch.setenv(
        "AI_CAREER_AGENT_DATABASE_URL", "postgresql+asyncpg://test:test@db:5432/test"
    )
    url = make_url(Settings(_env_file=env_file).database_url)
    assert (url.host, url.port) == ("db", 5432)
