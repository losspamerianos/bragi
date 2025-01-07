import aiohttp
import hashlib
import os
from typing import Dict, Optional
import aiofiles
import mimetypes

from ..config import settings

class StorageManager:
    def __init__(self):
        # Erstelle Verzeichnisstruktur falls nicht vorhanden
        os.makedirs(f"{settings.STORAGE_PATH}/originals", exist_ok=True)
        os.makedirs(f"{settings.STORAGE_PATH}/processed/avif", exist_ok=True)
        os.makedirs(f"{settings.STORAGE_PATH}/processed/webp", exist_ok=True)
        
    async def fetch_image(self, url: str) -> bytes:
        """Lädt ein Bild von einer URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as response:
                if response.status != 200:
                    raise ValueError(f"Fehler beim Laden des Bildes: {response.status}")
                    
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    raise ValueError(f"Ungültiger Content-Type: {content_type}")
                    
                return