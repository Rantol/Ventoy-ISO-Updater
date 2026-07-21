"""Curated catalog of connectable ISO sources.

Each distro declares *how* its latest version is discovered via a ``resolver``
kind (implemented in :mod:`updater`):

* ``json_api``      - fetch a JSON endpoint, filter by variant/arch (Fedora).
* ``current_dir``   - read a ``current``/``latest`` symlink directory listing
                      and parse the ISO filename (Debian, Arch, Kali).
* ``release_index`` - read a releases index, pick the highest version folder,
                      then build the ISO URL from a template (Ubuntu, Mint...).
* ``popos_api``     - System76 build API (Pop!_OS).

Everything here is plain data; adding a distro is a dict, not code. Editions may
override ``slug`` (URL piece), ``file_re``/``match_re`` (filename regex, with
``{arch}``/``{slug}``/ctx placeholders) and ``ctx`` (extra template keys).
"""

from __future__ import annotations

# category -> ordering weight (linux first, then utilities)
CATEGORIES = {"linux": 0, "utility": 1}


CATALOG: list[dict] = [
    {
        "id": "ubuntu",
        "name": "Ubuntu",
        "category": "linux",
        "color": "#E95420",
        "homepage": "https://ubuntu.com",
        "desc": {"ru": "Популярный дистрибутив на базе Debian.",
                 "en": "Popular Debian-based distribution."},
        "resolver": "release_index",
        "archs": ["amd64"],
        "resolver_cfg": {
            "index_url": "https://releases.ubuntu.com/",
            "version_re": r"(\d+\.\d+(?:\.\d+)?)/",
            "iso_template": "https://releases.ubuntu.com/{ver}/ubuntu-{ver}-{slug}-{arch}.iso",
        },
        "editions": [
            {"id": "desktop", "label": {"ru": "Рабочий стол", "en": "Desktop"},
             "slug": "desktop",
             "match_re": r"ubuntu-([\d.]+)-desktop-{arch}\.iso"},
            {"id": "server", "label": {"ru": "Сервер", "en": "Server"},
             "slug": "live-server",
             "match_re": r"ubuntu-([\d.]+)-live-server-{arch}\.iso"},
        ],
    },
    {
        "id": "debian",
        "name": "Debian",
        "category": "linux",
        "color": "#A80030",
        "homepage": "https://debian.org",
        "desc": {"ru": "Стабильный универсальный дистрибутив.",
                 "en": "Rock-solid universal distribution."},
        "resolver": "current_dir",
        "archs": ["amd64", "arm64"],
        "resolver_cfg": {
            "dir_template": "https://cdimage.debian.org/debian-cd/current/{arch}/{isodir}/",
        },
        "editions": [
            {"id": "netinst", "label": {"ru": "Netinst", "en": "Netinst"},
             "ctx": {"isodir": "iso-cd"},
             "file_re": r"debian-([\d.]+)-{arch}-netinst\.iso"},
            {"id": "dvd", "label": {"ru": "DVD", "en": "DVD"},
             "ctx": {"isodir": "iso-dvd"},
             "file_re": r"debian-([\d.]+)-{arch}-DVD-1\.iso"},
        ],
    },
    {
        "id": "linuxmint",
        "name": "Linux Mint",
        "category": "linux",
        "color": "#87CF3E",
        "homepage": "https://linuxmint.com",
        "desc": {"ru": "Дружелюбный дистрибутив для новичков.",
                 "en": "Friendly, beginner-oriented distribution."},
        "resolver": "release_index",
        "archs": ["x86_64"],
        "resolver_cfg": {
            "index_url": "https://mirrors.edge.kernel.org/linuxmint/stable/",
            "version_re": r"(\d+(?:\.\d+)?)/",
            "iso_template": "https://mirrors.edge.kernel.org/linuxmint/stable/{ver}/linuxmint-{ver}-{slug}-64bit.iso",
        },
        "editions": [
            {"id": "cinnamon", "label": {"ru": "Cinnamon", "en": "Cinnamon"},
             "slug": "cinnamon", "match_re": r"linuxmint-([\d.]+)-cinnamon-64bit\.iso"},
            {"id": "xfce", "label": {"ru": "Xfce", "en": "Xfce"},
             "slug": "xfce", "match_re": r"linuxmint-([\d.]+)-xfce-64bit\.iso"},
            {"id": "mate", "label": {"ru": "MATE", "en": "MATE"},
             "slug": "mate", "match_re": r"linuxmint-([\d.]+)-mate-64bit\.iso"},
        ],
    },
    {
        "id": "fedora",
        "name": "Fedora",
        "category": "linux",
        "color": "#51A2DA",
        "homepage": "https://fedoraproject.org",
        "desc": {"ru": "Передовой дистрибутив от Red Hat.",
                 "en": "Leading-edge distribution by Red Hat."},
        "resolver": "json_api",
        "archs": ["x86_64", "aarch64"],
        "resolver_cfg": {
            "json_url": "https://fedoraproject.org/releases.json",
        },
        "editions": [
            {"id": "workstation", "label": {"ru": "Workstation", "en": "Workstation"},
             "variant": "Workstation", "name_contains": "Workstation-Live",
             "match_re": r"Fedora-Workstation-Live-.*(\d\d)-.*\.iso"},
            {"id": "kde", "label": {"ru": "KDE Plasma", "en": "KDE Plasma"},
             "variant": "KDE", "name_contains": "KDE-Desktop-Live",
             "match_re": r"Fedora-KDE-Desktop-Live-.*(\d\d)-.*\.iso"},
            {"id": "server", "label": {"ru": "Сервер", "en": "Server"},
             "variant": "Server", "name_contains": "Server-dvd",
             "match_re": r"Fedora-Server-dvd-.*(\d\d)-.*\.iso"},
        ],
    },
    {
        "id": "arch",
        "name": "Arch Linux",
        "category": "linux",
        "color": "#1793D1",
        "homepage": "https://archlinux.org",
        "desc": {"ru": "Роллинг-релиз для опытных пользователей.",
                 "en": "Rolling-release for advanced users."},
        "resolver": "arch_json",
        "archs": ["x86_64"],
        "resolver_cfg": {
            "json_url": "https://archlinux.org/releng/releases/json/",
            "iso_template": "https://geo.mirror.pkgbuild.com/iso/{ver}/archlinux-{ver}-{arch}.iso",
        },
        "editions": [
            {"id": "iso", "label": {"ru": "Установочный ISO", "en": "Install ISO"},
             "file_re": r"archlinux-(\d{4}\.\d{2}\.\d{2})-{arch}\.iso"},
        ],
    },
    {
        "id": "kali",
        "name": "Kali Linux",
        "category": "linux",
        "color": "#557C94",
        "homepage": "https://kali.org",
        "desc": {"ru": "Дистрибутив для пентеста и безопасности.",
                 "en": "Penetration testing & security distro."},
        "resolver": "current_dir",
        "archs": ["amd64"],
        "resolver_cfg": {
            "dir_template": "https://cdimage.kali.org/current/",
        },
        "editions": [
            {"id": "installer", "label": {"ru": "Установщик", "en": "Installer"},
             "slug": "installer",
             "file_re": r"kali-linux-([\d.]+[a-z]?)-installer-{arch}\.iso"},
            {"id": "live", "label": {"ru": "Live", "en": "Live"},
             "slug": "live", "available": False,
             "file_re": r"kali-linux-([\d.]+[a-z]?)-live-{arch}\.iso"},
        ],
    },
    {
        "id": "popos",
        "name": "Pop!_OS",
        "category": "linux",
        "color": "#48B9C7",
        "homepage": "https://pop.system76.com",
        "desc": {"ru": "Дистрибутив от System76 на базе Ubuntu.",
                 "en": "System76's Ubuntu-based distribution."},
        "resolver": "popos_api",
        "archs": ["amd64"],
        "resolver_cfg": {
            "api_template": "https://api.pop-os.org/builds/{release}/{variant}",
        },
        "editions": [
            {"id": "2404-intel", "label": {"ru": "24.04 Intel/AMD", "en": "24.04 Intel/AMD"},
             "ctx": {"release": "24.04", "variant": "intel"},
             "match_re": r"pop-os_.*_intel_.*\.iso"},
            {"id": "2404-nvidia", "label": {"ru": "24.04 NVIDIA", "en": "24.04 NVIDIA"},
             "ctx": {"release": "24.04", "variant": "nvidia"},
             "match_re": r"pop-os_.*_nvidia_.*\.iso"},
        ],
    },
    {
        "id": "opensuse",
        "name": "openSUSE Leap",
        "category": "linux",
        "color": "#73BA25",
        "homepage": "https://opensuse.org",
        "desc": {"ru": "Стабильный дистрибутив от SUSE.",
                 "en": "Stable distribution by SUSE."},
        "resolver": "release_index",
        "archs": ["x86_64"],
        "resolver_cfg": {
            "index_url": "https://download.opensuse.org/distribution/leap/",
            "version_re": r"(\d+\.\d+)/",
            "version_allow_re": r"^(1[5-9]|[23]\d)\.",
            "iso_template": "https://download.opensuse.org/distribution/leap/{ver}/iso/openSUSE-Leap-{ver}-DVD-{arch}-Current.iso",
        },
        "editions": [
            {"id": "dvd", "label": {"ru": "DVD", "en": "DVD"},
             "match_re": r"openSUSE-Leap-([\d.]+)-DVD-{arch}.*\.iso"},
        ],
    },
    {
        "id": "rocky",
        "name": "Rocky Linux",
        "category": "linux",
        "color": "#10B981",
        "homepage": "https://rockylinux.org",
        "desc": {"ru": "Корпоративный клон RHEL.",
                 "en": "Enterprise RHEL-compatible distro."},
        "resolver": "current_dir",
        "archs": ["x86_64"],
        "resolver_cfg": {
            "dir_template": "https://download.rockylinux.org/pub/rocky/{major}/isos/{arch}/",
        },
        "editions": [
            {"id": "9-minimal", "label": {"ru": "9 Minimal", "en": "9 Minimal"},
             "ctx": {"major": "9"},
             "file_re": r"Rocky-([\d.]+)-{arch}-minimal\.iso"},
            {"id": "10-minimal", "label": {"ru": "10 Minimal", "en": "10 Minimal"},
             "ctx": {"major": "10"},
             "file_re": r"Rocky-([\d.]+)-{arch}-minimal\.iso"},
        ],
    },
]

# ―― Accessors ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

_BY_ID = {d["id"]: d for d in CATALOG}


def all_distros() -> list[dict]:
    return sorted(CATALOG, key=lambda d: (CATEGORIES.get(d["category"], 9), d["name"].lower()))


def get_distro(distro_id: str) -> dict | None:
    return _BY_ID.get(distro_id)


def get_edition(distro: dict, edition_id: str) -> dict | None:
    for ed in distro.get("editions", []):
        if ed["id"] == edition_id:
            return ed
    return distro.get("editions", [None])[0]


def available_editions(distro: dict) -> list[dict]:
    """Editions currently backed by a downloadable ISO source."""
    return [edition for edition in distro.get("editions", [])
            if edition.get("available", True)]


def edition_label(edition: dict, lang: str) -> str:
    lbl = edition.get("label", {})
    if isinstance(lbl, dict):
        return lbl.get(lang) or lbl.get("en") or edition.get("id", "")
    return str(lbl)


def distro_desc(distro: dict, lang: str) -> str:
    d = distro.get("desc", {})
    return d.get(lang) or d.get("en") or ""
