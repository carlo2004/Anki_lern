from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Dict, Optional, Tuple


DEFAULT_LOOKAHEAD = 3
MIN_LOOKAHEAD = 1
MAX_LOOKAHEAD = 10


def normalize_lookahead(
    value: object,
    *,
    default: int = DEFAULT_LOOKAHEAD,
) -> int:
    """Return a safe live-buffer size between one and ten cards.

    Numeric strings are accepted because add-on configuration may be edited by
    hand. Invalid values fall back to ``default``; values outside the supported
    range are clamped.
    """

    safe_default = max(MIN_LOOKAHEAD, min(MAX_LOOKAHEAD, int(default)))
    if isinstance(value, bool):
        return safe_default

    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        parsed = safe_default

    return max(MIN_LOOKAHEAD, min(MAX_LOOKAHEAD, parsed))


def queue_entry_card_id(entry: object) -> int:
    """Extract and validate ``entry.card.id`` without importing Anki types."""

    try:
        card = getattr(entry, "card")
        raw_card_id = getattr(card, "id")
    except AttributeError as exc:
        raise ValueError("queue entry must expose entry.card.id") from exc

    if isinstance(raw_card_id, bool) or not isinstance(raw_card_id, int):
        raise ValueError("queue card id must be an integer")
    if raw_card_id <= 0:
        raise ValueError("queue card id must be positive")
    return raw_card_id


def select_question_lookahead(
    entries: Iterable[object],
    current_card_id: int,
    lookahead: object = DEFAULT_LOOKAHEAD,
) -> Tuple[int, ...]:
    """Select future card IDs while a reviewer question is visible.

    Anki's queue normally starts with the currently displayed card. It is
    skipped only when the *first* queue entry has the same ID. A matching ID at
    any later position is kept, as it may represent a legitimate scheduler
    result rather than the displayed queue head.
    """

    limit = normalize_lookahead(lookahead)
    iterator = iter(entries)
    selected = []

    try:
        first_id = queue_entry_card_id(next(iterator))
    except StopIteration:
        return ()

    if first_id != current_card_id:
        selected.append(first_id)

    for entry in iterator:
        if len(selected) >= limit:
            break
        selected.append(queue_entry_card_id(entry))

    return tuple(selected[:limit])


def select_after_answer_lookahead(
    entries: Iterable[object],
    lookahead: object = DEFAULT_LOOKAHEAD,
) -> Tuple[int, ...]:
    """Select queue heads after an answer without filtering any card ID.

    At this point Anki has already updated the queue. The just-answered card can
    legitimately be queued again as a learning card, so no ID is removed.
    """

    limit = normalize_lookahead(lookahead)
    selected = []
    for entry in entries:
        selected.append(queue_entry_card_id(entry))
        if len(selected) >= limit:
            break
    return tuple(selected)


class LiveJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class LiveJobKey:
    """Stable identity for deduplicating a live generation request.

    ``request_fingerprint`` should cover settings that change the generated
    result, such as provider, model, prompt version and media payload mode.
    """

    profile_key: str
    card_id: int
    source_hash: str
    request_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.profile_key:
            raise ValueError("profile_key must not be empty")
        if isinstance(self.card_id, bool) or not isinstance(self.card_id, int):
            raise ValueError("card_id must be an integer")
        if self.card_id <= 0:
            raise ValueError("card_id must be positive")
        if not self.source_hash:
            raise ValueError("source_hash must not be empty")


class LiveJobRegistry:
    """Small thread-safe job ledger used to suppress duplicate API calls.

    Queued, running and ready keys are considered reserved. Failed or cancelled
    keys may be reserved again. Status updates return ``False`` when a key was
    discarded in the meantime, which lets late callbacks be ignored safely.
    """

    _RESERVED = frozenset(
        (LiveJobStatus.QUEUED, LiveJobStatus.RUNNING, LiveJobStatus.READY)
    )

    def __init__(self) -> None:
        self._states: Dict[LiveJobKey, LiveJobStatus] = {}
        self._lock = RLock()

    def reserve(self, key: LiveJobKey) -> bool:
        with self._lock:
            if self._states.get(key) in self._RESERVED:
                return False
            self._states[key] = LiveJobStatus.QUEUED
            return True

    def reserve_many(self, keys: Iterable[LiveJobKey]) -> Tuple[LiveJobKey, ...]:
        reserved = []
        with self._lock:
            for key in keys:
                if self._states.get(key) in self._RESERVED:
                    continue
                self._states[key] = LiveJobStatus.QUEUED
                reserved.append(key)
        return tuple(reserved)

    def status(self, key: LiveJobKey) -> Optional[LiveJobStatus]:
        with self._lock:
            return self._states.get(key)

    def set_status(self, key: LiveJobKey, status: LiveJobStatus) -> bool:
        with self._lock:
            if key not in self._states:
                return False
            self._states[key] = status
            return True

    def discard(self, key: LiveJobKey) -> bool:
        with self._lock:
            return self._states.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._states.clear()

    def snapshot(self) -> Dict[LiveJobKey, LiveJobStatus]:
        with self._lock:
            return dict(self._states)

    def __len__(self) -> int:
        with self._lock:
            return len(self._states)
