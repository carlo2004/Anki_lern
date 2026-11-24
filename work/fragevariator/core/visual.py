"""Pure contracts for deciding and attaching rendered-front screenshots."""

from __future__ import annotations

import re
from dataclasses import replace

from ..i18n import tr
from .models import CardImage, CardSnapshot


_VISUAL_ELEMENT_RE = re.compile(
    r"<\s*(?:anki-mathjax|canvas|figure|img|math|picture|svg|table)\b",
    re.IGNORECASE,
)
_MATHJAX_SOURCE_RE = re.compile(
    r"(?:\\\(|\\\[|\$\$|\\begin\s*\{)",
    re.IGNORECASE,
)
_VISUAL_CSS_RE = re.compile(
    r"(?:background(?:-image)?|border-image|content|list-style-image|mask(?:-image)?)"
    r"\s*:\s*(?:url\s*\(|image-set\s*\(|['\"]\s*[^'\"])",
    re.IGNORECASE,
)


def front_requires_screenshot(source_html: str) -> bool:
    """Return whether meaning may depend on more than rendered plain text.

    Normal formatting elements, text alignment and font styles stay on the
    inexpensive text-only path. Images, diagrams, tables, rendered maths and
    CSS-generated visual content use one screenshot of the complete front.
    """

    source = source_html or ""
    return bool(
        _VISUAL_ELEMENT_RE.search(source)
        or _MATHJAX_SOURCE_RE.search(source)
        or _VISUAL_CSS_RE.search(source)
    )


def fitted_capture_size(
    viewport_width: object,
    viewport_height: object,
    content_width: object,
    content_height: object,
    *,
    min_width: int = 720,
    min_height: int = 520,
    max_width: int = 1600,
    max_height: int = 2048,
) -> tuple[int, int]:
    """Bound a rendered-front viewport while including tall card content."""

    def positive_int(value: object, fallback: int) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError, OverflowError):
            return fallback
        return parsed if parsed > 0 else fallback

    base_width = positive_int(viewport_width, min_width)
    base_height = positive_int(viewport_height, min_height)
    rendered_width = positive_int(content_width, base_width)
    rendered_height = positive_int(content_height, base_height)
    return (
        max(min_width, min(max_width, max(base_width, rendered_width))),
        max(min_height, min(max_height, max(base_height, rendered_height))),
    )


def attach_front_screenshot(
    snapshot: CardSnapshot,
    data: bytes,
    mime_type: str = "image/png",
) -> CardSnapshot:
    """Return a snapshot carrying exactly one rendered-front screenshot."""

    if mime_type not in {"image/png", "image/jpeg"} or not data:
        raise ValueError(tr("failure.image_unreadable"))
    non_front = tuple(image for image in snapshot.images if image.role != "front")
    screenshot = CardImage(
        filename="variator-rendered-front." + ("png" if mime_type == "image/png" else "jpg"),
        mime_type=mime_type,
        data=bytes(data),
        role="front",
        kind="rendered_front_screenshot",
    )
    return replace(
        snapshot,
        images=(screenshot,) + non_front,
        front_screenshot_required=False,
        unsupported_reason=None,
    )


def mark_front_screenshot_failed(snapshot: CardSnapshot) -> CardSnapshot:
    """Use safe source images when available, otherwise fail one card closed."""

    fallback_images = tuple(
        image
        for image in snapshot.images
        if image.role == "front" and image.kind == "source_image_fallback"
    )
    if fallback_images:
        return replace(
            snapshot,
            front_screenshot_required=False,
            unsupported_reason=None,
        )

    return replace(
        snapshot,
        images=tuple(image for image in snapshot.images if image.role != "front"),
        front_screenshot_required=False,
        unsupported_reason=tr("failure.image_unreadable"),
    )


__all__ = [
    "attach_front_screenshot",
    "fitted_capture_size",
    "front_requires_screenshot",
    "mark_front_screenshot_failed",
]
