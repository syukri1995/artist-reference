"""Live Danbooru API smoke test (uses .env; never prints secrets)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

env_path = ROOT / ".env"
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

from managers.danbooru_manager import DanbooruError, DanbooruManager


def main() -> int:
    mgr = DanbooruManager()
    login_set = bool(
        os.environ.get("DANBOORU_LOGIN", "").strip()
        or os.environ.get("DANBOORU_USERNAME", "").strip()
    )
    key_set = bool(os.environ.get("DANBOORU_API_KEY", "").strip())
    print(f"Base URL: {mgr.base_url}")
    print(f"Credentials: {'configured' if mgr.has_credentials() else 'missing'}")
    print(f"  login/username set: {login_set}")
    print(f"  DANBOORU_API_KEY set: {key_set}")

    if not mgr.has_credentials():
        print("WARN: Set DANBOORU_LOGIN and DANBOORU_API_KEY in .env")
        return 1

    try:
        posts = mgr.search_posts("rating:general", page=1, limit=3)
    except DanbooruError as exc:
        print(f"Search FAILED: {exc}")
        return 1

    print(f"Search OK — {len(posts)} post(s)")
    for post in posts:
        print(f"  #{post.id} rating={post.rating} downloadable={bool(post.full_file_url)}")

    if not posts:
        print("No posts returned (try different tags).")
        return 0

    preview = mgr.fetch_preview_bytes(posts[0])
    size = len(preview) if preview else 0
    print(f"Preview for #{posts[0].id}: {'OK' if size > 100 else 'FAILED'} ({size} bytes)")
    return 0 if size > 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
