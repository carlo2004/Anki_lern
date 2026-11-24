"""Small, controller-agnostic Qt dialogs used by the add-on.

All Qt classes are imported through :mod:`aqt.qt`, as required by Anki.  The
dialogs deliberately return plain values/model instances so the controller can
decide how and where to persist them.
"""

from __future__ import annotations

from dataclasses import replace
from html import escape
import os
from typing import Any

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    Qt,
    QVBoxLayout,
    QWidget,
)

from ..core.models import BatchGenerationResult, GeneratedVariants
from ..core.secrets import ENVIRONMENT_KEYS, persistent_storage_is_protected
from ..i18n import language_options, normalize_ui_language, tr


_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("OpenAI", "openai"),
    ("Google Gemini", "gemini"),
    ("Anthropic Claude", "anthropic"),
    ("xAI Grok", "xai"),
)

_DEFAULT_MODELS: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.2-sol"),
    "gemini": (
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-4-hydrogen",
        "gemini-3.6-flash",
    ),
    "anthropic": ("claude-haiku-5-5", "claude-sonnet-5-5"),
    "xai": ("grok-4.7", "grok-4.5"),
}

_PROVIDER_KEY_URLS: dict[str, tuple[str, str]] = {
    "openai": ("OpenAI", "https://platform.openai.com/api-keys"),
    "gemini": ("Google AI Studio", "https://aistudio.google.com/app/apikey"),
    "anthropic": ("Claude Platform", "https://platform.claude.com/settings/keys"),
    "xai": ("xAI Console", "https://console.x.ai/"),
}

_REWRITE_INTENSITIES: tuple[tuple[str, str], ...] = (
    ("intensity.near", "near"),
    ("intensity.light", "light"),
    ("intensity.distinct", "distinct"),
    ("intensity.maximum", "maximum"),
)


class GenerationSetupDialog(QDialog):
    """Collect provider credentials and generation parameters.

    API keys remain in this dialog unless the controller explicitly persists
    them after :meth:`store_api_key_plaintext` returns ``True``.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        card_count: int = 0,
        max_retries: int = 2,
        provider: str = "openai",
        model: str = "",
        variant_count: int = 1,
        api_key: str = "",
        store_api_key_plaintext: bool = False,
        api_key_source: str = "",
        live_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._initial_provider = provider
        self._provider_signal_ready = False
        self._live_mode = bool(live_mode)
        self._environment_key_active = str(api_key_source) == "environment"
        self.setWindowTitle(
            tr("setup.title.live") if self._live_mode else tr("setup.title.batch")
        )
        self.setMinimumWidth(720 if self._live_mode else 620)

        layout = QVBoxLayout(self)

        intro_text = tr(
            "setup.intro.live" if self._live_mode else "setup.intro.batch"
        )
        intro = QLabel(intro_text)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        layout.addLayout(form)

        self.provider_combo = QComboBox(self)
        self.provider_combo.setObjectName("providerCombo")
        for label, value in _PROVIDERS:
            self.provider_combo.addItem(label, value)
        provider_index = self.provider_combo.findData(provider)
        self.provider_combo.setCurrentIndex(provider_index if provider_index >= 0 else 0)
        if provider_index < 0:
            # Never carry a credential from an unknown/corrupt provider value
            # into the first supported provider shown in the dialog.
            self._initial_provider = self.provider()
            api_key = ""
            store_api_key_plaintext = False
            self._environment_key_active = False
        form.addRow(tr("common.provider"), self.provider_combo)

        # Keep the former widget as a hidden compatibility attribute.  The
        # live workflow deliberately asks for exactly one wording per card.
        self.variant_count_spin = QSpinBox(self)
        self.variant_count_spin.setObjectName("variantCountSpin")
        self.variant_count_spin.setRange(1, 1)
        self.variant_count_spin.setValue(1)
        self.variant_count_spin.setSuffix(" variant")
        self.variant_count_spin.setVisible(False)

        key_row = QWidget(self)
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        self.api_key_edit = QLineEdit(key_row)
        self.api_key_edit.setObjectName("apiKeyEdit")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setText(api_key)
        self.api_key_edit.setPlaceholderText(tr("setup.api_key_placeholder"))
        key_layout.addWidget(self.api_key_edit, 1)

        self.show_key_checkbox = QCheckBox(tr("common.show"), key_row)
        self.show_key_checkbox.setObjectName("showApiKeyCheckbox")
        self.show_key_checkbox.toggled.connect(self._set_key_visible)
        key_layout.addWidget(self.show_key_checkbox)
        form.addRow(tr("common.api_key"), key_row)

        self.api_key_link = QLabel(self)
        self.api_key_link.setObjectName("providerApiKeyLink")
        self.api_key_link.setOpenExternalLinks(True)
        self.api_key_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        form.addRow("", self.api_key_link)

        self.store_key_checkbox = QCheckBox(tr("setup.remember"), self)
        self.store_key_checkbox.setObjectName("storeApiKeyPlaintextCheckbox")
        self.store_key_checkbox.setChecked(store_api_key_plaintext)
        self.store_key_checkbox.toggled.connect(self._update_remember_key_state)
        layout.addWidget(self.store_key_checkbox)
        self._set_environment_key_state(self._environment_key_active)

        self.advanced_toggle_button = QPushButton(tr("setup.advanced.show"), self)
        self.advanced_toggle_button.setObjectName("advancedDetailsToggle")
        self.advanced_toggle_button.setCheckable(True)
        self.advanced_toggle_button.setChecked(False)
        self.advanced_toggle_button.toggled.connect(
            self._set_advanced_details_visible
        )
        layout.addWidget(self.advanced_toggle_button)

        self.advanced_details_widget = QWidget(self)
        self.advanced_details_widget.setObjectName("advancedDetails")
        advanced_form = QFormLayout(self.advanced_details_widget)
        advanced_form.setContentsMargins(12, 0, 0, 0)

        self.model_combo = QComboBox(self.advanced_details_widget)
        self.model_combo.setObjectName("modelCombo")
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        advanced_form.addRow(tr("common.model"), self.model_combo)
        self.advanced_details_widget.setVisible(False)
        layout.addWidget(self.advanced_details_widget)

        self.cost_notice = QLabel(self)
        self.cost_notice.setObjectName("liveCostNotice")
        self.cost_notice.setWordWrap(True)
        self.cost_notice.setTextFormat(Qt.TextFormat.PlainText)
        if self._live_mode:
            cost_text = tr("setup.cost.live")
        elif card_count > 0:
            cost_text = tr("setup.cost.batch_count", count=card_count)
        else:
            cost_text = tr("setup.cost.batch")
        self.cost_notice.setText(cost_text)
        self.cost_notice.setVisible(True)
        layout.addWidget(self.cost_notice)

        self.privacy_toggle_button = QPushButton(tr("setup.privacy.show"), self)
        self.privacy_toggle_button.setObjectName("privacyDetailsToggle")
        self.privacy_toggle_button.setCheckable(True)
        self.privacy_toggle_button.setChecked(False)
        self.privacy_toggle_button.toggled.connect(
            self._set_privacy_details_visible
        )
        layout.addWidget(self.privacy_toggle_button)

        self.privacy_details_widget = QWidget(self)
        self.privacy_details_widget.setObjectName("privacyDetails")
        privacy_layout = QVBoxLayout(self.privacy_details_widget)
        privacy_layout.setContentsMargins(12, 0, 0, 0)

        self.storage_privacy_notice = QLabel(self)
        self.storage_privacy_notice.setObjectName("plaintextStorageWarning")
        self.storage_privacy_notice.setWordWrap(True)
        privacy_layout.addWidget(self.storage_privacy_notice)
        self._update_storage_privacy_notice()

        request_text = tr(
            "setup.privacy.live" if self._live_mode else "setup.privacy.batch"
        )
        if card_count > 0 and not self._live_mode:
            request_text += " " + tr(
                "setup.privacy.retries",
                attempts=card_count * (max(0, int(max_retries)) + 1),
            )
        transfer_notice = QLabel(request_text, self)
        transfer_notice.setObjectName("contentTransferNotice")
        transfer_notice.setWordWrap(True)
        privacy_layout.addWidget(transfer_notice)
        self.privacy_details_widget.setVisible(False)
        layout.addWidget(self.privacy_details_widget)

        self.content_transfer_checkbox = QCheckBox(
            self._content_transfer_consent_text(), self
        )
        self.content_transfer_checkbox.setObjectName("contentTransferConsentCheckbox")
        self.content_transfer_checkbox.setChecked(False)
        layout.addWidget(self.content_transfer_checkbox)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText(
                tr("common.activate") if self._live_mode else tr("common.continue")
            )
        cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if cancel_button is not None:
            cancel_button.setText(tr("common.cancel"))
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self._populate_models(preferred=model)
        self._update_api_key_link()
        self._provider_signal_ready = True

    def _set_key_visible(self, visible: bool) -> None:
        self.api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )

    def _update_remember_key_state(self, remembered: bool) -> None:
        if self._environment_key_active:
            detail = tr(
                "setup.remember.environment",
                variable=ENVIRONMENT_KEYS.get(self.provider(), "API key"),
            )
        else:
            detail = tr(
                "setup.remember.device" if remembered else "setup.remember.session"
            )
        self.store_key_checkbox.setToolTip(detail)
        self.store_key_checkbox.setAccessibleDescription(detail)

    def _set_environment_key_state(self, active: bool) -> None:
        self._environment_key_active = bool(active)
        if active:
            self.store_key_checkbox.setText(
                tr(
                    "setup.remember.environment",
                    variable=ENVIRONMENT_KEYS.get(self.provider(), "API key"),
                )
            )
        else:
            self.store_key_checkbox.setText(tr("setup.remember"))
        self.api_key_edit.setEnabled(not active)
        self.show_key_checkbox.setEnabled(not active)
        self.store_key_checkbox.setEnabled(not active)
        if active:
            self.show_key_checkbox.setChecked(False)
            self.store_key_checkbox.setChecked(False)
        self._update_remember_key_state(self.store_key_checkbox.isChecked())
        self._update_storage_privacy_notice()

    def _update_storage_privacy_notice(self) -> None:
        notice = getattr(self, "storage_privacy_notice", None)
        if notice is None:
            return
        if self._environment_key_active:
            text = tr(
                "setup.privacy.storage_environment",
                variable=ENVIRONMENT_KEYS.get(self.provider(), "API key"),
            )
        else:
            text = tr(
                "setup.privacy.storage_protected"
                if persistent_storage_is_protected()
                else "setup.privacy.storage"
            )
        notice.setText(text)

    def _set_advanced_details_visible(self, visible: bool) -> None:
        self.advanced_details_widget.setVisible(visible)
        self.advanced_toggle_button.setText(
            tr("setup.advanced.hide" if visible else "setup.advanced.show")
        )

    def _set_privacy_details_visible(self, visible: bool) -> None:
        self.privacy_details_widget.setVisible(visible)
        self.privacy_toggle_button.setText(
            tr("setup.privacy.hide" if visible else "setup.privacy.show")
        )

    def _provider_changed(self, _index: int) -> None:
        self._populate_models()
        self._update_api_key_link()
        self.content_transfer_checkbox.setText(
            self._content_transfer_consent_text()
        )
        if self._provider_signal_ready and self.provider() != self._initial_provider:
            # A credential for one company must never be forwarded to another.
            variable = ENVIRONMENT_KEYS.get(self.provider(), "")
            environment_key = os.environ.get(variable, "").strip() if variable else ""
            self.api_key_edit.setText(environment_key)
            self._set_environment_key_state(bool(environment_key))
            self.store_key_checkbox.setChecked(False)
            # Consent names the selected company and must be renewed after a
            # company change, even when the user had checked it beforehand.
            self.content_transfer_checkbox.setChecked(False)
            self._initial_provider = self.provider()

    def _update_api_key_link(self) -> None:
        provider_label, url = _PROVIDER_KEY_URLS.get(
            self.provider(), ("Provider", "")
        )
        if not url:
            self.api_key_link.clear()
            self.api_key_link.setVisible(False)
            return
        self.api_key_link.setText(
            '<a href="%s">%s</a>'
            % (
                escape(url, quote=True),
                tr("setup.key_link", provider=escape(provider_label)),
            )
        )
        self.api_key_link.setVisible(True)

    def _content_transfer_consent_text(self) -> str:
        provider_name = self.provider_combo.currentText().strip() or "AI provider"
        return tr("setup.consent", provider=provider_name)

    def _populate_models(self, preferred: str = "") -> None:
        models = _DEFAULT_MODELS.get(self.provider(), ())
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(list(models))
        if preferred:
            existing_index = self.model_combo.findText(preferred)
            if existing_index >= 0:
                self.model_combo.setCurrentIndex(existing_index)
            else:
                self.model_combo.setEditText(preferred)
        elif models:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)

    def _validate_and_accept(self) -> None:
        if not self.model():
            QMessageBox.warning(
                self,
                tr("setup.validation.model_title"),
                tr("setup.validation.model"),
            )
            self.model_combo.setFocus()
            return
        if not self.api_key():
            QMessageBox.warning(
                self,
                tr("setup.validation.key_title"),
                tr("setup.validation.key"),
            )
            self.api_key_edit.setFocus()
            return
        if not self.content_transfer_checkbox.isChecked():
            QMessageBox.warning(
                self,
                tr("setup.validation.consent_title"),
                tr(
                    "setup.validation.consent",
                    provider=self.provider_combo.currentText().strip()
                    or "AI provider",
                ),
            )
            self.content_transfer_checkbox.setFocus()
            return
        self.accept()

    def provider(self) -> str:
        """Return the controller-facing provider identifier."""

        value = self.provider_combo.currentData()
        return str(value) if value is not None else ""

    def model(self) -> str:
        return self.model_combo.currentText().strip()

    def variant_count(self) -> int:
        """Return the fixed number of variants generated for each card."""

        return 1

    def api_key(self) -> str:
        return self.api_key_edit.text().strip()

    def api_key_source(self) -> str:
        if self._environment_key_active:
            return "environment"
        return "device" if self.store_key_checkbox.isChecked() else "session"

    def store_api_key_plaintext(self) -> bool:
        return self.store_key_checkbox.isChecked()

    # Friendly aliases for controllers that use the wording from settings UIs.
    def remember_api_key(self) -> bool:
        return self.store_api_key_plaintext()

    def setup_values(self) -> dict[str, Any]:
        return {
            "provider": self.provider(),
            "model": self.model(),
            "variant_count": self.variant_count(),
            "api_key": self.api_key(),
            "store_api_key_plaintext": self.store_api_key_plaintext(),
            "content_transfer_confirmed": self.content_transfer_checkbox.isChecked(),
        }


class OfflinePreparationDialog(QDialog):
    """Choose a deck and how many upcoming cards to prepare for offline study."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        decks: list[Any] | tuple[Any, ...],
        default_deck_id: int | str | None = None,
        default_count: int = 20,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("offlinePreparationDialog")
        self.setWindowTitle(tr("offline.title"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        summary = QLabel(tr("offline.summary"), self)
        summary.setObjectName("offlinePreparationSummary")
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(summary)

        form = QFormLayout()
        layout.addLayout(form)

        self.deck_combo = QComboBox(self)
        self.deck_combo.setObjectName("offlineDeckCombo")
        self.deck_combo.setAccessibleName(tr("offline.deck_accessible"))
        self.deck_combo.setAccessibleDescription(tr("offline.deck_description"))
        normalised_decks = self._normalise_decks(decks)
        for deck_id, name in normalised_decks:
            self.deck_combo.addItem(name, deck_id)

        if normalised_decks:
            try:
                preferred_id = int(default_deck_id)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                preferred_id = None
            preferred_index = self.deck_combo.findData(preferred_id)
            self.deck_combo.setCurrentIndex(
                preferred_index if preferred_index >= 0 else 0
            )
        else:
            self.deck_combo.addItem(tr("offline.no_decks"), None)
            self.deck_combo.setEnabled(False)

        deck_label = QLabel(tr("offline.deck_label"), self)
        deck_label.setBuddy(self.deck_combo)
        form.addRow(deck_label, self.deck_combo)

        self.card_count_spin = QSpinBox(self)
        self.card_count_spin.setObjectName("offlineCardCountSpin")
        self.card_count_spin.setRange(1, 50)
        try:
            count = int(default_count)
        except (TypeError, ValueError):
            count = 20
        self.card_count_spin.setValue(max(1, min(50, count)))
        self.card_count_spin.setSuffix(tr("common.cards_suffix"))
        self.card_count_spin.setAccessibleName(tr("offline.count_accessible"))
        self.card_count_spin.setAccessibleDescription(
            tr("offline.count_description")
        )
        count_label = QLabel(tr("offline.count_label"), self)
        count_label.setBuddy(self.card_count_spin)
        form.addRow(count_label, self.card_count_spin)

        cost_notice = QLabel(tr("offline.cost"), self)
        cost_notice.setObjectName("offlineCostNotice")
        cost_notice.setWordWrap(True)
        cost_notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(cost_notice)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.prepare_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Ok
        )
        if self.prepare_button is not None:
            self.prepare_button.setObjectName("offlinePrepareButton")
            self.prepare_button.setText(tr("offline.prepare"))
            self.prepare_button.setAccessibleName(tr("offline.prepare_accessible"))
            self.prepare_button.setEnabled(bool(normalised_decks))
            self.prepare_button.setDefault(True)
            self.prepare_button.setAutoDefault(True)
        self.cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if self.cancel_button is not None:
            self.cancel_button.setObjectName("offlineCancelButton")
            self.cancel_button.setText(tr("common.cancel"))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        if normalised_decks:
            self.deck_combo.setFocus()
        else:
            self.card_count_spin.setFocus()

    @staticmethod
    def _normalise_decks(decks: Any) -> list[tuple[int, str]]:
        """Return unique, valid ``(deck_id, name)`` pairs in input order."""

        if not isinstance(decks, (list, tuple)):
            return []

        result: list[tuple[int, str]] = []
        seen_ids: set[int] = set()
        for entry in decks:
            if isinstance(entry, dict):
                raw_id = entry.get("deck_id", entry.get("id"))
                raw_name = entry.get("name")
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                raw_id, raw_name = entry[0], entry[1]
            else:
                raw_id = getattr(entry, "deck_id", getattr(entry, "id", None))
                raw_name = getattr(entry, "name", None)

            try:
                deck_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            name = str(raw_name).strip() if raw_name is not None else ""
            if deck_id <= 0 or not name or deck_id in seen_ids:
                continue
            seen_ids.add(deck_id)
            result.append((deck_id, name))
        return result

    def deck_id(self) -> int | None:
        """Return the stable Anki deck identifier selected by the user."""

        value = self.deck_combo.currentData()
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def card_count(self) -> int:
        """Return the number of upcoming cards to prepare."""

        return self.card_count_spin.value()


class ReviewResultsDialog(QDialog):
    """Review, edit and select generated question variants."""

    def __init__(
        self,
        result: BatchGenerationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.result = result
        self._variant_rows: list[
            tuple[GeneratedVariants, list[tuple[QCheckBox, QPlainTextEdit]]]
        ] = []

        self.setWindowTitle(tr("review.title"))
        self.resize(860, 680)

        root = QVBoxLayout(self)
        generated_count = len(result.generated)
        failure_count = len(result.failures)
        summary_text = tr(
            "review.summary",
            generated=generated_count,
            failed=failure_count,
        )
        if result.cancelled:
            summary_text = tr("review.cancelled") + summary_text
        summary = QLabel(summary_text, self)
        summary.setWordWrap(True)
        root.addWidget(summary)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        select_all = QPushButton(tr("review.select_all"), self)
        select_all.clicked.connect(lambda: self._set_all_variants_checked(True))
        toolbar.addWidget(select_all)
        select_none = QPushButton(tr("review.select_none"), self)
        select_none.clicked.connect(lambda: self._set_all_variants_checked(False))
        toolbar.addWidget(select_none)
        root.addLayout(toolbar)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)

        for generated in result.generated:
            group = self._build_generated_group(generated, content)
            content_layout.addWidget(group)

        if result.failures:
            failure_group = QGroupBox(tr("review.failures"), content)
            failure_layout = QVBoxLayout(failure_group)
            for failure in result.failures:
                failure_label = QLabel(
                    tr(
                        "review.failure",
                        card_id=failure.card_id,
                        reason=failure.reason,
                    ),
                    failure_group,
                )
                # Provider messages are data, never UI markup.
                failure_label.setTextFormat(Qt.TextFormat.PlainText)
                failure_label.setWordWrap(True)
                failure_layout.addWidget(failure_label)
            content_layout.addWidget(failure_group)

        if not result.generated and not result.failures:
            empty = QLabel(tr("review.empty"), content)
            empty.setWordWrap(True)
            content_layout.addWidget(empty)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText(tr("review.apply"))
            save_button.setEnabled(bool(result.generated))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if cancel_button is not None:
            cancel_button.setText(tr("common.cancel"))
        root.addWidget(self.button_box)

    def _build_generated_group(
        self, generated: GeneratedVariants, parent: QWidget
    ) -> QGroupBox:
        group = QGroupBox(tr("review.card", card_id=generated.card_id), parent)
        layout = QVBoxLayout(group)

        original_title = QLabel(tr("review.original_question"), group)
        layout.addWidget(original_title)
        original = QPlainTextEdit(group)
        original.setObjectName(f"originalQuestion_{generated.card_id}")
        original.setReadOnly(True)
        original.setPlainText(generated.original_question)
        original.setMaximumHeight(82)
        original.setToolTip(escape(generated.original_question))
        layout.addWidget(original)

        aspect_title = QLabel(tr("review.core_aspect"), group)
        layout.addWidget(aspect_title)
        aspect = QPlainTextEdit(group)
        aspect.setObjectName(f"coreAspect_{generated.card_id}")
        aspect.setReadOnly(True)
        aspect.setPlainText(generated.core_aspect)
        aspect.setMaximumHeight(64)
        aspect.setToolTip(escape(generated.core_aspect))
        layout.addWidget(aspect)

        if generated.warnings:
            layout.addWidget(QLabel(tr("review.warnings"), group))
            warnings = QLabel(" · ".join(generated.warnings), group)
            warnings.setTextFormat(Qt.TextFormat.PlainText)
            warnings.setWordWrap(True)
            layout.addWidget(warnings)

        variants_title = QLabel(tr("review.variants"), group)
        layout.addWidget(variants_title)
        rows: list[tuple[QCheckBox, QPlainTextEdit]] = []
        for index, variant in enumerate(generated.variants, start=1):
            row_widget = QWidget(group)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            checkbox = QCheckBox(str(index), row_widget)
            checkbox.setObjectName(
                f"variantSelected_{generated.card_id}_{index - 1}"
            )
            checkbox.setToolTip(tr("review.use_variant"))
            checkbox.setChecked(True)
            row_layout.addWidget(checkbox)

            editor = QPlainTextEdit(row_widget)
            editor.setObjectName(f"variantText_{generated.card_id}_{index - 1}")
            editor.setPlainText(variant)
            editor.setMaximumHeight(70)
            editor.setTabChangesFocus(True)
            editor.setToolTip(escape(variant))
            row_layout.addWidget(editor, 1)
            layout.addWidget(row_widget)
            rows.append((checkbox, editor))

        self._variant_rows.append((generated, rows))
        return group

    def _set_all_variants_checked(self, checked: bool) -> None:
        for _generated, rows in self._variant_rows:
            for checkbox, _editor in rows:
                checkbox.setChecked(checked)

    def selected_generated(self) -> list[GeneratedVariants]:
        """Return copies containing only the selected, edited variants.

        Cards without a selected non-empty variant are omitted. Duplicate edits
        on the same card are collapsed while preserving their display order.
        """

        selected: list[GeneratedVariants] = []
        for generated, rows in self._variant_rows:
            variants: list[str] = []
            seen: set[str] = set()
            for checkbox, editor in rows:
                text = editor.toPlainText().strip()
                if checkbox.isChecked() and text and text not in seen:
                    seen.add(text)
                    variants.append(text)
            if variants:
                selected.append(replace(generated, variants=variants))
        return selected


class SettingsDialog(QDialog):
    """Edit learning behaviour, prefetching and the provider connection."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        enabled: bool = True,
        show_original_on_answer: bool = True,
        rewrite_intensity: str = "distinct",
        live_prefetch_enabled: bool = False,
        live_prefetch_count: int = 3,
        provider: str = "openai",
        model: str = "",
        connection_ready: bool = False,
        sent_card_count: int = 0,
        ui_language: str = "auto",
    ) -> None:
        super().__init__(parent)
        self._connection_action = ""
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumWidth(660)
        self.resize(700, 720)

        layout = QVBoxLayout(self)

        title = QLabel("<b>Variator</b>", self)
        title.setObjectName("settingsBrandTitle")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)
        subtitle = QLabel(
            tr("settings.subtitle"), self
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        scroll = QScrollArea(self)
        scroll.setObjectName("settingsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)

        language_form = QFormLayout()
        self.ui_language_combo = QComboBox(content)
        self.ui_language_combo.setObjectName("uiLanguageCombo")
        self.ui_language_combo.setAccessibleName(
            tr("settings.language_accessible")
        )
        for value, label in language_options():
            self.ui_language_combo.addItem(label, value)
        language_index = self.ui_language_combo.findData(
            normalize_ui_language(ui_language)
        )
        self.ui_language_combo.setCurrentIndex(
            language_index if language_index >= 0 else 0
        )
        language_form.addRow(tr("settings.language"), self.ui_language_combo)
        content_layout.addLayout(language_form)

        learning_group = QGroupBox(tr("settings.learning_group"), content)
        learning_group.setObjectName("learningSettingsGroup")
        learning_layout = QVBoxLayout(learning_group)
        self.enabled_checkbox = QCheckBox(
            tr("settings.enabled"), learning_group
        )
        self.enabled_checkbox.setObjectName("enabledCheckbox")
        self.enabled_checkbox.setChecked(enabled)
        learning_layout.addWidget(self.enabled_checkbox)

        intensity_group = QGroupBox(tr("settings.intensity_group"), learning_group)
        self.rewrite_intensity_group = intensity_group
        intensity_group.setObjectName("rewriteIntensityGroup")
        intensity_group.setEnabled(enabled)
        intensity_layout = QVBoxLayout(intensity_group)

        intensity_explanation = QLabel(tr("settings.intensity_help"), intensity_group)
        intensity_explanation.setWordWrap(True)
        intensity_layout.addWidget(intensity_explanation)

        self.rewrite_intensity_combo = QComboBox(intensity_group)
        self.rewrite_intensity_combo.setObjectName("rewriteIntensityCombo")
        for label_key, value in _REWRITE_INTENSITIES:
            self.rewrite_intensity_combo.addItem(tr(label_key), value)
        intensity_index = self.rewrite_intensity_combo.findData(rewrite_intensity)
        self.rewrite_intensity_combo.setCurrentIndex(
            intensity_index if intensity_index >= 0 else 2
        )
        intensity_layout.addWidget(self.rewrite_intensity_combo)
        learning_layout.addWidget(intensity_group)

        self.show_original_checkbox = QCheckBox(
            tr("settings.original_after_answer"), learning_group
        )
        self.show_original_checkbox.setObjectName("showOriginalOnAnswerCheckbox")
        self.show_original_checkbox.setChecked(show_original_on_answer)
        self.show_original_checkbox.setEnabled(enabled)
        learning_layout.addWidget(self.show_original_checkbox)
        content_layout.addWidget(learning_group)

        live_group = QGroupBox(tr("settings.prefetch_group"), content)
        self.live_prefetch_group = live_group
        live_group.setObjectName("livePrefetchGroup")
        live_group.setEnabled(enabled)
        live_layout = QVBoxLayout(live_group)

        self.live_prefetch_checkbox = QCheckBox(
            tr("settings.prefetch_enabled"), live_group
        )
        self.live_prefetch_checkbox.setObjectName("livePrefetchEnabledCheckbox")
        self.live_prefetch_checkbox.setChecked(live_prefetch_enabled)
        live_layout.addWidget(self.live_prefetch_checkbox)

        live_explanation = QLabel(tr("settings.prefetch_help"), live_group)
        live_explanation.setWordWrap(True)
        live_layout.addWidget(live_explanation)

        prefetch_row = QWidget(live_group)
        prefetch_row_layout = QHBoxLayout(prefetch_row)
        prefetch_row_layout.setContentsMargins(0, 0, 0, 0)
        prefetch_row_layout.addWidget(
            QLabel(tr("settings.prefetch_label"), prefetch_row)
        )
        self.live_prefetch_count_spin = QSpinBox(prefetch_row)
        self.live_prefetch_count_spin.setObjectName("livePrefetchCountSpin")
        self.live_prefetch_count_spin.setRange(1, 10)
        self.live_prefetch_count_spin.setValue(
            max(1, min(10, int(live_prefetch_count)))
        )
        self.live_prefetch_count_spin.setSuffix(tr("common.cards_suffix"))
        self.live_prefetch_count_spin.setEnabled(live_prefetch_enabled)
        prefetch_row_layout.addWidget(self.live_prefetch_count_spin)
        prefetch_row_layout.addStretch(1)
        live_layout.addWidget(prefetch_row)

        self.live_prefetch_checkbox.toggled.connect(
            self.live_prefetch_count_spin.setEnabled
        )
        self.enabled_checkbox.toggled.connect(self._master_enabled_changed)
        content_layout.addWidget(live_group)

        connection_group = QGroupBox(tr("settings.connection_group"), content)
        connection_group.setObjectName("connectionPrivacyGroup")
        connection_layout = QVBoxLayout(connection_group)

        provider_label = next(
            (label for label, value in _PROVIDERS if value == provider), provider
        )
        if connection_ready:
            status = tr(
                "settings.connected", provider=provider_label or "AI provider"
            )
            if model.strip():
                status += " · %s" % model.strip()
        else:
            status = tr("settings.not_connected")
        self.connection_status_label = QLabel(status, connection_group)
        self.connection_status_label.setObjectName("connectionStatusLabel")
        self.connection_status_label.setWordWrap(True)
        self.connection_status_label.setTextFormat(Qt.TextFormat.PlainText)
        connection_layout.addWidget(self.connection_status_label)

        self.sent_card_count_label = QLabel(
            tr(
                "settings.sent_cards",
                count=max(0, int(sent_card_count)),
            ),
            connection_group,
        )
        self.sent_card_count_label.setObjectName("sentCardCountLabel")
        self.sent_card_count_label.setTextFormat(Qt.TextFormat.PlainText)
        self.sent_card_count_label.setToolTip(tr("settings.sent_cards_help"))
        connection_layout.addWidget(self.sent_card_count_label)

        connection_buttons = QVBoxLayout()
        self.connection_setup_button = QPushButton(
            tr(
                "settings.connection_change"
                if connection_ready
                else "settings.connection_setup"
            ),
            connection_group,
        )
        self.connection_setup_button.setObjectName("connectionSetupButton")
        self.connection_setup_button.clicked.connect(
            self._request_connection_setup
        )
        connection_buttons.addWidget(self.connection_setup_button)

        self.disconnect_connection_button = QPushButton(
            tr("settings.disconnect"), connection_group
        )
        self.disconnect_connection_button.setObjectName(
            "disconnectConnectionButton"
        )
        self.disconnect_connection_button.setEnabled(connection_ready)
        self.disconnect_connection_button.clicked.connect(
            self._request_connection_disconnect
        )
        connection_buttons.addWidget(self.disconnect_connection_button)
        connection_layout.addLayout(connection_buttons)

        privacy_summary = QLabel(tr("settings.privacy_summary"), connection_group)
        privacy_summary.setObjectName("settingsPrivacySummary")
        privacy_summary.setWordWrap(True)
        connection_layout.addWidget(privacy_summary)

        data_group = QGroupBox(tr("settings.local_data_group"), connection_group)
        data_group.setObjectName("localDataGroup")
        data_layout = QVBoxLayout(data_group)

        self.delete_profile_data_checkbox = QCheckBox(
            tr("settings.delete_variants"), data_group
        )
        self.delete_profile_data_checkbox.setObjectName(
            "deleteProfileVariantsCheckbox"
        )
        self.delete_profile_data_checkbox.setChecked(False)
        data_layout.addWidget(self.delete_profile_data_checkbox)

        self.delete_api_keys_checkbox = QCheckBox(
            tr("settings.delete_keys"), data_group
        )
        self.delete_api_keys_checkbox.setObjectName("deleteAllApiKeysCheckbox")
        self.delete_api_keys_checkbox.setChecked(False)
        data_layout.addWidget(self.delete_api_keys_checkbox)

        delete_note = QLabel(tr("settings.delete_note"), data_group)
        delete_note.setWordWrap(True)
        data_layout.addWidget(delete_note)
        connection_layout.addWidget(data_group)
        content_layout.addWidget(connection_group)

        note = QLabel(tr("settings.unchanged_note"), self)
        note.setWordWrap(True)
        content_layout.addWidget(note)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText(tr("common.save"))
        cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if cancel_button is not None:
            cancel_button.setText(tr("common.cancel"))
        layout.addWidget(self.button_box)

    def _request_connection_setup(self) -> None:
        self._connection_action = "setup"
        self.accept()

    def _request_connection_disconnect(self) -> None:
        self._connection_action = "disconnect"
        self.accept()

    def enabled(self) -> bool:
        return self.enabled_checkbox.isChecked()

    def _master_enabled_changed(self, enabled: bool) -> None:
        self.rewrite_intensity_group.setEnabled(enabled)
        self.show_original_checkbox.setEnabled(enabled)
        self.live_prefetch_group.setEnabled(enabled)
        if not enabled:
            self.live_prefetch_checkbox.setChecked(False)

    def show_original_on_answer(self) -> bool:
        return self.show_original_checkbox.isChecked()

    def rewrite_intensity(self) -> str:
        value = self.rewrite_intensity_combo.currentData()
        return str(value) if value is not None else "distinct"

    def live_prefetch_enabled(self) -> bool:
        return self.live_prefetch_checkbox.isChecked()

    def live_prefetch_count(self) -> int:
        return self.live_prefetch_count_spin.value()

    def ui_language(self) -> str:
        value = self.ui_language_combo.currentData()
        return normalize_ui_language(value)

    def settings_values(self) -> dict[str, bool | int | str]:
        return {
            "enabled": self.enabled(),
            "show_original_on_answer": self.show_original_on_answer(),
            "rewrite_intensity": self.rewrite_intensity(),
            "live_prefetch_enabled": self.live_prefetch_enabled(),
            "live_prefetch_count": self.live_prefetch_count(),
            "ui_language": self.ui_language(),
        }

    def delete_profile_variants(self) -> bool:
        return self.delete_profile_data_checkbox.isChecked()

    def delete_all_api_keys(self) -> bool:
        return self.delete_api_keys_checkbox.isChecked()

    def connection_setup_requested(self) -> bool:
        """Return whether settings should continue into provider setup."""

        return self._connection_action == "setup"

    def connection_disconnect_requested(self) -> bool:
        """Return whether credentials and transfer consent should be revoked."""

        return self._connection_action == "disconnect"

    # Readable aliases for controllers that phrase the actions differently.
    def configure_connection_requested(self) -> bool:
        return self.connection_setup_requested()

    def disconnect_connection_requested(self) -> bool:
        return self.connection_disconnect_requested()
