# FUTURE UPGRADES — OST Roadmap

Planned and proposed upgrades. Nothing here is implemented yet; this is the
wish-list and engineering plan for the next versions of OST.

**Priority legend:** 🟢 short term · 🟡 medium term · 🔵 nice-to-have

---

## 1. Web interface (browser app) — ✅ implemented in v0.2.0

> Done. `ost web` serves a local, zero-dependency web app (stdlib only) with
> list/check/download/install/update + the full ODT/OCT configurator, live job
> progress and logs, and optional `--host 0.0.0.0 --token` LAN mode. Remaining
> ideas below are refinements.

The biggest usability jump: manage office software from any browser — including
phones/tablets and remote machines — with zero install on the client.

- `ost serve` — start a local web server exposing the full manager.
  - Default binds `127.0.0.1`; `--host 0.0.0.0` for LAN access from other devices.
  - Optional auth token (`--token`) so the LAN mode is safe.
- Same screens and actions as the TUI/CLI: `list`, `check`, `download`,
  `install`, `update`, and the full ODT/OCT configurator.
- **REST API + WebSocket** for live download/install progress (reuse the same
  engine + cache; no duplicated logic).
- Mobile-friendly layout (touch controls) — the phone becomes a remote control
  for office installs on the desktop/server.
- Security-first: localhost-only by default, token auth, CSRF-safe, no external
  network calls (all data still fetched from official vendor servers).

## 2. GUI interface (desktop app)

A real windowed app for users who won't touch a terminal.

- New `ost gui` entry point / `ost-gui` binary, reusing the exact same engine as
  CLI and TUI (single source of truth for logic).
- Implementation options to evaluate:
  1. **Tkinter** — already present with Python, zero new dependencies, small.
  2. **PySide6/Qt** — richer widgets/tables, larger bundle.
  3. **pywebview WebView** wrapping the web interface (best reuse of #1).
- Auto-open GUI when the binary is run with no TTY (double-click on Windows/macOS
  currently opens a console — window apps should *not* show a terminal).
- System tray icon with Notifications on download/install completion.

## 3. Fixes & hardening (short term)

- **Code signing** — macOS notarization and Windows Authenticode so users stop
  seeing SmartScreen / Gatekeeper warnings.
- **aarch64 Linux binary** via GitHub ARM runners; optional Windows x86-32 build.
- **SHA-256 verification** of every downloaded installer before use.
- **Resumable downloads** (HTTP Range) with httpx + stdlib fallback, cached across
  sessions.
- **`ost self-update`** — check for a newer version, download and hot-swap the
  running binary / reinstall the wheel.
- **PyPI release** (`pip install ost`) — solves Android/Termux and script pipelines.
- **Automated tests** — pytest suite for core, providers, installer and ODT config;
  a CI test job that runs on every PR.
- **MSOffice ODT/OCT enhancements** — multiple languages per product,
  `UpdatesEnabled`, `OfficeMgmtCOM`, display-level variants, `/extract` preset
  selection, acceptance/PIN-in flags.
- **Offline bundle mode** — stage every file needed for a suite, then install on an
  air-gapped machine.
- Structured logging + a crash report file that is easy to attach to issues.

## 4. Packaging & distribution (medium term)

- Linux **AppImage** and **Flatpak**.
- Windows **NSIS installer** with Start-Menu entry and uninstaller.
- macOS **.dmg** containing a proper `.app` bundle.
- **Docker/OCI image** for servers and cloud VMs: `docker run <image> ost serve`.

## 5. Platforms

- **Full Android support** — drive installs inside proot/box64 so suites actually
  install, not just download (currently possible via Termux scripts).
- **Chromebook (Crostini)** verification.
- FreeBSD/OpenBSD best-effort support.

## 6. Nice-to-haves (backlog)

- Web UI prints a **QR code** to open it from a phone on the LAN.
- **Mirror selection** + speed test for downloads.
- Detect a running Office suite and prompt before install/update.
- Extra suites: OnlyOffice Desktop, FreeOffice, Calligra, Collabora.
- Dashboard screen — storage used, available update badges for all suites.
- Playwright/E2E coverage for the TUI and web UI.
- i18n of UI strings (first: Mandarin, Hindi, Bangla, Arabic, Spanish).