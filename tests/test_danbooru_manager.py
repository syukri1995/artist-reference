import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.danbooru_manager import (
    POST_SEARCH_ONLY,
    DanbooruManager,
    DanbooruPost,
)


class TestDanbooruManager(unittest.TestCase):
    def test_normalize_user_tags(self):
        self.assertEqual(
            DanbooruManager.normalize_user_tags("nami (one piece)"),
            "nami_(one_piece)",
        )

    def test_build_tags_query(self):
        q = DanbooruManager.build_tags_query("1girl solo", "general")
        self.assertIn("1girl", q)
        self.assertIn("rating:general", q)

    def test_build_tags_query_empty_uses_default(self):
        q = DanbooruManager.build_tags_query("", "all")
        self.assertEqual(q, "rating:general")

    def test_parse_post(self):
        raw = {
            "id": 123,
            "rating": "g",
            "tag_string": "1girl solo",
            "file_url": "https://danbooru.donmai.us/data/original/ab/cd/file.jpg",
            "preview_file_url": "https://danbooru.donmai.us/data/preview/ab/cd/file.jpg",
            "file_ext": "jpg",
        }
        post = DanbooruManager._parse_post(raw)
        self.assertIsNotNone(post)
        self.assertEqual(post.id, 123)
        self.assertEqual(post.tag_list, ["1girl", "solo"])
        self.assertEqual(post.preview_source_url, raw["preview_file_url"])
        self.assertEqual(post.full_file_url, raw["file_url"])

    def test_invalid_base_url_rejected(self):
        with self.assertRaises(Exception):
            DanbooruManager("https://evil.example.com")

    def test_build_url_omits_credentials(self):
        mgr = DanbooruManager()
        mgr.login = "user"
        mgr.api_key = "secret"
        url = mgr._build_url("/posts.json", {"tags": "1girl", "limit": 1})
        self.assertNotIn("api_key", url)
        self.assertNotIn("login", url)
        self.assertEqual(mgr._auth(), ("user", "secret"))

    def test_search_only_excludes_tag_string(self):
        self.assertNotIn("tag_string", POST_SEARCH_ONLY)

    def test_parse_post_count(self):
        self.assertEqual(DanbooruManager._parse_post_count([{"posts": 42}]), 42)
        self.assertEqual(
            DanbooruManager._parse_post_count({"counts": {"posts": 1000}}),
            1000,
        )

    def test_search_posts_cursor_pages(self):
        mgr = DanbooruManager()
        captured: dict = {}

        def fake_request(path, query=None, **kwargs):
            captured.clear()
            captured.update(query or {})
            return []

        mgr._request_json = fake_request  # type: ignore[method-assign]
        mgr.search_posts("1girl", before_id=500)
        self.assertEqual(captured.get("page"), "b500")
        mgr.search_posts("1girl", after_id=999)
        self.assertEqual(captured.get("page"), "a999")

    def test_enrich_posts_with_tags(self):
        mgr = DanbooruManager()
        posts = [
            DanbooruPost(1, "g", "", None, None, None, "jpg"),
            DanbooruPost(2, "g", "", None, None, None, "jpg"),
        ]

        def fake_request(path, query=None):
            self.assertEqual(path, "/posts.json")
            self.assertIn("search[id]", query or {})
            return [
                {"id": 1, "tag_string": "1girl solo"},
                {"id": 2, "tag_string": "landscape"},
            ]

        mgr._request_json = fake_request  # type: ignore[method-assign]
        mgr.enrich_posts_with_tags(posts)
        self.assertEqual(posts[0].tag_string, "1girl solo")
        self.assertEqual(posts[1].tag_string, "landscape")

    def test_fetch_post_tag_string(self):
        mgr = DanbooruManager()

        def fake_request(path, query=None, **kwargs):
            self.assertEqual(query.get("search[id]"), "42")
            return [{"id": 42, "tag_string": "1girl solo"}]

        mgr._request_json = fake_request  # type: ignore[method-assign]
        self.assertEqual(mgr.fetch_post_tag_string(42), "1girl solo")


if __name__ == "__main__":
    unittest.main()
