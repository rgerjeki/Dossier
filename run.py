#!/usr/bin/env python3
"""Launch Dossier reliably, without depending on the editable-install path hook.

Some environments (seen on Homebrew Python 3.14) do not honor the editable
install's ``.pth`` file, so ``python -m dossier`` can fail with
``No module named dossier``. This launcher puts ``src`` on the path explicitly,
so ``python run.py`` always works. Run it from the project root.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dossier.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
