import os
import hashlib
from pathlib import Path
from PIL import Image
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QScrollArea, QCheckBox, QFileDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
from managers.image_manager import ImageManager

class ProcessWorker(QThread):
    item_processed = pyqtSignal(dict)
    
    def __init__(self, items, image_mgr):
        super().__init__()
        self.items = items
        self.image_mgr = image_mgr
        
    def run(self):
        for item in self.items:
            try:
                # 1. Generate small thumbnail QPixmap bytes-like via PIL
                img = Image.open(item['path'])
                img.thumbnail((100, 100))
                
                # Convert PIL to QImage safely without crashing Python C bindings
                if img.mode == "RGB":
                    r, g, b = img.split()
                    img = Image.merge("RGB", (b, g, r))
                elif img.mode == "RGBA":
                    r, g, b, a = img.split()
                    img = Image.merge("RGBA", (b, g, r, a))
                elif img.mode == "L":
                    img = img.convert("RGBA")
                    
                data = img.tobytes("raw", "RGBA")
                qim = QImage(data, img.size[0], img.size[1], QImage.Format_ARGB32)
                item['qpixmap'] = QPixmap.fromImage(qim)
                
                # 2. Compute hash
                hash_md5 = hashlib.md5()
                with open(item['path'], "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                item['hash'] = hash_md5.hexdigest()

                # 3. Check duplicate
                dup = self.image_mgr.check_duplicate_by_hash(item['hash'])
                if dup:
                    item['status'] = 'duplicate'
                    item['duplicate_name'] = dup
                else:
                    item['status'] = 'new'
                    
                self.item_processed.emit(item)
            except Exception as e:
                print(f"Error processing {item['path']}: {e}")
                item['status'] = 'error'
                self.item_processed.emit(item)

class UploadWorker(QThread):
    finished_upload = pyqtSignal()
    
    def __init__(self, items, image_mgr):
        super().__init__()
        self.items = items
        self.image_mgr = image_mgr
        
    def run(self):
        from managers.collection_manager import CollectionManager
        from database import get_connection
        col_mgr = CollectionManager()
        
        col_cache = {}
        
        def get_or_create_collection(path_str):
            if path_str in col_cache: return col_cache[path_str]
            parts = path_str.split("/")
            parent_id = None
            current_path = ""
            for part in parts:
                if current_path: current_path += "/" + part
                else: current_path = part
                
                if current_path in col_cache:
                    parent_id = col_cache[current_path]
                    continue
                    
                cols = col_mgr.get_collections()
                match = next((c for c in cols if c['name'] == part and c.get('parent_id') == parent_id), None)
                if not match:
                    col_mgr.create_collection(part, parent_id=parent_id)
                    cols = col_mgr.get_collections()
                    match = next((c for c in cols if c['name'] == part and c.get('parent_id') == parent_id), None)
                
                if match:
                    parent_id = match['id']
                    col_cache[current_path] = parent_id
            return parent_id
        
        for item in self.items:
            self.image_mgr.import_image(str(item['path']))
            
            if item['collection']:
                col_id = get_or_create_collection(item['collection'])
                if col_id:
                    try:
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute("SELECT id FROM images WHERE file_hash = ? ORDER BY id DESC LIMIT 1", (item['hash'],))
                        row = c.fetchone()
                        conn.close()
                        if row:
                            col_mgr.add_images_to_collection([row['id']], col_id)
                    except: pass
                    
        self.finished_upload.emit()

class NativeDropZone(QWidget):
    files_dropped = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QWidget { background-color: #1E293B; border: 2px dashed #334155; border-radius: 12px; }
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        icon = QLabel("☁️")
        icon.setStyleSheet("font-size: 64px; border: none; background: transparent;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        title = QLabel("Drag & drop images here")
        title.setStyleSheet("font-size: 20px; font-weight: bold; border: none; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        sub = QLabel("Supports JPG, PNG, WEBP, GIF")
        sub.setStyleSheet("color: #94A3B8; border: none; background: transparent;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls]
        self.files_dropped.emit(paths)

class UploadView(QWidget):
    def __init__(self, master, cancel_callback, on_upload_success_callback):
        super().__init__(master)
        
        self.cancel_callback = cancel_callback
        self.on_upload_success_callback = on_upload_success_callback
        self.image_mgr = ImageManager()
        
        self.pending_files = [] 
        
        self._setup_ui()
        
    def reset(self):
        for item in self.pending_files:
            if item.get('frame'): item['frame'].deleteLater()
            if item.get('ui_row'): item['ui_row'].deleteLater()
        self.pending_files.clear()
        
        self.upload_anyway_chk.setChecked(False)
        self.upload_btn.setEnabled(False)
        self.upload_btn.setText("Upload 0 images")
        self.cancel_btn.setEnabled(True)
        self._update_summary()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Split layout
        split_layout = QHBoxLayout()
        layout.addLayout(split_layout, stretch=1)
        
        # Left Side
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        split_layout.addWidget(left_widget)
        
        self.drop_zone = NativeDropZone()
        self.drop_zone.files_dropped.connect(self._add_files)
        left_layout.addWidget(self.drop_zone, stretch=1)
        
        btn_layout = QHBoxLayout()
        browse_btn = QPushButton("Browse Files")
        browse_btn.clicked.connect(self._browse_files)
        btn_layout.addWidget(browse_btn)
        
        folder_btn = QPushButton("Import Folder (Recursive)")
        folder_btn.clicked.connect(self._browse_folder)
        btn_layout.addWidget(folder_btn)
        
        left_layout.addLayout(btn_layout)
        
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setFixedHeight(120)
        self.thumb_content = QWidget()
        self.thumb_layout = QHBoxLayout(self.thumb_content)
        self.thumb_scroll.setWidget(self.thumb_content)
        self.thumb_scroll.setWidgetResizable(True)
        left_layout.addWidget(self.thumb_scroll)
        
        # Right Side
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        split_layout.addWidget(right_widget)
        
        self.summary_lbl = QLabel("0 new, 0 duplicate found")
        self.summary_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(self.summary_lbl)
        
        self.status_scroll = QScrollArea()
        self.status_content = QWidget()
        self.status_layout = QVBoxLayout(self.status_content)
        self.status_layout.setAlignment(Qt.AlignTop)
        self.status_scroll.setWidget(self.status_content)
        self.status_scroll.setWidgetResizable(True)
        right_layout.addWidget(self.status_scroll)
        
        self.upload_anyway_chk = QCheckBox("Upload duplicates anyway")
        self.upload_anyway_chk.stateChanged.connect(self._update_summary)
        right_layout.addWidget(self.upload_anyway_chk)
        
        # Action Bar
        action_bar = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_callback)
        action_bar.addWidget(self.cancel_btn)
        
        self.upload_btn = QPushButton("Upload 0 images")
        self.upload_btn.setStyleSheet("background-color: #7C3AED;")
        self.upload_btn.setEnabled(False)
        self.upload_btn.clicked.connect(self._do_upload)
        action_bar.addWidget(self.upload_btn)
        
        layout.addLayout(action_bar)
        
    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images", "", "Image Files (*.png *.jpg *.jpeg *.webp *.gif)")
        if files:
            self._add_files(files)
            
    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder: return
        
        base_path = Path(folder)
        base_folder_name = base_path.name
        
        files_to_import = []
        for root, dirs, files in os.walk(folder):
            for file in files:
                filepath = Path(root) / file
                if filepath.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']:
                    rel_path = filepath.relative_to(base_path.parent)
                    col_name = str(rel_path.parent).replace('\\', '/')
                    if col_name == '.': col_name = base_folder_name
                    files_to_import.append((str(filepath), col_name))
                    
        if files_to_import:
            self._add_files(files_to_import, is_folder_import=True)
            
    def _add_files(self, filepaths, is_folder_import=False):
        new_files = []
        for item_data in filepaths:
            fp = item_data[0] if is_folder_import else item_data
            col_name = item_data[1] if is_folder_import else None
            
            path = Path(fp)
            if not path.is_file(): continue
            if path.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']: continue
            
            if any(f['path'] == path for f in self.pending_files): continue
            
            item = {
                'path': path,
                'status': 'pending',
                'hash': None,
                'duplicate_name': None,
                'qpixmap': None,
                'frame': None,
                'ui_row': None,
                'collection': col_name
            }
            new_files.append(item)
            self.pending_files.append(item)
            
        for item in new_files:
            self._render_thumbnail_placeholder(item)
            self._render_status_row(item)
            
        if new_files:
            self.worker = ProcessWorker(new_files, self.image_mgr)
            self.worker.item_processed.connect(self._update_item_ui)
            self.worker.start()
            
    def _render_thumbnail_placeholder(self, item):
        frame = QWidget()
        layout = QVBoxLayout(frame)
        
        lbl = QLabel("⏳")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedSize(80, 80)
        lbl.setStyleSheet("background-color: #334155; border-radius: 6px;")
        layout.addWidget(lbl)
        
        btn = QPushButton("✕")
        btn.setStyleSheet("background-color: red; color: white;")
        btn.clicked.connect(lambda _, i=item: self._remove_file(i))
        layout.addWidget(btn)
        
        item['frame'] = frame
        item['thumb_lbl'] = lbl
        self.thumb_layout.addWidget(frame)
        
    def _render_status_row(self, item):
        lbl = QLabel(f"⏳ Checking {item['path'].name}...")
        lbl.setStyleSheet("color: #94A3B8;")
        item['ui_row'] = lbl
        self.status_layout.addWidget(lbl)
        
    def _update_item_ui(self, item):
        if item['status'] == 'error':
            item['thumb_lbl'].setText("❌")
            item['ui_row'].setText(f"❌ Error loading {item['path'].name}")
            item['ui_row'].setStyleSheet("color: #EF4444;")
        else:
            if item.get('qpixmap'):
                item['thumb_lbl'].setPixmap(item['qpixmap'])
                item['thumb_lbl'].setText("")
            
            if item['status'] == 'duplicate':
                item['ui_row'].setText(f"⚠️ Duplicate {item['path'].name} (Matches: {item['duplicate_name']})")
                item['ui_row'].setStyleSheet("color: #F59E0B;")
            elif item['status'] == 'new':
                item['ui_row'].setText(f"✅ Ready {item['path'].name}")
                item['ui_row'].setStyleSheet("color: #10B981;")
                
        self._update_summary()
        
    def _remove_file(self, item):
        if item in self.pending_files:
            self.pending_files.remove(item)
        if item.get('frame'): item['frame'].deleteLater()
        if item.get('ui_row'): item['ui_row'].deleteLater()
        self._update_summary()
        
    def _update_summary(self):
        new_ct = sum(1 for f in self.pending_files if f['status'] == 'new')
        dup_ct = sum(1 for f in self.pending_files if f['status'] == 'duplicate')
        pending_ct = sum(1 for f in self.pending_files if f['status'] == 'pending')
        
        self.summary_lbl.setText(f"{new_ct} new, {dup_ct} duplicate found")
        
        if pending_ct > 0:
            self.upload_btn.setEnabled(False)
            self.upload_btn.setText("Processing...")
            return
            
        anyway = self.upload_anyway_chk.isChecked()
        valid = new_ct + (dup_ct if anyway else 0)
        
        if valid > 0:
            self.upload_btn.setEnabled(True)
            self.upload_btn.setText(f"Upload {valid} images")
        else:
            self.upload_btn.setEnabled(False)
            self.upload_btn.setText("Upload 0 images")
            
    def _do_upload(self):
        valid_items = []
        anyway = self.upload_anyway_chk.isChecked()
        for item in self.pending_files:
            if item['status'] == 'new' or (item['status'] == 'duplicate' and anyway):
                valid_items.append(item)
                
        if not valid_items: return
        
        self.upload_btn.setEnabled(False)
        self.upload_btn.setText("Uploading...")
        self.cancel_btn.setEnabled(False)
        
        self.up_worker = UploadWorker(valid_items, self.image_mgr)
        self.up_worker.finished_upload.connect(self.on_upload_success_callback)
        self.up_worker.start()

