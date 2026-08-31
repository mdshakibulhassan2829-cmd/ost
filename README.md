# OST — Office Suite Toolkit

> by **MD. Shakibul Hassan (Shuvo)**

A terminal tool to **check, download, install and update** office software, always
fetched from the **official servers** of each vendor — now with a **web interface**
too, and a graphical UI on the way:

| Suite | Vendor | Official source used |
|-------|--------|----------------------|
| LibreOffice | The Document Foundation | `download.documentfoundation.org` |
| Microsoft Office (Microsoft 365 / Office LTSC) | Microsoft | Microsoft Download Center + Office Deployment Tool (ODT) |
| WPS Office | Kingsoft | `linux.wps.cn` / `wps.com` |
| Apache OpenOffice | Apache Software Foundation | `dlcdn.apache.org/openoffice` |

For Microsoft Office it includes a full **ODT + OCT-style configurator**: pick
products, channels, languages, excluded applications, update policies, silent
install/display options and activation keys, exactly like Microsoft's *Office
Customization Tool* — it generates the real `configuration.xml` and drives
`setup.exe /download`, `/configure` and `/extract`.

## Quick start

Run with **no arguments** and OST asks which interface you prefer:

```
ost                # choose: 1) Terminal UI  2) Web interface  3) GUI (coming soon)
```

```
ost tui            # straight into the terminal UI
ost web            # open the web interface in your browser (http://127.0.0.1:8765)
ost list           # normal CLI
ost check all
python main.py     # when running from source (same interface chooser)
```

## Install

Requires Python 3.10+.

```
python -m pip install -e .      # core tool (stdlib only for check/download)
python -m pip install -e ".[tui]"   # + the terminal UI (textual)
python -m pip install -e ".[http]"  # optional faster networking (httpx)
```

If `httpx` is missing the tool transparently falls back to the Python standard
library, so `check`/`download` work with zero extra dependencies.

## Binary downloads (no Python needed)

Single-file executables are built by GitHub Actions and published with each
**release** (tag `v0.1.0`, `v0.1.1`, …). **No Python or pip is required** — just
download, run, done:

| Platform | Asset | Run |
|----------|-------|-----|
| Linux (x86_64) | `ost-linux-x86_64` | `chmod +x ost-linux-x86_64 && ./ost-linux-x86_64` |
| Windows (x86_64) | `ost-windows-x86_64.exe` | double-click, or `ost-windows-x86_64.exe list` in a terminal |
| macOS | `ost-macos` | `chmod +x ost-macos && ./ost-macos` |

Each binary, when run with no arguments, shows the **interface chooser**
(Terminal UI / Web interface / GUI-coming-soon) and behaves as the CLI below
when given arguments. macOS users on an unsigned-notarized binary may need
right-click → Open the first time; Windows SmartScreen just needs
"More info → Run anyway" (signing can be added later if you want it gone).

## Android / Termux

Termux uses the official Python wheel instead of a binary (PyInstaller does not
support Android). On Termux:

```
pkg install python
pip install ost                     # installs the latest release wheel
ost                                 # opens the TUI
ost check all                       # or use it as the CLI
```

> Tip: if the latest release wheel isn't on PyPI yet, install straight from the
> release Assets: `pip install "https://github.com/<user>/ost/releases/download/v0.1.0/ost-0.1.0-py3-none-any.whl[all]"`.

## CLI

```
python main.py                     # same as: python -m ost
```

Every workflow first checks whether the selected suite is **natively available on
the current OS**. `ms-office` (its `setup.exe`) is Windows-only, so on Linux/macOS
OST reports it as unavailable for install/deploy while the OCT configurator still
works to prepare `configuration.xml` for a Windows machine.

```
ost list                          # suites + availability on this OS
ost check all                     # check latest version on official servers
ost check libreoffice

ost download libreoffice          # download for the current OS/arch
ost download openoffice --lang de
ost download wps --out /media/usb
ost download ms-office            # fetch the official ODT package (setup.exe)

ost install libreoffice [path to .tar.gz/.deb/.msi/.dmg]
ost install openoffice
ost update libreoffice            # download latest + install

ost oct-config --products ProPlus2024Volume,VisioPro2024Volume --channel PerpetualVL2024
ost oct-config -w configuration.xml
ost oct-info                      # every ODT product / channel / language id
ost tui                           # launch the terminal UI
```

Installs on Linux use `dpkg`/`rpm` (auto `sudo` when needed), on Windows
`msiexec`/`setup.exe /configure`, on macOS the disk image / app bundle.
Run `python -m ost` (or `python main.py`) with no arguments to launch the TUI.

## TUI

`ost tui` (or `ost-tui`, or just `python main.py`) opens the animated terminal
interface (Textual + Rich):

- **Home** — every suite with installed/latest status, availability badge for the
  current OS, an animated gradient marquee and a "check all" action with live spinner.
- **Suite screen** — check, download, install, update with an animated activity
  pulse, live progress bar and log.
- **Microsoft Office screen** — the ODT/OCT configurator (works on every OS; the
  Windows-only ODT buttons are labelled accordingly on non-Windows):

  - **Products & languages** — checkbox list of suites (M365, Office LTSC 2024/2021/2019/2016,
    Visio, Project, single apps), a primary language picker and excluded apps.
  - **Deployment** — channel (Monthly Enterprise, Current, Semi-Annual,
    Perpetual LTSC…), 64/32-bit, LTSC version pin, source path, update policy/path,
    and "remove MSI versions" cleanup.
  - **Advanced** — display level (Full / silent None), Accept EULA, AUTOACTIVATE,
    FORCEAPPSHUTDOWN, product key (PIDKEY), company/user, logging.
  - **Configuration.xml** — live, syntax-coloured preview; every change is saved to disk.
  - Action bar — *Download ODT tool*, *Download Office files* (`/download`),
    *Install (configure)* (`/configure`), *Extract files* (`/extract`).

### ODT/OCT behaviour note

Microsoft periodically switches the ODT package between a `.zip` and a
self-extracting `officedeploymenttool_*.exe`. OST detects both, extracts
`setup.exe`, writes `configuration.xml` next to it, and invokes the ODT exactly
as the Microsoft docs describe. If Microsoft hides the direct link from a
given client, OST tells you to grab the package from the official Microsoft
Download Center and re-run — it is then picked up automatically.

## Web interface

`ost web` (or `ost-web`, or option 2 of the launcher) serves a local, browser
based version of everything the TUI does — no extra install. Defaults to
`http://127.0.0.1:8765`.

```
ost web                              # local only, zero setup
ost web --port 9000
ost web --host 0.0.0.0 --token my-secret    # reach it from phones/LAN devices
```

- **Check, download, install, update** any suite, with live progress and logs.
- Full **Microsoft ODT/OCT configurator** (products, channel, language, edition,
  PIDKEY) with live `configuration.xml` preview and save.
- Every install/update first notifies you that **root/administrator permission is
  being requested** for the system (sudo on Linux, UAC on Windows, password on
  macOS) — follow the system prompt and it finishes the job.
- The web app needs only the Python standard library (it is bundled inside the
  single-file binaries too).

## Data locations (Linux shown)

| What | Where |
|------|-------|
| Downloads | `~/.local/share/ost/downloads/<suite>/` |
| MS config (`configuration.xml`) | `~/.config/ost/ms_office_configuration.xml` |
| MS selections (OCT state) | `~/.config/ost/config.json` |

## Platform notes

- OST auto-detects the OS (`linux`, `macos`, `windows`) and only offers actions a
  suite actually supports there — `ost list`/`ost check` and the TUI mark `ms-office`
  as Windows-only on other systems, and its check/download/install buttons are
  disabled while the ODT/OCT configurator stays usable to build `configuration.xml`.
- **Microsoft Office** installing/deploying requires Windows; on other OSes OST
  still downloads the ODT and gives you the exact command to run on a Windows PC.
- **WPS Office** only publishes x86_64 Linux builds; on aarch64/arm64 the tool
  reports the available package but installing it needs an x86_64 machine (or an
  emulator like box64).
- macOS paths use `ditto` to install `.app` bundles and `installer` for `.pkg`.
- Installing a suite requests **root/administrator permission** on your system and
  opens a `sudo` password prompt (Linux), a UAC prompt (Windows) or a password
  prompt (macOS). OST notifies you first and blocks until you allow it.
- **Android / Termux**: installs inside the proot need the suite's packages to be
  installable there; download/check/update and the web UI work fully.

## License

MIT.