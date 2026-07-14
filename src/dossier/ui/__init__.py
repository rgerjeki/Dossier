"""The PySide6 (Qt) desktop shell.

Everything in this package imports Qt at module top level, so it must only be
imported after the ``ui`` extra is confirmed installed (see ``dossier.app.main``).
The engine (models, case, collectors, report) never imports this package.
"""
