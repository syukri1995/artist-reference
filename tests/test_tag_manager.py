import unittest
from unittest.mock import patch, MagicMock
from managers.tag_manager import TagManager

class TestTagManager(unittest.TestCase):
    def setUp(self):
        self.tag_manager = TagManager()

    @patch('managers.tag_manager.get_connection')
    def test_tag_image_success(self, mock_get_connection):
        # Setup mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Call the method
        result = self.tag_manager.tag_image(1, 1)

        # Assertions
        self.assertTrue(result)
        mock_cursor.executemany.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch('managers.tag_manager.get_connection')
    def test_tag_image_failure(self, mock_get_connection):
        # Setup mock to raise an exception
        mock_get_connection.side_effect = Exception("Database error")

        # Call the method
        result = self.tag_manager.tag_image(1, 1)

        # Assertions
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
