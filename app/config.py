from pydantic_settings import BaseSettings
from typing import List
from pydantic import ConfigDict
import os

class Settings(BaseSettings):
    # Server Config
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    
    # Security
    BRAGI_SECRET_KEY: str = os.getenv("BRAGI_SECRET_KEY")
    
    # Storage Config
    STORAGE_PATH: str = "/app/storage"
    PROCESSED_PATH: str = "/app/storage/processed"
    MAX_FILE_SIZE: int = 10

    # Service URLs
    REDIS_URL: str = "redis://redis:6379"
    RABBITMQ_URL: str = "amqp://user:password@rabbitmq:5672/"
    
    # Image Processing Settings
    SUPPORTED_FORMATS: List[str] = ["jpg", "jpeg", "png", "webp"]
    DEFAULT_SIZES: List[int] = [1920, 1280, 800]
    AVIF_EFFORT: int = 2
    MAX_WORKERS: int = 2
    
    # Queue Processing Config
    MAX_CONCURRENT_TASKS: int = 5
    TASK_TIMEOUT: int = 300  # 5 minutes
    
    # Duplicate Detection Settings
    PHASH_THRESHOLD: float = 0.85
    HISTOGRAM_THRESHOLD: float = 0.90
    COMBINED_THRESHOLD: float = 0.85

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow"  # Erlaubt zusätzliche Felder
    )

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