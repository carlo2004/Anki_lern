from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini", "xai")


@dataclass(frozen=True)
class CardImage:
    """One transient visual input derived from a rendered card.

    Bytes are kept only in the transient snapshot/network pipeline. They are
    never written to the variant database.
    """

    filename: str
    mime_type: str
    data: bytes
    role: str = "front"
    kind: str = "source_image"


@dataclass(frozen=True)
class CardSnapshot:
    card_id: int
    note_id: int
    source_html: str
    answer_html: str
    question_text: str
    answer_text: str
    source_hash: str
    note_type: str = ""
    deck_name: str = ""
    unsupported_reason: Optional[str] = None
    images: Tuple[CardImage, ...] = ()
    front_screenshot_required: bool = False
    card_ordinal: int = 0


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    model: str
    api_key: str
    timeout_seconds: int = 60
    max_retries: int = 2


@dataclass
class GeneratedVariants:
    card_id: int
    note_id: int
    source_hash: str
    original_question: str
    core_aspect: str
    variants: List[str]
    warnings: List[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    uses_front_image: bool = False
    # ``uses_front_image`` records private request provenance. Front images are
    # analysis-only; ``replace`` records that the generated text safely stands
    # alone while the original visual remains hidden behind the Original control.
    front_visual_mode: str = "none"


@dataclass
class GenerationFailure:
    card_id: int
    original_question: str
    reason: str


@dataclass
class BatchGenerationResult:
    generated: List[GeneratedVariants] = field(default_factory=list)
    failures: List[GenerationFailure] = field(default_factory=list)
    cancelled: bool = False
    terminal_error: bool = False
    # One logical provider request per card. Provider-internal HTTP retries do
    # not increase this value, which keeps the user-facing counter meaningful.
    sent_cards: int = 0
    # Results can outlive the operation that started them (for example after a
    # profile switch). Marking the result makes callback accounting idempotent.
    usage_recorded: bool = False


@dataclass(frozen=True)
class StoredVariants:
    profile_key: str
    card_id: int
    note_id: int
    source_hash: str
    question_preview: str
    core_aspect: str
    variants: List[str]
    provider: str
    model: str
    updated_at: str
    uses_front_image: bool = False
    front_visual_mode: str = "none"
