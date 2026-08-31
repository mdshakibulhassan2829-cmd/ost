from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from ost.core import Asset, Release, config_dir

from .base import Provider

ODT_PAGE = "https://www.microsoft.com/en-us/download/details.aspx?id=49117"

# Direct download links used by Microsoft for the ODT package over the years.
ODT_DIRECT_LINKS = [
    "https://go.microsoft.com/fwlink/?linkid=626510",
    "https://go.microsoft.com/fwlink/?linkid=626065",
    "https://go.microsoft.com/fwlink/?LinkID=612889",
]

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _is_html_like(first: bytes) -> bool:
    head = first[:256].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<!doctype" in first[:256].lower()


def _odt_filename(url: str, content_disposition: str, first: bytes) -> str:
    import re

    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', content_disposition, re.I)
    if m:
        name = m.group(1).strip().strip('"')
        if name.endswith((".exe", ".zip", ".cab")):
            return name
    if url:
        base = url.rsplit("/", 1)[-1]
        if base and "?" not in base and "." in base:
            return base
    if first[:2] == b"MZ":
        return "officedeploymenttool.exe"
    if first[:2] == b"PK":
        return "officedeploymenttool.zip"
    return "officedeploymenttool"

# (category, [(ID, human label), ...])
PRODUCT_CATALOG: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Office suites",
        [
            ("ProPlus2024Volume", "Office LTSC 2024 Professional Plus (Volume)"),
            ("ProPlus2024Retail", "Office LTSC 2024 Professional Plus (Retail)"),
            ("O365ProPlusRetail", "Microsoft 365 Apps for enterprise"),
            ("O365BusinessRetail", "Microsoft 365 Apps for business"),
            ("ProPlus2021Volume", "Office LTSC 2021 Professional Plus (Volume)"),
            ("ProPlus2021Retail", "Office LTSC 2021 Professional Plus (Retail)"),
            ("ProPlus2019Volume", "Office 2019 Professional Plus (Volume)"),
            ("ProPlus2019Retail", "Office 2019 Professional Plus (Retail)"),
            ("ProPlus2016Volume", "Office 2016 Professional Plus (Volume)"),
            ("Standard2024Volume", "Office LTSC 2024 Standard (Volume)"),
            ("Standard2024Retail", "Office LTSC 2024 Standard (Retail)"),
            ("Standard2021Volume", "Office LTSC 2021 Standard (Volume)"),
            ("Standard2019Volume", "Office 2019 Standard (Volume)"),
            ("Professional2024Retail", "Office 2024 Professional (Retail)"),
            ("MondoVolume", "Mondo Volume (server / permanent LTSC bundle)"),
        ],
    ),
    (
        "Visio",
        [
            ("VisioPro2024Volume", "Visio LTSC 2024 Professional (Volume)"),
            ("VisioPro2024Retail", "Visio LTSC 2024 Professional (Retail)"),
            ("VisioPro2021Volume", "Visio LTSC 2021 Professional (Volume)"),
            ("VisioPro2019Volume", "Visio 2019 Professional (Volume)"),
            ("VisioStd2024Volume", "Visio LTSC 2024 Standard (Volume)"),
            ("VisioStd2019Volume", "Visio 2019 Standard (Volume)"),
        ],
    ),
    (
        "Project",
        [
            ("ProjectPro2024Volume", "Project LTSC 2024 Professional (Volume)"),
            ("ProjectPro2024Retail", "Project LTSC 2024 Professional (Retail)"),
            ("ProjectPro2021Volume", "Project LTSC 2021 Professional (Volume)"),
            ("ProjectPro2019Volume", "Project 2019 Professional (Volume)"),
            ("ProjectStd2024Volume", "Project LTSC 2024 Standard (Volume)"),
            ("ProjectStd2021Volume", "Project LTSC 2021 Standard (Volume)"),
        ],
    ),
    (
        "Single apps & legacy",
        [
            ("Access2024Retail", "Access LTSC 2024 (Retail)"),
            ("Access2024Volume", "Access LTSC 2024 (Volume)"),
            ("O365HomePremRetail", "Microsoft 365 Family / Personal"),
            ("O365SmallBusPremRetail", "Microsoft 365 Business Premium"),
            ("Office2019HomeBusinessRetail", "Office 2019 Home & Business"),
        ],
    ),
]

CHANNELS: list[tuple[str, str, str]] = [
    ("MonthlyEnterprise", "Monthly Enterprise Channel", "Updated monthly; recommended baseline for organizations."),
    ("Current", "Current Channel", "Newest features immediately; stays at the latest build."),
    ("SemiAnnualEnterprise", "Semi-Annual Enterprise Channel", "Updated twice a year; maximum stability."),
    ("Monthly", "Monthly Channel (consumer)", "Consumer-style monthly channel."),
    ("PerpetualVL2024", "Perpetual (Office LTSC 2024)", "Perpetual volume license, no feature updates."),
    ("PerpetualVL2021", "Perpetual (Office LTSC 2021)", "Perpetual volume license, no feature updates."),
    ("PerpetualVL2019", "Perpetual (Office 2019)", "Perpetual volume license, no feature updates."),
    ("PerpetualVL2016", "Perpetual (Office 2016)", "Legacy perpetual volume license."),
    ("BetaChannel", "Beta Channel", "Pre-release builds for testing."),
]

LANGUAGES: list[tuple[str, str]] = [
    ("en-us", "English (US)"),
    ("en-gb", "English (UK)"),
    ("af-za", "Afrikaans"),
    ("ar-sa", "Arabic"),
    ("bg-bg", "Bulgarian"),
    ("ca-es", "Catalan"),
    ("cs-cz", "Czech"),
    ("da-dk", "Danish"),
    ("de-de", "German"),
    ("el-gr", "Greek"),
    ("es-es", "Spanish"),
    ("et-ee", "Estonian"),
    ("fi-fi", "Finnish"),
    ("fr-fr", "French"),
    ("he-il", "Hebrew"),
    ("hi-in", "Hindi"),
    ("hr-hr", "Croatian"),
    ("hu-hu", "Hungarian"),
    ("id-id", "Indonesian"),
    ("it-it", "Italian"),
    ("ja-jp", "Japanese"),
    ("kk-kz", "Kazakh"),
    ("ko-kr", "Korean"),
    ("lt-lt", "Lithuanian"),
    ("lv-lv", "Latvian"),
    ("ms-my", "Malay"),
    ("nb-no", "Norwegian (Bokmal)"),
    ("nl-nl", "Dutch"),
    ("pl-pl", "Polish"),
    ("pt-br", "Portuguese (Brazil)"),
    ("pt-pt", "Portuguese (Portugal)"),
    ("ro-ro", "Romanian"),
    ("ru-ru", "Russian"),
    ("sk-sk", "Slovak"),
    ("sl-si", "Slovenian"),
    ("sr-latn-rs", "Serbian (Latin)"),
    ("sv-se", "Swedish"),
    ("th-th", "Thai"),
    ("tr-tr", "Turkish"),
    ("uk-ua", "Ukrainian"),
    ("vi-vn", "Vietnamese"),
    ("zh-cn", "Chinese (Simplified)"),
    ("zh-tw", "Chinese (Traditional)"),
]

EXCLUDE_APPS: list[tuple[str, str]] = [
    ("Access", "Access database"),
    ("Bing", "Bing search"),
    ("Excel", "Excel"),
    ("Groove", "Groove (OneDrive for Business sync)"),
    ("Lync", "Lync / Skype for Business"),
    ("OneDrive", "OneDrive"),
    ("OneNote", "OneNote"),
    ("Outlook", "Outlook"),
    ("PowerPoint", "PowerPoint"),
    ("Project", "Project"),
    ("Publisher", "Publisher"),
    ("SharePointDesigner", "SharePoint Designer"),
    ("Teams", "Teams"),
    ("Visio", "Visio"),
    ("Word", "Word"),
]

MAIN_APPS = {
    "Access": "Access",
    "Excel": "Excel",
    "OneNote": "OneNote",
    "Outlook": "Outlook",
    "PowerPoint": "PowerPoint",
    "Project": "Project",
    "Publisher": "Publisher",
    "Skype": "Skype for Business",
    "Teams": "Teams",
    "Visio": "Visio",
    "Word": "Word",
}

DISPLAY_LEVELS = [("None", "None - fully silent"), ("Full", "Full - show setup UI (default)")]

LOGGING_LEVELS = [("Off", "Off"), ("Standard", "Standard"), ("Verbose", "Verbose")]


def default_cfg() -> dict:
    return {
        "edition": "64",
        "channel": "PerpetualVL2024",
        "version": "",
        "source_path": "",
        "update_enabled": True,
        "update_channel": "",
        "update_path": "",
        "products": [],
        "primary_language": "en-us",
        "additional_languages": [],
        "exclude_apps": [],
        "display_level": "Full",
        "accept_eula": True,
        "autoactivate": True,
        "force_app_shutdown": True,
        "remove_msi": False,
        "pid_key": "",
        "company_name": "",
        "user_name": "",
        "logging_level": "Off",
        "logging_path": "",
    }


def build_configuration_xml(cfg: dict) -> str:
    root = ET.Element("Configuration")

    add = ET.SubElement(root, "Add")
    add.set("OfficeClientEdition", str(cfg.get("edition", "64")))
    add.set("Channel", cfg.get("channel", "PerpetualVL2024"))
    if cfg.get("version"):
        add.set("Version", str(cfg["version"]))
    if cfg.get("source_path"):
        add.set("SourcePath", str(cfg["source_path"]))

    products = cfg.get("products") or []
    if not products:
        products = ["ProPlus2024Volume"]
    for pid in products:
        prod = ET.SubElement(add, "Product")
        prod.set("ID", pid)
        ET.SubElement(prod, "Language", {"ID": cfg.get("primary_language", "en-us")})
        for lang in cfg.get("additional_languages", []):
            ET.SubElement(prod, "Language", {"ID": lang})
        for app in cfg.get("exclude_apps", []):
            ET.SubElement(prod, "ExcludeApp", {"ID": app})

    display_level = cfg.get("display_level", "Full")
    if display_level or cfg.get("accept_eula"):
        disp = ET.SubElement(root, "Display")
        if display_level:
            disp.set("Level", str(display_level))
        if cfg.get("accept_eula"):
            disp.set("AcceptEULA", "TRUE")

    logging_level = cfg.get("logging_level", "Off")
    if logging_level and logging_level != "Off":
        log = ET.SubElement(root, "Logging")
        log.set("Level", str(logging_level))
        if cfg.get("logging_path"):
            log.set("Path", str(cfg["logging_path"]))

    if cfg.get("autoactivate"):
        ET.SubElement(root, "Property", {"Name": "AUTOACTIVATE", "Value": "1"})
    if cfg.get("force_app_shutdown"):
        ET.SubElement(root, "Property", {"Name": "FORCEAPPSHUTDOWN", "Value": "TRUE"})
    if cfg.get("pid_key"):
        ET.SubElement(root, "Property", {"Name": "PIDKEY", "Value": str(cfg["pid_key"])})
    if cfg.get("company_name"):
        ET.SubElement(root, "Property", {"Name": "CompanyName", "Value": str(cfg["company_name"])})
    if cfg.get("user_name"):
        ET.SubElement(root, "Property", {"Name": "USERNAME", "Value": str(cfg["user_name"])})

    if cfg.get("remove_msi"):
        ET.SubElement(root, "RemoveMSI", {"All": "TRUE"})

    updates = ET.SubElement(root, "Updates")
    if cfg.get("update_enabled", True):
        updates.set("Enabled", "TRUE")
        updates.set("Channel", str(cfg.get("update_channel") or cfg.get("channel") or "MonthlyEnterprise"))
        if cfg.get("update_path"):
            updates.set("Path", str(cfg["update_path"]))
    else:
        updates.set("Enabled", "FALSE")

    ET.indent(root)
    return ET.tostring(root, encoding="unicode")


def save_configuration_xml(cfg: dict, path: Optional[Path] = None) -> Path:
    p = path or (config_dir() / "ms_office_configuration.xml")
    p.write_text(build_configuration_xml(cfg))
    return p


class MSOfficeProvider(Provider):
    slug = "ms-office"
    name = "Microsoft Office (ODT / OCT)"
    vendor = "Microsoft"
    official_url = ODT_PAGE
    description = (
        "Microsoft 365 / Office LTSC via the official Office Deployment Tool (ODT). "
        "Configure products, channels, languages and applications like the Office Customization Tool (OCT)."
    )
    # setup.exe runs natively on Windows only. The OCT configurator still works on
    # every OS to prepare configuration.xml for use on a Windows machine.
    platforms: set[str] = {"windows"}

    def install_modes(self) -> list[str]:
        return ["windows"]

    async def resolve_tool_url(self) -> Optional[str]:
        """Best effort: find the current official ODT download URL."""
        from ost.net import fetch, probe

        for link in ODT_DIRECT_LINKS:
            info = await probe(link, timeout=60)
            if not info:
                continue
            if _is_html_like(info["first_bytes"]):
                continue
            return info["final_url"]
        for page in (
            "https://www.microsoft.com/en-us/download/confirmation.aspx?id=49117",
            "https://www.microsoft.com/en-us/download/details.aspx?id=49117",
        ):
            try:
                html = await fetch(page, timeout=60, headers={"User-Agent": BROWSER_UA})
            except Exception:
                continue
            import re

            for m in re.findall(r'https?://[^\s"\'<>]+officedeploymenttool[^\s"\'<>]*', html):
                info = await probe(m, timeout=60)
                if info and not _is_html_like(info["first_bytes"]):
                    return info["final_url"]
            try:
                m = re.search(r'(https?://[^\s"\'<>]*officedeploymenttool[^\s"\'<>]*\.(?:exe|zip))', html)
                if m:
                    info = await probe(m.group(1), timeout=60)
                    if info and not _is_html_like(info["first_bytes"]):
                        return info["final_url"]
            except Exception:
                continue
        return None

    async def latest(self, platform: str, arch: str, **opts) -> Optional[Release]:
        from ost.net import probe

        url: Optional[str] = None
        fd = ""
        size = 0
        try:
            url = await self.resolve_tool_url()
        except Exception:
            url = None
        if url:
            info = await probe(url, timeout=60)
            if info and not _is_html_like(info["first_bytes"]):
                size = info["content_length"]
                fd = info.get("content_disposition") or ""
                name = _odt_filename(url, fd, info["first_bytes"])
            else:
                url = None
        return Release(
            version="odt",
            channel="odt",
            released="" if url else "manual",
            notes_url=ODT_PAGE,
            assets=[
                Asset(
                    name=_odt_filename(url, fd, b"") if url else "officedeploymenttool",
                    url=url or "",
                    size=size,
                    kind="tool",
                )
            ],
        )

    def config_xml(self, cfg: dict) -> str:
        return build_configuration_xml(cfg)


def _probe() -> None:
    asyncio.run(MSOfficeProvider().latest("linux", "x86_64"))


if __name__ == "__main__":
    _probe()