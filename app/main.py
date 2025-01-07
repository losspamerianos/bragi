from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Union
from pydantic import BaseModel, HttpUrl
import asyncio

from .config import settings
from .services.image import ImageProcessor
from .services.storage import StorageManager

app = FastAPI(title="Bragi Image Server")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class ImageUrlRequest(BaseModel):
    url: HttpUrl
    size: Optional[Union[int, str]] = None  # px oder %

class HtmlTagRequest(BaseModel):
    html: str

class ImageBatchRequest(BaseModel):
    urls: List[HttpUrl]
    check_duplicates: Optional[bool] = False

class ImageResponse(BaseModel):
    original_url: str
    status: str  # "working" oder "complete"
    optimized_url: Optional[str] = None
    formats: Optional[dict] = None

# Services
image_processor = ImageProcessor()
storage_manager = StorageManager()

# Routes
@app.post("/api/url", response_model=ImageResponse)
async def process_image_url(request: ImageUrlRequest, background_tasks: BackgroundTasks):
    # Validiere URL und hole Bild
    try:
        image_data = await storage_manager.fetch_image(request.url)
        image_hash = storage_manager.calculate_hash(image_data)
        
        # Prüfe ob bereits optimierte Version existiert
        if storage_manager.optimized_exists(image_hash):
            return ImageResponse(
                original_url=str(request.url),
                status="complete",
                optimized_url=storage_manager.get_optimized_url(image_hash),
                formats=storage_manager.get_available_formats(image_hash)
            )
        
        # Starte Optimierung im Hintergrund
        background_tasks.add_task(
            image_processor.optimize_image,
            image_data,
            image_hash,
            size=request.size
        )
        
        return ImageResponse(
            original_url=str(request.url),
            status="working"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/html")
async def process_html_tag(request: HtmlTagRequest, background_tasks: BackgroundTasks):
    try:
        # Parse HTML und extrahiere Bild-URL und Attribute
        image_data = image_processor.parse_html_tag(request.html)
        if not image_data:
            raise ValueError("Kein valider img Tag gefunden")
            
        image_hash = storage_manager.calculate_hash(image_data['content'])
        
        # Wenn optimiert, Picture-Tag zurückgeben
        if storage_manager.optimized_exists(image_hash):
            return image_processor.create_picture_tag(
                image_hash,
                image_data['attributes']
            )
            
        # Sonst Optimierung starten und Original zurückgeben
        background_tasks.add_task(
            image_processor.optimize_image,
            image_data['content'],
            image_hash
        )
        return request.html
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/batch", response_model=List[ImageResponse])
async def process_image_batch(request: ImageBatchRequest, background_tasks: BackgroundTasks):
    try:
        # Hole alle Bilder parallel
        images = await asyncio.gather(*[
            storage_manager.fetch_image(url) 
            for url in request.urls
        ])
        
        # Wenn Duplikaterkennung aktiviert
        if request.check_duplicates:
            images = image_processor.remove_duplicates(images)
            
        # Verarbeite jedes Bild
        responses = []
        for img, url in zip(images, request.urls):
            image_hash = storage_manager.calculate_hash(img)
            
            if storage_manager.optimized_exists(image_hash):
                responses.append(ImageResponse(
                    original_url=str(url),
                    status="complete",
                    optimized_url=storage_manager.get_optimized_url(image_hash),
                    formats=storage_manager.get_available_formats(image_hash)
                ))
            else:
                background_tasks.add_task(
                    image_processor.optimize_image,
                    img,
                    image_hash
                )
                responses.append(ImageResponse(
                    original_url=str(url),
                    status="working"
                ))
                
        return responses
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)