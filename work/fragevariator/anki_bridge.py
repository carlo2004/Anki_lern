"""Narrow bridge between Anki objects and Variator's pure core.

The functions in this module deliberately contain no Qt code.  Collection
reads are expected to run in a collection-backed ``QueryOp`` and
``generate_batch()`` in a network-only ``QueryOp.without_collection()``.
"""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .core.intensity import DEFAULT_REWRITE_INTENSITY
from .core.models import (
    BatchGenerationResult,
    CardImage,
    CardSnapshot,
    GeneratedVariants,
    GenerationFailure,
    ProviderSettings,
)
from .core.prompt import build_prompt
from .core.providers import ImageInput, generate_json
from .core.providers import ErrorKind, ProviderError
from .core.result_parser import UnsupportedCardError, parse_generation
from .core.text import (
    answer_without_question,
    has_typed_answer,
    html_to_text,
    source_hash,
    variant_source_hash,
)
from .core.visual import front_requires_screenshot
from .i18n import tr


_NON_IMAGE_MEDIA_RE = re.compile(
    r"<\s*(?:audio|video|object|iframe)\b|"
    r"\[sound:|\{\{\s*tts\b",
    re.IGNORECASE,
)
_IMG_TAG_RE = re.compile(r"<\s*img\b", re.IGNORECASE)
_RENDER_DEPENDENT_FRONT_RE = re.compile(
    r"<\s*(?:anki-mathjax|canvas|figure|math|picture|svg|table)\b|"
    r"(?:background(?:-image)?|border-image|content|mask(?:-image)?)\s*:|"
    r"(?:position\s*:\s*(?:absolute|fixed|sticky)|"
    r"display\s*:\s*(?:flex|inline-flex|grid|inline-grid)|"
    r"(?:transform|clip-path|object-position|z-index)\s*:)",
    re.IGNORECASE,
)
_MAX_INLINE_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_INLINE_IMAGE_TOTAL_BYTES = 10 * 1024 * 1024
_MAX_INLINE_IMAGES = 4


def snapshot_cards(
    col: Any,
    card_ids: Iterable[int],
    *,
    allow_images: bool = False,
    rewrite_intensity: object = DEFAULT_REWRITE_INTENSITY,
) -> list[CardSnapshot]:
    """Render one immutable snapshot for every distinct selected card.

    A bad or unsupported card is represented by a snapshot with
    ``unsupported_reason`` instead of aborting the complete selection.  This
    makes the later review dialog able to report per-card failures.
    """

    snapshots: list[CardSnapshot] = []
    seen: set[int] = set()
    for raw_card_id in card_ids:
        try:
            card_id = int(raw_card_id)
        except (TypeError, ValueError):
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        try:
            snapshots.append(
                snapshot_card(
                    col,
                    card_id,
                    allow_images=allow_images,
                    rewrite_intensity=rewrite_intensity,
                )
            )
        except Exception as exc:
            snapshots.append(_unreadable_snapshot(card_id, exc))
    return snapshots


def snapshot_card(
    col: Any,
    card_id: int,
    *,
    allow_images: bool = False,
    rewrite_intensity: object = DEFAULT_REWRITE_INTENSITY,
) -> CardSnapshot:
    """Render and normalize one Anki card without changing the collection."""

    card = col.get_card(card_id)
    note = _card_note(col, card)
    notetype = _note_type(col, note)

    # question()/answer() are intentionally used instead of guessing which
    # note fields a template displays.  This also handles reversed cards and
    # custom templates correctly.
    question_html = str(card.question() or "")
    answer_html = str(card.answer() or "")
    question_text = html_to_text(question_html)
    rendered_answer_text = html_to_text(answer_html)
    answer_text = answer_without_question(question_text, rendered_answer_text)
    visual_front = front_requires_screenshot(question_html)
    images = (
        _extract_portable_card_images(
            col,
            note,
            question_html=question_html,
            answer_html=answer_html,
        )
        if allow_images
        else ()
    )
    front_screenshot_required = bool(
        allow_images
        and visual_front
        and not _single_source_image_fully_represents_front(
            question_html,
            images,
        )
    )

    unsupported_reason: str | None = None
    if _is_image_occlusion(note, notetype):
        unsupported_reason = tr("failure.image_occlusion")
    elif has_typed_answer(question_html) or has_typed_answer(answer_html):
        unsupported_reason = tr("failure.typed_answer")
    elif (
        _NON_IMAGE_MEDIA_RE.search(question_html)
        or _NON_IMAGE_MEDIA_RE.search(answer_html)
        or _card_has_av_tags(card, "question_av_tags")
        or _card_has_av_tags(card, "answer_av_tags")
    ):
        unsupported_reason = tr("failure.unsupported_media")
    elif visual_front and not allow_images:
        unsupported_reason = tr("failure.images_live_only")
    if unsupported_reason is None and not question_text and not front_screenshot_required:
        unsupported_reason = tr("failure.front_no_text")
    elif unsupported_reason is None and not answer_text:
        unsupported_reason = tr("failure.answer_no_text")

    note_id = int(getattr(card, "nid", getattr(note, "id", 0)) or 0)
    return CardSnapshot(
        card_id=int(card_id),
        note_id=note_id,
        source_html=question_html,
        answer_html=answer_html,
        question_text=question_text,
        answer_text=answer_text,
        source_hash=variant_source_hash(
            question_html, answer_html, rewrite_intensity
        ),
        note_type=str(notetype.get("name", "")) if isinstance(notetype, dict) else "",
        deck_name=_deck_name(col, card),
        unsupported_reason=unsupported_reason,
        images=images,
        front_screenshot_required=front_screenshot_required,
        card_ordinal=int(getattr(card, "ord", 0) or 0),
    )


def _extract_portable_card_images(
    col: Any,
    note: Any,
    *,
    question_html: str,
    answer_html: str,
) -> tuple[CardImage, ...]:
    """Keep high-resolution local image fallbacks for both card sides.

    The rendered-front capture remains preferred because it preserves layout.
    Source bytes make ordinary pasted screenshot cards reliable when Chromium
    cannot paint an off-screen page.  Images repeated through ``FrontSide`` are
    de-duplicated and retain their original ``front`` role; distinct images
    appearing only on the back are labelled ``answer``.
    """

    media = getattr(col, "media", None)
    files_in_str = getattr(media, "files_in_str", None)
    media_dir = getattr(media, "dir", None)
    if not callable(files_in_str) or not callable(media_dir):
        return ()
    try:
        mid = int(getattr(note, "mid"))
        root = Path(media_dir()).resolve()
    except (AttributeError, OSError, TypeError, ValueError):
        return ()

    ordered: list[tuple[str, str]] = []
    for role, source in (("front", question_html), ("answer", answer_html)):
        try:
            names = files_in_str(mid, source, include_remote=False)
        except Exception:
            continue
        for raw_name in names:
            name = unquote(str(raw_name or "")).strip()
            if name:
                ordered.append((role, name))

    candidates: list[CardImage] = []
    seen: set[str] = set()
    for role, name in ordered:
        if name in seen:
            continue
        seen.add(name)
        candidate = (root / name).resolve()
        try:
            candidate.relative_to(root)
            size = candidate.stat().st_size
            mime_type = _portable_image_mime(candidate)
            if not candidate.is_file() or not mime_type:
                continue
            if size <= 0 or size > _MAX_INLINE_IMAGE_BYTES:
                continue
            data = candidate.read_bytes()
        except (OSError, ValueError):
            continue
        if len(data) != size or not _image_magic_matches(data, mime_type):
            continue
        candidates.append(
            CardImage(
                filename=name,
                mime_type=mime_type,
                data=data,
                role=role,
                kind="source_image_fallback",
            )
        )

    # Reserve capacity for both sides.  A front screenshot plus a visual answer
    # is the common real-world case in the user's Analysis deck.
    front = [image for image in candidates if image.role == "front"]
    answer = [image for image in candidates if image.role == "answer"]
    selected = front[:2] + answer[:2]
    if len(selected) < _MAX_INLINE_IMAGES:
        selected_ids = {id(image) for image in selected}
        selected.extend(
            image
            for image in candidates
            if id(image) not in selected_ids
        )
    result: list[CardImage] = []
    total_bytes = 0
    for image in selected[:_MAX_INLINE_IMAGES]:
        next_total = total_bytes + len(image.data)
        if next_total > _MAX_INLINE_IMAGE_TOTAL_BYTES:
            continue
        result.append(image)
        total_bytes = next_total
    return tuple(result)


def _single_source_image_fully_represents_front(
    question_html: str,
    images: tuple[CardImage, ...],
) -> bool:
    """Prefer the original pasted screenshot when no layout raster is needed."""

    front_images = [image for image in images if image.role == "front"]
    return bool(
        len(front_images) == 1
        and len(_IMG_TAG_RE.findall(question_html or "")) == 1
        and not _RENDER_DEPENDENT_FRONT_RE.search(question_html or "")
    )


def _portable_image_mime(path: Path) -> str:
    mime_type, _encoding = mimetypes.guess_type(path.name)
    return mime_type if mime_type in {"image/png", "image/jpeg"} else ""


def _image_magic_matches(data: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return (
            len(data) >= 24
            and data.startswith(b"\x89PNG\r\n\x1a\n")
            and data[12:16] == b"IHDR"
        )
    return (
        len(data) >= 5
        and data.startswith(b"\xff\xd8\xff")
        and data.endswith(b"\xff\xd9")
    )


def generate_batch(
    snapshots: Sequence[CardSnapshot],
    settings: ProviderSettings,
    variant_count: int,
    cancelled: Callable[[], bool] | None = None,
    *,
    intensity: object = DEFAULT_REWRITE_INTENSITY,
) -> BatchGenerationResult:
    """Generate and validate variants, isolating failures to one card each."""

    requested_count = max(1, min(10, int(variant_count)))
    result = BatchGenerationResult()

    for snapshot in snapshots:
        if cancelled is not None and cancelled():
            result.cancelled = True
            break
        if snapshot.unsupported_reason:
            result.failures.append(
                GenerationFailure(
                    card_id=snapshot.card_id,
                    original_question=snapshot.question_text,
                    reason=snapshot.unsupported_reason,
                )
            )
            continue
        if snapshot.front_screenshot_required:
            # Visual fronts must never fall through to a text-only request.  The
            # UI capture stage clears this marker only after a complete image is
            # attached to the immutable snapshot.
            result.failures.append(
                GenerationFailure(
                    card_id=snapshot.card_id,
                    original_question=snapshot.question_text,
                    reason=tr("failure.image_unreadable"),
                )
            )
            continue

        try:
            system_prompt, user_prompt, schema = build_prompt(
                snapshot, requested_count, intensity
            )
            # Count logical card submissions, not provider-level retry
            # attempts. The call below owns any retry policy internally.
            result.sent_cards += 1
            raw = generate_json(
                settings,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                cancelled=cancelled,
                images=[
                    ImageInput.from_bytes(image.data, image.mime_type)
                    for image in snapshot.images
                ]
                or None,
            )
            parsed = parse_generation(
                raw,
                original_question=snapshot.question_text,
                answer_text=snapshot.answer_text,
                requested_count=requested_count,
                intensity=intensity,
                front_image_present=any(
                    image.role == "front" for image in snapshot.images
                ),
            )
        except (KeyboardInterrupt, InterruptedError):
            result.cancelled = True
            break
        except UnsupportedCardError as exc:
            result.failures.append(
                GenerationFailure(
                    card_id=snapshot.card_id,
                    original_question=snapshot.question_text,
                    reason=_safe_exception_text(exc, settings.api_key),
                )
            )
        except ProviderError as exc:
            result.failures.append(
                GenerationFailure(
                    card_id=snapshot.card_id,
                    original_question=snapshot.question_text,
                    reason=_provider_failure_reason(exc),
                )
            )
            if exc.kind in {
                ErrorKind.AUTH,
                ErrorKind.PERMISSION,
                ErrorKind.QUOTA,
                ErrorKind.RATE_LIMIT,
                ErrorKind.MODEL_NOT_FOUND,
                ErrorKind.BAD_REQUEST,
                ErrorKind.NETWORK,
                ErrorKind.TIMEOUT,
                ErrorKind.UNAVAILABLE,
            }:
                result.terminal_error = True
                break
        except Exception as exc:
            result.failures.append(
                GenerationFailure(
                    card_id=snapshot.card_id,
                    original_question=snapshot.question_text,
                    reason=_safe_exception_text(exc, settings.api_key),
                )
            )
        else:
            result.generated.append(
                GeneratedVariants(
                    card_id=snapshot.card_id,
                    note_id=snapshot.note_id,
                    source_hash=snapshot.source_hash,
                    original_question=snapshot.question_text,
                    core_aspect=str(parsed["core_aspect"]),
                    variants=list(parsed["variants"]),
                    warnings=list(parsed.get("warnings", [])),
                    provider=settings.provider,
                    model=settings.model,
                    uses_front_image=any(
                        image.role == "front" for image in snapshot.images
                    ),
                    front_visual_mode=str(parsed["front_visual_mode"]),
                )
            )

    return result


def _card_note(col: Any, card: Any) -> Any:
    note_method = getattr(card, "note", None)
    if callable(note_method):
        return note_method()
    return col.get_note(int(card.nid))


def _note_type(col: Any, note: Any) -> dict[str, Any]:
    note_type_method = getattr(note, "note_type", None)
    if callable(note_type_method):
        value = note_type_method()
        if isinstance(value, dict):
            return value
    value = col.models.get(getattr(note, "mid", None))
    return value if isinstance(value, dict) else {}


def _is_image_occlusion(note: Any, notetype: dict[str, Any]) -> bool:
    """Identify Anki's stock Image Occlusion type plus conservative copies."""

    stock_kind = notetype.get("originalStockKind")
    # The legacy notetype dict exposes OriginalStockKind, not StockNotetype.Kind.
    # In Anki's public protobuf schema, Image Occlusion is value 6 in that enum.
    if stock_kind == 6:
        return True

    name = str(notetype.get("name", "")).casefold().replace("_", " ")
    if "image occlusion" in name or "bildverdeckung" in name:
        return True

    try:
        field_names = {str(name).casefold() for name in note.keys()}
    except (AttributeError, TypeError):
        field_names = {
            str(field.get("name", "")).casefold()
            for field in notetype.get("flds", [])
            if isinstance(field, dict)
        }
    has_occlusions = "occlusion" in field_names or "occlusions" in field_names
    return has_occlusions and "image" in field_names


def _deck_name(col: Any, card: Any) -> str:
    try:
        current_deck_id = getattr(card, "current_deck_id", None)
        deck_id = current_deck_id() if callable(current_deck_id) else card.did
        name_method = getattr(col.decks, "name", None)
        if callable(name_method):
            return str(name_method(deck_id) or "")
        deck = col.decks.get(deck_id)
        return str(deck.get("name", "")) if isinstance(deck, dict) else ""
    except Exception:
        return ""


def _card_has_av_tags(card: Any, method_name: str) -> bool:
    try:
        getter = getattr(card, method_name, None)
        return bool(getter()) if callable(getter) else False
    except Exception:
        # If Anki exposes the media API but it cannot be evaluated, preserve
        # the original card instead of guessing that it is text-only.
        return callable(getattr(card, method_name, None))


def _unreadable_snapshot(card_id: int, exc: Exception) -> CardSnapshot:
    reason = tr(
        "failure.card_unreadable",
        detail=_safe_exception_text(exc, ""),
    )
    return CardSnapshot(
        card_id=card_id,
        note_id=0,
        source_html="",
        answer_html="",
        question_text="",
        answer_text="",
        source_hash=source_hash(""),
        unsupported_reason=reason,
    )


def _safe_exception_text(exc: BaseException, api_key: str) -> str:
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    if api_key:
        text = text.replace(api_key, tr("redaction.api_key"))
    return text[:800]


_PROVIDER_ERROR_TRANSLATION_KEYS: dict[ErrorKind, str] = {
    ErrorKind.AUTH: "provider_error.auth",
    ErrorKind.PERMISSION: "provider_error.permission",
    ErrorKind.QUOTA: "provider_error.quota",
    ErrorKind.RATE_LIMIT: "provider_error.rate_limit",
    ErrorKind.BAD_REQUEST: "provider_error.bad_request",
    ErrorKind.MODEL_NOT_FOUND: "provider_error.model_not_found",
    ErrorKind.TIMEOUT: "provider_error.timeout",
    ErrorKind.NETWORK: "provider_error.network",
    ErrorKind.UNAVAILABLE: "provider_error.unavailable",
    ErrorKind.REFUSAL: "provider_error.refusal",
    ErrorKind.INCOMPLETE: "provider_error.incomplete",
    ErrorKind.INVALID_RESPONSE: "provider_error.invalid_response",
    ErrorKind.CANCELLED: "provider_error.cancelled",
}


def _provider_failure_reason(exc: ProviderError) -> str:
    """Return a concise localized reason without leaking provider payloads."""

    return tr(
        _PROVIDER_ERROR_TRANSLATION_KEYS.get(
            exc.kind,
            "provider_error.unknown",
        )
    )


# Descriptive aliases make the boundary pleasant to use from tests and future
# controllers without retaining any legacy Anki camelCase naming.
create_card_snapshot = snapshot_card
create_card_snapshots = snapshot_cards
generate_variants = generate_batch


__all__ = [
    "create_card_snapshot",
    "create_card_snapshots",
    "generate_batch",
    "generate_variants",
    "snapshot_card",
    "snapshot_cards",
]
