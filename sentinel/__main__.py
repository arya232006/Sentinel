"""`python -m sentinel <command>`, for use without installing the console script."""

from __future__ import annotations

from sentinel.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
