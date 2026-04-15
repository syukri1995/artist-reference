import webbrowser
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
from PyQt5.QtCore import Qt

class UpdateDialog(QDialog):
    def __init__(self, parent, current_version, new_version, release_notes, download_url):
        super().__init__(parent)
        
        self.download_url = download_url
        self.setWindowTitle("Software Update")
        self.setFixedSize(450, 350)
        
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("A new version is available!")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Version info
        version_lbl = QLabel(f"Current Version: {current_version}   |   Latest Version: {new_version}")
        version_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_lbl)
        
        # Release Notes Text Box
        self.notes_box = QTextEdit()
        self.notes_box.setReadOnly(True)
        self.notes_box.setPlainText(release_notes)
        layout.addWidget(self.notes_box)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.skip_btn = QPushButton("Remind Me Later")
        self.skip_btn.setStyleSheet("background-color: #334155;")
        self.skip_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.skip_btn)
        
        self.download_btn = QPushButton("Download Update")
        self.download_btn.setStyleSheet("background-color: #7C3AED;")
        self.download_btn.clicked.connect(self.download_update)
        btn_layout.addWidget(self.download_btn)
        
        layout.addLayout(btn_layout)
        
    def download_update(self):
        if self.download_url.startswith(("http://", "https://")):
            webbrowser.open(self.download_url)
        self.accept()
