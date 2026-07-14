"""Allow launching the desktop app with ``python -m dossier``."""

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
