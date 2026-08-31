from __future__ import annotations

import asyncio
import re
from typing import Optional

from ost.core import Asset, Release, parse_version
from ost.net import fetch, head_size, probe

from .base import Provider

BASE = "https://download.documentfoundation.org/libreoffice/stable/"


def _file_arch(arch: str) -> str:
    """LibreOffice installer file names use 'x86-64' (hyphen), not 'x86_64'.

    Directory names keep the underscore (deb/x86_64/), the file names do not.
    """
    return "x86-64" if arch == "x86_64" else arch


class LibreOfficeProvider(Provider):
    slug = "libreoffice"
    name = "LibreOffice"
    vendor = "The Document Foundation"
    official_url = "https://www.libreoffice.org"
    description = "LibreOffice is a free, open source office suite - Writer, Calc, Impress, Draw, Base, Math."

    def install_modes(self) -> list[str]:
        return ["linux", "windows", "macos"]

    async def _versions(self) -> list[str]:
        try:
            html = await fetch(BASE)
        except Exception:
            return []
        found = re.findall(r'href="(\d+\.\d+\.\d+)/"', html)
        return sorted(set(found), key=parse_version, reverse=True)

    async def latest(self, platform: str, arch: str, variant: str = "auto", **opts) -> Optional[Release]:
        versions = await self._versions()
        if not versions:
            return None
        ver = versions[0]
        asset = await self._pick_asset(ver, platform, arch, variant)
        if asset is None:
            return None
        return Release(
            version=ver,
            channel="stable",
            notes_url="https://www.libreoffice.org/download/release-notes/",
            assets=[asset],
        )

    async def _pick_asset(self, ver: str, platform: str, arch: str, variant: str) -> Optional[Asset]:
        base = f"{BASE}{ver}/"
        fa = _file_arch(arch)

        candidates: list[tuple[str, str]] = []
        if platform == "linux":
            if variant == "rpm":
                candidates.append((f"rpm/{arch}/LibreOffice_{ver}_Linux_{fa}_rpm.tar.gz", "rpm"))
            else:
                candidates.append((f"deb/{arch}/LibreOffice_{ver}_Linux_{fa}_deb.tar.gz", "deb"))
                if variant == "auto":
                    candidates.append((f"rpm/{arch}/LibreOffice_{ver}_Linux_{fa}_rpm.tar.gz", "rpm"))
        elif platform == "windows":
            # win/x86_64/ and win/aarch64/ directories; file names are Win_<arch>.
            candidates.append((f"win/{arch}/LibreOffice_{ver}_Win_{fa}.msi", "msi"))
        elif platform == "macos":
            # mac/x86_64/ and mac/aarch64/ directories; file names are MacOS_<arch>.
            candidates.append((f"mac/{arch}/LibreOffice_{ver}_MacOS_{fa}.dmg", "dmg"))

        for rel, kind in candidates:
            url = f"{base}{rel}"
            info = await probe(url, timeout=60)
            if info:
                real = await head_size(url)
                size = real or info.get("content_length") or 0
                return Asset(name=url.rsplit("/", 1)[-1], url=url, size=size, kind=kind)
        return None


def _probe() -> None:
    async def run() -> None:
        p = LibreOfficeProvider()
        rel = await p.latest("linux", "aarch64")
        print(rel)

    asyncio.run(run())


if __name__ == "__main__":
    _probe()