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
                    
                return await response.read()

    def calculate_hash(self, image_data: bytes) -> str:
        """Berechnet einen eindeutigen Hash für das Bild"""
        return hashlib.sha256(image_data).hexdigest()

    def optimized_exists(self, image_hash: str) -> bool:
        """Prüft ob bereits optimierte Versionen existieren"""
        avif_path = Path(f"{settings.STORAGE_PATH}/processed/avif/{image_hash}.avif")
        webp_path = Path(f"{settings.STORAGE_PATH}/processed/webp/{image_hash}.webp")
        print(f"Checking paths:\nAVIF: {avif_path}\nWebP: {webp_path}")
        print(f"Exist?: AVIF: {avif_path.exists()}, WebP: {webp_path.exists()}")
        return avif_path.exists() and webp_path.exists()

    def get_optimized_url(self, image_hash: str, format_type: str = 'avif', size: Optional[int] = None) -> str:
        """Gibt die URL der optimierten Version zurück
        
        Args:
            image_hash: Hash des Bildes
            format_type: Format (avif, webp, original)
            size: Optionale Größe für skalierte Versionen
        """
        if format_type == 'original':
            extension = self.get_original_extension(image_hash) or ""
            base_path = f"{settings.HOST}/storage/originals/{image_hash}{extension}"
        else:
            base_path = f"{settings.HOST}/storage/processed/{format_type}/{image_hash}.{format_type}"
        
        if size:
            # Füge Größe zum Pfad hinzu, z.B. image_500.avif
            path_parts = base_path.rsplit('.', 1)
            return f"{path_parts[0]}_{size}.{path_parts[1]}"
            
        return base_path
    
    def get_original_extension(self, image_hash: str) -> Optional[str]:
        """Ermittelt die original Dateiendung des gespeicherten Bildes"""
        base_path = Path(f"{settings.STORAGE_PATH}/originals/{image_hash}")
        # Suche nach allen Dateien die mit dem Hash beginnen
        matches = list(base_path.parent.glob(f"{image_hash}.*"))
        if matches:
            # Nimm die Endung der ersten gefundenen Datei
            return matches[0].suffix
        return None

    def get_available_formats(self, image_hash: str) -> Dict[str, str]:
        """Gibt URLs für alle verfügbaren Formate zurück"""
        original_ext = self.get_original_extension(image_hash) or ""
        
        return {
            "avif": f"{settings.HOST}/storage/processed/avif/{image_hash}.avif",
            "webp": f"{settings.HOST}/storage/processed/webp/{image_hash}.webp",
            "original": f"{settings.HOST}/storage/originals/{image_hash}{original_ext}"
        }

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