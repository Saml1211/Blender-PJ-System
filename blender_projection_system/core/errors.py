"""Exception types shared by the pure-math core."""

from __future__ import annotations

import math


class ProjectionError(ValueError):
    """Raised when projection inputs are physically meaningless.

    Callers in the Blender layer catch this and turn it into an operator
    ``self.report({'ERROR'}, ...)`` rather than letting a traceback escape.
    """


def require_positive(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProjectionError(f"{name} must be a real number, got {value!r}")
    if value <= 0.0:
        raise ProjectionError(f"{name} must be greater than zero, got {value}")
    return float(value)


def require_finite(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProjectionError(f"{name} must be finite, got {value}")
    return float(value)
