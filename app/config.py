from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    STORAGE_PATH: str = "/app/storage"
    MAX_FILE_SIZE: int = 10  # MB
    
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
        env_file = ".env"

settings = Settings()