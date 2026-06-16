"""
image_viewer.py — Full-screen lightbox viewer with navigation and quick actions.
"""
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize
from PyQt5.QtGui import QPainter, QIcon
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QShortcut, QWidget, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsOpacityEffect
)
from PIL import Image

from managers.image_manager import ImageManager
from utils_image import pil_to_qpixmap
from ui.branding import icon_path

class ImageViewer(QDialog):
    """
    Immersive lightbox overlay for viewing images in high resolution.
    Supports navigation through a list of paths.
    """
    
    # Signals for external actions
    add_to_workspace = pyqtSignal(str) # Emits the file path
    
    def __init__(self, parent: QWidget, paths: list[str], index: int, image_mgr: ImageManager) -> None:
        super().__init__(parent)
        self.paths = paths
        self.current_index = index
        self.image_mgr = image_mgr
        
        self.setWindowTitle("Image Viewer")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Ensure we cover the parent window
        if parent:
            self.setGeometry(parent.geometry())
        
        self._setup_ui()
        self._update_display()
        
        # Opening animation
        self._opacity_effect = QGraphicsOpacityEffect(self.bg_frame)
        self.bg_frame.setGraphicsEffect(self._opacity_effect)
        
        self.anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()

    def _setup_ui(self) -> None:
        # Main layout with dark semi-transparent background
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("viewerBackground")
        self.bg_frame.setStyleSheet("""
            QFrame#viewerBackground {
                background-color: rgba(11, 15, 26, 240);
            }
        """)
        self.root_layout.addWidget(self.bg_frame)
        
        # Inner layout for the frame
        self.main_layout = QVBoxLayout(self.bg_frame)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Top Bar
        self.top_bar = QFrame()
        self.top_bar.setFixedHeight(60)
        self.top_bar.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #F1F5F9; font-size: 14px; font-weight: 500;")
        top_layout.addWidget(self.info_label)
        
        top_layout.addStretch()
        
        # Actions in top bar
        self.fav_btn = QPushButton()
        self.fav_btn.setFixedSize(40, 40)
        self.fav_btn.setIconSize(QSize(24, 24))
        self.fav_btn.clicked.connect(self._toggle_favorite)
        top_layout.addWidget(self.fav_btn)
        
        self.ws_btn = QPushButton()
        self.ws_btn.setIcon(QIcon(icon_path("plus")))
        self.ws_btn.setIconSize(QSize(18, 18))
        self.ws_btn.setText(" WS")
        self.ws_btn.setToolTip("Add to workspace")
        self.ws_btn.setFixedSize(80, 40)
        self.ws_btn.clicked.connect(self._send_to_workspace)
        top_layout.addWidget(self.ws_btn)
        
        self.close_btn = QPushButton()
        self.close_btn.setIcon(QIcon(icon_path("x")))
        self.close_btn.setIconSize(QSize(24, 24))
        self.close_btn.setFixedSize(40, 40)
        self.close_btn.setStyleSheet("background: transparent; border: none; color: #94A3B8;")
        self.close_btn.clicked.connect(self.accept)
        top_layout.addWidget(self.close_btn)
        
        self.main_layout.addWidget(self.top_bar)
        
        # Image Area
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Prev Button
        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(QIcon(icon_path("chevron-left")))
        self.prev_btn.setIconSize(QSize(48, 48))
        self.prev_btn.setFixedSize(80, 200)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 10);
            }
        """)
        self.prev_btn.clicked.connect(self._prev_image)
        content_layout.addWidget(self.prev_btn)
        
        # Image Display
        self.image_container = QWidget()
        img_layout = QVBoxLayout(self.image_container)
        img_layout.setContentsMargins(40, 20, 40, 40)
        
        self.view = QGraphicsView()
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.scene = QGraphicsScene()

        self.view.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        img_layout.addWidget(self.view)
        content_layout.addWidget(self.image_container, stretch=1)
        
        # Next Button
        self.next_btn = QPushButton()
        self.next_btn.setIcon(QIcon(icon_path("chevron-right")))
        self.next_btn.setIconSize(QSize(48, 48))
        self.next_btn.setFixedSize(80, 200)
        self.next_btn.setStyleSheet(self.prev_btn.styleSheet())
        self.next_btn.clicked.connect(self._next_image)
        content_layout.addWidget(self.next_btn)
        
        self.main_layout.addLayout(content_layout, stretch=1)
        
        # Shortcuts
        QShortcut(Qt.Key_Left, self, self._prev_image)
        QShortcut(Qt.Key_Right, self, self._next_image)
        QShortcut(Qt.Key_Escape, self, self.accept)
        QShortcut(Qt.Key_F, self, self._toggle_favorite)
        QShortcut(Qt.Key_W, self, self._send_to_workspace)

    def _update_display(self) -> None:
        if not self.paths:
            return
            
        path = self.paths[self.current_index]
        self.info_label.setText(f"{Path(path).name}  ({self.current_index + 1} / {len(self.paths)})")
        
        # Check favorite status
        is_fav = self.image_mgr.is_favorite(path)
        icon_name = "star-filled" if is_fav else "star"
        self.fav_btn.setIcon(QIcon(icon_path(icon_name)))
        self.fav_btn.setStyleSheet("background: transparent; border: none;")
        
        # Load and scale image using PIL to avoid noisy Qt/libpng warnings
        try:
            with Image.open(path) as pil_img:
                # Handle orientation (EXIF)
                from PIL import ImageOps
                pil_img = ImageOps.exif_transpose(pil_img)
                pixmap = pil_to_qpixmap(pil_img)
                
            if not pixmap.isNull():
                self.pixmap_item.setPixmap(pixmap)
                self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
                self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            else:
                self.info_label.setText(f"Failed to load (null pixmap): {Path(path).name}")
        except Exception as e:
            self.info_label.setText(f"Failed to load: {Path(path).name} ({str(e)})")
            
        # Update button states
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.paths) - 1)

    def _prev_image(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self._update_display()
            
    def _next_image(self) -> None:
        if self.current_index < len(self.paths) - 1:
            self.current_index += 1
            self._update_display()
            
    def _toggle_favorite(self) -> None:
        path = self.paths[self.current_index]
        self.image_mgr.toggle_favorites({path})
        self._update_display()
        
    def _send_to_workspace(self) -> None:
        path = self.paths[self.current_index]
        self.add_to_workspace.emit(path)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.pixmap_item.pixmap() and not self.pixmap_item.pixmap().isNull():
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def mousePressEvent(self, event) -> None:
        # Close if clicked outside the image area (on the background frame but not buttons)
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.pos())
            if child == self.bg_frame or child == self.image_container:
                self.accept()
        super().mousePressEvent(event)
