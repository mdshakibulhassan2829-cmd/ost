from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ost.core import (
    Asset,
    Release,
    current_arch,
    current_platform,
    detect_installed,
    downloads_dir,
)
from ost.installer import InstallResult, extract_odt_tool, install_artifact, run_odt
from ost.net import download
from ost.providers import get_provider

Progress = Callable[[int, Optional[int]], None]


@dataclass
class CheckResult:
    suite: str
    name: str
    installed: Optional[str]
    latest: Optional[str]
    release: Optional[Release]
    available: bool = True
    reason: str = ""
    error: str = ""
    platform: str = ""


async def check_suite(slug: str, platform: str | None = None, arch: str | None = None) -> CheckResult:
    provider = get_provider(slug)
    plat = platform or current_platform()
    a = arch or current_arch()
    if not provider.supports_platform(plat):
        return CheckResult(
            suite=slug,
            name=provider.name,
            installed=None,
            latest=None,
            release=None,
            available=False,
            reason=provider.unsupported_reason(plat),
            platform=plat,
        )
    release = None
    error = ""
    try:
        release = await provider.latest(plat, a)
    except Exception as e:
        error = str(e)
    return CheckResult(
        suite=slug,
        name=provider.name,
        installed=detect_installed(slug),
        latest=release.version if release else None,
        release=release,
        error=error,
        platform=plat,
    )


async def download_suite(
    slug: str,
    progress: Optional[Progress] = None,
    dest_dir: Optional[Path] = None,
    platform: str | None = None,
    arch: str | None = None,
    **opts,
) -> tuple[Path, Asset]:
    provider = get_provider(slug)
    plat = platform or current_platform()
    a = arch or current_arch()
    if not provider.supports_platform(plat):
        raise RuntimeError(provider.unsupported_reason(plat))
    release = await provider.latest(plat, a, **opts)
    if release is None or not release.assets:
        raise RuntimeError("No downloadable asset found for this platform.")
    asset = release.best_asset()
    assert asset is not None
    if not asset.url:
        from ost.providers.msoffice import ODT_PAGE

        raise RuntimeError(
            "Microsoft did not expose a direct download link from this machine.\n"
            "Grab the Office Deployment Tool manually and place it in the downloads/"
            "ms-office folder, then the installed ODT is found automatically:\n  " + ODT_PAGE
        )
    base = dest_dir or downloads_dir()
    dest = base / slug / asset.name
    await download(asset.url, dest, progress=progress)
    if slug == "ms-office":
        extract_odt_tool()
    return dest, asset


def install_suite(
    slug: str,
    path: Optional[Path] = None,
    cfg: Optional[dict] = None,
    log: Optional[Callable[[str], None]] = None,
) -> InstallResult:
    if slug == "ms-office":
        return run_odt("configure", cfg or {}, log=log)
    if path is None:
        # pick most recent download
        base = downloads_dir() / slug
        if not base.exists():
            return InstallResult(False, "No downloaded file yet. Download first.")
        files = sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return InstallResult(False, "No downloaded file yet. Download first.")
        path = files[0]
    return install_artifact(slug, path, log=log)


async def update_suite(
    slug: str,
    progress: Optional[Progress] = None,
    log: Optional[Callable[[str], None]] = None,
    cfg: Optional[dict] = None,
    **opts,
) -> tuple[InstallResult, Path | None]:
    if slug == "ms-office":
        return run_odt("configure", cfg or {}, log=log), None
    path, _asset = await download_suite(slug, progress=progress, **opts)
    return install_suite(slug, path, log=log), path