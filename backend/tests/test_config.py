import pytest
from app.config import Settings


def test_database_url_has_no_implicit_sqlite_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Settings(_env_file=None)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        config.require_database_url()


def test_isolated_tests_can_choose_sqlite_explicitly() -> None:
    config = Settings(database_url="sqlite:///:memory:", _env_file=None)
    assert config.require_database_url() == "sqlite:///:memory:"
