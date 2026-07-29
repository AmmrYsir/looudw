import asyncio
from datetime import datetime, timezone
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loouwd.core.config import settings
from loouwd.core.logging import logger
from loouwd.core.limiter import domain_limiter


class SourceExecutionContext:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        credentials: dict[str, str] | None = None,
        proxy_url: str | None = settings.PROXY_URL,
    ):
        self.credentials = credentials or {}
        self.now = datetime.now(timezone.utc).isoformat()
        self._proxy_url = proxy_url

        limits = httpx.Limits(
            max_connections=settings.HTTP_MAX_CONNECTIONS,
            max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
        )

        timeout = httpx.Timeout(settings.HTTP_TIMEOUT_SECONDS)

        headers = {
            "User-Agent": settings.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        self._client = client or httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            headers=headers,
            proxy=self._proxy_url,
            follow_redirects=True,
            http2=True,
        )

    @property
    def http(self) -> httpx.AsyncClient:
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def fetch_text(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> str:
        await domain_limiter.acquire(url)
        try:
            req_headers = dict(self._client.headers)
            if headers:
                req_headers.update(headers)
            response = await self._client.get(url, headers=req_headers, params=params)
            response.raise_for_status()
            return response.text
        finally:
            domain_limiter.release(url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def fetch_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> dict | list:
        await domain_limiter.acquire(url)
        try:
            req_headers = dict(self._client.headers)
            if headers:
                req_headers.update(headers)
            response = await self._client.get(url, headers=req_headers, params=params)
            response.raise_for_status()
            return response.json()
        finally:
            domain_limiter.release(url)

    async def aclose(self) -> None:
        await self._client.aclose()


default_context = SourceExecutionContext()
