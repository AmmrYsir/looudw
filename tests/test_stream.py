import unittest
import asyncio
from loouwd.core.limiter import DomainRateLimiter
from loouwd.core.stream import stream_engine, ReactiveStreamEngine
from loouwd.main import app
from fastapi.testclient import TestClient


class TestReactiveStream(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_domain_rate_limiter_acquire_release(self):
        async def _test():
            limiter = DomainRateLimiter(max_concurrent=2, min_interval_seconds=0.1)
            url = "https://spankbang.com/most_popular/1/"

            await limiter.acquire(url)
            self.assertEqual(len(limiter._semaphores), 1)
            limiter.release(url)

        asyncio.run(_test())

    def test_reactive_stream_engine_yields_items(self):
        async def _test():
            items = []
            async for item in stream_engine.stream_browse(query="", page=1):
                items.append(item)
                if len(items) >= 10:
                    break
            self.assertGreater(len(items), 0)

        asyncio.run(_test())

    def test_sse_streaming_endpoint(self):
        response = self.client.get("/api/v1/unified/stream?query=goku")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertTrue(response.text.startswith("data:"))


if __name__ == "__main__":
    unittest.main()
