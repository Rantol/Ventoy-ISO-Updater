"""Reusable, theme-aware widgets shared across the views."""

from __future__ import annotations

from PySide6.QtCore import (
    Qt, Signal, QSize, Property, QPropertyAnimation, QEasingCurve, QRectF,
)
from PySide6.QtGui import QColor, QFont, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSizePolicy,
)

import theme as theme_mod


# ―― Status pill ――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

_STATUS_TONE = {
    "uptodate": "success",
    "updated": "success",
    "outdated": "warning",
    "downloading": "info",
    "verifying": "info",
    "copying": "info",
    "checking": "info",
    "notdrive": "danger",
    "error": "danger",
    "ondrive": "text_dim",
    "unknown": "text_faint",
}


class StatusBadge(QLabel):
    """A small colored pill describing an ISO's state."""

    def __init__(self, text: str = "", status: str = "unknown", theme: str = "dark"):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(26)
        self.setContentsMargins(8, 0, 8, 0)
        self.set_status(text, status, theme)

    def set_status(self, text: str, status: str, theme: str):
        c = theme_mod.palette(theme)
        tone_key = _STATUS_TONE.get(status, "text_faint")
        color = c.get(tone_key, c["text_faint"])
        self.setText(text)
        self.setStyleSheet(
            f"QLabel {{ color: {color}; background: {_soft(color, 38)}; "
            f"border: 1px solid {_soft(color, 76)}; border-radius: 7px; "
            f"padding: 2px 8px; font-size: 11px; font-weight: 600; }}"
        )


def _soft(hex_color: str, alpha: int = 38) -> str:
    """Return an rgba() string: the given color at low opacity for a pill bg."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha/255:.2f})"


# ―― Distro monogram avatar ―――――――――――――――――――――――――――――――――――――――――――――――

class Monogram(QWidget):
    """Circular badge with the distro's initial in its brand color."""

    def __init__(self, letter: str, color: str, size: int = 40):
        super().__init__()
        self._letter = (letter or "?")[0].upper()
        self._color = QColor(color)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._color))
        p.drawEllipse(0, 0, self._size, self._size)
        p.setPen(QPen(QColor("#ffffff")))
        f = QFont()
        f.setPixelSize(int(self._size * 0.45))
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._letter)
        p.end()


# ―― Card ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")


def hairline() -> QFrame:
    f = QFrame()
    f.setObjectName("Hairline")
    f.setFixedHeight(1)
    return f


# ―― Nav item ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class NavItem(QPushButton):
    def __init__(self, text: str, badge: int = 0):
        super().__init__(text)
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


# ―― Sidebar ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class Sidebar(QWidget):
    """Left navigation column: brand, nav items, and a drive status chip."""

    navigate = Signal(int)   # emits the index of the selected view

    def __init__(self, lang: dict, theme: str):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(224)
        self._lang = lang
        self._theme = theme
        self._items: list[NavItem] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 20, 16, 16)
        root.setSpacing(6)

        # Brand
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        dot = QLabel("◆")
        dot.setObjectName("BrandDot")
        brand = QLabel("Ventoy ISO Updater")
        brand.setObjectName("Brand")
        brand_row.addWidget(dot)
        brand_row.addWidget(brand)
        brand_row.addStretch()
        root.addLayout(brand_row)
        root.addSpacing(18)

        sect = QLabel(lang.get("nav_manage", "MANAGE").upper())
        sect.setObjectName("NavSection")
        root.addWidget(sect)
        root.addSpacing(4)

        for idx, key in enumerate(
            ("nav_library", "nav_sources", "nav_activity", "nav_settings")
        ):
            item = NavItem(lang.get(key, key))
            item.clicked.connect(lambda _=False, i=idx: self._select(i))
            root.addWidget(item)
            self._items.append(item)

        root.addStretch()

        # Drive chip
        self._chip = DriveChip(lang, theme)
        root.addWidget(self._chip)

        if self._items:
            self._items[0].setChecked(True)

    def _select(self, index: int):
        for i, item in enumerate(self._items):
            item.setChecked(i == index)
        self.navigate.emit(index)

    def set_index(self, index: int):
        self._select(index)

    def set_library_badge(self, count: int):
        base = self._lang.get("nav_library", "Library")
        self._items[0].setText(f"{base}   ●{count}" if count else base)

    def update_drive(self, info: dict | None):
        self._chip.update_drive(info)


# ―― Drive chip ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class DriveChip(Card):
    def __init__(self, lang: dict, theme: str):
        super().__init__()
        self._lang = lang
        self._theme = theme
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._dot = QLabel("●")
        self._title = QLabel("—")
        self._title.setStyleSheet("font-weight: 600; font-size: 12px;")
        top.addWidget(self._dot)
        top.addWidget(self._title)
        top.addStretch()
        lay.addLayout(top)

        self._detail = QLabel("")
        self._detail.setObjectName("Subtle")
        lay.addWidget(self._detail)
        self.update_drive(None)

    def update_drive(self, info: dict | None):
        c = theme_mod.palette(self._theme)
        if info:
            self._dot.setStyleSheet(f"color: {c['success']};")
            self._title.setText(self._lang.get("drive_found", "Drive"))
            self._detail.setText(
                f"{info['letter']}:\\  ·  {self._lang.get('drive_free','Free')} "
                f"{info['free_gb']:.0f}/{info['total_gb']:.0f} GB"
            )
        else:
            self._dot.setStyleSheet(f"color: {c['danger']};")
            self._title.setText(self._lang.get("drive_not_found", "No drive"))
            self._detail.setText("—")


# ―― Toggle switch ―――――――――――――――――――――――――――――――――――――――――――――――――――――――

class ToggleSwitch(QWidget):
    """An animated on/off switch used in place of a checkbox in Settings."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, theme: str = "dark"):
        super().__init__()
        self._checked = checked
        self._theme = theme
        self._offset = 1.0 if checked else 0.0
        self._w, self._h = 46, 26
        self.setFixedSize(self._w, self._h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # animated knob position, 0.0 (off) .. 1.0 (on)
    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float):
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if checked == self._checked:
            return
        self._checked = checked
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def set_theme(self, theme: str):
        self._theme = theme
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            self.toggled.emit(self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        c = theme_mod.palette(self._theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = self._h / 2
        off_bg = QColor(c["border_strong"])
        on_bg = QColor(c["accent"])
        track = QColor(on_bg)
        # interpolate track color between off and on
        t = self._offset
        track.setRgb(
            int(off_bg.red() + (on_bg.red() - off_bg.red()) * t),
            int(off_bg.green() + (on_bg.green() - off_bg.green()) * t),
            int(off_bg.blue() + (on_bg.blue() - off_bg.blue()) * t),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(QRectF(0, 0, self._w, self._h), radius, radius)
        # knob
        margin = 3
        knob_d = self._h - margin * 2
        x = margin + t * (self._w - knob_d - margin * 2)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QRectF(x, margin, knob_d, knob_d))
        p.end()
