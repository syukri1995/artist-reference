import json
import logging
import re
import threading
import urllib.request

logger = logging.getLogger(__name__)


class UpdateManager:
    def __init__(self, current_version, update_url):
        self.current_version = current_version
        self.update_url = update_url

    def check_for_updates(self, callback):
        """
        Runs the update check in a background thread and calls `callback` with
        (latest_version, release_notes, download_url) if an update is found.
        """
        def _check():
            try:
                # Add a user-agent to prevent 403 Forbidden from GitHub API
                req = urllib.request.Request(self.update_url, headers={'User-Agent': 'Mozilla/5.0 ArtistRefApp'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode())
                        
                        latest_version = data.get("tag_name", "").lstrip("vV")
                        release_notes = data.get("body", "No release notes provided.")
                        download_url = self._pick_download_url(data)

                        if self._is_newer(latest_version, self.current_version):
                            callback(latest_version, release_notes, download_url)
            except Exception as e:
                logger.debug("Update check failed: %s", e)

        check_thread = threading.Thread(target=_check, daemon=True)
        check_thread.start()

    @staticmethod
    def _pick_download_url(release_data: dict) -> str:
        """Prefer direct .zip/.exe asset URL over the GitHub release page."""
        preferred_names = (
            "ArtistReferenceManager-win64.zip",
            "ArtistReferenceManager.exe",
        )
        assets = release_data.get("assets") or []
        by_name = {a.get("name", ""): a for a in assets if isinstance(a, dict)}
        for name in preferred_names:
            asset = by_name.get(name)
            if asset:
                url = asset.get("browser_download_url", "")
                if url.startswith("https://"):
                    return url
        for asset in assets:
            name = asset.get("name", "")
            url = asset.get("browser_download_url", "")
            if url.startswith("https://") and (
                name.endswith(".zip") or name.endswith(".exe")
            ):
                return url
        return release_data.get("html_url", "")

    def _is_newer(self, latest, current):
        """Helper to compare semantic versions simply."""
        def parse_version(v):
            # Extract only digits and periods
            v = re.sub(r'[^0-9\.]', '', v)
            return [int(x) for x in v.split('.') if x.isdigit()]
            
        latest_parts = parse_version(latest)
        current_parts = parse_version(current)
        
        for l, c in zip(latest_parts, current_parts):
            if l > c: return True
            if l < c: return False
            
        # If all matched parts are equal, check if latest has more parts (e.g. 1.0.1 vs 1.0)
        return len(latest_parts) > len(current_parts)
