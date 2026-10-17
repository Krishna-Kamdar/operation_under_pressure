from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://ops_pressure:ops_pressure_dev"
        "@localhost:5433/ops_pressure"
    )
    app_env: str = "development"
    jwt_secret: str = "replace-this-for-local-development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
