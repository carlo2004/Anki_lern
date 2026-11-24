from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
import sys
from types import SimpleNamespace


WORK_ROOT = Path(__file__).resolve().parents[1]
if str(WORK_ROOT) not in sys.path:
    sys.path.insert(0, str(WORK_ROOT))

from fragevariator.deck_queue import (
    first_upcoming_card_ids_for_all_decks,
    normal_decks,
    upcoming_card_ids_for_current_deck,
    upcoming_card_ids_for_deck,
)


@dataclass(frozen=True)
class _Card:
    id: object


@dataclass(frozen=True)
class _QueueEntry:
    card: _Card


class _Decks:
    def __init__(self, current: int = 10) -> None:
        self.current = current
        self.selections: list[int] = []
        self.entries: list[object] = []

    def get_current_id(self) -> int:
        return self.current

    def set_current(self, deck_id: int) -> None:
        self.current = int(deck_id)
        self.selections.append(self.current)

    def all_names_and_ids(
        self, *, skip_empty_default: bool, include_filtered: bool
    ) -> list[object]:
        self.all_names_args = (skip_empty_default, include_filtered)
        return list(self.entries)


class _Scheduler:
    def __init__(
        self,
        decks: _Decks,
        queues: dict[int, list[object]],
        *,
        failing_decks: set[int] | None = None,
    ) -> None:
        self.decks = decks
        self.queues = queues
        self.failing_decks = set(failing_decks or ())
        self.fetches: list[tuple[int, int]] = []

    def get_queued_cards(self, *, fetch_limit: int) -> object:
        deck_id = self.decks.get_current_id()
        self.fetches.append((deck_id, int(fetch_limit)))
        if deck_id in self.failing_decks:
            raise RuntimeError("scheduler unavailable")
        ids = self.queues.get(deck_id, [])[:fetch_limit]
        return SimpleNamespace(
            cards=tuple(_QueueEntry(_Card(card_id)) for card_id in ids)
        )


def _collection(
    queues: dict[int, list[object]],
    *,
    current: int = 10,
    failing_decks: set[int] | None = None,
) -> tuple[object, _Decks, _Scheduler]:
    decks = _Decks(current)
    scheduler = _Scheduler(decks, queues, failing_decks=failing_decks)
    return SimpleNamespace(decks=decks, sched=scheduler), decks, scheduler


class DeckQueueTests(unittest.TestCase):
    def test_normal_decks_preserve_display_order_and_dedupe_ids(self) -> None:
        collection, decks, _scheduler = _collection({})
        decks.entries = [
            SimpleNamespace(id=7, name="Zoologie"),
            SimpleNamespace(id=2, name="  Anatomie  "),
            SimpleNamespace(id=7, name="Doppelter Eintrag"),
            SimpleNamespace(id=0, name="Ungültig"),
            SimpleNamespace(id=9, name=""),
            object(),
        ]

        result = normal_decks(collection)

        self.assertEqual(
            [(item.deck_id, item.name) for item in result],
            [(7, "Zoologie"), (2, "Anatomie")],
        )
        self.assertEqual(decks.all_names_args, (True, False))

    def test_current_deck_ordered_dedupe_overfetches_without_selecting(self) -> None:
        collection, decks, scheduler = _collection(
            {10: [101, 101, 0, "bad", 102, 103, 104]},
            current=10,
        )

        result = upcoming_card_ids_for_current_deck(collection, limit=3)

        self.assertEqual(result, [101, 102, 103])
        self.assertEqual(decks.get_current_id(), 10)
        self.assertEqual(decks.selections, [])
        self.assertEqual(scheduler.fetches[0][0], 10)
        self.assertGreater(
            scheduler.fetches[0][1],
            3,
            "Die Scheduler-Abfrage muss Duplikate durch begrenztes Overfetch ausgleichen.",
        )

    def test_other_deck_ordered_dedupe_and_restores_original_selection(self) -> None:
        collection, decks, scheduler = _collection(
            {22: [201, 201, 202, 203]},
            current=10,
        )

        result = upcoming_card_ids_for_deck(collection, deck_id=22, limit=2)

        self.assertEqual(result, [201, 202])
        self.assertEqual(decks.get_current_id(), 10)
        self.assertEqual(decks.selections, [22, 10])
        self.assertGreater(scheduler.fetches[0][1], 2)
        self.assertEqual(scheduler.fetches[-1], (10, 1))

    def test_deeply_nested_child_uses_its_own_queue_and_restores_parent(self) -> None:
        """Deck ids, not hierarchy labels, define an explicit offline query."""

        parent_id = 100
        fpv_child_id = 203
        collection, decks, scheduler = _collection(
            {
                parent_id: [1001, 1002],
                fpv_child_id: [2031, 2032, 2033],
            },
            current=parent_id,
        )

        result = upcoming_card_ids_for_deck(
            collection,
            deck_id=fpv_child_id,
            limit=2,
        )

        self.assertEqual(result, [2031, 2032])
        self.assertEqual(decks.get_current_id(), parent_id)
        self.assertEqual(decks.selections, [fpv_child_id, parent_id])
        self.assertEqual(scheduler.fetches[0][0], fpv_child_id)
        self.assertEqual(scheduler.fetches[-1], (parent_id, 1))

    def test_other_deck_restores_original_when_scheduler_raises(self) -> None:
        collection, decks, scheduler = _collection(
            {}, current=10, failing_decks={22}
        )

        result = upcoming_card_ids_for_deck(collection, deck_id=22, limit=5)

        self.assertEqual(result, [])
        self.assertEqual(decks.get_current_id(), 10)
        self.assertEqual(decks.selections, [22, 10])
        self.assertEqual(scheduler.fetches[-1], (10, 1))

    def test_all_deck_first_cards_prioritize_current_and_dedupe_parents(self) -> None:
        collection, decks, scheduler = _collection(
            {
                20: [201],
                10: [101],
                30: [101],  # parent deck resolves to the same first card
                40: [401],
            },
            current=20,
        )
        decks.entries = [
            SimpleNamespace(id=10, name="Parent"),
            SimpleNamespace(id=20, name="Current"),
            SimpleNamespace(id=30, name="Parent::Child"),
            SimpleNamespace(id=40, name="Other"),
        ]

        result = first_upcoming_card_ids_for_all_decks(collection)

        self.assertEqual(result, [201, 101, 401])
        self.assertEqual([deck_id for deck_id, _limit in scheduler.fetches[:-1]], [20, 10, 30, 40])
        self.assertEqual(decks.get_current_id(), 20)
        self.assertEqual(decks.selections[-1], 20)

    def test_all_deck_scan_has_a_defensive_bound(self) -> None:
        collection, decks, scheduler = _collection(
            {deck_id: [deck_id * 10] for deck_id in range(1, 6)},
            current=1,
        )
        decks.entries = [
            SimpleNamespace(id=deck_id, name=f"Deck {deck_id}")
            for deck_id in range(1, 6)
        ]

        result = first_upcoming_card_ids_for_all_decks(
            collection,
            max_decks=3,
        )

        self.assertEqual(result, [10, 20, 30])
        # Three deck reads plus one scheduler rebuild after restoring selection.
        self.assertEqual(len(scheduler.fetches), 4)


if __name__ == "__main__":
    unittest.main()
