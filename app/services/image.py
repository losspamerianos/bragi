import os
import io
import cv2
import pyvips # type: ignore
import imagehash # type: ignore
import hashlib

import numpy as np

from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Tuple
from bs4 import BeautifulSoup

from ..config import settings
from .storage import StorageManager  # StorageManager Import hinzugefügt

class ImageProcessor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
        self.storage_manager = StorageManager()
        
    async def process_url(self, url: str, url_hash: str, size: Any = None):
        """Verarbeitet eine URL komplett im Hintergrund"""
        try:
            # Hole das Bild
            image_data = await self.storage_manager.fetch_image(url)
            
            # Speichere Original
            extension = self.storage_manager.get_file_extension("image/jpeg")  # Fallback
            await self.storage_manager.save_original(image_data, url_hash, extension)
            
            # Optimiere es
            await self.optimize_image(image_data, url_hash, size)
            
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")
            import traceback
            print(traceback.format_exc())
        
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
        
    def _create_avif(self, image: pyvips.Image, image_hash: str):
        """Erstellt eine AVIF Version des Bildes"""
        output_path = f"{settings.STORAGE_PATH}/processed/avif/{image_hash}.avif"
        print(f"Creating AVIF at: {output_path}")
        try:
            image.write_to_file(output_path, effort=settings.AVIF_EFFORT)
            print("AVIF creation successful")
        except Exception as e:
            print(f"Error creating AVIF: {str(e)}")
            raise
        
    def _create_webp(self, image: pyvips.Image, image_hash: str):
        """Erstellt eine WebP Version des Bildes"""
        output_path = f"{settings.STORAGE_PATH}/processed/webp/{image_hash}.webp"
        print(f"Creating WebP at: {output_path}")
        try:
            image.write_to_file(output_path)
            print("WebP creation successful")
        except Exception as e:
            print(f"Error creating WebP: {str(e)}")
            raise

    def _format_exists(self, image_hash: str, format: str) -> bool:
        """Prüft ob ein bestimmtes Format existiert"""
        path = f"{settings.STORAGE_PATH}/processed/{format}/{image_hash}.{format}"
        return os.path.exists(path)

    def _get_url(self, image_hash: str, format: str) -> str:
        """Generiert die URL für ein bestimmtes Format"""
        if format == "original":
            return f"/storage/originals/{image_hash}"
        return f"/storage/processed/{format}/{image_hash}.{format}"