"""Tag editor with search and inline tag creation."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from managers.tag_manager import TagManager


class TagEditDialog(QDialog):
    def __init__(
        self,
        parent,
        tag_mgr: TagManager,
        image_ids: list[int],
        on_saved=None,
    ) -> None:
        super().__init__(parent)
        self.tag_mgr = tag_mgr
        self.image_ids = image_ids
        self._on_saved = on_saved
        n = len(image_ids)
        self.setWindowTitle("Edit Tags")
        self.setMinimumSize(360, 420)

        root = QVBoxLayout(self)
        header = QLabel(f"Applying to {n} image{'s' if n != 1 else ''}")
        header.setStyleSheet("font-weight: bold; color: #E2E8F0;")
        root.addWidget(header)

        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("Filter tags…")
        self.search_entry.setClearButtonEnabled(True)
        self.search_entry.textChanged.connect(self._filter_tags)
        root.addWidget(self.search_entry)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._tag_container = QWidget()
        self._tag_layout = QVBoxLayout(self._tag_container)
        self._tag_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._tag_container)
        root.addWidget(scroll, stretch=1)

        create_row = QHBoxLayout()
        self.new_tag_entry = QLineEdit()
        self.new_tag_entry.setPlaceholderText("New tag name")
        self.new_tag_entry.setClearButtonEnabled(True)
        create_row.addWidget(self.new_tag_entry, stretch=1)
        add_btn = QPushButton("Create")
        add_btn.clicked.connect(self._create_tag)
        create_row.addWidget(add_btn)
        root.addLayout(create_row)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("background-color: #7C3AED; border-color: #6D28D9;")
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

        self._checkboxes: dict[int, QCheckBox] = {}
        self._all_tags = sorted(tag_mgr.get_tags(), key=lambda t: t["name"].lower())
        single = n == 1
        active_ids = (
            {t["id"] for t in tag_mgr.get_tags_for_image(image_ids[0])}
            if single
            else set()
        )
        for t in self._all_tags:
            cb = QCheckBox(t["name"])
            cb.setChecked(t["id"] in active_ids)
            self._checkboxes[t["id"]] = cb
            self._tag_layout.addWidget(cb)

    def _filter_tags(self, text: str) -> None:
        needle = text.strip().lower()
        for tid, cb in self._checkboxes.items():
            cb.setVisible(not needle or needle in cb.text().lower())

    def _create_tag(self) -> None:
        name = self.new_tag_entry.text().strip()
        if not name or not self.tag_mgr.create_tag(name):
            return
        self.new_tag_entry.clear()
        tags = self.tag_mgr.get_tags()
        new_tag = next((t for t in tags if t["name"] == name), None)
        if new_tag and new_tag["id"] not in self._checkboxes:
            cb = QCheckBox(name)
            cb.setChecked(True)
            self._checkboxes[new_tag["id"]] = cb
            self._tag_layout.addWidget(cb)
            self._all_tags.append(new_tag)

    def _save(self) -> None:
        selected = [tid for tid, cb in self._checkboxes.items() if cb.isChecked()]
        for img_id in self.image_ids:
            self.tag_mgr.remove_all_tags_from_image(img_id)
            self.tag_mgr.add_tags_to_image(img_id, selected)
        if self._on_saved:
            try:
                self._on_saved(len(self.image_ids))
            except TypeError:
                # Handle cases where the callback doesn't expect arguments (e.g. GalleryView.load_gallery)
                self._on_saved()
        self.accept()
