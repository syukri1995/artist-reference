import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.update_dialog import UpdateDialog


class TestSecurity(unittest.TestCase):
    @patch('webbrowser.open')
    def test_download_update_valid_url_https(self, mock_open):
        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = "https://example.com/download"

        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()

        mock_open.assert_called_once_with("https://example.com/download")
        mock_accept.assert_called_once()

    @patch('webbrowser.open')
    def test_download_update_valid_url_http(self, mock_open):
        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = "http://example.com/download"

        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()

        mock_open.assert_called_once_with("http://example.com/download")
        mock_accept.assert_called_once()

    @patch('webbrowser.open')
    def test_download_update_invalid_url_file(self, mock_open):
        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = "file:///etc/passwd"

        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()

        mock_open.assert_not_called()
        mock_accept.assert_called_once()

    @patch('webbrowser.open')
    def test_download_update_invalid_url_javascript(self, mock_open):
        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = "javascript:alert(1)"

        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()

        mock_open.assert_not_called()
        mock_accept.assert_called_once()


if __name__ == '__main__':
    unittest.main()
