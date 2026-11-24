"""Anki/Qt controller for Variator.

This module owns UI hooks and background-operation orchestration.  Provider,
parsing, persistence and rendering details remain behind the core interfaces.
"""

from __future__ import annotations

import json
import hashlib
import os
import random
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

from aqt import gui_hooks, mw
from aqt.operations import QueryOp
from aqt.qt import QAction, QDialog, QTimer
from aqt.utils import askUser, qconnect, showInfo, showWarning, tooltip

from .anki_bridge import generate_batch, snapshot_cards
from .core.intensity import DEFAULT_REWRITE_INTENSITY, normalize_rewrite_intensity
from .core.models import BatchGenerationResult, GeneratedVariants, ProviderSettings
from .core.render import (
    original_context_available,
    render_answer_context,
    render_question,
    safe_initially_visible_fragment,
    safe_original_fragment,
)
from .core.reviewer_bar import (
    bottom_bar_head,
    clear_original_inline_script,
    hide_original_inline_script,
    hide_original_script,
    parse_original_toggle_message,
    retranslate_inline_script,
    retranslate_script,
    set_original_inline_script,
    set_original_script,
    show_original_inline_script,
)
from .core.secrets import SecretStore
from .core.store import VariantStore
from .core.text import html_to_text, variant_source_hash
from .core.visual import mark_front_screenshot_failed
from .deck_queue import (
    first_upcoming_card_ids_for_all_decks,
    normal_decks,
    upcoming_card_ids_for_current_deck,
    upcoming_card_ids_for_deck,
)
from .live import select_after_answer_lookahead, select_question_lookahead
from .i18n import normalize_ui_language, set_ui_language, tr
from .ui.dialogs import (
    GenerationSetupDialog,
    OfflinePreparationDialog,
    ReviewResultsDialog,
    SettingsDialog,
)


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "ui_language": "auto",
    "show_original_on_answer": True,
    "provider": "openai",
    "model": "gpt-6-luna",
    "variant_count": 1,
    "sent_card_count": 0,
    "rewrite_intensity": DEFAULT_REWRITE_INTENSITY,
    "live_prefetch_enabled": False,
    "live_prefetch_count": 3,
    "live_consent_revoked_profiles": [],
    "offline_prepare_count": 20,
    "timeout_seconds": 90,
    "max_retries": 2,
}

PRODUCT_NAME = "Variator"

_BROWSER_ACTION_ATTRIBUTE = "_fragevariator_generate_action"
_BROWSER_DELETE_ACTION_ATTRIBUTE = "_fragevariator_delete_action"
_MAX_REVIEW_CHOICES = 2048
_MAX_GENERATION_CARDS = 50
_MAX_OFFLINE_CARDS = 50
_MAX_STARTUP_RESERVE_DECKS = 200
_MAX_SENT_CARD_COUNT = 2_147_483_647
_STARTUP_RESERVE_DELAY_MS = 250
_STARTUP_RESERVE_STEP_DELAY_MS = 400
_LIVE_CONSENT_VERSION = 2
_LIVE_CONSENT_REVOCATION_FILE = "live-consent.revoked"


@dataclass(frozen=True)
class _ReviewChoice:
    profile_key: str
    source_hash: str
    variant: str
    original_html: str
    front_original_fragment: str = ""
    rewrite_intensity: str = DEFAULT_REWRITE_INTENSITY


@dataclass
class _VariantCycle:
    fingerprint: tuple[str, ...]
    remaining: list[str]
    last: str = ""


def _review_front_visual_mode(stored: Any) -> str:
    """Return a validated display decision for one generated question.

    Front images are analysis-only and must be replaced by a self-contained
    question. Historical text-only records are accepted as ``none``; image
    records from the former visible-image policy fail closed.
    """

    mode = str(getattr(stored, "front_visual_mode", "") or "").strip().casefold()
    uses_front_image = bool(getattr(stored, "uses_front_image", False))
    if uses_front_image:
        return "replace" if mode == "replace" else ""
    return "none" if mode in {"", "none"} else ""


class FrageVariatorController:
    """Defensive, single-instance controller registered during add-on load."""

    def __init__(self, main_window: Any) -> None:
        self.mw = main_window
        self.package = self.mw.addonManager.addonFromModule(__name__)
        self.config = self._load_config()
        self._ui_language = set_ui_language(
            self.config.get("ui_language", "auto"), self.mw
        )
        self._installed = False
        self._generation_in_progress = False
        self._generation_cancel_event: threading.Event | None = None
        self._generation_progress_owner: threading.Event | None = None
        self._generation_progress_cleanup: Callable[[], None] | None = None
        self._profile_epoch = 0
        self._review_choices: dict[int, _ReviewChoice] = {}
        self._variant_cycles: dict[int, _VariantCycle] = {}
        self._variant_cache: dict[tuple[str, int], Any] = {}
        self._prepared_cache: dict[tuple[str, int], Any] = {}
        self._prepared_consumed_ids: set[int] = set()
        # Prevent silent background retries from paying twice for the same
        # unchanged card after a non-terminal quality/provider failure.  The
        # cache is intentionally session-only and is cleared with all other
        # profile/runtime state.
        self._session_failed_generation_keys: set[
            tuple[str, int, str, str, str, str]
        ] = set()
        self._variant_cache_revision = 0
        self._session_revoked_consent_scopes: set[str] = set()
        self._live_ready: dict[int, GeneratedVariants] = {}
        self._live_in_use: dict[int, GeneratedVariants] = {}
        self._live_inflight_ids: set[int] = set()
        self._live_network_ids: set[int] = set()
        self._live_failed_ids: set[int] = set()
        self._live_desired_ids: tuple[int, ...] = ()
        self._live_job_cancels: dict[int, threading.Event] = {}
        self._live_cancel_event: threading.Event | None = None
        self._live_session_epoch = 0
        self._live_session_active = False
        self._live_paused = False
        self._live_failure_notice_shown = False
        self._session_reframed_count = 0
        self._original_control_card_id: int | None = None
        self._preparation_in_progress = False
        self._preparation_cancel_event: threading.Event | None = None
        self._preparation_card_ids: set[int] = set()
        self._preparation_mode = ""
        self._preparation_progress_owner: threading.Event | None = None
        self._preparation_progress_cleanup: Callable[[], None] | None = None
        self._preparation_schedule_serial = 0
        self._current_deck_schedule_pending = False
        # Opening a different deck while a one-card warm-up is still running
        # used to drop the new deck's request entirely.  That was especially
        # easy to hit while navigating from a parent deck into a nested deck.
        # Keep one coalesced retry for whichever deck is current when the
        # active preparation finishes.
        self._current_deck_warmup_pending = False
        # Keep one durable first-card reserve per deck.  Work is serialized and
        # current-deck navigation always jumps ahead of this idle queue.
        self._startup_reserve_card_ids: list[int] = []
        self._startup_reserve_schedule_serial = 0
        self._sync_in_progress = False
        self._live_action: QAction | None = None
        self._setup_action: QAction | None = None
        self._settings_action: QAction | None = None
        self._offline_action: QAction | None = None
        self._top_menu: Any | None = None
        self._rng = random.SystemRandom()
        self._main_actions: list[QAction] = []
        self._browser_refs: list[weakref.ReferenceType[Any]] = []
        self._storage_error: Exception | None = None
        self.secret_store: SecretStore | None = None
        self.variant_store: VariantStore | None = None
        self._front_screenshot_service: Any | None = None

    def install(self) -> None:
        if self._installed:
            return
        self._installed = True

        gui_hooks.browser_menus_did_init.append(self.on_browser_menus_did_init)
        gui_hooks.browser_will_show_context_menu.append(
            self.on_browser_will_show_context_menu
        )
        gui_hooks.browser_did_change_row.append(self.on_browser_did_change_row)
        gui_hooks.card_will_show.append(self.on_card_will_show)
        gui_hooks.reviewer_did_show_question.append(
            self.on_reviewer_did_show_question
        )
        gui_hooks.reviewer_did_show_answer.append(self.on_reviewer_did_show_answer)
        gui_hooks.reviewer_did_answer_card.append(self.on_reviewer_did_answer_card)
        gui_hooks.reviewer_will_end.append(self.on_reviewer_will_end)
        gui_hooks.webview_will_set_content.append(
            self.on_webview_will_set_content
        )
        gui_hooks.webview_did_receive_js_message.append(
            self.on_webview_did_receive_js_message
        )
        gui_hooks.profile_did_open.append(self.on_profile_did_open)
        gui_hooks.profile_will_close.append(self.on_profile_will_close)
        gui_hooks.overview_did_refresh.append(self.on_overview_did_refresh)
        gui_hooks.sync_will_start.append(self.on_sync_will_start)
        gui_hooks.sync_did_finish.append(self.on_sync_did_finish)
        self.mw.addonManager.setConfigAction(self.package, self.open_settings)
        self._install_tools_actions()
        if getattr(self.mw, "col", None) is not None:
            self.on_profile_did_open()

    # ------------------------------------------------------------------
    # Menus and selection handling

    def _install_tools_actions(self) -> None:
        form = getattr(self.mw, "form", None)
        menu_bar = getattr(form, "menubar", None)
        if menu_bar is None:
            menu_bar_method = getattr(self.mw, "menuBar", None)
            menu_bar = menu_bar_method() if callable(menu_bar_method) else None
        if menu_bar is not None:
            menu = menu_bar.addMenu(PRODUCT_NAME)
            menu.setObjectName("frageVariatorMenu")
            help_menu = getattr(form, "menuHelp", None)
            help_action = help_menu.menuAction() if help_menu is not None else None
            if help_action is not None:
                menu_bar.removeAction(menu.menuAction())
                menu_bar.insertMenu(help_action, menu)
            self._top_menu = menu
        else:
            # Defensive fallback for transformed/older Anki forms.
            menu = getattr(form, "menuTools", None)
        if menu is None:
            return

        live_action = QAction(tr("menu.automatic_questions"), self.mw)
        live_action.setObjectName("frageVariatorLivePrefetchAction")
        live_action.setCheckable(True)
        live_action.setChecked(bool(self.config.get("live_prefetch_enabled", False)))
        qconnect(live_action.toggled, self._on_live_action_toggled)
        menu.addAction(live_action)
        self._live_action = live_action
        self._main_actions.append(live_action)

        setup_action = QAction(tr("menu.connection"), self.mw)
        setup_action.setObjectName("frageVariatorLiveSetupAction")
        qconnect(setup_action.triggered, self.setup_live_mode)
        menu.addAction(setup_action)
        self._main_actions.append(setup_action)
        self._setup_action = setup_action

        settings_action = QAction(tr("menu.settings"), self.mw)
        settings_action.setObjectName("frageVariatorSettingsAction")
        qconnect(settings_action.triggered, self.open_settings)
        menu.addAction(settings_action)
        self._main_actions.append(settings_action)
        self._settings_action = settings_action

        menu.addSeparator()

        offline_action = QAction(tr("menu.offline_prepare"), self.mw)
        offline_action.setObjectName("frageVariatorOfflinePreparationAction")
        qconnect(offline_action.triggered, self.prepare_deck_for_offline)
        menu.addAction(offline_action)
        self._main_actions.append(offline_action)
        self._offline_action = offline_action
        self._sync_live_action()

    def _retranslate_main_menu(self) -> None:
        """Refresh persistent controls after a language change."""

        labels = (
            (self._live_action, tr("menu.automatic_questions")),
            (self._setup_action, tr("menu.connection")),
            (self._settings_action, tr("menu.settings")),
            (self._offline_action, tr("menu.offline_prepare")),
        )
        for action, label in labels:
            if action is None:
                continue
            setter = getattr(action, "setText", None)
            if callable(setter):
                setter(label)
            elif hasattr(action, "text"):
                action.text = label

        alive_browser_refs: list[weakref.ReferenceType[Any]] = []
        for browser_ref in self._browser_refs:
            browser = browser_ref()
            if browser is None:
                continue
            alive_browser_refs.append(browser_ref)
            browser_labels = (
                (_BROWSER_ACTION_ATTRIBUTE, tr("browser.generate")),
                (_BROWSER_DELETE_ACTION_ATTRIBUTE, tr("browser.delete")),
            )
            for attribute, label in browser_labels:
                try:
                    action = getattr(browser, attribute, None)
                    setter = getattr(action, "setText", None)
                    if callable(setter):
                        setter(label)
                    elif action is not None and hasattr(action, "text"):
                        action.text = label
                except (AttributeError, RuntimeError):
                    # A Qt browser can be destroyed between weakref lookup and
                    # accessing its wrapped C++ action.
                    continue
        self._browser_refs = alive_browser_refs

        # The menu title itself is the always-visible status indicator.
        self._sync_live_action()

        bottom_web = getattr(self.mw, "bottom_web", None)
        if bottom_web is None:
            reviewer = getattr(self.mw, "reviewer", None)
            bottom = getattr(reviewer, "bottom", None)
            bottom_web = getattr(bottom, "web", None)
        evaluate = getattr(bottom_web, "eval", None)
        if callable(evaluate):
            try:
                evaluate(retranslate_script())
            except RuntimeError:
                # The reviewer webview may already be closing.
                pass

        reviewer = getattr(self.mw, "reviewer", None)
        reviewer_web = getattr(reviewer, "web", None)
        evaluate_inline = getattr(reviewer_web, "eval", None)
        if callable(evaluate_inline):
            try:
                card = getattr(reviewer, "card", None)
                card_id = int(card.id) if card is not None else None
                evaluate_inline(retranslate_inline_script(card_id))
            except RuntimeError:
                pass
            except (AttributeError, TypeError, ValueError):
                pass

    def _remember_browser(self, browser: Any) -> None:
        """Track an open browser without keeping the Qt window alive."""

        alive_refs: list[weakref.ReferenceType[Any]] = []
        already_tracked = False
        for browser_ref in self._browser_refs:
            current = browser_ref()
            if current is None:
                continue
            alive_refs.append(browser_ref)
            if current is browser:
                already_tracked = True
        self._browser_refs = alive_refs
        if already_tracked:
            return
        try:
            self._browser_refs.append(weakref.ref(browser))
        except TypeError:
            # Real Anki browser windows support weak references.  Keep the
            # fallback leak-free for transformed/test objects that do not.
            pass

    def open_browser(self) -> None:
        try:
            open_browser = getattr(self.mw, "onBrowse", None)
            if not callable(open_browser):
                raise RuntimeError(tr("browser.unavailable"))
            open_browser()
            tooltip(
                tr("browser.selection_hint"),
                parent=self.mw,
            )
        except Exception as exc:
            self._show_error(tr("error.browser_open"), exc)

    def prepare_deck_for_offline(self) -> None:
        """Prepare the exact next cards of one explicitly selected deck."""

        if (
            self._preparation_in_progress
            and self._preparation_mode in {"automatic", "reserve"}
        ):
            self._cancel_preparation()
        if self._preparation_in_progress or self._generation_in_progress:
            tooltip(tr("notice.preparation_running"), parent=self.mw)
            return
        if getattr(self.mw, "state", "") == "review":
            showInfo(
                tr("notice.finish_review_first"),
                parent=self.mw,
            )
            return
        if not self._storage_available(self.mw):
            return
        automatic_was_enabled = self._live_enabled_requested()
        if not self._live_configuration_ready():
            if not self.setup_live_mode(activate=automatic_was_enabled):
                return
        # An explicit offline request takes priority over the silent one-card
        # warm-up that setup may just have scheduled.
        self._cancel_preparation()

        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        if not profile_key:
            return

        def load_decks(col: Any) -> tuple[list[Any], int | None]:
            current_id: int | None = None
            try:
                current_id = int(col.decks.get_current_id())
            except Exception:
                pass
            return normal_decks(col), current_id

        def decks_loaded(payload: tuple[list[Any], int | None]) -> None:
            if (
                self._profile_epoch != profile_epoch
                or self._profile_key() != profile_key
            ):
                return
            decks, current_id = payload
            dialog = OfflinePreparationDialog(
                self.mw,
                decks=decks,
                default_deck_id=current_id,
                default_count=_bounded_int(
                    self.config.get("offline_prepare_count"), 20, 1, _MAX_OFFLINE_CARDS
                ),
            )
            if not _dialog_was_accepted(dialog):
                return
            deck_id = dialog.deck_id()
            count = _bounded_int(dialog.card_count(), 20, 1, _MAX_OFFLINE_CARDS)
            if deck_id is None:
                return
            self._update_config(offline_prepare_count=count)

            def cards_loaded(card_ids: list[int]) -> None:
                if (
                    self._profile_epoch != profile_epoch
                    or self._profile_key() != profile_key
                ):
                    return
                if not card_ids:
                    showInfo(
                        tr("notice.no_due_cards"),
                        parent=self.mw,
                    )
                    return
                self._start_prepared_batch(card_ids, mode="offline", parent=self.mw)

            operation = QueryOp(
                parent=self.mw,
                op=lambda col: upcoming_card_ids_for_deck(col, deck_id, count),
                success=cards_loaded,
            )
            operation.failure(
                lambda exc: self._show_error(
                    tr("error.next_cards"), exc, self.mw
                )
            )
            operation.with_progress(tr("progress.finding_cards"))
            operation.run_in_background()

        try:
            operation = QueryOp(parent=self.mw, op=load_decks, success=decks_loaded)
            operation.failure(
                lambda exc: self._show_error(
                    tr("error.load_decks"), exc, self.mw
                )
            )
            operation.run_in_background()
        except Exception as exc:
            self._show_error(tr("error.load_decks"), exc, self.mw)

    def on_overview_did_refresh(self, _overview: Any) -> None:
        # This hook runs after a user has actually opened a deck.  It lets that
        # deck jump ahead of the low-priority startup reserve.
        self._schedule_current_deck_preparation()

    def on_sync_will_start(self) -> None:
        self._sync_in_progress = True
        self._cancel_preparation()

    def on_sync_did_finish(self) -> None:
        self._sync_in_progress = False
        self._schedule_current_deck_preparation(delay_ms=250)
        self._schedule_startup_reserve(delay_ms=700)

    def _schedule_current_deck_preparation(self, *, delay_ms: int = 0) -> None:
        self._preparation_schedule_serial += 1
        serial = self._preparation_schedule_serial
        profile_epoch = self._profile_epoch
        self._current_deck_schedule_pending = True

        def start() -> None:
            if (
                serial != self._preparation_schedule_serial
                or profile_epoch != self._profile_epoch
            ):
                return
            self._current_deck_schedule_pending = False
            self._start_current_deck_preparation(schedule_serial=serial)

        QTimer.singleShot(max(0, int(delay_ms)), start)

    def _start_current_deck_preparation(
        self, *, schedule_serial: int | None = None
    ) -> None:
        if schedule_serial is None:
            schedule_serial = self._preparation_schedule_serial
        if (
            self._sync_in_progress
            or self._live_session_active
            or self._live_paused
            or getattr(self.mw, "state", "") == "review"
            or not self._live_enabled_requested()
            or not self._live_configuration_ready()
        ):
            return
        if self._preparation_in_progress or self._generation_in_progress:
            # Do not spend another request in parallel.  Once the current work
            # ends, query Anki's then-current deck again.  A boolean is enough:
            # repeated parent/child navigation coalesces to the latest deck.
            if schedule_serial == self._preparation_schedule_serial:
                self._current_deck_warmup_pending = True
            return
        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        if not profile_key:
            return
        self._current_deck_warmup_pending = False

        def success(card_ids: list[int]) -> None:
            if (
                schedule_serial == self._preparation_schedule_serial
                and self._profile_epoch == profile_epoch
                and self._profile_key() == profile_key
                and card_ids
            ):
                self._start_prepared_batch(card_ids[:1], mode="automatic", parent=self.mw)

        try:
            operation = QueryOp(
                parent=self.mw,
                op=lambda col: upcoming_card_ids_for_current_deck(col, 1),
                success=success,
            )
            operation.failure(lambda _exc: None)
            operation.run_in_background()
        except Exception:
            pass

    def _schedule_startup_reserve(
        self, *, delay_ms: int = _STARTUP_RESERVE_DELAY_MS
    ) -> None:
        """Plan an idle scan for one persistent next-card reserve per deck."""

        self._startup_reserve_schedule_serial += 1
        serial = self._startup_reserve_schedule_serial
        profile_epoch = self._profile_epoch

        def start() -> None:
            if (
                serial != self._startup_reserve_schedule_serial
                or profile_epoch != self._profile_epoch
            ):
                return
            self._start_startup_reserve_scan(schedule_serial=serial)

        QTimer.singleShot(max(0, int(delay_ms)), start)

    def _start_startup_reserve_scan(
        self, *, schedule_serial: int | None = None
    ) -> None:
        if schedule_serial is None:
            schedule_serial = self._startup_reserve_schedule_serial
        if (
            schedule_serial != self._startup_reserve_schedule_serial
            or self._sync_in_progress
            or self._live_session_active
            or self._live_paused
            or getattr(self.mw, "state", "") == "review"
            or not self._live_enabled_requested()
            or not self._live_configuration_ready()
        ):
            return
        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        if not profile_key or self.variant_store is None:
            return

        def success(card_ids: list[int]) -> None:
            if (
                schedule_serial != self._startup_reserve_schedule_serial
                or profile_epoch != self._profile_epoch
                or profile_key != self._profile_key()
            ):
                return
            active_ids = set(self._preparation_card_ids)
            reserve_ids: list[int] = []
            seen: set[int] = set()
            for raw_id in card_ids:
                try:
                    card_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if (
                    card_id <= 0
                    or card_id in seen
                    or card_id in self._prepared_consumed_ids
                    or card_id in active_ids
                ):
                    continue
                seen.add(card_id)
                reserve_ids.append(card_id)
            self._startup_reserve_card_ids = reserve_ids
            self._drain_startup_reserve()

        try:
            operation = QueryOp(
                parent=self.mw,
                op=lambda col: first_upcoming_card_ids_for_all_decks(
                    col,
                    max_decks=_MAX_STARTUP_RESERVE_DECKS,
                ),
                success=success,
            )
            operation.failure(lambda _exc: None)
            operation.run_in_background()
        except Exception:
            pass

    def _drain_startup_reserve(self) -> None:
        """Prepare one idle reserve card, leaving room for user navigation."""

        if (
            not self._startup_reserve_card_ids
            or self._preparation_in_progress
            or self._generation_in_progress
            or self._current_deck_schedule_pending
            or self._sync_in_progress
            or self._live_session_active
            or self._live_paused
            or getattr(self.mw, "state", "") == "review"
            or not self._live_enabled_requested()
            or not self._live_configuration_ready()
        ):
            return
        while self._startup_reserve_card_ids:
            card_id = self._startup_reserve_card_ids.pop(0)
            if card_id in self._prepared_consumed_ids:
                continue
            self._start_prepared_batch(
                [card_id],
                mode="reserve",
                parent=self.mw,
            )
            return

    def _capture_front_screenshots(
        self,
        snapshots: list[Any],
        *,
        success: Callable[[list[Any]], None],
        cancelled: Callable[[], bool],
    ) -> None:
        """Attach rendered-front screenshots on the GUI thread when needed."""

        if not any(
            bool(getattr(snapshot, "front_screenshot_required", False))
            for snapshot in snapshots
        ):
            success(snapshots)
            return
        try:
            if self._front_screenshot_service is None:
                # Qt WebEngine is intentionally imported only for visual cards;
                # plain-text reviews keep the existing zero-overhead path.
                from .front_screenshot import FrontScreenshotService

                self._front_screenshot_service = FrontScreenshotService(self.mw)
            self._front_screenshot_service.capture_snapshots(
                snapshots,
                success=success,
                cancelled=cancelled,
            )
        except Exception:
            success(
                [
                    mark_front_screenshot_failed(snapshot)
                    if getattr(snapshot, "front_screenshot_required", False)
                    else snapshot
                    for snapshot in snapshots
                ]
            )

    def _cancel_front_screenshots(self) -> None:
        service = self._front_screenshot_service
        self._front_screenshot_service = None
        if service is None:
            return
        try:
            service.cancel_all()
        except Exception:
            pass

    def _start_prepared_batch(
        self, card_ids: list[int], *, mode: str, parent: Any
    ) -> None:
        if mode not in {"automatic", "reserve", "offline"}:
            return
        if mode in {"automatic", "reserve"} and self._live_paused:
            return
        ids = list(dict.fromkeys(int(card_id) for card_id in card_ids if int(card_id) > 0))
        ids = ids[:_MAX_OFFLINE_CARDS]
        if not ids:
            return
        if self._preparation_in_progress or self._generation_in_progress:
            if mode == "offline":
                tooltip(tr("notice.preparation_running"), parent=parent)
            return
        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        store = self.variant_store
        settings = self._live_provider_settings(profile_key)
        rewrite_intensity = normalize_rewrite_intensity(
            self.config.get("rewrite_intensity")
        )
        if not profile_key or store is None or settings is None:
            return

        cancel_event = threading.Event()
        self._preparation_in_progress = True
        self._preparation_cancel_event = cancel_event
        self._preparation_card_ids = set(ids)
        self._preparation_mode = mode
        self._preparation_schedule_serial += 1
        self._current_deck_schedule_pending = False
        if mode == "offline":
            self._start_preparation_progress(cancel_event, parent)

        def snapshot_op(col: Any) -> tuple[list[Any], list[Any]]:
            snapshots = snapshot_cards(
                col,
                ids,
                allow_images=True,
                rewrite_intensity=rewrite_intensity,
            )
            existing = store.list_prepared_for_cards(profile_key, ids)
            return snapshots, existing

        def snapshot_success(payload: tuple[list[Any], list[Any]]) -> None:
            if not self._owns_preparation(
                cancel_event, profile_key, profile_epoch, store, rewrite_intensity, mode
            ):
                return
            snapshots, existing_items = payload
            existing_by_id = {int(item.card_id): item for item in existing_items}
            pending: list[Any] = []
            already = 0
            unsuitable = 0
            for snapshot in snapshots:
                card_id = int(snapshot.card_id)
                existing = existing_by_id.get(card_id)
                if (
                    existing is not None
                    and existing.source_hash == snapshot.source_hash
                    and any(value.strip() for value in existing.variants if isinstance(value, str))
                    and card_id not in self._prepared_consumed_ids
                ):
                    self._prepared_cache[(profile_key, card_id)] = existing
                    already += 1
                    continue
                if snapshot.unsupported_reason:
                    unsuitable += 1
                    continue
                pending.append(snapshot)
            unsuitable += max(0, len(ids) - len(snapshots))
            if not pending:
                self._finish_preparation(
                    cancel_event,
                    mode=mode,
                    parent=parent,
                    prepared=0,
                    already=already,
                    unsuitable=unsuitable,
                )
                return

            def screenshots_ready(captured: list[Any]) -> None:
                if not self._owns_preparation(
                    cancel_event,
                    profile_key,
                    profile_epoch,
                    store,
                    rewrite_intensity,
                    mode,
                ):
                    return
                ready = [item for item in captured if not item.unsupported_reason]
                capture_failures = len(captured) - len(ready)
                if not ready:
                    self._finish_preparation(
                        cancel_event,
                        mode=mode,
                        parent=parent,
                        prepared=0,
                        already=already,
                        unsuitable=unsuitable + capture_failures,
                    )
                    return
                self._start_preparation_network(
                    ready,
                    requested=len(ids),
                    already=already,
                    unsuitable=unsuitable + capture_failures,
                    settings=settings,
                    profile_key=profile_key,
                    profile_epoch=profile_epoch,
                    store=store,
                    cancel_event=cancel_event,
                    rewrite_intensity=rewrite_intensity,
                    mode=mode,
                    parent=parent,
                )

            self._capture_front_screenshots(
                pending,
                success=screenshots_ready,
                cancelled=cancel_event.is_set,
            )

        def snapshot_failure(_exc: Exception) -> None:
            if self._preparation_cancel_event is cancel_event:
                self._finish_preparation(
                    cancel_event,
                    mode=mode,
                    parent=parent,
                    prepared=0,
                    already=0,
                    unsuitable=len(ids),
                )

        try:
            operation = QueryOp(parent=parent, op=snapshot_op, success=snapshot_success)
            operation.failure(snapshot_failure)
            operation.run_in_background()
        except Exception as exc:
            snapshot_failure(exc)

    def _start_preparation_network(
        self,
        snapshots: list[Any],
        *,
        requested: int,
        already: int,
        unsuitable: int,
        settings: ProviderSettings,
        profile_key: str,
        profile_epoch: int,
        store: VariantStore,
        cancel_event: threading.Event,
        rewrite_intensity: str,
        mode: str,
        parent: Any,
    ) -> None:
        eligible_snapshots: list[Any] = []
        cached_failure_ids: set[int] = set()
        for snapshot in snapshots:
            failure_key = self._generation_failure_key(
                profile_key, snapshot, rewrite_intensity, settings
            )
            if (
                mode in {"automatic", "reserve"}
                and failure_key is not None
                and failure_key in self._session_failed_generation_keys
            ):
                cached_failure_ids.add(int(snapshot.card_id))
                continue
            eligible_snapshots.append(snapshot)
        snapshots = eligible_snapshots
        unsuitable += len(cached_failure_ids)
        target_ids = {int(snapshot.card_id) for snapshot in snapshots}
        if not target_ids:
            self._finish_preparation(
                cancel_event,
                mode=mode,
                parent=parent,
                prepared=0,
                already=already,
                unsuitable=unsuitable,
            )
            return

        def network_success(result: BatchGenerationResult) -> None:
            self._record_sent_cards(result)
            if not self._owns_preparation(
                cancel_event, profile_key, profile_epoch, store, rewrite_intensity, mode
            ):
                return
            generated: list[GeneratedVariants] = []
            generated_ids: set[int] = set()
            for item in result.generated:
                card_id = int(item.card_id)
                variants = [value.strip() for value in item.variants if value.strip()]
                if card_id not in target_ids or item.warnings or not variants:
                    continue
                item.variants = [variants[0]]
                generated.append(item)
                generated_ids.add(card_id)
            failed_now = len(target_ids - generated_ids)
            error_reason = (
                self._first_generation_failure_reason(result)
                if result.terminal_error
                else ""
            )
            if (
                mode in {"automatic", "reserve"}
                and not result.terminal_error
                and not result.cancelled
            ):
                self._remember_generation_failures(
                    profile_key,
                    snapshots,
                    target_ids - generated_ids,
                    rewrite_intensity,
                    settings,
                )
            if not generated:
                self._finish_preparation(
                    cancel_event,
                    mode=mode,
                    parent=parent,
                    prepared=0,
                    already=already,
                    unsuitable=(
                        unsuitable
                        if result.terminal_error
                        else unsuitable + failed_now
                    ),
                    error_reason=error_reason,
                )
                return
            self._persist_prepared_results(
                generated,
                requested=requested,
                already=already,
                unsuitable=(
                    unsuitable
                    if result.terminal_error
                    else unsuitable + failed_now
                ),
                profile_key=profile_key,
                profile_epoch=profile_epoch,
                store=store,
                cancel_event=cancel_event,
                rewrite_intensity=rewrite_intensity,
                mode=mode,
                parent=parent,
                error_reason=error_reason,
            )

        def network_failure(_exc: Exception) -> None:
            if self._preparation_cancel_event is cancel_event:
                self._finish_preparation(
                    cancel_event,
                    mode=mode,
                    parent=parent,
                    prepared=0,
                    already=already,
                    unsuitable=unsuitable,
                    error_reason=tr("provider_error.unknown"),
                )

        try:
            operation = QueryOp(
                parent=parent,
                op=lambda _col: generate_batch(
                    snapshots,
                    settings,
                    1,
                    cancel_event.is_set,
                    intensity=rewrite_intensity,
                ),
                success=network_success,
            )
            operation.failure(network_failure)
            operation.without_collection().run_in_background()
        except Exception as exc:
            network_failure(exc)

    @staticmethod
    def _generation_failure_key(
        profile_key: str,
        snapshot: Any,
        rewrite_intensity: str,
        settings: ProviderSettings,
    ) -> tuple[str, int, str, str, str, str] | None:
        """Identify one paid attempt without retaining card content or a key."""

        try:
            card_id = int(snapshot.card_id)
            source_hash = str(snapshot.source_hash).strip()
        except (AttributeError, TypeError, ValueError):
            return None
        provider = str(settings.provider).strip().lower()
        model = str(settings.model).strip()
        profile = str(profile_key).strip()
        if card_id <= 0 or not profile or not source_hash or not provider or not model:
            return None
        return (
            profile,
            card_id,
            source_hash,
            normalize_rewrite_intensity(rewrite_intensity),
            provider,
            model,
        )

    def _remember_generation_failures(
        self,
        profile_key: str,
        snapshots: list[Any],
        failed_ids: set[int],
        rewrite_intensity: str,
        settings: ProviderSettings,
    ) -> None:
        """Suppress repeat background charges for unchanged failed cards."""

        if not failed_ids:
            return
        for snapshot in snapshots:
            try:
                card_id = int(snapshot.card_id)
            except (AttributeError, TypeError, ValueError):
                continue
            if card_id not in failed_ids:
                continue
            failure_key = self._generation_failure_key(
                profile_key, snapshot, rewrite_intensity, settings
            )
            if failure_key is not None:
                self._session_failed_generation_keys.add(failure_key)

    @staticmethod
    def _first_generation_failure_reason(result: BatchGenerationResult) -> str:
        for failure in result.failures:
            reason = " ".join(str(failure.reason).split())
            if reason:
                return reason
        return tr("provider_error.unknown")

    def _pause_live_after_failure(self, reason: str) -> None:
        self._live_paused = True
        pending_snapshot_ids = list(
            self._live_inflight_ids - self._live_network_ids
        )
        for card_id in pending_snapshot_ids:
            job_cancel = self._live_job_cancels.get(card_id)
            if job_cancel is not None:
                job_cancel.set()
            self._finish_live_request([card_id], job_cancel)
        self._sync_live_action()
        if self._live_failure_notice_shown:
            return
        self._live_failure_notice_shown = True
        clean_reason = " ".join(str(reason).split()) or tr(
            "provider_error.unknown"
        )
        tooltip(
            tr("notice.live_failed_detail", reason=clean_reason),
            parent=self.mw,
            period=6000,
        )

    def _persist_prepared_results(
        self,
        generated: list[GeneratedVariants],
        *,
        requested: int,
        already: int,
        unsuitable: int,
        profile_key: str,
        profile_epoch: int,
        store: VariantStore,
        cancel_event: threading.Event,
        rewrite_intensity: str,
        mode: str,
        parent: Any,
        error_reason: str = "",
    ) -> None:
        generated_by_id = {int(item.card_id): item for item in generated}

        def save(col: Any) -> tuple[list[Any], int]:
            if not self._owns_preparation(
                cancel_event,
                profile_key,
                profile_epoch,
                store,
                rewrite_intensity,
                mode,
            ):
                return [], len(generated)
            fresh = snapshot_cards(
                col,
                list(generated_by_id),
                allow_images=True,
                rewrite_intensity=rewrite_intensity,
            )
            accepted: list[GeneratedVariants] = []
            for snapshot in fresh:
                item = generated_by_id.get(int(snapshot.card_id))
                if (
                    item is not None
                    and not snapshot.unsupported_reason
                    and int(item.note_id) == int(snapshot.note_id)
                    and item.source_hash == snapshot.source_hash
                ):
                    accepted.append(item)
            if not self._owns_preparation(
                cancel_event,
                profile_key,
                profile_epoch,
                store,
                rewrite_intensity,
                mode,
            ):
                return [], len(generated)
            store.save_prepared_many(profile_key, accepted)
            saved = store.list_prepared_for_cards(
                profile_key, [int(item.card_id) for item in accepted]
            )
            return saved, len(generated) - len(accepted)

        def success(payload: tuple[list[Any], int]) -> None:
            if not self._owns_preparation(
                cancel_event, profile_key, profile_epoch, store, rewrite_intensity, mode
            ):
                return
            saved, stale = payload
            self._variant_cache_revision += 1
            for item in saved:
                self._prepared_cache[(profile_key, int(item.card_id))] = item
            self._finish_preparation(
                cancel_event,
                mode=mode,
                parent=parent,
                prepared=len(saved),
                already=already,
                unsuitable=unsuitable + stale,
                error_reason=error_reason,
            )

        def failure(_exc: Exception) -> None:
            if self._preparation_cancel_event is cancel_event:
                self._finish_preparation(
                    cancel_event,
                    mode=mode,
                    parent=parent,
                    prepared=0,
                    already=already,
                    unsuitable=unsuitable + len(generated),
                    error_reason=error_reason,
                )

        try:
            operation = QueryOp(parent=parent, op=save, success=success)
            operation.failure(failure)
            operation.run_in_background()
        except Exception as exc:
            failure(exc)

    def _owns_preparation(
        self,
        cancel_event: threading.Event,
        profile_key: str,
        profile_epoch: int,
        store: VariantStore,
        rewrite_intensity: str,
        mode: str,
    ) -> bool:
        return bool(
            self._preparation_in_progress
            and self._preparation_cancel_event is cancel_event
            and self._preparation_mode == mode
            and not cancel_event.is_set()
            and self._profile_epoch == profile_epoch
            and self._profile_key() == profile_key
            and self.variant_store is store
            and normalize_rewrite_intensity(self.config.get("rewrite_intensity"))
            == rewrite_intensity
            and (
                mode not in {"automatic", "reserve"}
                or (self._live_enabled_requested() and not self._live_paused)
            )
        )

    def _start_preparation_progress(
        self, owner: threading.Event, parent: Any
    ) -> None:
        progress_started = False
        cancel_poll = QTimer(self.mw)
        cancel_poll.setInterval(200)
        cancel_poll.timeout.connect(
            lambda: (
                self._cancel_preparation()
                if self._preparation_cancel_event is owner
                and self.mw.progress.want_cancel()
                else None
            )
        )
        try:
            self.mw.progress.start(
                parent=parent,
                label=tr("progress.preparing_next_cards"),
                immediate=False,
                title=PRODUCT_NAME,
            )
            progress_started = True
            cancel_poll.start()
        except Exception:
            pass

        def cleanup() -> None:
            nonlocal progress_started
            try:
                cancel_poll.stop()
                cancel_poll.deleteLater()
            except RuntimeError:
                pass
            if progress_started:
                try:
                    self.mw.progress.finish()
                except Exception:
                    pass
                progress_started = False

        self._preparation_progress_owner = owner
        self._preparation_progress_cleanup = cleanup

    def _finish_preparation(
        self,
        owner: threading.Event,
        *,
        mode: str,
        parent: Any,
        prepared: int,
        already: int,
        unsuitable: int,
        error_reason: str = "",
    ) -> None:
        if self._preparation_cancel_event is not owner:
            return
        retry_current_deck = self._current_deck_warmup_pending
        self._current_deck_warmup_pending = False
        self._finish_owned_preparation_progress(owner)
        self._preparation_in_progress = False
        self._preparation_cancel_event = None
        self._preparation_card_ids.clear()
        self._preparation_mode = ""
        if not owner.is_set() and error_reason:
            if mode == "offline":
                showWarning(
                    tr("warning.offline_failed", reason=error_reason),
                    parent=parent,
                )
            else:
                self._pause_live_after_failure(error_reason)
        elif mode == "offline" and not owner.is_set():
            tooltip(
                tr(
                    "notice.offline_result",
                    prepared=prepared,
                    already=already,
                    unsuitable=unsuitable,
                ),
                parent=parent,
                period=6000,
            )
        if self._live_session_active:
            QTimer.singleShot(0, self._refill_live_from_current_question)
        elif retry_current_deck and not owner.is_set():
            # The user may have moved through several parent/subdeck levels
            # while this request was running.  Resolve the currently selected
            # deck now instead of retaining a stale deck id.
            self._schedule_current_deck_preparation()
        elif (
            mode in {"automatic", "reserve"}
            and not owner.is_set()
            and not error_reason
            and self._startup_reserve_card_ids
        ):
            QTimer.singleShot(
                _STARTUP_RESERVE_STEP_DELAY_MS,
                self._drain_startup_reserve,
            )

    def _finish_owned_preparation_progress(self, owner: threading.Event) -> None:
        if self._preparation_progress_owner is not owner:
            return
        cleanup = self._preparation_progress_cleanup
        self._preparation_progress_owner = None
        self._preparation_progress_cleanup = None
        if cleanup is not None:
            cleanup()

    def _cancel_preparation(self) -> None:
        self._preparation_schedule_serial += 1
        self._current_deck_schedule_pending = False
        self._startup_reserve_schedule_serial += 1
        self._startup_reserve_card_ids.clear()
        self._current_deck_warmup_pending = False
        owner = self._preparation_cancel_event
        if owner is not None:
            owner.set()
            self._finish_owned_preparation_progress(owner)
        self._preparation_in_progress = False
        self._preparation_cancel_event = None
        self._preparation_card_ids.clear()
        self._preparation_mode = ""

    def _on_live_action_toggled(self, enabled: bool) -> None:
        if not enabled:
            self._update_config(live_prefetch_enabled=False)
            self._stop_live_session()
            self._cancel_preparation()
            self._sync_live_action()
            tooltip(tr("notice.live_paused"), parent=self.mw)
            return
        if self._live_paused:
            # The unchecked action is the user's explicit retry control after
            # a terminal error. Start with a clean live pipeline.
            self._stop_live_session()
        if self._live_configuration_ready():
            self._update_config(enabled=True, live_prefetch_enabled=True)
            self._start_live_for_current_reviewer()
            self._schedule_current_deck_preparation()
            self._schedule_startup_reserve()
            self._sync_live_action()
            return
        if not self.setup_live_mode():
            self._sync_live_action()

    def setup_live_mode(
        self, _checked: bool = False, *, activate: bool = True
    ) -> bool:
        """Collect a provider/key and explicit consent for automatic sending."""

        profile_key = self._profile_key()
        secret_store = self.secret_store
        if not profile_key or secret_store is None:
            showWarning(tr("error.no_profile"), parent=self.mw)
            self._sync_live_action()
            return False
        consent = self._read_live_consent()
        provider = str(consent.get("provider") or self.config.get("provider", "openai"))
        preferred_model = str(
            consent.get("model") or self.config.get("model", DEFAULT_CONFIG["model"])
        )
        try:
            api_key = secret_store.get(provider, profile_key) or ""
            api_key_source = _secret_source_kind(
                secret_store, provider, profile_key, bool(api_key)
            )
            key_is_persisted = api_key_source == "device"
        except Exception:
            api_key = ""
            key_is_persisted = False
            api_key_source = "missing"
            showWarning(
                tr("warning.remembered_key_unavailable"),
                parent=self.mw,
            )

        dialog = GenerationSetupDialog(
            self.mw,
            provider=provider,
            model=preferred_model,
            variant_count=1,
            api_key=api_key,
            store_api_key_plaintext=key_is_persisted,
            api_key_source=api_key_source,
            max_retries=int(self.config.get("max_retries", 2)),
            live_mode=True,
        )
        if not _dialog_was_accepted(dialog):
            return False

        selected_provider = dialog.provider()
        selected_model = dialog.model()
        selected_key = dialog.api_key()
        selected_key_source = _dialog_api_key_source(dialog, api_key_source)
        persist_key = dialog.store_api_key_plaintext()
        try:
            old_key_remove_error = _store_setup_api_key(
                secret_store,
                selected_provider,
                profile_key,
                selected_key,
                persist=persist_key,
                source=selected_key_source,
            )
        except Exception as exc:
            showWarning(
                tr("warning.key_session_only", detail=_safe_message(exc)),
                parent=self.mw,
            )
        else:
            if old_key_remove_error is not None:
                showWarning(
                    tr("warning.old_key_remove_failed_session_active"),
                    parent=self.mw,
                )
        try:
            # Write the newly accepted consent while a previous revocation gate
            # is still active. Only clear that gate after the new consent is
            # safely on disk, so an I/O error can never revive stale consent.
            self._write_live_consent(selected_provider, selected_model)
            if not self._clear_live_consent_revocation():
                showWarning(
                    tr("warning.revocation_clear_failed"),
                    parent=self.mw,
                )
                self._sync_live_action()
                return False
        except Exception as exc:
            showWarning(
                tr("warning.consent_save_failed", detail=_safe_message(exc)),
                parent=self.mw,
            )
            self._sync_live_action()
            return False
        self._update_config(
            provider=selected_provider,
            model=selected_model,
            variant_count=1,
            enabled=True if activate else bool(self.config.get("enabled", True)),
            live_prefetch_enabled=bool(activate),
        )
        self._stop_live_session()
        self._sync_live_action()
        if activate:
            self._start_live_for_current_reviewer()
            self._schedule_current_deck_preparation()
            self._schedule_startup_reserve()
            tooltip(
                tr(
                    "notice.live_active",
                    count=_bounded_int(
                        self.config.get("live_prefetch_count"), 3, 1, 10
                    ),
                ),
                parent=self.mw,
            )
        else:
            tooltip(tr("notice.connection_saved"), parent=self.mw)
        return True

    def _live_configuration_ready(self) -> bool:
        consent = self._read_live_consent()
        provider = str(consent.get("provider") or "")
        model = str(consent.get("model") or "")
        profile_key = self._profile_key()
        if not profile_key or not provider or not model:
            return False
        secret_store = self.secret_store
        if secret_store is None:
            return False
        try:
            return bool(secret_store.get(provider, profile_key))
        except Exception:
            return False

    def _live_enabled_requested(self) -> bool:
        """Return the local, authoritative opt-in state.

        Consent and a usable key are necessary to send, but they must never
        override the explicit on/off switch.  This remains false even if a
        stale consent file could not be removed from disk.
        """

        return bool(self.config.get("enabled", True)) and bool(
            self.config.get("live_prefetch_enabled", False)
        )

    def _live_consent_path(self) -> Path:
        return self._profile_data_directory() / "live-consent.json"

    def _live_consent_revocation_path(self) -> Path:
        return self._profile_data_directory() / _LIVE_CONSENT_REVOCATION_FILE

    def _live_consent_scope(self) -> str:
        """Return a non-identifying, profile-specific revocation key."""

        try:
            profile_path = self._profile_data_directory().resolve()
        except Exception:
            return ""
        normalized = os.path.normcase(str(profile_path))
        return hashlib.sha256(normalized.encode("utf-8", "surrogatepass")).hexdigest()

    def _revoked_consent_scopes(self) -> set[str]:
        value = self.config.get("live_consent_revoked_profiles", [])
        if not isinstance(value, list):
            return set()
        return {
            item
            for item in value
            if isinstance(item, str) and len(item) == 64
        }

    def _is_live_consent_revoked(self) -> bool:
        scope = self._live_consent_scope()
        if scope and (
            scope in self._session_revoked_consent_scopes
            or scope in self._revoked_consent_scopes()
        ):
            return True
        try:
            return self._live_consent_revocation_path().is_file()
        except Exception:
            return False

    def _mark_live_consent_revoked(self) -> bool:
        """Persist a profile-local deny gate before removing consent data."""

        scope = self._live_consent_scope()
        if scope:
            self._session_revoked_consent_scopes.add(scope)
        scopes = self._revoked_consent_scopes()
        if scope:
            scopes.add(scope)
        config_saved = self._update_config(
            live_consent_revoked_profiles=sorted(scopes)
        )
        marker_saved = False
        try:
            self._live_consent_revocation_path().write_text(
                "revoked\n", encoding="utf-8"
            )
            marker_saved = True
        except Exception:
            pass
        return config_saved or marker_saved

    def _clear_live_consent_revocation(self) -> bool:
        """Clear only the current profile's gate after fresh consent."""

        marker_cleared = True
        try:
            path = self._live_consent_revocation_path()
            if path.exists():
                path.unlink()
        except Exception:
            marker_cleared = False
        scope = self._live_consent_scope()
        scopes = self._revoked_consent_scopes()
        if scope:
            scopes.discard(scope)
        config_saved = self._update_config(
            live_consent_revoked_profiles=sorted(scopes)
        )
        if marker_cleared and config_saved:
            self._session_revoked_consent_scopes.discard(scope)
            return True
        return False

    def _write_live_consent(self, provider: str, model: str) -> None:
        path = self._live_consent_path()
        payload = {
            "version": _LIVE_CONSENT_VERSION,
            "provider": str(provider),
            "model": str(model),
            "allows_images": True,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_live_consent(self) -> dict[str, Any]:
        if self._is_live_consent_revoked():
            return {}
        try:
            payload = json.loads(self._live_consent_path().read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("version") == _LIVE_CONSENT_VERSION
                and isinstance(payload.get("provider"), str)
                and isinstance(payload.get("model"), str)
                and payload.get("allows_images") is True
            ):
                return payload
        except Exception:
            pass
        return {}

    def _clear_live_consent(self) -> bool:
        try:
            path = self._live_consent_path()
            if path.exists():
                path.unlink()
            return True
        except Exception:
            return False

    def _sync_live_action(self) -> None:
        action = self._live_action
        requested = self._live_enabled_requested()
        ready = self._live_configuration_ready()
        active = requested and ready and not self._live_paused
        if not requested:
            status_key = "status.off"
            help_key = "status.off_help"
        elif active:
            status_key = "status.live"
            help_key = "status.live_help"
        else:
            status_key = "status.paused"
            help_key = "status.paused_help"

        if action is not None:
            action.blockSignals(True)
            action.setChecked(active)
            action.blockSignals(False)
            _set_qt_text(
                action,
                "setText",
                "text",
                tr("menu.automatic_questions"),
            )
            help_text = tr(help_key)
            _set_qt_text(action, "setToolTip", "tool_tip", help_text)
            _set_qt_text(action, "setStatusTip", "status_tip", help_text)

        menu = self._top_menu
        if menu is not None:
            _set_qt_text(
                menu,
                "setTitle",
                "title",
                f"{PRODUCT_NAME} {tr(status_key)}",
            )

    def _record_sent_cards(self, result: BatchGenerationResult) -> None:
        """Persist a best-effort, content-free logical request count.

        Usage accounting must never interrupt studying. The result marker also
        protects against duplicate callbacks without retaining card IDs.
        """

        if bool(getattr(result, "usage_recorded", False)):
            return
        result.usage_recorded = True
        count = _bounded_int(
            getattr(result, "sent_cards", 0), 0, 0, _MAX_SENT_CARD_COUNT
        )
        if count <= 0:
            return
        current = _bounded_int(
            self.config.get("sent_card_count"), 0, 0, _MAX_SENT_CARD_COUNT
        )
        updated = dict(self.config)
        updated["sent_card_count"] = min(
            _MAX_SENT_CARD_COUNT, current + count
        )
        self.config = updated
        try:
            self.mw.addonManager.writeConfig(self.package, updated)
        except Exception:
            # A display-only statistic is never allowed to disturb learning.
            pass

    def _start_live_for_current_reviewer(self) -> None:
        if not self._live_enabled_requested() or not self._live_configuration_ready():
            return
        reviewer = getattr(self.mw, "reviewer", None)
        card = getattr(reviewer, "card", None)
        if card is not None:
            self.on_reviewer_did_show_question(card)

    def on_browser_menus_did_init(self, browser: Any) -> None:
        self._remember_browser(browser)
        if getattr(browser, _BROWSER_ACTION_ATTRIBUTE, None) is not None:
            return
        try:
            action = self._new_generate_action(browser, browser)
            form = getattr(browser, "form", None)
            menu = getattr(form, "menu_Cards", None)
            if menu is None:
                # Older/transformed UIs may expose only the Notes menu.
                menu = getattr(form, "menu_Notes", None)
            if menu is None:
                return
            menu.addAction(action)
            setattr(browser, _BROWSER_ACTION_ATTRIBUTE, action)
            delete_action = self._new_delete_action(browser, browser)
            menu.addAction(delete_action)
            setattr(browser, _BROWSER_DELETE_ACTION_ATTRIBUTE, delete_action)
            self._update_browser_action(browser)
        except Exception as exc:
            self._show_error(tr("error.browser_action"), exc)

    def on_browser_will_show_context_menu(self, browser: Any, menu: Any) -> None:
        try:
            action = self._new_generate_action(browser, menu)
            action.setEnabled(bool(self._selected_card_ids(browser)))
            menu.addAction(action)
            delete_action = self._new_delete_action(browser, menu)
            delete_action.setEnabled(bool(self._selected_card_ids(browser)))
            menu.addAction(delete_action)
        except Exception as exc:
            self._show_error(tr("error.context_menu"), exc)

    def on_browser_did_change_row(self, browser: Any) -> None:
        self._update_browser_action(browser)

    def _new_generate_action(self, browser: Any, parent: Any) -> QAction:
        action = QAction(tr("browser.generate"), parent)
        action.setObjectName("frageVariatorGenerateAction")
        qconnect(
            action.triggered,
            lambda: self.generate_for_browser_selection(browser),
        )
        return action

    def _new_delete_action(self, browser: Any, parent: Any) -> QAction:
        action = QAction(tr("browser.delete"), parent)
        action.setObjectName("frageVariatorDeleteAction")
        qconnect(action.triggered, lambda: self.delete_for_browser_selection(browser))
        return action

    def _update_browser_action(self, browser: Any) -> None:
        action = getattr(browser, _BROWSER_ACTION_ATTRIBUTE, None)
        if action is None:
            return
        try:
            has_selection = bool(self._selected_card_ids(browser))
            action.setEnabled(has_selection)
            delete_action = getattr(browser, _BROWSER_DELETE_ACTION_ATTRIBUTE, None)
            if delete_action is not None:
                delete_action.setEnabled(has_selection)
        except Exception:
            action.setEnabled(False)

    @staticmethod
    def _selected_card_ids(browser: Any) -> list[int]:
        selected_cards = getattr(browser, "selected_cards", None)
        if not callable(selected_cards):
            return []
        ids: list[int] = []
        seen: set[int] = set()
        for raw_id in selected_cards():
            try:
                card_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if card_id not in seen:
                seen.add(card_id)
                ids.append(card_id)
        return ids

    def generate_for_browser_selection(self, browser: Any) -> None:
        """Save the browser editor first, then read ``selected_cards()``."""

        if self._generation_in_progress:
            showInfo(tr("notice.generation_running"), parent=browser)
            return
        if not self._storage_available(browser):
            return

        def after_note_saved() -> None:
            try:
                card_ids = self._selected_card_ids(browser)
                if not card_ids:
                    showInfo(
                        tr("notice.select_card"),
                        parent=browser,
                    )
                    return
                if len(card_ids) > _MAX_GENERATION_CARDS:
                    showWarning(
                        tr("notice.max_cards", count=_MAX_GENERATION_CARDS),
                        parent=browser,
                    )
                    return
                self._show_generation_setup(browser, card_ids)
            except Exception as exc:
                self._show_error(tr("error.read_selection"), exc, browser)

        editor = getattr(browser, "editor", None)
        save_first = getattr(editor, "call_after_note_saved", None)
        if callable(save_first):
            try:
                save_first(after_note_saved, keepFocus=True)
            except TypeError:
                # Keep compatibility with versions whose method did not yet
                # expose keepFocus as a keyword.
                save_first(after_note_saved)
            except Exception as exc:
                self._show_error(tr("error.save_note"), exc, browser)
        else:
            after_note_saved()

    def delete_for_browser_selection(self, browser: Any) -> None:
        if not self._storage_available(browser):
            return
        card_ids = self._selected_card_ids(browser)
        if not card_ids:
            showInfo(tr("notice.select_card"), parent=browser)
            return
        if not askUser(
            tr("confirm.delete_selected", count=len(card_ids)),
            parent=browser,
        ):
            return
        store = self.variant_store
        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        if store is None or not profile_key:
            return

        def success(count: int) -> None:
            if (
                self._profile_epoch != profile_epoch
                or self.variant_store is not store
            ):
                return
            self._variant_cache_revision += 1
            for card_id in card_ids:
                self._review_choices.pop(card_id, None)
                self._variant_cycles.pop(card_id, None)
                self._variant_cache.pop((profile_key, card_id), None)
                self._prepared_cache.pop((profile_key, card_id), None)
                self._prepared_consumed_ids.discard(card_id)
            tooltip(tr("notice.deleted_selected", count=count), parent=browser)

        def failure(exc: Exception) -> None:
            if (
                self._profile_epoch == profile_epoch
                and self.variant_store is store
            ):
                self._show_error(
                    tr("error.delete_variants"), exc, browser
                )

        def delete(_col: Any) -> int:
            return store.delete_cards(
                profile_key, card_ids
            ) + store.delete_prepared_cards(profile_key, card_ids)

        operation = QueryOp(
            parent=browser,
            op=delete,
            success=success,
        )
        operation.failure(failure)
        operation.without_collection().run_in_background()

    # ------------------------------------------------------------------
    # Generation pipeline

    def _show_generation_setup(self, parent: Any, card_ids: list[int]) -> None:
        provider = str(self.config.get("provider", "openai"))
        profile_key = self._profile_key()
        secret_store = self.secret_store
        if secret_store is None or not profile_key:
            showWarning(tr("error.no_profile"), parent=parent)
            return
        try:
            api_key = secret_store.get(provider, profile_key) or ""
            api_key_source = _secret_source_kind(
                secret_store, provider, profile_key, bool(api_key)
            )
            key_is_persisted = api_key_source == "device"
        except Exception:
            api_key = ""
            key_is_persisted = False
            api_key_source = "missing"
            showWarning(
                tr("warning.remembered_key_unavailable"),
                parent=parent,
            )

        dialog = GenerationSetupDialog(
            parent,
            card_count=len(card_ids),
            max_retries=int(self.config.get("max_retries", 2)),
            provider=provider,
            model=str(self.config.get("model", DEFAULT_CONFIG["model"])),
            variant_count=1,
            api_key=api_key,
            store_api_key_plaintext=key_is_persisted,
            api_key_source=api_key_source,
        )
        if not _dialog_was_accepted(dialog):
            return

        settings = ProviderSettings(
            provider=dialog.provider(),
            model=dialog.model(),
            api_key=dialog.api_key(),
            timeout_seconds=int(self.config.get("timeout_seconds", 90)),
            max_retries=int(self.config.get("max_retries", 2)),
        )
        selected_key_source = _dialog_api_key_source(dialog, api_key_source)
        variant_count = dialog.variant_count()
        rewrite_intensity = normalize_rewrite_intensity(
            self.config.get("rewrite_intensity")
        )
        start_profile_key = self._profile_key()
        start_profile_epoch = self._profile_epoch
        if not start_profile_key:
            showWarning(tr("error.no_profile"), parent=parent)
            return

        persist_key = dialog.store_api_key_plaintext()
        try:
            old_key_remove_error = _store_setup_api_key(
                secret_store,
                settings.provider,
                start_profile_key,
                settings.api_key,
                persist=persist_key,
                source=selected_key_source,
            )
        except Exception as exc:
            showWarning(
                tr("warning.key_session_only", detail=_safe_message(exc)),
                parent=parent,
            )
        else:
            if old_key_remove_error is not None:
                showWarning(
                    tr("warning.old_key_remove_failed_session_active"),
                    parent=parent,
                )

        self._update_config(
            provider=settings.provider,
            model=settings.model,
            variant_count=variant_count,
        )
        self._cancel_preparation()
        self._generation_in_progress = True
        cancel_event = threading.Event()
        self._generation_cancel_event = cancel_event
        self._start_snapshot_query(
            parent,
            card_ids,
            settings,
            variant_count,
            start_profile_key,
            start_profile_epoch,
            cancel_event,
            rewrite_intensity,
        )

    def _start_snapshot_query(
        self,
        parent: Any,
        card_ids: list[int],
        settings: ProviderSettings,
        variant_count: int,
        start_profile_key: str,
        start_profile_epoch: int,
        cancel_event: threading.Event,
        rewrite_intensity: str,
    ) -> None:
        def snapshot_success(snapshots: list[Any]) -> None:
            if (
                cancel_event.is_set()
                or self._profile_epoch != start_profile_epoch
                or self._profile_key() != start_profile_key
            ):
                self._finish_manual_generation(
                    cancel_event,
                    start_profile_key,
                    start_profile_epoch,
                )
                return
            def screenshots_ready(captured: list[Any]) -> None:
                if (
                    cancel_event.is_set()
                    or self._profile_epoch != start_profile_epoch
                    or self._profile_key() != start_profile_key
                ):
                    self._finish_manual_generation(
                        cancel_event,
                        start_profile_key,
                        start_profile_epoch,
                    )
                    return
                self._start_network_query(
                    parent,
                    captured,
                    settings,
                    variant_count,
                    start_profile_key,
                    start_profile_epoch,
                    cancel_event,
                    rewrite_intensity,
                )

            self._capture_front_screenshots(
                snapshots,
                success=screenshots_ready,
                cancelled=cancel_event.is_set,
            )

        def snapshot_failure(exc: Exception) -> None:
            if not self._finish_manual_generation(
                cancel_event,
                start_profile_key,
                start_profile_epoch,
            ):
                return
            self._show_error(tr("error.prepare_cards"), exc, parent)

        try:
            operation = QueryOp(
                parent=parent,
                op=lambda col: snapshot_cards(
                    col,
                    card_ids,
                    allow_images=True,
                    rewrite_intensity=rewrite_intensity,
                ),
                success=snapshot_success,
            )
            operation.failure(snapshot_failure)
            operation.with_progress(tr("progress.prepare_cards"))
            operation.run_in_background()
        except Exception as exc:
            snapshot_failure(exc)

    def _start_network_query(
        self,
        parent: Any,
        snapshots: list[Any],
        settings: ProviderSettings,
        variant_count: int,
        start_profile_key: str,
        start_profile_epoch: int,
        cancel_event: threading.Event,
        rewrite_intensity: str,
    ) -> None:
        """Run all provider traffic without holding Anki's collection lane."""

        progress_started = False
        # Keep the cancellation poll alive even if the Browser window that
        # started the operation is closed before the request finishes.
        cancel_poll = QTimer(self.mw)
        cancel_poll.setInterval(200)
        cancel_poll.timeout.connect(
            lambda: cancel_event.set() if self.mw.progress.want_cancel() else None
        )
        try:
            self.mw.progress.start(
                parent=parent,
                label=tr("progress.ai_generating"),
                immediate=False,
                title=PRODUCT_NAME,
            )
            progress_started = True
            cancel_poll.start()
        except Exception:
            pass

        def finish_progress() -> None:
            nonlocal progress_started
            try:
                cancel_poll.stop()
                cancel_poll.deleteLater()
            except RuntimeError:
                pass
            if progress_started:
                try:
                    self.mw.progress.finish()
                except Exception:
                    pass
                progress_started = False

        self._generation_progress_owner = cancel_event
        self._generation_progress_cleanup = finish_progress

        def success(result: BatchGenerationResult) -> None:
            self._record_sent_cards(result)
            if not self._finish_manual_generation(
                cancel_event,
                start_profile_key,
                start_profile_epoch,
            ):
                return
            if normalize_rewrite_intensity(
                self.config.get("rewrite_intensity")
            ) != rewrite_intensity:
                showWarning(
                    tr("warning.intensity_changed_discard"),
                    parent=parent,
                )
                return
            self._review_results(
                parent,
                result,
                start_profile_key,
                start_profile_epoch,
                rewrite_intensity,
            )

        def failure(exc: Exception) -> None:
            if not self._finish_manual_generation(
                cancel_event,
                start_profile_key,
                start_profile_epoch,
            ):
                return
            message = _safe_message(exc, settings.api_key)
            showWarning(
                tr("warning.ai_failed", detail=message),
                parent=parent,
            )

        try:
            operation = QueryOp(
                parent=parent,
                # QueryOp still supplies mw.col to the callable; the lambda
                # intentionally ignores it and generate_batch has no Anki API.
                op=lambda _col: generate_batch(
                    snapshots,
                    settings,
                    variant_count,
                    cancel_event.is_set,
                    intensity=rewrite_intensity,
                ),
                success=success,
            )
            operation.failure(failure)
            operation.without_collection()
            operation.run_in_background()
        except Exception as exc:
            failure(exc)

    def _finish_manual_generation(
        self,
        owner: threading.Event,
        profile_key: str,
        profile_epoch: int,
    ) -> bool:
        """Finish the current Browser generation and resume a dropped warm-up.

        Late callbacks from a closed/switched profile or a superseded request
        are deliberately ignored.  Clearing the pending flag before scheduling
        makes duplicate success/failure callbacks harmless, while the normal
        schedule serial and live-state guards remain authoritative.
        """

        self._finish_owned_generation_progress(owner)
        if (
            self._generation_cancel_event is not owner
            or self._profile_epoch != profile_epoch
            or self._profile_key() != profile_key
        ):
            return False

        self._generation_in_progress = False
        self._generation_cancel_event = None
        if self._current_deck_warmup_pending:
            self._current_deck_warmup_pending = False
            self._schedule_current_deck_preparation()
        return True

    def _review_results(
        self,
        parent: Any,
        result: BatchGenerationResult,
        start_profile_key: str,
        start_profile_epoch: int,
        rewrite_intensity: str,
    ) -> None:
        try:
            dialog = ReviewResultsDialog(result, parent)
            if not _dialog_was_accepted(dialog):
                return
            accepted = dialog.selected_generated()
            if not accepted:
                showInfo(tr("notice.no_variants_selected"), parent=parent)
                return
            self._persist_accepted(
                parent,
                accepted,
                start_profile_key,
                start_profile_epoch,
                rewrite_intensity,
            )
        except Exception as exc:
            self._show_error(tr("error.accept_results"), exc, parent)

    def _persist_accepted(
        self,
        parent: Any,
        accepted: list[GeneratedVariants],
        start_profile_key: str,
        start_profile_epoch: int,
        rewrite_intensity: str,
    ) -> None:
        store = self.variant_store
        if store is None or not self._storage_available(parent):
            return
        if (
            self._profile_epoch != start_profile_epoch
            or self._profile_key() != start_profile_key
        ):
            showWarning(
                tr("warning.profile_changed"),
                parent=parent,
            )
            return

        def save(col: Any) -> tuple[list[Any], list[int], bool]:
            if (
                self._profile_epoch != start_profile_epoch
                or self.variant_store is not store
            ):
                raise InterruptedError(tr("warning.profile_changed"))
            if normalize_rewrite_intensity(
                self.config.get("rewrite_intensity")
            ) != rewrite_intensity:
                return [], [], True
            fresh: list[GeneratedVariants] = []
            stale: list[int] = []
            for generated in accepted:
                try:
                    current = snapshot_cards(
                        col,
                        [generated.card_id],
                        allow_images=True,
                        rewrite_intensity=rewrite_intensity,
                    )[0]
                except Exception:
                    stale.append(int(generated.card_id))
                    continue
                if (
                    current.note_id != generated.note_id
                    or current.source_hash != generated.source_hash
                    or current.unsupported_reason
                ):
                    stale.append(int(generated.card_id))
                else:
                    fresh.append(generated)
            store.save_many(start_profile_key, fresh)
            saved = store.list_for_cards(
                start_profile_key, [item.card_id for item in fresh]
            )
            return saved, stale, False

        def success(outcome: tuple[list[Any], list[int], bool]) -> None:
            if (
                self._profile_epoch != start_profile_epoch
                or self.variant_store is not store
            ):
                return
            saved, stale, intensity_changed = outcome
            if intensity_changed:
                showWarning(
                    tr("warning.intensity_changed_not_saved"),
                    parent=parent,
                )
                return
            self._variant_cache_revision += 1
            for generated in accepted:
                self._review_choices.pop(int(generated.card_id), None)
                self._variant_cycles.pop(int(generated.card_id), None)
                self._variant_cache.pop(
                    (start_profile_key, int(generated.card_id)), None
                )
            for stored in saved:
                self._variant_cache[(start_profile_key, int(stored.card_id))] = stored
            if stale:
                showWarning(
                    tr("warning.stale_results", count=len(stale)),
                    parent=parent,
                )
            tooltip(
                tr("notice.saved_variants", count=len(saved)),
                parent=parent,
            )

        def failure(exc: Exception) -> None:
            if (
                self._profile_epoch == start_profile_epoch
                and self.variant_store is store
            ):
                self._show_error(
                    tr("error.save_variants"), exc, parent
                )

        try:
            operation = QueryOp(parent=parent, op=save, success=success)
            operation.failure(failure)
            operation.run_in_background()
        except Exception as exc:
            failure(exc)

    # ------------------------------------------------------------------
    # Live review prefetch

    def on_reviewer_did_show_question(self, card: Any) -> None:
        self._show_original_control_for(card)
        if (
            not self._live_enabled_requested()
            or not self._live_configuration_ready()
        ):
            return
        if not self._live_session_active:
            self._live_session_epoch += 1
            self._live_session_active = True
            self._live_cancel_event = threading.Event()
            self._live_ready.clear()
            self._live_in_use.clear()
            self._live_inflight_ids.clear()
            self._live_failed_ids.clear()
        try:
            current_card_id = int(card.id)
        except Exception:
            return
        self._live_refill(current_card_id=current_card_id, after_answer=False)

    def on_reviewer_did_show_answer(self, card: Any) -> None:
        # The answer side itself always contains the original question, so the
        # temporary front-side disclosure control is no longer needed.
        self._hide_original_control(card)

    def on_reviewer_will_end(self) -> None:
        self._hide_original_control()
        self._stop_live_session()
        self._review_choices.clear()
        self._variant_cycles.clear()
        count = self._session_reframed_count
        self._session_reframed_count = 0
        if count > 0:
            tooltip(
                tr("notice.session_summary", count=count),
                parent=self.mw,
            )
        # Once the reviewer has yielded, refresh the durable reserves while the
        # user is deciding what to study next.
        self._schedule_current_deck_preparation(delay_ms=250)
        self._schedule_startup_reserve(delay_ms=700)

    def on_webview_will_set_content(
        self, web_content: Any, context: Any
    ) -> None:
        reviewer = getattr(context, "reviewer", None)
        if (
            reviewer is None
            or context.__class__.__name__ != "ReviewerBottomBar"
            or getattr(reviewer, "mw", None) is not self.mw
        ):
            return
        web_content.head += bottom_bar_head()

    def on_webview_did_receive_js_message(
        self,
        handled: tuple[bool, Any],
        message: str,
        context: Any,
    ) -> tuple[bool, Any]:
        if handled[0]:
            return handled
        toggle_request = parse_original_toggle_message(message)
        if toggle_request is None:
            return handled
        reviewer = getattr(context, "reviewer", None)
        if (
            reviewer is None
            or context.__class__.__name__ != "ReviewerBottomBar"
            or getattr(reviewer, "mw", None) is not self.mw
        ):
            return handled
        visible, requested_card_id = toggle_request
        try:
            current_card_id = int(reviewer.card.id)
            choice = self._review_choices.get(current_card_id)
            if (
                requested_card_id != current_card_id
                or choice is None
                or not choice.front_original_fragment.strip()
            ):
                # Consume delayed messages from the previous card, but never
                # apply them to the new one.
                return (True, None)
            reviewer.web.eval(
                show_original_inline_script(requested_card_id)
                if visible
                else hide_original_inline_script(requested_card_id)
            )
            # Return keyboard focus to the card so Anki's normal Space shortcut
            # keeps revealing the answer after a quick look at the original.
            reviewer.web.setFocus()
        except Exception:
            pass
        return (True, None)

    def _show_original_control_for(self, card: Any) -> None:
        try:
            card_id = int(card.id)
        except Exception:
            self._hide_original_control()
            return
        previous_card_id = self._original_control_card_id
        if previous_card_id is not None and previous_card_id != card_id:
            # Cards can change without the usual answer hook (skip, bury,
            # suspend or delete). Retire the old owner before considering the
            # next card, while keeping every queued command card-scoped.
            self._hide_original_control(previous_card_id)
        choice = self._review_choices.get(card_id)
        if choice is None or not choice.variant:
            self._hide_original_control(card_id)
            return
        context_available = original_context_available(
            choice.front_original_fragment,
            omit_images=False,
        )
        if not context_available:
            self._hide_original_control(card_id)
            return
        reviewer = getattr(self.mw, "reviewer", None)
        current_card = getattr(reviewer, "card", None)
        if reviewer is None or current_card is None:
            return
        try:
            if int(current_card.id) != card_id:
                self._hide_original_control(card_id)
                return
            # Original-question context lives directly below the generated
            # prompt. The lower webview receives only an availability flag,
            # keeping its toggle at Anki's native button size.
            self._original_control_card_id = card_id
            reviewer.web.eval(set_original_inline_script(card_id))
            reviewer.bottom.web.eval(
                set_original_script("available", card_id)
            )
        except Exception:
            self._hide_original_control(card_id)

    def _hide_original_control(self, card: Any | int | None = None) -> None:
        reviewer = getattr(self.mw, "reviewer", None)
        if reviewer is None:
            return
        scope = card
        if scope is None:
            scope = self._original_control_card_id
        if scope is None:
            scope = getattr(reviewer, "card", None)
        try:
            card_id = int(scope.id) if hasattr(scope, "id") else int(scope)
        except (AttributeError, TypeError, ValueError):
            return
        # The toolbar and card live in separate webviews. One of them can
        # already be rebuilding or closing while the other is still alive, so
        # clean them independently. In particular, a toolbar error must never
        # leave stale front-side context beside the revealed answer.
        for web, script in (
            (
                getattr(getattr(reviewer, "bottom", None), "web", None),
                hide_original_script(card_id),
            ),
            (
                getattr(reviewer, "web", None),
                clear_original_inline_script(card_id),
            ),
        ):
            evaluate = getattr(web, "eval", None)
            if not callable(evaluate):
                continue
            try:
                evaluate(script)
            except Exception:
                continue
        if self._original_control_card_id == card_id:
            self._original_control_card_id = None

    def _stop_live_session(self) -> None:
        self._live_session_epoch += 1
        self._live_session_active = False
        if self._live_cancel_event is not None:
            self._live_cancel_event.set()
        self._live_cancel_event = None
        self._live_ready.clear()
        self._live_in_use.clear()
        self._live_inflight_ids.clear()
        self._live_network_ids.clear()
        self._live_failed_ids.clear()
        self._live_desired_ids = ()
        for job_cancel in self._live_job_cancels.values():
            job_cancel.set()
        self._live_job_cancels.clear()
        self._live_paused = False
        self._live_failure_notice_shown = False
        self._variant_cycles.clear()

    def _live_refill(self, *, current_card_id: int, after_answer: bool) -> None:
        if (
            not self._live_session_active
            or self._live_paused
            or not self._live_enabled_requested()
            or not self._live_configuration_ready()
        ):
            return
        cancel_event = self._live_cancel_event
        col = getattr(self.mw, "col", None)
        if cancel_event is None or cancel_event.is_set() or col is None:
            return

        lookahead = _bounded_int(
            self.config.get("live_prefetch_count"), 3, 1, 10
        )
        try:
            fetch_limit = lookahead if after_answer else lookahead + 1
            queued = col.sched.get_queued_cards(fetch_limit=fetch_limit)
            entries = tuple(getattr(queued, "cards", ()) or ())
            if after_answer:
                candidate_ids = select_after_answer_lookahead(entries, lookahead)
            else:
                candidate_ids = select_question_lookahead(
                    entries, current_card_id, lookahead
                )
        except Exception:
            return

        # Scheduler queues can contain the same card more than once.  One
        # generated question is sufficient for all occurrences in this live
        # window, so preserve order while deduplicating IDs.
        desired_ids = tuple(dict.fromkeys(int(card_id) for card_id in candidate_ids))
        self._live_desired_ids = desired_ids
        desired_set = set(desired_ids)

        # Reconcile every refill with Anki's current next-N window.  Jobs that
        # have not sent yet are cancelled; already-running HTTP calls are
        # ignored on completion and never occupy a slot for the new window.
        for card_id in tuple(self._live_inflight_ids):
            if card_id not in desired_set:
                job_cancel = self._live_job_cancels.get(card_id)
                if job_cancel is not None:
                    job_cancel.set()
                # A request that has already entered the network stage may
                # have been received/billed. Keep it in the global capacity
                # count until its callback returns instead of stacking a new
                # full window on top. Snapshot-only jobs can be dropped now.
                if card_id not in self._live_network_ids:
                    self._live_job_cancels.pop(card_id, None)
                    self._live_inflight_ids.discard(card_id)
        for card_id in tuple(self._live_ready):
            if card_id not in desired_set:
                self._live_ready.pop(card_id, None)
        self._live_failed_ids.intersection_update(desired_set)

        target_ids = [
            card_id
            for card_id in desired_ids
            if card_id not in self._live_ready
            and card_id not in self._live_in_use
            and card_id not in self._live_inflight_ids
            and card_id not in self._live_failed_ids
            and card_id not in self._preparation_card_ids
        ]
        if not target_ids:
            return
        available_slots = max(
            0,
            _bounded_int(self.config.get("live_prefetch_count"), 3, 1, 10)
            - len(self._live_inflight_ids)
            - len(desired_set.intersection(self._live_ready)),
        )
        if available_slots <= 0:
            return
        target_ids = target_ids[:available_slots]

        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        session_epoch = self._live_session_epoch
        rewrite_intensity = normalize_rewrite_intensity(
            self.config.get("rewrite_intensity")
        )
        if not profile_key:
            return
        for card_id in target_ids:
            job_cancel = threading.Event()
            self._live_inflight_ids.add(card_id)
            self._live_job_cancels[card_id] = job_cancel
            self._start_live_card_snapshot(
                card_id,
                profile_key,
                profile_epoch,
                session_epoch,
                cancel_event,
                job_cancel,
                rewrite_intensity,
            )

    def _start_live_card_snapshot(
        self,
        card_id: int,
        profile_key: str,
        profile_epoch: int,
        session_epoch: int,
        cancel_event: threading.Event,
        job_cancel: threading.Event,
        rewrite_intensity: str,
    ) -> None:
        def snapshot_success(snapshots: list[Any]) -> None:
            if not self._owns_live_job(
                card_id,
                profile_key,
                profile_epoch,
                session_epoch,
                cancel_event,
                job_cancel,
            ):
                return
            snapshot = snapshots[0] if snapshots else None
            if snapshot is None or snapshot.unsupported_reason:
                self._live_failed_ids.add(card_id)
                self._finish_live_request([card_id], job_cancel)
                return
            prepared = self._prepared_cache.get((profile_key, card_id))
            if (
                prepared is not None
                and prepared.source_hash == snapshot.source_hash
                and any(value.strip() for value in prepared.variants if isinstance(value, str))
                and card_id not in self._prepared_consumed_ids
            ):
                # The persistent one-shot will be consumed only when this card
                # is actually shown. Mark the current window as satisfied so a
                # paid live request is not started for the same card.
                self._live_failed_ids.add(card_id)
                self._finish_live_request([card_id], job_cancel)
                return
            if prepared is not None:
                self._prepared_cache.pop((profile_key, card_id), None)
                self._delete_prepared_record(profile_key, card_id, self.variant_store)

            def screenshot_ready(captured: list[Any]) -> None:
                if not self._owns_live_job(
                    card_id,
                    profile_key,
                    profile_epoch,
                    session_epoch,
                    cancel_event,
                    job_cancel,
                ):
                    return
                ready = captured[0] if captured else None
                if ready is None or ready.unsupported_reason:
                    self._live_failed_ids.add(card_id)
                    self._finish_live_request([card_id], job_cancel)
                    return
                self._live_network_ids.add(card_id)
                self._start_live_network(
                    [ready],
                    [card_id],
                    profile_key,
                    profile_epoch,
                    session_epoch,
                    cancel_event,
                    job_cancel,
                    rewrite_intensity,
                )

            self._capture_front_screenshots(
                [snapshot],
                success=screenshot_ready,
                cancelled=lambda: (
                    cancel_event.is_set()
                    or job_cancel.is_set()
                    or not self._owns_live_job(
                        card_id,
                        profile_key,
                        profile_epoch,
                        session_epoch,
                        cancel_event,
                        job_cancel,
                    )
                ),
            )

        def snapshot_failure(_exc: Exception) -> None:
            if self._owns_live_job(
                card_id,
                profile_key,
                profile_epoch,
                session_epoch,
                cancel_event,
                job_cancel,
            ):
                self._live_failed_ids.add(card_id)
                self._finish_live_request([card_id], job_cancel)

        try:
            operation = QueryOp(
                parent=self.mw,
                op=lambda collection: snapshot_cards(
                    collection,
                    [card_id],
                    allow_images=True,
                    rewrite_intensity=rewrite_intensity,
                ),
                success=snapshot_success,
            )
            operation.failure(snapshot_failure)
            operation.run_in_background()
        except Exception as exc:
            snapshot_failure(exc)

    def _start_live_network(
        self,
        snapshots: list[Any],
        target_ids: list[int],
        profile_key: str,
        profile_epoch: int,
        session_epoch: int,
        cancel_event: threading.Event,
        job_cancel: threading.Event | None = None,
        rewrite_intensity: str = DEFAULT_REWRITE_INTENSITY,
    ) -> None:
        if self._live_paused:
            self._live_failed_ids.update(target_ids)
            self._finish_live_request(target_ids, job_cancel)
            return
        settings = self._live_provider_settings(profile_key)
        if settings is None:
            self._live_failed_ids.update(target_ids)
            self._finish_live_request(target_ids, job_cancel)
            return

        eligible_snapshots: list[Any] = []
        cached_failure_ids: set[int] = set()
        for snapshot in snapshots:
            failure_key = self._generation_failure_key(
                profile_key, snapshot, rewrite_intensity, settings
            )
            if (
                failure_key is not None
                and failure_key in self._session_failed_generation_keys
            ):
                cached_failure_ids.add(int(snapshot.card_id))
                continue
            eligible_snapshots.append(snapshot)
        if cached_failure_ids:
            self._live_failed_ids.update(cached_failure_ids)
            self._finish_live_request(list(cached_failure_ids), job_cancel)
            target_ids = [
                card_id for card_id in target_ids if card_id not in cached_failure_ids
            ]
            snapshots = eligible_snapshots
            if not target_ids:
                return

        def success(result: BatchGenerationResult) -> None:
            self._record_sent_cards(result)
            if not self._owns_live_pipeline(
                profile_key, profile_epoch, session_epoch, cancel_event
            ):
                return
            if job_cancel is not None and (
                job_cancel.is_set()
                or any(
                    card_id not in self._live_desired_ids
                    or self._live_job_cancels.get(card_id) is not job_cancel
                    for card_id in target_ids
                )
            ):
                self._finish_live_request(target_ids, job_cancel)
                return
            generated_ids: set[int] = set()
            failed_ids = {int(failure.card_id) for failure in result.failures}
            for generated in result.generated:
                card_id = int(generated.card_id)
                if card_id not in target_ids or card_id not in self._live_desired_ids:
                    continue
                if generated.warnings:
                    failed_ids.add(card_id)
                    continue
                variants = [value.strip() for value in generated.variants if value.strip()]
                if not variants:
                    continue
                generated.variants = [variants[0]]
                generated_ids.add(card_id)
                self._live_ready.pop(card_id, None)
                self._live_ready[card_id] = generated
            # A provider returning a syntactically valid but empty/mismatched
            # batch must not trigger an immediate paid retry loop.
            failed_ids.update(set(target_ids) - generated_ids - failed_ids)
            self._live_failed_ids.update(failed_ids)
            if not result.terminal_error and not result.cancelled:
                self._remember_generation_failures(
                    profile_key,
                    snapshots,
                    failed_ids,
                    rewrite_intensity,
                    settings,
                )
            if result.terminal_error:
                self._pause_live_after_failure(
                    self._first_generation_failure_reason(result)
                )
            desired_set = set(self._live_desired_ids)
            for card_id in tuple(self._live_ready):
                if card_id not in desired_set:
                    self._live_ready.pop(card_id, None)
            self._finish_live_request(target_ids, job_cancel)

        def failure(_exc: Exception) -> None:
            if not self._owns_live_pipeline(
                profile_key, profile_epoch, session_epoch, cancel_event
            ):
                return
            if job_cancel is not None and (
                job_cancel.is_set()
                or any(
                    card_id not in self._live_desired_ids
                    or self._live_job_cancels.get(card_id) is not job_cancel
                    for card_id in target_ids
                )
            ):
                self._finish_live_request(target_ids, job_cancel)
                return
            self._live_failed_ids.update(target_ids)
            self._pause_live_after_failure(tr("provider_error.unknown"))
            self._finish_live_request(target_ids, job_cancel)

        try:
            operation = QueryOp(
                parent=self.mw,
                op=lambda _col: generate_batch(
                    snapshots,
                    settings,
                    1,
                    lambda: cancel_event.is_set()
                    or (job_cancel is not None and job_cancel.is_set()),
                    intensity=rewrite_intensity,
                ),
                success=success,
            )
            operation.failure(failure)
            operation.without_collection().run_in_background()
        except Exception as exc:
            failure(exc)

    def _live_provider_settings(self, profile_key: str) -> ProviderSettings | None:
        consent = self._read_live_consent()
        provider = str(consent.get("provider") or "")
        model = str(consent.get("model") or "").strip()
        secret_store = self.secret_store
        if not provider or not model or secret_store is None:
            return None
        try:
            api_key = secret_store.get(provider, profile_key) or ""
        except Exception:
            return None
        if not api_key:
            return None
        return ProviderSettings(
            provider=provider,
            model=model,
            api_key=api_key,
            timeout_seconds=int(self.config.get("timeout_seconds", 90)),
            max_retries=int(self.config.get("max_retries", 2)),
        )

    def _owns_live_pipeline(
        self,
        profile_key: str,
        profile_epoch: int,
        session_epoch: int,
        cancel_event: threading.Event,
    ) -> bool:
        return bool(
            self._live_session_active
            and self._live_enabled_requested()
            and not cancel_event.is_set()
            and self._live_cancel_event is cancel_event
            and self._profile_epoch == profile_epoch
            and self._profile_key() == profile_key
            and self._live_session_epoch == session_epoch
        )

    def _owns_live_job(
        self,
        card_id: int,
        profile_key: str,
        profile_epoch: int,
        session_epoch: int,
        cancel_event: threading.Event,
        job_cancel: threading.Event,
    ) -> bool:
        return bool(
            self._owns_live_pipeline(
                profile_key, profile_epoch, session_epoch, cancel_event
            )
            and not job_cancel.is_set()
            and card_id in self._live_desired_ids
            and self._live_job_cancels.get(card_id) is job_cancel
        )

    def _finish_live_request(
        self,
        target_ids: list[int],
        job_cancel: threading.Event | None = None,
    ) -> None:
        for card_id in target_ids:
            current_cancel = self._live_job_cancels.get(card_id)
            if job_cancel is not None and current_cancel is not job_cancel:
                continue
            self._live_inflight_ids.discard(card_id)
            self._live_network_ids.discard(card_id)
            if current_cancel is not None:
                self._live_job_cancels.pop(card_id, None)
        if self._live_session_active and not self._live_paused:
            QTimer.singleShot(0, self._refill_live_from_current_question)

    def _refill_live_from_current_question(self) -> None:
        reviewer = getattr(self.mw, "reviewer", None)
        card = getattr(reviewer, "card", None)
        if card is None:
            return
        try:
            card_id = int(card.id)
        except Exception:
            return
        self._live_refill(current_card_id=card_id, after_answer=False)

    # ------------------------------------------------------------------
    # Review rendering

    def on_card_will_show(self, text: str, card: Any, kind: str) -> str:
        """Render only real review sides; previews/layout screens stay native."""

        if kind not in ("reviewQuestion", "reviewAnswer"):
            return text
        profile_key = self._profile_key()
        if not profile_key:
            return text

        if not bool(self.config.get("enabled", True)):
            # If the add-on is switched off while a generated question is
            # already visible, keep that one answer coherent. New questions
            # immediately return to Anki's native rendering.
            if kind != "reviewAnswer":
                return text
            try:
                card_id = int(card.id)
                if card_id not in self._review_choices:
                    return text
                return self._render_review_answer(text, card, card_id, profile_key)
            except Exception:
                return text

        store = self.variant_store
        if store is None:
            return text

        try:
            card_id = int(card.id)
            if kind == "reviewQuestion":
                return self._render_review_question(text, card, card_id, profile_key)
            return self._render_review_answer(text, card, card_id, profile_key)
        except Exception:
            # Reviewing must never be interrupted by add-on storage, another
            # add-on's HTML, or a malformed historical record.
            return text

    def _render_review_question(
        self,
        incoming_html: str,
        card: Any,
        card_id: int,
        profile_key: str,
    ) -> str:
        original_html = _question_html(card, incoming_html)
        original_answer_html = _answer_html(card, "")
        rewrite_intensity = normalize_rewrite_intensity(
            self.config.get("rewrite_intensity")
        )
        current_hash = variant_source_hash(
            original_html, original_answer_html, rewrite_intensity
        )
        live_requested = (
            self._live_enabled_requested() and self._live_configuration_ready()
        )
        # Once a generated question has actually been selected for this card,
        # keep it stable across harmless reviewer redraws and even a mid-card
        # pause. It is removed only after Anki records the answer.
        stored = self._live_in_use.get(card_id)
        if stored is None and live_requested:
            live_ready = self._live_ready.get(card_id)
            if live_ready is not None and live_ready.source_hash == current_hash:
                stored = self._live_ready.pop(card_id)
                self._live_in_use[card_id] = stored
            elif live_ready is not None:
                self._live_ready.pop(card_id, None)
        if stored is None and card_id not in self._prepared_consumed_ids:
            prepared = self._prepared_cache.get((profile_key, card_id))
            if (
                prepared is not None
                and prepared.source_hash == current_hash
                and any(value.strip() for value in prepared.variants if isinstance(value, str))
            ):
                stored = prepared
                self._prepared_cache.pop((profile_key, card_id), None)
                self._prepared_consumed_ids.add(card_id)
                self._live_failed_ids.discard(card_id)
                self._live_in_use[card_id] = prepared
                self._delete_prepared_record(profile_key, card_id, self.variant_store)
            elif prepared is not None:
                self._prepared_cache.pop((profile_key, card_id), None)
                self._delete_prepared_record(profile_key, card_id, self.variant_store)
        if stored is None and not live_requested:
            stored = self._variant_cache.get((profile_key, card_id))
        front_visual_mode = (
            _review_front_visual_mode(stored) if stored is not None else ""
        )
        if (
            stored is None
            or stored.source_hash != current_hash
            or not stored.variants
            or not front_visual_mode
        ):
            self._review_choices.pop(card_id, None)
            return incoming_html

        variants = [value.strip() for value in stored.variants if value.strip()]
        if not variants:
            self._review_choices.pop(card_id, None)
            return incoming_html

        existing = self._review_choices.get(card_id)
        reused_choice = bool(
            existing is not None
            and existing.profile_key == profile_key
            and existing.source_hash == current_hash
            and existing.variant in variants
        )
        if reused_choice:
            variant = existing.variant
            front_original_fragment = existing.front_original_fragment
        else:
            variant = self._next_variant(card_id, variants)
            # Sanitize the exact front supplied by the hook once. This same
            # fragment drives both the embedded context and button
            # availability, so the two webviews cannot disagree.
            front_original_fragment = safe_original_fragment(incoming_html)
        self._remember_review_choice(
            card_id,
            _ReviewChoice(
                profile_key=profile_key,
                source_hash=current_hash,
                variant=variant,
                original_html=original_html,
                front_original_fragment=front_original_fragment,
                rewrite_intensity=rewrite_intensity,
            ),
        )
        if not reused_choice:
            self._session_reframed_count += 1
        # Preserve HTML changes made by earlier filters inside the optional
        # inline original-question context.
        return render_question(
            variant,
            incoming_html,
            original_fragment=front_original_fragment,
            front_card_id=card_id,
        )

    def _next_variant(self, card_id: int, variants: list[str]) -> str:
        fingerprint = tuple(variants)
        cycle = self._variant_cycles.get(card_id)
        if cycle is None or cycle.fingerprint != fingerprint:
            cycle = _VariantCycle(fingerprint=fingerprint, remaining=[])
            self._variant_cycles[card_id] = cycle
        if not cycle.remaining:
            cycle.remaining = list(variants)
            self._rng.shuffle(cycle.remaining)
            if len(cycle.remaining) > 1 and cycle.remaining[-1] == cycle.last:
                cycle.remaining[0], cycle.remaining[-1] = (
                    cycle.remaining[-1],
                    cycle.remaining[0],
                )
        selected = cycle.remaining.pop()
        cycle.last = selected
        return selected

    def on_reviewer_did_answer_card(
        self, _reviewer: Any, card: Any, _ease: Any
    ) -> None:
        try:
            self._hide_original_control(card)
            card_id = int(card.id)
            self._review_choices.pop(card_id, None)
            self._live_in_use.pop(card_id, None)
            self._live_failed_ids.discard(card_id)
            if self._live_session_active and self._live_enabled_requested():
                # The scheduler operation has completed before this hook. This
                # provides the earliest possible head start; the following
                # did_show hook revalidates the window against the card Anki
                # actually displays.
                self._live_refill(current_card_id=card_id, after_answer=True)
        except Exception:
            pass

    def _render_review_answer(
        self,
        answer_html: str,
        card: Any,
        card_id: int,
        profile_key: str,
    ) -> str:
        choice = self._review_choices.get(card_id)
        if choice is None or choice.profile_key != profile_key:
            return answer_html

        current_original = _question_html(card, choice.original_html)
        current_answer = _answer_html(card, answer_html)
        current_hash = variant_source_hash(
            current_original,
            current_answer,
            choice.rewrite_intensity,
        )
        if current_hash != choice.source_hash:
            # The note or template changed between question and answer. Fail
            # closed. The in-memory choice itself is sufficient proof of what
            # was actually shown, even if Live was switched off meanwhile.
            self._review_choices.pop(card_id, None)
            return answer_html

        # Use the exact, already-sanitized hook fragment that was embedded on
        # the front. Anki may munge media URLs (spaces/Unicode -> percent
        # escapes) differently from ``card.question()``; mixing the two forms
        # can duplicate a screenshot or append a path that WebEngine cannot
        # load reliably.
        display_original = choice.front_original_fragment
        original_already_present = bool(display_original.strip()) and (
            _html_contains_original(answer_html, display_original)
        )
        return render_answer_context(
            answer_html,
            choice.variant,
            display_original,
            original_already_present=original_already_present,
            show_original=bool(
                self.config.get("show_original_on_answer", True)
            ),
        )

    def _remember_review_choice(self, card_id: int, choice: _ReviewChoice) -> None:
        # Reinsert an existing card so insertion order reflects the latest
        # review, which keeps the bounded cache eviction predictable.
        self._review_choices.pop(card_id, None)
        self._review_choices[card_id] = choice
        if len(self._review_choices) > _MAX_REVIEW_CHOICES:
            oldest_card_id = next(iter(self._review_choices))
            self._review_choices.pop(oldest_card_id, None)

    # ------------------------------------------------------------------
    # Settings/storage helpers

    def _delete_prepared_record(
        self,
        profile_key: str,
        card_id: int,
        store: VariantStore | None,
    ) -> None:
        """Delete a consumed/stale one-shot without blocking the reviewer."""

        if store is None or not profile_key:
            return
        profile_epoch = self._profile_epoch
        self._variant_cache_revision += 1

        def success(_count: int) -> None:
            if (
                self._profile_epoch == profile_epoch
                and self._profile_key() == profile_key
                and self.variant_store is store
            ):
                self._prepared_cache.pop((profile_key, int(card_id)), None)

        try:
            operation = QueryOp(
                parent=self.mw,
                op=lambda _col: store.delete_prepared_cards(profile_key, [card_id]),
                success=success,
            )
            operation.failure(lambda _exc: None)
            operation.without_collection().run_in_background()
        except Exception:
            pass

    def open_settings(self) -> bool:
        try:
            previous_ui_preference = normalize_ui_language(
                self.config.get("ui_language", "auto")
            )
            previous_live_count = _bounded_int(
                self.config.get("live_prefetch_count"), 3, 1, 10
            )
            previous_rewrite_intensity = normalize_rewrite_intensity(
                self.config.get("rewrite_intensity")
            )
            previous_connection_ready = self._live_configuration_ready()
            consent = self._read_live_consent()
            connection_provider = str(
                consent.get("provider") or self.config.get("provider", "openai")
            )
            connection_model = str(
                consent.get("model") or self.config.get("model", "")
            )
            dialog = SettingsDialog(
                self.mw,
                enabled=bool(self.config.get("enabled", True)),
                show_original_on_answer=bool(
                    self.config.get("show_original_on_answer", True)
                ),
                rewrite_intensity=previous_rewrite_intensity,
                live_prefetch_enabled=(
                    self._live_enabled_requested()
                    and self._live_configuration_ready()
                    and not self._live_paused
                ),
                live_prefetch_count=int(
                    self.config.get("live_prefetch_count", 3)
                ),
                provider=connection_provider,
                model=connection_model,
                connection_ready=self._live_configuration_ready(),
                sent_card_count=_bounded_int(
                    self.config.get("sent_card_count"),
                    0,
                    0,
                    _MAX_SENT_CARD_COUNT,
                ),
                ui_language=previous_ui_preference,
            )
            if not _dialog_was_accepted(dialog):
                return False
            delete_requested = dialog.delete_profile_variants()
            delete_keys_requested = dialog.delete_all_api_keys()
            connection_setup_requested = dialog.connection_setup_requested()
            connection_disconnect_requested = (
                dialog.connection_disconnect_requested()
            )
            if connection_disconnect_requested and not self._disconnect_live_connection(
                connection_provider, parent=self.mw
            ):
                return False
            values = dialog.settings_values()
            values["ui_language"] = normalize_ui_language(
                values.get("ui_language", previous_ui_preference)
            )
            values["rewrite_intensity"] = normalize_rewrite_intensity(
                values.get("rewrite_intensity")
            )
            requested_live = bool(values.get("live_prefetch_enabled", False))
            if connection_disconnect_requested:
                requested_live = False
                values["live_prefetch_enabled"] = False
            if not bool(values.get("enabled", True)):
                requested_live = False
                values["live_prefetch_enabled"] = False
            needs_live_setup = connection_setup_requested or (
                requested_live and not self._live_configuration_ready()
            )
            if needs_live_setup:
                values["live_prefetch_enabled"] = False
            self._update_config(**values, variant_count=1)
            self._ui_language = set_ui_language(
                values["ui_language"], self.mw
            )
            self._retranslate_main_menu()
            if (
                connection_disconnect_requested
                or needs_live_setup
                or not bool(values.get("enabled", True))
                or not requested_live
                or values["rewrite_intensity"] != previous_rewrite_intensity
            ):
                self._cancel_preparation()
            if connection_disconnect_requested:
                self._sync_live_action()
            elif needs_live_setup:
                self._stop_live_session()
                activate_after_setup = requested_live and bool(
                    values.get("enabled", True)
                )
                if not self.setup_live_mode(activate=activate_after_setup):
                    # The setup dialog is transactional: cancelling it keeps
                    # the previous valid connection and live state instead of
                    # silently turning automatic questions off.
                    restore_live = (
                        activate_after_setup and previous_connection_ready
                    )
                    self._update_config(live_prefetch_enabled=restore_live)
                    if restore_live:
                        self._start_live_for_current_reviewer()
                        self._schedule_current_deck_preparation()
                        self._schedule_startup_reserve()
            elif not bool(self.config.get("enabled", True)):
                self._variant_cycles.clear()
                self._stop_live_session()
            elif not requested_live:
                self._stop_live_session()
            else:
                if (
                    int(values.get("live_prefetch_count", 3)) != previous_live_count
                    or values["rewrite_intensity"] != previous_rewrite_intensity
                ):
                    self._stop_live_session()
                self._start_live_for_current_reviewer()
                self._schedule_current_deck_preparation()
                self._schedule_startup_reserve()
            self._sync_live_action()
            if delete_requested:
                self._delete_current_profile_variants()
            if delete_keys_requested:
                self._delete_all_api_keys()
        except Exception as exc:
            self._show_error(tr("error.settings_open"), exc, self.mw)
            return False
        return True

    def _disconnect_live_connection(
        self, provider: str, *, parent: Any
    ) -> bool:
        if not askUser(
            tr("confirm.disconnect"),
            parent=parent,
        ):
            return False
        self._update_config(live_prefetch_enabled=False)
        self._stop_live_session()
        self._cancel_preparation()
        revocation_saved = self._mark_live_consent_revoked()
        consent_removed = self._clear_live_consent()
        secret_store = self.secret_store
        profile_key = self._profile_key()
        if secret_store is not None and profile_key and provider:
            try:
                secret_store.delete(provider, profile_key)
            except Exception as exc:
                showWarning(
                    tr("warning.key_delete_failed", detail=_safe_message(exc)),
                    parent=parent,
                )
        self._sync_live_action()
        if consent_removed:
            tooltip(tr("notice.disconnected"), parent=parent)
            return True
        if revocation_saved:
            showWarning(
                tr("warning.consent_file_remove_failed"),
                parent=parent,
            )
            return True
        showWarning(
            tr("warning.revocation_persist_failed"),
            parent=parent,
        )
        return False

    def _delete_current_profile_variants(self) -> None:
        store = self.variant_store
        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        if store is None or not profile_key:
            return

        if not askUser(
            tr("confirm.delete_profile_variants"),
            parent=self.mw,
        ):
            return

        def success(count: int) -> None:
            if (
                self._profile_epoch != profile_epoch
                or self.variant_store is not store
            ):
                return
            self._clear_runtime_cache()
            tooltip(tr("notice.deleted_profile", count=count), parent=self.mw)

        def failure(exc: Exception) -> None:
            if (
                self._profile_epoch == profile_epoch
                and self.variant_store is store
            ):
                self._show_error(
                    tr("error.delete_local_variants"), exc, self.mw
                )

        operation = QueryOp(
            parent=self.mw,
            op=lambda _col: store.delete_profile(profile_key),
            success=success,
        )
        operation.failure(failure)
        operation.without_collection().run_in_background()

    def _delete_all_api_keys(self) -> None:
        secret_store = self.secret_store
        if secret_store is None:
            return
        if not askUser(
            tr("confirm.delete_api_keys"),
            parent=self.mw,
        ):
            return
        try:
            secret_store.clear_all()
            if not self._live_configuration_ready():
                self._stop_live_session()
                self._cancel_preparation()
            self._sync_live_action()
            tooltip(tr("notice.deleted_api_keys"), parent=self.mw)
        except Exception as exc:
            self._show_error(tr("error.delete_api_keys"), exc, self.mw)

    def on_profile_did_open(self) -> None:
        self._profile_epoch += 1
        self._cancel_front_screenshots()
        self._ui_language = set_ui_language(
            self.config.get("ui_language", "auto"), self.mw
        )
        self._retranslate_main_menu()
        self._stop_live_session()
        self._cancel_preparation()
        self._sync_in_progress = False
        self._clear_runtime_cache()
        self._storage_error = None
        try:
            data_directory = self._profile_data_directory()
            self.secret_store = SecretStore(data_directory / "secrets.json")
            self.variant_store = VariantStore(data_directory / "variants.sqlite3")
        except Exception as exc:
            self.secret_store = None
            self.variant_store = None
            self._storage_error = exc
            self._sync_live_action()
            return
        self._sync_live_action()
        store = self.variant_store
        profile_key = self._profile_key()
        profile_epoch = self._profile_epoch
        if store is None or not profile_key:
            return

        # Start network preparation independently of the cache read.  A slow or
        # damaged cache must never cost the first card its head start.
        if self._live_enabled_requested() and self._live_configuration_ready():
            self._schedule_current_deck_preparation()
            self._schedule_startup_reserve()

        def start_cache_load(expected_revision: int) -> None:
            def load(_col: Any) -> tuple[list[Any], list[Any]]:
                # Loading is deliberately read-only. Automatic deletion on a
                # transient collection error could destroy valid local variants;
                # users can purge the profile explicitly in Settings.
                return (
                    store.list_for_profile(profile_key),
                    store.list_prepared_for_profile(profile_key),
                )

            def success(payload: tuple[list[Any], list[Any]]) -> None:
                if (
                    self._profile_epoch != profile_epoch
                    or self._profile_key() != profile_key
                    or self.variant_store is not store
                ):
                    return
                if self._variant_cache_revision != expected_revision:
                    # A save/delete completed while SQLite was being read.
                    # Query the authoritative store again instead of erasing a
                    # newer cache entry or a live card's review choice.
                    try:
                        start_cache_load(self._variant_cache_revision)
                    except Exception:
                        pass
                    return
                items, prepared_items = payload
                self._variant_cache.update(
                    {(profile_key, int(item.card_id)): item for item in items}
                )
                self._prepared_cache.update(
                    {
                        (profile_key, int(item.card_id)): item
                        for item in prepared_items
                        if int(item.card_id) not in self._prepared_consumed_ids
                    }
                )

            operation = QueryOp(parent=self.mw, op=load, success=success)
            operation.failure(lambda _exc: None)
            # The add-on cache is independent of Anki's collection.  Keeping
            # this read outside the collection queue lets the priority
            # first-card lookup start immediately.
            operation.without_collection().run_in_background()

        try:
            start_cache_load(self._variant_cache_revision)
        except Exception:
            # Prepared rows remain discoverable by the per-card warm-up.  Cache
            # hydration is an optimization and must not disable Variator.
            pass

    def on_profile_will_close(self) -> None:
        self._profile_epoch += 1
        self._cancel_front_screenshots()
        self._stop_live_session()
        self._cancel_preparation()
        self._generation_in_progress = False
        if self._generation_cancel_event is not None:
            self._generation_cancel_event.set()
            self._finish_owned_generation_progress(self._generation_cancel_event)
        if self.secret_store is not None:
            self.secret_store.clear_session(self._profile_key())
        self._clear_runtime_cache()
        self.secret_store = None
        self.variant_store = None
        self._sync_live_action()

    def _finish_owned_generation_progress(
        self, owner: threading.Event
    ) -> None:
        if self._generation_progress_owner is not owner:
            return
        cleanup = self._generation_progress_cleanup
        self._generation_progress_owner = None
        self._generation_progress_cleanup = None
        if cleanup is not None:
            cleanup()

    def _clear_runtime_cache(self) -> None:
        self._review_choices.clear()
        self._variant_cycles.clear()
        self._variant_cache.clear()
        self._prepared_cache.clear()
        self._prepared_consumed_ids.clear()
        self._session_failed_generation_keys.clear()
        self._variant_cache_revision += 1

    def _load_config(self) -> dict[str, Any]:
        config = dict(DEFAULT_CONFIG)
        try:
            loaded = self.mw.addonManager.getConfig(self.package)
            if isinstance(loaded, dict):
                config.update(loaded)
        except Exception:
            pass
        config["enabled"] = _as_bool(config.get("enabled"), True)
        config["ui_language"] = normalize_ui_language(
            config.get("ui_language", "auto")
        )
        config["show_original_on_answer"] = _as_bool(
            config.get("show_original_on_answer"), True
        )
        config["variant_count"] = 1
        config["sent_card_count"] = _bounded_int(
            config.get("sent_card_count"), 0, 0, _MAX_SENT_CARD_COUNT
        )
        config["rewrite_intensity"] = normalize_rewrite_intensity(
            config.get("rewrite_intensity")
        )
        config["live_prefetch_enabled"] = _as_bool(
            config.get("live_prefetch_enabled"), False
        )
        config["live_prefetch_count"] = _bounded_int(
            config.get("live_prefetch_count"), 3, 1, 10
        )
        revoked_scopes = config.get("live_consent_revoked_profiles", [])
        if not isinstance(revoked_scopes, list):
            revoked_scopes = []
        config["live_consent_revoked_profiles"] = sorted(
            {
                item
                for item in revoked_scopes
                if isinstance(item, str) and len(item) == 64
            }
        )[:128]
        config["offline_prepare_count"] = _bounded_int(
            config.get("offline_prepare_count"), 20, 1, _MAX_OFFLINE_CARDS
        )
        config.pop("onboarding_seen", None)
        config["timeout_seconds"] = _bounded_int(
            config.get("timeout_seconds"), 90, 5, 3600
        )
        config["max_retries"] = _bounded_int(
            config.get("max_retries"), 2, 0, 5
        )
        return config

    def _update_config(self, **values: Any) -> bool:
        updated = dict(self.config)
        updated.update(values)
        self.config = updated
        try:
            self.mw.addonManager.writeConfig(self.package, updated)
            return True
        except Exception as exc:
            showWarning(
                tr("warning.settings_not_saved", detail=_safe_message(exc)),
                parent=self.mw,
            )
            return False

    def _profile_data_directory(self) -> Path:
        try:
            profile_folder = Path(self.mw.pm.profileFolder())
        except Exception as exc:
            raise RuntimeError(tr("error.profile_folder")) from exc
        path = profile_folder / "fragevariator"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _storage_available(self, parent: Any) -> bool:
        if self.variant_store is not None:
            return True
        detail = (
            _safe_message(self._storage_error)
            if self._storage_error
            else tr("storage.unknown_error")
        )
        showWarning(
            tr("storage.unavailable", detail=detail),
            parent=parent,
        )
        return False

    def _profile_key(self) -> str:
        # The database itself lives inside one profile folder, so it never
        # needs to persist the human-readable profile name.
        return "profile" if self.variant_store is not None else ""

    @staticmethod
    def _show_error(
        title: str, exc: BaseException, parent: Any | None = None
    ) -> None:
        clean_title = str(title).strip()
        suffix = "" if clean_title.endswith((".", "!", "?", "…", ":")) else "."
        showWarning(
            "%s%s\n\n%s" % (clean_title, suffix, _safe_message(exc)),
            parent=parent,
        )


def _dialog_was_accepted(dialog: QDialog) -> bool:
    dialog_code = getattr(QDialog, "DialogCode", None)
    accepted = getattr(dialog_code, "Accepted", getattr(QDialog, "Accepted", 1))
    return dialog.exec() == accepted


def _set_qt_text(
    target: Any,
    setter_name: str,
    fallback_attribute: str,
    value: str,
) -> None:
    """Set text on a Qt object and on the small doubles used in tests."""

    setter = getattr(target, setter_name, None)
    if callable(setter):
        setter(value)
    elif hasattr(target, fallback_attribute):
        setattr(target, fallback_attribute, value)


def _question_html(card: Any, fallback: str) -> str:
    try:
        return str(card.question() or "")
    except Exception:
        return fallback


def _answer_html(card: Any, fallback: str) -> str:
    try:
        return str(card.answer() or "")
    except Exception:
        return fallback


def _html_contains_original(answer_html: str, original_html: str) -> bool:
    original_fragment = safe_initially_visible_fragment(original_html).strip()
    answer_fragment = safe_initially_visible_fragment(answer_html)
    # Compare only the passive, visibility-aware fragments.  Raw card HTML
    # can still contain FrontSide text that the note template hides with CSS;
    # treating that as visible would suppress the original-question context
    # after the answer is shown.
    if not original_fragment:
        return False
    start = answer_fragment.find(original_fragment)
    while start >= 0:
        end = start + len(original_fragment)
        # Markup must match structurally. Plain text counts only at an HTML
        # node boundary, so "A" cannot match an unrelated "ANSWER" and two
        # image-only cards cannot match via the generic [image] text token.
        if (
            "<" in original_fragment
            or (
                (start == 0 or answer_fragment[start - 1] == ">")
                and (end == len(answer_fragment) or answer_fragment[end] == "<")
            )
        ):
            return True
        start = answer_fragment.find(original_fragment, start + 1)
    original_text = " ".join(html_to_text(original_fragment).split())
    meaningful_text = original_text.replace("[image]", "").replace(
        "[audio]", ""
    ).strip()
    if len(meaningful_text) >= 4:
        answer_text = " ".join(html_to_text(answer_fragment).split())
        if answer_text.startswith(original_text):
            return True
    return False


def _secret_source_kind(
    secret_store: Any,
    provider: str,
    profile_key: str,
    has_key: bool,
) -> str:
    """Return a stable source code across real and legacy/test secret stores."""

    source_method = getattr(secret_store, "source_kind", None)
    if callable(source_method):
        value = str(source_method(provider, profile_key))
        if value in {"environment", "session", "device", "missing"}:
            return value
    persisted_method = getattr(secret_store, "is_persisted", None)
    if callable(persisted_method) and persisted_method(provider, profile_key):
        return "device"
    return "session" if has_key else "missing"


def _dialog_api_key_source(dialog: Any, fallback: str) -> str:
    source_method = getattr(dialog, "api_key_source", None)
    if callable(source_method):
        value = str(source_method())
        if value in {"environment", "session", "device"}:
            return value
    return fallback


def _store_setup_api_key(
    secret_store: Any,
    provider: str,
    profile_key: str,
    api_key: str,
    *,
    persist: bool,
    source: str,
) -> BaseException | None:
    """Keep a new session key active even if removing the old key fails."""

    if source == "environment":
        return None
    if persist:
        secret_store.set(
            provider,
            api_key,
            persist=True,
            scope=profile_key,
        )
        return None

    removal_error: BaseException | None = None
    try:
        secret_store.delete(provider, profile_key)
    except Exception as exc:
        removal_error = exc
    secret_store.set(
        provider,
        api_key,
        persist=False,
        scope=profile_key,
    )
    return removal_error


def _safe_message(exc: BaseException | None, secret: str = "") -> str:
    if exc is None:
        return tr("storage.unknown_error")
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    if secret:
        message = message.replace(secret, tr("error.secret_redacted"))
    return message[:1000]


def _as_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        converted = int(value)
    except (TypeError, ValueError):
        converted = default
    return max(minimum, min(maximum, converted))


_controller: FrageVariatorController | None = None


def register() -> None:
    """Install Variator once; called by the package ``__init__``."""

    global _controller
    if _controller is not None:
        return
    if mw is None:
        return
    controller = FrageVariatorController(mw)
    controller.install()
    _controller = controller


__all__ = ["DEFAULT_CONFIG", "FrageVariatorController", "register"]
