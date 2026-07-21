"""Parse ISO filenames to extract OS type, name, version, and edition."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class IsoInfo:
    filename: str
    os_type: str       # windows, linux, other
    os_name: str       # Windows 11, Ubuntu, Fedora, …
    version: str       # 23H2, 24.04, 39, …
    edition: str       # Pro, Home, Server, …
    arch: str          # x64, arm64, …
    lang: str          # en-US, ru-RU, …
    raw_label: str     # cleaned-up display name


# ── Patterns ──────────────────────────────────────────────────────────────────

_WIN_PATTERNS = [
    # Windows.11.Pro.23H2.x64.en-US
    re.compile(
        r"windows[\s.]+(?P<ver>\d+)[\s.]+(?P<edition>home|pro|education|enterprise|ltsc|iot)"
        r"[\s.]+(?P<build>\d{2}H\d{1,2})"
        r"(?:[\s.]+(?P<arch>x64|arm64))?"
        r"(?:[\s.]+(?P<lang>[a-z]{2}-[A-Z]{2}))?",
        re.I,
    ),
    # Windows 11 23H2 x64 en-US
    re.compile(
        r"windows\s+(?P<ver>\d+)\s+(?P<build>\d{2}H\d{1,2})"
        r"(?:\s+(?P<arch>x64|arm64))?"
        r"(?:\s+(?P<lang>[a-z]{2}-[A-Z]{2}))?",
        re.I,
    ),
    # Windows 10 22H2 Pro x64
    re.compile(
        r"windows\s+(?P<ver>\d+)\s+(?P<build>\d{2}H\d{1,2})"
        r"(?:\s+(?P<edition>home|pro|education|enterprise|ltsc|iot))?"
        r"(?:\s+(?P<arch>x64|arm64))?"
        r"(?:\s+(?P<lang>[a-z]{2}-[A-Z]{2}))?",
        re.I,
    ),
    # Windows.Server.2022.Standard.x64
    re.compile(
        r"windows[\s.]*(?:server|srv)[\s.]+(?P<ver>\d{4})"
        r"(?:[\s.]+(?P<edition>standard|datacenter|essential))?"
        r"(?:[\s.]+(?P<arch>x64|arm64))?"
        r"(?:[\s.]+(?P<lang>[a-z]{2}-[A-Z]{2}))?",
        re.I,
    ),
]

_LINUX_PATTERNS = [
    # Manjaro-KDE-24.0.2-linux64.iso
    re.compile(
        r"(?P<name>manjaro)"
        r"[\s_-]+(?P<variant>kde|gnome|xfce|cinamon)"
        r"[\s_-]+(?P<ver>[\d]+(?:\.[\d]+)*)"
        r"(?:[\s_-]+(?P<arch>linux64|x64|x86_64|amd64))?",
        re.I,
    ),
    # openSUSE.Leap.15.5.x86_64.iso
    re.compile(
        r"(?P<name>opensuse)"
        r"[\s._-]+(?P<variant>leap|tumbleweed)"
        r"[\s._-]+(?P<ver>[\d]+(?:\.[\d]+)*)"
        r"(?:[\s._-]+(?P<arch>x64|x86_64|amd64))?",
        re.I,
    ),
    # Kali-Linux-2024.1-installer-amd64.iso
    re.compile(
        r"(?P<name>kali)"
        r"(?:[\s_-]+linux)?"
        r"[\s_-]+(?P<ver>[\d]+(?:\.[\d]+)*)"
        r"(?:[\s_-]+(?P<variant>installer|live|netinstall))?"
        r"(?:[\s_-]+(?P<arch>x64|x86_64|amd64|arm64))?",
        re.I,
    ),
    # Ubuntu 24.04.2 LTS Desktop x64
    re.compile(
        r"(?P<name>ubuntu|debian|linux\s*mint|opensuse|suse|centos|almalinux|rocky|pop!\s*os|zorin|elementary|parrot)"
        r"[\s._-]*(?P<ver>[\d]+(?:\.[\d]+)*)?"
        r"(?:[\s._-]*(?P<lts>lts))?"
        r"(?:[\s._-]+(?P<variant>desktop|server|minimal|netinstall|live|gnome|kde|xfce|cinnamon|mate))?"
        r"(?:[\s._-]+(?P<arch>x64|x86_64|amd64|i386|aarch64|arm64))?",
        re.I,
    ),
    # Archlinux-2024.01.01-x86_64.iso
    re.compile(
        r"(?P<name>arch\s*linux)"
        r"[\s._-]*(?P<ver>[\d]+(?:\.[\d]+)*)?"
        r"(?:[\s._-]+(?P<arch>x64|x86_64|amd64|i386|aarch64|arm64))?",
        re.I,
    ),
    # Fedora-Workstation-Live-39-1.5
    re.compile(
        r"(?P<name>fedora)"
        r"[\s_-]+(?P<variant>workstation|server|cloud|spin)"
        r"(?:[\s_-]+(?:base|live))?"
        r"[\s_-]+(?P<ver>\d+)"
        r"(?:[\s_-]+(?P<extra>[\d.]+))?",
        re.I,
    ),
]


def _clean(name: str) -> str:
    """Replace underscores and dashes with spaces, preserve dots in version numbers."""
    # First, protect version-like patterns (e.g., 24.04.2)
    name = re.sub(r"(\d+)\.(\d+(?:\.\d+)*)", r"\1.\2", name)
    # Replace underscores and dashes with spaces
    name = re.sub(r"[_-]", " ", name)
    # Replace dots that are not part of version numbers
    name = re.sub(r"(?<!\d)\.(?!\d)", " ", name)
    # Collapse multiple spaces
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


def parse_iso_filename(filename: str) -> IsoInfo:
    """Best-effort extraction of metadata from an ISO filename."""
    stem = Path(filename).stem if "/" in filename or "\\" in filename else filename.rsplit(".", 1)[0]
    cleaned = _clean(stem)

    os_type = "other"
    os_name = ""
    version = ""
    edition = ""
    arch = ""
    lang = ""

    # ── Windows ───────────────────────────────────────────────────────────────
    for pat in _WIN_PATTERNS:
        m = pat.search(cleaned)
        if m:
            os_type = "windows"
            g = m.groupdict()
            os_name = "Windows Server" if "server" in cleaned.lower() else "Windows"
            version = g.get("build") or g.get("ver") or ""
            edition = (g.get("edition") or "").capitalize()
            arch = (g.get("arch") or "x64").upper()
            lang = g.get("lang") or ""
            break

    # ── Linux ─────────────────────────────────────────────────────────────────
    if os_type == "other":
        for pat in _LINUX_PATTERNS:
            m = pat.search(cleaned)
            if m:
                os_type = "linux"
                g = m.groupdict()
                os_name = (g.get("name") or "").title()
                version = (g.get("ver") or "").strip()
                if g.get("lts"):
                    version += " LTS"
                edition = (g.get("variant") or "").capitalize()
                arch = (g.get("arch") or "")
                if arch.lower() in ("x86_64", "amd64", "linux64"):
                    arch = "x64"
                elif arch.lower() in ("aarch64",):
                    arch = "arm64"
                lang = g.get("lang") or ""
                break

    # ── Fallback label ────────────────────────────────────────────────────────
    parts = [os_name or cleaned.split()[0].title()]
    if version:
        parts.append(version)
    if edition:
        parts.append(edition)
    if arch:
        parts.append(arch)
    if lang:
        parts.append(lang)
    raw_label = " ".join(parts)

    return IsoInfo(
        filename=filename,
        os_type=os_type,
        os_name=os_name or cleaned.split()[0].title(),
        version=version,
        edition=edition,
        arch=arch,
        lang=lang,
        raw_label=raw_label,
    )


# ── Convenience ───────────────────────────────────────────────────────────────

from pathlib import Path  # noqa: E402


def parse_iso_files(directory: str) -> list[IsoInfo]:
    """Return parsed info for every .iso in *directory*."""
    p = Path(directory)
    if not p.is_dir():
        return []
    return sorted(
        (parse_iso_filename(f.name) for f in p.glob("*.iso")),
        key=lambda x: (x.os_name, x.version, x.edition),
    )
