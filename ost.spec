# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the OST single-file app.

Build (from repo root):
    pyinstaller --noconfirm --clean ost.spec
Entry point is main.py: no arguments -> interface chooser, otherwise -> CLI.
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

datas, binaries, hiddenimports = [], [], []

# textual bundles a lot of runtime-loaded CSS/JSON and plugin modules; the
# TUI breaks in a frozen binary unless we collect all of it.
for pkg in ("textual", "rich"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
    datas += copy_metadata(pkg, recursive=True)

# The ost package itself, including every submodule (covers the function-level
# lazy imports in cli.py / core.py / installer.py).
for pkg in ("ost",):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
    hiddenimports += collect_submodules(pkg)
    try:
        datas += copy_metadata(pkg, recursive=True)
    except Exception:  # noqa: BLE001 -- package need not be installed to freeze
        pass

# Belt-and-braces: stdlib modules referenced lazily inside functions.
hiddenimports += [
    "urllib.request",
    "zipfile",
    "tarfile",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "test", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)