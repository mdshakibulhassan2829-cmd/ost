from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ost.core import current_platform, downloads_dir, is_root, run_root

Log = Callable[[str], None]


@dataclass
class InstallResult:
    ok: bool = False
    message: str = ""
    instructions: str = ""


def _nolog(_line: str) -> None:
    pass


def _extract_linux_archive(tmp: Path, archive: Path) -> list[Path]:
    """Extract a .deb/.rpm source archive and return the package files.

    `filter="data"` blocks absolute paths and path traversal; Python < 3.10.12
    does not know the argument, so fall back to the plain extractall.
    """
    with tarfile.open(archive) as tf:
        try:
            tf.extractall(tmp, filter="data")
        except TypeError:  # Python < 3.10.12
            tf.extractall(tmp)
    pkgs: list[Path] = []
    for root, _dirs, files in os.walk(tmp):
        for fn in files:
            if fn.endswith((".deb", ".rpm")):
                pkgs.append(Path(root) / fn)
    return pkgs


def _install_linux_packages(archive: Path, log: Log) -> InstallResult:
    tmp = Path(tempfile.mkdtemp(prefix="ost-extract-"))
    try:
        pkgs = _extract_linux_archive(tmp, archive)
        debs = sorted(p for p in pkgs if p.suffix == ".deb")
        rpms = sorted(p for p in pkgs if p.suffix == ".rpm")
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return InstallResult(False, f"Failed to extract {archive.name}: {e}")
    if not pkgs:
        shutil.rmtree(tmp, ignore_errors=True)
        return InstallResult(False, "No .deb/.rpm packages found in the downloaded archive.")
    if debs:
        result = _install_debs(debs, log)
    else:
        rc, _out = run_root(["rpm", "-ivh", *[str(p) for p in rpms]], log=log)
        result = InstallResult(rc == 0, "rpm install " + ("OK" if rc == 0 else "failed"))
    if not result.ok:
        result.instructions = (result.instructions + " " if result.instructions else "") + f"Packages remain in: {tmp}"
        return result
    shutil.rmtree(tmp, ignore_errors=True)
    return result


def _install_debs(debs: list[Path], log: Log) -> InstallResult:
    if not debs:
        return InstallResult(False, "No .deb packages found in the downloaded archive.")
    rc, out = run_root(["dpkg", "-i", *[str(d) for d in debs]], log=log)
    if rc != 0:
        return InstallResult(
            False,
            "Package installation failed.",
            f"Manually run: dpkg -i {' '.join(str(d) for d in debs)}",
        )
    return InstallResult(True, "Installed successfully.")


def _windows_run(cmd: list[str], log: Log) -> InstallResult:
    log(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            log(line.rstrip("\n"))
        rc = proc.wait()
        return InstallResult(rc == 0, "Finished with code " + str(rc))
    except FileNotFoundError as e:
        return InstallResult(False, f"Command not found: {e}")


def _macos_install_dmg(dmg: Path, bundle_name: str, log: Log) -> InstallResult:
    log(f"mounting {dmg.name} ...")
    mount = subprocess.run(
        ["hdiutil", "attach", str(dmg), "-nobrowse", "-noautoopen"],
        capture_output=True, text=True,
    )
    if mount.returncode != 0:
        return InstallResult(False, "hdiutil attach failed.", mount.stderr)
    mounted = None
    for line in mount.stdout.splitlines():
        if "/Volumes/" in line:
            mounted = line.split("\t")[-1].strip()
    if not mounted:
        return InstallResult(False, "Could not locate mounted volume.")
    mounted_dir = Path(mounted)
    bundle = mounted_dir / bundle_name
    if not bundle.exists():
        apps = sorted(p for p in mounted_dir.iterdir() if p.is_dir() and p.suffix == ".app")
        if not apps:
            return InstallResult(False, f"No '{bundle_name}' App bundle found on the mounted volume.")
        bundle = apps[0]
        log(f"bundle not at {bundle_name}, using {bundle.name}")
    target = Path("/Applications") / bundle.name
    rc = subprocess.run(["ditto", str(bundle), str(target)], capture_output=True, text=True)
    subprocess.run(["hdiutil", "detach", mounted], capture_output=True, text=True)
    if rc.returncode != 0:
        return InstallResult(False, "ditto copy failed.", rc.stderr)
    return InstallResult(True, f"Installed {target.name} into /Applications.")


def install_artifact(slug: str, path: Path, log: Optional[Log] = None) -> InstallResult:
    log = log or _nolog
    plat = current_platform()
    suffix = path.suffix.lower()
    name = path.name.lower()

    if slug in ("libreoffice", "openoffice"):
        if plat == "linux" and (suffix in (".gz", ".xz", ".tgz") or "tar" in name):
            return _install_linux_packages(path, log)
        if plat == "linux" and suffix == ".deb":
            return _install_debs([path], log)
        if plat == "linux" and suffix == ".rpm":
            rc, _out = run_root(["rpm", "-ivh", str(path)], log=log)
            return InstallResult(rc == 0, "rpm install " + ("OK" if rc == 0 else "failed"))
        if plat == "windows":
            if suffix == ".msi":
                return _windows_run(["msiexec", "/i", str(path), "/qn", "/norestart"], log)
            if suffix == ".exe":
                return _windows_run([str(path)], log)
        if plat == "macos" and suffix == ".dmg":
            if slug == "libreoffice":
                return _macos_install_dmg(path, "LibreOffice.app", log)
            return _macos_install_dmg(path, "OpenOffice.org.app", log)
        return InstallResult(False, "Wrong installer format for the current platform.")

    if slug == "wps":
        if plat == "linux" and suffix == ".deb":
            return _install_debs([path], log)
        if plat == "linux" and suffix == ".rpm":
            rc, _out = run_root(["rpm", "-ivh", str(path)], log=log)
            return InstallResult(rc == 0, "rpm install " + ("OK" if rc == 0 else "failed"))
        if plat == "windows" and suffix in (".exe", ".msi"):
            return _windows_run([str(path)], log)
        if plat == "macos":
            return _macos_install_dmg(path, "wpsoffice.app", log)
        return InstallResult(False, "Wrong installer format for the current platform.")

    if slug == "ms-office":
        if plat != "windows":
            return InstallResult(
                False,
                "Microsoft Office (ODT) can only install on Windows.",
                "Download the files here, copy them to a Windows PC and run setup.exe /configure configuration.xml",
            )
        return InstallResult(False, "Use the ODT workflow (run_odt) instead of direct install.")

    return InstallResult(False, f"Unknown suite: {slug}")


def _find_setup_in(base: Path) -> Path | None:
    for name in ("setup.exe", "setup"):
        p = base / name
        if p.exists():
            return p
    return None


def extract_odt_tool(download_dir: Optional[Path] = None) -> Path | None:
    base = (download_dir or downloads_dir()) / "ms-office"
    base.mkdir(parents=True, exist_ok=True)
    setup = _find_setup_in(base)
    if setup:
        return setup
    packages = sorted(base.glob("officedeploymenttool*"))
    if not packages:
        return None
    pkg = packages[0]
    try:
        is_zip = zipfile.is_zipfile(pkg)
    except Exception:
        is_zip = False
    if is_zip:
        with zipfile.ZipFile(pkg) as zf:
            zf.extractall(base)
        return _find_setup_in(base)
    if pkg.suffix.lower() == ".exe":
        if current_platform() == "windows":
            subprocess.run([str(pkg), "/quiet", "/extract:" + str(base)], check=False)
            return _find_setup_in(base)
        if shutil.which("7z"):
            subprocess.run(
                ["7z", "x", str(pkg), f"-o{base}", "-y"],
                capture_output=True,
            )
        elif shutil.which("cabextract"):
            subprocess.run(["cabextract", str(pkg)], cwd=base, capture_output=True)
        return _find_setup_in(base)
    return None


def find_or_download_odt(download_dir: Optional[Path] = None) -> Path | None:
    """Return the extracted setup.exe if the ODT package is available locally."""
    base = (download_dir or downloads_dir()) / "ms-office"
    base.mkdir(parents=True, exist_ok=True)
    return extract_odt_tool(base)


def run_odt(action: str, cfg: dict, log: Optional[Log] = None) -> InstallResult:
    """action: 'download' | 'configure' | 'extract'."""
    log = log or _nolog
    from ost.providers.msoffice import save_configuration_xml

    if current_platform() != "windows":
        return InstallResult(
            False,
            "The Office Deployment Tool only runs on Windows.",
            "Copy the 'ms-office' download folder (setup.exe + configuration.xml) to Windows "
            "and run: setup.exe /%s configuration.xml" % action,
        )
    base = downloads_dir() / "ms-office"
    base.mkdir(parents=True, exist_ok=True)
    setup = find_or_download_odt()
    if setup is None:
        return InstallResult(False, "setup.exe not found. Download the Office Deployment Tool first.")
    cfg_path = save_configuration_xml(cfg, base / "configuration.xml")
    cfg_path = cfg_path.resolve()
    log(f"Configuration written to {cfg_path}")
    old = os.getcwd()
    os.chdir(base)
    try:
        proc = subprocess.Popen(
            ["setup.exe", "/" + action, str(cfg_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            log(line.rstrip("\n"))
        proc.wait()
    finally:
        os.chdir(old)
    return InstallResult(True, f"setup.exe /{action} finished.")