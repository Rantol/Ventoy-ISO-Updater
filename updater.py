"""Resolve the latest ISO for a catalog entry, and download/copy workers.

The module has two layers:

* Pure functions (``resolve_latest`` and the ``_resolve_*`` helpers) that hit
  the network and return a :class:`LatestInfo`. These are import-safe without a
  running Qt application and are exercised by ``python -m updater --selftest``.
* ``QThread`` workers (:class:`CheckWorker`, :class:`UpdateWorker`) that drive
  the UI without blocking it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

from PySide6.QtCore import QThread, Signal

import catalog

USER_AGENT = "VentoyISOUpdater/1.0 (+https://ventoy.net)"
NET_TIMEOUT = 20


# ―― Data ――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

@dataclass
class LatestInfo:
    version: str = ""
    url: str = ""
    filename: str = ""
    sha256: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.url) and not self.error


# ―― Network helpers ―――――――――――――――――――――――――――――――――――――――――――――――――――――――

def _open(url: str, timeout: int = NET_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_text(url: str) -> str:
    with _open(url) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_json(url: str):
    with _open(url) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def url_exists(url: str) -> bool:
    """HEAD (falling back to a ranged GET) to check a URL resolves to a file."""
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as resp:
            return 200 <= resp.status < 400
    except Exception:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as resp:
                return 200 <= resp.status < 400
        except Exception:
            return False


def fetch_page_links(url: str) -> list[str]:
    try:
        html = fetch_text(url)
    except Exception:
        return []
    return re.findall(r'href=["\']([^"\']+)["\']', html)


# ―― Version helpers ――――――――――――――――――――――――――――――――――――――――――――――――――――――

def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.split(r"[^0-9]+", v or "") if p.isdigit())


def is_newer(latest: str, current: str) -> bool:
    """True when *latest* is a strictly newer version than *current*."""
    if not current:
        return bool(latest)
    if not latest:
        return False
    return parse_version(latest) > parse_version(current)


# ―― Template / regex placeholder substitution ――――――――――――――――――――――――――――

def _fill(text: str, ctx: dict) -> str:
    for key, val in ctx.items():
        text = text.replace("{" + key + "}", str(val))
    return text


def build_ctx(distro: dict, edition: dict, arch: str, ver: str = "") -> dict:
    ctx = {
        "arch": arch,
        "slug": edition.get("slug", ""),
        "edition": edition.get("id", ""),
        "ver": ver,
        "major": ver.split(".")[0] if ver else "",
    }
    ctx.update(edition.get("ctx", {}))   # edition ctx can override (e.g. major)
    if ver:
        ctx["ver"] = ver
        ctx["major"] = ctx.get("major") or ver.split(".")[0]
    return ctx


# ―― Resolvers ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

def _resolve_current_dir(distro, edition, arch) -> LatestInfo:
    cfg = distro["resolver_cfg"]
    ctx = build_ctx(distro, edition, arch)
    dir_url = _fill(cfg["dir_template"], ctx)
    file_re = edition.get("file_re") or cfg.get("file_re", "")
    if not file_re:
        return LatestInfo(error="no file_re configured")
    pat = re.compile(_fill(file_re, ctx), re.I)
    links = fetch_page_links(dir_url)
    best_ver, best_name, best_key = "", "", ()
    for link in links:
        name = link.rstrip("/").split("/")[-1]
        # Directory listings also contain .torrent, checksum, and signature
        # sidecars. A partial regex match would select e.g. ``image.iso.torrent``.
        if not name.lower().endswith(".iso"):
            continue
        m = pat.fullmatch(name)
        if not m:
            continue
        ver = m.group(1) if m.groups() else name
        key = parse_version(ver)
        if not best_name or key > best_key:
            best_ver, best_name, best_key = ver, name, key
    if not best_name:
        return LatestInfo(error=f"no matching ISO in {dir_url}")
    return LatestInfo(version=best_ver, url=urljoin(dir_url, best_name), filename=best_name)


def _resolve_release_index(distro, edition, arch) -> LatestInfo:
    cfg = distro["resolver_cfg"]
    vpat = re.compile(cfg["version_re"])
    allow = cfg.get("version_allow_re")
    allow_re = re.compile(allow) if allow else None
    links = fetch_page_links(cfg["index_url"])
    versions = set()
    for link in links:
        m = vpat.search(link)
        if not m:
            continue
        ver = m.group(1)
        if allow_re and not allow_re.search(ver):
            continue
        versions.add(ver)
    if not versions:
        return LatestInfo(error=f"no versions in {cfg['index_url']}")
    # Try newest first; fall back if the templated ISO URL does not exist yet.
    for ver in sorted(versions, key=parse_version, reverse=True):
        ctx = build_ctx(distro, edition, arch, ver=ver)
        url = _fill(cfg["iso_template"], ctx)
        if url_exists(url):
            return LatestInfo(version=ver, url=url,
                              filename=url.split("/")[-1].split("?")[0])
    # None verified: return newest templated URL as a best effort.
    ver = max(versions, key=parse_version)
    ctx = build_ctx(distro, edition, arch, ver=ver)
    url = _fill(cfg["iso_template"], ctx)
    return LatestInfo(version=ver, url=url,
                      filename=url.split("/")[-1].split("?")[0])


def _resolve_json_api(distro, edition, arch) -> LatestInfo:
    cfg = distro["resolver_cfg"]
    data = fetch_json(cfg["json_url"])
    if not isinstance(data, list):
        return LatestInfo(error="unexpected JSON shape")
    variant = edition.get("variant")
    name_contains = edition.get("name_contains", "")
    best = None
    best_key = ()
    for item in data:
        if item.get("arch") != arch:
            continue
        if variant and item.get("variant") != variant:
            continue
        link = item.get("link", "")
        if not link.endswith(".iso"):
            continue
        if name_contains and name_contains not in link:
            continue
        ver = str(item.get("version", ""))
        key = parse_version(ver)
        if best is None or key > best_key:
            best = (ver, link, item.get("sha256", ""))
            best_key = key
    if not best:
        return LatestInfo(error="no matching entry in JSON")
    ver, link, sha = best
    return LatestInfo(version=ver, url=link,
                      filename=link.split("/")[-1].split("?")[0], sha256=sha)


def _resolve_popos(distro, edition, arch) -> LatestInfo:
    cfg = distro["resolver_cfg"]
    ctx = build_ctx(distro, edition, arch)
    api = _fill(cfg["api_template"], ctx)
    j = fetch_json(api)
    if not isinstance(j, dict) or not j.get("url"):
        return LatestInfo(error="unexpected Pop!_OS API response")
    release = str(ctx.get("release", ""))
    build = j.get("build")
    ver = f"{release}.{build}" if build is not None else release
    url = j["url"]
    return LatestInfo(version=ver, url=url,
                      filename=url.split("/")[-1].split("?")[0],
                      sha256=j.get("sha_sum", ""))


def _resolve_arch_json(distro, edition, arch) -> LatestInfo:
    cfg = distro["resolver_cfg"]
    data = fetch_json(cfg["json_url"])
    ver = str(data.get("latest_version", ""))
    sha = ""
    for rel in data.get("releases", []):
        if str(rel.get("version")) == ver:
            sha = rel.get("sha256_sum", "") or ""
            break
    if not ver:
        return LatestInfo(error="no latest_version in Arch JSON")
    ctx = build_ctx(distro, edition, arch, ver=ver)
    url = _fill(cfg["iso_template"], ctx)
    return LatestInfo(version=ver, url=url,
                      filename=url.split("/")[-1].split("?")[0], sha256=sha)


_RESOLVERS = {
    "current_dir": _resolve_current_dir,
    "release_index": _resolve_release_index,
    "json_api": _resolve_json_api,
    "popos_api": _resolve_popos,
    "arch_json": _resolve_arch_json,
}


def resolve_latest(distro: dict, edition: dict, arch: str) -> LatestInfo:
    if not edition or not edition.get("available", True):
        return LatestInfo(error="source is currently unavailable")
    fn = _RESOLVERS.get(distro.get("resolver", ""))
    if not fn:
        return LatestInfo(error=f"unknown resolver '{distro.get('resolver')}'")
    try:
        return fn(distro, edition, arch)
    except urllib.error.URLError as e:
        return LatestInfo(error=f"network: {e.reason}")
    except Exception as e:  # pragma: no cover - defensive
        return LatestInfo(error=f"{type(e).__name__}: {e}")


def _guess_version_from_filename(filename: str) -> str:
    """Try to extract a version-like string from an ISO filename."""
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    m = re.search(r"(\d{6,8})", base)
    if m:
        return m.group(1)
    m = re.search(r"(\d+\.\d+(?:\.\d+)*)", base)
    if m:
        return m.group(1)
    m = re.search(r"(\d{4}\.\d{2})", base)
    if m:
        return m.group(1)
    return ""


def resolve_custom(url: str, pattern: str) -> LatestInfo:
    """Custom source: direct ISO URL + optional version regex.

    When *pattern* is empty the version is guessed from the ISO filename.
    """
    filename = url.split("/")[-1].split("?")[0]
    candidates = []
    if filename.lower().endswith(".iso"):
        candidates.append((url, filename))
    else:
        for link in fetch_page_links(url):
            full = link if link.startswith("http") else urljoin(url, link)
            name = full.split("/")[-1].split("?")[0]
            if name.lower().endswith(".iso"):
                candidates.append((full, name))
    if not candidates:
        return LatestInfo(error="no ISO link found", url=url)

    if not pattern:
        selected = max(candidates, key=lambda item: parse_version(
            _guess_version_from_filename(item[1])))
        return LatestInfo(version=_guess_version_from_filename(selected[1]),
                          url=selected[0], filename=selected[1])
    versions = []
    for full, name in candidates:
        m = re.search(pattern, full)
        if m:
            versions.append((m.group(1) if m.lastindex else m.group(0), full, name))
    if not versions:
        m = re.search(pattern, url)
        ver = (m.group(1) if m and m.lastindex else (m.group(0) if m else ""))
        selected_url, selected_name = candidates[0]
    else:
        ver, selected_url, selected_name = max(versions, key=lambda item: parse_version(item[0]))
    return LatestInfo(version=ver, url=selected_url, filename=selected_name)


def custom_drive_match_regex(filename: str, explicit: str = ""):
    """Compile a custom source's drive mask, guessing version slots if needed."""
    raw = explicit.strip()
    if not raw and filename:
        stem = filename.rsplit(".", 1)[0]
        parts = re.split(r"(\d+(?:\.\d+)+|\d{6,8})", stem)
        raw = "".join("([\\d.]+)" if part.isdigit() or re.fullmatch(
            r"\d+(?:\.\d+)+", part) else re.escape(part) for part in parts)
        raw += r"\.iso"
    if not raw:
        return None
    try:
        return re.compile(raw, re.I)
    except re.error:
        return None


# ―― Drive matching ―――――――――――――――――――――――――――――――――――――――――――――――――――――――

def drive_match_regex(distro, edition, arch):
    raw = edition.get("match_re") or edition.get("file_re")
    if not raw:
        return None
    try:
        return re.compile(_fill(raw, build_ctx(distro, edition, arch)), re.I)
    except re.error:
        return None


def find_installed(distro, edition, arch, drive_path: str, target_dir: str) -> list[tuple[Path, str]]:
    """Return (path, version) for files in *target_dir* matching this edition."""
    base = Path(drive_path) / target_dir if target_dir else Path(drive_path)
    if not base.is_dir():
        return []
    rx = drive_match_regex(distro, edition, arch)
    out: list[tuple[Path, str]] = []
    try:
        for f in base.glob("*.iso"):
            if rx:
                m = rx.search(f.name)
                if not m:
                    continue
                ver = m.group(1) if m.groups() else ""
            else:
                ver = ""
            out.append((f, ver))
    except OSError:
        return []
    return out


# ―― Formatting helpers ―――――――――――――――――――――――――――――――――――――――――――――――――――

def human_size(num_bytes: float) -> str:
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def human_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec >= 1024 * 1024:
        return f"{bytes_per_sec / 1024 / 1024:.1f} MB/s"
    return f"{bytes_per_sec / 1024:.0f} KB/s"


# ―― Workers ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――

class CheckWorker(QThread):
    """Resolve latest versions for a list of specs off the UI thread.

    Each spec is a dict: ``{"key", "kind": "catalog"|"custom", ...}``.
    Emits ``checked(key, LatestInfo)`` per spec.
    """

    checked = Signal(str, object)
    progress = Signal(int, int)   # done, total

    def __init__(self, specs: list[dict]):
        super().__init__()
        self.specs = specs
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.specs)
        for i, spec in enumerate(self.specs):
            if self._stop:
                break
            self.progress.emit(i, total)
            if spec.get("kind") == "custom":
                info = resolve_custom(spec.get("url", ""), spec.get("pattern", ""))
            else:
                distro = catalog.get_distro(spec.get("distro", ""))
                if not distro:
                    info = LatestInfo(error="unknown distro")
                else:
                    edition = catalog.get_edition(distro, spec.get("edition", ""))
                    info = resolve_latest(distro, edition, spec.get("arch", ""))
            self.checked.emit(spec.get("key", ""), info)
        self.progress.emit(total, total)


class UpdateWorker(QThread):
    """Download (verify) then copy a list of jobs to the Ventoy drive.

    Each job dict: ``{key, name, url, filename, sha256, cache_dir,
    drive_dir, old_files:[Path]}``.
    """

    phase = Signal(int, str)                    # index, phase
    progress = Signal(int, float, float, float)  # index, done, total, speed
    job_done = Signal(int, bool, str)           # index, ok, message
    done = Signal()

    CHUNK = 1024 * 256
    COPY_BUF = 4 * 1024 * 1024

    def __init__(self, jobs: list[dict]):
        super().__init__()
        self.jobs = jobs
        self._stop = False

    def stop(self):
        self._stop = True

    # -- steps -----------------------------------------------------------
    def _download(self, i: int, url: str, dest: Path) -> bool:
        self.phase.emit(i, "download")
        try:
            with _open(url, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                done = 0
                start = time.time()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as fout:
                    while not self._stop:
                        chunk = resp.read(self.CHUNK)
                        if not chunk:
                            break
                        fout.write(chunk)
                        done += len(chunk)
                        elapsed = time.time() - start
                        speed = done / elapsed if elapsed > 0 else 0
                        self.progress.emit(i, done, total, speed)
                if total and done != total:
                    raise OSError(f"incomplete download ({done}/{total} bytes)")
        except Exception as e:
            dest.unlink(missing_ok=True)
            self.job_done.emit(i, False, f"download failed: {e}")
            return False
        if self._stop:
            dest.unlink(missing_ok=True)
            return False
        return True

    def _verify(self, i: int, path: Path, sha256: str) -> bool:
        if not sha256:
            return True
        self.phase.emit(i, "verify")
        try:
            h = hashlib.sha256()
            size = path.stat().st_size or 1
            done = 0
            with open(path, "rb") as f:
                while not self._stop:
                    buf = f.read(self.COPY_BUF)
                    if not buf:
                        break
                    h.update(buf)
                    done += len(buf)
                    self.progress.emit(i, done, size, 0)
        except OSError as e:
            self.job_done.emit(i, False, f"checksum verification failed: {e}")
            return False
        if self._stop:
            return False
        if h.hexdigest().lower() != sha256.lower():
            self.job_done.emit(i, False, "checksum mismatch")
            return False
        return True

    def _copy(self, i: int, src: Path, dst: Path) -> bool:
        self.phase.emit(i, "copy")
        partial = dst.with_name(f"{dst.name}.part")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            size = src.stat().st_size or 1
            done = 0
            start = time.time()
            partial.unlink(missing_ok=True)
            with open(src, "rb") as fin, open(partial, "wb") as fout:
                while not self._stop:
                    buf = fin.read(self.COPY_BUF)
                    if not buf:
                        break
                    fout.write(buf)
                    done += len(buf)
                    elapsed = time.time() - start
                    speed = done / elapsed if elapsed > 0 else 0
                    self.progress.emit(i, done, size, speed)
                fout.flush()
                # Do not remove an existing ISO until the complete replacement
                # has reached the Ventoy drive.
                if done != size:
                    raise OSError("incomplete copy")
            partial.replace(dst)
        except Exception as e:
            partial.unlink(missing_ok=True)
            self.job_done.emit(i, False, f"copy failed: {e}")
            return False
        if self._stop:
            partial.unlink(missing_ok=True)
            return False
        return True

    def _remove_old_files(self, job: dict, dst_file: Path) -> str:
        """Remove superseded source-matched ISOs after a successful replacement."""
        failed_removals = []
        for old in job.get("old_files", []):
            try:
                old_path = Path(old)
                if old_path.exists() and old_path.resolve() != dst_file.resolve():
                    old_path.unlink()
            except OSError as e:
                failed_removals.append(f"{Path(old).name}: {e}")
        return "; ".join(failed_removals)

    def run(self):
        for i, job in enumerate(self.jobs):
            if self._stop:
                self.job_done.emit(i, False, "stopped")
                continue
            cache_dir = Path(job["cache_dir"])
            dest = cache_dir / job["filename"]
            dst_file = Path(job["drive_dir"]) / job["filename"]
            if job.get("action") == "cleanup":
                self.phase.emit(i, "cleanup")
                failed_removals = self._remove_old_files(job, dst_file)
                if failed_removals:
                    self.job_done.emit(i, False, "old ISO was not removed: " + failed_removals)
                else:
                    self.job_done.emit(i, True, "ok")
                continue
            if not self._download(i, job["url"], dest):
                if self._stop:
                    self.job_done.emit(i, False, "stopped")
                continue
            if not self._verify(i, dest, job.get("sha256", "")):
                if self._stop:
                    self.job_done.emit(i, False, "stopped")
                continue
            if not self._copy(i, dest, dst_file):
                if self._stop:
                    self.job_done.emit(i, False, "stopped")
                continue
            # Remove superseded files only after the new ISO is safely in place.
            failed_removals = self._remove_old_files(job, dst_file)
            if failed_removals:
                self.job_done.emit(i, False, "old ISO was not removed: " + failed_removals)
                continue
            self.job_done.emit(i, True, "ok")
        self.done.emit()


# ―― CLI selftest ―――――――――――――――――――――――――――――――――――――――――――――――――――――――――

def selftest(only: str = "") -> int:
    rows = []
    for distro in catalog.all_distros():
        if only and distro["id"] != only:
            continue
        for edition in catalog.available_editions(distro):
            for arch in distro["archs"]:
                info = resolve_latest(distro, edition, arch)
                status = "OK " if info.ok and info.filename.lower().endswith(".iso") else "ERR"
                detail = info.error if info.error else f"{info.version:<14} {info.filename}"
                rows.append((status, distro["id"], edition["id"], arch, detail))
    width = max((len(r[1]) for r in rows), default=6)
    ok = 0
    for status, did, eid, arch, detail in rows:
        if status == "OK ":
            ok += 1
        print(f"[{status}] {did:<{width}} {eid:<12} {arch:<8} {detail}")
    print(f"\n{ok}/{len(rows)} sources resolved")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        args.remove("--selftest")
        target = args[0] if args else ""
        raise SystemExit(selftest(target))
    print("usage: python -m updater --selftest [distro_id]")
