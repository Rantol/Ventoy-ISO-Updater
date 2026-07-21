"""Ventoy USB drive detection and scanning (Windows-first).

Drives are identified by their *volume label* (default ``Ventoy``). On
non-Windows platforms the detection functions return empty results so the rest
of the app still imports and runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from iso_parser import parse_iso_filename

# Directories that belong to a booted distro rather than to a user's ISO
# collection - skipped while scanning so we do not treat them as images.
SCAN_IGNORED_DIRS = {
    "grub", "efi", ".disk", "boot", "casper", "isolinux", "syslinux",
    "ventoy", "system volume information", "$recycle.bin",
}


def get_ventoy_drives(label: str) -> list[dict]:
    """Return every mounted volume whose label matches *label*."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        drives: list[dict] = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = f"{letter}:\\"
            buf = ctypes.create_unicode_buffer(256)
            ok = kernel32.GetVolumeInformationW(
                drive_path, buf, 256, None, None, None, None, 0
            )
            if not ok:
                continue
            if buf.value != label:
                continue
            try:
                import psutil
                usage = psutil.disk_usage(drive_path)
                total_gb = round(usage.total / (1024 ** 3), 1)
                free_gb = round(usage.free / (1024 ** 3), 1)
            except Exception:
                total_gb = free_gb = 0.0
            drives.append({
                "letter": letter,
                "mountpoint": drive_path,
                "label": label,
                "total_gb": total_gb,
                "free_gb": free_gb,
            })
        return drives
    except Exception:
        return []


def find_ventoy_path(label: str) -> str | None:
    drives = get_ventoy_drives(label)
    return drives[0]["mountpoint"] if drives else None


def drive_info(label: str) -> dict | None:
    drives = get_ventoy_drives(label)
    return drives[0] if drives else None


def scan_ventoy_drive(label: str) -> list[dict]:
    """Recursively find ``*.iso`` files on the Ventoy drive with metadata."""
    ventoy_path = find_ventoy_path(label)
    if not ventoy_path:
        return []
    base = Path(ventoy_path)
    result: list[dict] = []
    try:
        iterator = base.rglob("*.iso")
    except OSError:
        return []
    for f in iterator:
        try:
            rel = f.relative_to(base)
            if any(part.lower() in SCAN_IGNORED_DIRS for part in rel.parts[:-1]):
                continue
            size_gb = round(f.stat().st_size / (1024 ** 3), 2)
        except OSError:
            continue
        info = parse_iso_filename(f.name)
        result.append({
            "relative_path": str(rel),
            "filename": f.name,
            "size_gb": size_gb,
            "os_type": info.os_type,
            "os_name": info.os_name,
            "version": info.version,
            "edition": info.edition,
            "arch": info.arch,
        })
    result.sort(key=lambda x: x["relative_path"].lower())
    return result


def ventoy_folders(label: str) -> list[str]:
    """Return selectable ISO folders relative to the Ventoy drive root."""
    ventoy_path = find_ventoy_path(label)
    if not ventoy_path:
        return [""]
    base = Path(ventoy_path)
    folders = {""}
    try:
        for folder in base.rglob("*"):
            if not folder.is_dir():
                continue
            rel = folder.relative_to(base)
            if any(part.lower() in SCAN_IGNORED_DIRS for part in rel.parts):
                continue
            folders.add(str(rel))
    except OSError:
        pass
    return sorted(folders, key=lambda item: (item != "", item.lower()))
