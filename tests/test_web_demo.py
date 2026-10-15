import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class WebDemoTests(unittest.TestCase):
    def test_pages_copy_is_in_sync(self):
        from tools.sync_web import FILES
        for f in FILES:
            src = (ROOT / "gigguard" / f).read_text(encoding="utf-8")
            dst = (ROOT / "docs" / "py" / "gigguard" / f).read_text(encoding="utf-8")
            self.assertEqual(src, dst, f"docs/py/gigguard/{f} is stale: run python tools/sync_web.py")

    def test_index_lists_every_file(self):
        from tools.sync_web import FILES
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        for f in FILES:
            self.assertIn(f'"{f}"', html)


if __name__ == "__main__":
    unittest.main()
