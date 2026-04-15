import webbrowser
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, 
                             QLabel, QHBoxLayout, QComboBox, QSlider, QFrame)
from PyQt5.QtCore import Qt
try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "Unknown"

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ Settings & About")
        self.setFixedSize(450, 400)
        
        layout = QVBoxLayout(self)
        
        self.tabview = QTabWidget()
        layout.addWidget(self.tabview)
        
        self.tab_settings = QWidget()
        self.tab_about = QWidget()
        
        self.tabview.addTab(self.tab_settings, "Settings")
        self.tabview.addTab(self.tab_about, "About")
        
        self._build_settings_tab()
        self._build_about_tab()

    def _build_settings_tab(self):
        layout = QVBoxLayout(self.tab_settings)
        layout.setAlignment(Qt.AlignTop)
        
        # Appearance Mode
        app_layout = QHBoxLayout()
        app_label = QLabel("Appearance Mode:")
        app_label.setStyleSheet("font-weight: bold;")
        app_layout.addWidget(app_label)
        
        mode_menu = QComboBox()
        mode_menu.addItems(["Dark"]) # Hardcoded Dark for now since we set raw CSS
        app_layout.addWidget(mode_menu)
        layout.addLayout(app_layout)
        
        # Opacity Slider
        op_layout = QHBoxLayout()
        self.opacity_label = QLabel("Window Opacity: 100%")
        self.opacity_label.setStyleSheet("font-weight: bold;")
        op_layout.addWidget(self.opacity_label)
        
        opacity_slider = QSlider(Qt.Horizontal)
        opacity_slider.setRange(20, 100)
        opacity_slider.setValue(100)
        
        def update_opacity(val):
            self.opacity_label.setText(f"Window Opacity: {val}%")
            if self.parent():
                self.parent().setWindowOpacity(val / 100.0)
            self.setWindowOpacity(val / 100.0)
            
        opacity_slider.valueChanged.connect(update_opacity)
        op_layout.addWidget(opacity_slider)
        layout.addLayout(op_layout)

    def _build_about_tab(self):
        layout = QVBoxLayout(self.tab_about)
        layout.setAlignment(Qt.AlignTop)
        
        def add_info(title, value, is_link=False):
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-weight: bold;")
            layout.addWidget(title_lbl)
            
            val_lbl = QLabel(value)
            if is_link:
                val_lbl.setStyleSheet("color: #3B82F6; text-decoration: underline;")
                val_lbl.setCursor(Qt.PointingHandCursor)
                val_lbl.mousePressEvent = lambda e: webbrowser.open("https://github.com/syukri1995/artist-reference/issues")
            layout.addWidget(val_lbl)
            
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setStyleSheet("background-color: #334155;")
            layout.addWidget(line)
            
        add_info("Software Version:", APP_VERSION)
        add_info("License Information:", "MIT License (Open Source)\nFree for personal and commercial use.")
        add_info("System Requirements:", "OS: Windows 10/11, macOS, Linux\nRAM: Minimum 4GB\nDisplay: 1280x720 Minimum")
        add_info("Contact Support:", "Report an Issue / Request Feature", is_link=True)
