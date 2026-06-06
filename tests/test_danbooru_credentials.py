import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.danbooru_manager import DanbooruManager


class TestDanbooruCredentials(unittest.TestCase):
    def setUp(self):
        for key in ("DANBOORU_LOGIN", "DANBOORU_USERNAME", "DANBOORU_API_KEY"):
            os.environ.pop(key, None)

    def test_reads_from_app_settings_when_env_missing(self):
        mock_settings = unittest.mock.Mock()
        mock_settings.get_danbooru_login.return_value = "saved_user"
        mock_settings.get_danbooru_api_key.return_value = "saved_key"

        with patch("app_settings.get_settings", return_value=mock_settings):
            mgr = DanbooruManager()

        self.assertEqual(mgr.login, "saved_user")
        self.assertEqual(mgr.api_key, "saved_key")
        self.assertTrue(mgr.has_credentials())

    def test_env_overrides_app_settings(self):
        os.environ["DANBOORU_LOGIN"] = "env_user"
        os.environ["DANBOORU_API_KEY"] = "env_key"
        mock_settings = unittest.mock.Mock()
        mock_settings.get_danbooru_login.return_value = "saved_user"
        mock_settings.get_danbooru_api_key.return_value = "saved_key"

        with patch("app_settings.get_settings", return_value=mock_settings):
            mgr = DanbooruManager()

        self.assertEqual(mgr.login, "env_user")
        self.assertEqual(mgr.api_key, "env_key")

    def test_reload_credentials_picks_up_settings(self):
        mock_settings = unittest.mock.Mock()
        mock_settings.get_danbooru_login.return_value = ""
        mock_settings.get_danbooru_api_key.return_value = ""

        with patch("app_settings.get_settings", return_value=mock_settings):
            mgr = DanbooruManager()
            self.assertFalse(mgr.has_credentials())

            mock_settings.get_danbooru_login.return_value = "new_user"
            mock_settings.get_danbooru_api_key.return_value = "new_key"
            mgr.reload_credentials()

        self.assertTrue(mgr.has_credentials())
        self.assertEqual(mgr.login, "new_user")


if __name__ == "__main__":
    unittest.main()
