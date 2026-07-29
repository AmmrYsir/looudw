import unittest
import asyncio
from loouwd.adapters.nhentai import NHentaiAdapter
from loouwd.main import app
from fastapi.testclient import TestClient


class TestTagAutocomplete(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_nhentai_adapter_autocomplete_tags(self):
        async def _test():
            adapter = NHentaiAdapter()
            suggestions = await adapter.autocomplete_tags("school", tag_type="tag")
            self.assertIsInstance(suggestions, list)
            self.assertGreater(len(suggestions), 0)
            self.assertTrue(any("school" in s.name.lower() for s in suggestions))

        asyncio.run(_test())

    def test_autocomplete_api_endpoint(self):
        response = self.client.get("/api/v1/sources/nhentai/tags/autocomplete?query=school&type=tag")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("name", data[0])


if __name__ == "__main__":
    unittest.main()
