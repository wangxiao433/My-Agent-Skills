"""Load the split daily project context collector implementation."""

from __future__ import annotations

from pathlib import Path

_PARTS = tuple(sorted(Path(__file__).with_name(name) for name in (
    "gather_daily_project_context_part01.pyfrag",
    "gather_daily_project_context_part02.pyfrag",
    "gather_daily_project_context_part03.pyfrag",
    "gather_daily_project_context_part04.pyfrag",
    "gather_daily_project_context_part05.pyfrag",
    "gather_daily_project_context_part06.pyfrag",
)))
_SOURCE = "".join(part.read_text(encoding="utf-8") for part in _PARTS)
exec(compile(_SOURCE, str(Path(__file__).with_name("gather_daily_project_context_impl.py")), "exec"), globals(), globals())
