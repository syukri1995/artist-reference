"""Design tokens and global Qt stylesheet."""


TOKENS = {
    "bg_base": "#0B0F1A",       # Deeper, richer navy
    "bg_surface": "#161D2F",    # Surface color
    "bg_elevated": "#252F44",   # Elevated panels
    "bg_hover": "#2D394E",      # Hover state
    "text_primary": "#F1F5F9",  # Off-white for high readability
    "text_secondary": "#94A3B8", # Slate for metadata
    "text_muted": "#64748B",     # Disabled/Muted text
    "accent": "#8B5CF6",        # Vibrant Violet
    "accent_hover": "#A78BFA",  # Lighter hover violet
    "accent_active": "#7C3AED", # Deeper active violet
    "danger": "#EF4444",        # Modern red
    "success": "#10B981",       # Modern green
    "warning": "#F59E0B",       # Modern amber
    "radius": "8px",            # Slightly larger radius for modern look
    "font_family": "'Plus Jakarta Sans', 'Inter', 'Segoe UI', system-ui, sans-serif",
    "font_size": "13px",
}


def build_stylesheet() -> str:
    t = TOKENS
    return f"""
            QMainWindow {{ background-color: {t['bg_base']}; }}
            QWidget {{ 
                color: {t['text_primary']}; 
                font-family: {t['font_family']}; 
                font-size: {t['font_size']}; 
                background-color: transparent; 
            }}
            
            QStatusBar {{ 
                background-color: {t['bg_surface']}; 
                color: {t['text_secondary']}; 
                border-top: 1px solid {t['bg_elevated']}; 
                padding: 4px;
            }}

            QScrollArea {{ border: none; background-color: transparent; }}
            QScrollArea > QWidget > QWidget {{ background-color: transparent; }}

            /* Buttons */
            QPushButton {{
                background-color: {t['bg_elevated']};
                color: {t['text_primary']};
                border: 1px solid transparent;
                border-radius: {t['radius']};
                padding: 7px 16px;
                font-weight: 600;
                outline: none;
            }}
            QPushButton:hover {{ 
                background-color: {t['bg_hover']}; 
                border-color: {t['accent_hover']}; 
            }}
            QPushButton:pressed {{ 
                background-color: {t['accent_active']}; 
                border-color: {t['accent_active']}; 
                color: #FFFFFF;
            }}
            QPushButton:disabled {{ 
                background-color: {t['bg_surface']}; 
                color: {t['text_muted']}; 
                border-color: transparent; 
            }}
            
            /* Accent Buttons */
            QPushButton#accentButton {{
                background-color: {t['accent']};
                color: #FFFFFF;
            }}
            QPushButton#accentButton:hover {{
                background-color: {t['accent_hover']};
            }}

            /* Toolbars */
            QFrame#toolbar, QWidget#toolbar {{
                background-color: {t['bg_surface']};
                border-bottom: 1px solid {t['bg_elevated']};
            }}

            /* Menus */
            QMenu {{
                background-color: {t['bg_surface']};
                color: {t['text_primary']};
                border: 1px solid {t['bg_elevated']};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{ 
                padding: 8px 32px 8px 12px; 
                border-radius: 4px; 
                margin: 2px;
            }}
            QMenu::item:selected {{ 
                background-color: {t['accent']}; 
                color: #FFFFFF; 
            }}
            QMenu::separator {{ 
                height: 1px; 
                background: {t['bg_elevated']}; 
                margin: 6px 8px; 
            }}

            /* Inputs */
            QLineEdit {{ 
                background-color: {t['bg_base']}; 
                color: {t['text_primary']}; 
                border-radius: {t['radius']}; 
                padding: 8px 12px; 
                border: 1px solid {t['bg_elevated']}; 
            }}
            QLineEdit:focus {{ 
                border: 1px solid {t['accent']}; 
                background-color: {t['bg_surface']};
            }}

            /* ComboBox */
            QComboBox {{
                background-color: {t['bg_elevated']};
                border: 1px solid {t['bg_elevated']};
                border-radius: {t['radius']};
                padding: 6px 12px;
                min-width: 100px;
            }}
            QComboBox:hover {{ border-color: {t['accent_hover']}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox::down-arrow {{ image: none; border: none; }} /* Custom arrow needed? */
            
            QComboBox QAbstractItemView {{
                background-color: {t['bg_surface']};
                border: 1px solid {t['bg_elevated']};
                selection-background-color: {t['accent']};
                outline: none;
            }}

            QLabel {{ color: {t['text_secondary']}; }}
            QLabel#title {{ color: {t['text_primary']}; font-size: 18px; font-weight: bold; }}

            /* ListWidgets (Sidebar) */
            QListWidget {{
                background-color: {t['bg_base']};
                border: none;
                outline: none;
            }}
            QListWidget::item {{ 
                padding: 10px 12px; 
                border-radius: 6px; 
                margin: 2px 8px;
                color: {t['text_secondary']};
            }}
            QListWidget::item:hover {{ 
                background-color: {t['bg_surface']}; 
                color: {t['text_primary']};
            }}
            QListWidget::item:selected {{ 
                background-color: {t['accent']}; 
                color: #FFFFFF; 
            }}

            /* Checkboxes */
            QCheckBox {{ spacing: 8px; font-weight: 500; }}
            QCheckBox::indicator {{ 
                width: 18px; 
                height: 18px; 
                border-radius: 4px; 
                border: 2px solid {t['bg_elevated']}; 
                background-color: {t['bg_base']}; 
            }}
            QCheckBox::indicator:hover {{ border-color: {t['accent_hover']}; }}
            QCheckBox::indicator:checked {{ 
                background-color: {t['accent']}; 
                border-color: {t['accent']}; 
            }}

            /* Sliders */
            QSlider::groove:horizontal {{ 
                height: 6px; 
                background: {t['bg_elevated']}; 
                border-radius: 3px; 
            }}
            QSlider::handle:horizontal {{ 
                background: #FFFFFF; 
                border: 2px solid {t['accent']};
                width: 16px; 
                height: 16px; 
                margin: -6px 0; 
                border-radius: 9px; 
            }}
            QSlider::sub-page:horizontal {{ 
                background: {t['accent']}; 
                border-radius: 3px; 
            }}

            /* ScrollBars */
            QScrollBar:vertical {{
                background: {t['bg_base']};
                width: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #5B437B; /* Muted purple */
                min-height: 24px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['accent_hover']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}

            QScrollBar:horizontal {{
                background: {t['bg_base']};
                height: 12px;
                margin: 0px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background: #5B437B; /* Muted purple */
                min-width: 24px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {t['accent_hover']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}

            /* Tabs */
            QTabWidget::pane {{ border: 1px solid {t['bg_elevated']}; top: -1px; border-radius: 6px; }}
            QTabBar::tab {{
                background: {t['bg_surface']};
                color: {t['text_secondary']};
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: {t['bg_elevated']};
                color: {t['text_primary']};
                border-bottom: 2px solid {t['accent']};
            }}
            QTabBar::tab:hover {{ color: {t['text_primary']}; }}

            QToolTip {{
                background-color: #1E293B;
                color: #F1F5F9;
                border: 1px solid {t['accent']};
                padding: 6px 10px;
                border-radius: 4px;
            }}
        """

