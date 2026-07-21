"""Ventoy ISO Updater — application entry point and controller.

The main window owns application state and exposes a small controller API that
the views call: ``rows()``, ``start_check()``, ``start_update()``,
``connect_source()``, etc. Networking and copying happen in worker threads
(:mod:`updater`); the controller marshals their signals back to the views.

Author: Rantol
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QMessageBox,
)

import config
import catalog
import drive as drive_mod
import updater
from i18n import get_lang, tr
import theme as theme_mod
from widgets import Sidebar
from views import LibraryView, SourcesView, ActivityView, SettingsView

APP_VERSION = "1.0.0"


class VentoyUpdaterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = config.load_settings()
        self.lang_code = self.settings.get("lang", "ru")
        self.lang = get_lang(self.lang_code)
        self.theme = self.settings.get("theme", "dark")

        self._scanned: list[dict] = []
        self._drive_info: dict | None = None
        self._rows: list[dict] = []
        self._latest: dict[str, updater.LatestInfo] = {}  # key -> LatestInfo
        self._check_worker: updater.CheckWorker | None = None
        self._update_worker: updater.UpdateWorker | None = None
        self._busy = False

        self.setWindowTitle(f"{self.t('app_name')}")
        self.setMinimumSize(1080, 680)
        self.resize(1180, 760)

        self._build_ui()
        self._apply_theme()

        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.rescan)

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._auto_tick)
        self._reschedule_auto()

        QTimer.singleShot(150, self._initial_load)

    # ―― i18n ――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
    def t(self, key: str) -> str:
        return tr(self.lang, key)

    # ―― UI ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.sidebar = Sidebar(self.lang, self.theme)
        self.sidebar.navigate.connect(self._navigate)
        lay.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        self.library = LibraryView(self)
        self.sources = SourcesView(self)
        self.activity = ActivityView(self)
        self.settings_view = SettingsView(self)
        for v in (self.library, self.sources, self.activity, self.settings_view):
            self.stack.addWidget(v)

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(theme_mod.stylesheet(self.theme))

    def _navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        view = self.stack.widget(index)
        if hasattr(view, "refresh"):
            view.refresh()

    def _rebuild_ui(self, rescan: bool = False):
        """Rebuild the whole UI after a language/theme change.

        Called deferred (via a zero-delay timer) so we never tear down the
        widget that is currently handling the Save click. ``setCentralWidget``
        disposes of the previous widget tree for us.
        """
        self.lang = get_lang(self.lang_code)
        idx = self.stack.currentIndex()
        self._build_ui()
        self._apply_theme()
        if rescan:
            self.rescan()
        else:
            self.sidebar.update_drive(self._drive_info)
            self._rebuild_rows()
            self.refresh_all()
        self.sidebar.set_index(idx)

    # ―― initial load / scanning ―――――――――――――――――――――――――――――――――――――――
    def _initial_load(self):
        self.rescan()
        if self.settings.get("check_on_startup", True):
            QTimer.singleShot(600, self.start_check)

    def rescan(self):
        label = self.settings.get("ventoy_label", "Ventoy")
        self._drive_info = drive_mod.drive_info(label)
        self._scanned = drive_mod.scan_ventoy_drive(label)
        self.sidebar.update_drive(self._drive_info)
        self._rebuild_rows()
        self.refresh_all()

    def drive_present(self) -> bool:
        return self._drive_info is not None

    # ―― row model ―――――――――――――――――――――――――――――――――――――――――――――――――――――
    def _rebuild_rows(self):
        """Compute Library rows from connected sources + every ISO on the drive.

        Rows come in two kinds: source-backed rows (with a Latest version to
        compare against) and plain drive rows for ISOs that are present on the
        stick but not tied to any source. ``claimed`` tracks the relative paths
        already represented by a source so a file is never listed twice.
        """
        rows: list[dict] = []
        drive_path = self._drive_info["mountpoint"] if self._drive_info else ""
        claimed: set[str] = set()

        for rec in self.connected_sources():
            distro = catalog.get_distro(rec.get("distro", ""))
            if not distro:
                continue
            edition = catalog.get_edition(distro, rec.get("edition", ""))
            matched = self._matched_isos(rec)   # newest first, any folder
            for iso, _v in matched:
                claimed.add(iso.get("relative_path", "").lower())
            best = matched[0] if matched else None
            latest = self._latest.get(rec["key"])
            latest_ver = latest.version if latest else rec.get("last_version", "")
            stale = bool(latest and latest.ok and any(
                updater.is_newer(latest.version, version) for _iso, version in matched
            ))
            rows.append(self._make_row(
                key=rec["key"],
                name=self._display_name(
                    rec["key"],
                    f"{distro['name']} · {catalog.edition_label(edition, self.lang_code)}"),
                subtitle=best[0]["relative_path"] if best else self._expected_path(rec, latest),
                drive_ver=best[1] if best else "", latest_ver=latest_ver,
                on_drive=best is not None,
                size_gb=best[0].get("size_gb", 0.0) if best else 0.0,
                latest=latest,
                has_stale=stale,
                delete_path=best[0]["relative_path"] if best else "",
            ))

        for rec in self.custom_sources():
            latest = self._latest.get(rec["key"])
            latest_ver = latest.version if latest else rec.get("last_version", "")
            target = rec.get("target_dir", "")
            filename = rec.get("filename_on_drive", "")
            matched = self._matched_isos(rec)   # newest first, any folder
            for iso, _v in matched:
                claimed.add(iso.get("relative_path", "").lower())
            best = matched[0] if matched else None
            stale = bool(latest and latest.ok and any(
                updater.is_newer(latest.version, version) for _iso, version in matched
            ))
            fallback = self._expected_path(rec, latest)
            rows.append(self._make_row(
                key=rec["key"],
                name=self._display_name(rec["key"], rec.get("name", filename)),
                subtitle=best[0]["relative_path"] if best else fallback,
                drive_ver=best[1] if best else "", latest_ver=latest_ver,
                on_drive=best is not None,
                size_gb=best[0].get("size_gb", 0.0) if best else 0.0,
                latest=latest,
                has_stale=stale,
                delete_path=best[0]["relative_path"] if best else "",
            ))

        # Every remaining ISO physically present on the drive (any folder).
        for iso in self._scanned:
            rel = iso.get("relative_path", "")
            if rel.lower() in claimed:
                continue
            display = self._display_name(
                f"drive:{rel}", iso.get("os_name") or iso.get("filename", rel))
            ver = iso.get("version", "")
            rows.append(self._make_row(
                key=f"drive:{rel}",
                name=display,
                subtitle=rel,
                drive_ver=ver, latest_ver="",
                on_drive=True,
                size_gb=iso.get("size_gb", 0.0),
                latest=None, has_stale=False, delete_path=rel,
            ))

        self._rows = rows
        self._update_badge()

    def _matched_isos(self, rec: dict) -> list[tuple[dict, str]]:
        """ISOs on the drive (in ANY folder) that belong to *rec*, newest first.

        Returns ``(scanned_iso_dict, version)`` pairs. Catalog sources match by
        the edition's filename regex; custom sources match by exact filename.
        A source with a configured target folder matches only that folder. This
        permits separate sources for the same distro/edition in different
        locations while keeping legacy sources without a folder flexible.
        """
        scanned = self._scanned
        target_dir = rec.get("target_dir", "").strip("/\\").lower()

        def is_in_target(iso: dict) -> bool:
            if not target_dir:
                return True
            parent = str(Path(iso.get("relative_path", "")).parent)
            return parent.strip(".\\/").replace("\\", "/").lower() == target_dir.replace("\\", "/")

        if rec.get("kind") == "custom":
            fn = (rec.get("filename_on_drive") or "").lower()
            rx = updater.custom_drive_match_regex(
                rec.get("filename_on_drive", ""), rec.get("drive_match_re", ""))
            if not rx:
                return []
            out = []
            for iso in scanned:
                if not is_in_target(iso):
                    continue
                m = rx.fullmatch(iso.get("filename", ""))
                if not m:
                    continue
                version = m.group(1) if m.groups() else iso.get("version", "")
                out.append((iso, version))
            out.sort(key=lambda item: updater.parse_version(item[1]), reverse=True)
            return out
        distro = catalog.get_distro(rec.get("distro", ""))
        if not distro:
            return []
        edition = catalog.get_edition(distro, rec.get("edition", ""))
        arch = rec.get("arch", distro["archs"][0])
        rx = updater.drive_match_regex(distro, edition, arch)
        out: list[tuple[dict, str]] = []
        for iso in scanned:
            if not is_in_target(iso):
                continue
            m = rx.search(iso.get("filename", "")) if rx else None
            if not m:
                continue
            ver = m.group(1) if m.groups() else iso.get("version", "")
            out.append((iso, ver))
        out.sort(key=lambda t: updater.parse_version(t[1]), reverse=True)
        return out

    def _make_row(self, key, name, subtitle, drive_ver, latest_ver,
                  on_drive, size_gb, latest, has_stale: bool = False,
                  delete_path: str = "") -> dict:
        # status precedence: error > checking-known > not on drive > outdated > uptodate
        if latest is not None and latest.error:
            status, skey = "error", "status_error"
        elif not on_drive:
            status, skey = "notdrive", "status_notdrive"
        elif has_stale or (latest_ver and updater.is_newer(latest_ver, drive_ver)):
            status, skey = "outdated", "status_outdated"
        elif latest_ver:
            status, skey = "uptodate", "status_uptodate"
        elif on_drive:
            status, skey = "ondrive", "status_ondrive"
        else:
            status, skey = "unknown", "status_unknown"
        return {
            "key": key, "name": name, "subtitle": subtitle,
            "drive_ver": drive_ver, "latest_ver": latest_ver,
            "status": status, "status_text_key": skey,
            "size_gb": size_gb,
            "delete_path": delete_path,
        }

    def _expected_path(self, rec: dict, latest: updater.LatestInfo | None) -> str:
        target = rec.get("target_dir", "")
        filename = rec.get("filename_on_drive", "") or (latest.filename if latest else "")
        path = "/".join(part for part in (target, filename) if part) or "/"
        return f"{path} · {self.t('path_missing')}"

    def rows(self) -> list[dict]:
        return self._rows

    def _display_name(self, key: str, fallback: str) -> str:
        return self.settings.setdefault("display_names", {}).get(key, fallback)

    def _update_badge(self):
        n = sum(1 for r in self._rows if r["status"] in ("outdated", "notdrive"))
        self.sidebar.set_library_badge(n)

    # ―― source records ――――――――――――――――――――――――――――――――――――――――――――――――
    def connected_sources(self) -> list[dict]:
        return self.settings.setdefault("connected_sources", [])

    def custom_sources(self) -> list[dict]:
        out = []
        for rec in self.settings.setdefault("custom_sources", []):
            r = dict(rec)
            r.setdefault("kind", "custom")
            r.setdefault("key", f"cus:{r.get('name','custom')}")
            out.append(r)
        return out

    def source_title(self, rec: dict) -> str:
        if rec.get("kind") == "custom":
            return rec.get("name", "custom")
        distro = catalog.get_distro(rec.get("distro", ""))
        if not distro:
            return rec.get("distro", "?")
        edition = catalog.get_edition(distro, rec.get("edition", ""))
        return f"{distro['name']} · {catalog.edition_label(edition, self.lang_code)}"

    def source_subtitle(self, rec: dict) -> str:
        arch = rec.get("arch", "")
        target = rec.get("target_dir", "") or "/"
        auto = self.t("auto_update") if rec.get("auto", True) else ""
        parts = [p for p in (arch, target, auto) if p]
        return "  ·  ".join(parts)

    def target_folders(self) -> list[str]:
        return drive_mod.ventoy_folders(self.settings.get("ventoy_label", "Ventoy"))

    def connect_source(self, rec: dict):
        srcs = self.connected_sources()
        srcs[:] = [s for s in srcs if s.get("key") != rec["key"]]
        srcs.append(rec)
        config.save_settings(self.settings)
        self._rebuild_rows()
        self.refresh_all()
        # Immediately resolve the just-connected source.
        self.start_check(keys=[rec["key"]])

    def disconnect_source(self, key: str):
        self.settings["connected_sources"] = [
            s for s in self.connected_sources() if s.get("key") != key]
        self.settings["custom_sources"] = [
            s for s in self.settings.get("custom_sources", [])
            if s.get("key") != key and f"cus:{s.get('name','custom')}" != key]
        self._latest.pop(key, None)
        config.save_settings(self.settings)
        self._rebuild_rows()
        self.refresh_all()

    def add_custom_source(self, rec: dict):
        customs = self.settings.setdefault("custom_sources", [])
        customs[:] = [s for s in customs if s.get("name") != rec["name"]]
        customs.append({k: v for k, v in rec.items() if k != "kind"})
        config.save_settings(self.settings)
        self._rebuild_rows()
        self.refresh_all()
        self.start_check(keys=[rec["key"]])

    def update_source(self, original_key: str, rec: dict):
        """Replace a persisted source record, including a changed catalog key."""
        if rec.get("kind") == "custom":
            customs = self.settings.setdefault("custom_sources", [])
            customs[:] = [s for s in customs
                          if s.get("key") != original_key
                          and f"cus:{s.get('name', 'custom')}" != original_key]
            customs.append({k: v for k, v in rec.items() if k != "kind"})
        else:
            sources = self.connected_sources()
            sources[:] = [s for s in sources if s.get("key") != original_key]
            sources[:] = [s for s in sources if s.get("key") != rec["key"]]
            sources.append(rec)
        self._latest.pop(original_key, None)
        config.save_settings(self.settings)
        self._rebuild_rows()
        self.refresh_all()
        self.start_check(keys=[rec["key"]])

    def rename_source(self, key: str, name: str):
        """Change only the display name of a custom source."""
        for source in self.settings.setdefault("custom_sources", []):
            source_key = source.get("key") or f"cus:{source.get('name', 'custom')}"
            if source_key == key or f"cus:{source.get('name', 'custom')}" == key:
                source["name"] = name
                config.save_settings(self.settings)
                self._rebuild_rows()
                self.refresh_all()
                return

    def rename_row(self, key: str, name: str):
        """Persist a user-facing library name without changing source identity."""
        if not name.strip():
            return
        self.settings.setdefault("display_names", {})[key] = name.strip()
        config.save_settings(self.settings)
        self._rebuild_rows()
        self.refresh_all()

    # ―― specs for the check worker ―――――――――――――――――――――――――――――――――――――
    def _specs(self, keys: list[str] | None = None) -> list[dict]:
        specs = []
        for rec in self.connected_sources():
            if keys and rec["key"] not in keys:
                continue
            specs.append({"key": rec["key"], "kind": "catalog",
                          "distro": rec.get("distro"), "edition": rec.get("edition"),
                          "arch": rec.get("arch")})
        for rec in self.custom_sources():
            if keys and rec["key"] not in keys:
                continue
            specs.append({"key": rec["key"], "kind": "custom",
                          "url": rec.get("url", ""), "pattern": rec.get("pattern", "")})
        return specs

    # ―― check flow ――――――――――――――――――――――――――――――――――――――――――――――――――――
    def start_check(self, keys: list[str] | None = None):
        if self._busy:
            return
        specs = self._specs(keys)
        if not specs:
            return
        self._set_busy(True)
        self.library.set_status(self.t("checking"))
        self.log("info", self.t("ev_check_start"))
        self._check_worker = updater.CheckWorker(specs)
        self._check_worker.progress.connect(self._on_check_progress)
        self._check_worker.checked.connect(self._on_checked)
        self._check_worker.finished.connect(self._on_check_finished)
        self._check_worker.start()

    def _on_check_progress(self, done: int, total: int):
        pct = int(done / total * 100) if total else 100
        self.library.set_progress(pct, f"{self.t('checking')} ({done}/{total})")

    def _on_checked(self, key: str, info):
        self._latest[key] = info
        name = self._name_for_key(key)
        if info.ok:
            self.log("info", self.t("ev_resolved").format(name=name, ver=info.version))
            self._store_last_version(key, info.version)
        else:
            self.log("error", self.t("ev_resolve_fail").format(name=name, err=info.error))
        self._rebuild_rows()
        self.library.refresh()

    def _on_check_finished(self):
        self._set_busy(False)
        n = sum(1 for r in self._rows if r["status"] in ("outdated", "notdrive"))
        self.library.set_progress(100, self.t("check_done"))
        self.log("ok", self.t("ev_check_done").format(n=n))
        config.save_settings(self.settings)
        self._rebuild_rows()
        self.refresh_all()

    # ―― update flow ―――――――――――――――――――――――――――――――――――――――――――――――――――
    def start_update(self, keys: list[str]):
        if self._busy:
            return
        if not self._drive_info:
            QMessageBox.warning(self, self.t("app_name"), self.t("warn_no_drive"))
            return
        jobs = self._build_jobs(keys)
        if not jobs:
            QMessageBox.information(self, self.t("app_name"),
                                    self.t("warn_nothing_to_update"))
            return
        reply = QMessageBox.question(
            self, self.t("confirm"),
            self.t("confirm_update").format(n=len(jobs)))
        if reply != QMessageBox.StandardButton.Yes:
            return

        cache_dir = Path(self.settings.get("cache_dir", config.default_cache_dir()))
        cache_dir.mkdir(parents=True, exist_ok=True)

        self._set_busy(True)
        self._update_jobs = jobs
        self._update_worker = updater.UpdateWorker(jobs)
        self._update_worker.phase.connect(self._on_update_phase)
        self._update_worker.progress.connect(self._on_update_progress)
        self._update_worker.job_done.connect(self._on_job_done)
        self._update_worker.done.connect(self._on_update_done)
        self._update_worker.start()

    def _build_jobs(self, keys: list[str]) -> list[dict]:
        cache_dir = self.settings.get("cache_dir", config.default_cache_dir())
        drive_path = self._drive_info["mountpoint"]
        jobs = []
        for key in keys:
            info = self._latest.get(key)
            if not info or not info.ok:
                continue
            rec = self._record_for_key(key)
            if not rec:
                continue
            target = rec.get("target_dir", "")
            matched = self._matched_isos(rec)   # existing copies, any folder
            if matched:
                # Keep the new ISO in the SAME folder as the old one it replaces.
                drive_dir = str((Path(drive_path) / matched[0][0]["relative_path"]).parent)
            else:
                drive_dir = str(Path(drive_path) / target) if target else drive_path
            if rec.get("kind") == "custom":
                filename = info.filename or rec.get("filename_on_drive", "")
            else:
                filename = info.filename
            dst_file = Path(drive_dir) / filename
            old_files = [str(Path(drive_path) / iso["relative_path"])
                         for iso, _v in matched
                         if (Path(drive_path) / iso["relative_path"]).resolve() != dst_file.resolve()]
            # A current ISO plus older versions needs only cleanup. Previously
            # this state was marked current and the stale copies became stuck.
            action = "cleanup" if dst_file.exists() and old_files else "update"
            jobs.append({
                "key": key, "name": self._name_for_key(key),
                "url": info.url, "filename": filename, "sha256": info.sha256,
                "version": info.version,
                "cache_dir": cache_dir, "drive_dir": drive_dir,
                "old_files": old_files,
                "action": action,
            })
        return jobs

    def _on_update_phase(self, index: int, phase: str):
        job = self._update_jobs[index]
        keymap = {"download": "status_downloading", "verify": "status_verifying",
                  "copy": "status_copying", "cleanup": "status_cleanup"}
        self.library.set_status(f"{job['name']} · {self.t(keymap.get(phase, 'status_updated'))}")
        if phase == "download":
            self.log("info", self.t("ev_download").format(
                name=job["name"], ver=job["version"]))

    def _on_update_progress(self, index: int, done: float, total: float, speed: float):
        pct = int(done / total * 100) if total else 0
        overall = int((index + pct / 100) / len(self._update_jobs) * 100)
        self.library.set_progress(
            overall, speed=updater.human_speed(speed) if speed else "")

    def _on_job_done(self, index: int, ok: bool, message: str):
        job = self._update_jobs[index]
        if ok:
            self.log("ok", self.t("ev_updated").format(
                name=job["name"], ver=job["version"]))
            self._store_last_version(job["key"], job["version"])
        elif message == "checksum mismatch":
            self.log("error", self.t("ev_verify_fail").format(name=job["name"]))
        elif message == "stopped":
            self.log("info", self.t("ev_stopped"))
        else:
            self.log("error", self.t("ev_update_fail").format(
                name=job["name"], err=message))

    def _on_update_done(self):
        self._set_busy(False)
        self.library.set_progress(100, self.t("check_done"))
        config.save_settings(self.settings)
        self.rescan()

    # ―― stop ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
    def stop_action(self):
        if self._check_worker and self._check_worker.isRunning():
            self._check_worker.stop()
        if self._update_worker and self._update_worker.isRunning():
            self._update_worker.stop()
        self.library.set_status(self.t("ev_stopped"))

    def delete_image(self, relative_path: str):
        """Delete a scanned ISO only after an explicit confirmation."""
        if self._busy or not self._drive_info or not relative_path:
            return
        root = Path(self._drive_info["mountpoint"]).resolve()
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return
        if candidate.suffix.lower() != ".iso" or not candidate.is_file():
            QMessageBox.warning(self, self.t("app_name"), self.t("warn_image_missing"))
            return
        reply = QMessageBox.question(
            self, self.t("confirm"),
            self.t("confirm_delete_image").format(name=candidate.name),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            candidate.unlink()
        except OSError as e:
            QMessageBox.warning(self, self.t("app_name"), self.t("delete_image_failed").format(err=e))
            return
        self.log("ok", self.t("ev_image_deleted").format(name=candidate.name))
        self.rescan()

    def clear_cache(self):
        """Remove cached download artifacts without deleting an arbitrary folder."""
        if self._busy:
            return
        cache_dir = Path(self.settings.get("cache_dir", config.default_cache_dir()))
        if not cache_dir.is_dir():
            return
        reply = QMessageBox.question(
            self, self.t("confirm"), self.t("confirm_clear_cache"),
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        removed = 0
        for item in cache_dir.iterdir():
            if item.is_file() and item.suffix.lower() in (".iso", ".part"):
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    continue
        self.log("ok", self.t("ev_cache_cleared").format(n=removed))
        QMessageBox.information(self, self.t("app_name"), self.t("cache_cleared").format(n=removed))

    # ―― helpers ―――――――――――――――――――――――――――――――――――――――――――――――――――――――
    def _record_for_key(self, key: str) -> dict | None:
        for rec in self.connected_sources():
            if rec.get("key") == key:
                return rec
        for rec in self.custom_sources():
            if rec.get("key") == key:
                return rec
        return None

    def _name_for_key(self, key: str) -> str:
        rec = self._record_for_key(key)
        return self.source_title(rec) if rec else key

    def _store_last_version(self, key: str, version: str):
        for rec in self.connected_sources():
            if rec.get("key") == key:
                rec["last_version"] = version
                rec["last_checked"] = _now()
                return
        for rec in self.settings.get("custom_sources", []):
            if f"cus:{rec.get('name','custom')}" == key:
                rec["last_version"] = version
                rec["last_checked"] = _now()
                return

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.library.set_busy(busy)

    # ―― activity log ―――――――――――――――――――――――――――――――――――――――――――――――――
    def log(self, level: str, msg: str):
        events = self.settings.setdefault("activity", [])
        events.append({"level": level, "msg": msg, "time": _now()})
        if len(events) > config.MAX_ACTIVITY:
            del events[:-config.MAX_ACTIVITY]
        if self.stack.currentWidget() is self.activity:
            self.activity.refresh()

    def activity_events(self) -> list[dict]:
        return self.settings.get("activity", [])

    def clear_activity(self):
        self.settings["activity"] = []
        config.save_settings(self.settings)
        self.activity.refresh()

    # ―― settings apply ――――――――――――――――――――――――――――――――――――――――――――――――
    def apply_settings(self, new: dict):
        old_lang = self.lang_code
        old_theme = self.theme
        old_label = self.settings.get("ventoy_label")
        self.settings.update(new)
        self.lang_code = new.get("lang", self.lang_code)
        self.theme = new.get("theme", self.theme)
        self.lang = get_lang(self.lang_code)
        config.save_settings(self.settings)
        self._reschedule_auto()
        label_changed = self.settings.get("ventoy_label") != old_label
        ui_changed = self.lang_code != old_lang or self.theme != old_theme
        if ui_changed:
            # Apply the stylesheet immediately, then recreate translated widgets.
            # Clearing first forces Qt to repolish existing widgets on theme swaps.
            QApplication.instance().setStyleSheet("")
            self._apply_theme()
            # Defer so the current Save click handler can finish before its
            # widget tree is replaced (prevents a use-after-free style crash).
            QTimer.singleShot(0, lambda: self._rebuild_ui(rescan=label_changed))
        else:
            if label_changed:
                self.rescan()
            QMessageBox.information(self, self.t("app_name"), self.t("settings_saved"))

    # ―― auto-check ―――――――――――――――――――――――――――――――――――――――――――――――――――
    def _reschedule_auto(self):
        self._auto_timer.stop()
        if self.settings.get("auto_check", True):
            minutes = int(self.settings.get("auto_check_interval_min", 720))
            self._auto_timer.start(max(15, minutes) * 60 * 1000)

    def _auto_tick(self):
        if not self._busy:
            self.start_check()

    # ―― refresh ――――――――――――――――――――――――――――――――――――――――――――――――――――――
    def refresh_all(self):
        for view in (self.library, self.sources, self.activity):
            view.refresh()


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Ventoy ISO Updater")
    window = VentoyUpdaterApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
