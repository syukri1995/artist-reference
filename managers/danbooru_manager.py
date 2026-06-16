"""Danbooru API client for searching and downloading posts.

See https://danbooru.donmai.us/wiki_pages/help:api — use `only` to trim JSON,
HTTP Basic Auth for credentials, and respect the ~10 read requests/second limit.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from managers.http_cache import HttpClient

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://danbooru.donmai.us"
ALLOWED_HOSTS = frozenset({
    "danbooru.donmai.us",
    "hijiribe.donmai.us",
    "sonohara.donmai.us",
    "safebooru.donmai.us",
    "cdn.donmai.us",
})
# Grid search: omit tag_string (large); tags fetched in one batch on import if needed.
POST_SEARCH_ONLY = "id,file_url,large_file_url,preview_file_url,file_ext,rating"
POST_TAGS_ONLY = "id,tag_string"
TAG_JSON_ONLY = "id,name,post_count"
_TAG_CACHE_TTL_SEC = 3600
USER_AGENT = "ArtistReferenceManager/1.0 (desktop reference tool)"
# Cap preview downloads; full originals are fetched only on import.
MAX_PREVIEW_BYTES = 2 * 1024 * 1024
API_CACHE_SEC = 600
COUNT_CACHE_SEC = 300
PREVIEW_CACHE_SEC = 86400 * 7
HTTP_TIMEOUT = (5, 25)


@dataclass
class DanbooruPost:
    id: int
    rating: str
    tag_string: str
    file_url: str | None
    large_file_url: str | None
    preview_url: str | None
    file_ext: str

    @property
    def preview_source_url(self) -> str | None:
        """Compressed URL for grid display only (never the original file)."""
        return self.preview_url or self.large_file_url

    @property
    def full_file_url(self) -> str | None:
        """Original file — downloaded only when importing to the library."""
        return self.file_url

    @property
    def tag_list(self) -> list[str]:
        return [t for t in self.tag_string.split() if t]


class DanbooruError(Exception):
    pass


class DanbooruManager:
    _shared_http: HttpClient | None = None

    @staticmethod
    def _login_from_config() -> str:
        for key in ("DANBOORU_LOGIN", "DANBOORU_USERNAME"):
            val = os.environ.get(key, "").strip()
            if val:
                return val
        try:
            from app_settings import get_settings

            return get_settings().get_danbooru_login()
        except Exception:
            return ""

    @staticmethod
    def _api_key_from_config() -> str:
        val = os.environ.get("DANBOORU_API_KEY", "").strip()
        if val:
            return val
        try:
            from app_settings import get_settings

            return get_settings().get_danbooru_api_key()
        except Exception:
            return ""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("DANBOORU_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._validate_base_url(self.base_url)
        self.login = self._login_from_config()
        self.api_key = self._api_key_from_config()
        if DanbooruManager._shared_http is None:
            verify = os.environ.get("DANBOORU_SSL_VERIFY", "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )
            DanbooruManager._shared_http = HttpClient(USER_AGENT, verify_ssl=verify)
        self._http = DanbooruManager._shared_http
        self._tag_cache: dict[str, tuple[float, list[dict]]] = {}

    @staticmethod
    def _validate_base_url(url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise DanbooruError(f"Invalid Danbooru URL scheme: {url}")
        host = (parsed.hostname or "").lower()
        if host not in ALLOWED_HOSTS:
            raise DanbooruError(
                f"Host not allowed: {host}. Use danbooru.donmai.us or set DANBOORU_BASE_URL."
            )

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise DanbooruError("Invalid download URL")
        host = (parsed.hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
            if "donmai.us" not in host and "safebooru.org" not in host:
                raise DanbooruError(f"Download host not allowed: {host}")

    def _auth(self) -> tuple[str, str] | None:
        if self.login and self.api_key:
            return (self.login, self.api_key)
        return None

    def _build_url(self, path: str, query: dict | None = None) -> str:
        params = dict(query or {})
        qs = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        if qs:
            url = f"{url}?{qs}"
        return url

    def _request_json(
        self,
        path: str,
        query: dict | None = None,
        *,
        cache_sec: int = API_CACHE_SEC,
    ) -> list | dict:
        url = self._build_url(path, query)
        try:
            return self._http.fetch_json(
                url,
                max_age_sec=cache_sec,
                timeout=HTTP_TIMEOUT,
                auth=self._auth(),
            )
        except Exception as exc:
            raise DanbooruError(f"Network error: {exc}") from exc

    def _fetch_url_bytes(
        self,
        url: str,
        *,
        max_bytes: int | None = None,
        cache_sec: int = PREVIEW_CACHE_SEC,
    ) -> bytes:
        self._validate_download_url(url)
        try:
            if cache_sec <= 0:
                data = self._http.fetch_bytes(
                    url,
                    timeout=HTTP_TIMEOUT,
                    use_cache=False,
                    auth=self._auth(),
                )
            else:
                data = self._http.fetch_bytes(
                    url,
                    timeout=HTTP_TIMEOUT,
                    max_age_sec=cache_sec,
                    auth=self._auth(),
                )
        except Exception as exc:
            raise DanbooruError(f"Download failed: {exc}") from exc
        if max_bytes and len(data) > max_bytes:
            raise DanbooruError(f"Response too large (>{max_bytes} bytes)")
        return data

    @staticmethod
    def normalize_user_tags(user_tags: str) -> str:
        """Danbooru tags use underscores; spaces break many searches."""
        return user_tags.strip().replace(" ", "_")

    @staticmethod
    def build_tags_query(user_tags: str, rating: str | None) -> str:
        """Combine user tags with optional rating filter."""
        normalized = DanbooruManager.normalize_user_tags(user_tags)
        parts = [normalized] if normalized else []
        if rating and rating != "all":
            parts.append(f"rating:{rating}")
        return " ".join(parts).strip() or "rating:general"

    def suggest_tags(self, prefix: str, limit: int = 12) -> list[dict]:
        """Return tag suggestions (cached; filters client-side when possible)."""
        prefix = prefix.strip().replace(" ", "_").lower()
        if len(prefix) < 2:
            return []

        bucket = prefix[:2] if len(prefix) < 4 else prefix[:3]
        cached = self._tag_cache.get(bucket)
        if cached and (time.time() - cached[0]) < _TAG_CACHE_TTL_SEC:
            return self._filter_tag_suggestions(cached[1], prefix, limit)

        items = self._fetch_tag_suggestions(prefix, bucket)
        self._tag_cache[bucket] = (time.time(), items)
        return self._filter_tag_suggestions(items, prefix, limit)

    def _fetch_tag_suggestions(self, prefix: str, bucket: str) -> list[dict]:
        """Prefer /tags/autocomplete.json (built for typing); fall back to /tags.json."""
        pattern = f"{prefix}*"
        try:
            data = self._request_json(
                "/tags/autocomplete.json",
                {
                    "search[name_matches]": pattern,
                    "limit": 40,
                },
            )
            if isinstance(data, list):
                items = self._parse_tag_records(data)
                if items:
                    return items
        except DanbooruError as exc:
            logger.debug("Tag autocomplete failed: %s", exc)

        data = self._request_json(
            "/tags.json",
            {
                "search[name_matches]": f"{bucket}*",
                "search[order]": "count",
                "limit": 40,
                "only": TAG_JSON_ONLY,
            },
        )
        if not isinstance(data, list):
            return []
        return self._parse_tag_records(data)

    @staticmethod
    def _parse_tag_records(data: list) -> list[dict]:
        items: list[dict] = []
        for t in data:
            if not isinstance(t, dict):
                continue
            name = t.get("name")
            if not name:
                continue
            items.append(
                {"name": str(name), "post_count": int(t.get("post_count") or 0)}
            )
        return items

    @staticmethod
    def _filter_tag_suggestions(items: list[dict], prefix: str, limit: int) -> list[dict]:
        prefix = prefix.lower()
        scored: list[tuple[int, dict]] = []
        for item in items:
            name = item["name"].lower()
            if name.startswith(prefix):
                score = 0
            elif prefix in name:
                score = 1
            else:
                continue
            scored.append((score, item))
        scored.sort(key=lambda x: (-x[1]["post_count"], x[0], x[1]["name"]))
        out: list[dict] = []
        seen: set[str] = set()
        for _, item in scored:
            if item["name"] in seen:
                continue
            seen.add(item["name"])
            out.append(item)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def current_token(text: str) -> str:
        """Last tag token being typed (after final space)."""
        text = text.strip()
        if not text:
            return ""
        if " " in text:
            return text.rsplit(" ", 1)[-1].strip()
        return text

    @staticmethod
    def apply_tag_token(full_text: str, tag_name: str) -> str:
        """Insert/replace the active token with a chosen tag name."""
        tag_name = tag_name.strip().replace(" ", "_")
        full_text = full_text.strip()
        if not full_text or " " not in full_text:
            return tag_name
        base = full_text.rsplit(" ", 1)[0]
        return f"{base} {tag_name}".strip()

    def count_posts(self, tags: str) -> int | None:
        """Total matching posts via GET /counts/posts.json (help:api)."""
        try:
            data = self._request_json(
                "/counts/posts.json",
                {"tags": tags},
                cache_sec=COUNT_CACHE_SEC,
            )
        except DanbooruError:
            return None
        return self._parse_post_count(data)

    @staticmethod
    def _parse_post_count(data: object) -> int | None:
        if isinstance(data, list) and data:
            row = data[0]
            if isinstance(row, dict):
                for key in ("posts", "count", "post_count"):
                    if key in row:
                        try:
                            return int(row[key])
                        except (TypeError, ValueError):
                            pass
        if isinstance(data, dict):
            counts = data.get("counts")
            if isinstance(counts, dict) and "posts" in counts:
                try:
                    return int(counts["posts"])
                except (TypeError, ValueError):
                    pass
            if "posts" in data:
                try:
                    return int(data["posts"])
                except (TypeError, ValueError):
                    pass
        return None

    def search_posts(
        self,
        tags: str,
        *,
        page: int = 1,
        limit: int = 40,
        before_id: int | None = None,
        after_id: int | None = None,
    ) -> list[DanbooruPost]:
        if limit < 1 or limit > 200:
            limit = 40
        query: dict[str, str | int] = {
            "tags": tags,
            "limit": limit,
            "only": POST_SEARCH_ONLY,
        }
        # With id-desc results: b{id} = older page after id, a{id} = newer page before id.
        if before_id is not None:
            query["page"] = f"b{before_id}"
        elif after_id is not None:
            query["page"] = f"a{after_id}"
        else:
            query["page"] = max(1, page)
        data = self._request_json("/posts.json", query)
        if not isinstance(data, list):
            raise DanbooruError("Unexpected API response")
        posts: list[DanbooruPost] = []
        for raw in data:
            post = self._parse_post(raw)
            if post and post.preview_source_url:
                posts.append(post)
        return posts

    def enrich_posts_with_tags(self, posts: list[DanbooruPost]) -> None:
        """One API call to fill tag_string before import (search omits tags for speed)."""
        ids = [p.id for p in posts if p.id]
        if not ids:
            return
        id_param = ",".join(str(i) for i in ids[:200])
        try:
            data = self._request_json(
                "/posts.json",
                {
                    "search[id]": id_param,
                    "search[order]": "custom",
                    "limit": min(len(ids), 200),
                    "only": POST_TAGS_ONLY,
                },
            )
        except DanbooruError as exc:
            logger.warning("Batch tag fetch failed: %s", exc)
            return
        if not isinstance(data, list):
            return
        by_id: dict[int, str] = {}
        for raw in data:
            try:
                by_id[int(raw["id"])] = str(raw.get("tag_string") or "")
            except (KeyError, TypeError, ValueError):
                continue
        for post in posts:
            if post.id in by_id:
                post.tag_string = by_id[post.id]

    def fetch_post_tag_string(self, post_id: int) -> str:
        """Fetch tag_string for one post (fallback when batch enrich missed it)."""
        try:
            data = self._request_json(
                "/posts.json",
                {
                    "search[id]": str(post_id),
                    "limit": 1,
                    "only": POST_TAGS_ONLY,
                },
            )
        except DanbooruError as exc:
            logger.debug("Tag fetch for post %s failed: %s", post_id, exc)
            return ""
        if isinstance(data, list) and data:
            return str(data[0].get("tag_string") or "")
        return ""

    @staticmethod
    def _parse_post(raw: dict) -> DanbooruPost | None:
        try:
            post_id = int(raw["id"])
        except (KeyError, TypeError, ValueError):
            return None
        return DanbooruPost(
            id=post_id,
            rating=str(raw.get("rating") or ""),
            tag_string=str(raw.get("tag_string") or ""),
            file_url=raw.get("file_url"),
            large_file_url=raw.get("large_file_url"),
            preview_url=raw.get("preview_file_url") or raw.get("preview_url"),
            file_ext=str(raw.get("file_ext") or "jpg"),
        )

    def download_post(self, post: DanbooruPost, dest_dir: Path | None = None) -> Path:
        """Download full-resolution original (import only)."""
        url = post.full_file_url
        if not url:
            raise DanbooruError(
                f"Post {post.id} has no original file URL — cannot import full resolution"
            )
        self._validate_download_url(url)

        ext = post.file_ext.lower().lstrip(".")
        if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
            ext = "jpg"
        safe_name = re.sub(r"[^\w.\-]", "_", f"danbooru_{post.id}.{ext}")

        if dest_dir is None:
            dest_dir = Path(tempfile.gettempdir()) / "artist_ref_danbooru"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / safe_name

        data = self._fetch_url_bytes(url, max_bytes=50 * 1024 * 1024, cache_sec=0)
        
        # Validation: Check for HTML tags at start of data (common on expired/protected links)
        if data.startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
            raise DanbooruError(
                f"Post {post.id} download returned HTML instead of an image. "
                "This usually means the direct link has expired or the file is protected."
            )
            
        dest.write_bytes(data)
        return dest

    def fetch_preview_bytes(self, post: DanbooruPost) -> bytes | None:
        """Download a compressed preview/sample — never the original file."""
        url = post.preview_source_url
        if not url:
            return None
        try:
            self._validate_download_url(url)
        except DanbooruError:
            return None
        try:
            return self._fetch_url_bytes(url, max_bytes=MAX_PREVIEW_BYTES)
        except DanbooruError:
            return None
        except Exception as exc:
            logger.debug("Preview fetch failed for %s: %s", post.id, exc)
            return None

    def can_import_full_resolution(self, post: DanbooruPost) -> bool:
        return bool(post.full_file_url)

    def has_credentials(self) -> bool:
        return bool(self.login and self.api_key)

    def reload_credentials(self) -> None:
        """Reload login/api_key from env or saved settings (no restart needed)."""
        self.login = self._login_from_config()
        self.api_key = self._api_key_from_config()
