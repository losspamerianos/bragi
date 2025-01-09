from typing import Optional, Dict, Any, Callable
import aio_pika
from aio_pika.exceptions import AMQPConnectionError  # Korrekter Import
import json
import asyncio
from functools import partial
import logging
import backoff

logger = logging.getLogger(__name__)

class QueueService:
    def __init__(
        self,
        rabbitmq_url: str = "amqp://user:password@rabbitmq:5672/",
        queue_name: str = "image_processing",
        max_retries: int = 5,
        initial_delay: float = 1.0
    ):
        self.rabbitmq_url = rabbitmq_url
        self.queue_name = queue_name
        self.connection = None
        self.channel = None
        self.queue = None
        self.max_retries = max_retries
        self.initial_delay = initial_delay

    @backoff.on_exception(
        backoff.expo,
        (AMQPConnectionError, ConnectionError),  # Aktualisierter Exception-Typ
        max_tries=5,
        max_time=30
    )
    async def connect(self):
        """Connect to RabbitMQ with exponential backoff retry"""
        if not self.connection:
            try:
                logger.info(f"Connecting to RabbitMQ at {self.rabbitmq_url}")
                self.connection = await aio_pika.connect_robust(
                    self.rabbitmq_url,
                    timeout=30
                )
                self.channel = await self.connection.channel()
                self.queue = await self.channel.declare_queue(
                    self.queue_name,
                    durable=True
                )
                logger.info("Successfully connected to RabbitMQ")
            except Exception as e:
                logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
                raise
    
    async def close(self):
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.channel = None
            self.queue = None
    
    async def ensure_connected(self):
        """Ensure we have a connection, reconnect if necessary"""
        if not self.connection or self.connection.is_closed:
            await self.connect()
        
    async def enqueue_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0
    ):
        """Add a task to the queue"""
        await self.ensure_connected()
        
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
        await self.ensure_connected()
        
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
        await self.ensure_connected()
        await self.channel.set_qos(prefetch_count=prefetch_count)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    body = json.loads(message.body.decode())
                    await callback(body)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Could implement retry logic here
        
        await self.queue.consume(process_message)
        
        try:
            await asyncio.Future()  # wait forever
        finally:
            await self.close()
    
    async def get_queue_info(self) -> Dict[str, int]:
        """Get queue statistics"""
        await self.ensure_connected()
        
        declare_ok = await self.channel.declare_queue(
            self.queue_name,
            durable=True,
            passive=True
        )
        
        return {
            "message_count": declare_ok.message_count,
            "consumer_count": declare_ok.consumer_count
        }