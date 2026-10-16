import json
import unittest
from pathlib import Path

from recorder import make_url

ROOT = Path(__file__).resolve().parents[1]


class RecorderConfigTests(unittest.TestCase):
    def test_relative_route(self):
        self.assertEqual(make_url("https://haryomix.eu.cc", "/pdf-editor"), "https://haryomix.eu.cc/pdf-editor")

    def test_root_route(self):
        self.assertEqual(make_url("https://haryomix.eu.cc/", "/"), "https://haryomix.eu.cc/")

    def test_absolute_route_is_preserved(self):
        self.assertEqual(make_url("https://haryomix.eu.cc", "https://example.org/demo"), "https://example.org/demo")

    def test_default_config_targets_haryomix_and_discovers_pages(self):
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["base_url"], "https://haryomix.eu.cc")
        self.assertEqual(cfg["browser"]["viewport"], {"width": 1920, "height": 1080})
        self.assertTrue(cfg["auto_discover"]["enabled"])
        self.assertGreater(cfg["auto_discover"]["max_pages"], 0)


if __name__ == "__main__":
    unittest.main()
