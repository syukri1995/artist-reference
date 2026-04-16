import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock customtkinter before importing UI components
mock_ctk = MagicMock()
# CustomTkinter base class for UpdateDialog
class MockCTkToplevel:
    def __init__(self, *args, **kwargs):
        pass
mock_ctk.CTkToplevel = MockCTkToplevel
sys.modules['customtkinter'] = mock_ctk

from ui.update_dialog import UpdateDialog

class TestSecurity(unittest.TestCase):
    @patch('webbrowser.open')
    def test_download_update_valid_url_https(self, mock_open):
        # Setup
        master = MagicMock()
        url = "https://example.com/download"

        # Instantiate and mock methods that might cause issues
        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = url



        # Execute
        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()
            dialog.accept = mock_accept

        # Verify
        mock_open.assert_called_once_with(url)


    @patch('webbrowser.open')
    def test_download_update_valid_url_http(self, mock_open):
        # Setup
        master = MagicMock()
        url = "http://example.com/download"

        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = url



        # Execute
        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()
            dialog.accept = mock_accept

        # Verify
        mock_open.assert_called_once_with(url)


    @patch('webbrowser.open')
    def test_download_update_invalid_url_file(self, mock_open):
        # Setup
        master = MagicMock()
        dangerous_url = "file:///etc/passwd"

        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = dangerous_url


        # Execute
        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()
            dialog.accept = mock_accept

        # Verify
        mock_open.assert_not_called()


    @patch('webbrowser.open')
    def test_download_update_invalid_url_javascript(self, mock_open):
        # Setup
        master = MagicMock()
        dangerous_url = "javascript:alert(1)"

        dialog = UpdateDialog.__new__(UpdateDialog)
        dialog.download_url = dangerous_url


        # Execute
        with patch.object(dialog, 'accept') as mock_accept:
            dialog.download_update()
            dialog.accept = mock_accept

        # Verify
        mock_open.assert_not_called()


if __name__ == '__main__':
    unittest.main()
