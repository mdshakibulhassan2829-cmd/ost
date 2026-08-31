from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

APP_NAME = "ost"


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def downloads_dir() -> Path:
    d = data_dir() / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ms_config_path() -> Path:
    return config_dir() / "ms_office_configuration.xml"


def load_config() -> dict:
    p = config_dir() / "config.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    (config_dir() / "config.json").write_text(json.dumps(cfg, indent=2))


def ms_config_data() -> dict:
    return load_config().get("ms_config", {})


def save_ms_config(data: dict) -> None:
    cfg = load_config()
    cfg["ms_config"] = data
    save_config(cfg)


@dataclass
class Asset:
    name: str
    url: str
    size: Optional[int] = None
    sha256: Optional[str] = None
    kind: str = "installer"


@dataclass
class Release:
    version: str
    channel: str = "stable"
    released: str = ""
    notes_url: str = ""
    assets: list[Asset] = field(default_factory=list)

    def best_asset(self) -> Optional[Asset]:
        return self.assets[0] if self.assets else None


@dataclass
class SuiteInfo:
    slug: str
    name: str
    vendor: str
    description: str
    official_url: str
    install_modes: list[str] = field(default_factory=list)


def current_platform() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    # Termux reports "Android"; treat it as a Linux userspace (proot/userland).
    if s.startswith("android"):
        return "linux"
    return s


def current_arch() -> str:
    m = platform.machine().lower()
    aliases = {"amd64": "x86_64", "arm64": "aarch64", "x86": "x86", "i386": "x86", "i686": "x86"}
    return aliases.get(m, m)


def platform_tag(plat: str | None = None, arch: str | None = None) -> str:
    return f"{(plat or current_platform())}-{(arch or current_arch())}"


def parse_version(v: str) -> tuple:
    nums = []
    for part in v.replace("-", ".").split("."):
        if part.isdigit():
            nums.append(int(part))
        else:
            break
    return tuple(nums)


def is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def notify(title: str, message: str) -> None:
    """Best-effort desktop notification. Never raises on any platform."""
    def _notify_linux() -> None:
        if has_cmd("notify-send"):
            subprocess.run(
                ["notify-send", "--app-name=OST", title, message],
                capture_output=True,
                timeout=10,
            )

    def _notify_macos() -> None:
        script = (
            'display notification "'
            + message.replace('"', '\\"')
            + '" with title "'
            + title.replace('"', '\\"')
            + '"'
        )
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)

    def _notify_windows() -> None:
        t = title.replace("'", "''")
        m = message.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            f"$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Information;"
            f"$n.BalloonTipTitle='{t}';$n.BalloonTipText='{m}';"
            "$n.Visible=$true;$n.ShowBalloonTip(5000)"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=15,
        )

    try:
        if not is_root() or sys.platform == "win32":
            if sys.platform == "darwin":
                _notify_macos()
            elif sys.platform == "win32":
                _notify_windows()
            else:
                _notify_linux()
    except Exception:
        pass


def run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def run_root(cmd: list[str], log=None) -> tuple[int, str]:
    def emit(line: str) -> None:
        if log:
            log(line)
        else:
            print(line)

    if not is_root():
        if has_cmd("sudo"):
            cmd = ["sudo", "-n", *cmd]
        elif has_cmd("doas"):
            cmd = ["doas", "-n", *cmd]
        else:
            emit("[!] Root privileges required. Run as root or re-run with sudo.")
            return 1, ""
    try:
        emit(f"$ {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            out.append(line)
            emit(line)
        rc = proc.wait()
        return rc, "\n".join(out)
    except (PermissionError, OSError) as e:
        emit(f"[!] Cannot elevate privileges: {e}")
        return 1, str(e)


def detect_installed(suite_slug: str) -> str | None:
    """Best-effort detection of an installed office version."""
    if suite_slug == "libreoffice":
        for exe in ("libreoffice", "soffice"):
            path = shutil.which(exe)
            if path:
                try:
                    out = run([path, "--version"], timeout=30).stdout.strip()
                    if "LibreOffice" in out:
                        return out.split("LibreOffice", 1)[1].strip().split()[0]
                except Exception:
                    pass
        return None
    if suite_slug == "openoffice":
        path = shutil.which("soffice")
        if path:
            try:
                out = run([path, "--version"], timeout=30).stdout.strip()
                if "OpenOffice" in out:
                    return out.split("OpenOffice", 1)[1].strip().split()[0]
            except Exception:
                pass
        return None
    if suite_slug == "wps":
        for exe, flag in (("wps", "--version"), ("wps-office", "--version")):
            path = shutil.which(exe)
            if path:
                try:
                    out = run([path, flag], timeout=30).stdout.strip()
                    return out.split()[-1].strip(")") if out else None
                except Exception:
                    pass
        return None
    if suite_slug == "ms-office":
        if current_platform() != "windows":
            return None
        keys = [
            "HKLM\\SOFTWARE\\Microsoft\\Office\\ClickToRun\\Configuration",
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Office\\ClickToRun\\Configuration",
        ]
        for key in keys:
            try:
                out = run(["reg", "query", key, "/v", "VersionToReport"], timeout=20).stdout
                if out.strip():
                    return out.strip().split()[-1]
            except Exception:
                pass
        return None
    return None