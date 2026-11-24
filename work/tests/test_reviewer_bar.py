from __future__ import annotations

import json
import unittest

from fragevariator.core.reviewer_bar import (
    BOTTOM_BAR_HEAD,
    CLEAR_ORIGINAL_INLINE_SCRIPT,
    COLLAPSE_ORIGINAL_BUTTON_SCRIPT,
    HIDE_ORIGINAL_INLINE_SCRIPT,
    HIDE_ORIGINAL_SCRIPT,
    SHOW_ORIGINAL_INLINE_SCRIPT,
    TOGGLE_ORIGINAL_MESSAGE,
    bottom_bar_head,
    clear_original_inline_script,
    hide_original_inline_script,
    parse_original_toggle_message,
    retranslate_inline_script,
    retranslate_script,
    set_original_inline_script,
    set_original_script,
    show_original_inline_script,
)
from fragevariator.i18n import set_ui_language, tr


class ReviewerBottomBarContractTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_ui_language("en")

    def test_toolbar_reuses_ankis_native_button_layout(self) -> None:
        self.assertIn('document.createElement("button")', BOTTOM_BAR_HEAD)
        self.assertIn("findButtonPlacement", BOTTOM_BAR_HEAD)
        self.assertIn(
            "placement.host.insertBefore(button, placement.before)",
            BOTTOM_BAR_HEAD,
        )
        self.assertIn("matchButtonGeometry", BOTTOM_BAR_HEAD)
        self.assertIn("MutationObserver", BOTTOM_BAR_HEAD)
        self.assertNotIn("<style>", BOTTOM_BAR_HEAD)
        self.assertNotIn("min-width", BOTTOM_BAR_HEAD)
        self.assertNotIn("min-height", BOTTOM_BAR_HEAD)
        self.assertNotIn("padding-top", BOTTOM_BAR_HEAD)
        self.assertNotIn("linear-gradient", BOTTOM_BAR_HEAD)
        self.assertNotIn("translateY", BOTTOM_BAR_HEAD)
        self.assertNotIn('document.createElement("td")', BOTTOM_BAR_HEAD)

    def test_toolbar_sends_explicit_state_for_the_current_card(self) -> None:
        self.assertIn(TOGGLE_ORIGINAL_MESSAGE, BOTTOM_BAR_HEAD)
        self.assertIn('state.open ? "show" : "hide"', BOTTOM_BAR_HEAD)
        self.assertIn("state.cardId", BOTTOM_BAR_HEAD)
        self.assertNotIn("fv-original-panel", BOTTOM_BAR_HEAD)
        self.assertNotIn("notifyResize", BOTTOM_BAR_HEAD)
        self.assertNotIn("resize-original-bar", BOTTOM_BAR_HEAD)
        self.assertNotIn("adjustHeightToFit", BOTTOM_BAR_HEAD)

    def test_toolbar_labels_follow_the_selected_language(self) -> None:
        for language in ("de", "en", "es", "fr", "ru"):
            set_ui_language(language)
            rendered = bottom_bar_head()
            for key in ("reviewer.show_original", "reviewer.hide_original"):
                self.assertIn(json.dumps(tr(key), ensure_ascii=True), rendered)

    def test_open_toolbar_can_be_retranslated_without_reloading_it(self) -> None:
        set_ui_language("ru")
        script = retranslate_script()

        self.assertIn("frageVariatorSetLabels", script)
        for key in ("reviewer.show_original", "reviewer.hide_original"):
            self.assertIn(json.dumps(tr(key), ensure_ascii=True), script)

    def test_disclosure_is_accessible_with_native_keyboard_activation(self) -> None:
        self.assertIn('button.type = "button"', BOTTOM_BAR_HEAD)
        self.assertIn('button.setAttribute("aria-label"', BOTTOM_BAR_HEAD)
        self.assertIn('button.setAttribute("aria-expanded"', BOTTOM_BAR_HEAD)
        self.assertNotIn("event.detail", BOTTOM_BAR_HEAD)
        self.assertNotIn("preventScroll", BOTTOM_BAR_HEAD)

    def test_original_availability_does_not_copy_card_data_to_bottom_bar(self) -> None:
        original = 'Frage "A"?\nZweite Zeile'
        script = set_original_script(original, 123)

        self.assertIn('frageVariatorSetOriginal(true, "123")', script)
        self.assertNotIn("Frage", script)
        self.assertIn(
            'frageVariatorSetOriginal(false, "123")',
            set_original_script("", 123),
        )
        self.assertIn("frageVariatorHideOriginal", HIDE_ORIGINAL_SCRIPT)

    def test_main_script_waits_for_and_toggles_the_inline_section(self) -> None:
        script = set_original_inline_script(123)

        self.assertIn('const expectedCardId = "123"', script)
        self.assertIn('data-fv-original-front="${expectedCardId}"', script)
        self.assertNotIn("if (!initialRegion) return", script)
        self.assertIn("let desiredOpen = false", script)
        self.assertIn("let lastAppliedOpen = false", script)
        self.assertIn("const shouldScroll = desiredOpen", script)
        self.assertIn("const observer = new MutationObserver(applyState)", script)
        self.assertIn("observer.observe(document.documentElement", script)
        self.assertIn("if (!region) {", script)
        self.assertIn(
            "region.hidden = !desiredOpen",
            script,
        )
        self.assertIn("frageVariatorSetOriginalInlineOpen", script)
        self.assertIn('region.setAttribute("aria-hidden"', script)
        self.assertIn('region.style.setProperty(', script)
        self.assertIn(
            '"display", desiredOpen ? "block" : "none", "important"',
            script,
        )
        self.assertIn("region.scrollIntoView", script)
        self.assertNotIn("Original question", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("createElement", script)
        self.assertNotIn("insertBefore", script)
        self.assertNotIn("appendChild", script)
        self.assertNotIn("position: fixed", script)
        self.assertNotIn("bottom:", script)
        self.assertNotIn("max-height", script)
        self.assertNotIn('querySelector(".fv-answer-original")', script)
        self.assertNotIn("adjustHeightToFit", script)
        self.assertNotIn("notifyResize", script)

    def test_inline_context_has_lifecycle_controls_without_card_payload(self) -> None:
        script = set_original_inline_script(987)

        self.assertNotIn("Frage", script)
        self.assertIn("frageVariatorToggleOriginalInline", script)
        self.assertIn("frageVariatorHideOriginalInline", script)
        self.assertIn("frageVariatorClearOriginalInline", script)
        self.assertIn("frageVariatorDisposeOriginalInline", script)
        self.assertIn("observer.disconnect()", script)
        self.assertIn(
            'SetOriginalInlineOpen(true, "987")',
            show_original_inline_script(987),
        )
        self.assertIn(
            'SetOriginalInlineOpen(false, "987")',
            hide_original_inline_script(987),
        )
        self.assertIn(
            'frageVariatorClearOriginalInline("987")',
            clear_original_inline_script(987),
        )
        for compatibility_script in (
            SHOW_ORIGINAL_INLINE_SCRIPT,
            HIDE_ORIGINAL_INLINE_SCRIPT,
            CLEAR_ORIGINAL_INLINE_SCRIPT,
        ):
            self.assertIn('"0"', compatibility_script)
        self.assertIn("frageVariatorSetOriginalOpen(false)", COLLAPSE_ORIGINAL_BUTTON_SCRIPT)

    def test_inline_heading_can_be_retranslated(self) -> None:
        set_ui_language("fr")
        script = retranslate_inline_script(123)

        self.assertIn("data-fv-original-front", script)
        self.assertIn('\\"123\\"', script)
        self.assertTrue(script.startswith("(() => {"))
        self.assertTrue(script.endswith("})();"))
        self.assertIn(".fv-answer-label", script)
        self.assertIn("aria-label", script)
        self.assertIn(json.dumps(tr("reviewer.original"), ensure_ascii=True), script)

    def test_toggle_messages_are_card_scoped_and_fail_closed(self) -> None:
        self.assertEqual(
            parse_original_toggle_message(
                f"{TOGGLE_ORIGINAL_MESSAGE}:show:123456"
            ),
            (True, 123456),
        )
        self.assertEqual(
            parse_original_toggle_message(
                f"{TOGGLE_ORIGINAL_MESSAGE}:hide:123456"
            ),
            (False, 123456),
        )
        for invalid in (
            TOGGLE_ORIGINAL_MESSAGE,
            f"{TOGGLE_ORIGINAL_MESSAGE}:toggle:123",
            f"{TOGGLE_ORIGINAL_MESSAGE}:show:not-a-card",
            f"{TOGGLE_ORIGINAL_MESSAGE}:show:-1",
        ):
            self.assertIsNone(parse_original_toggle_message(invalid))


if __name__ == "__main__":
    unittest.main()
