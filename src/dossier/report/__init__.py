"""Report rendering: included findings to a cited document.

Two render paths, one data model (decision D2). A shared citation builder turns
findings into a source list, then a Word template (``docxtpl``) produces the
``.docx`` and a simple HTML template drives Qt's ``QTextDocument`` for the in-app
preview and PDF. Both paths consume the same findings and the same citations, so
content is identical even where layout differs.
"""
