"""Animated widgets for the OST terminal user interface.

Everything is pre-rendered into truecolor Rich markup so the animation loop is
cheap (no per-frame string building) and the motion looks smooth.
"""

from __future__ import annotations

import math

from textual.widgets import Static

# Premium brand palette (teal -> violet).
TEAL = (45, 212, 191)
VIOLET = (167, 139, 250)
SKY = (56, 189, 248)
PURPLE = (192, 132, 252)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _rgb(c: tuple[int, int, int]) -> str:
    return f"[rgb({c[0]},{c[1]},{c[2]})]"


def gradient_text(
    text: str,
    start: tuple[int, int, int] = TEAL,
    end: tuple[int, int, int] = VIOLET,
    bold: bool = True,
    pad: str = " ",
) -> str:
    """Render *text* as a left-to-right colour gradient as Rich markup."""
    if not text:
        return ""
    span = max(len(text) - 1, 1)
    parts: list[str] = []
    for i, ch in enumerate(text):
        color = _mix(start, end, i / span)
        style = "[b]" if bold else ""
        slash = "[/]" if bold else ""
        if ch.strip():
            parts.append(f"{style}{_rgb(color)}{ch}{slash}")
        else:
            parts.append(ch)
    return pad + "".join(parts) + pad


class Spinner(Static):
    """A self-animating progress indicator with a colour-cycling glyph."""

    DEFAULT_CSS = """
    Spinner {
        width: auto;
        height: 1;
        background: transparent;
    }
    """

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text: str = "", *, id: str | None = None) -> None:
        super().__init__("", id=id)
        self._text = text
        self._frame = 0
        self._timer = None
        self._running = False

    def on_mount(self) -> None:
        self.start()

    def on_unmount(self) -> None:
        self.stop("")

    def start(self, text: str | None = None) -> None:
        if text is not None:
            self._text = text
        self._running = True
        if self._timer is None:
            self._timer = self.set_interval(0.08, self._tick)

    def stop(self, final: str = "") -> None:
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.update(f"[b][dim]{final}[/dim][/b]" if final else "")

    def _tick(self) -> None:
        if not self._running:
            return
        self._frame = (self._frame + 1) % len(self.FRAMES)
        glyph = self.FRAMES[self._frame]
        color = _mix(TEAL, VIOLET, self._frame / max(len(self.FRAMES) - 1, 1))
        if self._text:
            self.update(f"{_rgb(color)}[b]{glyph}[/b][/] {self._text}")
        else:
            self.update(f"{_rgb(color)}[b]{glyph}[/][/]")


class Marquee(Static):
    """A smooth animated gradient band with a travelling specular highlight.

    Frames are pre-rendered once per width and rebuilt on resize, so the idle
    animation is a fixed 60-80fps-friendly snapshot sequence with no jitter.
    """

    DEFAULT_CSS = """
    Marquee {
        width: 1fr;
        height: 1;
        background: transparent;
        color: transparent;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)
        self._frames: list[str] = []
        self._frame = 0
        self._timer = None
        self._last_width = -1
        self._base = TEAL
        self._accent = VIOLET

    def on_mount(self) -> None:
        self._rebuild()
        if self._timer is None:
            self._timer = self.set_interval(0.066, self._tick)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def on_resize(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        width = max(self.size.width or 0, 4)
        if width == self._last_width and self._frames:
            return
        self._last_width = width
        self._frames = self._frame_sequence(width)
        self._frame = self._frame % max(len(self._frames), 1)

    @staticmethod
    def _frame_sequence(width: int) -> list[str]:
        steps = 48
        span = max(width - 1, 1)
        sigma = max(width * 0.14, 2.0)
        sigma2 = 2 * sigma * sigma
        frames: list[str] = []
        for step in range(steps):
            pos = step / max(steps - 1, 1)
            cells: list[str] = []
            for x in range(width):
                t = x / span
                base = _mix(TEAL, VIOLET, t)
                # travelling specular glow
                d = x - pos * width
                glow = math.exp(-(d * d) / sigma2) * 0.9
                if x < width * 0.08 or x > width * 0.92:
                    glow = min(glow, 0.12)
                r = min(255, base[0] + int(150 * glow))
                g = min(255, base[1] + int(150 * glow))
                b = min(255, base[2] + int(150 * glow))
                cells.append(f"[rgb({r},{g},{b})]█[/]")
            frames.append("".join(cells))
        return frames

    def _tick(self) -> None:
        if not self._frames:
            self._rebuild()
        if not self._frames:
            return
        self._frame = (self._frame + 1) % len(self._frames)
        self.update(self._frames[self._frame])