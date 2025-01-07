from typing import List
import os
from pydantic import BaseModel

class Settings(BaseModel):
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    STORAGE_PATH: str = "/app/storage"
    MAX_FILE_SIZE: int = 10
    
    # Image Processing Settings
    SUPPORTED_FORMATS: List[str] = ["jpg", "jpeg", "png", "webp"]
    DEFAULT_SIZES: List[int] = [1920, 1280, 800]
    AVIF_EFFORT: int = 2
    MAX_WORKERS: int = 2

    # Duplicate Detection Settings
    PHASH_THRESHOLD: float = 0.85
    HISTOGRAM_THRESHOLD: float = 0.90
    COMBINED_THRESHOLD: float = 0.85

    @property
    def allowed_hosts_list(self) -> List[str]:
        return [host.strip() for host in self.ALLOWED_HOSTS.split(",")]

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",")]

def get_settings():
    return Settings(
        DEBUG=os.getenv("DEBUG", "False").lower() == "true",
        HOST=os.getenv("HOST", "0.0.0.0"),
        PORT=int(os.getenv("PORT", "8000")),
        ALLOWED_HOSTS=os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1"),
        CORS_ALLOWED_ORIGINS=os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"),
        SECRET_KEY=os.getenv("SECRET_KEY", "your_secret_key"),
        STORAGE_PATH=os.getenv("STORAGE_PATH", "/app/storage"),
        MAX_FILE_SIZE=int(os.getenv("MAX_FILE_SIZE", "10"))
    )

settings = get_settings()