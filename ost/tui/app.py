"""OST - Office Suite Toolkit (terminal user interface)."""

from __future__ import annotations

import asyncio
import math
import re
import threading
from pathlib import Path
from typing import Callable

from rich.markup import escape as markup_escape
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    Log,
    ProgressBar,
    Rule,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from ost import __version__
from ost.actions import check_suite, download_suite, install_suite
from ost.core import (
    current_platform,
    detect_installed,
    ms_config_data,
    save_ms_config,
)
from ost.providers import get_provider, list_providers
from ost.providers.base import Provider
from ost.providers.msoffice import (
    CHANNELS,
    EXCLUDE_APPS,
    LANGUAGES,
    PRODUCT_CATALOG,
    build_configuration_xml,
    default_cfg,
    save_configuration_xml,
)
from ost.tui.widgets import Marquee, Spinner, gradient_text

CSS = """
Screen { layout: vertical; background: #060910; scrollbar-size: 1 1; }

Footer { background: #0a0f1a; color: $text-muted; }

/* ----- shared top bar ----- */
.topbar { height: 3; padding: 0 3; }
.top-title { text-style: bold; }
.top-right { dock: right; color: $text-muted; }

/* ----- home ----- */
#home-hero { padding: 2 4 0 4; content-align: center top; }
#home-title {
    width: 100%;
    padding: 0;
    height: 1;
}
#home-tagline { width: 100%; content-align: center middle; }
#home-marquee, #suite-marquee, #oct-marquee { margin: 1 2 0 2; }

.muted { color: $text-muted; }
.url { color: $accent; }

#home-list { height: 1fr; padding: 1 2 0 2; }
.suite-card {
    border: round #1c2b44;
    background: #0a0f1a;
    padding: 0 2;
    margin: 0 0 1 0;
    height: 6;
}
.suite-card:hover, .suite-card:focus-within {
    border: round $accent;
    background: #0e1526;
}
.card-name { text-style: bold; }
.card-desc { margin: 0 0 0 0; color: $text-muted; }
.card-status { margin: 0; color: $text; }
.card-btn { dock: right; width: 12; height: 3; margin-top: 1; }

.home-cta-row { padding: 0 3; margin: 0 0 1 0; height: 3; }
.home-cta-row Button { min-width: 26; margin-right: 2; }
#btn-check-all { background: $accent; color: $background; text-style: bold; }
#home-spinner { display: none; width: 46; }

/* ----- buttons ----- */
Button {
    background: #101828;
    border: none;
    min-width: 12;
    height: 3;
}
Button:disabled { background: $surface; color: $text-disabled; }
Button:focus, Button:hover { background: $accent; color: $background; }
Button.cta { background: $accent; color: $background; text-style: bold; }
Button.act { margin: 0 1 0 0; }

/* ----- suite / oct ----- */
.suite-head, .oct-head { padding: 1 3 0 3; }
#suite-actions, #oct-actions { padding: 0 3; margin: 1 0 0 0; }
#suite-progress, #oct-progress {
    height: 1;
    margin: 1 3 0 3;
    background: $panel;
}
.log-head { padding: 1 3 0 3; }
#suite-log, #oct-log {
    height: 1fr;
    border: round #1c2b44;
    margin: 0 3 1 3;
    padding: 0 1;
    background: #070b12;
}
#suite-note { padding: 0 3; color: $warning; }
#oct-note { padding: 0 3 0 0; color: $warning; }

/* ----- OCT form ----- */
TabbedContent { background: $panel; border: round #1c2b44; margin: 0 3 1 3; height: auto; }
TabPane { padding: 0 2; }
.tabhead { text-style: bold; color: $accent; margin: 1 0; }
.field-label { width: 30; height: 1; text-style: dim; margin-top: 1; color: $text-muted; }
.row { height: 3; align: left middle; }
Select, Input { width: 1fr; background: $panel; border: tall #1c2b44; }
Checkbox { padding: 0 0 0 2; }

#oct-preview {
    border: round $accent;
    padding: 1 2;
    overflow: auto;
    color: $text;
    background: #0b1118;
}
.prod-group { margin: 0 2 1 0; }
"""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _readable_size(n: int | None) -> str:
    if not n:
        return "-"
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            if unit == "B":
                return f"{n} B"
            return f"{n / 1024:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} GiB"


def _sel(options: list[tuple[str, str]], value: str, id: str) -> Select:
    values = [v for _, v in options]
    return Select(options=options, value=value if value in values else None, id=id)


def _topbar(title: str, sub: str = "") -> Container:
    return Container(
        Label(f"[b]{title}[/b]  [dim]{sub}[/dim]", classes="top-title"),
        Label(f"[dim]OST v{__version__} · {current_platform()}[/dim]", classes="top-right"),
        classes="topbar",
    )


def _xml_rich(text: str) -> str:
    """Syntax-colour a configuration.xml document as Rich markup."""
    esc = markup_escape(text)
    ATTRS = re.compile(r'(\w[\w-]*)="([^"]*)"')
    TAG = re.compile(r"(</?[A-Za-z][\w-]*)([^>]*?)(/?>)")

    def attrs(m: re.Match) -> str:
        return f"[magenta]{m.group(1)}[/][dim]=[/][green]\"{m.group(2)}\"[/]"

    def repl(m: re.Match) -> str:
        head = m.group(1)
        inside = ATTRS.sub(attrs, m.group(2))
        close = m.group(3)
        return f"[cyan]{head}[/]{inside}[cyan]{close}[/]"

    return TAG.sub(repl, esc)


class _LogStream:
    """Thread-safe line buffer drained on the UI thread."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def write(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)

    def drain(self) -> list[str]:
        with self._lock:
            lines, self._lines = self._lines, []
            return lines


async def _run_blocking(log: Log, fn: Callable[[Callable[[str], None]], object]) -> object:
    """Run a blocking call in a thread while streaming its logs into a Log.

    Widget updates only ever happen on the Textual (main) thread, so there are
    no cross-thread rendering glitches and long installs stay animated.
    """
    stream = _LogStream()
    task = asyncio.create_task(asyncio.to_thread(fn, stream.write))
    while not task.done():
        for line in stream.drain():
            log.write(line)
        await asyncio.sleep(0.06)
    try:
        result = task.result()
    except Exception as e:
        for line in stream.drain():
            log.write(line)
        log.write(f"[red]error:[/red] {e}")
        raise
    for line in stream.drain():
        log.write(line)
    return result


# ---------------------------------------------------------------------------
# screens
# ---------------------------------------------------------------------------


class HomeScreen(Screen):
    BINDINGS = [("q", "app.quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.title = "Home"
        self._cards: dict[str, tuple[Static, Button]] = {}

    def compose(self) -> ComposeResult:
        yield _topbar("Home", "check · download · install · update")
        yield Container(
            Static(gradient_text("OST"), id="home-title"),
            Label("[dim]office software, straight from the official servers[/dim]", id="home-tagline"),
            Marquee(id="home-marquee"),
            id="home-hero",
        )
        yield VerticalScroll(*self._suite_cards(), id="home-list")
        yield Horizontal(
            Button("Check all suites online", id="btn-check-all"),
            Spinner("checking online availability …", id="home-spinner"),
            classes="home-cta-row",
        )
        yield Footer()

    def _suite_cards(self) -> list[Container]:
        plat = current_platform()
        cards: list[Container] = []
        for p in list_providers():
            avail = p.supports_platform(plat)
            installed = detect_installed(p.slug)
            if installed:
                chip = f"[green]● installed {installed}[/]"
            elif avail:
                chip = "[dim]○ not installed[/]"
            else:
                chip = f"[red]✖ not available on {plat}[/]"
            only = "" if avail else f"  [red]({', '.join(sorted(p.platforms))} only)[/]"
            status_label = Static(
                f"[dim]latest:[/dim] [cyan]checking…[/cyan]   {chip}",
                id=f"status-{p.slug}",
                classes="card-status",
            )
            open_btn = Button("Open", id=f"open-{p.slug}", classes="card-btn")
            card = Container(
                Label(f"[b]{p.name}[/b]  [dim]{p.vendor}[/dim]{only}", classes="card-name"),
                Label(p.description, classes="muted card-desc"),
                status_label,
                open_btn,
                classes="suite-card",
                id=f"card-{p.slug}",
            )
            self._cards[p.slug] = (status_label, open_btn)
            cards.append(card)
        return cards

    @on(Button.Pressed, "#btn-check-all")
    async def _check_all(self) -> None:
        button = self.query_one("#btn-check-all", Button)
        spinner = self.query_one("#home-spinner", Spinner)
        button.disabled = True
        spinner.styles.display = "block"
        spinner.start()
        try:
            for slug, (status_label, _btn) in self._cards.items():
                res = await check_suite(slug)
                if not res.available:
                    status_label.update(
                        f"[dim]latest:[/dim] [yellow]—[/]      [red]{res.reason}[/]"
                    )
                    continue
                ver = res.latest or "unknown"
                installed = res.installed or "not installed"
                color = "green" if res.installed else "yellow"
                ex = f"  [red]{res.error}[/]" if res.error else ""
                status_label.update(
                    f"[dim]latest:[/dim] [b][cyan]{ver}[/cyan][/b]   "
                    f"[{color}]installed: {installed}[/]{ex}"
                )
        finally:
            spinner.stop("")
            spinner.styles.display = "none"
            button.disabled = False

    @on(Button.Pressed, "Button.card-btn")
    def _open_suite(self, event: Button.Pressed) -> None:
        slug = event.button.id.removeprefix("open-")
        self.app.push_screen(SuiteScreen(slug))


class SuiteScreen(Screen):
    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("c", "check", "Check online"),
        ("d", "download", "Download"),
        ("i", "install", "Install"),
        ("u", "update", "Update"),
    ]

    def __init__(self, slug: str) -> None:
        super().__init__()
        self.slug = slug
        self.provider: Provider = get_provider(slug)
        self.title = self.provider.name
        self.latest = None
        self.installed: str | None = None
        self.install_path: Path | None = None
        self.supported = self.provider.supports_platform(current_platform())
        self._unsupported: str = ""
        self._pulse_timer = None
        self._pulse_phase = 0.0

    @property
    def _is_ms(self) -> bool:
        return self.slug == "ms-office"

    def compose(self) -> ComposeResult:
        yield _topbar(self.provider.name, self.provider.vendor)
        yield Container(
            Label(self.provider.description, classes="muted"),
            Label(self.provider.official_url or "", classes="muted url"),
            Label("", id="suite-status"),
            Label("", id="suite-note"),
            classes="suite-head",
        )
        yield Horizontal(
            Button("Check online", id="act-check", classes="act"),
            Button("Download", id="act-download", classes="act"),
            Button("Install", id="act-install", classes="act"),
            Button("Update", id="act-update", classes="act"),
            *([Button("ODT / OCT config", id="act-oct", classes="act cta")] if self._is_ms else []),
            id="suite-actions",
        )
        yield Marquee(id="suite-marquee")
        yield Static("activity log", classes="muted log-head")
        yield ProgressBar(total=100, show_eta=False, id="suite-progress")
        yield Log(highlight=True, id="suite-log")
        yield Footer()

    def on_mount(self) -> None:
        self.installed = detect_installed(self.slug)
        if not self.supported:
            self._unsupported = self.provider.unsupported_reason(current_platform())
            self._render_status()
            self._apply_platform_gate()
            note = self.query_one("#suite-note", Label)
            if self._is_ms:
                note.update(
                    f"[red]Windows only.[/] {self._unsupported}\n"
                    "The ODT / OCT configurator below still works on any OS - it builds "
                    "configuration.xml to use with setup.exe on a Windows machine."
                )
            else:
                note.update(f"[red]{self._unsupported}[/]")
            return
        self._render_status()
        self.run_worker(self._check(), group="suite", exclusive=True)
        if self._is_ms:
            cfg = {**default_cfg(), **ms_config_data()}
            save_ms_config(cfg)

    def on_unmount(self) -> None:
        self._pulse_stop()

    def _apply_platform_gate(self) -> None:
        for wid in ("#act-check", "#act-download", "#act-install", "#act-update"):
            try:
                self.query_one(wid, Button).disabled = True
            except Exception:
                pass

    def _render_status(self) -> None:
        if self._unsupported:
            self.query_one("#suite-status", Label).update(
                f"[dim]installed:[/dim] [b]{self.installed or 'not detected'}[/b]   "
            )
            return
        inst = self.installed or "not detected"
        latest = self.latest.version if self.latest else "unknown"
        size = _readable_size(self.latest.best_asset().size) if self.latest and self.latest.best_asset() else "-"
        self.query_one("#suite-status", Label).update(
            f"[dim]installed:[/dim] [b]{inst}[/b]   "
            f"[dim]latest online:[/dim] [b][cyan]{latest}[/cyan][/b]   "
            f"[dim]size:[/dim] {size}"
        )

    def _enable_actions(self, enabled: bool) -> None:
        if not self.supported:
            return
        for wid in ("#act-check", "#act-download", "#act-install", "#act-update"):
            try:
                self.query_one(wid, Button).disabled = not enabled
            except Exception:
                pass
        if self._is_ms and enabled:
            try:
                self.query_one("#act-oct", Button).disabled = False
            except Exception:
                pass

    # ----- smooth indeterminate pulse -----
    def _pulse_start(self) -> None:
        if self._pulse_timer is not None:
            return
        self._pulse_phase = 0.0
        self._pulse_timer = self.set_interval(0.08, self._pulse_tick)

    def _pulse_tick(self) -> None:
        try:
            bar = self.query_one("#suite-progress", ProgressBar)
        except Exception:
            return
        self._pulse_phase += 0.12
        # eased sweep 0 -> 100 -> 0 (sin decelerates at the ends)
        p = int((99.5 + 99.0 * -math.cos(self._pulse_phase)) * 0.5) % 100
        bar.update(progress=p, total=100)

    def _pulse_stop(self) -> None:
        if self._pulse_timer is not None:
            self._pulse_timer.stop()
            self._pulse_timer = None

    # ----- actions -----
    async def _check(self) -> None:
        self._pulse_start()
        res = await check_suite(self.slug)
        self._pulse_stop()
        if self.app.screen is not self:
            return
        self.latest = res.release
        self.installed = res.installed
        self._render_status()
        log = self.query_one("#suite-log", Log)
        if not res.available:
            log.write(f"[red]{res.reason}[/red]")
            return
        log.write(
            f"Checked official server for {self.provider.name}.\n"
            f"  online: {res.latest or 'no release found'}   installed: {res.installed or '-'}"
            + (f"   [red]{res.error}[/]" if res.error else "")
        )

    @on(Button.Pressed, "#act-check")
    def _on_check(self) -> None:
        if self.supported:
            self.run_worker(self._check(), group="suite", exclusive=True)

    @on(Button.Pressed, "#act-download")
    def _on_download(self) -> None:
        self._enable_actions(False)
        self.run_worker(self._download(), group="suite", exclusive=True)

    async def _download(self) -> None:
        if not self.supported:
            return
        bar = self.query_one("#suite-progress", ProgressBar)
        log = self.query_one("#suite-log", Log)

        def prog(done: int, total: int | None) -> None:
            if self.app.screen is not self:
                return
            bar.update(progress=done, total=total or done or 1)

        log.write(f"Downloading {self.provider.name} from official server ...")
        try:
            path, asset = await download_suite(self.slug, progress=prog)
        except Exception as e:
            if self.app.screen is self:
                log.write(f"[red]Download failed:[/red] {e}")
                bar.update(progress=0, total=100)
                self._enable_actions(True)
            return
        if self.app.screen is not self:
            return
        self.install_path = path
        log.write(f"[green]Saved:[/green] {path}")
        log.write(f"[green]Size:[/green] {_readable_size(asset.size)}")
        if not self._is_ms:
            log.write("[yellow]Tip:[/yellow] press [b]i[/b] to install the downloaded packages.")
        bar.update(progress=100, total=100)
        self._enable_actions(True)

    @on(Button.Pressed, "#act-install")
    def _on_install(self) -> None:
        self._enable_actions(False)
        self.run_worker(self._install(), group="suite", exclusive=True)

    async def _install(self) -> None:
        if self.app.screen is not self:
            return
        log = self.query_one("#suite-log", Log)
        cfg = {**default_cfg(), **ms_config_data()} if self._is_ms else None
        result: object = await _run_blocking(
            log,
            lambda cb: install_suite(self.slug, path=self.install_path, cfg=cfg, log=cb),
        )
        if self.app.screen is not self:
            return
        ok = bool(getattr(result, "ok", False))
        message = str(getattr(result, "message", ""))
        instructions = str(getattr(result, "instructions", ""))
        log.write(("[green]OK:[/green] " if ok else "[red]FAILED:[/red] ") + message)
        if instructions:
            log.write("[yellow]" + instructions + "[/yellow]")
        self.installed = detect_installed(self.slug)
        self._render_status()
        self._enable_actions(True)

    @on(Button.Pressed, "#act-update")
    def _on_update(self) -> None:
        self._enable_actions(False)
        self.run_worker(self._update(), group="suite", exclusive=True)

    async def _update(self) -> None:
        if not self.supported or self.app.screen is not self:
            return
        bar = self.query_one("#suite-progress", ProgressBar)
        log = self.query_one("#suite-log", Log)

        def prog(done: int, total: int | None) -> None:
            if self.app.screen is not self:
                return
            bar.update(progress=done, total=total or done or 1)

        cfg = {**default_cfg(), **ms_config_data()} if self._is_ms else None
        try:
            path, _asset = await download_suite(self.slug, progress=prog)
        except Exception as e:
            if self.app.screen is self:
                log.write(f"[red]Download failed:[/red] {e}")
                self._enable_actions(True)
            return
        if self.app.screen is not self:
            return
        self.install_path = path
        log.write(f"[green]Downloaded:[/green] {path}")
        result: object = await _run_blocking(
            log,
            lambda cb: install_suite(self.slug, path=path, cfg=cfg, log=cb),
        )
        if self.app.screen is not self:
            return
        ok = bool(getattr(result, "ok", False))
        log.write(("[green]OK:[/green] " if ok else "[red]FAILED:[/red] ") + str(getattr(result, "message", "")))
        instructions = str(getattr(result, "instructions", ""))
        if instructions:
            log.write("[yellow]" + instructions + "[/yellow]")
        self.installed = detect_installed(self.slug)
        self._render_status()
        self._enable_actions(True)

    @on(Button.Pressed, "#act-oct")
    def _open_oct(self) -> None:
        self.app.push_screen(OctScreen())

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_check(self) -> None:
        if self.supported:
            self.run_worker(self._check(), group="suite", exclusive=True)

    def action_download(self) -> None:
        self._on_download()

    def action_install(self) -> None:
        self._on_install()

    def action_update(self) -> None:
        self._on_update()


class OctScreen(Screen):
    """Microsoft Office ODT/OCT configurator."""

    BINDINGS = [("escape", "go_back", "Back"), ("s", "save", "Save config")]

    def __init__(self) -> None:
        super().__init__()
        self.title = "Microsoft Office - ODT / OCT configuration"
        self.cfg: dict = {**default_cfg(), **ms_config_data()}

    def compose(self) -> ComposeResult:
        yield _topbar("Microsoft Office", "ODT · OCT configurator")
        if current_platform() != "windows":
            yield Label(
                "[red]ODT setup.exe runs on Windows only.[/] On this OS the configurator "
                "still works: build configuration.xml here, then use it with setup.exe "
                "on a Windows PC.",
                id="oct-note",
            )
        with TabbedContent(id="oct-tabs"):
            with TabPane("Products & languages", id="tab-products"):
                yield self._products_panel()
            with TabPane("Deployment", id="tab-deploy"):
                yield self._deploy_panel()
            with TabPane("Advanced", id="tab-advanced"):
                yield self._advanced_panel()
            with TabPane("Configuration.xml", id="tab-xml"):
                yield self._xml_panel()
        yield Marquee(id="oct-marquee")
        yield Horizontal(
            Button("Download ODT tool", id="oct-dl-tool", classes="act"),
            Button("Download Office files", id="oct-dl", classes="act"),
            Button("Install (configure)", id="oct-install", classes="act cta"),
            Button("Extract files", id="oct-extract", classes="act"),
            Button("Save config.xml", id="oct-save", classes="act"),
            id="oct-actions",
        )
        yield ProgressBar(total=100, show_eta=False, id="oct-progress")
        yield Log(highlight=True, id="oct-log")
        yield Footer()

    def _panel(self, *children, vertical: bool = True) -> VerticalScroll:
        container_cls = VerticalScroll if vertical else Vertical
        return container_cls(*children)

    def _products_panel(self) -> VerticalScroll:
        groups: list[Vertical] = []
        for cat, items in PRODUCT_CATALOG:
            boxes = [
                Checkbox(label, value=pid in self.cfg["products"], id=f"prod-{pid}", classes="prod")
                for pid, label in items
            ]
            groups.append(
                Vertical(
                    Label(f"[b]{cat}[/b]", classes="tabhead"),
                    *boxes,
                    classes="prod-group",
                )
            )
        excl = [
            Checkbox(label, value=app in self.cfg["exclude_apps"], id=f"excl-{app}", classes="excl")
            for app, label in EXCLUDE_APPS
        ]
        lang_options = [(label, wlc) for wlc, label in LANGUAGES]
        lang = _sel(lang_options, self.cfg.get("primary_language") or "en-us", "oct-lang")
        return self._panel(
            Label("[b]Select products to install[/b]", classes="tabhead"),
            Label("Language IDs follow w.w.w-LCID2, e.g. en-us. Select a primary language:", classes="muted"),
            Horizontal(Label("Primary language", classes="field-label"), lang, classes="row"),
            Label("[b]Exclude applications[/b]", classes="tabhead"),
            *excl,
            *groups,
        )

    def _deploy_panel(self) -> VerticalScroll:
        c = self.cfg
        channels = [(f"{label}  [{note}]", ch) for ch, label, note in CHANNELS]
        channel = _sel(channels, c["channel"], "oct-channel")
        edition = _sel([("64-bit", "64"), ("32-bit", "32")], c["edition"], "oct-edition")
        update_chan = _sel(
            [("(inherit from channel)", "")] + channels,
            c.get("update_channel") or "",
            "oct-update-channel",
        )
        return self._panel(
            Label("[b]Channel & architecture[/b]", classes="tabhead"),
            Horizontal(Label("Update / install channel", classes="field-label"), channel, classes="row"),
            Horizontal(Label("Architecture", classes="field-label"), edition, classes="row"),
            Horizontal(
                Label("Version pin (LTSC, e.g. 16.0.xxxxx)", classes="field-label"),
                Input(value=c.get("version", ""), placeholder="optional", id="oct-version"),
                classes="row",
            ),
            Horizontal(
                Label("Source path (\\\\server\\share or local)", classes="field-label"),
                Input(value=c.get("source_path", ""), placeholder="optional", id="oct-source"),
                classes="row",
            ),
            Rule(classes="spacing"),
            Label("[b]Updates[/b]", classes="tabhead"),
            Checkbox("Enabled (recommended)", value=c.get("update_enabled", True), id="oct-update-enable"),
            Horizontal(Label("Update channel", classes="field-label"), update_chan, classes="row"),
            Horizontal(
                Label("Update path (local share)", classes="field-label"),
                Input(value=c.get("update_path", ""), placeholder="optional", id="oct-update-path"),
                classes="row",
            ),
            Rule(classes="spacing"),
            Label("[b]Cleanup[/b]", classes="tabhead"),
            Checkbox("Remove all MSI versions of Office first", value=c.get("remove_msi", False), id="oct-remove-msi"),
        )

    def _advanced_panel(self) -> VerticalScroll:
        c = self.cfg
        disp = _sel(
            [("None - fully silent", "None"), ("Full - show setup UI", "Full")],
            c.get("display_level", "Full"),
            "oct-display",
        )
        loglvl = _sel(
            [("Off", "Off"), ("Standard", "Standard"), ("Verbose", "Verbose")],
            c.get("logging_level", "Off"),
            "oct-logging",
        )
        return self._panel(
            Label("[b]Setup & activation[/b]", classes="tabhead"),
            Horizontal(Label("Setup display level", classes="field-label"), disp, classes="row"),
            Checkbox("Accept EULA", value=c.get("accept_eula", True), id="oct-eula"),
            Checkbox("Auto-activate (AUTOACTIVATE)", value=c.get("autoactivate", True), id="oct-autoactivate"),
            Checkbox(
                "Force close open Office apps (FORCEAPPSHUTDOWN)",
                value=c.get("force_app_shutdown", True),
                id="oct-force-shutdown",
            ),
            Rule(classes="spacing"),
            Label("[b]Product key & identity[/b]", classes="tabhead"),
            Horizontal(
                Label("Product key (PIDKEY)", classes="field-label"),
                Input(value=c.get("pid_key", ""), placeholder="optional XXXXX-XXXXX-…", id="oct-pidkey"),
                classes="row",
            ),
            Horizontal(
                Label("Company name", classes="field-label"),
                Input(value=c.get("company_name", ""), placeholder="optional", id="oct-company"),
                classes="row",
            ),
            Horizontal(
                Label("User name", classes="field-label"),
                Input(value=c.get("user_name", ""), placeholder="optional", id="oct-user"),
                classes="row",
            ),
            Rule(classes="spacing"),
            Label("[b]Logging[/b]", classes="tabhead"),
            Horizontal(Label("Logging level", classes="field-label"), loglvl, classes="row"),
            Horizontal(
                Label("Logging path", classes="field-label"),
                Input(value=c.get("logging_path", ""), placeholder="optional", id="oct-log-path"),
                classes="row",
            ),
        )

    def _xml_panel(self) -> VerticalScroll:
        return self._panel(
            Label("[b]configuration.xml[/b] - regenerated on every change and saved automatically.", classes="tabhead"),
            Label(
                f"Saved to: [b]{save_configuration_xml(self.cfg)}[/b]\n"
                "Also mirrored next to setup.exe in the downloads folder before running.",
                classes="muted",
            ),
            Static(_xml_rich(build_configuration_xml(self.cfg)), id="oct-preview"),
        )

    # ----- state collection -----

    def _collect(self) -> None:
        self.cfg["products"] = []
        self.cfg["exclude_apps"] = []
        if self.query("#tab-products"):
            pane = self.query_one("#tab-products", TabPane)
            for box in pane.query(Checkbox):
                if box.has_class("prod") and box.value:
                    self.cfg["products"].append(box.id.removeprefix("prod-"))
                if box.has_class("excl") and box.value:
                    self.cfg["exclude_apps"].append(box.id.removeprefix("excl-"))
        self._persist()

    def _persist(self) -> None:
        save_ms_config(self.cfg)
        save_configuration_xml(self.cfg)
        if self.query("#oct-preview"):
            self.query_one("#oct-preview", Static).update(_xml_rich(build_configuration_xml(self.cfg)))

    def _setup_inputs(self, directive: tuple[str, ...], value: object) -> None:
        key = {
            "oct-lang": "primary_language",
            "oct-channel": "channel",
            "oct-edition": "edition",
            "oct-update-channel": "update_channel",
            "oct-version": "version",
            "oct-source": "source_path",
            "oct-update-path": "update_path",
            "oct-display": "display_level",
            "oct-logging": "logging_level",
            "oct-pidkey": "pid_key",
            "oct-company": "company_name",
            "oct-user": "user_name",
            "oct-log-path": "logging_path",
        }
        if directive and directive[0] in key:
            self.cfg[key[directive[0]]] = value
            self._persist()

    @on(Checkbox.Changed)
    def _on_checkbox(self, event: Checkbox.Changed) -> None:
        cid = event.checkbox.id or ""
        val = event.value
        if cid in {
            "oct-update-enable", "oct-remove-msi", "oct-eula",
            "oct-autoactivate", "oct-force-shutdown",
        }:
            key = {
                "oct-update-enable": "update_enabled",
                "oct-remove-msi": "remove_msi",
                "oct-eula": "accept_eula",
                "oct-autoactivate": "autoactivate",
                "oct-force-shutdown": "force_app_shutdown",
            }[cid]
            self.cfg[key] = bool(val)
            self._persist()
            return
        if cid.startswith("prod-") or cid.startswith("excl-"):
            self._collect()

    @on(Select.Changed)
    def _on_select(self, event: Select.Changed) -> None:
        self._setup_inputs(event.control.id, event.value)

    @on(Input.Changed)
    def _on_input(self, event: Input.Changed) -> None:
        self._setup_inputs(event.control.id, event.value)

    @on(Button.Pressed, "#oct-save")
    def _save(self) -> None:
        path = save_configuration_xml(self.cfg)
        self.query_one("#oct-log", Log).write(f"configuration.xml saved -> {path}")

    # ----- ODT actions -----

    def _ms_actions_enabled(self, on: bool) -> None:
        for wid in ("#oct-dl-tool", "#oct-dl", "#oct-install", "#oct-extract", "#oct-save"):
            try:
                self.query_one(wid, Button).disabled = not on
            except Exception:
                pass

    @on(Button.Pressed, "#oct-dl-tool")
    def _dl_tool(self) -> None:
        self._ms_actions_enabled(False)
        self.run_worker(self._download_tool(), group="oct", exclusive=True)

    async def _download_tool(self) -> None:
        log = self.query_one("#oct-log", Log)
        bar = self.query_one("#oct-progress", ProgressBar)

        def prog(done: int, total: int | None) -> None:
            bar.update(progress=done, total=total or done or 1)

        log.write("Downloading official Office Deployment Tool (setup.exe) ...")
        try:
            path, asset = await download_suite("ms-office", progress=prog)
        except Exception as e:
            if self.app.screen is self:
                log.write(f"[red]Failed:[/red] {e}")
                self._ms_actions_enabled(True)
            return
        if self.app.screen is not self:
            return
        log.write(f"[green]ODT saved:[/green] {path}  ({_readable_size(asset.size)})")
        bar.update(progress=100, total=100)
        self._ms_actions_enabled(True)

    @on(Button.Pressed, "#oct-dl")
    def _dl(self) -> None:
        self._ms_actions_enabled(False)
        self.run_worker(self._run("download"), group="oct", exclusive=True)

    @on(Button.Pressed, "#oct-install")
    def _install(self) -> None:
        self._ms_actions_enabled(False)
        save_configuration_xml(self.cfg)
        self.run_worker(self._run("configure"), group="oct", exclusive=True)

    @on(Button.Pressed, "#oct-extract")
    def _extract(self) -> None:
        self._ms_actions_enabled(False)
        save_configuration_xml(self.cfg)
        self.run_worker(self._run("extract"), group="oct", exclusive=True)

    async def _run(self, action: str) -> None:
        from ost.installer import run_odt

        log = self.query_one("#oct-log", Log)
        log.write(f"setup.exe /{action} configuration.xml")
        result: object = await _run_blocking(
            log,
            lambda cb: run_odt(action, self.cfg, log=cb),
        )
        if self.app.screen is not self:
            return
        ok = bool(getattr(result, "ok", False))
        log.write(("[green]" if ok else "[red]") + str(getattr(result, "message", "")) + "[/]")
        instructions = str(getattr(result, "instructions", ""))
        if instructions:
            log.write("[yellow]" + instructions + "[/]")
        self._ms_actions_enabled(True)

    def action_go_back(self) -> None:
        self._persist()
        self.app.pop_screen()

    def action_save(self) -> None:
        self._save()


class OstApp(App):
    TITLE = "OST - Office Suite Toolkit"
    SUB_TITLE = "check · download · install · update"
    CSS = CSS

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())


def main() -> int:
    OstApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())