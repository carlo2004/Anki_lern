from __future__ import annotations

import ast
from pathlib import Path
import unittest


SOURCE_PATH = Path(__file__).parents[1] / "fragevariator" / "ui" / "dialogs.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
UI_INIT_SOURCE = SOURCE_PATH.with_name("__init__.py").read_text(encoding="utf-8")


def _class(name: str) -> ast.ClassDef:
    return next(
        node
        for node in TREE.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _method(class_name: str, method_name: str) -> ast.FunctionDef:
    return next(
        node
        for node in _class(class_name).body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


class RewriteIntensityUiContractTests(unittest.TestCase):
    def test_four_ordered_intensities_have_stable_values(self) -> None:
        assignment = next(
            node
            for node in TREE.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_REWRITE_INTENSITIES"
        )
        self.assertEqual(
            ast.literal_eval(assignment.value),
            (
                ("intensity.near", "near"),
                ("intensity.light", "light"),
                ("intensity.distinct", "distinct"),
                ("intensity.maximum", "maximum"),
            ),
        )

    def test_settings_default_and_public_value_api_use_distinct(self) -> None:
        init = _method("SettingsDialog", "__init__")
        defaults = {
            argument.arg: ast.literal_eval(default)
            for argument, default in zip(
                init.args.kwonlyargs, init.args.kw_defaults, strict=True
            )
            if default is not None
        }
        self.assertEqual(defaults["rewrite_intensity"], "distinct")
        self.assertIsNotNone(_method("SettingsDialog", "rewrite_intensity"))

        settings_values = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "settings_values")
        )
        self.assertIn('"rewrite_intensity": self.rewrite_intensity()', settings_values)

    def test_intensity_control_is_between_master_switch_and_live_group(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "__init__")
        )
        learning_position = init_source.index(
            "content_layout.addWidget(learning_group)"
        )
        live_position = init_source.index("content_layout.addWidget(live_group)")
        connection_position = init_source.index(
            "content_layout.addWidget(connection_group)"
        )
        self.assertLess(learning_position, live_position)
        self.assertLess(live_position, connection_position)
        self.assertIn("learning_layout.addWidget(self.enabled_checkbox)", init_source)
        self.assertIn("learning_layout.addWidget(intensity_group)", init_source)
        self.assertIn('setObjectName("rewriteIntensityCombo")', init_source)

    def test_setup_dialog_does_not_duplicate_the_rare_setting(self) -> None:
        setup = _class("GenerationSetupDialog")
        setup_source = ast.get_source_segment(SOURCE, setup)
        self.assertNotIn("rewrite_intensity", setup_source)
        self.assertNotIn("rewriteIntensityCombo", setup_source)

    def test_original_comparison_is_a_visible_saved_learning_option(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "__init__")
        )
        values_source = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "settings_values")
        )
        master_source = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "_master_enabled_changed")
        )

        self.assertIn('setObjectName("showOriginalOnAnswerCheckbox")', init_source)
        self.assertIn(
            "self.show_original_checkbox.setChecked(show_original_on_answer)",
            init_source,
        )
        self.assertIn(
            "learning_layout.addWidget(self.show_original_checkbox)", init_source
        )
        self.assertNotIn("self.show_original_checkbox.setVisible(False)", init_source)
        self.assertIn(
            '"show_original_on_answer": self.show_original_on_answer()',
            values_source,
        )
        self.assertIn(
            "self.show_original_checkbox.setEnabled(enabled)", master_source
        )


class SetupDialogUxContractTests(unittest.TestCase):
    def test_provider_key_links_are_official_and_provider_specific(self) -> None:
        assignment = next(
            node
            for node in TREE.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_PROVIDER_KEY_URLS"
        )
        links = ast.literal_eval(assignment.value)
        self.assertEqual(set(links), {"openai", "gemini", "anthropic", "xai"})
        self.assertIn("platform.openai.com/api-keys", links["openai"][1])
        self.assertIn("aistudio.google.com/app/apikey", links["gemini"][1])
        self.assertIn("platform.claude.com/settings/keys", links["anthropic"][1])
        self.assertIn("console.x.ai", links["xai"][1])

    def test_setup_keeps_only_provider_and_key_in_primary_form(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("GenerationSetupDialog", "__init__")
        )
        provider_position = init_source.index('form.addRow(tr("common.provider")')
        key_position = init_source.index('form.addRow(tr("common.api_key")')
        remember_position = init_source.index("layout.addWidget(self.store_key_checkbox)")
        advanced_position = init_source.index(
            'setObjectName("advancedDetailsToggle")'
        )
        self.assertLess(provider_position, key_position)
        self.assertLess(key_position, remember_position)
        self.assertLess(remember_position, advanced_position)
        self.assertIn('advanced_form.addRow(tr("common.model")', init_source)
        self.assertIn('tr("setup.remember")', init_source)
        self.assertIn("self.advanced_details_widget.setVisible(False)", init_source)

    def test_live_cost_notice_and_consent_stay_visible(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("GenerationSetupDialog", "__init__")
        )
        self.assertIn('setObjectName("liveCostNotice")', init_source)
        self.assertIn("self.cost_notice.setVisible(True)", init_source)
        self.assertIn("self.privacy_details_widget.setVisible(False)", init_source)
        self.assertIn(
            "layout.addWidget(self.content_transfer_checkbox)", init_source
        )

    def test_live_startup_prefetch_is_explicit_in_privacy_and_consent(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("GenerationSetupDialog", "__init__")
        )
        consent_source = ast.get_source_segment(
            SOURCE,
            _method("GenerationSetupDialog", "_content_transfer_consent_text"),
        )
        self.assertIn('"setup.privacy.live"', init_source)
        self.assertIn('tr("setup.consent"', consent_source)
        self.assertNotIn("Profilstart", consent_source)

    def test_remember_wording_is_short_and_session_state_is_explicit(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("GenerationSetupDialog", "__init__")
        )
        state_source = ast.get_source_segment(
            SOURCE, _method("GenerationSetupDialog", "_update_remember_key_state")
        )
        self.assertIn('tr("setup.remember")', init_source)
        self.assertIn('"setup.remember.session"', state_source)
        self.assertNotIn("Klartext speichern", init_source)

    def test_environment_key_is_shown_as_externally_managed(self) -> None:
        init = _method("GenerationSetupDialog", "__init__")
        defaults = {
            argument.arg: ast.literal_eval(default)
            for argument, default in zip(
                init.args.kwonlyargs, init.args.kw_defaults, strict=True
            )
            if default is not None
        }
        self.assertEqual(defaults["api_key_source"], "")
        state_source = ast.get_source_segment(
            SOURCE,
            _method("GenerationSetupDialog", "_set_environment_key_state"),
        )
        self.assertIn('"setup.remember.environment"', state_source)
        self.assertIn("self.api_key_edit.setEnabled(not active)", state_source)
        self.assertIn("self.store_key_checkbox.setEnabled(not active)", state_source)


class SettingsConnectionUxContractTests(unittest.TestCase):
    def test_connection_context_has_backward_compatible_defaults(self) -> None:
        init = _method("SettingsDialog", "__init__")
        defaults = {
            argument.arg: ast.literal_eval(default)
            for argument, default in zip(
                init.args.kwonlyargs, init.args.kw_defaults, strict=True
            )
            if default is not None
        }
        self.assertEqual(defaults["provider"], "openai")
        self.assertEqual(defaults["model"], "")
        self.assertFalse(defaults["connection_ready"])
        self.assertEqual(defaults["sent_card_count"], 0)

    def test_connection_buttons_expose_controller_flags(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "__init__")
        )
        self.assertIn('setObjectName("connectionStatusLabel")', init_source)
        self.assertIn('setObjectName("sentCardCountLabel")', init_source)
        self.assertIn('tr("settings.sent_cards_help")', init_source)
        self.assertIn('setObjectName("connectionSetupButton")', init_source)
        self.assertIn('"disconnectConnectionButton"', init_source)
        self.assertIsNotNone(
            _method("SettingsDialog", "connection_setup_requested")
        )
        self.assertIsNotNone(
            _method("SettingsDialog", "connection_disconnect_requested")
        )

    def test_destructive_options_are_grouped_as_local_data(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "__init__")
        )
        data_group_position = init_source.index(
            'QGroupBox(tr("settings.local_data_group")'
        )
        variants_position = init_source.index("self.delete_profile_data_checkbox")
        keys_position = init_source.index("self.delete_api_keys_checkbox")
        self.assertLess(data_group_position, variants_position)
        self.assertLess(variants_position, keys_position)

    def test_language_preference_is_first_class_and_saved(self) -> None:
        init = _method("SettingsDialog", "__init__")
        defaults = {
            argument.arg: ast.literal_eval(default)
            for argument, default in zip(
                init.args.kwonlyargs, init.args.kw_defaults, strict=True
            )
            if default is not None
        }
        self.assertEqual(defaults["ui_language"], "auto")
        init_source = ast.get_source_segment(SOURCE, init)
        self.assertIn('setObjectName("uiLanguageCombo")', init_source)
        self.assertIn("language_options()", init_source)
        values_source = ast.get_source_segment(
            SOURCE, _method("SettingsDialog", "settings_values")
        )
        self.assertIn('"ui_language": self.ui_language()', values_source)


class OfflinePreparationDialogContractTests(unittest.TestCase):
    def test_public_constructor_and_getters_are_stable(self) -> None:
        init = _method("OfflinePreparationDialog", "__init__")
        keyword_names = [argument.arg for argument in init.args.kwonlyargs]
        self.assertEqual(
            keyword_names,
            ["decks", "default_deck_id", "default_count"],
        )
        defaults = {
            argument.arg: ast.literal_eval(default)
            for argument, default in zip(
                init.args.kwonlyargs, init.args.kw_defaults, strict=True
            )
            if default is not None
        }
        self.assertIsNone(defaults["default_deck_id"])
        self.assertEqual(defaults["default_count"], 20)
        self.assertIsNotNone(_method("OfflinePreparationDialog", "deck_id"))
        self.assertIsNotNone(_method("OfflinePreparationDialog", "card_count"))
        self.assertIn("OfflinePreparationDialog", UI_INIT_SOURCE)

    def test_dialog_asks_only_for_deck_and_upcoming_card_count(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("OfflinePreparationDialog", "__init__")
        )
        self.assertIn('setObjectName("offlineDeckCombo")', init_source)
        self.assertIn('setObjectName("offlineCardCountSpin")', init_source)
        self.assertIn("self.card_count_spin.setRange(1, 50)", init_source)
        self.assertIn("max(1, min(50, count))", init_source)
        self.assertIn('setText(tr("offline.prepare"))', init_source)
        self.assertIn('setText(tr("common.cancel"))', init_source)
        self.assertNotIn("QCheckBox", init_source)
        self.assertNotIn("QLineEdit", init_source)

    def test_costs_and_next_due_cards_are_clear(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("OfflinePreparationDialog", "__init__")
        )
        self.assertIn('tr("offline.summary")', init_source)
        self.assertIn('tr("offline.cost")', init_source)
        self.assertIn('setObjectName("offlineCostNotice")', init_source)
        self.assertIn("summary.setTextFormat(Qt.TextFormat.PlainText)", init_source)
        self.assertIn("cost_notice.setTextFormat(Qt.TextFormat.PlainText)", init_source)
        self.assertNotIn("So funktioniert", init_source)
        self.assertNotIn("Schritt", init_source)

    def test_deck_entries_are_normalised_and_empty_state_is_safe(self) -> None:
        normalise_source = ast.get_source_segment(
            SOURCE, _method("OfflinePreparationDialog", "_normalise_decks")
        )
        init_source = ast.get_source_segment(
            SOURCE, _method("OfflinePreparationDialog", "__init__")
        )
        self.assertIn('entry.get("deck_id", entry.get("id"))', normalise_source)
        self.assertIn("seen_ids", normalise_source)
        self.assertIn("if deck_id <= 0 or not name", normalise_source)
        self.assertIn('addItem(tr("offline.no_decks"), None)', init_source)
        self.assertIn("setEnabled(bool(normalised_decks))", init_source)

    def test_keyboard_and_accessibility_contract_is_explicit(self) -> None:
        init_source = ast.get_source_segment(
            SOURCE, _method("OfflinePreparationDialog", "__init__")
        )
        self.assertIn("deck_label.setBuddy(self.deck_combo)", init_source)
        self.assertIn("count_label.setBuddy(self.card_count_spin)", init_source)
        self.assertIn("setAccessibleName", init_source)
        self.assertIn("self.prepare_button.setDefault(True)", init_source)
        self.assertIn("self.button_box.rejected.connect(self.reject)", init_source)


if __name__ == "__main__":
    unittest.main()
