"""Load the split daily project context collector implementation."""

from __future__ import annotations

import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_PARTS = tuple(sorted(Path(__file__).with_name(name) for name in (
    "gather_daily_project_context_part01.pyfrag",
    "gather_daily_project_context_part02.pyfrag",
    "gather_daily_project_context_part03.pyfrag",
    "gather_daily_project_context_part04.pyfrag",
    "gather_daily_project_context_part05.pyfrag",
    "gather_daily_project_context_part06.pyfrag",
)))
_SOURCE = "".join(part.read_text(encoding="utf-8") for part in _PARTS)
_SOURCE = _SOURCE.replace('encoding="utf-8", errors="ignore"', 'encoding="utf-8-sig", errors="ignore"')
exec(compile(_SOURCE, str(Path(__file__).with_name("gather_daily_project_context_impl.py")), "exec"), globals(), globals())
