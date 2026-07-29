import asyncio
import time
from typing import Any, Callable, TypeVar
from functools import wraps
from loouwd.core.config import settings
from loouwd.core.logging import logger

T = TypeVar("T")


class AsyncTTLCache:
    def __init__(self, ttl: int = settings.CACHE_TTL_SECONDS, maxsize: int = settings.CACHE_MAXSIZE):
        self.ttl = ttl
        self.maxsize = maxsize
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        if not settings.CACHE_ENABLED:
            return None
        async with self._lock:
            if key not in self._cache:
                return None
            timestamp, value = self._cache[key]
            if time.time() - timestamp > self.ttl:
                del self._cache[key]
                return None
            return value

    async def set(self, key: str, value: Any) -> None:
        if not settings.CACHE_ENABLED:
            return
        async with self._lock:
            if len(self._cache) >= self.maxsize:
                # Evict oldest entry
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), value)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
            logger.info("Cache cleared successfully.")


global_cache = AsyncTTLCache()


def cached(ttl: int | None = None, key_prefix: str = ""):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not settings.CACHE_ENABLED:
                return await func(*args, **kwargs)

            # Generate cache key from func name + stringified args/kwargs
            raw_key = f"{key_prefix}:{func.__qualname__}:{args[1:]}:{sorted(kwargs.items())}"
            cached_val = await global_cache.get(raw_key)
            if cached_val is not None:
                return cached_val

            result = await func(*args, **kwargs)
            if result is not None:
                await global_cache.set(raw_key, result)
            return result

        return wrapper

    return decorator
