"""Design tokens and global Qt stylesheet."""

from pathlib import Path

TOKENS = {
    "bg_base": "#0F172A",
    "bg_surface": "#1E293B",
    "bg_elevated": "#334155",
    "text_primary": "#E2E8F0",
    "text_secondary": "#94A3B8",
    "accent": "#7C3AED",
    "accent_hover": "#6D28D9",
    "danger": "#DC2626",
    "success": "#10B981",
    "warning": "#F59E0B",
    "radius": "6px",
    "font_family": "'Segoe UI'",
    "font_size": "13px",
}


def build_stylesheet() -> str:
    t = TOKENS
    return f"""
            QMainWindow {{ background-color: {t['bg_base']}; }}
            QWidget {{ color: {t['text_primary']}; font-family: {t['font_family']}; font-size: {t['font_size']}; background-color: transparent; }}
            QStatusBar {{ background-color: {t['bg_surface']}; color: {t['text_secondary']}; border-top: 1px solid {t['bg_elevated']}; }}
            QScrollArea {{ border: none; }}
            QScrollArea > QWidget > QWidget {{ background-color: transparent; }}
            QProgressBar {{
                background-color: {t['bg_elevated']};
                border: none;
                border-radius: 4px;
                text-align: center;
                color: {t['text_primary']};
            }}
            QProgressBar::chunk {{ background-color: {t['accent']}; border-radius: 4px; }}

            QPushButton {{
                background-color: {t['bg_surface']};
                color: {t['text_primary']};
                border: 1px solid {t['bg_elevated']};
                border-radius: {t['radius']};
                padding: 5px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['bg_elevated']}; border-color: {t['accent']}; }}
            QPushButton:pressed {{ background-color: {t['accent']}; border-color: {t['accent']}; }}
            QPushButton:disabled {{ color: #64748B; border-color: {t['bg_surface']}; }}
            QPushButton[activeFilter="true"] {{
                background-color: {t['accent']};
                border-color: {t['accent_hover']};
                color: #FFFFFF;
            }}

            QMenu {{
                background-color: {t['bg_surface']};
                color: {t['text_primary']};
                border: 1px solid {t['bg_elevated']};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {t['accent']}; color: #FFFFFF; }}
            QMenu::separator {{ height: 1px; background: {t['bg_elevated']}; margin: 4px 8px; }}

            QLineEdit {{ background-color: {t['bg_surface']}; color: {t['text_primary']}; border-radius: {t['radius']}; padding: 6px; border: 1px solid {t['bg_elevated']}; }}
            QLineEdit:focus {{ border: 1px solid {t['accent']}; }}

            QLabel {{ color: {t['text_secondary']}; background-color: transparent; }}

            QListWidget {{
                background-color: {t['bg_base']};
                color: {t['text_primary']};
                border: 1px solid {t['bg_surface']};
                border-radius: 4px;
            }}
            QListWidget::item {{ padding: 4px 8px; border-radius: 3px; }}
            QListWidget::item:selected {{ background-color: {t['accent']}; color: #FFFFFF; }}
            QListWidget::item:hover {{ background-color: {t['bg_surface']}; }}

            QCheckBox {{ color: {t['text_primary']}; spacing: 6px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 3px; border: 1px solid #475569; background-color: {t['bg_surface']}; }}
            QCheckBox::indicator:checked {{ background-color: {t['accent']}; border-color: {t['accent']}; }}

            QSlider::groove:horizontal {{ height: 4px; background: {t['bg_elevated']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {t['accent']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
            QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}

            QScrollBar:vertical {{ background: {t['bg_base']}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {t['bg_elevated']}; border-radius: 4px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {t['accent']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar:horizontal {{ background: {t['bg_base']}; height: 8px; border-radius: 4px; }}
            QScrollBar::handle:horizontal {{ background: {t['bg_elevated']}; border-radius: 4px; min-width: 30px; }}
            QScrollBar::handle:horizontal:hover {{ background: {t['accent']}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

            QToolTip {{
                background-color: {t['bg_surface']};
                color: {t['text_primary']};
                border: 1px solid {t['accent']};
                padding: 4px 8px;
            }}
        """
