# AGENTS.md — Memory file for the OST project

Read this file first when starting a session. It is the quick-reference so you
don't need to re-explore the whole codebase. Keep it up to date as the project
changes.

## What this is

**OST — Office Suite Toolkit** (`ost`). A cross-platform (Linux/macOS/Windows)
CLI + Terminal UI (textual) + Web UI that **checks, downloads, installs and
updates** office suites, always pulling from each vendor's **official servers**:

| Suite | Provider module |
|-------|-----------------|
| LibreOffice | `ost/providers/libreoffice.py` |
| Microsoft Office (ODT/OCT config) | `ost/providers/msoffice.py` |
| WPS Office | `ost/providers/wps.py` |
| Apache OpenOffice | `ost/providers/openoffice.py` |

Plus a **Microsoft ODT/OCT configurator** that generates the real
`configuration.xml` for the Office Deployment Tool.

Current version: **0.2.0**. Author: **MD. Shakibul Hassan (Shuvo)**.
Remote: `https://github.com/mdshakibulhassan2829-cmd/ost.git` (branch `main`).

## THE VENV (critical — don't use system python)

The project's working Python is **`~/ost-venv/bin/python`** (Python 3.10.12).
It has `textual` (8.x), `httpx`, `rich`, and `ost` installed **editable**.
Use it for everything (running, tests, building). **Do NOT use the system
`python3`** — it lacks textual/httpx.

```bash
~/ost-venv/bin/python -m ost list        # CLI (also: ~/ost-venv/bin/ost ...)
~/ost-venv/bin/python -m ost web         # web UI on http://127.0.0.1:8765
~/ost-venv/bin/python -c "from ost.tui.app import main; main()"   # TUI
```

The venv lacked `pip`, so (re)install deps with:
```bash
~/ost-venv/bin/python -m pip install -e ".[all]"
```
This also refreshes the `ost`, `ost-tui`, `ost-web` console scripts.

## Entry points

- `main.py` → `ost/cli.py:main`
- `ost/__main__.py` → `ost.cli:main` (so `python -m ost` works)
- Console scripts in `pyproject.toml [project.scripts]`: `ost` (CLI),
  `ost-tui` (TUI main), `ost-web` (web main).

**Launcher behavior:** running with NO arguments shows an interactive interface
chooser (1=TUI, 2=Web, 3=GUI-coming-soon, 0=quit) implemented in
`ost/cli.py:launcher()`. Subcommands (`list`, `check`, `download`, `install`,
`update`, `oct-config`, `oct-info`, `tui`, `web`, `gui`) go straight to the
action. `gui` is a stub ("coming soon").

## Architecture / module map

- `ost/core.py` — platform detection, dirs, version parsing, `run`/`run_root`
  (sudo/UAC/password elevation), `detect_installed`, `notify` (desktop
  notification, best-effort), MS config load/save (`ms_config_data`,
  `save_ms_config`).
- `ost/actions.py` — orchestration: `check_suite`, `download_suite`,
  `install_suite`, `update_suite`. `install_suite` emits a `privilege_notice`
  + `notify()` before every elevated install.
- `ost/installer.py` — `InstallResult`, `privilege_notice`, extract/install
  logic, MS `run_odt`.
- `ost/net.py` — download (httpx or stdlib fallback) + cache.
- `ost/cli.py` — argparse CLI + launcher menu.
- `ost/web.py` — **zero-dependency (stdlib only)** web server
  (`ThreadingHTTPServer` + embedded HTML page). Uses a background `Job`/`Jobs`
  system for live progress/logs. API under `/api/*`:
  `state`, `oct-meta`, `oct-config`, `job/check/download/install/update`,
  `jobs`. Optional `--host 0.0.0.0 --token` LAN mode.
- `ost/tui/app.py` — textual app (`main()`), mirrors CLI + full OCT
  configurator.
- `ost/providers/` — provider classes; registry in `__init__.py`
  (`list_providers()`, `get_provider(slug)`), each has `.slug`, `.name`,
  `.vendor`, `.official_url`, `.supports_platform(plat)`,
  `.install_modes()`, `.check()/.download()` style methods.

Cross-platform intentionally: MS Office needs Windows for native install
(sets up an 800MB download though); on Linux/macOS the OCT configurator still
works to build `configuration.xml` for a Windows machine.

## Tests / verification

There is **no automated test suite yet** (it's a roadmap item, see
`FUTURE_UPGRADE.md`). Verify changes with:
```bash
~/ost-venv/bin/python -m compileall -q ost/ main.py
~/ost-venv/bin/python -m ost list
~/ost-venv/bin/python -m ost check all        # live network — may be slow
~/ost-venv/bin/python -m ost web --port 8899 --no-browser  # then curl /api/state
```
(Note: the web `/api/state` first `curl` right after startup can race and
return empty — just retry.)

## Data locations (Linux shown)

Under the platform data/config base: config dir, data dir, downloads dir, and
`ms-config.json` — all defined in `ost/core.py` (`config_dir`, `data_dir`,
`downloads_dir`, `ms_config_path`).

## Building binaries

- `ost.spec` = PyInstaller spec (collects `textual`/`rich`/`ost` wholesale;
  note the fixed entry in `ost.spec` was updated to say "interface chooser").
- `build.sh` (Linux/macOS) and `build.ps1` (Windows) produce `dist/ost` /
  `dist/ost.exe`.
- `.github/workflows/build.yml` — CI matrix (ubuntu/windows/macos) building
  one-file binaries + smoke test on main branch and `v*` tags.

## Roadmap / future work

See **`FUTURE_UPGRADE.md`** for the full wishlist. Status highlights:
- ✅ Web interface (done in v0.2.0).
- 🟡 GUI desktop app (`ost gui`) — planned, not implemented.
- 🟡 aarch64 Linux binary, code signing, SHA-256 verification, resumable
  downloads, `ost self-update`, PyPI release, pytest suite.
- 🔵 QR code in web UI, mirror selection, extra suites (OnlyOffice, etc.).

## Git conventions

- Commit messages: short imperative, matching existing style (e.g. "Add
  PyInstaller spec, build scripts, CI workflow, and docs"). Only commit/push
  when explicitly asked.
- The next expected release bump is from `0.2.0`. Keep `__version__` in
  `ost/__init__.py` and `version` in `pyproject.toml` in sync.
