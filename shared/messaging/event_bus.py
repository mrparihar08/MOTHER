"""
Event Bus for Inter-Service Event Publishing and Subscription.
"""
import os
import json
import logging
from typing import Callable, Dict, Any, List

logger = logging.getLogger("shared.messaging.event_bus")


class EventBus:
    """Asynchronous and synchronous event publisher/subscriber."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.redis_client = None
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                self.redis_client = redis.from_url(redis_url)
            except Exception as e:
                logger.warning(f"Could not connect to Redis event bus: {e}")

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]):
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    def publish(self, topic: str, payload: Dict[str, Any]):
        # Local in-memory dispatch
        handlers = self._handlers.get(topic, [])
        for handler in handlers:
            try:
                handler(payload)
            except Exception as e:
                logger.error(f"Error handling event {topic}: {e}")

        # Redis pub/sub dispatch if connected
        if self.redis_client:
            try:
                self.redis_client.publish(topic, json.dumps(payload))
            except Exception as e:
                logger.error(f"Failed to publish to Redis topic {topic}: {e}")


# Global default instance
event_bus = EventBus()
