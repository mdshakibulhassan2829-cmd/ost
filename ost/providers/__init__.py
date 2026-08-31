"""Office suite providers - data fetched from official servers."""

from __future__ import annotations

from .libreoffice import LibreOfficeProvider
from .msoffice import MSOfficeProvider
from .openoffice import OpenOfficeProvider
from .wps import WPSProvider

REGISTRY: list = [
    LibreOfficeProvider(),
    MSOfficeProvider(),
    WPSProvider(),
    OpenOfficeProvider(),
]


def list_providers() -> list:
    return list(REGISTRY)


def get_provider(slug: str):
    for p in REGISTRY:
        if p.slug == slug:
            return p
    raise KeyError(slug)