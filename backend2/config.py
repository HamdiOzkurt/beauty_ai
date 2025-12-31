"""
Backend2 Configuration - Pydantic Settings
Reads environment variables from .env file
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# Get the directory where this config file is located
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Application Settings"""

    # API Keys
    GEMINI_API_KEY: str
    DIRECTUS_TOKEN: str

    # ElevenLabs TTS Settings (loaded via os.getenv)
    ELEVENLABS_API_KEY: Optional[str] = None
    ELEVENLABS_VOICE_ID: str = "IuRRIAcbQK5AQk1XevPj"  # Rachel voice (default) doa IuRRIAcbQK5AQk1XevPj  adeline Z3R5wn05IrDiVCyEkUrK
    ELEVENLABS_MODEL: str = "eleven_multilingual_v2"  # Best for Turkish

    # Directus CMS (All data managed through Directus)
    DIRECTUS_URL: str = "https://cms.demirtech.com"
    TENANT_ID: int = 1

    # Google Gemini Model
    AGENT_MODEL: str = "gemini-2.0-flash-exp"

    # Business Hours
    BUSINESS_HOURS_START: int = 9  # 09:00
    BUSINESS_HOURS_END: int = 19   # 19:00
    APPOINTMENT_SLOT_MINUTES: int = 30  # Her slot 30 dakika

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # CORS
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Logging
    LOG_LEVEL: str = "DEBUG"

    # Optional: Google Cloud Credentials path
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# Global settings instance
settings = Settings()

# Explicitly set GOOGLE_APPLICATION_CREDENTIALS environment variable
# This ensures the Google Cloud client can find the credentials
if settings.GOOGLE_APPLICATION_CREDENTIALS:
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = settings.GOOGLE_APPLICATION_CREDENTIALS

# Load ELEVENLABS_API_KEY from environment if not set in .env
if not settings.ELEVENLABS_API_KEY:
    settings.ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
