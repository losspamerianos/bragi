# ---------------------------------------------------
# Image Processor
# /services/image.py
# ---------------------------------------------------
import os
import io
import cv2
import pyvips # type: ignore
import imagehash # type: ignore
import hashlib
import logging

import numpy as np

from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup

from ..config import settings
from .storage import StorageManager
from .cache import CacheService, ProcessingStatus  # Neue Imports

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class ImageProcessor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
        self.storage_manager = StorageManager()
        
# services/image.py

# services/image.py

class ImageProcessor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
        self.storage_manager = StorageManager()
        
        # Die Variable haben wir hinzugefügt aber die Instanz fehlt
        # self.cache_service = CacheService(settings.REDIS_URL)
        
    async def process_url(self, url: str, url_hash: str, size: Any = None):
        dimensions = {}
        try:
            logger.info(f"Starting processing of {url} with hash {url_hash} and size {size}")
            
            image_data = await self.storage_manager.fetch_image(url)
            extension = self.storage_manager.get_file_extension("image/jpeg")
            await self.storage_manager.save_original(image_data, url_hash, extension)

            image = pyvips.Image.new_from_buffer(image_data, "")
            dimensions['original'] = f"{image.width}x{image.height}"
            
            # Basis-Versionen erstellen
            self._create_avif(image, url_hash)
            self._create_webp(image, url_hash)
            
            # Skalierte Version wenn notwendig
            if size:
                scale = size/image.width
                resized = image.resize(scale)
                dimensions[str(size)] = f"{resized.width}x{resized.height}"
                
                size_hash = f"{url_hash}_{size}"
                self._create_avif(resized, size_hash)
                self._create_webp(resized, size_hash)
            
            formats = self.storage_manager.get_available_formats(url_hash, size)
            
            return {
                "original_url": url,
                "status": "complete",
                "optimized_url": formats['avif'],
                "formats": formats,
                "dimensions": dimensions
            }

        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}", exc_info=True)
            raise
        
    async def optimize_image(self, image_data: bytes, image_hash: str, size: Any = None):
        """Optimiert ein Bild asynchron in verschiedene Formate"""
        print("Starting image optimization")
        try:
            # Lade Bild in pyvips
            image = pyvips.Image.new_from_buffer(image_data, "")
            print("Image loaded into pyvips")
            
            # Größenanpassung wenn nötig
            if size:
                print(f"Resizing image to {size}")
                image = self._resize_image(image, size)
            
            print("Starting format conversion")
            # Erzeuge verschiedene Formate - direkt, nicht über ThreadPool
            self._create_avif(image, image_hash)
            self._create_webp(image, image_hash)
            print("Format conversion complete")
            
        except Exception as e:
            print(f"Error in optimize_image: {str(e)}")
            import traceback
            print(traceback.format_exc())
            raise
        
    def parse_html_tag(self, html: str) -> Dict[str, Any]:
        """Extrahiert Bild und Attribute aus HTML Tag"""
        soup = BeautifulSoup(html, 'html.parser')
        img = soup.find('img')
        if not img or 'src' not in img.attrs:
            return None
            
        return {
            'url': img['src'],  # Wir geben nur die URL zurück
            'attributes': dict(img.attrs)
        }
        
    def create_picture_tag(self, image_hash: str, attributes: Dict[str, str]) -> str:
        """Erstellt einen Picture Tag mit allen verfügbaren Formaten"""
        # Basisattribute übernehmen
        attrs = ' '.join([f'{k}="{v}"' for k, v in attributes.items() if k != 'src'])
        
        # Picture Tag aufbauen
        html = ['<picture>']
        
        # AVIF Source
        if self._format_exists(image_hash, 'avif'):
            html.append(f'<source srcset="{self._get_url(image_hash, "avif")}" type="image/avif">')
            
        # WebP Source
        if self._format_exists(image_hash, 'webp'):
            html.append(f'<source srcset="{self._get_url(image_hash, "webp")}" type="image/webp">')
            
        # Fallback Image
        html.append(f'<img src="{self._get_url(image_hash, "original")}" {attrs}>')
        html.append('</picture>')
        
        return '\n'.join(html)

    def remove_duplicates(self, images: List[bytes]) -> List[bytes]:
        """Entfernt Duplikate aus einer Liste von Bildern"""
        # Berechne Features parallel
        with ThreadPoolExecutor() as executor:
            phashes = list(executor.map(self._calculate_phash, images))
            histograms = list(executor.map(self._calculate_histogram, images))
            
        # Finde eindeutige Bilder
        unique_indices = []
        for i in range(len(images)):
            is_duplicate = False
            for j in unique_indices:
                # Prüfe pHash und Histogram Ähnlichkeit
                phash_sim = 1 - (phashes[i] - phashes[j]) / 64  # Normalisierte Hamming-Distanz
                hist_sim = cv2.compareHist(histograms[i], histograms[j], cv2.HISTCMP_CORREL)
                
                # Gewichtete Kombination
                combined_sim = 0.7 * phash_sim + 0.3 * hist_sim
                
                if combined_sim > settings.COMBINED_THRESHOLD:
                    is_duplicate = True
                    break
                    
            if not is_duplicate:
                unique_indices.append(i)
                
        return [images[i] for i in unique_indices]

    def _calculate_phash(self, image_data: bytes) -> int:
        """Berechnet den perceptual Hash eines Bildes"""
        image = Image.open(io.BytesIO(image_data))
        return imagehash.average_hash(image)
        
    def _calculate_histogram(self, image_data: bytes) -> np.ndarray:
        """Berechnet das Farbhistogramm eines Bildes"""
        # Konvertiere zu OpenCV Format
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Berechne Histogramm für jeden Farbkanal
        hist = cv2.calcHist([image], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        
        return hist
        
    def _resize_image(self, image: pyvips.Image, size: Any) -> pyvips.Image:
        """Passt die Bildgröße an"""
        original_width = image.width
        
        if isinstance(size, int):
            # Absolute Größe in Pixeln
            scale = size / original_width
        else:
            # Prozentuale Größe
            scale = float(size.strip('%')) / 100
            
        return image.resize(scale)
        
    def _create_avif(self, image: pyvips.Image, image_hash: str, size: Optional[int] = None):
        """Erstellt eine AVIF Version des Bildes"""
        output_path = self.storage_manager.get_output_path(image_hash, 'avif', size)
        print(f"Creating AVIF at: {output_path}")
        try:
            image.write_to_file(output_path, effort=settings.AVIF_EFFORT)
            print("AVIF creation successful")
        except Exception as e:
            print(f"Error creating AVIF: {str(e)}")
            raise

    def _create_webp(self, image: pyvips.Image, image_hash: str, size: Optional[int] = None):
        """Erstellt eine WebP Version des Bildes"""
        output_path = self.storage_manager.get_output_path(image_hash, 'webp', size)
        print(f"Creating WebP at: {output_path}")
        try:
            image.write_to_file(output_path)
            print("WebP creation successful")
        except Exception as e:
            print(f"Error creating WebP: {str(e)}")
            raise

    def _format_exists(self, image_hash: str, format: str, size: int = None) -> bool:
        size_suffix = f"-{size}" if size else ""
        path = f"{settings.STORAGE_PATH}/processed/{format}/{image_hash}{size_suffix}.{format}"
        return os.path.exists(path)

    def _get_url(self, image_hash: str, format: str, size: int = None) -> str:
        base = f"{settings.HOST}/storage/processed"
        if format == "original":
            return f"/storage/originals/{image_hash}"
        
        size_suffix = f"-{size}" if size else ""
        return f"{base}/{format}/{image_hash}{size_suffix}.{format}"