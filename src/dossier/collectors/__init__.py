"""Collectors: pluggable modules that each return a normalized list of Findings.

Each collector wraps a public, no-login source (or an existing OSINT tool) and
returns ``list[Finding]``. Collectors degrade gracefully: a blocked, rate
limited, or unreachable source yields findings with the matching
``FindingStatus`` rather than an exception or a silent drop.

Implementations land in later build steps:
    usernames.py  Maigret        (decision D1)
    email.py      holehe + Gravatar
    metadata.py   ExifTool
    searchkit.py  guided pivot links
"""
