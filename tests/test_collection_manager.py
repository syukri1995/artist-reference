import unittest
from unittest.mock import patch, MagicMock
from managers.collection_manager import CollectionManager

class TestCollectionManager(unittest.TestCase):
    def setUp(self):
        self.collection_manager = CollectionManager()

    @patch('managers.collection_manager.get_connection')
    def test_create_collection_success(self, mock_get_connection):
        # Setup mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Call the method
        result = self.collection_manager.create_collection("Test Collection", "Test Description")

        # Assertions
        self.assertTrue(result)
        mock_cursor.execute.assert_called_once()
        args, _ = mock_cursor.execute.call_args
        self.assertIn("INSERT INTO collections", args[0])
        self.assertEqual(args[1], ("Test Collection", "Test Description"))
        mock_conn.commit.assert_called_once()

    @patch('managers.collection_manager.get_connection')
    def test_create_collection_success_no_description(self, mock_get_connection):
        # Setup mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Call the method
        result = self.collection_manager.create_collection("Test Collection")

        # Assertions
        self.assertTrue(result)
        mock_cursor.execute.assert_called_once()
        args, _ = mock_cursor.execute.call_args
        self.assertEqual(args[1], ("Test Collection", ""))
        mock_conn.commit.assert_called_once()

    @patch('managers.collection_manager.get_connection')
    def test_create_collection_failure(self, mock_get_connection):
        # Setup mock to raise an exception
        mock_get_connection.side_effect = Exception("Database error")

        # Call the method
        result = self.collection_manager.create_collection("Test Collection")

        # Assertions
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
