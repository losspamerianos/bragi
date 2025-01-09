from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Union
from pydantic import BaseModel, HttpUrl
import hashlib
import asyncio
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator # type: ignore
import logging

from .config import settings
from .services.image import ImageProcessor
from .services.storage import StorageManager
from .services.cache import CacheService, ProcessingStatus
from .services.queue import QueueService


# Metrics
PROCESSING_TIME = Histogram(
    'image_processing_duration_seconds',
    'Time spent processing images'
)
PROCESSED_IMAGES = Counter(
    'processed_images_total',
    'Total number of processed images'
)

app = FastAPI(
    title="Bragi Image Server",
    redirect_slashes=False
)

# Initialize services
storage_manager = StorageManager()
image_processor = ImageProcessor()
cache_service = CacheService(settings.REDIS_URL)
queue_service = QueueService(settings.RABBITMQ_URL)

# ---------------------------------------------------
# Auth / Secret Middleware
# ---------------------------------------------------
@app.middleware("http")
async def verify_secret(request: Request, call_next):
    if request.url.path.startswith("/storage/processed"):
        return await call_next(request)
        
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {settings.BRAGI_SECRET_KEY}":
        raise HTTPException(status_code=403, detail="Unauthorized")
    return await call_next(request)

# ---------------------------------------------------
# CORS Middleware
# ---------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# Models
# ---------------------------------------------------
class ImageUrlRequest(BaseModel):
    url: HttpUrl
    size: Optional[Union[int, str]] = None

class HtmlTagRequest(BaseModel):
    html: str

class ImageBatchRequest(BaseModel):
    urls: List[HttpUrl]
    check_duplicates: Optional[bool] = False

class ImageResponse(BaseModel):
    original_url: str
    status: str
    optimized_url: Optional[str] = None
    formats: Optional[dict] = None

class HtmlResponse(BaseModel):
    original_html: str
    status: str
    optimized_html: Optional[str] = None

class BulkUrlRequest(BaseModel):
    items: List[ImageUrlRequest]
    check_duplicates: Optional[bool] = False

# ---------------------------------------------------
# Startup and Shutdown Events
# ---------------------------------------------------
@app.on_event("startup")
async def startup_event():
    retries = 5
    delay = 1
    last_exception = None
    
    for attempt in range(retries):
        try:
            # Connect to services
            await cache_service.connect()
            await queue_service.connect()
            
            # Start queue worker
            asyncio.create_task(start_queue_worker())
            
            # Initialize metrics
            Instrumentator().instrument(app).expose(app)
            return
            
        except Exception as e:
            last_exception = e
            logging.warning(f"Startup attempt {attempt + 1} failed: {str(e)}")
            await asyncio.sleep(delay)
            delay *= 2  # Exponential backoff
    
    logging.error("Failed to start application after multiple retries")
    raise last_exception

@app.on_event("shutdown")
async def shutdown_event():
    await cache_service.close()
    await queue_service.close()

# ---------------------------------------------------
# Queue Worker
# ---------------------------------------------------
async def start_queue_worker():
    async def process_image_task(task_data: dict):
        url = task_data["payload"]["url"]
        url_hash = task_data["payload"]["url_hash"]
        size = task_data["payload"].get("size")
        
        try:
            with PROCESSING_TIME.time():
                await image_processor.process_url(url, url_hash, size)
                PROCESSED_IMAGES.inc()
                await cache_service.set_image_status(
                    url_hash,
                    ProcessingStatus.COMPLETE,
                    metadata={
                        "optimized_url": storage_manager.get_optimized_url(url_hash),
                        "formats": storage_manager.get_available_formats(url_hash)
                    }
                )
        except Exception as e:
            await cache_service.set_image_status(
                url_hash,
                ProcessingStatus.ERROR,
                metadata={"error": str(e)}
            )
    
    await queue_service.process_queue(process_image_task)

# ---------------------------------------------------
# Routes
# ---------------------------------------------------
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    queue_info = await queue_service.get_queue_info()
    processing_count = await cache_service.get_queue_length()
    
    return {
        "status": "healthy",
        "queue_length": queue_info["message_count"],
        "processing": processing_count
    }

@app.post("/api/url", response_model=ImageResponse)
async def process_image_url(request: ImageUrlRequest):
    try:
        url_hash = hashlib.sha256(str(request.url).encode()).hexdigest()
        
        # Check cache first
        cached_status = await cache_service.get_image_status(url_hash)
        if cached_status:
            if cached_status["status"] == ProcessingStatus.COMPLETE:
                return ImageResponse(
                    original_url=str(request.url),
                    status="complete",
                    optimized_url=cached_status["metadata"]["optimized_url"],
                    formats=cached_status["metadata"]["formats"]
                )
            return ImageResponse(
                original_url=str(request.url),
                status=cached_status["status"]
            )
        
        # Check if already processed
        if storage_manager.optimized_exists(url_hash):
            response_data = {
                "original_url": str(request.url),
                "status": "complete",
                "optimized_url": storage_manager.get_optimized_url(url_hash),
                "formats": storage_manager.get_available_formats(url_hash)
            }
            await cache_service.set_image_status(
                url_hash,
                ProcessingStatus.COMPLETE,
                metadata=response_data
            )
            return ImageResponse(**response_data)
        
        # Try to acquire processing lock
        if not await cache_service.acquire_lock(url_hash):
            # Already being processed
            cached_status = await cache_service.get_image_status(url_hash)
            return ImageResponse(
                original_url=str(request.url),
                status=cached_status["status"] if cached_status else "processing"
            )
        
        # Queue new processing task
        await cache_service.set_image_status(url_hash, ProcessingStatus.PENDING)
        await queue_service.enqueue_task(
            "process_image",
            {
                "url": str(request.url),
                "url_hash": url_hash,
                "size": request.size
            }
        )
        
        return ImageResponse(
            original_url=str(request.url),
            status="pending"
        )
        
    except Exception as e:
        if url_hash:
            await cache_service.release_lock(url_hash)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/url/bulk", response_model=List[ImageResponse])
async def process_bulk_urls(request: BulkUrlRequest):
    try:
        responses = []
        tasks = []
        
        # First, get all hashes and check cache in bulk
        url_hashes = [
            hashlib.sha256(str(item.url).encode()).hexdigest()
            for item in request.items
        ]
        
        cached_statuses = await cache_service.get_bulk_status(url_hashes)
        
        for item, url_hash in zip(request.items, url_hashes):
            cached_status = cached_statuses.get(url_hash)
            
            if cached_status and cached_status["status"] == ProcessingStatus.COMPLETE:
                responses.append(ImageResponse(
                    original_url=str(item.url),
                    status="complete",
                    optimized_url=cached_status["metadata"]["optimized_url"],
                    formats=cached_status["metadata"]["formats"]
                ))
                continue
                
            if cached_status:
                responses.append(ImageResponse(
                    original_url=str(item.url),
                    status=cached_status["status"]
                ))
                continue
            
            # Check storage
            if storage_manager.optimized_exists(url_hash):
                response_data = {
                    "original_url": str(item.url),
                    "status": "complete",
                    "optimized_url": storage_manager.get_optimized_url(url_hash),
                    "formats": storage_manager.get_available_formats(url_hash)
                }
                await cache_service.set_image_status(
                    url_hash,
                    ProcessingStatus.COMPLETE,
                    metadata=response_data
                )
                responses.append(ImageResponse(**response_data))
                continue
            
            # Try to acquire lock
            if not await cache_service.acquire_lock(url_hash):
                cached_status = await cache_service.get_image_status(url_hash)
                responses.append(ImageResponse(
                    original_url=str(item.url),
                    status=cached_status["status"] if cached_status else "processing"
                ))
                continue
            
            # Queue new task
            tasks.append({
                "task_type": "process_image",
                "payload": {
                    "url": str(item.url),
                    "url_hash": url_hash,
                    "size": item.size
                }
            })
            
            await cache_service.set_image_status(url_hash, ProcessingStatus.PENDING)
            responses.append(ImageResponse(
                original_url=str(item.url),
                status="pending"
            ))
        
        # Enqueue all new tasks at once
        if tasks:
            await queue_service.enqueue_bulk_tasks(tasks)
        
        return responses
        
    except Exception as e:
        # Release any acquired locks
        for url_hash in url_hashes:
            await cache_service.release_lock(url_hash)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/html", response_model=HtmlResponse)
async def process_html_tag(request: HtmlTagRequest):
    try:
        image_data = image_processor.parse_html_tag(request.html)
        if not image_data:
            raise ValueError("No valid img tag found")
            
        url_hash = hashlib.sha256(image_data['url'].encode()).hexdigest()
        
        # Check cache first
        cached_status = await cache_service.get_image_status(url_hash)
        if cached_status and cached_status["status"] == ProcessingStatus.COMPLETE:
            return HtmlResponse(
                original_html=request.html,
                status="complete",
                optimized_html=image_processor.create_picture_tag(
                    url_hash,
                    image_data['attributes'],
                    cached_status["metadata"]["formats"]
                )
            )
        
        if storage_manager.optimized_exists(url_hash):
            formats = storage_manager.get_available_formats(url_hash)
            await cache_service.set_image_status(
                url_hash,
                ProcessingStatus.COMPLETE,
                metadata={"formats": formats}
            )
            return HtmlResponse(
                original_html=request.html,
                status="complete",
                optimized_html=image_processor.create_picture_tag(
                    url_hash,
                    image_data['attributes'],
                    formats
                )
            )
            
        # Try to acquire lock
        if not await cache_service.acquire_lock(url_hash):
            return HtmlResponse(
                original_html=request.html,
                status="processing"
            )
        
        # Queue new task
        await cache_service.set_image_status(url_hash, ProcessingStatus.PENDING)
        await queue_service.enqueue_task(
            "process_image",
            {
                "url": image_data['url'],
                "url_hash": url_hash
            }
        )
        
        return HtmlResponse(
            original_html=request.html,
            status="pending"
        )
        
    except Exception as e:
        if url_hash:
            await cache_service.release_lock(url_hash)
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)