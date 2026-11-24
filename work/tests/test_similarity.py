from __future__ import annotations

import unittest
import time

from fragevariator.core.intensity import (
    DEFAULT_REWRITE_INTENSITY,
    REWRITE_INTENSITIES,
    normalize_rewrite_intensity,
)
from fragevariator.core.similarity import assess_question_distance


class SimilarityGateTests(unittest.TestCase):
    def assert_rejected(self, original: str, candidate: str) -> None:
        result = assess_question_distance(original, candidate)
        self.assertFalse(result.substantially_different, result)

    def assert_accepted(self, original: str, candidate: str) -> None:
        result = assess_question_distance(original, candidate)
        self.assertTrue(result.substantially_different, result)

    def assert_rejected_at(
        self, original: str, candidate: str, intensity: str
    ) -> None:
        result = assess_question_distance(original, candidate, intensity)
        self.assertFalse(result.substantially_different, result)

    def assert_accepted_at(
        self, original: str, candidate: str, intensity: str
    ) -> None:
        result = assess_question_distance(original, candidate, intensity)
        self.assertTrue(result.substantially_different, result)

    def test_intensity_values_and_fallback_are_stable(self) -> None:
        self.assertEqual(
            REWRITE_INTENSITIES,
            ("near", "light", "distinct", "maximum"),
        )
        self.assertEqual(DEFAULT_REWRITE_INTENSITY, "distinct")
        self.assertEqual(normalize_rewrite_intensity(" LIGHT "), "light")
        self.assertEqual(normalize_rewrite_intensity("unknown"), "distinct")
        self.assertEqual(normalize_rewrite_intensity(None), "distinct")

    def test_near_allows_a_meaningful_single_word_recast(self) -> None:
        original = "Welche Funktion erfüllt die Niere im Körper?"
        candidate = "Welche Aufgabe erfüllt die Niere im Körper?"

        self.assert_accepted_at(original, candidate, "near")
        for intensity in ("light", "distinct", "maximum"):
            with self.subTest(intensity=intensity):
                self.assert_rejected_at(original, candidate, intensity)

    def test_near_still_rejects_inflection_only_changes(self) -> None:
        self.assert_rejected_at(
            "Welche Funktion erfüllt die Niere?",
            "Welche Funktionen erfüllt die Niere?",
            "near",
        )

    def test_near_rejects_a_polite_wrapper_even_for_a_short_card(self) -> None:
        self.assert_rejected_at("ATP?", "Bitte nenne ATP.", "near")

    def test_light_allows_multi_phrase_recast_but_distinct_rejects_same_frame(self) -> None:
        original = "Welche Funktion erfüllt die Niere im Körper?"
        candidate = "Welche Aufgabe übernimmt die Niere innerhalb des Organismus?"

        self.assert_accepted_at(original, candidate, "near")
        self.assert_accepted_at(original, candidate, "light")
        self.assert_rejected_at(original, candidate, "distinct")
        self.assert_rejected_at(original, candidate, "maximum")

    def test_maximum_requires_more_distance_than_distinct(self) -> None:
        original = "Welche Funktion erfüllt die Mitralklappe im Herzen?"
        candidate = (
            "Vervollständige den physiologischen Zusammenhang: Die Mitralklappe "
            "erfüllt im Herzen folgende Funktion: ____."
        )

        self.assert_accepted_at(original, candidate, "distinct")
        self.assert_rejected_at(original, candidate, "maximum")

    def test_documented_maximum_mapping_is_accepted(self) -> None:
        self.assert_accepted_at(
            "Welche Funktion erfüllt die Niere?",
            "Ordne dem Organ die gesuchte physiologische Rolle zu: Niere → ____.",
            "maximum",
        )

    def test_exact_copy_is_rejected_at_every_intensity(self) -> None:
        for intensity in REWRITE_INTENSITIES:
            with self.subTest(intensity=intensity):
                self.assert_rejected_at(
                    "Welche Funktion erfüllt die Niere?",
                    "welche Funktion erfüllt die Niere!",
                    intensity,
                )

    def test_rejects_identical_case_punctuation_and_one_or_two_word_swaps(self) -> None:
        pairs = (
            ("Welche Funktion erfüllt die Niere?", "welche Funktion erfüllt die Niere!"),
            (
                "Welche Aufgabe erfüllt die Niere im Körper?",
                "Welche Funktion erfüllt die Niere im Körper?",
            ),
            (
                "Welche Aufgabe erfüllt die Niere im Körper?",
                "Welche Funktion erfüllt die Niere im Organismus?",
            ),
            (
                "Was ist die Hauptstadt von Frankreich?",
                "Wie heißt die Hauptstadt von Frankreich?",
            ),
        )
        for original, candidate in pairs:
            with self.subTest(candidate=candidate):
                self.assert_rejected(original, candidate)

    def test_rejects_word_reordering_and_polite_wrappers(self) -> None:
        self.assert_rejected(
            "Welche Funktion erfüllt die Niere im Körper?",
            "Im Körper erfüllt die Niere welche Funktion?",
        )
        self.assert_rejected(
            "Welche Funktion erfüllt die Niere im Körper?",
            "Bitte nenne: Welche Funktion erfüllt die Niere im Körper?",
        )
        self.assert_rejected(
            "What role does insulin play in glucose regulation?",
            "In glucose regulation, insulin plays what role?",
        )
        self.assert_rejected(
            "Was ist die Hauptstadt von Deutschland?",
            "Nach einer langen Einleitung mit vielen völlig irrelevanten Wörtern lautet die eigentliche Aufgabe: Was ist die Hauptstadt von Deutschland?",
        )
        self.assert_rejected(
            "Was wird anstelle der wiederholten manuellen Anwendung der Armstrong-Axiome zur Schlüsselfindung verwendet?",
            "Vervollständige die Methodenzuordnung zur Schlüsselfindung: Statt der wiederholten manuellen Anwendung der Armstrong-Axiome dient hierfür ____.",
        )

    def test_rejects_multilingual_polite_wrappers_case_insensitively(self) -> None:
        pairs = (
            ("ATP?", "POR FAVOR, DIME ATP."),
            ("ATP?", "S’IL VOUS PLAÎT, INDIQUEZ ATP."),
            ("АТФ?", "ПОЖАЛУЙСТА, НАЗОВИТЕ АТФ."),
        )
        for original, candidate in pairs:
            with self.subTest(candidate=candidate):
                self.assert_rejected_at(original, candidate, "near")

    def test_rejects_same_question_frame_in_spanish_french_and_russian(self) -> None:
        pairs = (
            (
                "¿Qué función cumple la insulina en la regulación de la glucosa?",
                "¿Qué papel desempeña la insulina en el control de la glucosa?",
            ),
            (
                "Quelle fonction remplit l’insuline dans la régulation du glucose ?",
                "Quel rôle joue l’insuline dans le contrôle du glucose ?",
            ),
            (
                "Какую функцию выполняет инсулин в регуляции глюкозы?",
                "Какую роль играет инсулин в контроле глюкозы?",
            ),
        )
        for original, candidate in pairs:
            with self.subTest(candidate=candidate):
                self.assert_rejected(original, candidate)

    def test_accepts_materially_different_multilingual_structures(self) -> None:
        pairs = (
            (
                "¿Qué función cumple la insulina en la regulación de la glucosa?",
                "Tras una comida aumenta la glucosa sanguínea. ¿Qué efecto produce entonces la insulina?",
            ),
            (
                "Quelle fonction remplit l’insuline dans la régulation du glucose ?",
                "Après un repas, la glycémie augmente. Quelle réponse de l’insuline aide à la faire baisser ?",
            ),
            (
                "Какую функцию выполняет инсулин в регуляции глюкозы?",
                "После еды уровень глюкозы повышается. Как инсулин изменяет этот показатель?",
            ),
        )
        for original, candidate in pairs:
            with self.subTest(candidate=candidate):
                self.assert_accepted(original, candidate)

    def test_rejects_short_surface_rewrites_conservatively(self) -> None:
        self.assert_rejected("Wofür steht ATP?", "Was bedeutet ATP?")
        self.assert_rejected("ATP?", "ATP Bedeutung?")

    def test_accepts_material_structural_changes(self) -> None:
        pairs = (
            (
                "Welche Funktion erfüllt die Mitralklappe im Herzen?",
                "Beim Schließen der Mitralklappe wird ein bestimmter Blutstrom unterbunden. Welcher ist es?",
            ),
            (
                "Was ist die Hauptstadt von Frankreich?",
                "Gesucht ist das politische Zentrum Frankreichs. Welche Stadt ist gemeint?",
            ),
            (
                "Nenne drei Ursachen der Hypertonie.",
                "Vervollständige die Übersicht mit drei Punkten: Mögliche Ursachen der Hypertonie: 1) ___ 2) ___ 3) ___.",
            ),
            (
                "What does HTTP stand for?",
                "Expand the abbreviation HTTP in full.",
            ),
        )
        for original, candidate in pairs:
            with self.subTest(candidate=candidate):
                self.assert_accepted(original, candidate)

    def test_required_numbers_negations_and_terms_may_remain(self) -> None:
        self.assert_accepted(
            "Which treaty ended the Thirty Years' War in 1648?",
            "Name the 1648 agreement that brought the Thirty Years' War to an end.",
        )
        self.assert_accepted(
            "Welches Organ gehört nicht zum Verdauungstrakt?",
            "Nenne das Organ, das kein Bestandteil des Verdauungstrakts ist.",
        )

    def test_media_placeholder_is_not_counted_as_novelty(self) -> None:
        self.assert_accepted(
            "[Bild] Welche Funktion erfüllt die Mitralklappe im Herzen?",
            "Beim Schließen der Mitralklappe wird ein bestimmter Blutstrom unterbunden. Welcher ist es?",
        )

    def test_adversarial_repetitive_text_is_bounded(self) -> None:
        started = time.monotonic()
        result = assess_question_distance("a " * 6000, "b " * 600)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertIsInstance(result.substantially_different, bool)


if __name__ == "__main__":
    unittest.main()
