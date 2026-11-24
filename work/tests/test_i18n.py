from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest


MODULE_PATH = Path(__file__).parents[1] / "fragevariator" / "i18n.py"
SPEC = importlib.util.spec_from_file_location("variator_i18n_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
I18N = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(I18N)


class I18nContractTests(unittest.TestCase):
    def tearDown(self) -> None:
        I18N.set_ui_language("en")

    def test_supported_languages_and_normalisation(self) -> None:
        self.assertEqual(I18N.SUPPORTED_UI_LANGUAGES, ("en", "de", "es", "fr", "ru"))
        self.assertEqual(I18N.normalize_ui_language("de_DE"), "de")
        self.assertEqual(I18N.normalize_ui_language("Español"), "es")
        self.assertEqual(I18N.normalize_ui_language("ru-RU"), "ru")
        self.assertEqual(I18N.normalize_ui_language("unsupported"), "auto")

    def test_every_visible_key_has_all_five_translations(self) -> None:
        expected = set(I18N._EN)
        self.assertTrue(expected)
        for code, translations in I18N._TRANSLATIONS.items():
            with self.subTest(language=code):
                self.assertEqual(set(translations), expected)
                self.assertTrue(all(translations.values()))

    def test_active_anki_language_wins_over_profile_default(self) -> None:
        old_anki = sys.modules.get("anki")
        fake_anki = ModuleType("anki")
        fake_anki.lang = SimpleNamespace(current_lang="fr_FR")
        sys.modules["anki"] = fake_anki
        mw = SimpleNamespace(
            pm=SimpleNamespace(meta={"defaultLang": "de_DE"}, profile={})
        )
        try:
            self.assertEqual(I18N.detect_anki_language(mw), "fr")
        finally:
            if old_anki is None:
                sys.modules.pop("anki", None)
            else:
                sys.modules["anki"] = old_anki

    def test_unsupported_active_anki_language_falls_back_to_english(self) -> None:
        old_anki = sys.modules.get("anki")
        fake_anki = ModuleType("anki")
        fake_anki.lang = SimpleNamespace(current_lang="ja_JP")
        sys.modules["anki"] = fake_anki
        mw = SimpleNamespace(
            pm=SimpleNamespace(meta={"defaultLang": "de_DE"}, profile={})
        )
        try:
            self.assertEqual(I18N.detect_anki_language(mw), "en")
        finally:
            if old_anki is None:
                sys.modules.pop("anki", None)
            else:
                sys.modules["anki"] = old_anki

    def test_profile_locale_and_english_fallback(self) -> None:
        old_anki = sys.modules.get("anki")
        sys.modules.pop("anki", None)
        try:
            mw = SimpleNamespace(
                pm=SimpleNamespace(meta={"defaultLang": "ru_RU"}, profile={})
            )
            self.assertEqual(I18N.detect_anki_language(mw), "ru")
            self.assertEqual(I18N.detect_anki_language(SimpleNamespace()), "en")
        finally:
            if old_anki is not None:
                sys.modules["anki"] = old_anki

    def test_translation_formatting_and_language_options(self) -> None:
        I18N.set_ui_language("de")
        self.assertIn("3", I18N.tr("notice.live_active", count=3))
        options = dict(I18N.language_options())
        self.assertEqual(set(options), {"auto", "en", "de", "es", "fr", "ru"})
        self.assertEqual(options["de"], "Deutsch")
        self.assertIn("Anki", options["auto"])

    def test_compact_status_words_are_localized_without_decorative_dot(self) -> None:
        expected = {
            "en": ("On", "Off", "Error"),
            "de": ("Ein", "Aus", "Fehler"),
            "es": ("Activado", "Desactivado", "Error"),
            "fr": ("Activé", "Désactivé", "Erreur"),
            "ru": ("Вкл.", "Выкл.", "Ошибка"),
        }
        for language, labels in expected.items():
            with self.subTest(language=language):
                I18N.set_ui_language(language)
                self.assertEqual(
                    tuple(
                        I18N.tr(key)
                        for key in ("status.live", "status.off", "status.paused")
                    ),
                    labels,
                )
                self.assertEqual(
                    I18N.tr("menu.live_switch"),
                    I18N.tr("menu.automatic_questions"),
                )
                self.assertNotIn("·", I18N.tr("notice.live_active", count=3))

    def test_failure_guidance_is_localized_in_every_language(self) -> None:
        for language in I18N.SUPPORTED_UI_LANGUAGES:
            with self.subTest(language=language):
                I18N.set_ui_language(language)
                reason = I18N.tr("provider_error.auth")
                live = I18N.tr("notice.live_failed_detail", reason=reason)
                offline = I18N.tr("warning.offline_failed", reason=reason)
                self.assertIn(reason, live)
                self.assertIn(reason, offline)
                self.assertNotIn("{reason}", live + offline)


if __name__ == "__main__":
    unittest.main()
