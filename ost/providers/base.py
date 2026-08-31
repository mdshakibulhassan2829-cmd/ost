from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ost.core import Release


class Provider(ABC):
    slug: str = ""
    name: str = ""
    vendor: str = ""
    official_url: str = ""
    description: str = ""
    #: Operating systems this suite is natively available on.
    platforms: set[str] = {"linux", "macos", "windows"}

    def __init__(self) -> None:
        # Copy so subclasses never share the same mutable class-level set.
        self.platforms = set(self.platforms)

    def supports_platform(self, platform: str) -> bool:
        return platform in self.platforms

    def unsupported_reason(self, platform: str) -> str:
        shown = ", ".join(sorted(self.platforms))
        return f"{self.name} is only available natively on {shown} (current OS: {platform or 'unknown'})"

    @abstractmethod
    def install_modes(self) -> list[str]:
        ...

    @abstractmethod
    async def latest(self, platform: str, arch: str, **opts) -> Optional[Release]:
        """Return the newest release with a single matching asset."""
        ...