#!/usr/bin/env python3
"""OST - Office Suite Toolkit starter.

Run with no arguments to choose your interface (TUI / WEB / GUI-coming-soon),
or use any CLI subcommand directly:

    python main.py              # interface chooser
    python main.py tui          # terminal UI
    python main.py web          # web interface in the browser
    python main.py list         # list suites (with OS availability)
    python main.py check all    # check latest versions online

Equivalent to:  python -m ost
"""

from __future__ import annotations

import sys

from ost.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))