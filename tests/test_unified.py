import unittest
import asyncio
from loouwd.services.unified import unified_service, UnifiedBrowseRequest
from loouwd.main import app
from fastapi.testclient import TestClient


class TestUnifiedModule(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unified_service_browse_all(self):
        async def _test():
            req = UnifiedBrowseRequest(query="", page=1, per_page=10)
            res = await unified_service.browse_all(req)
            self.assertIsInstance(res.items, list)
            self.assertGreater(len(res.items), 0)
            self.assertIn("nhentai", res.sources_queried)
            self.assertIn("xvideos", res.sources_queried)

        asyncio.run(_test())

    def test_unified_browse_api_endpoint(self):
        response = self.client.post(
            "/api/v1/unified/browse",
            json={"query": "", "media_type": "all", "page": 1, "per_page": 12},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("items", data)
        self.assertIn("sourcesQueried", data)
        self.assertGreater(len(data["items"]), 0)

    def test_unified_feed_api_endpoint(self):
        response = self.client.get("/api/v1/unified/feed/manga?page=1&per_page=10")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("items", data)
        for item in data["items"]:
            self.assertEqual(item["mediaType"], "manga")


if __name__ == "__main__":
    unittest.main()
