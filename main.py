#!/usr/bin/env python3
"""OST - Office Suite Toolkit starter.

Run the rich terminal UI with no arguments, or use any CLI subcommand:

    python main.py              # modern TUI
    python main.py list         # list suites (with OS availability)
    python main.py check all    # check latest versions online
    python main.py tui          # TUI again

Equivalent to:  python -m ost
"""

from __future__ import annotations

import sys

from ost.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))