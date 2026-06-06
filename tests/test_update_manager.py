import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.update_manager import UpdateManager


class TestUpdateManager(unittest.TestCase):
    def test_pick_download_url_prefers_zip(self):
        data = {
            "html_url": "https://github.com/org/repo/releases/tag/v1.0.0",
            "assets": [
                {
                    "name": "ArtistReferenceManager.exe",
                    "browser_download_url": "https://github.com/org/repo/releases/download/v1.0.0/ArtistReferenceManager.exe",
                },
                {
                    "name": "ArtistReferenceManager-win64.zip",
                    "browser_download_url": "https://github.com/org/repo/releases/download/v1.0.0/ArtistReferenceManager-win64.zip",
                },
            ],
        }
        url = UpdateManager._pick_download_url(data)
        self.assertTrue(url.endswith(".zip"))

    def test_pick_download_url_falls_back_to_exe(self):
        data = {
            "html_url": "https://github.com/org/repo/releases/tag/v1.0.0",
            "assets": [
                {
                    "name": "ArtistReferenceManager.exe",
                    "browser_download_url": "https://github.com/org/repo/releases/download/v1.0.0/ArtistReferenceManager.exe",
                },
            ],
        }
        url = UpdateManager._pick_download_url(data)
        self.assertTrue(url.endswith(".exe"))

    def test_pick_download_url_falls_back_to_html(self):
        data = {"html_url": "https://github.com/org/repo/releases/tag/v1.0.0", "assets": []}
        url = UpdateManager._pick_download_url(data)
        self.assertEqual(url, data["html_url"])

    def test_is_newer(self):
        mgr = UpdateManager("1.0.0", "")
        self.assertTrue(mgr._is_newer("1.0.1", "1.0.0"))
        self.assertFalse(mgr._is_newer("1.0.0", "1.0.0"))
        self.assertFalse(mgr._is_newer("0.9.9", "1.0.0"))


if __name__ == "__main__":
    unittest.main()
