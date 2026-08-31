# OST — Office Suite Toolkit

A terminal tool to **check, download, install and update** office software, always
fetched from the **official servers** of each vendor:

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

```
python main.py        # animated terminal UI
python main.py check all
python -m ost list
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

## License

MIT.