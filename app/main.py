from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Union
from pydantic import BaseModel, HttpUrl
import asyncio

from .config import settings
from .services.image import ImageProcessor
from .services.storage import StorageManager

app = FastAPI(
    title="Bragi Image Server",
    # Deaktiviere automatische Redirects für trailing slashes
    redirect_slashes=False
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
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
    try:
        # Erstelle erstmal einen vorläufigen Hash aus der URL
        url_hash = hashlib.sha256(str(request.url).encode()).hexdigest()
        
        # Prüfe zunächst nur, ob bereits eine optimierte Version existiert
        if storage_manager.optimized_exists(url_hash):
            return ImageResponse(
                original_url=str(request.url),
                status="complete",
                optimized_url=storage_manager.get_optimized_url(url_hash),
                formats=storage_manager.get_available_formats(url_hash)
            )
        
        # Starte den kompletten Prozess im Hintergrund
        background_tasks.add_task(
            image_processor.process_url,
            request.url,
            url_hash,
            size=request.size
        )
        
        return ImageResponse(
            original_url=str(request.url),
            status="working",
            check_url=f"/api/status/{url_hash}"  # URL zum Status-Check
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{image_hash}", response_model=ImageResponse)
async def check_image_status(image_hash: str):
    """Prüft den Status einer Bildverarbeitung"""
    if storage_manager.optimized_exists(image_hash):
        return ImageResponse(
            original_url="",  # Hier könnten wir die Original-URL in einer DB speichern
            status="complete",
            optimized_url=storage_manager.get_optimized_url(image_hash),
            formats=storage_manager.get_available_formats(image_hash)
        )
    return ImageResponse(
        original_url="",
        status="working"
    )  # Trailing slash hinzugefügt
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