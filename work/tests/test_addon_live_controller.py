from __future__ import annotations

import importlib
import json
import sys
import tempfile
import threading
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


WORK_ROOT = Path(__file__).resolve().parents[1]
if str(WORK_ROOT) not in sys.path:
    sys.path.insert(0, str(WORK_ROOT))

# Import the package while Anki is absent, so its guarded __init__ does not try
# to register a real add-on.  The controller is imported below with a deliberately
# tiny fake AQT surface.
import fragevariator  # noqa: E402,F401

from fragevariator.core.models import (  # noqa: E402
    BatchGenerationResult,
    CardSnapshot,
    GenerationFailure,
    GeneratedVariants,
    ProviderSettings,
)
from fragevariator.core.text import variant_source_hash  # noqa: E402
from fragevariator.core.visual import attach_front_screenshot  # noqa: E402


class _Hook(list):
    pass


class _FakeAction:
    def __init__(self, *args: object, **_kwargs: object) -> None:
        self.text = str(args[0]) if args else ""
        self.checked = False
        self.checkable = False
        self.object_name = ""
        self.triggered = object()
        self.toggled = object()

    def setObjectName(self, name: str) -> None:
        self.object_name = name

    def setCheckable(self, checkable: bool) -> None:
        self.checkable = bool(checkable)

    def setChecked(self, checked: bool) -> None:
        self.checked = bool(checked)

    def blockSignals(self, _blocked: bool) -> None:
        pass

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def setText(self, text: str) -> None:
        self.text = str(text)

    def setToolTip(self, text: str) -> None:
        self.tool_tip = str(text)

    def setStatusTip(self, text: str) -> None:
        self.status_tip = str(text)


class _FakeMenu:
    def __init__(self, title: str = "") -> None:
        self.title = title
        self.actions: list[object] = []
        self.object_name = ""

    def setObjectName(self, name: str) -> None:
        self.object_name = name

    def setTitle(self, title: str) -> None:
        self.title = str(title)

    def addAction(self, action: object) -> None:
        self.actions.append(action)

    def addSeparator(self) -> None:
        self.actions.append("separator")

    def menuAction(self) -> "_FakeMenu":
        return self


class _FakeMenuBar:
    def __init__(self) -> None:
        self.menus: list[_FakeMenu] = []

    def addMenu(self, title: str) -> _FakeMenu:
        menu = _FakeMenu(title)
        self.menus.append(menu)
        return menu

    def removeAction(self, _action: object) -> None:
        pass

    def insertMenu(self, _before: object, menu: _FakeMenu) -> _FakeMenu:
        return menu


class _FakeDialog:
    Accepted = 1

    class DialogCode:
        Accepted = 1


class _FakeTimer:
    pending: list[object] = []

    @staticmethod
    def singleShot(_delay: int, callback: object) -> None:
        _FakeTimer.pending.append(callback)


class _FakeQueryOp:
    """Synchronous QueryOp double; QTimer callbacks remain explicitly queued."""

    runs: list["_FakeQueryOp"] = []

    def __init__(self, *, parent: object, op: object, success: object) -> None:
        self.parent = parent
        self.op = op
        self.success = success
        self.failure_callback = None
        self.uses_collection = True

    def failure(self, callback: object) -> "_FakeQueryOp":
        self.failure_callback = callback
        return self

    def without_collection(self) -> "_FakeQueryOp":
        self.uses_collection = False
        return self

    def with_progress(self, *_args: object, **_kwargs: object) -> "_FakeQueryOp":
        return self

    def run_in_background(self) -> None:
        type(self).runs.append(self)
        try:
            result = self.op(None)
        except Exception as exc:  # pragma: no cover - defensive harness branch
            if self.failure_callback is None:
                raise
            self.failure_callback(exc)
        else:
            self.success(result)


def _install_fake_aqt() -> None:
    hooks = SimpleNamespace(
        browser_menus_did_init=_Hook(),
        browser_will_show_context_menu=_Hook(),
        browser_did_change_row=_Hook(),
        card_will_show=_Hook(),
        reviewer_did_show_question=_Hook(),
        reviewer_did_show_answer=_Hook(),
        reviewer_did_answer_card=_Hook(),
        reviewer_will_end=_Hook(),
        webview_will_set_content=_Hook(),
        webview_did_receive_js_message=_Hook(),
        profile_did_open=_Hook(),
        profile_will_close=_Hook(),
        overview_did_refresh=_Hook(),
        sync_will_start=_Hook(),
        sync_did_finish=_Hook(),
    )

    aqt_module = types.ModuleType("aqt")
    aqt_module.gui_hooks = hooks
    aqt_module.mw = None

    operations_module = types.ModuleType("aqt.operations")
    operations_module.QueryOp = _FakeQueryOp

    qt_module = types.ModuleType("aqt.qt")
    qt_module.QAction = _FakeAction
    qt_module.QDialog = _FakeDialog
    qt_module.QTimer = _FakeTimer

    utils_module = types.ModuleType("aqt.utils")
    utils_module.askUser = lambda *_args, **_kwargs: True
    utils_module.qconnect = lambda *_args, **_kwargs: None
    utils_module.showInfo = lambda *_args, **_kwargs: None
    utils_module.showWarning = lambda *_args, **_kwargs: None
    utils_module.tooltip = lambda *_args, **_kwargs: None

    dialogs_module = types.ModuleType("fragevariator.ui.dialogs")
    dialogs_module.GenerationSetupDialog = type("GenerationSetupDialog", (), {})
    dialogs_module.OfflinePreparationDialog = type(
        "OfflinePreparationDialog", (), {}
    )
    dialogs_module.ReviewResultsDialog = type("ReviewResultsDialog", (), {})
    dialogs_module.SettingsDialog = type("SettingsDialog", (), {})

    sys.modules["aqt"] = aqt_module
    sys.modules["aqt.operations"] = operations_module
    sys.modules["aqt.qt"] = qt_module
    sys.modules["aqt.utils"] = utils_module
    sys.modules["fragevariator.ui.dialogs"] = dialogs_module


_install_fake_aqt()
sys.modules.pop("fragevariator.addon", None)
addon = importlib.import_module("fragevariator.addon")


@dataclass
class _Card:
    id: int
    front: str = "Front?"
    back: str = "Back"

    def question(self) -> str:
        return self.front

    def answer(self) -> str:
        return self.back


@dataclass(frozen=True)
class _QueueEntry:
    card: _Card


class _Scheduler:
    def __init__(self, *card_ids: int) -> None:
        self.card_ids = list(card_ids)
        self.fetch_limits: list[int] = []

    def get_queued_cards(self, *, fetch_limit: int) -> object:
        self.fetch_limits.append(fetch_limit)
        return SimpleNamespace(
            cards=tuple(_QueueEntry(_Card(card_id)) for card_id in self.card_ids)[
                :fetch_limit
            ]
        )


class _AddonManager:
    def __init__(self) -> None:
        self.config = dict(addon.DEFAULT_CONFIG)

    def addonFromModule(self, _module: str) -> str:
        return "fragevariator"

    def getConfig(self, _package: str) -> dict[str, object]:
        return dict(self.config)

    def writeConfig(self, _package: str, config: dict[str, object]) -> None:
        self.config = dict(config)

    def setConfigAction(self, _package: str, _callback: object) -> None:
        pass


class _MainWindow:
    def __init__(self, scheduler: _Scheduler) -> None:
        self.addonManager = _AddonManager()
        self.col = SimpleNamespace(sched=scheduler)
        self.form = SimpleNamespace(
            menubar=_FakeMenuBar(),
            menuHelp=None,
        )
        self.bottom_web = _FakeWeb()
        self.main_web = _FakeWeb()
        self.reviewer = SimpleNamespace(
            mw=self,
            card=None,
            state="question",
            bottom=SimpleNamespace(web=self.bottom_web),
            web=self.main_web,
        )


class _RecordingSecretStore:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def delete(self, provider: str, profile_key: str) -> None:
        self.deleted.append((provider, profile_key))


class _PreparedStore:
    def __init__(
        self,
        *,
        regular: list[GeneratedVariants] | None = None,
        prepared: list[GeneratedVariants] | None = None,
    ) -> None:
        self.regular = list(regular or ())
        self.prepared = list(prepared or ())
        self.deleted_prepared: list[tuple[str, tuple[int, ...]]] = []
        self.saved_prepared: list[tuple[str, tuple[GeneratedVariants, ...]]] = []

    def list_for_profile(self, _profile_key: str) -> list[GeneratedVariants]:
        return list(self.regular)

    def list_prepared_for_profile(
        self, _profile_key: str
    ) -> list[GeneratedVariants]:
        return list(self.prepared)

    def list_prepared_for_cards(
        self, _profile_key: str, card_ids: list[int]
    ) -> list[GeneratedVariants]:
        selected = {int(card_id) for card_id in card_ids}
        return [
            item for item in self.prepared if int(item.card_id) in selected
        ]

    def save_prepared_many(
        self, profile_key: str, items: list[GeneratedVariants]
    ) -> int:
        values = tuple(items)
        self.saved_prepared.append((profile_key, values))
        by_id = {int(item.card_id): item for item in self.prepared}
        by_id.update({int(item.card_id): item for item in values})
        self.prepared = [by_id[card_id] for card_id in sorted(by_id)]
        return len(values)

    def delete_prepared_cards(
        self, profile_key: str, card_ids: list[int]
    ) -> int:
        ids = tuple(int(card_id) for card_id in card_ids)
        self.deleted_prepared.append((profile_key, ids))
        before = len(self.prepared)
        selected = set(ids)
        self.prepared = [
            item for item in self.prepared if int(item.card_id) not in selected
        ]
        return before - len(self.prepared)


class _FakeWeb:
    def __init__(self) -> None:
        self.scripts: list[str] = []
        self.adjustments = 0
        self.focuses = 0

    def eval(self, script: str) -> None:
        self.scripts.append(script)

    def adjustHeightToFit(self) -> None:
        self.adjustments += 1

    def setFocus(self) -> None:
        self.focuses += 1


class ReviewerBottomBar:
    def __init__(self, reviewer: object) -> None:
        self.reviewer = reviewer


class LiveControllerHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeTimer.pending.clear()
        _FakeQueryOp.runs.clear()

    def controller(
        self, *queued_ids: int
    ) -> tuple[addon.FrageVariatorController, _Scheduler]:
        scheduler = _Scheduler(*queued_ids)
        controller = addon.FrageVariatorController(_MainWindow(scheduler))
        controller.variant_store = object()
        controller.config.update(
            enabled=True,
            live_prefetch_enabled=True,
            live_prefetch_count=3,
        )
        controller._live_configuration_ready = lambda: True
        return controller, scheduler

    @staticmethod
    def activate(controller: addon.FrageVariatorController) -> threading.Event:
        cancel_event = threading.Event()
        controller._live_session_active = True
        controller._live_cancel_event = cancel_event
        return cancel_event

    @staticmethod
    def preparation_snapshot(
        card_id: int = 42,
        *,
        source_hash: str = "hash-42",
        note_id: int = 142,
    ) -> CardSnapshot:
        return CardSnapshot(
            card_id=card_id,
            note_id=note_id,
            source_html="Original?",
            answer_html="Antwort",
            question_text="Original?",
            answer_text="Antwort",
            source_hash=source_hash,
        )

    @staticmethod
    def prepared_result(
        card_id: int = 42,
        *,
        source_hash: str = "hash-42",
        note_id: int = 142,
    ) -> GeneratedVariants:
        return GeneratedVariants(
            card_id=card_id,
            note_id=note_id,
            source_hash=source_hash,
            original_question="Original?",
            core_aspect="Kern",
            variants=["Neue Perspektive?"],
            provider="openai",
            model="test-model",
        )

    def test_offline_dialog_uses_selected_deck_and_count_and_remembers_count(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        captured: dict[str, object] = {}

        class Dialog:
            def __init__(self, _parent: object, **kwargs: object) -> None:
                captured.update(kwargs)

            def exec(self) -> int:
                return 1

            def deck_id(self) -> int:
                return 77

            def card_count(self) -> int:
                return 37

        decks = [SimpleNamespace(deck_id=77, name="Biologie")]
        with (
            mock.patch.object(addon, "OfflinePreparationDialog", Dialog),
            mock.patch.object(addon, "normal_decks", return_value=decks),
            mock.patch.object(
                addon,
                "upcoming_card_ids_for_deck",
                return_value=[701, 702, 703],
            ) as upcoming,
            mock.patch.object(controller, "_start_prepared_batch") as start,
        ):
            controller.prepare_deck_for_offline()

        self.assertIs(captured["decks"], decks)
        self.assertEqual(captured["default_count"], 20)
        upcoming.assert_called_once_with(None, 77, 37)
        start.assert_called_once_with(
            [701, 702, 703], mode="offline", parent=controller.mw
        )
        self.assertEqual(controller.config["offline_prepare_count"], 37)
        self.assertEqual(
            controller.mw.addonManager.config["offline_prepare_count"], 37
        )

    def test_offline_setup_does_not_briefly_enable_automatic_questions(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["live_prefetch_enabled"] = False
        controller._live_configuration_ready = lambda: False
        with mock.patch.object(
            controller, "setup_live_mode", return_value=False
        ) as setup:
            controller.prepare_deck_for_offline()

        setup.assert_called_once_with(activate=False)

    def test_automatic_current_deck_lookup_requires_opt_in_consent_and_key(
        self,
    ) -> None:
        cases = (
            ("ready", True, True, "api-key", "overview", False, True),
            ("live off", False, True, "api-key", "overview", False, False),
            ("no consent", True, False, "api-key", "overview", False, False),
            ("no key", True, True, "", "overview", False, False),
            ("review", True, True, "api-key", "review", False, False),
            ("sync", True, True, "api-key", "overview", True, False),
        )

        for label, live, consent, key, state, syncing, expected in cases:
            with self.subTest(label=label):
                controller, _scheduler = self.controller(1)
                controller.__dict__.pop("_live_configuration_ready", None)
                controller.config["live_prefetch_enabled"] = live
                controller.mw.state = state
                controller._sync_in_progress = syncing
                controller._read_live_consent = lambda enabled=consent: (
                    {"provider": "openai", "model": "test-model"}
                    if enabled
                    else {}
                )
                controller.secret_store = SimpleNamespace(
                    get=lambda _provider, _profile, value=key: value
                )
                with (
                    mock.patch.object(
                        addon,
                        "upcoming_card_ids_for_current_deck",
                        return_value=[42],
                    ) as upcoming,
                    mock.patch.object(controller, "_start_prepared_batch") as start,
                ):
                    controller._start_current_deck_preparation()

                self.assertEqual(upcoming.called, expected)
                self.assertEqual(start.called, expected)
                if expected:
                    upcoming.assert_called_once_with(None, 1)
                    start.assert_called_once_with(
                        [42], mode="automatic", parent=controller.mw
                    )

    def test_nested_deck_warmup_is_retried_after_parent_warmup_finishes(
        self,
    ) -> None:
        """Opening a child deck while its parent's request runs must not be lost."""

        controller, _scheduler = self.controller(1)
        parent_owner = threading.Event()
        controller._preparation_in_progress = True
        controller._preparation_cancel_event = parent_owner
        controller._preparation_mode = "automatic"
        controller._preparation_card_ids = {101}

        with (
            mock.patch.object(
                addon,
                "upcoming_card_ids_for_current_deck",
                return_value=[202],
            ) as upcoming,
            mock.patch.object(controller, "_start_prepared_batch") as start,
        ):
            # This represents A-TUM-Studium::2.Semester::FPV becoming current
            # while a previous parent-deck warm-up is still active.
            controller._start_current_deck_preparation()
            self.assertTrue(controller._current_deck_warmup_pending)
            upcoming.assert_not_called()

            controller._finish_preparation(
                parent_owner,
                mode="automatic",
                parent=controller.mw,
                prepared=1,
                already=0,
                unsuitable=0,
            )

            self.assertEqual(len(_FakeTimer.pending), 1)
            callback = _FakeTimer.pending.pop()
            callback()

        upcoming.assert_called_once_with(None, 1)
        start.assert_called_once_with(
            [202], mode="automatic", parent=controller.mw
        )
        self.assertFalse(controller._current_deck_warmup_pending)

    def test_stale_parent_deck_lookup_cannot_start_after_child_is_selected(
        self,
    ) -> None:
        """Late QueryOp callbacks must respect the latest nested-deck selection."""

        controller, _scheduler = self.controller(1)

        class DeferredQueryOp(_FakeQueryOp):
            pending: list["DeferredQueryOp"] = []

            def run_in_background(self) -> None:
                type(self).pending.append(self)

        with (
            mock.patch.object(addon, "QueryOp", DeferredQueryOp),
            mock.patch.object(controller, "_start_prepared_batch") as start,
        ):
            controller._schedule_current_deck_preparation()
            parent_timer = _FakeTimer.pending.pop()
            parent_timer()

            controller._schedule_current_deck_preparation()
            child_timer = _FakeTimer.pending.pop()
            child_timer()

            self.assertEqual(len(DeferredQueryOp.pending), 2)
            parent_lookup, child_lookup = DeferredQueryOp.pending
            parent_lookup.success([101])
            start.assert_not_called()

            child_lookup.success([202])

        start.assert_called_once_with(
            [202], mode="automatic", parent=controller.mw
        )

    def test_idle_reserve_prepares_one_card_at_a_time_and_ignores_bad_ids(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        with (
            mock.patch.object(
                addon,
                "first_upcoming_card_ids_for_all_decks",
                return_value=[11, "bad", 11, 12, 0],
            ) as upcoming,
            mock.patch.object(controller, "_start_prepared_batch") as start,
        ):
            controller._start_startup_reserve_scan()

        upcoming.assert_called_once_with(None, max_decks=200)
        start.assert_called_once_with(
            [11], mode="reserve", parent=controller.mw
        )
        self.assertEqual(controller._startup_reserve_card_ids, [12])

    def test_current_deck_timer_always_blocks_lower_priority_reserve(self) -> None:
        controller, _scheduler = self.controller(1)
        controller._startup_reserve_card_ids = [91]
        with mock.patch.object(controller, "_start_prepared_batch") as start:
            controller._schedule_current_deck_preparation()
            controller._drain_startup_reserve()

        start.assert_not_called()
        self.assertEqual(controller._startup_reserve_card_ids, [91])

    def test_cancelling_preparation_also_discards_stale_reserve_work(self) -> None:
        controller, _scheduler = self.controller(1)
        controller._startup_reserve_card_ids = [91, 92]
        previous_serial = controller._startup_reserve_schedule_serial

        controller._cancel_preparation()

        self.assertEqual(controller._startup_reserve_card_ids, [])
        self.assertGreater(
            controller._startup_reserve_schedule_serial,
            previous_serial,
        )

    def test_exact_prepared_hash_skips_preparation_provider_request(self) -> None:
        controller, _scheduler = self.controller(1)
        snapshot = self.preparation_snapshot()
        existing = self.prepared_result()
        store = _PreparedStore(prepared=[existing])
        controller.variant_store = store
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            "openai", "test-model", "api-key"
        )

        with (
            mock.patch.object(addon, "snapshot_cards", return_value=[snapshot]),
            mock.patch.object(addon, "generate_batch") as provider,
        ):
            controller._start_prepared_batch(
                [snapshot.card_id], mode="automatic", parent=controller.mw
            )

        provider.assert_not_called()
        self.assertIs(
            controller._prepared_cache[("profile", snapshot.card_id)], existing
        )
        self.assertFalse(store.saved_prepared)
        self.assertFalse(controller._preparation_in_progress)

    def test_generated_preparation_is_saved_only_after_freshness_recheck(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        initial = self.preparation_snapshot()
        fresh = self.preparation_snapshot()
        generated = self.prepared_result()
        store = _PreparedStore()
        controller.variant_store = store
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            "openai", "test-model", "api-key"
        )

        with (
            mock.patch.object(
                addon, "snapshot_cards", side_effect=[[initial], [fresh]]
            ) as snapshots,
            mock.patch.object(
                addon,
                "generate_batch",
                return_value=BatchGenerationResult(generated=[generated]),
            ) as provider,
        ):
            controller._start_prepared_batch(
                [initial.card_id], mode="automatic", parent=controller.mw
            )

        self.assertEqual(snapshots.call_count, 2)
        provider.assert_called_once()
        self.assertEqual(len(store.saved_prepared), 1)
        profile_key, saved = store.saved_prepared[0]
        self.assertEqual(profile_key, "profile")
        self.assertEqual(saved, (generated,))
        self.assertIs(
            controller._prepared_cache[("profile", generated.card_id)], generated
        )
        self.assertFalse(controller._preparation_in_progress)

    def test_changed_card_is_discarded_by_final_freshness_check(self) -> None:
        controller, _scheduler = self.controller(1)
        initial = self.preparation_snapshot()
        changed = self.preparation_snapshot(source_hash="changed-hash")
        generated = self.prepared_result()
        store = _PreparedStore()
        controller.variant_store = store
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            "openai", "test-model", "api-key"
        )

        with (
            mock.patch.object(
                addon, "snapshot_cards", side_effect=[[initial], [changed]]
            ),
            mock.patch.object(
                addon,
                "generate_batch",
                return_value=BatchGenerationResult(generated=[generated]),
            ),
        ):
            controller._start_prepared_batch(
                [initial.card_id], mode="automatic", parent=controller.mw
            )

        self.assertFalse(store.prepared)
        self.assertTrue(
            all(not saved for _profile, saved in store.saved_prepared)
        )
        self.assertNotIn(("profile", generated.card_id), controller._prepared_cache)

    def test_automatic_warmup_stays_idle_while_live_is_paused(self) -> None:
        controller, _scheduler = self.controller(1)
        controller._live_paused = True
        with (
            mock.patch.object(
                addon, "upcoming_card_ids_for_current_deck", return_value=[42]
            ) as upcoming,
            mock.patch.object(controller, "_start_prepared_batch") as start,
        ):
            controller._start_current_deck_preparation()

        upcoming.assert_not_called()
        start.assert_not_called()

    def test_automatic_terminal_failure_pauses_with_localized_reason(self) -> None:
        controller, _scheduler = self.controller(1)
        snapshot = self.preparation_snapshot()
        controller.variant_store = _PreparedStore()
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            "openai", "test-model", "api-key"
        )
        reason = addon.tr("provider_error.auth")
        result = BatchGenerationResult(
            failures=[GenerationFailure(snapshot.card_id, "Original?", reason)],
            terminal_error=True,
        )

        with (
            mock.patch.object(addon, "snapshot_cards", return_value=[snapshot]),
            mock.patch.object(addon, "generate_batch", return_value=result),
            mock.patch.object(addon, "tooltip") as notice,
        ):
            controller._start_prepared_batch(
                [snapshot.card_id], mode="automatic", parent=controller.mw
            )

        self.assertTrue(controller._live_paused)
        notice.assert_called_once_with(
            addon.tr("notice.live_failed_detail", reason=reason),
            parent=controller.mw,
            period=6000,
        )

    def test_offline_terminal_failure_is_not_reported_as_unsuitable(self) -> None:
        controller, _scheduler = self.controller(1)
        snapshot = self.preparation_snapshot()
        controller.variant_store = _PreparedStore()
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            "openai", "test-model", "api-key"
        )
        reason = addon.tr("provider_error.quota")
        result = BatchGenerationResult(
            failures=[GenerationFailure(snapshot.card_id, "Original?", reason)],
            terminal_error=True,
        )

        with (
            mock.patch.object(controller, "_start_preparation_progress"),
            mock.patch.object(addon, "snapshot_cards", return_value=[snapshot]),
            mock.patch.object(addon, "generate_batch", return_value=result),
            mock.patch.object(addon, "showWarning") as warning,
            mock.patch.object(addon, "tooltip") as notice,
        ):
            controller._start_prepared_batch(
                [snapshot.card_id], mode="offline", parent=controller.mw
            )

        warning.assert_called_once_with(
            addon.tr("warning.offline_failed", reason=reason),
            parent=controller.mw,
        )
        notice.assert_not_called()
        self.assertFalse(controller._live_paused)

    def test_automatic_nonterminal_failure_is_deduplicated_but_offline_retries(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        snapshot = self.preparation_snapshot()
        controller.variant_store = _PreparedStore()
        settings = ProviderSettings("openai", "test-model", "api-key")
        controller._live_provider_settings = lambda _profile: settings
        result = BatchGenerationResult(
            failures=[
                GenerationFailure(
                    snapshot.card_id,
                    "Original?",
                    addon.tr("parse.too_similar_local"),
                )
            ]
        )

        with (
            mock.patch.object(controller, "_start_preparation_progress"),
            mock.patch.object(addon, "snapshot_cards", return_value=[snapshot]),
            mock.patch.object(
                addon, "generate_batch", return_value=result
            ) as provider,
        ):
            controller._start_prepared_batch(
                [snapshot.card_id], mode="automatic", parent=controller.mw
            )
            controller._start_prepared_batch(
                [snapshot.card_id], mode="automatic", parent=controller.mw
            )
            provider.assert_called_once()

            # A deliberate offline action remains a user-controlled retry and
            # is never silently classified as an unsuitable card.
            controller._start_prepared_batch(
                [snapshot.card_id], mode="offline", parent=controller.mw
            )

        self.assertEqual(provider.call_count, 2)
        expected_key = (
            "profile",
            snapshot.card_id,
            snapshot.source_hash,
            "distinct",
            "openai",
            "test-model",
        )
        self.assertIn(expected_key, controller._session_failed_generation_keys)
        controller._clear_runtime_cache()
        self.assertFalse(controller._session_failed_generation_keys)

    def test_late_network_result_is_discarded_after_owner_changes(self) -> None:
        class DeferredQueryOp(_FakeQueryOp):
            latest: "DeferredQueryOp | None" = None

            def run_in_background(self) -> None:
                type(self).latest = self

        for change in ("profile", "intensity", "cancel"):
            with self.subTest(change=change):
                controller, _scheduler = self.controller(1)
                store = _PreparedStore()
                controller.variant_store = store
                owner = threading.Event()
                controller._preparation_in_progress = True
                controller._preparation_cancel_event = owner
                controller._preparation_card_ids = {42}
                controller._preparation_mode = "automatic"
                persist = mock.Mock()
                controller._persist_prepared_results = persist

                with mock.patch.object(addon, "QueryOp", DeferredQueryOp):
                    controller._start_preparation_network(
                        [self.preparation_snapshot()],
                        requested=1,
                        already=0,
                        unsuitable=0,
                        settings=ProviderSettings(
                            "openai", "test-model", "api-key"
                        ),
                        profile_key="profile",
                        profile_epoch=controller._profile_epoch,
                        store=store,
                        cancel_event=owner,
                        rewrite_intensity="distinct",
                        mode="automatic",
                        parent=controller.mw,
                    )

                operation = DeferredQueryOp.latest
                self.assertIsNotNone(operation)
                if change == "profile":
                    controller._profile_epoch += 1
                elif change == "intensity":
                    controller.config["rewrite_intensity"] = "maximum"
                else:
                    owner.set()
                assert operation is not None
                operation.success(
                    BatchGenerationResult(generated=[self.prepared_result()])
                )

                persist.assert_not_called()
                self.assertFalse(store.saved_prepared)

    def test_persist_worker_rechecks_profile_intensity_and_cancel_before_write(
        self,
    ) -> None:
        class DeferredQueryOp(_FakeQueryOp):
            latest: "DeferredQueryOp | None" = None

            def run_in_background(self) -> None:
                type(self).latest = self

        for change in ("profile", "intensity", "cancel"):
            with self.subTest(change=change):
                controller, _scheduler = self.controller(1)
                store = _PreparedStore()
                controller.variant_store = store
                owner = threading.Event()
                controller._preparation_in_progress = True
                controller._preparation_cancel_event = owner
                controller._preparation_card_ids = {42}
                controller._preparation_mode = "automatic"

                with (
                    mock.patch.object(addon, "QueryOp", DeferredQueryOp),
                    mock.patch.object(
                        addon,
                        "snapshot_cards",
                        return_value=[self.preparation_snapshot()],
                    ),
                ):
                    controller._persist_prepared_results(
                        [self.prepared_result()],
                        requested=1,
                        already=0,
                        unsuitable=0,
                        profile_key="profile",
                        profile_epoch=controller._profile_epoch,
                        store=store,
                        cancel_event=owner,
                        rewrite_intensity="distinct",
                        mode="automatic",
                        parent=controller.mw,
                    )
                    operation = DeferredQueryOp.latest
                    self.assertIsNotNone(operation)
                    if change == "profile":
                        controller._profile_epoch += 1
                    elif change == "intensity":
                        controller.config["rewrite_intensity"] = "maximum"
                    else:
                        owner.set()
                    assert operation is not None
                    operation.op(None)

                self.assertFalse(
                    store.prepared,
                    "%s changed while the persistence worker was queued"
                    % change,
                )

    def test_cancelled_offline_progress_cleans_all_preparation_state(self) -> None:
        class Signal:
            def __init__(self) -> None:
                self.callback: object | None = None

            def connect(self, callback: object) -> None:
                self.callback = callback

            def emit(self) -> None:
                assert callable(self.callback)
                self.callback()

        class PollTimer:
            latest: "PollTimer | None" = None

            def __init__(self, _parent: object) -> None:
                type(self).latest = self
                self.timeout = Signal()
                self.started = False
                self.stopped = False
                self.deleted = False

            def setInterval(self, _milliseconds: int) -> None:
                pass

            def start(self) -> None:
                self.started = True

            def stop(self) -> None:
                self.stopped = True

            def deleteLater(self) -> None:
                self.deleted = True

        class Progress:
            def __init__(self) -> None:
                self.started = 0
                self.finished = 0
                self.cancel_requested = False

            def start(self, **_kwargs: object) -> None:
                self.started += 1

            def finish(self) -> None:
                self.finished += 1

            def want_cancel(self) -> bool:
                return self.cancel_requested

        controller, _scheduler = self.controller(1)
        progress = Progress()
        controller.mw.progress = progress
        owner = threading.Event()
        controller._preparation_in_progress = True
        controller._preparation_cancel_event = owner
        controller._preparation_card_ids = {41, 42}
        controller._preparation_mode = "offline"

        with mock.patch.object(addon, "QTimer", PollTimer):
            controller._start_preparation_progress(owner, controller.mw)
            timer = PollTimer.latest
            self.assertIsNotNone(timer)
            progress.cancel_requested = True
            assert timer is not None
            timer.timeout.emit()

        self.assertTrue(owner.is_set())
        self.assertFalse(controller._preparation_in_progress)
        self.assertIsNone(controller._preparation_cancel_event)
        self.assertFalse(controller._preparation_card_ids)
        self.assertEqual(controller._preparation_mode, "")
        self.assertIsNone(controller._preparation_progress_owner)
        self.assertIsNone(controller._preparation_progress_cleanup)
        self.assertEqual((progress.started, progress.finished), (1, 1))
        self.assertTrue(timer.started)
        self.assertTrue(timer.stopped)
        self.assertTrue(timer.deleted)

    def test_top_toggle_off_pauses_without_revoking_consent(self) -> None:
        controller, _scheduler = self.controller(1, 2, 3, 4)
        self.activate(controller)
        secret_store = _RecordingSecretStore()
        controller.secret_store = secret_store
        clear_consent = mock.Mock()
        controller._clear_live_consent = clear_consent

        controller._on_live_action_toggled(False)

        self.assertFalse(controller.config["live_prefetch_enabled"])
        self.assertFalse(controller._live_session_active)
        clear_consent.assert_not_called()
        self.assertFalse(secret_store.deleted)

        # Consent and key may still make configuration_ready() true. The local
        # pause switch nevertheless remains authoritative and starts no work.
        controller.on_reviewer_did_show_question(_Card(1))
        self.assertFalse(controller._live_session_active)
        self.assertFalse(controller._live_inflight_ids)

    def test_explicit_disconnect_revokes_consent_and_current_provider_key(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        secret_store = _RecordingSecretStore()
        controller.secret_store = secret_store
        clear_consent = mock.Mock(return_value=True)
        controller._clear_live_consent = clear_consent
        self.activate(controller)

        with mock.patch.object(addon, "askUser", return_value=True):
            disconnected = controller._disconnect_live_connection(
                "gemini", parent=controller.mw
            )

        self.assertTrue(disconnected)
        self.assertFalse(controller.config["live_prefetch_enabled"])
        self.assertFalse(controller._live_session_active)
        clear_consent.assert_called_once_with()
        self.assertEqual(secret_store.deleted, [("gemini", "profile")])

    def test_failed_consent_file_removal_stays_revoked_and_forces_setup(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        controller._live_configuration_ready = (
            addon.FrageVariatorController._live_configuration_ready.__get__(
                controller
            )
        )

        class EnvironmentSecretStore(_RecordingSecretStore):
            def get(self, provider: str, profile_key: str) -> str:
                self.last_get = (provider, profile_key)
                return "still-available-environment-key"

        controller.secret_store = EnvironmentSecretStore()
        stale_payload = (
            '{"version": 1, "provider": "gemini", '
            '"model": "gemini-2.5-flash", "allows_images": true}'
        )

        with tempfile.TemporaryDirectory() as directory:
            profile_directory = Path(directory) / "profile-a" / "fragevariator"
            profile_directory.mkdir(parents=True)
            controller._profile_data_directory = lambda: profile_directory
            consent_path = profile_directory / "live-consent.json"
            consent_path.write_text(stale_payload, encoding="utf-8")
            revoked_scope = controller._live_consent_scope()

            with (
                mock.patch.object(addon, "askUser", return_value=True),
                mock.patch.object(addon, "showWarning") as warning,
                mock.patch.object(
                    Path,
                    "unlink",
                    side_effect=PermissionError("file is locked"),
                ),
            ):
                disconnected = controller._disconnect_live_connection(
                    "gemini", parent=controller.mw
                )

            self.assertTrue(disconnected)
            self.assertTrue(consent_path.exists())
            self.assertTrue(
                controller._live_consent_revocation_path().is_file()
            )
            self.assertIn(
                revoked_scope,
                controller.config["live_consent_revoked_profiles"],
            )
            self.assertIn(
                revoked_scope,
                controller.mw.addonManager.config[
                    "live_consent_revoked_profiles"
                ],
            )
            self.assertNotIn("live_consent_revoked", controller.config)
            self.assertEqual(controller._read_live_consent(), {})
            self.assertFalse(controller._live_configuration_ready())
            self.assertTrue(
                any(
                    call.args[0]
                    == addon.tr("warning.consent_file_remove_failed")
                    for call in warning.call_args_list
                )
            )

            setup = mock.Mock(return_value=False)
            controller.setup_live_mode = setup
            controller._on_live_action_toggled(True)
            setup.assert_called_once_with()

    def test_profile_b_fresh_consent_never_clears_profile_a_revocation(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        controller._live_configuration_ready = (
            addon.FrageVariatorController._live_configuration_ready.__get__(
                controller
            )
        )

        class EnvironmentSecretStore(_RecordingSecretStore):
            def __init__(self) -> None:
                super().__init__()
                self.get_calls: list[tuple[str, str]] = []

            def get(self, provider: str, profile_key: str) -> str:
                self.get_calls.append((provider, profile_key))
                return "environment-key"

        secrets = EnvironmentSecretStore()
        controller.secret_store = secrets

        with tempfile.TemporaryDirectory() as directory:
            profile_a = Path(directory) / "profile-a" / "fragevariator"
            profile_b = Path(directory) / "profile-b" / "fragevariator"
            profile_a.mkdir(parents=True)
            profile_b.mkdir(parents=True)
            active_profile = {"path": profile_a}
            controller._profile_data_directory = lambda: active_profile["path"]

            controller._write_live_consent("gemini", "gemini-2.5-flash")
            scope_a = controller._live_consent_scope()
            self.assertTrue(controller._mark_live_consent_revoked())
            marker_a = controller._live_consent_revocation_path()
            self.assertTrue(marker_a.is_file())

            active_profile["path"] = profile_b
            scope_b = controller._live_consent_scope()
            self.assertNotEqual(scope_a, scope_b)
            self.assertTrue(controller._mark_live_consent_revoked())
            marker_b = controller._live_consent_revocation_path()
            self.assertTrue(marker_b.is_file())

            # This is the security-sensitive order used by setup_live_mode:
            # persist fresh consent first, then clear only this profile's gate.
            controller._write_live_consent("openai", "gpt-test")
            self.assertTrue(controller._clear_live_consent_revocation())
            self.assertFalse(marker_b.exists())
            self.assertFalse(controller._is_live_consent_revoked())
            self.assertEqual(
                controller._read_live_consent().get("provider"), "openai"
            )

            revoked_profiles = controller.config[
                "live_consent_revoked_profiles"
            ]
            self.assertIn(scope_a, revoked_profiles)
            self.assertNotIn(scope_b, revoked_profiles)
            self.assertTrue(marker_a.is_file())

            # Simulate a restart/profile switch so no in-memory deny state can
            # hide a bug in the persisted, profile-scoped gate.
            controller._session_revoked_consent_scopes.clear()
            active_profile["path"] = profile_a
            self.assertEqual(controller._read_live_consent(), {})
            self.assertFalse(controller._live_configuration_ready())
            self.assertEqual(secrets.get_calls, [])

    def test_invalid_saved_rewrite_intensity_falls_back_to_default(self) -> None:
        scheduler = _Scheduler(1)
        main_window = _MainWindow(scheduler)
        main_window.addonManager.config["rewrite_intensity"] = "ultra"

        controller = addon.FrageVariatorController(main_window)

        self.assertEqual(controller.config["rewrite_intensity"], "distinct")

    def test_invalid_saved_ui_language_falls_back_to_anki_auto(self) -> None:
        scheduler = _Scheduler(1)
        main_window = _MainWindow(scheduler)
        main_window.addonManager.config["ui_language"] = "klingon"

        controller = addon.FrageVariatorController(main_window)

        self.assertEqual(controller.config["ui_language"], "auto")

    def test_secret_source_kind_keeps_environment_keys_distinct(self) -> None:
        class Store:
            def source_kind(self, _provider: str, _profile: str) -> str:
                return "environment"

            def is_persisted(self, _provider: str, _profile: str) -> bool:
                raise AssertionError("structured source must win")

        self.assertEqual(
            addon._secret_source_kind(Store(), "gemini", "profile", True),
            "environment",
        )

    def test_both_setup_paths_report_unreadable_remembered_key(self) -> None:
        controller, _scheduler = self.controller(1)
        controller._read_live_consent = lambda: {}

        class BrokenStore:
            def get(self, _provider: str, _profile: str) -> str:
                raise OSError("Windows DPAPI could not decrypt the key")

        captured: list[dict[str, object]] = []

        class RejectedDialog:
            def __init__(self, _parent: object, **kwargs: object) -> None:
                captured.append(dict(kwargs))

            def exec(self) -> int:
                return 0

        controller.secret_store = BrokenStore()
        with (
            mock.patch.object(addon, "GenerationSetupDialog", RejectedDialog),
            mock.patch.object(addon, "showWarning") as warning,
        ):
            self.assertFalse(controller.setup_live_mode())
            controller._show_generation_setup(controller.mw, [1])

        self.assertEqual(len(captured), 2)
        self.assertTrue(all(item["api_key"] == "" for item in captured))
        self.assertTrue(
            all(item["api_key_source"] == "missing" for item in captured)
        )
        self.assertEqual(warning.call_count, 2)
        self.assertTrue(
            all(
                call.args[0]
                == addon.tr("warning.remembered_key_unavailable")
                for call in warning.call_args_list
            )
        )

    def test_both_setup_paths_keep_new_session_key_after_delete_error(
        self,
    ) -> None:
        class ReadOnlyOldKeyStore:
            def __init__(self) -> None:
                self.set_calls: list[tuple[str, str, bool, str]] = []
                self.delete_calls: list[tuple[str, str]] = []

            def get(self, _provider: str, _profile: str) -> str:
                return "old-device-key"

            def source_kind(self, _provider: str, _profile: str) -> str:
                return "device"

            def delete(self, provider: str, profile: str) -> None:
                self.delete_calls.append((provider, profile))
                raise PermissionError("secrets.json is read-only")

            def set(
                self,
                provider: str,
                api_key: str,
                *,
                persist: bool,
                scope: str,
            ) -> None:
                self.set_calls.append((provider, api_key, persist, scope))

        class AcceptedSessionDialog:
            def __init__(self, _parent: object, **_kwargs: object) -> None:
                pass

            def exec(self) -> int:
                return 1

            def provider(self) -> str:
                return "openai"

            def model(self) -> str:
                return "test-model"

            def api_key(self) -> str:
                return "new-session-key"

            def api_key_source(self) -> str:
                return "device"

            def store_api_key_plaintext(self) -> bool:
                return False

            def variant_count(self) -> int:
                return 1

        for route in ("live", "browser"):
            with self.subTest(route=route):
                controller, _scheduler = self.controller(1)
                store = ReadOnlyOldKeyStore()
                controller.secret_store = store
                controller._read_live_consent = lambda: {}
                with (
                    mock.patch.object(
                        addon,
                        "GenerationSetupDialog",
                        AcceptedSessionDialog,
                    ),
                    mock.patch.object(addon, "showWarning") as warning,
                    mock.patch.object(controller, "_write_live_consent"),
                    mock.patch.object(
                        controller,
                        "_clear_live_consent_revocation",
                        return_value=True,
                    ),
                    mock.patch.object(controller, "_start_snapshot_query"),
                ):
                    if route == "live":
                        self.assertTrue(
                            controller.setup_live_mode(activate=False)
                        )
                    else:
                        controller._show_generation_setup(
                            controller.mw,
                            [1],
                        )

                self.assertEqual(
                    store.delete_calls,
                    [("openai", "profile")],
                )
                self.assertEqual(
                    store.set_calls,
                    [("openai", "new-session-key", False, "profile")],
                )
                self.assertTrue(
                    any(
                        call.args[0]
                        == addon.tr(
                            "warning.old_key_remove_failed_session_active"
                        )
                        for call in warning.call_args_list
                    )
                )

    def test_browser_snapshot_pipeline_captures_rewrite_intensity(self) -> None:
        controller, _scheduler = self.controller(1)
        cancel_event = threading.Event()
        controller._generation_cancel_event = cancel_event
        settings = ProviderSettings("openai", "model", "key")
        snapshots = [object()]
        network = mock.Mock()
        controller._start_network_query = network

        with mock.patch.object(
            addon, "snapshot_cards", return_value=snapshots
        ) as snapshot:
            controller._start_snapshot_query(
                controller.mw,
                [1],
                settings,
                1,
                "profile",
                controller._profile_epoch,
                cancel_event,
                "maximum",
            )

        self.assertEqual(
            snapshot.call_args.kwargs["rewrite_intensity"], "maximum"
        )
        self.assertEqual(network.call_args.args[-1], "maximum")

    def test_pending_nested_warmup_resumes_after_snapshot_abort_and_failure(
        self,
    ) -> None:
        settings = ProviderSettings("openai", "model", "key")

        for outcome in ("cancelled", "failure"):
            with self.subTest(outcome=outcome):
                controller, _scheduler = self.controller(1)
                owner = threading.Event()
                controller._generation_in_progress = True
                controller._generation_cancel_event = owner
                controller._current_deck_warmup_pending = True
                if outcome == "cancelled":
                    owner.set()
                    snapshot_effect: object = [object()]
                else:
                    snapshot_effect = RuntimeError("snapshot failed")

                with (
                    mock.patch.object(
                        addon,
                        "snapshot_cards",
                        side_effect=(
                            snapshot_effect
                            if isinstance(snapshot_effect, Exception)
                            else None
                        ),
                        return_value=(
                            snapshot_effect
                            if isinstance(snapshot_effect, list)
                            else None
                        ),
                    ),
                    mock.patch.object(
                        controller, "_schedule_current_deck_preparation"
                    ) as resume,
                    mock.patch.object(controller, "_show_error") as show_error,
                    mock.patch.object(controller, "_start_network_query") as network,
                ):
                    controller._start_snapshot_query(
                        controller.mw,
                        [1],
                        settings,
                        1,
                        "profile",
                        controller._profile_epoch,
                        owner,
                        "distinct",
                    )

                resume.assert_called_once_with()
                self.assertFalse(controller._generation_in_progress)
                self.assertIsNone(controller._generation_cancel_event)
                self.assertFalse(controller._current_deck_warmup_pending)
                network.assert_not_called()
                self.assertEqual(show_error.called, outcome == "failure")

    def test_pending_nested_warmup_resumes_after_network_success_and_failure(
        self,
    ) -> None:
        class Signal:
            def connect(self, callback: object) -> None:
                self.callback = callback

        class PollTimer:
            def __init__(self, _parent: object = None) -> None:
                self.timeout = Signal()

            def setInterval(self, _interval: int) -> None:
                pass

            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

            def deleteLater(self) -> None:
                pass

        settings = ProviderSettings("openai", "model", "key")

        for outcome in ("success", "failure"):
            with self.subTest(outcome=outcome):
                controller, _scheduler = self.controller(1)
                owner = threading.Event()
                controller._generation_in_progress = True
                controller._generation_cancel_event = owner
                controller._current_deck_warmup_pending = True
                provider_effect: object
                if outcome == "success":
                    provider_effect = BatchGenerationResult()
                else:
                    provider_effect = RuntimeError("provider failed")

                with (
                    mock.patch.object(addon, "QTimer", PollTimer),
                    mock.patch.object(
                        addon,
                        "generate_batch",
                        side_effect=(
                            provider_effect
                            if isinstance(provider_effect, Exception)
                            else None
                        ),
                        return_value=(
                            provider_effect
                            if isinstance(provider_effect, BatchGenerationResult)
                            else None
                        ),
                    ),
                    mock.patch.object(
                        controller, "_schedule_current_deck_preparation"
                    ) as resume,
                    mock.patch.object(controller, "_review_results") as review,
                    mock.patch.object(addon, "showWarning") as warning,
                ):
                    controller._start_network_query(
                        controller.mw,
                        [object()],
                        settings,
                        1,
                        "profile",
                        controller._profile_epoch,
                        owner,
                        "distinct",
                    )

                resume.assert_called_once_with()
                self.assertFalse(controller._generation_in_progress)
                self.assertIsNone(controller._generation_cancel_event)
                self.assertFalse(controller._current_deck_warmup_pending)
                self.assertEqual(review.called, outcome == "success")
                self.assertEqual(warning.called, outcome == "failure")

    def test_stale_manual_generation_callback_cannot_resume_other_profile(self) -> None:
        controller, _scheduler = self.controller(1)
        owner = threading.Event()
        controller._generation_in_progress = True
        controller._generation_cancel_event = owner
        controller._current_deck_warmup_pending = True

        with mock.patch.object(
            controller, "_schedule_current_deck_preparation"
        ) as resume:
            finished = controller._finish_manual_generation(
                owner,
                "profile",
                controller._profile_epoch + 1,
            )
            duplicate = controller._finish_manual_generation(
                owner,
                "different-profile",
                controller._profile_epoch,
            )

        self.assertFalse(finished)
        self.assertFalse(duplicate)
        resume.assert_not_called()
        self.assertTrue(controller._current_deck_warmup_pending)

    def test_profile_close_and_duplicate_callbacks_never_double_resume(self) -> None:
        controller, _scheduler = self.controller(1)
        owner = threading.Event()
        controller._generation_in_progress = True
        controller._generation_cancel_event = owner
        controller._current_deck_warmup_pending = True

        with mock.patch.object(
            controller, "_schedule_current_deck_preparation"
        ) as resume:
            first = controller._finish_manual_generation(
                owner,
                "profile",
                controller._profile_epoch,
            )
            duplicate = controller._finish_manual_generation(
                owner,
                "profile",
                controller._profile_epoch,
            )

        self.assertTrue(first)
        self.assertFalse(duplicate)
        resume.assert_called_once_with()

        closed_controller, _scheduler = self.controller(1)
        closed_owner = threading.Event()
        closed_epoch = closed_controller._profile_epoch
        closed_controller._generation_in_progress = True
        closed_controller._generation_cancel_event = closed_owner
        closed_controller._current_deck_warmup_pending = True
        with mock.patch.object(
            closed_controller, "_schedule_current_deck_preparation"
        ) as closed_resume:
            closed_controller.on_profile_will_close()
            late = closed_controller._finish_manual_generation(
                closed_owner,
                "profile",
                closed_epoch,
            )

        self.assertFalse(late)
        closed_resume.assert_not_called()
        self.assertFalse(closed_controller._current_deck_warmup_pending)

    def test_settings_change_restarts_live_with_new_intensity(self) -> None:
        controller, _scheduler = self.controller(1, 2, 3, 4)
        self.activate(controller)
        captured: dict[str, object] = {}

        class Dialog:
            def __init__(self, _parent: object, **kwargs: object) -> None:
                captured.update(kwargs)

            def exec(self) -> int:
                return 1

            def delete_profile_variants(self) -> bool:
                return False

            def delete_all_api_keys(self) -> bool:
                return False

            def connection_setup_requested(self) -> bool:
                return False

            def connection_disconnect_requested(self) -> bool:
                return False

            def settings_values(self) -> dict[str, object]:
                return {
                    "enabled": True,
                    "show_original_on_answer": True,
                    "rewrite_intensity": "maximum",
                    "live_prefetch_enabled": True,
                    "live_prefetch_count": 3,
                }

        with (
            mock.patch.object(addon, "SettingsDialog", Dialog),
            mock.patch.object(
                controller, "_stop_live_session", wraps=controller._stop_live_session
            ) as stop,
            mock.patch.object(controller, "_start_live_for_current_reviewer") as start,
        ):
            self.assertTrue(controller.open_settings())

        self.assertEqual(captured["rewrite_intensity"], "distinct")
        self.assertEqual(captured["ui_language"], "auto")
        self.assertEqual(controller.config["rewrite_intensity"], "maximum")
        stop.assert_called_once()
        start.assert_called_once()

    def test_cancelling_connection_change_restores_previous_live_state(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1, 2, 3)
        controller.config["live_prefetch_enabled"] = True

        class Dialog:
            def __init__(self, _parent: object, **_kwargs: object) -> None:
                pass

            def exec(self) -> int:
                return 1

            def delete_profile_variants(self) -> bool:
                return False

            def delete_all_api_keys(self) -> bool:
                return False

            def connection_setup_requested(self) -> bool:
                return True

            def connection_disconnect_requested(self) -> bool:
                return False

            def settings_values(self) -> dict[str, object]:
                return {
                    "enabled": True,
                    "show_original_on_answer": True,
                    "rewrite_intensity": "distinct",
                    "live_prefetch_enabled": True,
                    "live_prefetch_count": 3,
                    "ui_language": "auto",
                }

        with (
            mock.patch.object(addon, "SettingsDialog", Dialog),
            mock.patch.object(
                controller, "setup_live_mode", return_value=False
            ) as setup,
            mock.patch.object(
                controller, "_start_live_for_current_reviewer"
            ) as restart,
            mock.patch.object(
                controller, "_schedule_current_deck_preparation"
            ) as prepare,
        ):
            self.assertTrue(controller.open_settings())

        setup.assert_called_once_with(activate=True)
        self.assertTrue(controller.config["live_prefetch_enabled"])
        restart.assert_called_once_with()
        prepare.assert_called_once_with()

    def test_changing_connection_while_paused_does_not_enable_live_mode(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["live_prefetch_enabled"] = False

        class Dialog:
            def __init__(self, _parent: object, **_kwargs: object) -> None:
                pass

            def exec(self) -> int:
                return 1

            def delete_profile_variants(self) -> bool:
                return False

            def delete_all_api_keys(self) -> bool:
                return False

            def connection_setup_requested(self) -> bool:
                return True

            def connection_disconnect_requested(self) -> bool:
                return False

            def settings_values(self) -> dict[str, object]:
                return {
                    "enabled": True,
                    "show_original_on_answer": True,
                    "rewrite_intensity": "distinct",
                    "live_prefetch_enabled": False,
                    "live_prefetch_count": 3,
                    "ui_language": "auto",
                }

        with (
            mock.patch.object(addon, "SettingsDialog", Dialog),
            mock.patch.object(
                controller, "setup_live_mode", return_value=True
            ) as setup,
        ):
            self.assertTrue(controller.open_settings())

        setup.assert_called_once_with(activate=False)
        self.assertFalse(controller.config["live_prefetch_enabled"])

    def test_main_menu_can_be_retranslated_without_restart(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.mw.col = None
        controller.mw.reviewer.card = _Card(1)
        controller.install()

        addon.set_ui_language("fr", controller.mw)
        controller._retranslate_main_menu()

        self.assertEqual(
            controller._settings_action.text,
            addon.tr("menu.settings"),
        )
        self.assertIn(
            "frageVariatorSetLabels", controller.mw.bottom_web.scripts[-1]
        )
        self.assertIn(
            json.dumps(addon.tr("reviewer.show_original"), ensure_ascii=True),
            controller.mw.bottom_web.scripts[-1],
        )
        self.assertIn(
            "data-fv-original-front",
            controller.mw.main_web.scripts[-1],
        )
        self.assertIn('\\"1\\"', controller.mw.main_web.scripts[-1])
        self.assertIn(
            json.dumps(addon.tr("reviewer.original"), ensure_ascii=True),
            controller.mw.main_web.scripts[-1],
        )
        addon.set_ui_language("en", controller.mw)

    def test_open_browser_actions_are_retranslated_without_reopening(self) -> None:
        controller, _scheduler = self.controller(1)

        class Browser:
            def __init__(self) -> None:
                self.form = SimpleNamespace(menu_Cards=_FakeMenu())

            def selected_cards(self) -> list[int]:
                return [1]

        browser = Browser()
        controller.on_browser_menus_did_init(browser)
        generate_action = getattr(browser, addon._BROWSER_ACTION_ATTRIBUTE)
        delete_action = getattr(browser, addon._BROWSER_DELETE_ACTION_ATTRIBUTE)

        addon.set_ui_language("es", controller.mw)
        controller._retranslate_main_menu()

        self.assertEqual(generate_action.text, addon.tr("browser.generate"))
        self.assertEqual(delete_action.text, addon.tr("browser.delete"))
        addon.set_ui_language("en", controller.mw)

    def test_session_counter_counts_one_question_once_and_resets_at_review_end(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["live_prefetch_enabled"] = False
        card = _Card(1, "Originalfrage?", "Antwort")
        fingerprint = variant_source_hash(card.front, card.back)
        controller._variant_cache[("profile", card.id)] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question=card.front,
            core_aspect="Kern",
            variants=["Neue Perspektive?"],
        )

        first = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )
        redraw = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )

        self.assertIn("Neue Perspektive?", first)
        self.assertIn("Neue Perspektive?", redraw)
        self.assertIn('data-fv-original-front="1" hidden', first)
        self.assertEqual(
            controller._review_choices[card.id].front_original_fragment,
            "Originalfrage?",
        )
        self.assertEqual(first, redraw)
        self.assertEqual(controller._session_reframed_count, 1)

        with mock.patch.object(addon, "tooltip") as notice:
            controller.on_reviewer_will_end()
            self.assertEqual(controller._session_reframed_count, 0)
            self.assertFalse(controller._review_choices)
            notice.assert_called_once()
            self.assertEqual(
                notice.call_args.args[0],
                addon.tr("notice.session_summary", count=1),
            )

            # A second end hook without a new rendered question must stay
            # silent, proving that the prior session did not leak forward.
            controller.on_reviewer_will_end()
            notice.assert_called_once()

    def test_toggle_off_keeps_visible_question_coherent_on_answer_without_frontside(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        controller._clear_live_consent = lambda: None
        card = _Card(1, "<b>Originalfrage?</b>", "<div>Antwort</div>")
        controller.mw.reviewer.card = card
        fingerprint = variant_source_hash(card.front, card.back)
        controller._live_in_use[card.id] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question="Originalfrage?",
            core_aspect="Kern",
            variants=["Grundlegend andere Frage?"],
        )

        rendered_question = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )
        self.assertIn("Grundlegend andere Frage?", rendered_question)
        self.assertIn(card.id, controller._review_choices)

        controller._on_live_action_toggled(False)
        self.assertFalse(controller.config["live_prefetch_enabled"])
        self.assertIn(card.id, controller._review_choices)

        rendered_answer = controller.on_card_will_show(
            "<div>Antwort ohne FrontSide</div>", card, "reviewAnswer"
        )
        self.assertIn("Grundlegend andere Frage?", rendered_answer)
        self.assertIn("<b style=", rendered_answer)
        self.assertIn(">Originalfrage?</b>", rendered_answer)
        self.assertIn("Antwort ohne FrontSide", rendered_answer)
        self.assertEqual(rendered_answer.count("Originalfrage?"), 1)
        self.assertLess(
            rendered_answer.index("Grundlegend andere Frage?"),
            rendered_answer.index("Originalfrage?"),
        )
        self.assertLess(
            rendered_answer.index("Originalfrage?"),
            rendered_answer.index("Antwort ohne FrontSide"),
        )

    def test_answer_reuses_the_hook_munged_front_image_without_duplication(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["live_prefetch_enabled"] = False
        raw_front = '<img src="my image.png" alt="Question image">Original?'
        raw_back = raw_front + '<hr id="answer"><p>ANSWER</p>'
        card = _Card(1, raw_front, raw_back)
        fingerprint = variant_source_hash(card.front, card.back)
        controller._variant_cache[("profile", card.id)] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question="Original?",
            core_aspect="Kern",
            variants=["Alternative?"],
            uses_front_image=True,
            front_visual_mode="replace",
        )
        munged_front = (
            '<img src="my%20image.png" alt="Question image">Original?'
        )
        munged_back = munged_front + '<hr id="answer"><p>ANSWER</p>'

        rendered_question = controller.on_card_will_show(
            munged_front, card, "reviewQuestion"
        )
        rendered_answer = controller.on_card_will_show(
            munged_back, card, "reviewAnswer"
        )

        visible, hidden_original = rendered_question.split(
            '<section class="fv-answer-original"', 1
        )
        self.assertNotIn("my%20image.png", visible)
        self.assertIn("my%20image.png", hidden_original)
        self.assertEqual(rendered_answer.count('src="my%20image.png"'), 1)
        self.assertNotIn('src="my image.png"', rendered_answer)
        self.assertEqual(rendered_answer.count("Alternative?"), 1)
        self.assertLess(
            rendered_answer.index("Alternative?"),
            rendered_answer.index("my%20image.png"),
        )
        self.assertLess(
            rendered_answer.index("my%20image.png"), rendered_answer.index("ANSWER")
        )

    def test_answer_setting_can_hide_original_comparison(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["live_prefetch_enabled"] = False
        controller.config["show_original_on_answer"] = False
        front = '<img src="question.png">Original?'
        card = _Card(1, front, front + '<hr id="answer">ANSWER')
        fingerprint = variant_source_hash(card.front, card.back)
        controller._variant_cache[("profile", card.id)] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question="Original?",
            core_aspect="Kern",
            variants=["Alternative?"],
            uses_front_image=True,
            front_visual_mode="replace",
        )

        controller.on_card_will_show(front, card, "reviewQuestion")
        rendered_answer = controller.on_card_will_show(
            front + '<hr id="answer">ANSWER',
            card,
            "reviewAnswer",
        )

        self.assertIn("Alternative?", rendered_answer)
        self.assertIn("ANSWER", rendered_answer)
        self.assertNotIn("Original?", rendered_answer)
        self.assertNotIn("question.png", rendered_answer)

    def test_first_live_question_does_not_fall_back_to_persistent_variant(self) -> None:
        controller, _scheduler = self.controller(1, 2, 3, 4)
        card = _Card(1, "Original?", "Antwort")
        fingerprint = variant_source_hash(card.front, card.back)
        controller._variant_cache[("profile", card.id)] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question="Original?",
            core_aspect="Kern",
            variants=["Alte gespeicherte Variante?"],
        )

        # This mirrors Anki's real order: card_will_show runs before
        # reviewer_did_show_question starts the live session.
        rendered = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )
        self.assertEqual(rendered, card.front)

    def test_prepared_first_question_is_used_with_live_and_consumed_once(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1, 2, 3)
        card = _Card(
            1,
            '<img src="abbildung.png" alt="Schema"><div>Original?</div>',
            "Antwort",
        )
        fingerprint = variant_source_hash(card.front, card.back)
        prepared = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question="Original?",
            core_aspect="Kern",
            variants=["Welche Beziehung besteht zwischen den beiden Elementen?"],
            uses_front_image=True,
            front_visual_mode="replace",
        )
        store = _PreparedStore(prepared=[prepared])
        controller.variant_store = store
        controller._prepared_cache[("profile", card.id)] = prepared

        first = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )
        redraw = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )

        self.assertIn("Welche Beziehung besteht", first)
        visible, hidden_original = first.split(
            '<section class="fv-answer-original"', 1
        )
        self.assertNotIn("abbildung.png", visible)
        self.assertIn("abbildung.png", hidden_original)
        self.assertEqual(redraw, first)

        # Consumption may be persisted when the question is first rendered or
        # after it is answered. Repeated redraw/answer hooks must still result
        # in exactly one one-shot deletion.
        controller.on_reviewer_did_answer_card(None, card, None)
        controller.on_reviewer_did_answer_card(None, card, None)
        self.assertEqual(store.deleted_prepared, [("profile", (card.id,))])

    def test_fresh_prepared_hash_skips_live_network_for_future_card(self) -> None:
        controller, _scheduler = self.controller(1, 42)
        cancel_event = self.activate(controller)
        card = _Card(42, "Original?", "Antwort")
        fingerprint = variant_source_hash(card.front, card.back)
        prepared = GeneratedVariants(
            card_id=card.id,
            note_id=142,
            source_hash=fingerprint,
            original_question=card.front,
            core_aspect="Kern",
            variants=["Andere Perspektive?"],
        )
        controller._prepared_cache[("profile", card.id)] = prepared
        controller._live_desired_ids = (card.id,)
        controller._live_inflight_ids.add(card.id)
        job_cancel = threading.Event()
        controller._live_job_cancels[card.id] = job_cancel
        snapshot = CardSnapshot(
            card_id=card.id,
            note_id=142,
            source_html=card.front,
            answer_html=card.back,
            question_text=card.front,
            answer_text=card.back,
            source_hash=fingerprint,
        )

        with (
            mock.patch.object(addon, "snapshot_cards", return_value=[snapshot]),
            mock.patch.object(controller, "_start_live_network") as network,
        ):
            controller._start_live_card_snapshot(
                card.id,
                "profile",
                controller._profile_epoch,
                controller._live_session_epoch,
                cancel_event,
                job_cancel,
                "distinct",
            )

        network.assert_not_called()
        self.assertNotIn(card.id, controller._live_inflight_ids)

    def test_visual_live_card_is_captured_before_the_provider_stage(self) -> None:
        controller, _scheduler = self.controller(1, 42)
        cancel_event = self.activate(controller)
        card = _Card(42, '<img src="scan.png">Welche Struktur?', "Antwort")
        controller._live_desired_ids = (card.id,)
        controller._live_inflight_ids.add(card.id)
        job_cancel = threading.Event()
        controller._live_job_cancels[card.id] = job_cancel
        snapshot = CardSnapshot(
            card_id=card.id,
            note_id=142,
            source_html=card.front,
            answer_html=card.back,
            question_text="[image] Welche Struktur?",
            answer_text=card.back,
            source_hash=variant_source_hash(card.front, card.back),
            front_screenshot_required=True,
        )
        captured = attach_front_screenshot(
            snapshot,
            b"\x89PNG\r\n\x1a\nrendered-front",
        )

        def capture(
            items: list[CardSnapshot],
            *,
            success: object,
            cancelled: object,
        ) -> None:
            self.assertEqual(items, [snapshot])
            self.assertFalse(cancelled())  # type: ignore[operator]
            success([captured])  # type: ignore[operator]

        with (
            mock.patch.object(addon, "snapshot_cards", return_value=[snapshot]),
            mock.patch.object(
                controller, "_capture_front_screenshots", side_effect=capture
            ) as screenshot,
            mock.patch.object(controller, "_start_live_network") as network,
        ):
            controller._start_live_card_snapshot(
                card.id,
                "profile",
                controller._profile_epoch,
                controller._live_session_epoch,
                cancel_event,
                job_cancel,
                "distinct",
            )

        screenshot.assert_called_once()
        self.assertEqual(network.call_args.args[0], [captured])
        self.assertEqual(network.call_args.args[1], [card.id])
        self.assertIn(card.id, controller._live_network_ids)

    def test_duplicate_queue_ids_start_only_one_job_per_card(self) -> None:
        controller, _scheduler = self.controller(1, 2, 2, 3)
        self.activate(controller)
        starts = mock.Mock()
        controller._start_live_card_snapshot = starts

        controller._live_refill(current_card_id=1, after_answer=False)

        self.assertEqual([call.args[0] for call in starts.call_args_list], [2, 3])
        self.assertEqual(controller._live_inflight_ids, {2, 3})

    def test_live_refill_captures_selected_rewrite_intensity(self) -> None:
        controller, _scheduler = self.controller(1, 2)
        controller.config["rewrite_intensity"] = "maximum"
        self.activate(controller)
        starts = mock.Mock()
        controller._start_live_card_snapshot = starts

        controller._live_refill(current_card_id=1, after_answer=False)

        starts.assert_called_once()
        self.assertEqual(starts.call_args.args[-1], "maximum")

    def test_empty_generation_result_is_not_immediately_requested_again(self) -> None:
        controller, _scheduler = self.controller(1, 42)
        cancel_event = self.activate(controller)
        controller.mw.reviewer.card = _Card(1)
        controller._live_inflight_ids.add(42)
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            provider="openai",
            model="test-model",
            api_key="test-key",
            max_retries=0,
        )
        starts = mock.Mock()
        controller._start_live_card_snapshot = starts

        with mock.patch.object(
            addon, "generate_batch", return_value=BatchGenerationResult()
        ):
            controller._start_live_network(
                [object()],
                [42],
                "profile",
                controller._profile_epoch,
                controller._live_session_epoch,
                cancel_event,
            )

        self.assertTrue(_FakeTimer.pending)
        callback = _FakeTimer.pending.pop(0)
        callback()
        starts.assert_not_called()

    def test_live_network_forwards_the_captured_intensity(self) -> None:
        controller, _scheduler = self.controller(1, 42)
        cancel_event = self.activate(controller)
        controller._live_desired_ids = (42,)
        controller._live_inflight_ids.add(42)
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            provider="openai",
            model="test-model",
            api_key="test-key",
            max_retries=0,
        )

        with mock.patch.object(
            addon, "generate_batch", return_value=BatchGenerationResult()
        ) as generate:
            controller._start_live_network(
                [object()],
                [42],
                "profile",
                controller._profile_epoch,
                controller._live_session_epoch,
                cancel_event,
                rewrite_intensity="maximum",
            )

        self.assertEqual(generate.call_args.kwargs["intensity"], "maximum")

    def test_live_terminal_failure_shows_reason_and_toggle_retries(self) -> None:
        controller, _scheduler = self.controller(1, 42)
        cancel_event = self.activate(controller)
        controller._live_desired_ids = (42,)
        controller._live_inflight_ids.add(42)
        controller._live_network_ids.add(42)
        pending_cancel = threading.Event()
        controller._live_inflight_ids.add(43)
        controller._live_job_cancels[43] = pending_cancel
        controller._live_action = _FakeAction()
        settings = ProviderSettings("openai", "test-model", "test-key")
        controller._live_provider_settings = lambda _profile: settings
        snapshot = self.preparation_snapshot()
        reason = addon.tr("provider_error.model_not_found")
        result = BatchGenerationResult(
            failures=[GenerationFailure(42, "Original?", reason)],
            terminal_error=True,
        )

        with (
            mock.patch.object(addon, "generate_batch", return_value=result),
            mock.patch.object(addon, "tooltip") as notice,
        ):
            controller._start_live_network(
                [snapshot],
                [42],
                "profile",
                controller._profile_epoch,
                controller._live_session_epoch,
                cancel_event,
            )

        self.assertTrue(controller._live_paused)
        self.assertFalse(controller._live_action.checked)
        self.assertTrue(pending_cancel.is_set())
        self.assertNotIn(43, controller._live_inflight_ids)
        notice.assert_called_once_with(
            addon.tr("notice.live_failed_detail", reason=reason),
            parent=controller.mw,
            period=6000,
        )

        with mock.patch.object(
            controller, "_stop_live_session", wraps=controller._stop_live_session
        ) as stop:
            controller._on_live_action_toggled(True)
        stop.assert_called_once_with()
        self.assertFalse(controller._live_paused)
        self.assertTrue(controller.config["live_prefetch_enabled"])

    def test_stored_variant_is_visible_only_at_its_rewrite_intensity(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["live_prefetch_enabled"] = False
        card = _Card(1, "Originalfrage?", "Antwort")
        near_hash = variant_source_hash(card.front, card.back, "near")
        controller._variant_cache[("profile", card.id)] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=near_hash,
            original_question=card.front,
            core_aspect="Kern",
            variants=["Nahe Variante?"],
        )

        controller.config["rewrite_intensity"] = "distinct"
        self.assertEqual(
            controller.on_card_will_show(card.front, card, "reviewQuestion"),
            card.front,
        )

        controller.config["rewrite_intensity"] = "near"
        rendered = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )
        self.assertIn("Nahe Variante?", rendered)

    def test_mid_card_intensity_change_keeps_answer_coherent(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["rewrite_intensity"] = "near"
        card = _Card(1, "Originalfrage?", "<div>Antwort</div>")
        fingerprint = variant_source_hash(card.front, card.back, "near")
        controller._live_in_use[card.id] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question=card.front,
            core_aspect="Kern",
            variants=["Nahe Variante?"],
        )

        rendered_question = controller.on_card_will_show(
            card.front, card, "reviewQuestion"
        )
        self.assertIn("Nahe Variante?", rendered_question)

        controller.config["rewrite_intensity"] = "maximum"
        controller._stop_live_session()
        rendered_answer = controller.on_card_will_show(
            "<div>Antwort ohne FrontSide</div>", card, "reviewAnswer"
        )
        self.assertIn("Originalfrage?", rendered_answer)
        self.assertIn("Antwort ohne FrontSide", rendered_answer)

    def test_obsolete_inflight_jobs_do_not_block_current_rolling_window(self) -> None:
        controller, _scheduler = self.controller(1, 201, 202, 203)
        self.activate(controller)
        controller._live_inflight_ids.update({101, 102, 103})
        starts = mock.Mock()
        controller._start_live_card_snapshot = starts

        controller._live_refill(current_card_id=1, after_answer=False)

        desired = {201, 202, 203}
        represented = set(controller._live_inflight_ids)
        represented.update(call.args[0] for call in starts.call_args_list)
        self.assertTrue(
            desired.issubset(represented),
            "Das aktuelle Vorschaufenster muss alte, irrelevante Jobs ablösen.",
        )

    def test_obsolete_network_result_is_discarded_before_refilling(self) -> None:
        controller, scheduler = self.controller(1, 42)
        controller.config["live_prefetch_count"] = 1
        cancel_event = self.activate(controller)
        controller.mw.reviewer.card = _Card(1)
        controller._live_desired_ids = (42,)
        controller._live_inflight_ids.add(42)
        controller._live_network_ids.add(42)
        job_cancel = threading.Event()
        controller._live_job_cancels[42] = job_cancel
        controller._live_provider_settings = lambda _profile: ProviderSettings(
            provider="openai",
            model="test-model",
            api_key="test-key",
            max_retries=0,
        )

        class DeferredQueryOp(_FakeQueryOp):
            latest: "DeferredQueryOp | None" = None

            def run_in_background(self) -> None:
                type(self).latest = self

        with mock.patch.object(addon, "QueryOp", DeferredQueryOp):
            controller._start_live_network(
                [object()],
                [42],
                "profile",
                controller._profile_epoch,
                controller._live_session_epoch,
                cancel_event,
                job_cancel,
            )

        operation = DeferredQueryOp.latest
        self.assertIsNotNone(operation)
        scheduler.card_ids = [1, 43]
        starts = mock.Mock()
        controller._start_live_card_snapshot = starts
        controller._live_refill(current_card_id=1, after_answer=False)
        self.assertTrue(job_cancel.is_set())
        starts.assert_not_called()

        assert operation is not None
        operation.success(
            BatchGenerationResult(
                generated=[
                    GeneratedVariants(
                        card_id=42,
                        note_id=142,
                        source_hash="old",
                        original_question="Alt?",
                        core_aspect="Alt",
                        variants=["Veraltet?"],
                    )
                ]
            )
        )
        self.assertNotIn(42, controller._live_ready)
        self.assertNotIn(42, controller._live_inflight_ids)

        self.assertTrue(_FakeTimer.pending)
        _FakeTimer.pending.pop(0)()
        self.assertEqual([call.args[0] for call in starts.call_args_list], [43])

    def test_late_profile_cache_load_preserves_new_state_and_reloads_on_revision(
        self,
    ) -> None:
        controller, _scheduler = self.controller(1)
        stale = GeneratedVariants(
            card_id=1,
            note_id=10,
            source_hash="stale-hash",
            original_question="Alt?",
            core_aspect="Alt",
            variants=["Veraltete Variante?"],
        )
        saved_while_loading = GeneratedVariants(
            card_id=1,
            note_id=10,
            source_hash="fresh-hash",
            original_question="Aktuell?",
            core_aspect="Aktuell",
            variants=["Gerade gespeicherte Variante?"],
        )

        class RecordingStore:
            def __init__(self) -> None:
                self.items = [stale]
                self.loads: list[str] = []

            def list_for_profile(self, profile_key: str) -> list[GeneratedVariants]:
                self.loads.append(profile_key)
                return list(self.items)

            def list_prepared_for_profile(
                self, _profile_key: str
            ) -> list[GeneratedVariants]:
                return []

        class DeferredQueryOp(_FakeQueryOp):
            pending: list["DeferredQueryOp"] = []

            def run_in_background(self) -> None:
                self.result = self.op(None)
                type(self).pending.append(self)

        store = RecordingStore()
        with (
            mock.patch.object(
                controller,
                "_profile_data_directory",
                return_value=WORK_ROOT,
            ),
            mock.patch.object(addon, "SecretStore", return_value=object()),
            mock.patch.object(addon, "VariantStore", return_value=store),
            mock.patch.object(addon, "QueryOp", DeferredQueryOp),
        ):
            controller.on_profile_did_open()
            self.assertEqual(len(DeferredQueryOp.pending), 1)
            first_load = DeferredQueryOp.pending[0]

            choice = addon._ReviewChoice(
                profile_key="profile",
                source_hash="fresh-hash",
                variant="Gerade gespeicherte Variante?",
                original_html="Aktuell?",
            )
            controller._review_choices[1] = choice
            controller._variant_cache[("profile", 1)] = saved_while_loading
            controller._variant_cache_revision += 1
            store.items = [saved_while_loading]

            first_load.success(first_load.result)

            self.assertIs(controller._review_choices[1], choice)
            self.assertIs(
                controller._variant_cache[("profile", 1)],
                saved_while_loading,
            )
            self.assertEqual(len(DeferredQueryOp.pending), 2)
            self.assertEqual(store.loads, ["profile", "profile"])

            authoritative_reload = DeferredQueryOp.pending[1]
            authoritative_reload.success(authoritative_reload.result)

        self.assertIs(controller._review_choices[1], choice)
        self.assertIs(
            controller._variant_cache[("profile", 1)],
            saved_while_loading,
        )

    def test_profile_cache_loads_regular_and_prepared_rows(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.config["live_prefetch_enabled"] = False
        regular = GeneratedVariants(
            card_id=10,
            note_id=110,
            source_hash="regular-hash",
            original_question="Regulär?",
            core_aspect="Regulär",
            variants=["Reguläre Variante?"],
        )
        prepared = GeneratedVariants(
            card_id=20,
            note_id=120,
            source_hash="prepared-hash",
            original_question="Vorbereitet?",
            core_aspect="Vorbereitet",
            variants=["Vorbereitete Variante?"],
            uses_front_image=True,
            front_visual_mode="replace",
        )
        store = _PreparedStore(regular=[regular], prepared=[prepared])

        with tempfile.TemporaryDirectory() as directory:
            controller.mw.pm = SimpleNamespace(profileFolder=lambda: directory)
            with (
                mock.patch.object(addon, "VariantStore", return_value=store),
                mock.patch.object(
                    addon, "SecretStore", return_value=_RecordingSecretStore()
                ),
            ):
                controller.on_profile_did_open()

        self.assertIs(controller._variant_cache[("profile", 10)], regular)
        self.assertIs(controller._prepared_cache[("profile", 20)], prepared)
        self.assertTrue(
            controller._prepared_cache[("profile", 20)].uses_front_image
        )

    def test_profile_warmup_starts_without_waiting_for_cache_callback(self) -> None:
        controller, _scheduler = self.controller(1)

        class DeferredQueryOp(_FakeQueryOp):
            pending: list["DeferredQueryOp"] = []

            def run_in_background(self) -> None:
                type(self).pending.append(self)

        with tempfile.TemporaryDirectory() as directory:
            controller.mw.pm = SimpleNamespace(profileFolder=lambda: directory)
            with (
                mock.patch.object(addon, "VariantStore", return_value=_PreparedStore()),
                mock.patch.object(
                    addon, "SecretStore", return_value=_RecordingSecretStore()
                ),
                mock.patch.object(addon, "QueryOp", DeferredQueryOp),
                mock.patch.object(
                    controller, "_schedule_current_deck_preparation"
                ) as current,
                mock.patch.object(controller, "_schedule_startup_reserve") as reserve,
            ):
                controller.on_profile_did_open()

        self.assertEqual(len(DeferredQueryOp.pending), 1)
        current.assert_called_once_with()
        reserve.assert_called_once_with()

    def test_install_registers_overview_sync_hooks_and_clean_top_menu(self) -> None:
        controller, _scheduler = self.controller(1)
        self.assertEqual(
            Path(addon.__file__).resolve(),
            (WORK_ROOT / "fragevariator" / "addon.py").resolve(),
        )
        # Scope this test to registration and visible menu construction.
        controller.mw.col = None

        controller.install()

        self.assertIn(
            controller.on_overview_did_refresh,
            addon.gui_hooks.overview_did_refresh,
        )
        self.assertIn(
            controller.on_sync_will_start,
            addon.gui_hooks.sync_will_start,
        )
        self.assertIn(
            controller.on_sync_did_finish,
            addon.gui_hooks.sync_did_finish,
        )
        menu = controller._top_menu
        self.assertIsNotNone(menu)
        assert menu is not None
        actions = [
            action for action in menu.actions if isinstance(action, _FakeAction)
        ]
        object_names = {action.object_name for action in actions}
        labels = {action.text for action in actions}
        self.assertEqual(menu.title, f"Variator {addon.tr('status.live')}")
        self.assertNotIn("·", menu.title)
        self.assertTrue(controller._live_action.checkable)
        self.assertEqual(
            controller._live_action.text,
            addon.tr("menu.automatic_questions"),
        )
        self.assertIn("frageVariatorOfflinePreparationAction", object_names)
        self.assertNotIn("frageVariatorOpenBrowserAction", object_names)
        self.assertFalse(
            any("Browser" in label or "auswählen" in label for label in labels)
        )

    def test_menu_title_exposes_on_error_and_off_states(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.mw.col = None
        controller.install()

        controller.config.update(enabled=True, live_prefetch_enabled=True)
        with mock.patch.object(
            controller, "_live_configuration_ready", return_value=True
        ):
            controller._live_paused = False
            controller._sync_live_action()
            self.assertTrue(controller._live_action.checked)
            self.assertEqual(
                controller._top_menu.title,
                f"Variator {addon.tr('status.live')}",
            )

            controller._live_paused = True
            controller._sync_live_action()
            self.assertFalse(controller._live_action.checked)
            self.assertEqual(
                controller._top_menu.title,
                f"Variator {addon.tr('status.paused')}",
            )

        controller.config["live_prefetch_enabled"] = False
        controller._sync_live_action()
        self.assertEqual(
            controller._top_menu.title,
            f"Variator {addon.tr('status.off')}",
        )

    def test_sent_card_counter_is_idempotent_and_never_breaks_learning(self) -> None:
        controller, _scheduler = self.controller(1)
        result = BatchGenerationResult(sent_cards=3)

        controller._record_sent_cards(result)
        controller._record_sent_cards(result)

        self.assertEqual(controller.config["sent_card_count"], 3)
        self.assertEqual(controller.mw.addonManager.config["sent_card_count"], 3)

        controller.mw.addonManager.writeConfig = mock.Mock(
            side_effect=OSError("read only")
        )
        controller._record_sent_cards(BatchGenerationResult(sent_cards=2))
        self.assertEqual(controller.config["sent_card_count"], 5)

    def test_original_question_uses_inline_card_context_and_resets(self) -> None:
        controller, _scheduler = self.controller(1)
        card = _Card(
            1,
            (
                '<b onclick="danger()">Original?</b>'
                '<img src="capture.png" alt="Aufnahme" onerror="danger()">'
                "<script>secret()</script>"
            ),
            "Antwort",
        )
        controller.mw.reviewer.card = card
        front_fragment = addon.safe_original_fragment(card.front)
        controller._review_choices[1] = addon._ReviewChoice(
            profile_key="profile",
            source_hash="hash",
            variant="Andere Frage?",
            original_html=card.front,
            front_original_fragment=front_fragment,
        )

        controller._show_original_control_for(card)
        bottom_script = controller.mw.bottom_web.scripts[-1]
        inline_script = controller.mw.main_web.scripts[-1]
        self.assertIn('frageVariatorSetOriginal(true, "1")', bottom_script)
        self.assertNotIn("Original?", bottom_script)
        self.assertIn('const expectedCardId = "1"', inline_script)
        self.assertIn('data-fv-original-front="${expectedCardId}"', inline_script)
        self.assertNotIn("position: fixed", inline_script)
        self.assertNotIn("innerHTML", inline_script)
        self.assertNotIn("Original?", inline_script)
        self.assertEqual(front_fragment, (
            '<b>Original?</b>'
            '<img src="capture.png" alt="Aufnahme">'
        ))

        controller.on_reviewer_did_show_answer(card)
        self.assertIn(
            'frageVariatorHideOriginal("1")',
            controller.mw.bottom_web.scripts[-1],
        )
        self.assertIn(
            'frageVariatorClearOriginalInline("1")',
            controller.mw.main_web.scripts[-1],
        )

    def test_photo_question_hides_image_until_original_is_requested(self) -> None:
        controller, _scheduler = self.controller(1)
        card = _Card(
            1,
            '<img src="satz.jpg">Was gilt bei kompaktem K?',
            "Antwort",
        )
        controller.mw.reviewer.card = card
        fingerprint = variant_source_hash(card.front, card.back)
        controller._live_in_use[card.id] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question=card.front,
            core_aspect="Kern",
            variants=["Welche Eigenschaft besitzt f(K)?"],
            uses_front_image=True,
            front_visual_mode="replace",
        )

        rendered = controller.on_card_will_show(
            card.front,
            card,
            "reviewQuestion",
        )
        controller._show_original_control_for(card)

        self.assertEqual(rendered.count('src="satz.jpg"'), 1)
        visible, hidden_original = rendered.split(
            '<section class="fv-answer-original"', 1
        )
        self.assertNotIn("satz.jpg", visible)
        self.assertIn("satz.jpg", hidden_original)
        self.assertIn("Was gilt bei kompaktem K?", hidden_original)
        self.assertIn(
            'frageVariatorSetOriginal(true, "1")',
            controller.mw.bottom_web.scripts[-1],
        )

    def test_photographed_question_is_replaced_but_remains_available(self) -> None:
        controller, _scheduler = self.controller(1)
        card = _Card(1, '<img src="lemma-9-13.jpg">', "Antwort")
        controller.mw.reviewer.card = card
        fingerprint = variant_source_hash(card.front, card.back)
        controller._live_in_use[card.id] = GeneratedVariants(
            card_id=card.id,
            note_id=10,
            source_hash=fingerprint,
            original_question="[image]",
            core_aspect="Potenzreihe von ln(1+x)",
            variants=[
                "Gib die Potenzreihenentwicklung von ln(1+x) einschließlich ihres Gültigkeitsbereichs an."
            ],
            uses_front_image=True,
            front_visual_mode="replace",
        )

        rendered = controller.on_card_will_show(
            card.front,
            card,
            "reviewQuestion",
        )
        controller._show_original_control_for(card)

        visible, hidden_original = rendered.split(
            '<section class="fv-answer-original"', 1
        )
        self.assertNotIn("lemma-9-13.jpg", visible)
        self.assertIn("lemma-9-13.jpg", hidden_original)
        self.assertIn(
            'frageVariatorSetOriginal(true, "1")',
            controller.mw.bottom_web.scripts[-1],
        )

    def test_image_only_question_can_reveal_the_hidden_original(self) -> None:
        controller, _scheduler = self.controller(1)
        card = _Card(1, '<img src="diagram.jpg">', "Antwort")
        controller.mw.reviewer.card = card
        controller._review_choices[1] = addon._ReviewChoice(
            profile_key="profile",
            source_hash="hash",
            variant="Welche Struktur ist dargestellt?",
            original_html=card.front,
            front_original_fragment=addon.safe_original_fragment(card.front),
        )

        controller._show_original_control_for(card)

        self.assertIn(
            'frageVariatorSetOriginal(true, "1")',
            controller.mw.bottom_web.scripts[-1],
        )

    def test_inline_context_is_cleared_if_bottom_webview_is_rebuilding(self) -> None:
        controller, _scheduler = self.controller(1)
        controller._original_control_card_id = 1

        def unavailable(_script: str) -> None:
            raise RuntimeError("bottom webview rebuilding")

        controller.mw.bottom_web.eval = unavailable
        controller._hide_original_control()

        self.assertIn(
            'frageVariatorClearOriginalInline("1")',
            controller.mw.main_web.scripts[-1],
        )

    def test_card_switch_without_answer_retires_the_previous_control(self) -> None:
        controller, _scheduler = self.controller(2)
        controller._original_control_card_id = 1
        controller.mw.reviewer.card = _Card(2)

        controller._show_original_control_for(controller.mw.reviewer.card)

        self.assertTrue(
            any(
                'frageVariatorHideOriginal("1")' in script
                for script in controller.mw.bottom_web.scripts
            )
        )
        self.assertTrue(
            any(
                'frageVariatorClearOriginalInline("1")' in script
                for script in controller.mw.main_web.scripts
            )
        )
        self.assertIsNone(controller._original_control_card_id)

    def test_hidden_frontside_does_not_count_as_visible_original(self) -> None:
        original = "<div>Original?</div>"
        hidden_answer = (
            "<style>.front{display:none}</style>"
            '<div class="front">Original?</div>'
            '<div class="frame"><hr id="answer">ANSWER</div>'
        )

        self.assertFalse(addon._html_contains_original(hidden_answer, original))
        self.assertTrue(
            addon._html_contains_original(
                '<section class="frontside"><p>Original?</p></section>'
                '<hr id="answer">ANSWER',
                original,
            )
        )

    def test_closed_details_count_only_their_first_summary_as_visible(self) -> None:
        original = "<div>Original?</div>"

        self.assertFalse(
            addon._html_contains_original(
                "<details><summary>Hint</summary>"
                "<div>Original?</div></details><hr id=answer>ANSWER",
                original,
            )
        )
        self.assertTrue(
            addon._html_contains_original(
                "<details open><summary>Hint</summary>"
                "<div>Original?</div></details><hr id=answer>ANSWER",
                original,
            )
        )
        self.assertTrue(
            addon._html_contains_original(
                "<details><summary><div>Original?</div></summary>"
                "SECRET BODY</details><hr id=answer>ANSWER",
                original,
            )
        )

    def test_bottom_bar_hooks_are_scoped_to_the_reviewer(self) -> None:
        controller, _scheduler = self.controller(1)
        controller.mw.reviewer.card = _Card(1)
        controller._review_choices[1] = addon._ReviewChoice(
            profile_key="profile",
            source_hash="hash",
            variant="Alternative?",
            original_html="Front?",
            front_original_fragment="Front?",
        )
        context = ReviewerBottomBar(controller.mw.reviewer)
        content = SimpleNamespace(head="")

        controller.on_webview_will_set_content(content, context)
        self.assertIn("fv-original-button", content.head)
        self.assertIn("MutationObserver", content.head)

        handled = controller.on_webview_did_receive_js_message(
            (False, None), "fragevariator:toggle-original:show:1", context
        )
        self.assertEqual(handled, (True, None))
        self.assertIn(
            'frageVariatorSetOriginalInlineOpen(true, "1")',
            controller.mw.main_web.scripts[-1],
        )
        self.assertEqual(controller.mw.bottom_web.adjustments, 0)
        self.assertEqual(controller.mw.main_web.focuses, 1)

        obsolete_resize = controller.on_webview_did_receive_js_message(
            (False, None),
            "fragevariator:resize-original-bar",
            context,
        )
        self.assertEqual(obsolete_resize, (False, None))
        self.assertEqual(controller.mw.bottom_web.adjustments, 0)
        self.assertEqual(controller.mw.main_web.focuses, 1)

        foreign = ReviewerBottomBar(SimpleNamespace(mw=object()))
        untouched = controller.on_webview_did_receive_js_message(
            (False, None), "fragevariator:toggle-original:show:1", foreign
        )
        self.assertEqual(untouched, (False, None))

    def test_delayed_original_toggle_cannot_change_the_next_card(self) -> None:
        controller, _scheduler = self.controller(2)
        controller.mw.reviewer.card = _Card(2)
        controller._review_choices[2] = addon._ReviewChoice(
            profile_key="profile",
            source_hash="hash",
            variant="Alternative?",
            original_html="Front?",
            front_original_fragment="Front?",
        )
        context = ReviewerBottomBar(controller.mw.reviewer)

        stale = controller.on_webview_did_receive_js_message(
            (False, None), "fragevariator:toggle-original:show:1", context
        )
        self.assertEqual(stale, (True, None))
        self.assertFalse(controller.mw.main_web.scripts)
        self.assertEqual(controller.mw.main_web.focuses, 0)

        current = controller.on_webview_did_receive_js_message(
            (False, None), "fragevariator:toggle-original:hide:2", context
        )
        self.assertEqual(current, (True, None))
        self.assertIn(
            'frageVariatorSetOriginalInlineOpen(false, "2")',
            controller.mw.main_web.scripts[-1],
        )
        self.assertEqual(controller.mw.main_web.focuses, 1)


if __name__ == "__main__":
    unittest.main()
