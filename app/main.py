from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Union
from pydantic import BaseModel, HttpUrl
import asyncio
import hashlib

from .config import settings
from .services.image import ImageProcessor
from .services.storage import StorageManager

app = FastAPI(
    title="Bragi Image Server",
    redirect_slashes=False
)


@app.middleware("http")
async def verify_secret(request: Request, call_next):
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {settings.SECRET_KEY}":
        raise HTTPException(status_code=403, detail="Unauthorized")
    return await call_next(request)

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
storage_manager = StorageManager()
image_processor = ImageProcessor()

# Routes
@app.post("/api/url", response_model=ImageResponse)
async def process_image_url(request: ImageUrlRequest, background_tasks: BackgroundTasks):
    try:
        # Hash aus URL generieren
        url_hash = hashlib.sha256(str(request.url).encode()).hexdigest()
        
        # Prüfen ob optimierte Versionen existieren
        if storage_manager.optimized_exists(url_hash):
            return ImageResponse(
                original_url=str(request.url),
                status="complete",
                optimized_url=storage_manager.get_optimized_url(url_hash),
                formats=storage_manager.get_available_formats(url_hash)
            )
        
        # Wenn nicht, im Hintergrund verarbeiten
        background_tasks.add_task(
            image_processor.process_url,
            request.url,
            url_hash,
            size=request.size
        )
        
        # Sofort "working" zurückgeben
        return ImageResponse(
            original_url=str(request.url),
            status="working"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class HtmlResponse(BaseModel):
    original_html: str
    status: str  # "working" oder "complete"
    optimized_html: Optional[str] = None

@app.post("/api/html", response_model=HtmlResponse)
async def process_html_tag(request: HtmlTagRequest, background_tasks: BackgroundTasks):
    try:
        image_data = image_processor.parse_html_tag(request.html)
        if not image_data:
            raise ValueError("Kein valider img Tag gefunden")
            
        url_hash = hashlib.sha256(image_data['url'].encode()).hexdigest()
        
        # Prüfen ob bereits optimierte Versionen existieren
        if storage_manager.optimized_exists(url_hash):
            return HtmlResponse(
                original_html=request.html,
                status="complete",
                optimized_html=image_processor.create_picture_tag(
                    url_hash,
                    image_data['attributes']
                )
            )
            
        # Verarbeitung im Hintergrund starten
        background_tasks.add_task(
            image_processor.process_url,
            image_data['url'],
            url_hash
        )
        
        # Original HTML zurückgeben mit working status
        return HtmlResponse(
            original_html=request.html,
            status="working"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/batch", response_model=List[ImageResponse])
async def process_image_batch(request: ImageBatchRequest, background_tasks: BackgroundTasks):
    try:
        responses = []
        
        for url in request.urls:
            url_hash = hashlib.sha256(str(url).encode()).hexdigest()
            
            if storage_manager.optimized_exists(url_hash):
                responses.append(ImageResponse(
                    original_url=str(url),
                    status="complete",
                    optimized_url=storage_manager.get_optimized_url(url_hash),
                    formats=storage_manager.get_available_formats(url_hash)
                ))
            else:
                background_tasks.add_task(
                    image_processor.process_url,
                    url,
                    url_hash
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