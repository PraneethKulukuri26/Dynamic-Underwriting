"""
AIDUS Backend Configuration
Loads all settings from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Groq LLM ---
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model name")
    groq_temperature: float = Field(default=0.1, description="LLM temperature")
    groq_max_tokens: int = Field(default=4096, description="Max tokens per response")

    # --- Finexer Open Finance ---
    finexer_api_key: str = Field(default="", description="Finexer API key")
    finexer_base_url: str = Field(default="https://api.finexer.com/v1", description="Finexer API base URL")
    finexer_callback_url: str = Field(default="http://localhost:8000/api/v1/consent/callback", description="OAuth callback URL")

    # --- HaveIBeenPwned ---
    hibp_api_key: str = Field(default="", description="HIBP API key")
    hibp_base_url: str = Field(default="https://haveibeenpwned.com/api/v3", description="HIBP API base URL")

    # --- Digiverifier ---
    digiverifier_api_key: str = Field(default="", description="Digiverifier API key")
    digiverifier_base_url: str = Field(default="https://api.digiverifier.com/v1", description="Digiverifier API base URL")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://aidus:aidus_secret@postgres:5432/aidus_db",
        description="Async database connection URL"
    )

    # --- Redis ---
    redis_url: str = Field(default="redis://redis:6379/0", description="Redis connection URL")

    # --- Privacy ---
    default_epsilon: float = Field(default=1.0, description="Default LDP privacy budget epsilon")
    default_delta: float = Field(default=1e-5, description="Default LDP delta parameter")
    max_privacy_budget: float = Field(default=10.0, description="Maximum cumulative privacy budget")
    gradient_clip_norm: float = Field(default=1.0, description="L2 norm clipping threshold")

    # --- Application ---
    use_mock_data: bool = Field(default=True, description="Use mock data instead of real APIs")
    debug: bool = Field(default=True, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    app_host: str = Field(default="0.0.0.0", description="Server host")
    app_port: int = Field(default=8000, description="Server port")

    # --- Sherlock Docker ---
    sherlock_image: str = Field(default="sherlock/sherlock", description="Sherlock Docker image")
    sherlock_timeout: int = Field(default=60, description="Sherlock container timeout in seconds")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton settings instance
settings = Settings()
