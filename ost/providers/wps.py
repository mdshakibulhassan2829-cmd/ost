from __future__ import annotations

import asyncio
import re
from typing import Optional

from ost.core import Asset, Release
from ost.net import fetch, head_size

from .base import Provider

PAGES = [
    "https://www.wps.com/wps/download/",
    "https://linux.wps.cn/",
    "https://www.wps.com/office/linux/",
]

PLATFORM_PATTERNS = {
    "linux": re.compile(r"\.(deb|rpm|tar\.(xz|gz))", re.I),
    "windows": re.compile(r"\.(exe|msi)", re.I),
    "macos": re.compile(r"\.(dmg|pkg)", re.I),
}


class WPSProvider(Provider):
    slug = "wps"
    name = "WPS Office"
    vendor = "Kingsoft"
    official_url = "https://www.wps.com"
    description = "WPS Office is a lightweight office suite (Writer, Spreadsheets, Presentation) by Kingsoft."

    def install_modes(self) -> list[str]:
        return ["linux", "windows", "macos"]

    async def latest(self, platform: str, arch: str, **opts) -> Optional[Release]:
        urls: list[str] = []
        version = ""
        for page in PAGES:
            try:
                html = await fetch(page, timeout=45)
            except Exception:
                continue
            for href in re.findall(r'href=["\']([^"\' ]+\.(deb|rpm|exe|msi|dmg|pkg))["\']', html, re.I):
                url = href[0]
                if not url.lower().startswith(("http://", "https://")):
                    url = page + url.lstrip("/")
                if PLATFORM_PATTERNS[platform].search(url) and "wps" in url.lower():
                    urls.append(url)
            m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{1,4})\.\d+", html)
            if m:
                version = m.group(0)

        candidates: list[str] = []
        for url in sorted(set(urls)):
            is_arm = "arm64" in url or "aarch64" in url
            if platform == "linux":
                if arch == "aarch64" and is_arm:
                    candidates.insert(0, url)
                elif arch == "x86_64" and not is_arm:
                    candidates.insert(0, url)
                else:
                    candidates.append(url)
            else:
                candidates.append(url)

        chosen: Optional[Asset] = None
        fallback: Optional[Asset] = None
        for url in candidates:
            size = 0
            try:
                size = await head_size(url)
            except Exception:
                size = 0
            asset = Asset(name=url.rsplit("/", 1)[-1], url=url, size=size, kind="installer")
            if size > 0:
                chosen = asset
                break
            if fallback is None:
                fallback = asset

        if chosen is None and fallback is not None:
            chosen = fallback
        if chosen is None:
            return None
        return Release(
            version=version or "latest",
            channel="stable",
            released="",
            notes_url="https://www.wps.com/wps/download/",
            assets=[chosen],
        )


def _probe() -> None:
    asyncio.run(WPSProvider().latest("linux", "x86_64"))


if __name__ == "__main__":
    _probe()