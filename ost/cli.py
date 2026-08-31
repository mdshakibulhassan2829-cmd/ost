from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ost import __version__
from ost.actions import check_suite, download_suite, install_suite, update_suite
from ost.core import current_platform, downloads_dir
from ost.providers import list_providers
from ost.providers.msoffice import (
    CHANNELS,
    LANGUAGES,
    PRODUCT_CATALOG,
    build_configuration_xml,
    default_cfg,
    save_configuration_xml,
)
from ost.providers.msoffice import ODT_PAGE

PROGRESS_W = 40


def _log(msg: str) -> None:
    print(msg, flush=True)


def _progress_bars(done: int, total: int | None) -> None:
    if total and total > 0:
        frac = min(done / total, 1.0)
    else:
        frac = 0
    bar = "#" * int(PROGRESS_W * frac)
    bar = bar.ljust(PROGRESS_W)
    shown = f"{done if total else ''}".rjust(1)
    if total:
        shown = f"{done/1024/1024:.1f}/{total/1024/1024:.1f} MiB"
    print(f"\r  [{bar}] {shown}   ", end="", flush=True)


def cmd_list(_args: argparse.Namespace) -> int:
    from ost.core import detect_installed

    plat = current_platform()
    print(f"\n OST {__version__} - Office software from official servers\n")
    print(f" {'SUITE':<24}{'INSTALLED':<14}{'ON THIS OS (' + plat + ')'}")
    print("-" * 62)
    for p in list_providers():
        if p.supports_platform(plat):
            avail = f"[OK] directly installable"
        else:
            avail = f"[NO] native only on {', '.join(sorted(p.platforms))}"
        print(f" {p.slug:<24}{str(detect_installed(p.slug)) or '-':<14}{avail}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    async def run() -> None:
        if args.suite == "all":
            suites = [p.slug for p in list_providers()]
        else:
            suites = [args.suite]
        for slug in suites:
            res = await check_suite(slug)
            if not res.available:
                print(f" {res.name:<28} [not available on {res.platform}]")
                print(f"   {res.reason}")
                if args.json:
                    print(json.dumps({
                        "suite": res.suite, "installed": res.installed, "latest": None,
                        "available": False, "reason": res.reason, "platform": res.platform,
                    }))
                continue
            latest = res.latest or "-"
            installed = res.installed or "-"
            note = f" (error: {res.error})" if res.error else ""
            print(f" {res.name:<28} installed={installed:<12} latest={latest}{note}")
            if args.json:
                print(json.dumps({
                    "suite": res.suite, "installed": res.installed, "latest": res.latest,
                    "available": True, "error": res.error, "platform": res.platform,
                }))

    try:
        asyncio.run(run())
    except KeyError:
        print(f"Unknown suite: {args.suite}")
        print("Available:", ", ".join(p.slug for p in list_providers()))
        return 2
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    async def run() -> None:
        opts = {}
        if args.variant:
            opts["variant"] = args.variant
        if args.lang:
            opts["lang"] = args.lang
        out = args.out or downloads_dir()
        print(f" Downloading {args.suite} ...")
        path, asset = await download_suite(
            args.suite, progress=_progress_bars, dest_dir=Path(out), **opts
        )
        print(f"\n Saved: {path}  ({path.stat().st_size if path.exists() else 0} bytes)")

    try:
        asyncio.run(run())
    except KeyError:
        print(f"Unknown suite: {args.suite}")
        return 2
    except (RuntimeError, OSError) as e:
        print(f" Failed: {e}")
        return 1
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else None
    result = install_suite(args.suite, path=path, log=_log)
    print("\n " + result.message)
    if result.instructions:
        print(" " + result.instructions)
    return 0 if result.ok else 1


def cmd_update(args: argparse.Namespace) -> int:
    async def run() -> None:
        print(f" Updating {args.suite} (download + install) ...")
        result, path = await update_suite(args.suite, progress=_progress_bars, log=_log)
        if path:
            print(f"\n Downloaded: {path}")
        print(" " + result.message)
        if result.instructions:
            print(" " + result.instructions)

    try:
        asyncio.run(run())
    except KeyError:
        print(f"Unknown suite: {args.suite}")
        print("Available:", ", ".join(p.slug for p in list_providers()))
        return 2
    except (RuntimeError, OSError) as e:
        print(f" Failed: {e}")
        return 1
    return 0


def cmd_oct(args: argparse.Namespace) -> int:
    cfg = default_cfg()
    cfg["channel"] = args.channel or cfg["channel"]
    cfg["edition"] = args.edition or cfg["edition"]
    if args.products:
        cfg["products"] = args.products.split(",")
    xml = build_configuration_xml(cfg)
    if args.write:
        p = save_configuration_xml(cfg, args.write)
        print(f" Written: {p}")
    else:
        print(xml)
    return 0


def cmd_oct_info(_args: argparse.Namespace) -> int:
    print(" ## Office Deployment Tool (ODT) reference data")
    print("\n ## ODT download")
    print("   " + ODT_PAGE)
    print("\n ## Channels")
    for ch, label, note in CHANNELS:
        print(f"  {ch:<24} {label}")
    print("\n ## Languages (WLC) - first is primary, rest added")
    print("  " + ", ".join(w for w, _ in LANGUAGES))
    print("\n ## Products")
    for cat, items in PRODUCT_CATALOG:
        print(f"  [{cat}]")
        for pid, label in items:
            print(f"   {pid:<22} {label}")
    return 0


def cmd_tui(_args: argparse.Namespace) -> int:
    try:
        from ost.tui.app import main as tui_main
    except ImportError as e:
        print("TUI requires 'textual'. Install with: pip install 'ost[tui]'")
        print(f" ({e})")
        return 1
    return tui_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ost",
        description="Office Suite Toolkit - check, download, install and update office software "
        "from official servers, including an ODT/OCT-style configurator for Microsoft Office.",
    )
    parser.add_argument("--version", action="version", version=f"ost {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("list", help="List available office suites")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("check", help="Check latest + installed version")
    p.add_argument("suite", help="suite slug or 'all'")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("download", help="Download installer for a suite")
    p.add_argument("suite")
    p.add_argument("-o", "--out", type=Path)
    p.add_argument("--variant", choices=["deb", "rpm", "msi", "auto"], help="Linux packaging (LibreOffice/OpenOffice)")
    p.add_argument("--lang", help="Language for Apache OpenOffice (e.g. en-US, de, fr)")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("install", help="Install a downloaded suite")
    p.add_argument("suite")
    p.add_argument("path", nargs="?", help="path to installer file (optional)")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("update", help="Update a suite (download latest + install)")
    p.add_argument("suite")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("oct-config", help="Generate Microsoft Office configuration.xml (OCT clone)")
    p.add_argument("--channel", help="channel, e.g. PerpetualVL2024, MonthlyEnterprise")
    p.add_argument("--edition", choices=["32", "64"])
    p.add_argument("--products", help="comma separated product IDs, e.g. ProPlus2024Volume,ProjectPro2024Volume")
    p.add_argument("-w", "--write", type=Path)
    p.set_defaults(func=cmd_oct)

    p = sub.add_parser("oct-info", help="Show ODT products, channels, languages")
    p.set_defaults(func=cmd_oct_info)

    p = sub.add_parser("tui", help="Launch the terminal user interface")
    p.set_defaults(func=cmd_tui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return cmd_tui(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())