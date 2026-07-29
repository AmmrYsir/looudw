import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "loouwd API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Cache Settings
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 300
    CACHE_MAXSIZE: int = 1000

    # HTTP Client & Network Settings
    HTTP_TIMEOUT_SECONDS: float = 15.0
    HTTP_MAX_CONNECTIONS: int = 100
    HTTP_MAX_KEEPALIVE_CONNECTIONS: int = 20
    DEFAULT_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    PROXY_URL: str | None = None

    # Rate Limit Settings
    RATE_LIMIT_PER_MINUTE: int = 120  # Set to 0 to disable rate limiting


settings = Settings()
