import asyncio
import time
from urllib.parse import urlparse
from loouwd.core.logging import logger


class DomainRateLimiter:
    """
    Per-Domain Rate Limiter & Concurrency Guard.
    Prevents IP bans (429 / 403 Cloudflare Turnstile) by enforcing:
    1. Maximum concurrent requests per domain host.
    2. Minimum time interval (delay) between consecutive requests per domain host.
    """

    def __init__(self, max_concurrent: int = 2, min_interval_seconds: float = 0.5):
        self.default_max_concurrent = max_concurrent
        self.default_min_interval = min_interval_seconds
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_request_times: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def _get_semaphore(self, domain: str) -> asyncio.Semaphore:
        async with self._lock:
            if domain not in self._semaphores:
                self._semaphores[domain] = asyncio.Semaphore(self.default_max_concurrent)
            return self._semaphores[domain]

    async def acquire(self, url: str) -> None:
        """Acquire permission to request a domain host while enforcing rate limits."""
        parsed = urlparse(url)
        domain = parsed.netloc or "default"

        sem = await self._get_semaphore(domain)
        await sem.acquire()

        try:
            # Enforce minimum delay between requests to the same domain host
            async with self._lock:
                last_time = self._last_request_times.get(domain, 0.0)
                now = time.time()
                elapsed = now - last_time
                if elapsed < self.default_min_interval:
                    sleep_time = self.default_min_interval - elapsed
                    logger.debug(f"Rate Limiter throttling '{domain}' for {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)

                self._last_request_times[domain] = time.time()
        except Exception:
            sem.release()
            raise

    def release(self, url: str) -> None:
        """Release semaphore after request completes."""
        parsed = urlparse(url)
        domain = parsed.netloc or "default"
        if domain in self._semaphores:
            try:
                self._semaphores[domain].release()
            except ValueError:
                pass


# Global singleton domain rate limiter
domain_limiter = DomainRateLimiter(max_concurrent=2, min_interval_seconds=0.3)
