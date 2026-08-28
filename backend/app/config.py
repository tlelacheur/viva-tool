import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    ANALYSIS_MODEL: str = "anthropic/claude-3.5-sonnet"
    EVALUATION_MODEL: str = "anthropic/claude-3.5-sonnet"

    LIVEKIT_URL: str = "wss://your-project.livekit.cloud"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "secret"

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    STORAGE_PATH: str = "./data/uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure storage path directory exists or fallback to local directory
storage_dir = Path(settings.STORAGE_PATH)
try:
    storage_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    storage_dir = Path("./data/uploads")
    storage_dir.mkdir(parents=True, exist_ok=True)
