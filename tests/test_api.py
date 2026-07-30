import unittest
from fastapi.testclient import TestClient
from loouwd.main import app


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("name", data)
        self.assertIn("active_adapters", data)
        self.assertEqual(len(data["active_adapters"]), 7)

    def test_list_sources_endpoint(self):
        response = self.client.get("/api/v1/sources")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 7)
        for item in data:
            icon = item.get("iconUrl") or item.get("icon_url")
            self.assertIsNotNone(icon)
            self.assertTrue(icon.startswith("http://") or icon.startswith("https://"))

    def test_get_single_source_endpoint(self):
        response = self.client.get("/api/v1/sources/nhentai")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "nhentai")
        icon = data.get("iconUrl") or data.get("icon_url")
        self.assertIsNotNone(icon)
        self.assertTrue(icon.startswith("http://") or icon.startswith("https://"))
        self.assertIn("x-ratelimit-limit", response.headers)

    def test_get_nonexistent_source_endpoint(self):
        response = self.client.get("/api/v1/sources/unknown_id")
        self.assertEqual(response.status_code, 404)

    def test_get_source_icon_endpoint(self):
        response = self.client.get("/api/v1/sources/nhentai/icon")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/"))
        self.assertGreater(len(response.content), 0)

    def test_get_nonexistent_source_icon_endpoint(self):
        response = self.client.get("/api/v1/sources/unknown_id/icon")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
