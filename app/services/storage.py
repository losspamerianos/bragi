# ---------------------------------------------------
# Storage
# /services/storage.py
# ---------------------------------------------------
import aiohttp
import hashlib
import os
from typing import Dict, Optional
import aiofiles # type: ignore
import mimetypes
from pathlib import Path

from ..config import settings

class StorageManager:
    def __init__(self):
        # Basis-Verzeichnisse
        os.makedirs(f"{settings.STORAGE_PATH}/originals", exist_ok=True)
        
        # Verzeichnisse für jedes Format und Größe
        for format_type in ['avif', 'webp']:
            base_path = f"{settings.STORAGE_PATH}/processed/{format_type}"
            os.makedirs(base_path, exist_ok=True)
            # Erstelle Unterverzeichnisse für DEFAULT_SIZES
            for size in settings.DEFAULT_SIZES:
                os.makedirs(f"{base_path}/{size}", exist_ok=True)

    async def fetch_image(self, url: str) -> bytes:
        """Lädt ein Bild von einer URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(str(url)) as response:
                if response.status != 200:
                    raise ValueError(f"Fehler beim Laden des Bildes: {response.status}")
                    
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    raise ValueError(f"Ungültiger Content-Type: {content_type}")
                    
                return await response.read()

    def optimized_exists(self, image_hash: str, size: Optional[int] = None) -> bool:
        """Prüft ob bereits optimierte Versionen existieren"""
        if size:
            avif_path = Path(f"{settings.STORAGE_PATH}/processed/avif/{size}/{image_hash}.avif")
            webp_path = Path(f"{settings.STORAGE_PATH}/processed/webp/{size}/{image_hash}.webp")
        else:
            avif_path = Path(f"{settings.STORAGE_PATH}/processed/avif/{image_hash}.avif")
            webp_path = Path(f"{settings.STORAGE_PATH}/processed/webp/{image_hash}.webp")
        return avif_path.exists() and webp_path.exists()

    def get_optimized_url(self, image_hash: str, format_type: str = 'avif', size: Optional[int] = None) -> str:
        """Gibt die URL der optimierten Version zurück"""
        # Entferne doppelte Slashes und trailing slashes
        base_url = settings.HOST.rstrip('/')
        
        if format_type == 'original':
            extension = self.get_original_extension(image_hash) or ""
            return f"{base_url}/storage/originals/{image_hash}{extension}"
        
        if size:
            # Format: hash_size.format statt size/hash.format
            return f"{base_url}/storage/processed/{format_type}/{image_hash}_{size}.{format_type}"
            
        return f"{base_url}/storage/processed/{format_type}/{image_hash}.{format_type}"
    
    def get_original_extension(self, image_hash: str) -> Optional[str]:
        """Ermittelt die original Dateiendung des gespeicherten Bildes"""
        base_path = Path(f"{settings.STORAGE_PATH}/originals/{image_hash}")
        # Suche nach allen Dateien die mit dem Hash beginnen
        matches = list(base_path.parent.glob(f"{image_hash}.*"))
        if matches:
            # Nimm die Endung der ersten gefundenen Datei
            return matches[0].suffix
        return None

    def get_available_formats(self, image_hash: str, size: Optional[int] = None) -> Dict[str, str]:
        """Gibt URLs für alle verfügbaren Formate zurück"""
        original_ext = self.get_original_extension(image_hash) or ""
        formats = {
            "original": f"{settings.HOST}/storage/originals/{image_hash}{original_ext}"
        }
        
        # Füge Basis-Formate hinzu
        for format_type in ['avif', 'webp']:
            formats[format_type] = self.get_optimized_url(image_hash, format_type)
        
        # Füge skalierte Versionen hinzu wenn size angegeben
        if size:
            for format_type in ['avif', 'webp']:
                formats[f"{format_type}_{size}"] = self.get_optimized_url(
                    image_hash, format_type, size
                )
        
        return formats

    def get_output_path(self, image_hash: str, format_type: str, size: Optional[int] = None) -> str:
        """Gibt den Dateipfad für das zu speichernde Bild zurück"""
        if size:
            return f"{settings.STORAGE_PATH}/processed/{format_type}/{size}/{image_hash}.{format_type}"
        return f"{settings.STORAGE_PATH}/processed/{format_type}/{image_hash}.{format_type}"


    async def save_original(self, image_data: bytes, image_hash: str, extension: str):
        """Speichert das Originalbild"""
        path = Path(f"{settings.STORAGE_PATH}/originals/{image_hash}{extension}")
        async with aiofiles.open(path, 'wb') as f:
            await f.write(image_data)

    def get_file_extension(self, content_type: str) -> str:
        """Ermittelt die Dateiendung aus dem Content-Type"""
        extension = mimetypes.guess_extension(content_type)
        if not extension:
            # Fallback wenn keine Endung gefunden wurde
            return '.jpg'
        return extension