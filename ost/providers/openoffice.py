from __future__ import annotations

import asyncio
import re
from typing import Optional

from ost.core import Asset, Release, parse_version
from ost.net import fetch, head_size, probe

from .base import Provider

BASE = "https://dlcdn.apache.org/openoffice/"


class OpenOfficeProvider(Provider):
    slug = "openoffice"
    name = "Apache OpenOffice"
    vendor = "Apache Software Foundation"
    official_url = "https://www.openoffice.org"
    description = "Apache OpenOffice is an open source office suite - Writer, Calc, Impress, Draw, Base, Math."

    def install_modes(self) -> list[str]:
        return ["linux", "windows", "macos"]

    async def _latest_version(self) -> Optional[str]:
        try:
            html = await fetch(BASE)
        except Exception:
            return None
        found = re.findall(r'href="(\d+\.\d+\.\d+)/"', html)
        if not found:
            return None
        return sorted(set(found), key=parse_version, reverse=True)[0]

    async def _languages(self, ver: str) -> list[str]:
        try:
            html = await fetch(f"{BASE}{ver}/binaries/")
        except Exception:
            return ["en-US"]
        langs = [m for m in re.findall(r'href="([a-z]+(-[A-Z0-9]+)?)/"', html)]
        return sorted({m[0] for m in langs}) or ["en-US"]

    async def latest(self, platform: str, arch: str, lang: str = "en-US", variant: str = "deb", **opts) -> Optional[Release]:
        ver = await self._latest_version()
        if not ver:
            return None
        asset = await self._pick_asset(ver, platform, arch, lang, variant)
        if asset is None:
            return None
        return Release(
            version=ver,
            channel="stable",
            released="",
            notes_url="https://www.openoffice.org/release-notes/",
            assets=[asset],
        )

    async def _pick_asset(self, ver: str, platform: str, arch: str, lang: str, variant: str) -> Optional[Asset]:
        base = f"{BASE}{ver}/binaries/{lang}/"
        candidates: list[str] = []
        if platform == "linux":
            install = "deb" if variant == "deb" else "rpm"
            if arch == "x86_64":
                candidates.extend(
                    [
                        f"Apache_OpenOffice_{ver}_Linux_x86-64_install-{install}_{lang}.tar.gz",
                        f"Apache_OpenOffice_{ver}_Linux_x86_install-{install}_{lang}.tar.gz",
                    ]
                )
            else:
                candidates.append(f"Apache_OpenOffice_{ver}_Linux_x86-64_install-{install}_{lang}.tar.gz")
        elif platform == "windows":
            candidates.append(f"Apache_OpenOffice_{ver}_Win_x86-64_install_{lang}.exe")
        elif platform == "macos":
            candidates.append(f"Apache_OpenOffice_{ver}_MacOS_x86-64_install_{lang}.dmg")

        for name in candidates:
            url = f"{base}{name}"
            info = await probe(url, timeout=60)
            if info:
                real = await head_size(url)
                size = real or info.get("content_length") or 0
                return Asset(name=name, url=url, size=size, kind="installer")
        return None


def _probe() -> None:
    asyncio.run(OpenOfficeProvider().latest("linux", "x86_64"))


if __name__ == "__main__":
    _probe()