"""Thread preset definitions for common standards."""

from __future__ import annotations

from .params import ThreadParameters


def _mm(val: float) -> float:
    return val / 10.0


# Presets temporarily simplified — will be expanded in v2
PRESETS = {}
