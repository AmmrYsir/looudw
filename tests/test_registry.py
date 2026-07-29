import unittest
from loouwd.core.registry import registry
import loouwd.adapters  # Trigger adapter registration


class TestRegistry(unittest.TestCase):
    def test_registry_registration(self):
        manifests = registry.list_manifests()
        self.assertEqual(len(manifests), 7)
        source_ids = {m.id for m in manifests}
        expected_ids = {"nhentai", "xvideos", "spankbang", "omegascans", "rule34world", "xhamster", "hentai20"}
        self.assertTrue(expected_ids.issubset(source_ids))

    def test_registry_get_adapter(self):
        adapter = registry.get("nhentai")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.manifest.id, "nhentai")
        self.assertEqual(adapter.manifest.name, "nhentai")

    def test_registry_get_nonexistent(self):
        adapter = registry.get("nonexistent_source")
        self.assertIsNone(adapter)
        with self.assertRaises(KeyError):
            registry.get_or_raise("nonexistent_source")


if __name__ == "__main__":
    unittest.main()
