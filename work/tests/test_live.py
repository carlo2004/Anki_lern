from __future__ import annotations

import unittest
from dataclasses import dataclass

from fragevariator.live import (
    LiveJobKey,
    LiveJobRegistry,
    LiveJobStatus,
    normalize_lookahead,
    queue_entry_card_id,
    select_after_answer_lookahead,
    select_question_lookahead,
)


@dataclass(frozen=True)
class FakeCard:
    id: int


@dataclass(frozen=True)
class FakeQueueEntry:
    card: FakeCard


def entries(*card_ids: int) -> list[FakeQueueEntry]:
    return [FakeQueueEntry(FakeCard(card_id)) for card_id in card_ids]


class LookaheadTests(unittest.TestCase):
    def test_default_question_lookahead_skips_matching_queue_head(self) -> None:
        self.assertEqual(
            select_question_lookahead(entries(10, 20, 30, 40, 50), 10),
            (20, 30, 40),
        )

    def test_question_lookahead_does_not_filter_a_later_current_id(self) -> None:
        self.assertEqual(
            select_question_lookahead(entries(20, 10, 30, 40), 10),
            (20, 10, 30),
        )
        self.assertEqual(
            select_question_lookahead(entries(10, 10, 20, 30), 10),
            (10, 20, 30),
        )

    def test_after_answer_never_filters_the_queue_head(self) -> None:
        self.assertEqual(
            select_after_answer_lookahead(entries(10, 20, 30, 40)),
            (10, 20, 30),
        )

    def test_empty_and_short_queues_are_supported(self) -> None:
        self.assertEqual(select_question_lookahead(entries(), 10), ())
        self.assertEqual(select_question_lookahead(entries(10), 10), ())
        self.assertEqual(select_after_answer_lookahead(entries(10, 20)), (10, 20))

    def test_lookahead_is_clamped_to_one_through_ten(self) -> None:
        self.assertEqual(normalize_lookahead(0), 1)
        self.assertEqual(normalize_lookahead(-100), 1)
        self.assertEqual(normalize_lookahead(11), 10)
        self.assertEqual(normalize_lookahead("4"), 4)
        self.assertEqual(normalize_lookahead(None), 3)
        self.assertEqual(normalize_lookahead(True), 3)
        self.assertEqual(
            select_after_answer_lookahead(entries(*range(1, 20)), 999),
            tuple(range(1, 11)),
        )

    def test_queue_entry_shape_and_id_are_validated(self) -> None:
        self.assertEqual(queue_entry_card_id(FakeQueueEntry(FakeCard(123))), 123)
        with self.assertRaises(ValueError):
            queue_entry_card_id(object())
        with self.assertRaises(ValueError):
            queue_entry_card_id(FakeQueueEntry(FakeCard(0)))


class LiveJobRegistryTests(unittest.TestCase):
    @staticmethod
    def key(card_id: int = 10, source_hash: str = "hash") -> LiveJobKey:
        return LiveJobKey("profile", card_id, source_hash, "provider:model:v1")

    def test_active_and_ready_jobs_are_deduplicated(self) -> None:
        registry = LiveJobRegistry()
        key = self.key()

        self.assertTrue(registry.reserve(key))
        self.assertFalse(registry.reserve(key))
        self.assertTrue(registry.set_status(key, LiveJobStatus.RUNNING))
        self.assertFalse(registry.reserve(key))
        self.assertTrue(registry.set_status(key, LiveJobStatus.READY))
        self.assertFalse(registry.reserve(key))

    def test_failed_or_cancelled_jobs_can_be_retried(self) -> None:
        registry = LiveJobRegistry()
        key = self.key()

        registry.reserve(key)
        registry.set_status(key, LiveJobStatus.FAILED)
        self.assertTrue(registry.reserve(key))
        registry.set_status(key, LiveJobStatus.CANCELLED)
        self.assertTrue(registry.reserve(key))

    def test_late_callbacks_do_not_recreate_discarded_jobs(self) -> None:
        registry = LiveJobRegistry()
        key = self.key()

        registry.reserve(key)
        self.assertTrue(registry.discard(key))
        self.assertFalse(registry.set_status(key, LiveJobStatus.READY))
        self.assertIsNone(registry.status(key))

    def test_reserve_many_deduplicates_and_source_changes_make_new_keys(self) -> None:
        registry = LiveJobRegistry()
        original = self.key()
        changed = self.key(source_hash="new-hash")

        self.assertEqual(
            registry.reserve_many([original, original, changed]),
            (original, changed),
        )
        self.assertEqual(len(registry), 2)
        self.assertEqual(registry.snapshot()[changed], LiveJobStatus.QUEUED)
        registry.clear()
        self.assertEqual(len(registry), 0)

    def test_job_keys_reject_ambiguous_values(self) -> None:
        with self.assertRaises(ValueError):
            LiveJobKey("", 1, "hash")
        with self.assertRaises(ValueError):
            LiveJobKey("profile", 0, "hash")
        with self.assertRaises(ValueError):
            LiveJobKey("profile", 1, "")


if __name__ == "__main__":
    unittest.main()
