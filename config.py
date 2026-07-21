"""Application configuration: load, save, defaults, and migration.

Settings live in ``settings.json`` next to the package. The schema grew over
several versions; :func:`load_settings` transparently migrates older layouts
(``downloads`` / ``isos`` / ``iso_bindings``) into the current one so no user
configuration is ever lost.
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "settings.json"

# How many activity-log entries to keep on disk.
MAX_ACTIVITY = 300


def default_cache_dir() -> str:
    return str(Path.home() / "VentoyISOs")


def default_settings() -> dict:
    return {
        "ventoy_label": "Ventoy",
        "cache_dir": default_cache_dir(),
        "theme": "dark",
        "lang": "ru",
        "connected_sources": [],   # catalog-backed sources
        "custom_sources": [],      # user URL + regex sources
        "display_names": {},       # user labels for library rows
        "auto_check": True,
        "auto_check_interval_min": 720,
        "check_on_startup": True,
        "activity": [],
    }


def _migrate(data: dict) -> dict:
    """Bring an arbitrary on-disk settings dict up to the current schema."""
    base = default_settings()
    for key, val in base.items():
        data.setdefault(key, val)

    # ―― Legacy per-file URL bindings (v3/v4) → custom_sources ――――――――――――――
    legacy = data.pop("iso_bindings", None)
    if legacy:
        existing = {(s.get("target_dir", ""), s.get("filename_on_drive", ""))
                    for s in data["custom_sources"]}
        for rel_path, binding in legacy.items():
            rel = Path(rel_path)
            target_dir = str(rel.parent) if str(rel.parent) not in (".", "") else ""
            filename = rel.name
            key = (target_dir, filename)
            if key in existing:
                continue
            data["custom_sources"].append({
                "name": filename or rel_path,
                "url": binding.get("url", ""),
                "pattern": binding.get("pattern", ""),
                "target_dir": target_dir,
                "filename_on_drive": filename,
                "last_version": "",
                "last_checked": "",
                "auto": True,
            })

    # ―― Even older folder-based "sources" list is obsolete: drop quietly ――――
    old_sources = data.get("sources")
    if isinstance(old_sources, list) and old_sources and \
            all(isinstance(s, dict) and "path" in s for s in old_sources):
        data.pop("sources", None)

    # ―― Very old download lists ―――――――――――――――――――――――――――――――――――――――――
    for old_key in ("isos", "downloads"):
        old = data.pop(old_key, None)
        if not old:
            continue
        for iso in old:
            url = iso.get("url", "")
            if not url:
                continue
            filename = url.split("/")[-1].split("?")[0]
            if not filename.endswith(".iso"):
                filename += ".iso"
            data["custom_sources"].append({
                "name": filename,
                "url": url,
                "pattern": iso.get("pattern", ""),
                "target_dir": "",
                "filename_on_drive": filename,
                "last_version": "",
                "last_checked": "",
                "auto": True,
            })

    if not data.get("cache_dir"):
        data["cache_dir"] = default_cache_dir()

    # Keep one record per manual source key. Older versions could create
    # duplicate keys after a source was renamed.
    unique_custom = {}
    for source in data.get("custom_sources", []):
        key = source.get("key") or f"cus:{source.get('name', 'custom')}"
        source["key"] = key
        unique_custom[key] = source
    data["custom_sources"] = list(unique_custom.values())
    return data


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return default_settings()
        return _migrate(data)
    return default_settings()


def save_settings(data: dict) -> None:
    # Cap the activity log before persisting.
    activity = data.get("activity")
    if isinstance(activity, list) and len(activity) > MAX_ACTIVITY:
        data["activity"] = activity[-MAX_ACTIVITY:]
    tmp = SETTINGS_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(SETTINGS_FILE)
