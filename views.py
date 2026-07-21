"""The four main screens: Library, Sources, Activity, Settings.

Each view is a ``QWidget`` that receives the main-window *controller* (``app``)
and reads data / triggers actions through it. Views never touch the network or
the filesystem directly — they render state and emit intent.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QProgressBar,
    QScrollArea, QFrame, QComboBox, QLineEdit, QDialog, QDialogButtonBox,
    QFormLayout, QCheckBox, QMessageBox, QSpinBox, QFileDialog, QInputDialog,
)

import theme as theme_mod
import catalog
from widgets import Card, Monogram, StatusBadge, ToggleSwitch, hairline


def _title_block(title: str, subtitle: str) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("H1")
    s = QLabel(subtitle)
    s.setObjectName("Subtle")
    box.addWidget(t)
    box.addWidget(s)
    return box


# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
# Library
# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class LibraryView(QWidget):
    COLS = ["", "col_name", "col_path", "col_drive_ver", "col_latest_ver",
            "col_status", "col_size", "col_action", "col_remove"]

    def __init__(self, app):
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(12)
        title_row = QHBoxLayout()
        title_row.addLayout(_title_block(app.t("library_title"), app.t("library_subtitle")))
        title_row.addStretch()
        header.addLayout(title_row)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.rescan_btn = QPushButton(app.t("rescan"))
        self.rescan_btn.setObjectName("Ghost")
        self.rescan_btn.clicked.connect(app.rescan)
        action_bar.addWidget(self.rescan_btn)

        self.check_btn = QPushButton(app.t("check"))
        self.check_btn.setObjectName("Ghost")
        self.check_btn.setToolTip(app.t("check_all"))
        self.check_btn.clicked.connect(app.start_check)
        action_bar.addWidget(self.check_btn)

        self.update_btn = QPushButton(app.t("update_chosen"))
        self.update_btn.setObjectName("Ghost")
        self.update_btn.setToolTip(app.t("update_selected"))
        self.update_btn.clicked.connect(self._update_selected)
        action_bar.addStretch()
        action_bar.addWidget(self.update_btn)

        self.update_all_btn = QPushButton(app.t("update_all"))
        self.update_all_btn.setObjectName("Primary")
        self.update_all_btn.clicked.connect(self._update_all)
        action_bar.addWidget(self.update_all_btn)

        self.stop_btn = QPushButton(app.t("stop"))
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.hide()
        self.stop_btn.clicked.connect(app.stop_action)
        action_bar.addWidget(self.stop_btn)
        header.addLayout(action_bar)
        root.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLS))
        self.table.setHorizontalHeaderLabels([app.t(c) if c else "" for c in self.COLS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.itemChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(self._rename_row)
        hdr = self.table.horizontalHeader()
        for column in range(len(self.COLS)):
            hdr.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        hdr.setMinimumSectionSize(34)
        hdr.setStretchLastSection(False)
        widths = [42, 180, 240, 92, 100, 148, 76, 118, 108]
        minimums = [42, 140, 180, 78, 84, 128, 64, 108, 96]
        for i, w in enumerate(widths):
            if w:
                self.table.setColumnWidth(i, w)
            self.table.setColumnWidth(i, max(self.table.columnWidth(i), minimums[i]))
        root.addWidget(self.table, 1)

        # progress footer
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)
        foot = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("Subtle")
        self.speed_label = QLabel("")
        self.speed_label.setObjectName("Subtle")
        foot.addWidget(self.status_label)
        foot.addStretch()
        foot.addWidget(self.speed_label)
        root.addLayout(foot)

        self._empty = QLabel("")
        self._empty.setObjectName("Subtle")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        root.addWidget(self._empty)
        self._empty.hide()
        self._selected_keys: set[str] = set()
        self._updating_table = False
        self._busy = False
        self._sync_selection_action()

    # -- rendering -------------------------------------------------------
    def refresh(self):
        app = self.app
        rows = app.rows()
        self._updating_table = True
        self.table.setRowCount(0)

        if not rows:
            self._selected_keys.clear()
            self.table.hide()
            self._empty.show()
            self._empty.setText(
                app.t("no_drive_library") if not app.drive_present()
                else app.t("empty_library")
            )
            self._updating_table = False
            self._sync_selection_action()
            return
        self._empty.hide()
        self.table.show()

        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            updatable = r["status"] in ("outdated", "notdrive")

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked if r["key"] in self._selected_keys
                              else Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, chk)

            name_item = QTableWidgetItem("  " + r["name"])
            name_item.setForeground(QColor(theme_mod.palette(app.theme)["text"]))
            f = QFont(); f.setBold(True); name_item.setFont(f)
            self.table.setItem(i, 1, name_item)

            self._set(i, 2, r["subtitle"], dim=True)
            self._set(i, 3, r["drive_ver"] or "—",
                      color="success" if r["drive_ver"] else "text_faint")
            self._set(i, 4, r["latest_ver"] or "—",
                      color="warning" if r["status"] == "outdated" else "text_dim")

            badge = StatusBadge(app.t(r["status_text_key"]), r["status"], app.theme)
            wrap = self._center(badge)
            self.table.setCellWidget(i, 5, wrap)

            self._set(i, 6, f"{r['size_gb']:.1f} GB" if r["size_gb"] else "—", dim=True)

            if updatable:
                btn = QPushButton(app.t("download") if r["status"] == "notdrive" else app.t("update"))
                btn.setObjectName("TableAction")
                btn.setFixedHeight(32)
                btn.setToolTip(btn.text())
                btn.clicked.connect(lambda _=False, k=r["key"]: self.app.start_update([k]))
                self.table.setCellWidget(i, 7, btn)
            else:
                self.table.setCellWidget(i, 7, self._empty_cell())
            if r.get("delete_path"):
                remove = QPushButton(app.t("delete"))
                remove.setObjectName("TableDelete")
                remove.setFixedHeight(32)
                remove.setToolTip(remove.text())
                remove.clicked.connect(lambda _=False, p=r["delete_path"]: self.app.delete_image(p))
                self.table.setCellWidget(i, 8, remove)
            else:
                self.table.setCellWidget(i, 8, self._empty_cell())
        self._updating_table = False
        self._sync_selection_action()

    def _set(self, row, col, text, color="text", dim=False):
        c = theme_mod.palette(self.app.theme)
        item = QTableWidgetItem(text)
        key = "text_faint" if dim else color
        item.setForeground(QColor(c.get(key, c["text"])))
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(row, col, item)

    def _center(self, w: QWidget) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("CellHost")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.addWidget(w, alignment=Qt.AlignmentFlag.AlignCenter)
        return wrap

    def _empty_cell(self) -> QWidget:
        cell = QWidget()
        cell.setObjectName("CellHost")
        return cell

    def _update_selected(self):
        keys = [row["key"] for row in self.app.rows()
                if row["key"] in self._selected_keys
                and row["status"] in ("outdated", "notdrive")]
        if not keys:
            QMessageBox.information(self, self.app.t("update_selected"),
                                    self.app.t("warn_no_selection"))
            return
        self.app.start_update(keys)

    def _update_all(self):
        keys = [row["key"] for row in self.app.rows()
                if row["status"] in ("outdated", "notdrive")]
        if not keys:
            QMessageBox.information(self, self.app.t("update_all"),
                                    self.app.t("warn_nothing_to_update"))
            return
        self.app.start_update(keys)

    def _rename_row(self, row: int, column: int):
        if column != 1 or row < 0 or row >= len(self.app.rows()):
            return
        source_key = self.app.rows()[row]["key"]
        current = self.app.rows()[row]["name"]
        name, accepted = QInputDialog.getText(
            self, self.app.t("rename_source"), self.app.t("rename_source_prompt"),
            text=current,
        )
        if accepted and name.strip() and name.strip() != current:
            self.app.rename_row(source_key, name.strip())

    def _selection_changed(self, item: QTableWidgetItem):
        if self._updating_table or item.column() != 0:
            return
        row = self.app.rows()[item.row()]
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_keys.add(row["key"])
        else:
            self._selected_keys.discard(row["key"])
        self._sync_selection_action()

    # -- progress hooks --------------------------------------------------
    def set_busy(self, busy: bool):
        self._busy = busy
        self.stop_btn.setEnabled(busy)
        self.stop_btn.setVisible(busy)
        self.check_btn.setEnabled(not busy)
        self.update_all_btn.setEnabled(not busy)
        self.rescan_btn.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self._sync_selection_action()
        if not busy:
            self.speed_label.setText("")

    def _sync_selection_action(self):
        self.update_btn.setEnabled(not self._busy and bool(self._selected_keys))

    def set_progress(self, pct: int, text: str = "", speed: str = ""):
        self.progress.setValue(pct)
        if text:
            self.status_label.setText(text)
        self.speed_label.setText(speed)

    def set_status(self, text: str):
        self.status_label.setText(text)


# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
# Sources
# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class SourcesView(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.addLayout(_title_block(app.t("sources_title"), app.t("sources_subtitle")))
        header.addStretch()
        add_custom = QPushButton(app.t("add_custom"))
        add_custom.setObjectName("Ghost")
        add_custom.clicked.connect(self._add_custom)
        header.addWidget(add_custom)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.inner_lay = QVBoxLayout(inner)
        self.inner_lay.setContentsMargins(0, 0, 8, 0)
        self.inner_lay.setSpacing(20)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self._catalog_label = QLabel(app.t("sources_catalog"))
        self._catalog_label.setObjectName("CardTitle")
        self.inner_lay.addWidget(self._catalog_label)
        self.grid = QGridLayout()
        self.grid.setSpacing(14)
        self.inner_lay.addLayout(self.grid)

        self._connected_label = QLabel(app.t("sources_connected"))
        self._connected_label.setObjectName("CardTitle")
        self.inner_lay.addWidget(self._connected_label)
        self.connected_box = QVBoxLayout()
        self.connected_box.setSpacing(10)
        self.inner_lay.addLayout(self.connected_box)
        self.inner_lay.addStretch()

    def refresh(self):
        self._build_catalog()
        self._build_connected()

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_catalog(self):
        self._clear(self.grid)
        cols = 2
        for idx, distro in enumerate(catalog.all_distros()):
            card = self._catalog_card(distro)
            self.grid.addWidget(card, idx // cols, idx % cols)

    def _catalog_card(self, distro: dict) -> Card:
        app = self.app
        card = Card()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        lay.addWidget(Monogram(distro["name"][0], distro["color"], 44))

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(distro["name"])
        name.setObjectName("CardTitle")
        desc = QLabel(catalog.distro_desc(distro, app.lang_code))
        desc.setObjectName("Subtle")
        desc.setWordWrap(True)
        col.addWidget(name)
        col.addWidget(desc)
        lay.addLayout(col, 1)

        btn = QPushButton(app.t("connect"))
        btn.setObjectName("Primary")
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda _=False, d=distro: self._connect(d))
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_connected(self):
        self._clear(self.connected_box)
        app = self.app
        records = app.connected_sources() + app.custom_sources()
        if not records:
            empty = QLabel(app.t("no_connected"))
            empty.setObjectName("Subtle")
            self.connected_box.addWidget(empty)
            return
        for rec in records:
            self.connected_box.addWidget(self._connected_row(rec))

    def _connected_row(self, rec: dict) -> Card:
        app = self.app
        card = Card()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        is_custom = rec.get("kind") == "custom"
        color = "#64748b"
        letter = "?"
        if not is_custom:
            distro = catalog.get_distro(rec.get("distro", ""))
            if distro:
                color = distro["color"]
                letter = distro["name"][0]
        else:
            letter = (rec.get("name") or "C")[0]
        lay.addWidget(Monogram(letter, color, 36))

        col = QVBoxLayout(); col.setSpacing(1)
        title = QLabel(app.source_title(rec))
        title.setStyleSheet("font-weight: 600;")
        sub = QLabel(app.source_subtitle(rec))
        sub.setObjectName("Subtle")
        col.addWidget(title)
        col.addWidget(sub)
        lay.addLayout(col, 1)

        edit = QPushButton(app.t("edit"))
        edit.setObjectName("Ghost")
        edit.setFixedHeight(30)
        edit.clicked.connect(lambda _=False, r=rec: self._edit(r))
        lay.addWidget(edit)

        disconnect = QPushButton(app.t("disconnect"))
        disconnect.setObjectName("Danger")
        disconnect.setFixedHeight(30)
        disconnect.clicked.connect(lambda _=False, k=rec["key"], n=app.source_title(rec):
                                   self._disconnect(k, n))
        lay.addWidget(disconnect)
        return card

    # -- actions ---------------------------------------------------------
    def _connect(self, distro: dict):
        dlg = ConnectDialog(self.app, distro, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.app.connect_source(dlg.result_record())

    def _disconnect(self, key: str, name: str):
        reply = QMessageBox.question(
            self, self.app.t("confirm"),
            self.app.t("confirm_disconnect").format(name=name))
        if reply == QMessageBox.StandardButton.Yes:
            self.app.disconnect_source(key)

    def _add_custom(self):
        dlg = CustomSourceDialog(self.app, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rec = dlg.result_record()
            if rec:
                self.app.add_custom_source(rec)

    def _edit(self, rec: dict):
        if rec.get("kind") == "custom":
            dlg = CustomSourceDialog(self.app, self, rec)
        else:
            distro = catalog.get_distro(rec.get("distro", ""))
            if not distro:
                return
            dlg = ConnectDialog(self.app, distro, self, rec)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.app.update_source(rec["key"], dlg.result_record())


class ConnectDialog(QDialog):
    def __init__(self, app, distro: dict, parent=None, record: dict | None = None):
        super().__init__(parent)
        self.app = app
        self.distro = distro
        self.setWindowTitle(app.t("connect_title") + " · " + distro["name"])
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(22, 22, 22, 22)

        self.edition = QComboBox()
        for ed in catalog.available_editions(distro):
            self.edition.addItem(catalog.edition_label(ed, app.lang_code), ed["id"])
        form.addRow(app.t("edition"), self.edition)

        self.arch = QComboBox()
        self.arch.addItems(distro["archs"])
        form.addRow(app.t("arch"), self.arch)

        self.target = QComboBox()
        folders = app.target_folders()
        current_target = (record or {}).get("target_dir", "")
        if current_target not in folders:
            folders.append(current_target)
        for folder in folders:
            self.target.addItem(app.t("target_root") if not folder else folder, folder)
        self.target.setCurrentIndex(max(0, self.target.findData(current_target)))
        form.addRow(app.t("target_dir"), self.target)
        hint = QLabel(app.t("target_dir_hint"))
        hint.setObjectName("Subtle")
        hint.setWordWrap(True)
        form.addRow("", hint)

        self.auto = ToggleSwitch(bool((record or {}).get("auto", True)), app.theme)
        form.addRow(app.t("auto_update"), self.auto)

        if record:
            self.edition.setCurrentIndex(max(0, self.edition.findData(record.get("edition"))))
            self.arch.setCurrentIndex(max(0, self.arch.findText(record.get("arch", ""))))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_record(self) -> dict:
        eid = self.edition.currentData()
        arch = self.arch.currentText()
        target = self.target.currentData() or ""
        return {
            "kind": "catalog",
            "key": f"cat:{self.distro['id']}:{eid}:{arch}:{target or 'root'}",
            "distro": self.distro["id"],
            "edition": eid,
            "arch": arch,
            "target_dir": target,
            "auto": self.auto.isChecked(),
            "last_version": "",
            "last_checked": "",
        }


class CustomSourceDialog(QDialog):
    def __init__(self, app, parent=None, record: dict | None = None):
        super().__init__(parent)
        self.app = app
        self._original_key = (record or {}).get("key", "")
        self.setWindowTitle(app.t("custom_title"))
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(22, 22, 22, 22)

        self.name = QLineEdit()
        self.name.setText((record or {}).get("name", ""))
        form.addRow(app.t("custom_name"), self.name)
        self.url = QLineEdit()
        self.url.setText((record or {}).get("url", ""))
        self.url.setPlaceholderText("https://…/image.iso")
        form.addRow(app.t("custom_url"), self.url)
        self.pattern = QLineEdit()
        self.pattern.setText((record or {}).get("pattern", ""))
        self.pattern.setPlaceholderText(app.t("custom_pattern_placeholder"))
        self.pattern.setToolTip(app.t("custom_pattern_hint"))
        form.addRow(app.t("custom_pattern"), self.pattern)
        hint = QLabel(app.t("custom_pattern_hint"))
        hint.setObjectName("Subtle")
        hint.setWordWrap(True)
        form.addRow("", hint)
        help_button = QPushButton(app.t("custom_pattern_help"))
        help_button.setObjectName("LinkButton")
        help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        help_button.clicked.connect(lambda: MaskHelpDialog(app, self).exec())
        form.addRow("", help_button)
        self.drive_match = QLineEdit()
        self.drive_match.setText((record or {}).get("drive_match_re", ""))
        self.drive_match.setPlaceholderText(app.t("custom_drive_match_placeholder"))
        self.drive_match.setToolTip(app.t("custom_drive_match_hint"))
        form.addRow(app.t("custom_drive_match"), self.drive_match)
        self.target = QComboBox()
        folders = app.target_folders()
        current_target = (record or {}).get("target_dir", "")
        if current_target not in folders:
            folders.append(current_target)
        for folder in folders:
            self.target.addItem(app.t("target_root") if not folder else folder, folder)
        self.target.setCurrentIndex(max(0, self.target.findData(current_target)))
        form.addRow(app.t("target_dir"), self.target)

        self.auto = ToggleSwitch(bool((record or {}).get("auto", True)), app.theme)
        form.addRow(app.t("auto_update"), self.auto)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_record(self) -> dict | None:
        url = self.url.text().strip()
        if not url:
            return None
        filename = url.split("/")[-1].split("?")[0]
        if not filename.endswith(".iso"):
            filename += ".iso"
        name = self.name.text().strip() or filename
        target = self.target.currentData() or ""
        key = self._original_key or f"cus:{name}"
        return {
            "kind": "custom",
            "key": key,
            "name": name,
            "url": url,
            "pattern": self.pattern.text().strip(),
            "drive_match_re": self.drive_match.text().strip(),
            "target_dir": target,
            "filename_on_drive": filename,
            "auto": self.auto.isChecked(),
            "last_version": "",
            "last_checked": "",
        }


class MaskHelpDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.setWindowTitle(app.t("custom_pattern_help_title"))
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        text = QLabel(app.t("custom_pattern_help_text"))
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text)
        close = QPushButton(app.t("close"))
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
# Activity
# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class ActivityView(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.addLayout(_title_block(app.t("activity_title"), app.t("activity_subtitle")))
        header.addStretch()
        clear = QPushButton(app.t("activity_clear"))
        clear.setObjectName("Ghost")
        clear.clicked.connect(self._clear)
        header.addWidget(clear)
        root.addLayout(header)

        self.list_card = Card()
        self.list_lay = QVBoxLayout(self.list_card)
        self.list_lay.setContentsMargins(4, 4, 4, 4)
        self.list_lay.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.list_card)
        root.addWidget(self.scroll, 1)

    def refresh(self):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        events = self.app.activity_events()
        if not events:
            lbl = QLabel(self.app.t("activity_empty"))
            lbl.setObjectName("Subtle")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setContentsMargins(0, 24, 0, 24)
            self.list_lay.addWidget(lbl)
            return
        for i, ev in enumerate(reversed(events)):
            self.list_lay.addWidget(self._row(ev))
            if i < len(events) - 1:
                self.list_lay.addWidget(hairline())

    def _row(self, ev: dict) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)
        c = theme_mod.palette(self.app.theme)
        tone = {"ok": c["success"], "error": c["danger"], "info": c["text_dim"]}.get(
            ev.get("level", "info"), c["text_dim"])
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {tone}; font-size: 10px;")
        lay.addWidget(dot)
        msg = QLabel(ev.get("msg", ""))
        msg.setWordWrap(True)
        lay.addWidget(msg, 1)
        ts = QLabel(ev.get("time", ""))
        ts.setObjectName("Subtle")
        lay.addWidget(ts)
        return w

    def _clear(self):
        reply = QMessageBox.question(self, self.app.t("confirm"),
                                     self.app.t("confirm_clear_activity"))
        if reply == QMessageBox.StandardButton.Yes:
            self.app.clear_activity()


# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
# Settings
# ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class SettingsView(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        s = app.settings
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(16)
        root.addLayout(_title_block(app.t("settings_title"), app.t("settings_subtitle")))

        card = Card()
        form = QFormLayout(card)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # cache dir + browse
        cache_row = QHBoxLayout()
        self.cache = QLineEdit(s.get("cache_dir", ""))
        self.cache.setMinimumWidth(320)
        browse = QPushButton(app.t("browse"))
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse)
        cache_row.addWidget(self.cache)
        cache_row.addWidget(browse)
        form.addRow(app.t("settings_cache"), cache_row)
        hint = QLabel(app.t("settings_cache_hint"))
        hint.setObjectName("Subtle")
        form.addRow("", hint)

        clear_cache = QPushButton(app.t("clear_cache"))
        clear_cache.setObjectName("Danger")
        clear_cache.clicked.connect(app.clear_cache)
        form.addRow("", clear_cache)

        self.theme = QComboBox()
        self.theme.addItem(app.t("theme_dark"), "dark")
        self.theme.addItem(app.t("theme_light"), "light")
        self.theme.setCurrentIndex(0 if s.get("theme") != "light" else 1)
        form.addRow(app.t("settings_theme"), self.theme)

        self.lang = QComboBox()
        self.lang.addItem("Русский", "ru")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(0 if s.get("lang") != "en" else 1)
        form.addRow(app.t("settings_lang"), self.lang)

        self.label = QLineEdit(s.get("ventoy_label", "Ventoy"))
        form.addRow(app.t("settings_label"), self.label)

        self.autocheck = ToggleSwitch(bool(s.get("auto_check", True)), app.theme)
        form.addRow(app.t("settings_autocheck"), self.autocheck)

        self.interval = QSpinBox()
        self.interval.setRange(15, 10080)
        self.interval.setValue(int(s.get("auto_check_interval_min", 720)))
        self.interval.setSuffix(" min")
        form.addRow(app.t("settings_interval"), self.interval)

        self.startup = ToggleSwitch(bool(s.get("check_on_startup", True)), app.theme)
        form.addRow(app.t("settings_startup"), self.startup)

        root.addWidget(card)

        save = QPushButton(app.t("settings_save"))
        save.setObjectName("Primary")
        save.setFixedWidth(200)
        save.setFixedHeight(42)
        save.clicked.connect(self._save)
        root.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addStretch()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, self.app.t("settings_cache"))
        if folder:
            self.cache.setText(folder)

    def _save(self):
        self.app.apply_settings({
            "cache_dir": self.cache.text().strip(),
            "theme": self.theme.currentData(),
            "lang": self.lang.currentData(),
            "ventoy_label": self.label.text().strip() or "Ventoy",
            "auto_check": self.autocheck.isChecked(),
            "auto_check_interval_min": self.interval.value(),
            "check_on_startup": self.startup.isChecked(),
        })
