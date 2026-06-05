"""Disk cache and pooled HTTP client for faster repeated downloads."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import certifi

from database import get_base_dir

logger = logging.getLogger(__name__)

_HAS_REQUESTS = None
requests = None  # type: ignore
HTTPAdapter = None  # type: ignore


def _ensure_requests() -> bool:
    global _HAS_REQUESTS, requests, HTTPAdapter
    if _HAS_REQUESTS is not None:
        return _HAS_REQUESTS
    try:
        import requests as _requests
        from requests.adapters import HTTPAdapter as _HTTPAdapter

        requests = _requests
        HTTPAdapter = _HTTPAdapter
        _HAS_REQUESTS = True
    except ImportError:
        _HAS_REQUESTS = False
    return _HAS_REQUESTS


def _cache_dir() -> Path:
    base = os.environ.get("ARTIST_REF_DATA_DIR")
    root = Path(base) if base else get_base_dir() / "data"
    path = root / "cache" / "http"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _url_key(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return _cache_dir() / digest[:2] / f"{digest}.bin"


class DiskHttpCache:
    def get_bytes(self, url: str, max_age_sec: int) -> bytes | None:
        path = _url_key(url)
        meta = path.with_suffix(".meta")
        if not path.exists():
            return None
        try:
            if meta.exists():
                ts = float(meta.read_text(encoding="utf-8").strip())
                if time.time() - ts > max_age_sec:
                    return None
            return path.read_bytes()
        except OSError as exc:
            logger.debug("cache read %s: %s", url[:60], exc)
            return None

    def put_bytes(self, url: str, data: bytes) -> None:
        path = _url_key(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.with_suffix(".meta").write_text(str(time.time()), encoding="utf-8")
        except OSError as exc:
            logger.debug("cache write %s: %s", url[:60], exc)

    def get_json(self, url: str, max_age_sec: int):
        raw = self.get_bytes(url, max_age_sec)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def put_json(self, url: str, data) -> None:
        self.put_bytes(url, json.dumps(data).encode("utf-8"))


class _RateLimiter:
    """Stay under Danbooru's global ~10 read requests/second (help:api)."""

    def __init__(self, min_interval: float = 0.11) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
            self._next_allowed = time.monotonic() + self._min_interval


_RETRYABLE_STATUS = frozenset({429, 502, 503})


class HttpClient:
    """Keep-alive HTTP with optional disk cache."""

    def __init__(self, user_agent: str, verify_ssl: bool | None = None) -> None:
        self.user_agent = user_agent
        self._cache = DiskHttpCache()
        self._rate_limiter = _RateLimiter()
        if verify_ssl is None:
            verify_ssl = os.environ.get("DANBOORU_SSL_VERIFY", "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )
        self._verify = verify_ssl
        self._session = self._build_session() if _ensure_requests() else None

    def _build_session(self):
        session = requests.Session()
        session.headers["User-Agent"] = self.user_agent
        session.verify = certifi.where() if self._verify else False
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=1)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get_with_retries(
        self,
        url: str,
        *,
        timeout: tuple[float, float],
        auth: tuple[str, str] | None = None,
    ) -> bytes:
        last_error: Exception | None = None
        for attempt in range(4):
            self._rate_limiter.wait()
            try:
                if self._session is not None:
                    resp = self._session.get(url, timeout=timeout, auth=auth)
                    if resp.status_code in _RETRYABLE_STATUS and attempt < 3:
                        delay = 0.4 * (attempt + 1)
                        if resp.status_code == 429:
                            delay = max(delay, 1.0)
                        logger.debug(
                            "HTTP %s for %s — retry in %.1fs",
                            resp.status_code,
                            url[:80],
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    resp.raise_for_status()
                    return resp.content
                import ssl
                import urllib.request

                ctx = ssl.create_default_context(cafile=certifi.where())
                if not self._verify:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
                if auth:
                    import base64

                    token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode("ascii")
                    req.add_header("Authorization", f"Basic {token}")
                with urllib.request.urlopen(req, timeout=timeout[1], context=ctx) as resp:
                    return resp.read()
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("unreachable")

    def fetch_bytes(
        self,
        url: str,
        *,
        timeout: tuple[float, float] = (5, 25),
        max_age_sec: int = 86400,
        use_cache: bool = True,
        auth: tuple[str, str] | None = None,
    ) -> bytes:
        if use_cache:
            cached = self._cache.get_bytes(url, max_age_sec)
            if cached is not None:
                return cached

        data = self._get_with_retries(url, timeout=timeout, auth=auth)

        if use_cache:
            self._cache.put_bytes(url, data)
        return data

    def fetch_json(
        self,
        url: str,
        *,
        max_age_sec: int = 600,
        timeout: tuple[float, float] = (5, 25),
        auth: tuple[str, str] | None = None,
    ) -> Any:
        if max_age_sec > 0:
            cached = self._cache.get_json(url, max_age_sec)
            if cached is not None:
                return cached
        data = self.fetch_bytes(
            url,
            timeout=timeout,
            max_age_sec=0,
            use_cache=False,
            auth=auth,
        )
        parsed = json.loads(data.decode("utf-8"))
        if max_age_sec > 0:
            self._cache.put_json(url, parsed)
        return parsed
