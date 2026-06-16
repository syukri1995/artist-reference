"""Persistent user preferences via QSettings."""

from PyQt5.QtCore import QSettings

_ORG = "ArtistReference"
_APP = "ArtistReferenceManager"


class AppSettings:
    def __init__(self) -> None:
        self._s = QSettings(_ORG, _APP)

    def get_opacity(self) -> int:
        return int(self._s.value("window/opacity", 100))

    def set_opacity(self, value: int) -> None:
        self._s.setValue("window/opacity", max(20, min(100, value)))

    def get_gallery_sort(self) -> str:
        return str(self._s.value("gallery/sort", "date_added_desc"))

    def set_gallery_sort(self, sort_key: str) -> None:
        self._s.setValue("gallery/sort", sort_key)

    def get_columns(self) -> int:
        return int(self._s.value("gallery/columns", 4))

    def set_columns(self, value: int) -> None:
        self._s.setValue("gallery/columns", max(2, min(8, value)))

    def get_workspace_slot(self) -> int:
        return int(self._s.value("workspace/slot", 1))

    def set_workspace_slot(self, slot: int) -> None:
        self._s.setValue("workspace/slot", max(1, min(5, slot)))

    def get_show_canvas_hint(self) -> bool:
        return self._s.value("workspace/show_canvas_hint", True, type=bool)

    def set_show_canvas_hint(self, show: bool) -> None:
        self._s.setValue("workspace/show_canvas_hint", show)

    def get_workspace_toolbar_visible(self) -> bool:
        return self._s.value("workspace/toolbar_visible", True, type=bool)

    def set_workspace_toolbar_visible(self, visible: bool) -> None:
        self._s.setValue("workspace/toolbar_visible", bool(visible))

    def get_workspace_float_mode(self) -> bool:
        return self._s.value("workspace/float_mode", False, type=bool)

    def set_workspace_float_mode(self, enabled: bool) -> None:
        self._s.setValue("workspace/float_mode", bool(enabled))

    def get_geometry(self) -> bytes | None:
        return self._s.value("window/geometry")

    def set_geometry(self, data: bytes) -> None:
        self._s.setValue("window/geometry", data)

    def get_recent_searches(self) -> list:
        raw = self._s.value("gallery/recent_searches", [])
        if isinstance(raw, list):
            return [str(x) for x in raw[:5]]
        if raw:
            return [str(raw)]
        return []

    def add_recent_search(self, term: str) -> None:
        term = term.strip()
        if not term:
            return
        recent = [t for t in self.get_recent_searches() if t != term]
        recent.insert(0, term)
        self._s.setValue("gallery/recent_searches", recent[:5])

    def get_danbooru_recent_tags(self) -> list:
        raw = self._s.value("danbooru/recent_tags", [])
        if isinstance(raw, list):
            return [str(x) for x in raw[:8]]
        if raw:
            return [str(raw)]
        return []

    def add_danbooru_recent_tag(self, tag_query: str) -> None:
        tag_query = tag_query.strip()
        if not tag_query:
            return
        recent = [t for t in self.get_danbooru_recent_tags() if t != tag_query]
        recent.insert(0, tag_query)
        self._s.setValue("danbooru/recent_tags", recent[:8])

    def get_danbooru_login(self) -> str:
        return str(self._s.value("danbooru/login", "")).strip()

    def set_danbooru_login(self, login: str) -> None:
        self._s.setValue("danbooru/login", login.strip())

    def get_danbooru_api_key(self) -> str:
        return str(self._s.value("danbooru/api_key", "")).strip()

    def set_danbooru_api_key(self, api_key: str) -> None:
        self._s.setValue("danbooru/api_key", api_key.strip())

    def get_workspace_slot_name(self, slot_id: int) -> str:
        return str(self._s.value(f"workspace/slot_name_{slot_id}", f"Slot {slot_id}"))

    def set_workspace_slot_name(self, slot_id: int, name: str) -> None:
        self._s.setValue(f"workspace/slot_name_{slot_id}", name.strip())

    def get_safe_mode(self) -> bool:
        return self._s.value("gallery/safe_mode", True, type=bool)

    def set_safe_mode(self, enabled: bool) -> None:
        self._s.setValue("gallery/safe_mode", bool(enabled))

    def get_items_per_page(self) -> int:
        return int(self._s.value("gallery/items_per_page", 50))

    def set_items_per_page(self, value: int) -> None:
        self._s.setValue("gallery/items_per_page", max(10, min(200, value)))

    def clear_danbooru_credentials(self) -> None:
        self._s.remove("danbooru/login")
        self._s.remove("danbooru/api_key")

    def sync(self) -> None:
        self._s.sync()


_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings
