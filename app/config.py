# config.py

from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    STORAGE_PATH: str = "/app/storage"
    MAX_FILE_SIZE: int = 10
    BRAGI_SECRET_KEY: str = os.getenv("BRAGI_SECRET_KEY")

    # Image Processing Settings
    SUPPORTED_FORMATS: List[str] = ["jpg", "jpeg", "png", "webp"]
    DEFAULT_SIZES: List[int] = [1920, 1280, 800]
    AVIF_EFFORT: int = 2
    MAX_WORKERS: int = 2

    # Duplicate Detection Settings
    PHASH_THRESHOLD: float = 0.85
    HISTOGRAM_THRESHOLD: float = 0.90
    COMBINED_THRESHOLD: float = 0.85

    class Config:
        # Point Pydantic to your .env file
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def allowed_hosts_list(self) -> List[str]:
        return [host.strip() for host in self.ALLOWED_HOSTS.split(",")]

    @property
    def cors_origins_list(self):
        raw_origins = [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",")]
        if "*" in raw_origins:
            return ["*"]  # Alle erlauben
        return raw_origins

# Instantiate the settings
settings = Settings()