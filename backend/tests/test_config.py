from app.config import Settings


def test_fly_database_urls_select_psycopg3() -> None:
    assert Settings(database_url="postgres://u:p@host/db").sqlalchemy_database_url == "postgresql+psycopg://u:p@host/db"
    assert Settings(database_url="postgresql://u:p@host/db").sqlalchemy_database_url == "postgresql+psycopg://u:p@host/db"


def test_explicit_driver_and_sqlite_urls_are_unchanged() -> None:
    assert Settings(database_url="postgresql+psycopg://u:p@host/db").sqlalchemy_database_url.startswith("postgresql+psycopg://")
    assert Settings(database_url="sqlite:///x.db").sqlalchemy_database_url == "sqlite:///x.db"
