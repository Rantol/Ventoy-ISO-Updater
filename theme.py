"""Design system: color tokens and Qt stylesheets for a sidebar layout.

Two palettes (``dark`` / ``light``) share the same token names so widgets can
theme themselves by asking :func:`palette` for a color. The big QSS string
styles the common Qt controls; per-widget accents are applied in code.
"""

from __future__ import annotations

# 8px spacing scale is used throughout the views: 4, 8, 12, 16, 24, 32.

DARK = {
    "bg": "#0b1120",
    "surface": "#0f172a",
    "surface_2": "#1e293b",
    "surface_3": "#273449",
    "sidebar": "#0d1526",
    "border": "#1e293b",
    "border_strong": "#334155",
    "text": "#e2e8f0",
    "text_dim": "#94a3b8",
    "text_faint": "#64748b",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_soft": "#1e3a5f",
    "on_accent": "#ffffff",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "info": "#38bdf8",
}

LIGHT = {
    "bg": "#f1f5f9",
    "surface": "#f8fafc",
    "surface_2": "#ffffff",
    "surface_3": "#eef2f7",
    "sidebar": "#ffffff",
    "border": "#e2e8f0",
    "border_strong": "#cbd5e1",
    "text": "#0f172a",
    "text_dim": "#475569",
    "text_faint": "#94a3b8",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_soft": "#dbeafe",
    "on_accent": "#ffffff",
    "success": "#16a34a",
    "warning": "#d97706",
    "danger": "#dc2626",
    "info": "#0284c7",
}


def palette(theme: str) -> dict:
    return LIGHT if theme == "light" else DARK


def stylesheet(theme: str) -> str:
    c = palette(theme)
    return f"""
* {{ outline: none; }}
QWidget {{
    background: {c['bg']}; color: {c['text']};
    font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px;
}}
QMainWindow {{ background: {c['bg']}; }}
QLabel {{ background: transparent; }}
QCheckBox {{ background: transparent; }}
QRadioButton {{ background: transparent; }}

/* ―― Sidebar ―――――――――――――――――――――――――――――――――――――― */
QWidget#Sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
QLabel#Brand {{ font-size: 16px; font-weight: 700; color: {c['text']}; }}
QLabel#BrandDot {{ color: {c['accent']}; font-size: 16px; font-weight: 800; }}
QLabel#NavSection {{
    color: {c['text_faint']}; font-size: 10px; font-weight: 700;
    letter-spacing: 1px;
}}

QPushButton#NavItem {{
    background: transparent; color: {c['text_dim']}; border: none;
    border-radius: 8px; padding: 10px 12px; text-align: left;
    font-size: 13px; font-weight: 500;
}}
QPushButton#NavItem:hover {{ background: {c['surface_2']}; color: {c['text']}; }}
QPushButton#NavItem:checked {{
    background: {c['accent_soft']}; color: {c['text']}; font-weight: 600;
}}

/* ―― Cards / surfaces ―――――――――――――――――――――――――――――― */
QFrame#Card {{
    background: {c['surface_2']}; border: 1px solid {c['border']};
    border-radius: 12px;
}}
QFrame#Card:hover {{ border: 1px solid {c['border_strong']}; }}
QFrame#Hairline {{ background: {c['border']}; max-height: 1px; border: none; }}

QLabel#H1 {{ font-size: 22px; font-weight: 700; }}
QLabel#Subtle {{ color: {c['text_faint']}; font-size: 12px; }}
QLabel#CardTitle {{ font-size: 15px; font-weight: 600; }}

/* ―― Buttons ―――――――――――――――――――――――――――――――――――――― */
QPushButton {{
    background: {c['surface_3']}; color: {c['text']}; border: none;
    border-radius: 8px; padding: 8px 16px; font-weight: 500;
}}
QPushButton:hover {{ background: {c['border_strong']}; }}
QPushButton:disabled {{ background: {c['surface_2']}; color: {c['text_faint']}; }}

QPushButton#Primary {{ background: {c['accent']}; color: {c['on_accent']}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#Primary:disabled {{ background: {c['surface_3']}; color: {c['text_faint']}; }}

QPushButton#Ghost {{ background: transparent; color: {c['text_dim']};
    border: 1px solid {c['border_strong']}; }}
QPushButton#Ghost:hover {{ background: {c['surface_2']}; color: {c['text']}; }}
QPushButton#LinkButton {{
    background: transparent; color: {c['accent']}; border: none;
    padding: 2px 0; text-align: left; text-decoration: underline;
}}
QPushButton#LinkButton:hover {{ color: {c['accent_hover']}; }}

QPushButton#Danger {{ background: transparent; color: {c['danger']};
    border: 1px solid {c['danger']}; }}
QPushButton#Danger:hover {{ background: {c['danger']}; color: #ffffff; }}

/* Compact table actions: never inherit the dark QWidget cell background. */
QWidget#CellHost {{ background: transparent; }}
QPushButton#TableAction {{
    background: {c['accent_soft']}; color: {c['accent']};
    border: 1px solid {c['accent']}; border-radius: 7px;
    padding: 4px 6px; font-size: 11px; font-weight: 600;
}}
QPushButton#TableAction:hover {{ background: {c['accent']}; color: {c['on_accent']}; }}
QPushButton#TableAction:disabled {{ background: {c['surface_3']}; color: {c['text_faint']}; border-color: {c['border_strong']}; }}
QPushButton#TableDelete {{
    background: transparent; color: {c['danger']};
    border: 1px solid {c['danger']}; border-radius: 7px;
    padding: 4px 6px; font-size: 11px; font-weight: 600;
}}
QPushButton#TableDelete:hover {{ background: {c['danger']}; color: #ffffff; }}

/* ―― Inputs ―――――――――――――――――――――――――――――――――――――――― */
QLineEdit, QComboBox {{
    background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; border-radius: 8px;
    padding: 8px 12px; font-size: 13px; selection-background-color: {c['accent']};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{
    image: none; border-left: 5px solid transparent; border-right: 5px solid transparent;
    border-top: 6px solid {c['text_dim']}; margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {c['surface_2']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; border-radius: 8px;
    selection-background-color: {c['accent']}; selection-color: {c['on_accent']};
    padding: 4px; outline: none;
}}

/* ―― Table ―――――――――――――――――――――――――――――――――――――――― */
QTableWidget {{
    background: {c['surface_2']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 12px;
    gridline-color: transparent; selection-background-color: {c['accent_soft']};
    selection-color: {c['text']};
}}
QTableWidget::item {{
    padding: 12px 8px;
    border-bottom: 1px solid {c['border']};
    border-right: 1px solid {c['border']};
}}
QTableWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
QHeaderView::section {{
    background: {c['surface']}; color: {c['text_faint']};
    border: none; border-right: 1px solid {c['border_strong']};
    border-bottom: 1px solid {c['border_strong']}; padding: 10px 8px;
    font-weight: 600; font-size: 11px; text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QTableCornerButton::section {{ background: transparent; border: none; }}

/* ―― Progress ―――――――――――――――――――――――――――――――――――――― */
QProgressBar {{
    background: {c['surface_3']}; border: none; height: 8px;
    border-radius: 4px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {c['accent']}, stop:1 {c['info']});
    border-radius: 4px;
}}

/* ―― Checkbox ―――――――――――――――――――――――――――――――――――――― */
QCheckBox {{ color: {c['text']}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 2px solid {c['border_strong']}; background: {c['surface']};
}}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}

QTableWidget::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 2px solid {c['border_strong']}; background: {c['surface']};
}}
QTableWidget::indicator:hover {{ border: 2px solid {c['text_dim']}; }}
QTableWidget::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
QTableWidget::indicator:disabled {{ background: {c['surface_2']}; border-color: {c['border']}; }}

/* ―― Scrollbars ―――――――――――――――――――――――――――――――――――― */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 5px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_faint']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 5px; min-width: 40px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollArea {{ border: none; background: transparent; }}

/* ―― Misc ―――――――――――――――――――――――――――――――――――――――――― */
QToolTip {{
    background: {c['surface_3']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; padding: 6px 8px; border-radius: 6px;
}}
QDialog {{ background: {c['surface']}; }}
QMessageBox {{ background: {c['surface']}; }}
"""
