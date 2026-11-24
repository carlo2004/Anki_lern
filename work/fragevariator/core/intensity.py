"""Shared rewrite-intensity values used by prompts and local validation."""

from __future__ import annotations

from typing import Literal, Tuple, cast


RewriteIntensity = Literal["near", "light", "distinct", "maximum"]

REWRITE_INTENSITIES: Tuple[RewriteIntensity, ...] = (
    "near",
    "light",
    "distinct",
    "maximum",
)
DEFAULT_REWRITE_INTENSITY: RewriteIntensity = "distinct"


def normalize_rewrite_intensity(value: object) -> RewriteIntensity:
    """Return a supported intensity, falling back safely for old config data."""

    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in REWRITE_INTENSITIES:
            return cast(RewriteIntensity, normalized)
    return DEFAULT_REWRITE_INTENSITY


__all__ = [
    "DEFAULT_REWRITE_INTENSITY",
    "REWRITE_INTENSITIES",
    "RewriteIntensity",
    "normalize_rewrite_intensity",
]
