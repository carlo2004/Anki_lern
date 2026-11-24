"""Small, defensive helpers for reading upcoming cards from Anki decks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeckOption:
    deck_id: int
    name: str


def normal_decks(col: Any) -> list[DeckOption]:
    """Return normal decks in Anki's display order, without creating decks."""

    entries = col.decks.all_names_and_ids(
        skip_empty_default=True,
        include_filtered=False,
    )
    result: list[DeckOption] = []
    seen: set[int] = set()
    for entry in entries:
        try:
            deck_id = int(getattr(entry, "id"))
            name = str(getattr(entry, "name") or "").strip()
        except (AttributeError, TypeError, ValueError):
            continue
        if deck_id <= 0 or deck_id in seen or not name:
            continue
        seen.add(deck_id)
        result.append(DeckOption(deck_id=deck_id, name=name))
    return result


def upcoming_card_ids_for_deck(
    col: Any,
    deck_id: int,
    limit: int,
) -> list[int]:
    """Read the exact current scheduler queue for one deck and restore selection."""

    requested = max(1, int(limit))
    # A scheduler queue can contain the same card more than once.  Fetch a
    # modest surplus so the caller still receives up to ``requested`` unique
    # cards without ever scanning the whole collection.
    fetch_limit = min(max(requested * 2, requested + 20), 2000)
    return _queued_ids_for_decks(col, [int(deck_id)], fetch_limit)[:requested]


def upcoming_card_ids_for_current_deck(col: Any, limit: int = 1) -> list[int]:
    """Read Anki's exact queue without changing the selected deck."""

    requested = max(1, int(limit))
    fetch_limit = min(max(requested * 2, requested + 20), 2000)
    queued = col.sched.get_queued_cards(fetch_limit=fetch_limit)
    result: list[int] = []
    seen: set[int] = set()
    for entry in tuple(getattr(queued, "cards", ()) or ()):
        try:
            card_id = int(getattr(getattr(entry, "card"), "id"))
        except (AttributeError, TypeError, ValueError):
            continue
        if card_id > 0 and card_id not in seen:
            seen.add(card_id)
            result.append(card_id)
    return result[:requested]


def first_upcoming_card_ids_for_all_decks(
    col: Any,
    *,
    max_decks: int = 200,
) -> list[int]:
    """Return one real next card per normal deck, current deck first.

    Parent and child decks can lead to the same next card.  The shared queue
    reader de-duplicates those ids, which keeps the background reserve small
    without weakening first-card coverage.  A generous deck cap protects Anki
    profiles with machine-generated thousands of decks; whichever deck the
    user actually opens is always handled separately by the priority warm-up.
    """

    try:
        current_deck_id = int(col.decks.get_current_id())
    except (AttributeError, TypeError, ValueError):
        current_deck_id = 0
    deck_ids = [item.deck_id for item in normal_decks(col)]
    if current_deck_id > 0:
        deck_ids = [current_deck_id] + [
            deck_id for deck_id in deck_ids if deck_id != current_deck_id
        ]
    bounded = deck_ids[: max(1, min(200, int(max_decks)))]
    return _queued_ids_for_decks(col, bounded, 1)


def _queued_ids_for_decks(
    col: Any,
    deck_ids: Iterable[int],
    per_deck_limit: int,
) -> list[int]:
    original_deck_id = int(col.decks.get_current_id())
    result: list[int] = []
    seen: set[int] = set()
    try:
        for raw_deck_id in deck_ids:
            try:
                deck_id = int(raw_deck_id)
                if deck_id <= 0:
                    continue
                if int(col.decks.get_current_id()) != deck_id:
                    col.decks.set_current(deck_id)
                queued = col.sched.get_queued_cards(fetch_limit=per_deck_limit)
                entries = tuple(getattr(queued, "cards", ()) or ())
            except Exception:
                # One corrupt/deleted deck must not prevent the others from
                # being inspected. The original selection is still restored in
                # the outer finally block before control returns to Anki.
                continue
            for entry in entries:
                try:
                    card_id = int(getattr(getattr(entry, "card"), "id"))
                except (AttributeError, TypeError, ValueError):
                    continue
                if card_id > 0 and card_id not in seen:
                    seen.add(card_id)
                    result.append(card_id)
    finally:
        if int(col.decks.get_current_id()) != original_deck_id:
            col.decks.set_current(original_deck_id)
            # Rebuild the live scheduler view for the restored deck.  This is
            # still inside the serialized collection operation, so Anki never
            # observes the temporary selection used by the offline dialog.
            col.sched.get_queued_cards(fetch_limit=1)
    return result


__all__ = [
    "DeckOption",
    "first_upcoming_card_ids_for_all_decks",
    "normal_decks",
    "upcoming_card_ids_for_deck",
    "upcoming_card_ids_for_current_deck",
]
