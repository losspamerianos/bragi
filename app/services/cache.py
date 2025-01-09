from typing import Optional, Dict, Any
from redis import asyncio as aioredis  # Verwenden das neue async redis
import json
from enum import Enum
from datetime import datetime

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"

class CacheService:
    def __init__(self, redis_url: str = "redis://redis:6379"):
        self.redis = None
        self.redis_url = redis_url
    
    async def connect(self):
        if not self.redis:
            self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
    
    async def close(self):
        if self.redis:
            await self.redis.close()
    
    async def get_image_status(self, url_hash: str) -> Optional[Dict[str, Any]]:
        """Get image processing status and metadata from cache"""
        await self.connect()
        data = await self.redis.get(f"image:{url_hash}")
        return json.loads(data) if data else None
    
    async def set_image_status(
        self, 
        url_hash: str, 
        status: ProcessingStatus,
        metadata: Optional[Dict[str, Any]] = None,
        expire: int = 3600
    ):
        """Set image processing status and metadata in cache"""
        await self.connect()
        data = {
            "status": status,
            "metadata": metadata or {},
            "updated_at": datetime.utcnow().isoformat()
        }
        await self.redis.set(
            f"image:{url_hash}",
            json.dumps(data),
            ex=expire
        )
    
    async def get_bulk_status(self, url_hashes: list[str]) -> Dict[str, Dict[str, Any]]:
        """Get multiple image statuses in one call"""
        await self.connect()
        pipe = self.redis.pipeline()
        for url_hash in url_hashes:
            pipe.get(f"image:{url_hash}")
        
        results = await pipe.execute()
        return {
            url_hash: json.loads(data) if data else None
            for url_hash, data in zip(url_hashes, results)
        }
    
    async def set_bulk_status(
        self,
        items: Dict[str, Dict[str, Any]],
        expire: int = 3600
    ):
        """Set multiple image statuses in one call"""
        await self.connect()
        pipe = self.redis.pipeline()
        for url_hash, data in items.items():
            data["updated_at"] = datetime.utcnow().isoformat()
            pipe.set(
                f"image:{url_hash}",
                json.dumps(data),
                ex=expire
            )
        await pipe.execute()
    
    async def acquire_lock(self, url_hash: str, expire: int = 30) -> bool:
        """Acquire a distributed lock for processing an image"""
        await self.connect()
        lock_key = f"lock:{url_hash}"
        return await self.redis.set(lock_key, "1", ex=expire, nx=True)
    
    async def release_lock(self, url_hash: str):
        """Release a distributed lock"""
        await self.connect()
        await self.redis.delete(f"lock:{url_hash}")

    async def get_queue_length(self) -> int:
        """Get number of images currently being processed"""
        await self.connect()
        keys = await self.redis.keys("image:*")
        processing = 0
        for key in keys:
            data = await self.redis.get(key)
            if data:
                status_data = json.loads(data)
                if status_data.get("status") == ProcessingStatus.PROCESSING:
                    processing += 1
        return processing