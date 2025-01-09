from typing import Optional, Dict, Any, Callable
import aio_pika # type: ignore
import json
import asyncio
from functools import partial

class QueueService:
    def __init__(
        self,
        rabbitmq_url: str = "amqp://user:password@rabbitmq:5672/",
        queue_name: str = "image_processing"
    ):
        self.rabbitmq_url = rabbitmq_url
        self.queue_name = queue_name
        self.connection = None
        self.channel = None
        self.queue = None
        
    async def connect(self):
        if not self.connection:
            self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
            self.channel = await self.connection.channel()
            self.queue = await self.channel.declare_queue(
                self.queue_name,
                durable=True
            )
    
    async def close(self):
        if self.connection:
            await self.connection.close()
    
    async def enqueue_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0
    ):
        """Add a task to the queue"""
        await self.connect()
        
        message = aio_pika.Message(
            body=json.dumps({
                "task_type": task_type,
                "payload": payload
            }).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            priority=priority
        )
        
        await self.channel.default_exchange.publish(
            message,
            routing_key=self.queue_name
        )
    
    async def enqueue_bulk_tasks(
        self,
        tasks: list[Dict[str, Any]],
        priority: int = 0
    ):
        """Add multiple tasks to the queue efficiently"""
        await self.connect()
        
        for task in tasks:
            message = aio_pika.Message(
                body=json.dumps(task).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority
            )
            await self.channel.default_exchange.publish(
                message,
                routing_key=self.queue_name
            )
    
    async def process_queue(
        self,
        callback: Callable,
        prefetch_count: int = 10
    ):
        """Process queue messages with the given callback"""
        await self.connect()
        await self.channel.set_qos(prefetch_count=prefetch_count)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    body = json.loads(message.body.decode())
                    await callback(body)
                except Exception as e:
                    # Log error and possibly retry
                    print(f"Error processing message: {e}")
                    # Could implement retry logic here
        
        await self.queue.consume(process_message)
        
        try:
            await asyncio.Future()  # wait forever
        finally:
            await self.close()
    
    async def get_queue_info(self) -> Dict[str, int]:
        """Get queue statistics"""
        await self.connect()
        
        declare_ok = await self.channel.declare_queue(
            self.queue_name,
            durable=True,
            passive=True
        )
        
        return {
            "message_count": declare_ok.message_count,
            "consumer_count": declare_ok.consumer_count
        }