from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    openrouter_api_key: str | None = None

    # Which OpenRouter model to use. Override with OPENROUTER_MODEL in .env to try a
    # different one without touching code. The default is the model this project was
    # built and tested against.
    openrouter_model: str = "dots-studio/dots-3-note-preview:free"

    # Relative to the working directory, which is /app in the image. The compose file
    # mounts a volume there so the board survives `docker compose down`.
    database_path: str = "./data/app.db"

    # Signs the session cookie. The default is fine for a local-only MVP and is
    # deliberately obvious so nobody ships it. docker-compose passes a real value from
    # SESSION_SECRET, and any deployment reachable by others must set it.
    session_secret: str = "dev-insecure-secret-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
