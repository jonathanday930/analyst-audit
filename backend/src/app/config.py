from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str | None = None
    database_url: str = "sqlite:///./analyst_audit.db"
    port: int = 8000
    frontend_url: str = "http://localhost:5173"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Make Fly-style PostgreSQL URLs explicitly select psycopg 3."""
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
