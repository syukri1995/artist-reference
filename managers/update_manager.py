import threading
import urllib.request
import json
import re

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
                        download_url = data.get("html_url", "")
                        
                        if self._is_newer(latest_version, self.current_version):
                            callback(latest_version, release_notes, download_url)
            except Exception as e:
                # Silently fail if offline or API rate limited
                print(f"Update check failed silently: {e}")

        check_thread = threading.Thread(target=_check, daemon=True)
        check_thread.start()

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
