# config.py

from pydantic import BaseSettings
from typing import List

class Settings(BaseSettings):
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    STORAGE_PATH: str = "/app/storage"
    MAX_FILE_SIZE: int = 10
    SECRET_KEY: str = "your_secret_key"

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

    def cors_origins_list(self) -> List[str]:
        """
        Zerlegt die Komma-separierte Liste aus der .env.
        Wenn du * in der .env erlauben willst, kannst du hier
        z. B. eine Abfrage einbauen, um 'allow_origins = ["*"]' zu ermöglichen.
        """
        raw_origins = [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",")]

        # Beispiel: Unterstützung für einen Eintrag "*" in der .env
        if "*" in raw_origins:
            return ["*"]
        return raw_origins

# Instantiate the settings
settings = Settings()