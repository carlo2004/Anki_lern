from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fragevariator.core.models import CardImage, CardSnapshot, GeneratedVariants, ProviderSettings
from fragevariator.core.prompt import build_prompt
from fragevariator.core.render import (
    original_context_available,
    render_answer_context,
    render_question,
    safe_initially_visible_fragment,
    safe_original_fragment,
)
from fragevariator.core.result_parser import (
    GenerationParseError,
    UnsupportedCardError,
    _candidate_leaks_answer,
    parse_generation,
)
from fragevariator.core.secrets import (
    SecretProtectionError,
    SecretStore,
    SecretStoreError,
    persistent_storage_is_protected,
)
from fragevariator.core.store import VariantStore
from fragevariator.core.text import (
    answer_without_question,
    html_to_text,
    source_hash,
    variant_source_hash,
)
from fragevariator.core.visual import (
    attach_front_screenshot,
    fitted_capture_size,
    front_requires_screenshot,
    mark_front_screenshot_failed,
)
from fragevariator.anki_bridge import generate_batch, snapshot_card
from fragevariator.core.providers import ErrorKind, ProviderError
from fragevariator.i18n import set_ui_language, tr


TEST_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
)
TEST_JPEG = b"\xff\xd8\xff\xe0visual-card\xff\xd9"


class _SnapshotNote:
    id = 101
    mid = 1

    def note_type(self) -> dict[str, object]:
        return {"name": "Einfach", "flds": []}

    def keys(self) -> list[str]:
        return ["Front", "Back"]


class _SnapshotCard:
    id = 1
    nid = 101
    did = 1

    def __init__(self, question_html: str, answer_html: str) -> None:
        self._question_html = question_html
        self._answer_html = answer_html
        self._note = _SnapshotNote()

    def note(self) -> _SnapshotNote:
        return self._note

    def question(self) -> str:
        return self._question_html

    def answer(self) -> str:
        return self._answer_html

    def question_av_tags(self) -> list[object]:
        return []

    def answer_av_tags(self) -> list[object]:
        return []

    def current_deck_id(self) -> int:
        return 1


class _SnapshotMedia:
    def __init__(self, root: Path, filenames: list[str]) -> None:
        self._root = root
        self._filenames = filenames

    def dir(self) -> str:
        return str(self._root)

    def files_in_str(
        self, _mid: int, source: str, *, include_remote: bool
    ) -> list[str]:
        assert include_remote is False
        return [filename for filename in self._filenames if filename in source]


class _SnapshotDecks:
    def name(self, _deck_id: int) -> str:
        return "Test"


class _SnapshotCollection:
    def __init__(self, card: _SnapshotCard, media: _SnapshotMedia) -> None:
        self._card = card
        self.media = media
        self.decks = _SnapshotDecks()

    def get_card(self, _card_id: int) -> _SnapshotCard:
        return self._card


class TextTests(unittest.TestCase):
    def test_visible_html_is_extracted_without_active_content(self) -> None:
        value = '<style>secret</style><div>Wo liegt <b>Berlin</b>?</div><script>alert(1)</script><img alt="Karte">'
        self.assertEqual(html_to_text(value), "Wo liegt Berlin?\n[image: Karte]")

    def test_visible_text_ignores_all_non_visible_subtrees(self) -> None:
        value = (
            "<div>Sichtbar eins</div>"
            "<div hidden>hidden <span>verschachtelt</span></div>"
            "<div inert>inert</div>"
            '<div aria-hidden="TRUE">aria hidden</div>'
            '<div style="display : none">display none</div>'
            '<div style="visibility: hidden">visibility hidden</div>'
            '<div style="visibility:collapse">visibility collapse</div>'
            "<noscript>noscript</noscript>"
            "<template>template</template>"
            '<div>Sichtbar zwei <img alt="Karte"></div>'
        )

        self.assertEqual(
            html_to_text(value),
            "Sichtbar eins\nSichtbar zwei [image: Karte]",
        )

    def test_media_and_truncation_metadata_is_language_neutral(self) -> None:
        value = '<img>[sound:voice.mp3]<div lang="ru">' + ("Я" * 30) + "</div>"
        rendered = html_to_text(value)
        truncated = html_to_text(value, max_chars=12)

        self.assertIn("[image]", rendered)
        self.assertIn("[audio]", rendered)
        self.assertTrue(truncated.endswith("[content-truncated]"))
        self.assertNotIn("Bild", rendered)
        self.assertNotIn("gekürzt", truncated)

    def test_hash_preserves_meaningful_whitespace_and_normalizes_line_endings(self) -> None:
        self.assertEqual(source_hash("a\r\nb"), source_hash("a\nb"))
        self.assertNotEqual(source_hash("a  b"), source_hash("a b"))
        self.assertNotEqual(source_hash("a b"), source_hash("a c"))

    def test_variant_hash_invalidates_pre_policy_raw_hashes(self) -> None:
        question_html = "<div>Welche Struktur ist markiert?</div>"
        answer_html = "<div>Die Mitralklappe.</div>"

        legacy_hash = source_hash(question_html + "\0" + answer_html)
        policy_hash = variant_source_hash(question_html, answer_html)

        self.assertNotEqual(policy_hash, legacy_hash)
        self.assertEqual(
            policy_hash,
            variant_source_hash(question_html, answer_html),
        )
        self.assertNotEqual(
            policy_hash,
            variant_source_hash(question_html + "!", answer_html),
        )

    def test_variant_hash_isolated_by_rewrite_intensity(self) -> None:
        question_html = "<div>Welche Struktur ist markiert?</div>"
        answer_html = "<div>Die Mitralklappe.</div>"
        hashes = {
            intensity: variant_source_hash(
                question_html, answer_html, intensity
            )
            for intensity in ("near", "light", "distinct", "maximum")
        }

        self.assertEqual(len(set(hashes.values())), 4)
        self.assertEqual(
            variant_source_hash(question_html, answer_html),
            hashes["distinct"],
        )
        self.assertEqual(
            variant_source_hash(question_html, answer_html, "invalid"),
            hashes["distinct"],
        )

    def test_front_media_detection_is_conservative(self) -> None:
        from fragevariator.core.text import has_front_media

        self.assertTrue(has_front_media('<img src="map.png">'))
        self.assertTrue(has_front_media('[sound:question.mp3]'))
        self.assertFalse(has_front_media('<b>Nur Text</b>'))

    def test_frontside_prefix_can_be_removed_from_answer_context(self) -> None:
        self.assertEqual(answer_without_question("Hauptstadt?", "Hauptstadt? — Berlin"), "Berlin")


class ParserTests(unittest.TestCase):
    def test_valid_generation_is_cleaned_and_deduplicated(self) -> None:
        variant = (
            "Vervollständige die Lernantwort mit genau drei Punkten: "
            "Sekundäre Hypertonie kann verursacht werden durch 1. ___, 2. ___, 3. ___."
        )
        parsed = parse_generation(
            {
                "status": "ok",
                "is_equivalent": True,
                "answer_not_revealed": True,
                "is_substantially_different": True,
                "change_strategy": "completion_prompt",
                "core_aspect": "Drei Ursachen der sekundären Hypertonie",
                "variants": [
                    variant,
                    variant,
                    "Nenne drei Ursachen der sekundären Hypertonie.",
                ],
                "warnings": [],
                "unsupported_reason": "",
            },
            "Nenne drei Ursachen der sekundären Hypertonie.",
            "Zum Beispiel Nierenerkrankungen, endokrine Störungen und Medikamente.",
            3,
        )
        self.assertEqual(parsed["variants"], [variant])
        self.assertTrue(parsed["warnings"])

    def test_internal_image_markers_never_reach_the_review_question(self) -> None:
        parsed = parse_generation(
            {
                "status": "ok",
                "is_equivalent": True,
                "answer_not_revealed": True,
                "is_substantially_different": True,
                "change_strategy": "completion_prompt",
                "core_aspect": "Zerlegung des Integrals [image]",
                "variants": [
                    "Vervollständigen Sie die Formel für das abgebildete Integral:\n"
                    "[image]"
                ],
                "warnings": [],
                "unsupported_reason": "",
            },
            "Welche Zerlegbarkeit ist für folgendes Integral erlaubt?\n[image]",
            "[image]",
            1,
        )

        self.assertEqual(
            parsed["variants"],
            ["Vervollständigen Sie die Formel für das abgebildete Integral:"],
        )
        self.assertEqual(parsed["core_aspect"], "Zerlegung des Integrals")

    def test_image_only_front_can_be_replaced_by_a_self_contained_question(self) -> None:
        parsed = parse_generation(
            {
                "status": "ok",
                "is_equivalent": True,
                "answer_not_revealed": True,
                "is_substantially_different": True,
                "change_strategy": "changed_perspective",
                "front_visual_mode": "replace",
                "variant_is_self_contained_without_front_visual": True,
                "core_aspect": "Potenzreihenentwicklung und Gültigkeitsbereich von ln(1+x)",
                "variants": [
                    "Gib die Potenzreihenentwicklung von ln(1+x) einschließlich ihres Gültigkeitsbereichs an."
                ],
                "warnings": [],
                "unsupported_reason": "",
            },
            "[image]",
            "[image]",
            1,
            front_image_present=True,
        )

        self.assertEqual(parsed["front_visual_mode"], "replace")
        self.assertEqual(len(parsed["variants"]), 1)

    def test_hidden_front_visual_must_not_be_referenced_by_replacement(self) -> None:
        with self.assertRaises(UnsupportedCardError):
            parse_generation(
                {
                    "status": "ok",
                    "is_equivalent": True,
                    "answer_not_revealed": True,
                    "is_substantially_different": True,
                    "change_strategy": "completion_prompt",
                    "front_visual_mode": "replace",
                    "variant_is_self_contained_without_front_visual": True,
                    "core_aspect": "Potenzreihenentwicklung von ln(1+x)",
                    "variants": ["Vervollständige die oben gezeigte Formel."],
                    "warnings": [],
                    "unsupported_reason": "",
                },
                "[image]",
                "[image]",
                1,
                front_image_present=True,
            )

    def test_front_visual_can_never_be_kept_beside_a_generated_question(self) -> None:
        with self.assertRaises(GenerationParseError):
            parse_generation(
                {
                    "status": "ok",
                    "is_equivalent": True,
                    "answer_not_revealed": True,
                    "is_substantially_different": True,
                    "change_strategy": "changed_perspective",
                    "front_visual_mode": "keep",
                    "variant_is_self_contained_without_front_visual": False,
                    "core_aspect": "Name der markierten Struktur",
                    "variants": ["Welche Struktur markiert der Pfeil?"],
                    "warnings": [],
                    "unsupported_reason": "",
                },
                "[image]",
                "Die Mitralklappe.",
                1,
                front_image_present=True,
            )

    def test_embedded_json_is_supported_but_html_is_kept_as_plain_text(self) -> None:
        value = {
            "status": "ok",
            "core_aspect": "Das Ergebnis der Multiplikation zwei mal drei",
            "is_equivalent": True,
            "answer_not_revealed": True,
            "is_substantially_different": True,
            "change_strategy": "completion_prompt",
            "variants": [
                "<script>x</script> Vervollständige die Rechnung: 2 × 3 = ____."
            ],
            "warnings": [],
            "unsupported_reason": "",
        }
        parsed = parse_generation(
            "result: " + json.dumps(value, ensure_ascii=False),
            "Welche Zahl ergibt sich aus zwei mal drei?",
            "Sechs.",
            1,
        )
        rendered = render_question(
            parsed["variants"][0],
            "<b>Welche Zahl ergibt sich aus zwei mal drei?</b>",
        )
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", rendered)
        self.assertNotIn("<script>x</script>", rendered)

    def test_unsupported_status_is_explicit(self) -> None:
        with self.assertRaises(UnsupportedCardError):
            parse_generation(
                {"status":"unsupported","core_aspect":"","variants":[],"warnings":[],"unsupported_reason":"Bildabhängig"},
                "?", "!", 3,
            )

    def test_empty_output_fails(self) -> None:
        with self.assertRaises(GenerationParseError):
            parse_generation("", "?", "!", 3)

    def test_equivalence_confirmation_is_required(self) -> None:
        base = {
            "status": "ok",
            "core_aspect": "Kern",
            "answer_not_revealed": True,
            "is_substantially_different": True,
            "change_strategy": "completion_prompt",
            "variants": [
                "Vervollständige die Rechnung mit dem gesuchten Ergebnis: 2 × 3 = ____."
            ],
            "warnings": [],
            "unsupported_reason": "",
        }
        with self.assertRaises(GenerationParseError):
            parse_generation(
                base,
                "Welche Zahl ergibt sich aus zwei mal drei?",
                "Sechs.",
                1,
            )
        with self.assertRaises(UnsupportedCardError):
            parse_generation(
                {**base, "is_equivalent": False},
                "Welche Zahl ergibt sich aus zwei mal drei?",
                "Sechs.",
                1,
            )


class FailureLocalizationTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_ui_language("en")

    def test_parser_failures_follow_each_supported_ui_language(self) -> None:
        for language in ("en", "de", "es", "fr", "ru"):
            with self.subTest(language=language):
                set_ui_language(language)
                with self.assertRaises(GenerationParseError) as raised:
                    parse_generation("", "Question?", "Answer", 1)
                self.assertEqual(str(raised.exception), tr("parse.empty_response"))

    def test_model_supplied_card_reason_is_not_translated(self) -> None:
        set_ui_language("fr")
        model_reason = "La imagen es necesaria para identificar la estructura."
        with self.assertRaises(UnsupportedCardError) as raised:
            parse_generation(
                {
                    "status": "unsupported",
                    "unsupported_reason": model_reason,
                },
                "Question?",
                "Answer",
                1,
            )
        self.assertEqual(str(raised.exception), model_reason)

    def test_local_parser_warning_follows_ui_language(self) -> None:
        set_ui_language("es")
        variant = (
            "Vervollständige die Lernantwort mit genau drei Punkten: "
            "Sekundäre Hypertonie kann verursacht werden durch 1. ___, 2. ___, 3. ___."
        )
        parsed = parse_generation(
            {
                "status": "ok",
                "is_equivalent": True,
                "answer_not_revealed": True,
                "is_substantially_different": True,
                "change_strategy": "completion_prompt",
                "core_aspect": "Drei Ursachen der sekundären Hypertonie",
                "variants": [variant],
                "warnings": [],
            },
            "Nenne drei Ursachen der sekundären Hypertonie.",
            "Nierenerkrankungen, endokrine Störungen und Medikamente.",
            2,
        )
        self.assertIn(
            tr("parse.partial_variants", actual=1, requested=2),
            parsed["warnings"],
        )

    def test_snapshot_failure_follows_ui_language(self) -> None:
        set_ui_language("ru")
        card = _SnapshotCard("", "Ответ")
        collection = _SnapshotCollection(
            card,
            _SnapshotMedia(Path.cwd(), []),
        )
        snapshot = snapshot_card(collection, card.id)
        self.assertEqual(snapshot.unsupported_reason, tr("failure.front_no_text"))

    def test_provider_failure_uses_short_localized_reason(self) -> None:
        set_ui_language("fr")
        snapshot = CardSnapshot(
            1,
            101,
            "Question?",
            "Answer",
            "Question?",
            "Answer",
            source_hash("Question?\0Answer"),
        )
        settings = ProviderSettings("openai", "model", "secret")
        error = ProviderError(
            ErrorKind.AUTH,
            "openai",
            "raw provider message that must not be shown",
        )
        with mock.patch(
            "fragevariator.anki_bridge.generate_json",
            side_effect=error,
        ):
            result = generate_batch([snapshot], settings, 1)
        self.assertEqual(result.failures[0].reason, tr("provider_error.auth"))
        self.assertNotIn("raw provider", result.failures[0].reason)


class MultilingualAnswerLeakTests(unittest.TestCase):
    def test_function_words_do_not_create_false_answer_leaks(self) -> None:
        cases = (
            (
                "¿Cuál es la capital de Francia?",
                "París está en Francia durante el verano.",
                "Durante el ejercicio, la capital está en Francia: ____.",
            ),
            (
                "Quelle ville est la capitale de la France ?",
                "Paris est pourtant en France pendant ce temps.",
                "Pendant ce temps, indique la capitale pourtant située en France : ____.",
            ),
            (
                "Какой город подходит под описание столицы России?",
                "Это Москва, которая также подходит под это описание.",
                "Дополните: столица, которая также подходит под описание, — ____.",
            ),
        )
        for original, answer, candidate in cases:
            with self.subTest(answer=answer):
                self.assertFalse(
                    _candidate_leaks_answer(original, answer, candidate)
                )

    def test_answer_terms_are_still_detected_in_each_card_language(self) -> None:
        cases = (
            ("¿Cuál es la capital de España?", "Madrid", "La capital es Madrid."),
            ("Quelle est la capitale de la France ?", "Paris", "La capitale est Paris."),
            ("Назовите столицу России.", "Москва", "Столица России — Москва."),
        )
        for original, answer, candidate in cases:
            with self.subTest(answer=answer):
                self.assertTrue(
                    _candidate_leaks_answer(original, answer, candidate)
                )


class ParserValidationTests(unittest.TestCase):

    def test_structural_distance_confirmation_is_required_and_boolean(self) -> None:
        base = {
            "status": "ok",
            "core_aspect": "Das Ergebnis der Multiplikation zwei mal drei",
            "is_equivalent": True,
            "answer_not_revealed": True,
            "change_strategy": "completion_prompt",
            "variants": [
                "Vervollständige die Rechnung mit dem gesuchten Ergebnis: 2 × 3 = ____."
            ],
            "warnings": [],
            "unsupported_reason": "",
        }
        original = "Welche Zahl ergibt sich aus zwei mal drei?"

        with self.assertRaises(GenerationParseError):
            parse_generation(base, original, "Sechs.", 1)
        with self.assertRaises(GenerationParseError):
            parse_generation(
                {**base, "is_substantially_different": 1},
                original,
                "Sechs.",
                1,
            )
        with self.assertRaises(UnsupportedCardError):
            parse_generation(
                {**base, "is_substantially_different": False},
                original,
                "Sechs.",
                1,
            )
        with self.assertRaises(GenerationParseError):
            parse_generation(
                {
                    **base,
                    "is_substantially_different": True,
                    "change_strategy": "none",
                },
                original,
                "Sechs.",
                1,
            )

    def test_model_claim_cannot_bypass_local_near_duplicate_gate(self) -> None:
        with self.assertRaises(UnsupportedCardError):
            parse_generation(
                {
                    "status": "ok",
                    "core_aspect": "Drei Ursachen der sekundären Hypertonie",
                    "is_equivalent": True,
                    "answer_not_revealed": True,
                    "is_substantially_different": True,
                    "change_strategy": "other",
                    "variants": [
                        "Welche drei Ursachen der sekundären Hypertonie kannst du nennen?"
                    ],
                    "warnings": [],
                    "unsupported_reason": "",
                },
                "Nenne drei Ursachen der sekundären Hypertonie.",
                "Zum Beispiel Nierenerkrankungen, endokrine Störungen und Medikamente.",
                1,
            )

    def test_parser_applies_selected_rewrite_intensity(self) -> None:
        original = "Welche Funktion erfüllt die Niere im Körper?"
        candidate = "Welche Aufgabe erfüllt die Niere im Körper?"
        response = {
            "status": "ok",
            "core_aspect": "Die Funktion der Niere im Körper",
            "is_equivalent": True,
            "answer_not_revealed": True,
            "is_substantially_different": True,
            "change_strategy": "other",
            "variants": [candidate],
            "warnings": [],
            "unsupported_reason": "",
        }

        parsed = parse_generation(
            response,
            original,
            "Sie filtert das Blut.",
            1,
            intensity="near",
        )
        self.assertEqual(parsed["variants"], [candidate])

        with self.assertRaises(UnsupportedCardError):
            parse_generation(response, original, "Sie filtert das Blut.", 1)
        with self.assertRaises(UnsupportedCardError):
            parse_generation(
                response,
                original,
                "Sie filtert das Blut.",
                1,
                intensity="distinct",
            )

    def test_structurally_new_completion_prompt_is_accepted(self) -> None:
        candidate = (
            "Vervollständige den physiologischen Zusammenhang: "
            "Die Mitralklappe sorgt dafür, dass ____."
        )
        parsed = parse_generation(
            {
                "status": "ok",
                "core_aspect": "Die Funktion der Mitralklappe im Herzen",
                "is_equivalent": True,
                "answer_not_revealed": True,
                "is_substantially_different": True,
                "change_strategy": "completion_prompt",
                "variants": [candidate],
                "warnings": [],
                "unsupported_reason": "",
            },
            "Welche Funktion erfüllt die Mitralklappe im Herzen?",
            (
                "Sie verhindert während der Systole den Rückfluss aus der linken "
                "Herzkammer in den linken Vorhof."
            ),
            1,
        )

        self.assertEqual(parsed["variants"], [candidate])

    def test_answer_leak_confirmation_and_local_gate_are_required(self) -> None:
        base = {
            "status": "ok",
            "core_aspect": "Die Funktionen der Niere",
            "is_equivalent": True,
            "is_substantially_different": True,
            "change_strategy": "completion_prompt",
            "variants": ["Vervollständige die Zuordnung: Niere → ____."],
            "warnings": [],
            "unsupported_reason": "",
        }
        original = "Welche Funktion erfüllt die Niere im Körper?"
        answer = (
            "Die Niere filtert das Blut, reguliert Wasser und Elektrolyte "
            "und scheidet Abfallstoffe aus."
        )
        with self.assertRaises(GenerationParseError):
            parse_generation(base, original, answer, 1)
        with self.assertRaises(UnsupportedCardError):
            parse_generation({**base, "answer_not_revealed": False}, original, answer, 1)
        with self.assertRaises(UnsupportedCardError):
            parse_generation(
                {
                    **base,
                    "answer_not_revealed": True,
                    "variants": [
                        "Die Niere filtert Blut und reguliert Wasser. Welche weitere Aufgabe fehlt?"
                    ],
                },
                original,
                answer,
                1,
            )


class RenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        # Existing fixtures are German; production selects this from Anki.
        set_ui_language("de")

    def tearDown(self) -> None:
        set_ui_language("en")

    def test_safe_original_fragment_keeps_only_passive_visible_markup(self) -> None:
        fragment = safe_original_fragment(
            '<p dir="rtl" class="card" onclick="danger()">'
            "<strong>Fett</strong> und <em>kursiv</em>"
            '<img src="capture.png" alt="Lokal" onerror="danger()">'
            '<img src="https://example.test/image.png" alt="Extern">'
            '<img src="javascript:danger()" alt="Unsicher">'
            "</p>"
            "<script>script secret</script>"
            "<div hidden>hidden secret</div>"
            "<div inert>inert secret</div>"
            '<div aria-hidden="true">aria secret</div>'
            '<div style="display:none">display secret</div>'
            '<div style="visibility:hidden">visibility secret</div>'
            "<noscript>noscript secret</noscript>"
            "<template>template secret</template>"
        )

        self.assertIn('<p dir="rtl">', fragment)
        self.assertIn("<strong>Fett</strong> und <em>kursiv</em>", fragment)
        self.assertIn('<img src="capture.png" alt="Lokal">', fragment)
        self.assertIn(
            '<img src="https://example.test/image.png" alt="Extern">', fragment
        )
        for forbidden in (
            "class=",
            "onclick",
            "onerror",
            "javascript:",
            "script secret",
            "hidden secret",
            "inert secret",
            "aria secret",
            "display secret",
            "visibility secret",
            "noscript secret",
            "template secret",
        ):
            self.assertNotIn(forbidden, fragment)

    def test_safe_original_fragment_omits_template_css_hidden_subtrees(self) -> None:
        fragment = safe_original_fragment(
            "<style>"
            ".hidden{display:none}"
            "#collapsed{visibility:collapse}"
            ".transparent{opacity:0}"
            "</style>"
            "<div>Question?</div>"
            '<div class="hidden">SECRET CLASS <span>SECRET DESCENDANT</span></div>'
            '<div id="collapsed">SECRET ID</div>'
            '<div class="transparent">SECRET OPACITY</div>'
        )

        self.assertEqual(fragment, "<div>Question?</div>")
        self.assertNotIn("SECRET", fragment)
        self.assertNotIn("<style>", fragment)
        self.assertNotIn("class=", fragment)
        self.assertNotIn("id=", fragment)

    def test_safe_original_fragment_honours_css_cascade_before_stripping_classes(
        self,
    ) -> None:
        fragment = safe_original_fragment(
            "<style>"
            ".restored{display:none}.restored{display:block}"
            "#revealed{visibility:hidden}#revealed{visibility:visible}"
            ".still-hidden{display:block}.still-hidden{display:none}"
            "</style>"
            '<div class="restored">Visible class content</div>'
            '<div id="revealed">Visible id content</div>'
            '<div class="still-hidden">SECRET CASCADE</div>'
        )

        self.assertIn("<div>Visible class content</div>", fragment)
        self.assertIn("<div>Visible id content</div>", fragment)
        self.assertNotIn("SECRET CASCADE", fragment)
        self.assertNotIn("class=", fragment)
        self.assertNotIn("id=", fragment)

    def test_invalid_css_cannot_reveal_content_hidden_by_valid_rules(self) -> None:
        fragment = safe_original_fragment(
            "<style>"
            ".bad-display{display:none}.bad-display{display:not-a-display}"
            ".duplicate{display:none}.duplicate{display:block block!important}"
            ".mixed{display:none}.mixed{display:flex grid!important}"
            ".bad-visibility{visibility:hidden}"
            ".bad-visibility{visibility:banana!important}"
            ".bad-opacity{opacity:0}.bad-opacity{opacity:opaque!important}"
            "</style>"
            "<div>Visible question?</div>"
            '<div class="bad-display">SECRET DISPLAY</div>'
            '<div class="duplicate">SECRET DUPLICATE</div>'
            '<div class="mixed">SECRET MIXED</div>'
            '<div class="bad-visibility">SECRET VISIBILITY</div>'
            '<div class="bad-opacity">SECRET OPACITY</div>'
        )

        self.assertEqual(fragment, "<div>Visible question?</div>")
        self.assertNotIn("SECRET", fragment)

    def test_original_table_keeps_caption_and_safe_cell_spans(self) -> None:
        fragment = safe_original_fragment(
            "<table><caption>Original table question?</caption>"
            '<thead><tr><th colspan="2">Heading</th></tr></thead>'
            '<tbody><tr><td rowspan="2">A</td><td>B</td></tr></tbody>'
            "</table>"
        )

        self.assertIn(
            "<table><caption>Original table question?</caption>", fragment
        )
        self.assertIn('<th colspan="2">Heading</th>', fragment)
        self.assertIn('<td rowspan="2">A</td>', fragment)

    def test_safe_original_fragment_hides_terminal_targets_of_static_selectors(
        self,
    ) -> None:
        fragment = safe_original_fragment(
            "<style>"
            ".card .hidden{display:none}"
            ".hidden{display:block}"
            ".other .hidden{display:block}"
            "body > #child{visibility:hidden}"
            ".card div.tag-hidden{display:none}"
            ".card .paired-hidden.answer{visibility:hidden}"
            "body > div#compound-child{opacity:0}"
            "body > div#wrong-tag{display:none}"
            ".card .inline-restored{display:none}"
            ".card .forced{display:none!important}"
            "</style>"
            '<div class="hidden">SECRET DESCENDANT</div>'
            '<div id="child">SECRET CHILD</div>'
            '<div class="tag-hidden">SECRET TAG TARGET</div>'
            '<span class="tag-hidden">Visible tag mismatch</span>'
            '<div class="paired-hidden answer">SECRET CLASS TARGET</div>'
            '<div class="paired-hidden">Visible class mismatch</div>'
            '<div id="compound-child">SECRET ID TARGET</div>'
            '<span id="wrong-tag">Visible ID tag mismatch</span>'
            '<div class="inline-restored" style="display:block">'
            "Visible inline content</div>"
            '<div class="forced" style="display:block">SECRET IMPORTANT</div>'
        )

        self.assertEqual(
            fragment,
            "<span>Visible tag mismatch</span>"
            "<div>Visible class mismatch</div>"
            "<span>Visible ID tag mismatch</span>"
            "<div>Visible inline content</div>",
        )
        self.assertNotIn("SECRET", fragment)

    def test_safe_original_fragment_preserves_closed_and_open_details_state(self) -> None:
        fragment = safe_original_fragment(
            '<details class="hint" onclick="danger()">'
            "<summary>Hint</summary>SECRET CLOSED</details>"
            '<details open="false" class="solution">'
            "<summary>Shown</summary>OPEN CONTENT</details>"
        )

        self.assertIn(
            "<details><summary>Hint</summary>SECRET CLOSED</details>",
            fragment,
        )
        self.assertIn(
            "<details open><summary>Shown</summary>OPEN CONTENT</details>",
            fragment,
        )
        self.assertEqual(fragment.count("<details open>"), 1)
        self.assertNotIn("class=", fragment)
        self.assertNotIn("onclick", fragment)

    def test_initially_visible_fragment_exposes_only_first_closed_summary(self) -> None:
        closed = safe_initially_visible_fragment(
            "<details>"
            "<summary><b>Visible summary</b></summary>"
            "SECRET BODY<img src=\"secret.png\">"
            "<summary>SECRET SECOND SUMMARY</summary>"
            "</details>"
        )
        opened = safe_initially_visible_fragment(
            "<details open><summary>Visible summary</summary>"
            "OPEN BODY<img src=\"open.png\"></details>"
        )

        self.assertEqual(
            closed,
            "<details><summary><b>Visible summary</b></summary></details>",
        )
        self.assertNotIn("SECRET", closed)
        self.assertNotIn("secret.png", closed)
        self.assertIn("<details open>", opened)
        self.assertIn("OPEN BODY", opened)
        self.assertIn('src="open.png"', opened)

    def test_safe_original_fragment_fails_closed_on_malformed_parser_state(self) -> None:
        with mock.patch(
            "fragevariator.core.render._SafeOriginalParser.feed",
            side_effect=RuntimeError("broken card markup"),
        ):
            fragment = safe_original_fragment(
                "Question?<span class='hidden'>SECRET ANSWER</span>"
            )

        self.assertEqual(fragment, "")

        with mock.patch(
            "fragevariator.core.render._SafeOriginalParser.feed",
            side_effect=RuntimeError("broken initial visibility"),
        ):
            initially_visible = safe_initially_visible_fragment(
                "Question?<details>SECRET ANSWER</details>"
            )

        self.assertEqual(initially_visible, "")

    def test_safe_original_fragment_balances_malformed_but_passive_markup(self) -> None:
        self.assertEqual(
            safe_original_fragment("</div><p>Original?</p>"),
            "<p>Original?</p>",
        )
        table = safe_original_fragment(
            "<table><tbody><tr><td>Original table question?"
        )
        self.assertEqual(
            table,
            "<table><tbody><tr><td>Original table question?</td></tr></tbody></table>",
        )

    def test_mismatched_closing_tag_cannot_escape_a_hidden_subtree(self) -> None:
        source = (
            '<div style="display:none"><span>HIDDEN</span></p>'
            '<img src="secret.png"><span>SECRET TOKEN</span></div>'
            "<p>Visible?</p>"
        )

        fragment = safe_original_fragment(source)
        rendered = render_question(
            "Generated?",
            source,
            original_fragment="",
        )

        self.assertEqual(fragment, "<p>Visible?</p>")
        self.assertNotIn("secret.png", rendered)

    def test_question_is_plain_and_does_not_include_original_card_ui(self) -> None:
        rendered = render_question(
            "A < B?",
            "<script>danger()</script><b>Original</b>",
            original_fragment="",
        )
        self.assertIn("A &lt; B?", rendered)
        self.assertNotIn("Original", rendered)
        self.assertNotIn("Neu formuliert", rendered)
        self.assertNotIn("Originalfrage anzeigen", rendered)
        self.assertNotIn("<details", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<b>Original</b>", rendered)

    def test_front_original_is_hidden_top_level_context_after_the_question(self) -> None:
        original = safe_original_fragment(
            '<div class="prompt"><b onclick="danger()">Original?</b>'
            '<img src="capture.png" onerror="danger()"></div>'
        )
        rendered = render_question(
            "Andere Frage?",
            '<div class="prompt">Original?</div>',
            original_fragment=original,
            front_card_id=123,
        )

        question_end = rendered.index("Andere Frage?</div>")
        context_start = rendered.index(
            '<section class="fv-answer-original" '
            'data-fv-original-front="123" hidden aria-hidden="true" '
            'style="display:none!important;position:static!important',
        )
        self.assertLess(question_end, context_start)
        self.assertIn(
            '.fv-answer-original[data-fv-original-front][hidden]'
            "{display:none!important}",
            rendered,
        )
        self.assertIn('class="fv-answer-label"', rendered)
        self.assertIn('class="fv-answer-question"', rendered)
        self.assertIn("<b style=", rendered)
        self.assertIn(">Original?</b>", rendered)
        self.assertIn('src="capture.png" alt=""', rendered)
        self.assertNotIn("onclick", rendered)
        self.assertNotIn("onerror", rendered)
        self.assertNotIn("position:fixed", rendered)

    def test_photo_front_is_hidden_until_original_is_revealed(self) -> None:
        source = (
            '<img src="satz-4-28.jpg"><br>'
            "Was gilt laut diesem Satz, wenn K kompakt ist?"
        )
        original = safe_original_fragment(source)

        rendered = render_question(
            "Welche Eigenschaft besitzt f(K) für kompaktes K?",
            source,
            original_fragment=original,
            front_card_id=1764065119690,
        )

        self.assertEqual(rendered.count('src="satz-4-28.jpg"'), 1)
        visible, hidden_original = rendered.split(
            '<section class="fv-answer-original"', 1
        )
        self.assertNotIn("satz-4-28.jpg", visible)
        self.assertIn("satz-4-28.jpg", hidden_original)
        self.assertIn("Was gilt laut diesem Satz", hidden_original)
        self.assertTrue(original_context_available(original))

    def test_image_only_front_is_hidden_but_has_original_disclosure(self) -> None:
        source = '<img src="visual-question.jpg" alt="Diagramm">'
        original = safe_original_fragment(source)

        rendered = render_question(
            "Welche Struktur verbindet den linken Vorhof mit der linken Herzkammer?",
            source,
            original_fragment=original,
            front_card_id=42,
        )

        self.assertEqual(rendered.count('src="visual-question.jpg"'), 1)
        visible, hidden_original = rendered.split(
            '<section class="fv-answer-original"', 1
        )
        self.assertNotIn("visual-question.jpg", visible)
        self.assertIn("visual-question.jpg", hidden_original)
        self.assertTrue(original_context_available(original))

    def test_front_original_stays_top_level_for_table_question_shells(self) -> None:
        rendered = render_question(
            "Andere Tabellenfrage?",
            "<table><tr><td>Sehr lange Originalfrage?</td></tr></table>",
            original_fragment="<p>Originalfrage?</p>",
            front_card_id=456,
        )

        self.assertIn(
            "Andere Tabellenfrage?</td></tr></table>"
            '<section class="fv-answer-original" '
            'data-fv-original-front="456" hidden',
            rendered,
        )

    def test_caption_question_and_original_context_remain_valid_siblings(self) -> None:
        rendered = render_question(
            "Welche Tabellenüberschrift passt?",
            (
                "<table><caption>Welche sehr ausführliche Überschrift gehört "
                "zu dieser Tabelle?</caption><tbody><tr><td>A</td></tr></tbody></table>"
            ),
            original_fragment=(
                "<table><caption>Original table question?</caption>"
                '<tbody><tr><td colspan="2">A</td></tr></tbody></table>'
            ),
            front_card_id=654,
        )

        self.assertIn(
            "Welche Tabellenüberschrift passt?</caption></table>"
            '<section class="fv-answer-original" '
            'data-fv-original-front="654" hidden',
            rendered,
        )
        self.assertIn("<caption style=", rendered)
        self.assertIn(">Original table question?</caption>", rendered)
        self.assertIn('colspan="2">A</td>', rendered)

    def test_template_css_cannot_turn_original_context_into_fixed_overlay(self) -> None:
        rendered = render_question(
            "Neue Frage?",
            (
                "<style>.prompt + section{position:fixed!important;"
                "bottom:0!important;right:0!important;transform:scale(.5)!important}"
                "</style><div class=prompt>Original?</div>"
            ),
            original_fragment="<div>Original?</div>",
            front_card_id=321,
        )

        context = rendered[rendered.index('<section class="fv-answer-original"'):]
        self.assertIn("position:static!important", context)
        self.assertIn("inset:auto!important", context)
        self.assertIn("transform:none!important", context)
        self.assertIn("float:none!important", context)
        self.assertIn("display:none!important", context)

    def test_generic_template_rules_cannot_move_or_shrink_context_children(self) -> None:
        rendered = render_question(
            "Neue Frage?",
            (
                "<style>div{position:fixed!important;bottom:0!important;"
                "font-size:8px!important;transform:scale(.2)!important}</style>"
                "<div>Original?</div>"
            ),
            original_fragment="<div><span>Original?</span></div>",
            front_card_id=322,
        )

        context = rendered[rendered.index('<section class="fv-answer-original"'):]
        self.assertIn('<div style="display:block!important;position:static!important;', context)
        self.assertIn('<span style="display:inline!important;position:static!important;', context)
        self.assertIn("font-size:inherit!important", context)
        self.assertNotIn("position:fixed", rendered)
        self.assertNotIn("font-size:8px", rendered)
        self.assertNotIn("scale(.2)", rendered)

    def test_deep_table_question_uses_neutral_shell_before_inline_context(self) -> None:
        deep_question = (
            '<div class="banner">Kapitel 3</div>'
            "<table><tbody><tr><td>"
            + "<div>" * 10
            + "Welche sehr lange Erklärung gehört zu diesem Sachverhalt?"
            + "</div>" * 10
            + "</td></tr></tbody></table>"
        )
        rendered = render_question(
            "Welche Alternative erklärt den Sachverhalt?",
            deep_question,
            original_fragment="<p>Originalfrage?</p>",
            front_card_id=789,
        )

        self.assertIn('<div data-fv-question="1" style="display:block!important;', rendered)
        self.assertIn(
            'font-size:inherit!important">Welche Alternative erklärt den '
            'Sachverhalt?</div><section class="fv-answer-original" '
            'data-fv-original-front="789" hidden',
            rendered,
        )
        self.assertNotIn('<tr data-fv-question="1">', rendered)
        self.assertNotIn('class="banner" data-fv-question="1"', rendered)

    def test_question_preserves_leading_template_css_and_presentation_shell(self) -> None:
        rendered = render_question(
            "Welche Beziehung gilt?",
            (
                "<style>.card {font-size: 34px; text-align: center}"
                ".prompt {font-weight: 600}</style>"
                '<div class="front prompt" style="line-height:1.4; position:fixed; '
                'background-image:url(https://example.test/x)">'
                '<span dir="rtl">Lange ursprüngliche Frage?</span></div>'
            ),
            original_fragment="",
        )

        self.assertIn(".card{font-size:34px;text-align:center}", rendered)
        self.assertIn('class="front prompt"', rendered)
        self.assertIn('data-fv-question="1"', rendered)
        self.assertIn(
            'style="line-height:1.4;display:block!important;'
            'position:static!important;',
            rendered,
        )
        self.assertIn(
            '<span dir="rtl" style="display:inline!important;'
            'position:static!important;inset:auto!important;',
            rendered,
        )
        self.assertIn("Welche Beziehung gilt?</span>", rendered)
        self.assertNotIn("Lange ursprüngliche Frage?", rendered)
        self.assertNotIn("position:fixed", rendered)
        self.assertNotIn("background-image", rendered)

    def test_risky_prompt_class_cannot_pin_or_shrink_generated_question(self) -> None:
        rendered = render_question(
            "Natürlich platzierte Alternative?",
            (
                "<style>"
                ".card{font-size:30px}"
                ".prompt{position:fixed;top:0;right:0;"
                "transform:translateX(20px);font-size:8px}"
                "</style>"
                '<div class="prompt">Original question?</div>'
            ),
            original_fragment="",
        )

        self.assertIn('<div class="prompt" data-fv-question="1"', rendered)
        self.assertNotIn("position:fixed", rendered)
        self.assertNotIn("font-size:8px", rendered)
        self.assertNotIn("translateX", rendered)
        self.assertIn(".card{font-size:30px}", rendered)

    def test_unsafe_compound_selector_does_not_remove_unmatched_safe_class(self) -> None:
        rendered = render_question(
            "Alternative?",
            (
                "<style>"
                ".prompt{font-size:8px}"
                ".prompt{font-size:30px;color:red}"
                ".prompt.small{font-size:8px}"
                "h1.prompt{position:fixed}"
                "</style>"
                '<div class="prompt">Original question?</div>'
            ),
            original_fragment="",
        )

        self.assertIn('class="prompt" data-fv-question="1"', rendered)
        self.assertNotIn("font-size:inherit!important", rendered)

        invalid_override = render_question(
            "Alternative?",
            (
                "<style>.prompt{font-size:8px}"
                ".prompt{font-size:1;color:red}</style>"
                '<div class="prompt">Original question?</div>'
            ),
            original_fragment="",
        )
        self.assertIn('class="prompt" data-fv-question="1"', invalid_override)
        self.assertNotIn("font-size:8px", invalid_override)
        self.assertNotIn("font-size:1", invalid_override)

    def test_font_shorthand_and_legacy_font_size_cannot_make_prompt_tiny(self) -> None:
        class_shorthand = render_question(
            "Alternative?",
            (
                "<style>.prompt{font:8px Arial;color:red}</style>"
                '<div class="prompt">Original question?</div>'
            ),
            original_fragment="",
        )
        self.assertIn('class="prompt" data-fv-question="1"', class_shorthand)
        self.assertNotIn("font:8px", class_shorthand)

        safe_override = render_question(
            "Alternative?",
            (
                "<style>.prompt{font:8px Arial}"
                ".prompt{font:30px Arial;color:red}</style>"
                '<div class="prompt">Original question?</div>'
            ),
            original_fragment="",
        )
        self.assertIn('class="prompt" data-fv-question="1"', safe_override)

        inline_shorthand = render_question(
            "Alternative?",
            '<div style="font:8px Arial;color:red">Original question?</div>',
            original_fragment="",
        )
        self.assertNotIn("font:8px", inline_shorthand)
        self.assertIn("color:red", inline_shorthand)
        self.assertIn("font-size:inherit!important", inline_shorthand)

        legacy_font = render_question(
            "Alternative?",
            '<font size="1" color="red" face="Arial">Original question?</font>',
            original_fragment="",
        )
        self.assertNotIn('size="1"', legacy_font)
        self.assertIn('color="red"', legacy_font)
        self.assertIn('face="Arial"', legacy_font)

    def test_question_copies_only_styles_before_the_card_content(self) -> None:
        rendered = render_question(
            "Sichere Variante?",
            (
                "<style>.card{font-size:30px}</style>"
                '<div class="prompt">Original?</div>'
                "<style>.prompt:after{content:'Original?';}</style>"
                "<script>danger()</script>"
            ),
            original_fragment="",
        )

        self.assertIn(".card{font-size:30px}", rendered)
        self.assertNotIn("content:'Original?'", rendered)
        self.assertNotIn("Original?", rendered)
        self.assertNotIn("danger()", rendered)

    def test_question_shell_ignores_elements_hidden_by_simple_template_css(self) -> None:
        rendered = render_question(
            "Welche Aussage ist korrekt?",
            (
                "<style>"
                ".hidden{display: none}"
                "#collapsed{visibility:collapse}"
                ".transparent{opacity:0}"
                ".shown{opacity:1}"
                "</style>"
                '<div class="hidden">Sehr lange verborgene Frage Nummer eins?</div>'
                '<div id="collapsed">Sehr lange verborgene Frage Nummer zwei?</div>'
                '<div class="transparent">Sehr lange verborgene Frage Nummer drei?</div>'
                '<div class="shown">Sichtbare Frage?</div>'
            ),
            original_fragment="",
        )

        self.assertIn('class="shown" data-fv-question="1"', rendered)
        self.assertNotIn('class="hidden" data-fv-question="1"', rendered)
        self.assertNotIn('id="collapsed" data-fv-question="1"', rendered)
        self.assertNotIn('class="transparent" data-fv-question="1"', rendered)
        for original in ("Nummer eins", "Nummer zwei", "Nummer drei", "Sichtbare Frage"):
            self.assertNotIn(original, rendered)

    def test_question_shell_ignores_terminal_targets_of_static_selectors(self) -> None:
        rendered = render_question(
            "Welche Aussage ist korrekt?",
            (
                "<style>"
                ".card .hidden{display:none}"
                ".hidden{display:block}"
                ".other .hidden{display:block}"
                "body > #child{visibility:hidden}"
                ".card div.tag-hidden{display:none}"
                ".card .paired-hidden.answer{visibility:hidden}"
                "body > div#compound-child{opacity:0}"
                "</style>"
                '<div class="hidden">Sehr lange verborgene Nachfahrenfrage?</div>'
                '<div id="child">Sehr lange verborgene direkte Kindfrage?</div>'
                '<div class="tag-hidden">Sehr lange verborgene Tagfrage?</div>'
                '<div class="paired-hidden answer">'
                "Sehr lange verborgene Klassenfrage?</div>"
                '<div id="compound-child">Sehr lange verborgene ID-Frage?</div>'
                '<div class="shown">Sichtbare Frage?</div>'
            ),
            original_fragment="",
        )

        self.assertIn('class="shown" data-fv-question="1"', rendered)
        self.assertNotIn('class="hidden" data-fv-question="1"', rendered)
        self.assertNotIn('id="child" data-fv-question="1"', rendered)
        for original in (
            "Nachfahrenfrage", "Kindfrage", "Tagfrage", "Klassenfrage", "ID-Frage"
        ):
            self.assertNotIn(original, rendered)

    def test_conditional_css_is_omitted_while_safe_overrides_still_win(self) -> None:
        rendered = render_question(
            "Neue Frage?",
            (
                "<style>"
                ".hovered:hover{display:none}"
                "@media(max-width:500px){.responsive{display:none}}"
                ".restored{display:none}.restored{display:block}"
                ".inline-override{display:none}"
                "</style>"
                '<div class="hovered">Längste sichtbare Frage über Hover?</div>'
                '<div class="responsive">Responsive Frage?</div>'
                '<div class="restored">Wieder sichtbare Frage?</div>'
                '<div class="inline-override" style="display:block">Inline sichtbar?</div>'
            ),
            original_fragment="",
        )

        self.assertIn('class="restored" data-fv-question="1"', rendered)
        self.assertNotIn('class="hovered" data-fv-question="1"', rendered)
        self.assertNotIn('class="responsive" data-fv-question="1"', rendered)
        self.assertNotIn("@media", rendered)

    def test_conditional_or_unsupported_hidden_content_never_leaks_as_media(self) -> None:
        original = (
            "<style>"
            "@media screen{.answer{display:none}}"
            "@supports(display:grid){.support-secret{visibility:hidden}}"
            "[data-theme] .attribute-secret{opacity:0}"
            ":root .root-secret{font-size:0}"
            "</style>"
            '<div class="answer"><img src="solution.png">SECRET ANSWER</div>'
            '<div class="support-secret">SECRET SUPPORT</div>'
            '<div class="attribute-secret">SECRET ATTRIBUTE</div>'
            '<div class="root-secret">SECRET ROOT</div>'
            '<div class="visible">Visible original question?</div>'
        )

        rendered = render_question(
            "Safe generated question?",
            original,
            original_fragment="",
        )

        self.assertIn('class="visible" data-fv-question="1"', rendered)
        self.assertNotIn("solution.png", rendered)
        for secret in ("SECRET ANSWER", "SECRET SUPPORT", "SECRET ATTRIBUTE", "SECRET ROOT"):
            self.assertNotIn(secret, safe_original_fragment(original))
            self.assertNotIn(secret, safe_initially_visible_fragment(original))

    def test_simple_attribute_visibility_targets_only_the_matching_region(self) -> None:
        original = (
            "<style>[data-answer]{display:none}"
            '[data-exact="yes"]{visibility:hidden}</style>'
            '<img src="question.png" alt="Visible diagram">'
            '<div data-answer>SECRET ANSWER<img src="solution.png"></div>'
            '<div data-exact="yes">SECRET EXACT</div>'
            '<p data-exact="no">Visible original question?</p>'
        )

        fragment = safe_original_fragment(original)
        rendered = render_question(
            "Safe generated question?",
            original,
            original_fragment="",
        )

        self.assertIn("question.png", fragment)
        self.assertIn("Visible original question?", fragment)
        self.assertNotIn("SECRET", fragment)
        self.assertNotIn('src="question.png"', rendered)
        self.assertNotIn("solution.png", rendered)

    def test_is_where_and_positive_not_compounds_do_not_leak_hidden_regions(self) -> None:
        source = (
            "<style>"
            ".card :is(.answer,.solution){display:none}"
            ".card :where(.hint){visibility:hidden}"
            ".card :not(.visible).answer-two{opacity:0}"
            "</style>"
            "<p>Visible?</p>"
            '<div class="answer">SECRET IS</div>'
            '<div class="solution">SECRET SECOND IS</div>'
            '<div class="hint">SECRET WHERE</div>'
            '<div class="answer-two">SECRET NOT</div>'
        )

        fragment = safe_original_fragment(source)

        self.assertIn("Visible?", fragment)
        self.assertNotIn("SECRET", fragment)

    def test_outer_card_visibility_is_inherited_and_obeys_safe_override(self) -> None:
        hidden = (
            "<style>.card{color:transparent}</style>"
            '<div>SECRET OUTER<img src="solution.png"></div>'
        )
        restored = (
            "<style>.card{font-size:0}.card{font-size:16px}</style>"
            "<div>Visible outer question?</div>"
        )
        calculated = (
            "<style>:root{--fg:#222;--card-opacity:1;--display:block;"
            "--visibility:visible;--scale:1;--indent:0}"
            ".card{color:var(--fg);font-size:calc(16px + .2vw);"
            "max-width:calc(100% - 2rem);opacity:var(--card-opacity);"
            "display:var(--display);visibility:var(--visibility);"
            "scale:var(--scale);text-indent:var(--indent)}"
            ".prompt{width:calc(100% - 2rem);opacity:calc(1)}</style>"
            '<img src="question.png"><p class="prompt">'
            "Visible calculated question?</p>"
        )

        self.assertNotIn("SECRET", safe_original_fragment(hidden))
        self.assertNotIn("solution.png", safe_original_fragment(hidden))
        self.assertIn("Visible outer question?", safe_original_fragment(restored))
        self.assertIn("question.png", safe_original_fragment(calculated))
        self.assertIn("Visible calculated question?", safe_original_fragment(calculated))

    def test_additional_css_concealment_patterns_are_omitted(self) -> None:
        hidden_rules = (
            "content-visibility:hidden",
            "clip-path:inset(50%)",
            "clip:rect(0,0,0,0)",
            "width:0",
            "height:0px",
            "width:calc(100% - 100%)",
            "height:calc(10px - 10px)",
            "max-height:calc(100vh - 100vh)",
            "position:absolute;left:-9999px",
            "transform:scale(0)",
            "transform:translateX(-9999px)",
            "filter:opacity(0)",
            "opacity:calc(1 - 1)",
            "opacity:min(0,1)",
            "scale:calc(1 - 1)",
            "text-indent:calc(-9999px)",
            "font-size:calc(1em - 1em)",
            "font:calc(16px - 16px) Arial",
        )
        for declaration in hidden_rules:
            with self.subTest(declaration=declaration):
                source = (
                    "<style>.secret{%s}</style>"
                    '<div class="secret">SECRET<img src="solution.png"></div>'
                    "<p>Visible?</p>"
                    % declaration
                )
                fragment = safe_original_fragment(source)
                self.assertNotIn("SECRET", fragment)
                self.assertNotIn("solution.png", fragment)
                self.assertIn("Visible?", fragment)

    def test_visibility_styles_after_card_content_are_still_enforced(self) -> None:
        source = (
            '<div class="answer">SECRET LATE STYLE<img src="solution.png"></div>'
            "<style>.answer{display:none}</style>"
            "<p>Visible?</p>"
        )

        fragment = safe_original_fragment(source)
        initial = safe_initially_visible_fragment(source)
        rendered = render_question(
            "Generated?",
            source,
            original_fragment="",
        )

        self.assertIn("Visible?", fragment)
        self.assertNotIn("SECRET", fragment)
        self.assertNotIn("SECRET", initial)
        self.assertNotIn("solution.png", rendered)

    def test_font_visibility_keywords_and_shorthand_follow_one_cascade(self) -> None:
        visible_rules = (
            "font-size:inherit",
            "font-size:medium",
            "font-size:calc(1rem + 1vw)",
            "font:inherit",
            "font:caption",
            "font-size:0;font:16px Arial",
            "font:0 Arial;font-size:16px",
            "font-size:0;font-size:large",
            "text-indent:initial",
            "text-indent:revert",
        )
        for declarations in visible_rules:
            with self.subTest(declarations=declarations):
                source = (
                    "<style>.q{%s}</style><div class=q>Original?</div>"
                    % declarations
                )
                self.assertIn("Original?", safe_original_fragment(source))
                self.assertIn("Original?", safe_initially_visible_fragment(source))

    def test_effectively_invisible_text_is_omitted_from_safe_fragments(self) -> None:
        hidden_rules = (
            "font-size:0",
            "font:0 Arial",
            "color:transparent",
            "color:rgba(255,0,0,0)",
            "color:rgb(0 0 0 / 0)",
            "color:hsla(120,100%,50%,0)",
            "color:#ffffff00",
            "-webkit-text-fill-color:#abc0",
            "color:color-mix(in srgb,transparent 100%,red 0%)",
            "color:rgb(0 0 0 / calc(0))",
            "text-indent:-9999px",
            "text-indent:9999px",
        )
        for declaration in hidden_rules:
            with self.subTest(declaration=declaration):
                source = (
                    "<style>.secret{%s}</style>"
                    '<div class="secret">SECRET</div><div>Visible?</div>'
                    % declaration
                )
                self.assertNotIn("SECRET", safe_original_fragment(source))
                self.assertNotIn("SECRET", safe_initially_visible_fragment(source))

    def test_live_question_never_preserves_front_images(self) -> None:
        rendered = render_question(
            "Welche Struktur ist markiert?",
            (
                '<img src="diagram.png" alt="Diagramm">'
                '<img src="javascript:danger()" alt="Unsicher">'
                '<div hidden><img src="private.png" alt="Versteckt"></div>'
                "Geheime Originalfrage"
                "<script>danger()</script>"
            ),
            original_fragment="",
        )
        self.assertNotIn("diagram.png", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("private.png", rendered)
        self.assertNotIn("Geheime Originalfrage", rendered)
        self.assertNotIn("<script>", rendered)

    def test_closed_details_use_summary_shell_and_hide_body_media(self) -> None:
        rendered = render_question(
            "Neue sichtbare Frage?",
            (
                "<details><summary>"
                '<span class="summary-prompt">Kurze sichtbare Frage?</span>'
                '<img src="summary.png" />'
                "</summary>"
                '<div class="hidden-body">Sehr lange verborgene Körperfrage?</div>'
                '<img src="secret.png" />'
                "</details>"
            ),
            original_fragment="",
        )

        self.assertIn('class="summary-prompt" data-fv-question="1"', rendered)
        self.assertNotIn('src="summary.png"', rendered)
        self.assertNotIn("hidden-body", rendered)
        self.assertNotIn("secret.png", rendered)
        self.assertNotIn("<details", rendered)
        self.assertNotIn("<summary", rendered)

    def test_open_details_body_and_media_are_initially_visible(self) -> None:
        rendered = render_question(
            "Neue offene Frage?",
            (
                "<details open><summary>Hint</summary>"
                '<div class="open-body">Sehr lange sichtbare Körperfrage?</div>'
                '<img src="open.png" />'
                "</details>"
            ),
            original_fragment="",
        )

        self.assertIn('class="open-body" data-fv-question="1"', rendered)
        self.assertNotIn('src="open.png"', rendered)
        self.assertNotIn("<details", rendered)
        self.assertNotIn("<summary", rendered)

    def test_direct_summary_text_falls_back_without_disclosure_ui(self) -> None:
        rendered = render_question(
            "Neutrale Frage?",
            "<details><summary>Originalfrage?</summary>SECRET BODY</details>",
            original_fragment="",
        )

        self.assertIn(
            '<div data-fv-question="1" style="display:block!important;',
            rendered,
        )
        self.assertIn(
            'font-size:inherit!important">Neutrale Frage?</div>', rendered
        )
        self.assertNotIn("<details", rendered)
        self.assertNotIn("<summary", rendered)
        self.assertNotIn("SECRET BODY", rendered)

    def test_answer_context_always_shows_exactly_one_original(self) -> None:
        added = render_answer_context(
            "ANSWER", "Variante?", "Original?", False
        )
        self.assertEqual(added.count("Variante?"), 1)
        self.assertIn(">Originalfrage</div>", added)
        self.assertEqual(added.count("Original?"), 1)
        self.assertNotIn("Originalfrage anzeigen", added)
        self.assertNotIn("<details", added)
        self.assertLess(added.index("Variante?"), added.index("Original?"))
        self.assertLess(added.index("Original?"), added.index("ANSWER"))

        already_present = render_answer_context(
            "Original?<hr>ANSWER", "Variante?", "Original?", True
        )
        self.assertEqual(already_present.count("Original?"), 1)
        self.assertEqual(already_present.count("Variante?"), 1)
        self.assertLess(
            already_present.index("Variante?"),
            already_present.index("Original?"),
        )
        self.assertLess(
            already_present.index("Original?"),
            already_present.index("ANSWER"),
        )

    def test_standard_frontside_is_moved_between_new_question_and_answer(self) -> None:
        rendered = render_answer_context(
            '<style>.card{font-size:32px;text-align:center}</style>'
            '<div class="front">Original?</div><hr class="line" id="answer">'
            '<div class="answer">ANSWER</div>',
            "Variante?",
            '<div class="front">Original?</div>',
            True,
        )

        self.assertEqual(rendered.count("Original?"), 1)
        self.assertIn(".card{font-size:32px;text-align:center}", rendered)
        self.assertEqual(rendered.count('id="answer"'), 1)
        self.assertLess(
            rendered.index(".card{font-size:32px;text-align:center}"),
            rendered.index('id="answer"'),
        )
        self.assertEqual(rendered.count("Variante?"), 1)
        self.assertLess(
            rendered.index('id="answer"'), rendered.index("Variante?")
        )
        self.assertLess(rendered.index("Variante?"), rendered.index("Original?"))
        self.assertLess(rendered.index("Original?"), rendered.index("ANSWER"))

    def test_standard_media_answer_keeps_comparison_before_solution(self) -> None:
        rendered = render_answer_context(
            'Original?<hr id=answer><audio controls src="answer.mp3"></audio>',
            "Variante?",
            "Original?",
            True,
        )

        self.assertEqual(rendered.count("Original?"), 1)
        self.assertEqual(rendered.count("Variante?"), 1)
        self.assertLess(rendered.index("id=answer"), rendered.index("Variante?"))
        self.assertLess(rendered.index("Variante?"), rendered.index("Original?"))
        self.assertLess(rendered.index("Original?"), rendered.index("<audio"))

    def test_answer_redraw_never_duplicates_the_generated_prompt(self) -> None:
        rendered = render_answer_context(
            'Original?<hr id="answer"><div>ANSWER</div>',
            "Variante?",
            "Original?",
            True,
        )
        redrawn = render_answer_context(
            rendered,
            "Variante?",
            "Original?",
            True,
        )

        self.assertEqual(redrawn, rendered)
        self.assertEqual(redrawn.count('data-fv-answer-prompt="1"'), 1)
        self.assertEqual(redrawn.count("Variante?"), 1)

    def test_nested_answer_separator_keeps_markup_and_inserts_prompt(self) -> None:
        answer = (
            '<style>.card{font-size:30px}</style>'
            '<div class="frame">Original?'
            '<hr id="answer"><span>ANSWER</span></div>'
        )
        rendered = render_answer_context(
            answer,
            "Variante?",
            "Original?",
            True,
        )

        self.assertEqual(rendered.count("Original?"), 1)
        self.assertEqual(rendered.count("Variante?"), 1)
        self.assertIn('<div class="frame"><hr', rendered)
        self.assertIn("<span>ANSWER</span></div>", rendered)
        self.assertLess(rendered.index('id="answer"'), rendered.index("Variante?"))
        self.assertLess(rendered.index("Variante?"), rendered.index("Original?"))
        self.assertLess(rendered.index("Original?"), rendered.index("ANSWER"))

    def test_answer_label_follows_the_ui_language(self) -> None:
        set_ui_language("fr")
        rendered = render_answer_context("ANSWER", "Variante?", "Original?", False)
        self.assertIn(">%s</div>" % tr("reviewer.original"), rendered)

    def test_answer_original_preserves_safe_formatting_but_not_active_markup(self) -> None:
        rendered = render_answer_context(
            '<div class="answer">ANSWER</div>',
            "Variante?",
            '<script>danger()</script><form>Original <b>Frage</b></form>',
            False,
        )
        self.assertIn("Original <b style=", rendered)
        self.assertIn(">Frage</b>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<form>", rendered)
        self.assertLess(rendered.index("Original "), rendered.index("ANSWER"))

    def test_original_comparison_can_be_hidden(self) -> None:
        rendered = render_answer_context(
            'Original?<hr id="answer"><div>ANSWER</div>',
            "Variante?",
            "Original?",
            True,
            show_original=False,
        )

        self.assertEqual(rendered.count("Variante?"), 1)
        self.assertNotIn("Original?", rendered)
        self.assertNotIn('class="fv-answer-original"', rendered)
        self.assertLess(rendered.index("Variante?"), rendered.index("ANSWER"))

    def test_answer_original_preserves_only_safe_images(self) -> None:
        rendered = render_answer_context(
            "ANSWER",
            "Variante?",
            '<img src="capture.png" alt="Aufnahme">'
            '<img src="javascript:danger()">Original?',
            False,
        )
        self.assertIn('src="capture.png" alt="Aufnahme"', rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertIn("Original?", rendered)


class CardSnapshotImageTests(unittest.TestCase):
    def _snapshot(
        self,
        question_html: str,
        answer_html: str,
        *,
        allow_images: bool = True,
    ) -> CardSnapshot:
        card = _SnapshotCard(question_html, answer_html)
        collection = _SnapshotCollection(
            card, _SnapshotMedia(Path.cwd(), [])
        )
        return snapshot_card(collection, card.id, allow_images=allow_images)

    def test_image_front_requests_one_rendered_screenshot(self) -> None:
        front = (
            "<style>.card{text-align:center}img{max-width:100%}</style>"
            '<img src="capture.png" alt="Aufnahme">Welche Struktur?'
        )
        snapshot = self._snapshot(front, front + "<hr>Bronchus")

        self.assertIsNone(snapshot.unsupported_reason)
        self.assertTrue(snapshot.front_screenshot_required)
        self.assertEqual(snapshot.images, ())

    def test_text_only_front_keeps_the_zero_screenshot_path(self) -> None:
        snapshot = self._snapshot(
            "<style>.card{text-align:center}</style><b>Welche Struktur?</b>",
            "<b>Welche Struktur?</b><hr>Bronchus",
        )

        self.assertIsNone(snapshot.unsupported_reason)
        self.assertFalse(snapshot.front_screenshot_required)
        self.assertEqual(snapshot.images, ())

    def test_capture_viewport_expands_for_tall_content_and_stays_bounded(self) -> None:
        self.assertEqual(
            fitted_capture_size(1000, 700, 980, 1800),
            (1000, 1800),
        )
        self.assertEqual(
            fitted_capture_size(4000, 3000, 9000, 12000),
            (1600, 2048),
        )
        self.assertEqual(
            fitted_capture_size("bad", None, float("inf"), -1),
            (720, 520),
        )

    def test_complex_visual_fronts_share_the_same_complete_capture_contract(self) -> None:
        fronts = {
            "multiple images": '<img src="one.png"><img src="two.png">Frage?',
            "remote image": '<img src="https://example.test/scan.png">Frage?',
            "responsive image": '<picture><img src="scan.png"></picture>Frage?',
            "svg": '<svg><path d="M0 0"></path></svg>Frage?',
            "table": '<table><tr><td>A</td></tr></table>Frage?',
            "mathjax": r"Berechne \(x^2\).",
            "css visual": '<style>.card{background-image:url("map.png")}</style>Frage?',
        }
        for label, front in fronts.items():
            with self.subTest(label=label):
                snapshot = self._snapshot(front, front + "<hr>Antwort")
                self.assertIsNone(snapshot.unsupported_reason)
                self.assertTrue(snapshot.front_screenshot_required)
                self.assertEqual(snapshot.images, ())

    def test_visual_front_fails_closed_when_capture_is_not_available(self) -> None:
        snapshot = self._snapshot(
            '<img src="scan.png">Welche Struktur?',
            '<img src="scan.png">Welche Struktur?<hr>Antwort',
            allow_images=False,
        )
        self.assertEqual(snapshot.unsupported_reason, tr("failure.images_live_only"))
        self.assertFalse(snapshot.front_screenshot_required)

    def test_capture_attachment_replaces_the_pending_marker(self) -> None:
        snapshot = self._snapshot(
            '<img src="scan.png">Welche Struktur?',
            '<img src="scan.png">Welche Struktur?<hr>Antwort',
        )
        captured = attach_front_screenshot(snapshot, TEST_PNG)

        self.assertFalse(captured.front_screenshot_required)
        self.assertIsNone(captured.unsupported_reason)
        self.assertEqual(len(captured.images), 1)
        self.assertEqual(captured.images[0].role, "front")
        self.assertEqual(captured.images[0].kind, "rendered_front_screenshot")
        self.assertEqual(captured.images[0].data, TEST_PNG)

        failed = mark_front_screenshot_failed(snapshot)
        self.assertFalse(failed.front_screenshot_required)
        self.assertEqual(failed.unsupported_reason, tr("failure.image_unreadable"))

    def test_pasted_front_and_visual_answer_are_kept_as_reliable_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "front.jpg").write_bytes(TEST_JPEG)
            (root / "answer.jpg").write_bytes(TEST_JPEG)
            question = 'Welche Ergänzung fehlt?<br><img src="front.jpg">'
            answer = (
                question
                + '<hr id="answer"><img src="answer.jpg">'
            )
            card = _SnapshotCard(question, answer)
            collection = _SnapshotCollection(
                card,
                _SnapshotMedia(root, ["front.jpg", "answer.jpg"]),
            )

            snapshot = snapshot_card(collection, card.id, allow_images=True)

        self.assertFalse(snapshot.front_screenshot_required)
        self.assertIsNone(snapshot.unsupported_reason)
        self.assertEqual(
            [(image.role, image.kind) for image in snapshot.images],
            [
                ("front", "source_image_fallback"),
                ("answer", "source_image_fallback"),
            ],
        )

        fallback = mark_front_screenshot_failed(snapshot)
        self.assertFalse(fallback.front_screenshot_required)
        self.assertIsNone(fallback.unsupported_reason)
        self.assertEqual(fallback.images, snapshot.images)

        captured = attach_front_screenshot(snapshot, TEST_PNG)
        self.assertEqual(
            [(image.role, image.kind) for image in captured.images],
            [
                ("front", "rendered_front_screenshot"),
                ("answer", "source_image_fallback"),
            ],
        )

    def test_frontside_repeat_is_not_mislabelled_as_an_answer_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "front.jpg").write_bytes(TEST_JPEG)
            question = '<img src="front.jpg">Was ist dargestellt?'
            card = _SnapshotCard(
                question,
                question + '<hr id="answer">Eine Funktion.',
            )
            collection = _SnapshotCollection(
                card,
                _SnapshotMedia(root, ["front.jpg"]),
            )
            snapshot = snapshot_card(collection, card.id, allow_images=True)

        self.assertEqual(len(snapshot.images), 1)
        self.assertEqual(snapshot.images[0].role, "front")

    def test_visual_detector_ignores_normal_text_formatting(self) -> None:
        self.assertFalse(
            front_requires_screenshot(
                '<style>.card{font-size:24px;text-align:center}</style>'
                '<div><strong>Nur Text</strong></div>'
            )
        )


class PromptPrivacyTests(unittest.TestCase):
    def test_visual_inputs_use_neutral_labels_instead_of_filenames(self) -> None:
        snapshot = CardSnapshot(
            1,
            101,
            '<img src="Patientin_Erika_Mustermann.png">Frage?',
            "Antwort",
            "[Bild] Frage?",
            "Antwort",
            source_hash("image-card"),
            images=(
                CardImage(
                    "Patientin_Erika_Mustermann.png",
                    "image/png",
                    TEST_PNG,
                    role="front",
                ),
            ),
        )

        system_prompt, user_prompt, schema = build_prompt(snapshot, 1)
        payload = json.loads(user_prompt.split("\n\n", 1)[1])

        self.assertNotIn("Patientin_Erika_Mustermann.png", user_prompt)
        self.assertIn("substantially different", system_prompt)
        self.assertIn("Every natural-language", system_prompt)
        self.assertNotIn("Welche Funktion erfüllt", system_prompt)
        self.assertIn("same as original_question", payload["output_language"])
        self.assertIn("rendered front screenshot", payload["output_language"])
        self.assertIn("is_substantially_different", schema["required"])
        self.assertIn("change_strategy", schema["required"])
        self.assertIn("front_visual_mode", schema["required"])
        self.assertIn(
            "variant_is_self_contained_without_front_visual",
            schema["required"],
        )
        self.assertEqual(
            schema["properties"]["is_substantially_different"],
            {"type": "boolean"},
        )
        self.assertIn(
            "completion_prompt",
            schema["properties"]["change_strategy"]["enum"],
        )
        self.assertEqual(
            schema["properties"]["front_visual_mode"]["enum"],
            ["none", "replace"],
        )
        self.assertIn("NEVER visible", system_prompt)
        self.assertEqual(
            payload["visual_inputs"],
            [
                {
                    "role": "front",
                    "kind": "source_image",
                    "label": "image_1",
                }
            ],
        )
        self.assertTrue(payload["front_image_present"])

    def test_each_rewrite_intensity_has_a_distinct_prompt_contract(self) -> None:
        snapshot = CardSnapshot(
            1,
            101,
            "Welche Funktion erfüllt die Niere?",
            "Sie filtert das Blut.",
            "Welche Funktion erfüllt die Niere?",
            "Sie filtert das Blut.",
            source_hash("text-card"),
        )

        prompts = {}
        for intensity in ("near", "light", "distinct", "maximum"):
            system_prompt, user_prompt, _schema = build_prompt(
                snapshot, 1, intensity
            )
            payload = json.loads(user_prompt.split("\n\n", 1)[1])
            prompts[intensity] = system_prompt
            self.assertEqual(payload["rewrite_intensity"], intensity)
            self.assertIn(
                "SELECTED REWRITE INTENSITY: %s" % intensity,
                system_prompt,
            )

        self.assertEqual(len(set(prompts.values())), 4)
        self.assertEqual(build_prompt(snapshot, 1)[0], prompts["distinct"])
        fallback_user_prompt = build_prompt(snapshot, 1, "obsolete-value")[1]
        fallback_payload = json.loads(fallback_user_prompt.split("\n\n", 1)[1])
        self.assertEqual(fallback_payload["rewrite_intensity"], "distinct")


class StoreTests(unittest.TestCase):
    @staticmethod
    def _generated(card_id: int, label: str) -> GeneratedVariants:
        return GeneratedVariants(
            card_id,
            card_id + 100,
            "hash-%s" % label,
            "Original %s" % label,
            "Kern %s" % label,
            ["Variante %s" % label],
            provider="openai",
            model="test-model",
        )

    def test_variants_are_profile_scoped_and_replace_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VariantStore(Path(directory) / "variants.sqlite3")
            first = GeneratedVariants(10, 20, "h1", "Original", "Kern", ["V1"], provider="openai", model="m")
            second = GeneratedVariants(10, 20, "h2", "Original neu", "Kern", ["V2", "V3"], provider="gemini", model="n")
            store.save_generated("profile-a", first)
            self.assertIsNone(store.get("profile-b", 10))
            store.save_generated("profile-a", second)
            loaded = store.get("profile-a", 10)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.source_hash, "h2")
            self.assertEqual(loaded.variants, ["V2", "V3"])
            self.assertEqual(store.delete_cards("profile-a", [10]), 1)

    def test_non_list_variant_json_is_treated_as_an_empty_cache_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variants.sqlite3"
            store = VariantStore(path)
            store.save_generated("profile-a", self._generated(10, "valid"))

            for invalid_json in ("null", "1", '{"wrong":"value"}'):
                with self.subTest(invalid_json=invalid_json):
                    connection = sqlite3.connect(path)
                    try:
                        connection.execute(
                            "UPDATE card_variants SET variants_json=? "
                            "WHERE profile_key=? AND card_id=?",
                            (invalid_json, "profile-a", 10),
                        )
                        connection.commit()
                    finally:
                        connection.close()
                    loaded = store.get("profile-a", 10)
                    self.assertIsNotNone(loaded)
                    assert loaded is not None
                    self.assertEqual(loaded.variants, [])

    def test_corrupt_variant_cache_is_quarantined_and_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variants.sqlite3"
            damaged = b"this is not a sqlite database"
            path.write_bytes(damaged)

            store = VariantStore(path)

            self.assertIsNotNone(store.recovered_from)
            assert store.recovered_from is not None
            self.assertTrue(store.recovered_from.is_file())
            self.assertEqual(store.recovered_from.read_bytes(), damaged)
            self.assertTrue(path.is_file())
            self.assertEqual(store.count("profile-a"), 0)
            store.save_generated("profile-a", self._generated(10, "recovered"))
            self.assertEqual(store.count("profile-a"), 1)

    def test_batch_save_and_profile_purge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VariantStore(Path(directory) / "variants.sqlite3")
            items = [
                GeneratedVariants(i, i + 100, "h", "O", "K", ["V"])
                for i in (1, 2)
            ]
            self.assertEqual(store.save_many("profile-a", items), 2)
            self.assertEqual(len(store.list_for_profile("profile-a")), 2)
            self.assertEqual(store.delete_profile("profile-a"), 2)
            self.assertEqual(store.count("profile-a"), 0)

    def test_prepared_variants_support_save_list_filter_delete_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VariantStore(Path(directory) / "variants.sqlite3")
            prepared = [
                self._generated(3, "drei"),
                self._generated(1, "eins"),
                self._generated(2, "zwei"),
            ]

            self.assertEqual(store.save_prepared_many("profile-a", prepared), 3)
            self.assertEqual(
                store.save_prepared_many(
                    "profile-b", [self._generated(9, "anderes-profil")]
                ),
                1,
            )
            self.assertEqual(store.save_prepared_many("profile-a", []), 0)
            self.assertEqual(store.prepared_count("profile-a"), 3)
            self.assertEqual(store.prepared_count("profile-b"), 1)
            self.assertEqual(
                [item.card_id for item in store.list_prepared_for_profile("profile-a")],
                [1, 2, 3],
            )
            self.assertEqual(
                [
                    item.card_id
                    for item in store.list_prepared_for_cards(
                        "profile-a", [3, 999, 1]
                    )
                ],
                [1, 3],
            )
            self.assertEqual(store.list_prepared_for_cards("profile-a", []), [])

            replacement = self._generated(2, "zwei-neu")
            self.assertEqual(store.save_prepared_many("profile-a", [replacement]), 1)
            stored_replacement = store.list_prepared_for_cards("profile-a", [2])
            self.assertEqual(len(stored_replacement), 1)
            self.assertEqual(stored_replacement[0].source_hash, "hash-zwei-neu")
            self.assertEqual(store.prepared_count("profile-a"), 3)

            self.assertEqual(store.delete_prepared_cards("profile-a", [2, 999]), 1)
            self.assertEqual(store.prepared_count("profile-a"), 2)
            self.assertEqual(store.delete_prepared_cards("profile-a", []), 0)
            self.assertEqual(store.delete_prepared_profile("profile-a"), 2)
            self.assertEqual(store.prepared_count("profile-a"), 0)
            self.assertEqual(store.prepared_count("profile-b"), 1)

    def test_prepared_and_regular_variants_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VariantStore(Path(directory) / "variants.sqlite3")
            regular = self._generated(10, "regulär")
            prepared = self._generated(10, "vorbereitet")
            store.save_generated("profile-a", regular)
            store.save_prepared_many("profile-a", [prepared])

            regular_loaded = store.get("profile-a", 10)
            self.assertIsNotNone(regular_loaded)
            assert regular_loaded is not None
            self.assertEqual(regular_loaded.source_hash, "hash-regulär")
            prepared_loaded = store.list_prepared_for_cards("profile-a", [10])
            self.assertEqual(len(prepared_loaded), 1)
            self.assertEqual(prepared_loaded[0].source_hash, "hash-vorbereitet")
            self.assertEqual(store.count("profile-a"), 1)
            self.assertEqual(store.prepared_count("profile-a"), 1)

            self.assertEqual(store.delete_prepared_cards("profile-a", [10]), 1)
            self.assertIsNotNone(store.get("profile-a", 10))
            self.assertEqual(store.count("profile-a"), 1)
            store.save_prepared_many("profile-a", [prepared])
            self.assertEqual(store.delete_cards("profile-a", [10]), 1)
            self.assertEqual(store.prepared_count("profile-a"), 1)
            self.assertEqual(
                store.list_prepared_for_cards("profile-a", [10])[0].source_hash,
                "hash-vorbereitet",
            )

    def test_delete_profile_removes_regular_and_prepared_rows_only_for_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VariantStore(Path(directory) / "variants.sqlite3")
            store.save_many(
                "profile-a",
                [self._generated(1, "a-reg-1"), self._generated(2, "a-reg-2")],
            )
            store.save_prepared_many(
                "profile-a", [self._generated(1, "a-prep-1")]
            )
            store.save_generated("profile-b", self._generated(1, "b-reg"))
            store.save_prepared_many(
                "profile-b", [self._generated(1, "b-prep")]
            )

            self.assertEqual(store.delete_profile("profile-a"), 3)
            self.assertEqual(store.count("profile-a"), 0)
            self.assertEqual(store.prepared_count("profile-a"), 0)
            self.assertEqual(store.count("profile-b"), 1)
            self.assertEqual(store.prepared_count("profile-b"), 1)

    def test_existing_database_gains_prepared_table_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variants.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """CREATE TABLE card_variants (
                    profile_key TEXT NOT NULL, card_id INTEGER NOT NULL,
                    note_id INTEGER NOT NULL, source_hash TEXT NOT NULL,
                    question_preview TEXT NOT NULL, core_aspect TEXT NOT NULL,
                    variants_json TEXT NOT NULL, provider TEXT NOT NULL,
                    model TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY (profile_key, card_id))"""
                )
                connection.execute(
                    """INSERT INTO card_variants
                    (profile_key, card_id, note_id, source_hash, question_preview,
                    core_aspect, variants_json, provider, model, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "legacy-profile",
                        42,
                        142,
                        "legacy-hash",
                        "Alte Originalfrage",
                        "Alter Kern",
                        json.dumps(["Alte Variante"], ensure_ascii=False),
                        "gemini",
                        "legacy-model",
                        "2025-01-02T03:04:05+00:00",
                    ),
                )
            connection.close()

            store = VariantStore(path)
            legacy = store.get("legacy-profile", 42)
            self.assertIsNotNone(legacy)
            assert legacy is not None
            self.assertEqual(legacy.source_hash, "legacy-hash")
            self.assertEqual(legacy.variants, ["Alte Variante"])
            self.assertEqual(legacy.updated_at, "2025-01-02T03:04:05+00:00")
            self.assertEqual(store.count("legacy-profile"), 1)
            self.assertEqual(store.prepared_count("legacy-profile"), 0)

            store.save_prepared_many(
                "legacy-profile", [self._generated(42, "offline")]
            )
            self.assertEqual(store.prepared_count("legacy-profile"), 1)
            legacy_after_migration = store.get("legacy-profile", 42)
            self.assertIsNotNone(legacy_after_migration)
            assert legacy_after_migration is not None
            self.assertEqual(legacy_after_migration.source_hash, "legacy-hash")
            self.assertEqual(legacy_after_migration.variants, ["Alte Variante"])

    def test_legacy_prepared_table_gains_visual_columns_without_data_loss(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variants.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """CREATE TABLE prepared_variants (
                    profile_key TEXT NOT NULL, card_id INTEGER NOT NULL,
                    note_id INTEGER NOT NULL, source_hash TEXT NOT NULL,
                    question_preview TEXT NOT NULL, core_aspect TEXT NOT NULL,
                    variants_json TEXT NOT NULL, provider TEXT NOT NULL,
                    model TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY (profile_key, card_id))"""
                )
                connection.execute(
                    """INSERT INTO prepared_variants
                    (profile_key, card_id, note_id, source_hash, question_preview,
                    core_aspect, variants_json, provider, model, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "legacy-profile",
                        42,
                        142,
                        "legacy-prepared-hash",
                        "Alte Frage",
                        "Alter Kern",
                        json.dumps(["Alte vorbereitete Variante"]),
                        "openai",
                        "legacy-model",
                        "2025-01-02T03:04:05+00:00",
                    ),
                )
            connection.close()

            store = VariantStore(path)
            with sqlite3.connect(path) as inspection:
                columns = {
                    str(row[1])
                    for row in inspection.execute(
                        "PRAGMA table_info(prepared_variants)"
                    ).fetchall()
                }
            inspection.close()

            self.assertIn("uses_front_image", columns)
            self.assertIn("front_visual_mode", columns)
            loaded = store.list_prepared_for_profile("legacy-profile")
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].source_hash, "legacy-prepared-hash")
            self.assertEqual(loaded[0].variants, ["Alte vorbereitete Variante"])
            self.assertFalse(loaded[0].uses_front_image)
            self.assertEqual(loaded[0].front_visual_mode, "")

            replacement = self._generated(42, "mit-bild")
            replacement.uses_front_image = True
            replacement.front_visual_mode = "replace"
            store.save_prepared_many("legacy-profile", [replacement])
            migrated = store.list_prepared_for_profile("legacy-profile")
            self.assertEqual(len(migrated), 1)
            self.assertTrue(migrated[0].uses_front_image)
            self.assertEqual(migrated[0].front_visual_mode, "replace")

    def test_secret_store_session_and_persistent_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            store = SecretStore(path)
            store.set("test-session", "session-key", persist=False, scope="A")
            self.assertEqual(store.get("test-session", "A"), "session-key")
            self.assertEqual(store.source_kind("test-session", "A"), "session")
            self.assertFalse(store.is_persisted("test-session", "A"))
            self.assertIsNone(store.get("test-session", "B"))
            self.assertFalse(path.exists())
            store.set("test-persistent", "persistent-key", persist=True, scope="A")
            self.assertEqual(
                SecretStore(path).get("test-persistent", "A"), "persistent-key"
            )
            self.assertEqual(
                store.source_kind("test-persistent", "A"), "device"
            )
            self.assertTrue(store.is_persisted("test-persistent", "A"))
            self.assertIsNone(SecretStore(path).get("test-persistent", "B"))
            disk = json.loads(path.read_text(encoding="utf-8"))
            disk_value = next(iter(disk.values()))
            if persistent_storage_is_protected():
                self.assertNotEqual(disk_value, "persistent-key")
                self.assertTrue(disk_value.startswith("dpapi-v1:"))
            else:
                self.assertEqual(disk_value, "persistent-key")
            self.assertNotIn("A", next(iter(disk)))
            store.clear_session("A")
            store.clear_all()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {})

    def test_secret_store_migrates_legacy_plaintext_when_protection_exists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            storage_key = SecretStore._storage_key("gemini", "profile-a")
            path.write_text(
                json.dumps({storage_key: "legacy-key"}), encoding="utf-8"
            )

            store = SecretStore(path)
            migrated = json.loads(path.read_text(encoding="utf-8"))[storage_key]
            if persistent_storage_is_protected():
                self.assertNotEqual(migrated, "legacy-key")
                self.assertTrue(migrated.startswith("dpapi-v1:"))
            else:
                self.assertEqual(migrated, "legacy-key")
            self.assertEqual(store.get("gemini", "profile-a"), "legacy-key")

    def test_secret_store_never_uses_legacy_plaintext_after_failed_migration(
        self,
    ) -> None:
        if not persistent_storage_is_protected():
            self.skipTest("DPAPI migration applies only on Windows")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            storage_key = SecretStore._storage_key("gemini", "profile-a")
            path.write_text(
                json.dumps({storage_key: "legacy-key"}), encoding="utf-8"
            )
            with unittest.mock.patch.object(
                SecretStore,
                "_write",
                side_effect=OSError("read-only profile"),
            ):
                store = SecretStore(path)
                with self.assertRaises(OSError):
                    store.get("gemini", "profile-a")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))[storage_key],
                "legacy-key",
            )

    def test_secret_store_never_returns_damaged_ciphertext_as_a_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            storage_key = SecretStore._storage_key("gemini", "profile-a")
            path.write_text(
                json.dumps({storage_key: "dpapi-v1:not-valid-base64!"}),
                encoding="utf-8",
            )
            store = SecretStore(path)
            with self.assertRaises(SecretProtectionError):
                store.get("gemini", "profile-a")
            with self.assertRaises(SecretProtectionError):
                store.source_kind("gemini", "profile-a")

    def test_corrupt_secret_file_is_reported_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            damaged = '{"provider-a": "key-a", broken'
            path.write_text(damaged, encoding="utf-8")
            store = SecretStore(path)

            with self.assertRaises(SecretStoreError):
                store.get("gemini", "profile-a")
            with self.assertRaises(SecretStoreError):
                store.set(
                    "gemini",
                    "new-session-key",
                    persist=True,
                    scope="profile-a",
                )

            self.assertEqual(path.read_text(encoding="utf-8"), damaged)
            self.assertEqual(
                store.get("gemini", "profile-a"),
                "new-session-key",
            )
            self.assertEqual(
                store.source_kind("gemini", "profile-a"),
                "session",
            )

    def test_session_key_overrides_old_device_key_after_delete_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            original = SecretStore(path)
            original.set(
                "gemini",
                "old-device-key",
                persist=True,
                scope="profile-a",
            )
            store = SecretStore(path)

            with mock.patch.object(
                store,
                "_write",
                side_effect=PermissionError("read-only profile"),
            ):
                with self.assertRaises(PermissionError):
                    store.delete("gemini", "profile-a")
            store.set(
                "gemini",
                "new-session-key",
                persist=False,
                scope="profile-a",
            )

            self.assertEqual(
                store.get("gemini", "profile-a"),
                "new-session-key",
            )
            self.assertEqual(
                store.source_kind("gemini", "profile-a"),
                "session",
            )
            self.assertEqual(
                SecretStore(path).get("gemini", "profile-a"),
                "old-device-key",
            )


class BatchGenerationTests(unittest.TestCase):
    @staticmethod
    def _snap(card_id: int) -> CardSnapshot:
        return CardSnapshot(
            card_id,
            card_id + 100,
            "Q",
            "A",
            "Frage?",
            "Antwort",
            source_hash("Q\0A"),
        )

    def test_cancel_stops_before_provider_call(self) -> None:
        settings = ProviderSettings("openai", "model", "secret")
        with unittest.mock.patch("fragevariator.anki_bridge.generate_json") as call:
            result = generate_batch([self._snap(1)], settings, 3, lambda: True)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.sent_cards, 0)
        call.assert_not_called()

    def test_pending_front_screenshot_never_reaches_provider(self) -> None:
        settings = ProviderSettings("openai", "model", "secret")
        snapshot = CardSnapshot(
            1,
            101,
            '<img src="scan.png">Welche Struktur?',
            "Antwort",
            "Welche Struktur?",
            "Antwort",
            source_hash("pending-visual-card"),
            front_screenshot_required=True,
        )
        with unittest.mock.patch("fragevariator.anki_bridge.generate_json") as call:
            result = generate_batch([snapshot], settings, 1)

        call.assert_not_called()
        self.assertEqual(result.sent_cards, 0)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].reason, tr("failure.image_unreadable"))

    def test_terminal_provider_error_stops_remaining_cards(self) -> None:
        settings = ProviderSettings("openai", "model", "secret")
        error = ProviderError(ErrorKind.AUTH, "openai", "rejected")
        with unittest.mock.patch(
            "fragevariator.anki_bridge.generate_json", side_effect=error
        ) as call:
            result = generate_batch(
                [self._snap(1), self._snap(2)], settings, 3
            )
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result.sent_cards, 1)
        self.assertEqual(len(result.failures), 1)
        self.assertTrue(result.terminal_error)

    def test_provider_wide_transient_exhaustion_stops_remaining_cards(self) -> None:
        settings = ProviderSettings("gemini", "model", "secret")
        for kind in (ErrorKind.RATE_LIMIT, ErrorKind.UNAVAILABLE):
            with self.subTest(kind=kind):
                error = ProviderError(
                    kind,
                    "gemini",
                    "temporary provider-wide failure",
                    retryable=True,
                )
                with unittest.mock.patch(
                    "fragevariator.anki_bridge.generate_json",
                    side_effect=error,
                ) as call:
                    result = generate_batch(
                        [self._snap(1), self._snap(2), self._snap(3)],
                        settings,
                        1,
                    )

                self.assertEqual(call.call_count, 1)
                self.assertEqual(len(result.failures), 1)
                self.assertTrue(result.terminal_error)

    def test_card_images_are_forwarded_to_provider(self) -> None:
        settings = ProviderSettings("openai", "model", "secret")
        png = TEST_PNG
        snapshot = CardSnapshot(
            1,
            101,
            '<img src="map.png">Welche Struktur ist mit dem Pfeil markiert?',
            "Die Mitralklappe.",
            "[Bild] Welche Struktur ist mit dem Pfeil markiert?",
            "Die Mitralklappe.",
            source_hash("image-card"),
            images=(CardImage("map.png", "image/png", png),),
        )
        response = {
            "status": "ok",
            "is_equivalent": True,
            "answer_not_revealed": True,
            "is_substantially_different": True,
            "change_strategy": "changed_perspective",
            "front_visual_mode": "replace",
            "variant_is_self_contained_without_front_visual": True,
            "core_aspect": "Lage der Mitralklappe",
            "variants": [
                "Welche Herzklappe liegt zwischen linkem Vorhof und linker Herzkammer?"
            ],
            "warnings": [],
            "unsupported_reason": "",
        }
        with unittest.mock.patch(
            "fragevariator.anki_bridge.generate_json", return_value=response
        ) as call:
            result = generate_batch([snapshot], settings, 1)
        self.assertEqual(len(result.generated), 1)
        self.assertEqual(result.sent_cards, 1)
        images = call.call_args.kwargs["images"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].data, png)
        self.assertEqual(result.generated[0].front_visual_mode, "replace")

    def test_image_only_card_reaches_provider_and_uses_replace_decision(self) -> None:
        settings = ProviderSettings("gemini", "model", "secret")
        snapshot = CardSnapshot(
            1,
            101,
            '<img src="front.jpg">',
            '<img src="front.jpg"><hr><img src="answer.jpg">',
            "[image]",
            "[image]",
            source_hash("image-only-card"),
            images=(
                CardImage("front.jpg", "image/jpeg", TEST_JPEG, role="front"),
                CardImage("answer.jpg", "image/jpeg", TEST_JPEG, role="answer"),
            ),
        )
        response = {
            "status": "ok",
            "is_equivalent": True,
            "answer_not_revealed": True,
            "is_substantially_different": True,
            "change_strategy": "changed_perspective",
            "front_visual_mode": "replace",
            "variant_is_self_contained_without_front_visual": True,
            "core_aspect": "Potenzreihenentwicklung und Gültigkeitsbereich von ln(1+x)",
            "variants": [
                "Gib die Potenzreihenentwicklung von ln(1+x) einschließlich ihres Gültigkeitsbereichs an."
            ],
            "warnings": [],
            "unsupported_reason": "",
        }

        with unittest.mock.patch(
            "fragevariator.anki_bridge.generate_json", return_value=response
        ) as call:
            result = generate_batch([snapshot], settings, 1)

        self.assertEqual(len(result.generated), 1)
        self.assertFalse(result.failures)
        self.assertEqual(result.generated[0].front_visual_mode, "replace")
        self.assertTrue(result.generated[0].uses_front_image)
        self.assertEqual(len(call.call_args.kwargs["images"]), 2)

    def test_batch_uses_the_same_intensity_for_prompt_and_local_gate(self) -> None:
        settings = ProviderSettings("openai", "model", "secret")
        snapshot = CardSnapshot(
            1,
            101,
            "Welche Funktion erfüllt die Niere?",
            "Sie filtert das Blut.",
            "Welche Funktion erfüllt die Niere?",
            "Sie filtert das Blut.",
            source_hash("kidney-card"),
        )
        response = {
            "status": "ok",
            "is_equivalent": True,
            "answer_not_revealed": True,
            "is_substantially_different": True,
            "change_strategy": "other",
            "core_aspect": "Funktion der Niere",
            "variants": ["Welche Aufgabe übernimmt die Niere?"],
            "warnings": [],
            "unsupported_reason": "",
        }

        with unittest.mock.patch(
            "fragevariator.anki_bridge.generate_json", return_value=response
        ) as call:
            near_result = generate_batch(
                [snapshot], settings, 1, intensity="near"
            )
        self.assertEqual(len(near_result.generated), 1)
        self.assertIn(
            "SELECTED REWRITE INTENSITY: near",
            call.call_args.kwargs["system_prompt"],
        )

        with unittest.mock.patch(
            "fragevariator.anki_bridge.generate_json", return_value=response
        ):
            distinct_result = generate_batch(
                [snapshot], settings, 1, intensity="distinct"
            )
        self.assertFalse(distinct_result.generated)
        self.assertEqual(len(distinct_result.failures), 1)


if __name__ == "__main__":
    unittest.main()
