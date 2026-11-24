"""Deterministic near-duplicate detection for generated questions.

The model is asked to change the retrieval surface substantially, but its
self-assessment is not a sufficient release gate.  This module deliberately
prefers a false rejection (show Anki's original card) over displaying a rewrite
that merely swaps a synonym or moves the same words around.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from .intensity import DEFAULT_REWRITE_INTENSITY, normalize_rewrite_intensity


_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*", re.UNICODE)
_MEDIA_LABEL_RE = re.compile(r"\[(?:bild|image|audio)(?::[^\]]*)?\]", re.IGNORECASE)
_POLITE_WRAPPER_WORDS = {
    # German
    "an", "bitte", "du", "führe", "gib", "kannst", "liste", "mir",
    "nenn", "nenne", "nennen", "sag", "sage", "sagen",
    # English
    "can", "could", "give", "kindly", "list", "me", "name", "please",
    "state", "tell", "you",
    # Spanish
    "di", "dime", "dígame", "enumera", "enumere", "favor", "indica",
    "indique", "lista", "me", "menciona", "mencione", "nombra", "nombre",
    "podría", "podrías", "por", "puedes",
    # French (straight and typographic apostrophes are both tokenized)
    "cite", "citez", "dis-moi", "dites-moi", "donne", "donnez", "énumère",
    "énumérez", "indique", "indiquez", "merci", "nomme", "nommez", "peux",
    "plait", "plaît", "pouvez", "s'il", "s’il", "tu", "vous",
    # Russian
    "дай", "дайте", "можете", "можешь", "мне", "назови", "назовите",
    "перечисли", "перечислите", "пожалуйста", "скажи", "скажите", "укажи",
    "укажите",
}
_FUNCTION_WORDS = {
    # Content words are collapsed below, so swapping several synonyms inside
    # an unchanged sentence frame does not count as a structural rewrite.
    "als", "am", "an", "auf", "aus", "bei", "bis", "das", "dem", "den",
    "der", "des", "die", "durch", "ein", "eine", "einer", "eines", "fuer",
    "für", "hat", "im", "in", "ist", "kann", "mit", "nach", "nenne", "nennen",
    "nicht", "oder", "sind", "um", "unter", "von", "vor", "war", "was",
    "welche", "welcher", "welches", "welchen", "wem", "wen", "wer", "wie",
    "wieso", "wo", "wodurch", "wofuer", "wofür", "warum", "wann", "zu", "zum",
    "zur", "and", "are", "as", "at", "by", "does", "for", "from", "how",
    "into", "is", "name", "not", "of", "on", "or", "the", "to", "under",
    "was", "what", "when", "where", "which", "who", "why", "with",
    # Spanish
    "a", "al", "como", "cómo", "con", "cuál", "cuáles", "cuando",
    "cuándo", "de", "del", "donde", "dónde", "el", "ella", "en", "es",
    "esta", "está", "este", "la", "las", "lo", "los", "más", "no", "o",
    "para", "por", "que", "qué", "se", "si", "sin", "son", "su", "sus",
    "un", "una", "y",
    # French
    "à", "au", "aux", "avec", "ce", "ces", "cette", "comment", "dans",
    "de", "des", "du", "en", "est", "et", "la", "le", "les", "ne", "ou",
    "où", "par", "pas", "pour", "quand", "que", "quel", "quelle", "quelles",
    "quels", "qui", "sans", "se", "sous", "sur", "un", "une",
    # Russian
    "а", "без", "был", "была", "были", "будет", "в", "во", "где", "для",
    "до", "есть", "зачем", "и", "из", "или", "к", "как", "какая", "какие",
    "каким", "каков", "какое", "какой", "какого", "какую", "когда", "ко",
    "ли", "между", "может", "на", "над", "но", "о", "об", "от", "по",
    "под", "почему", "при", "с", "со", "у", "что", "чтобы", "является",
}
_FUNCTION_WORD_EQUIVALENTS = {
    # Inflection or grammatical gender must not make an otherwise unchanged
    # question frame look novel.  Keep the groups narrow: content terms are
    # never normalized.
    "das": "de:article", "dem": "de:article", "den": "de:article",
    "der": "de:article", "des": "de:article", "die": "de:article",
    "welche": "de:welch", "welcher": "de:welch", "welches": "de:welch",
    "welchen": "de:welch",
    "cuál": "es:cual", "cuáles": "es:cual",
    "el": "romance:article", "la": "romance:article",
    "las": "romance:article", "los": "romance:article",
    "ce": "fr:demonstrative", "ces": "fr:demonstrative",
    "cette": "fr:demonstrative",
    "le": "romance:article", "les": "romance:article",
    "quel": "fr:quel", "quelle": "fr:quel", "quelles": "fr:quel",
    "quels": "fr:quel",
    "un": "article:indefinite", "une": "article:indefinite",
    "una": "article:indefinite",
    "какая": "ru:kakoi", "какие": "ru:kakoi", "каким": "ru:kakoi",
    "каков": "ru:kakoi", "какое": "ru:kakoi", "какой": "ru:kakoi",
    "какого": "ru:kakoi", "какую": "ru:kakoi",
}


@dataclass(frozen=True)
class QuestionDistance:
    """Transparent metrics and the conservative accept/reject decision."""

    substantially_different: bool
    reason: str
    character_similarity: float
    token_sequence_similarity: float
    retained_bigram_ratio: float
    token_multiset_distance: int


def assess_question_distance(
    original: str,
    candidate: str,
    intensity: object = DEFAULT_REWRITE_INTENSITY,
) -> QuestionDistance:
    """Return whether ``candidate`` meets the selected rewrite intensity.

    No language-specific stemming is used: required technical terms, names,
    numbers and negations remain intact.  Instead, several complementary
    surface metrics catch shallow edits. Old two-argument calls retain the
    conservative ``distinct`` behaviour. ``near`` intentionally permits a
    meaningful one-word recast because the user explicitly selected it.
    """

    selected = normalize_rewrite_intensity(intensity)
    original_tokens = _tokens(original)[:256]
    candidate_tokens = _tokens(candidate)[:256]
    original_text = " ".join(original_tokens)
    candidate_text = " ".join(candidate_tokens)

    if not original_tokens or not candidate_tokens:
        return _distance(False, "Eine Frage enthält keinen vergleichbaren Text.")

    character_similarity = SequenceMatcher(
        None, original_text[:4096], candidate_text[:4096], autojunk=True
    ).ratio()
    token_sequence_similarity = SequenceMatcher(
        None, original_tokens, candidate_tokens, autojunk=True
    ).ratio()
    retained_bigram_ratio = _retained_bigram_ratio(
        original_tokens, candidate_tokens
    )
    common_tokens = sum(
        (Counter(original_tokens) & Counter(candidate_tokens)).values()
    )
    token_multiset_distance = (
        len(original_tokens) + len(candidate_tokens) - (2 * common_tokens)
    )

    metrics = {
        "character_similarity": character_similarity,
        "token_sequence_similarity": token_sequence_similarity,
        "retained_bigram_ratio": retained_bigram_ratio,
        "token_multiset_distance": token_multiset_distance,
    }

    if original_text == candidate_text:
        return _distance(False, "Die Formulierung ist identisch.", **metrics)

    if _is_only_polite_wrapper_change(original_tokens, candidate_tokens):
        return _distance(
            False,
            "Es wurde lediglich eine Höflichkeits- oder Aufgabenhülle geändert.",
            **metrics,
        )

    if (
        min(len(original_tokens), len(candidate_tokens)) >= 4
        and (original_text in candidate_text or candidate_text in original_text)
    ):
        return _distance(
            False,
            "Eine Frage enthält die andere nahezu unverändert.",
            **metrics,
        )

    # At the gentlest explicitly selected level, any genuine textual recast is
    # sufficient. Exact/punctuation-only copies and wrappers containing the
    # complete original were already rejected above. Semantic fidelity and
    # answer leakage remain separate mandatory gates in result_parser.py.
    if selected == "near":
        if character_similarity >= 0.94 and token_multiset_distance <= 2:
            return _distance(
                False,
                "Die Änderung besteht nur aus einer sehr kleinen Form- oder Beugungsänderung.",
                **metrics,
            )
        return _distance(
            True,
            "Die Formulierung erfüllt die gewählte sanfte Änderungsstufe.",
            **metrics,
        )

    # ``light`` allows a familiar sentence frame and multi-word synonym recasts,
    # but not a single replaced token or a pure word-order shuffle.
    if selected == "light":
        if token_multiset_distance <= 2:
            return _distance(
                False,
                "Für diese Stufe wurde nur ein Wort ersetzt oder umgestellt.",
                **metrics,
            )
        if character_similarity >= 0.88 and token_multiset_distance <= 4:
            return _distance(
                False,
                "Wortlaut und Satzbild sind für diese Stufe noch zu ähnlich.",
                **metrics,
            )
        if token_sequence_similarity >= 0.90 and retained_bigram_ratio >= 0.82:
            return _distance(
                False,
                "Die ursprüngliche Wortfolge wurde fast vollständig übernommen.",
                **metrics,
            )
        return _distance(
            True,
            "Die Formulierung erfüllt die gewählte leichte Änderungsstufe.",
            **metrics,
        )

    # Reordering the same words or replacing at most two tokens is precisely
    # the photographic-memory failure mode this add-on is meant to avoid.
    if token_multiset_distance <= 4:
        return _distance(
            False,
            "Es wurden im Wesentlichen nur ein oder zwei Wörter ersetzt oder umgestellt.",
            **metrics,
        )

    # A high character match with at most three changed token pairs still looks
    # like the same card even when inflection creates a few distinct tokens.
    if character_similarity >= 0.80 and token_multiset_distance <= 6:
        return _distance(
            False,
            "Satzbild und Wortlaut sind noch nahezu identisch.",
            **metrics,
        )

    if token_sequence_similarity >= 0.78:
        return _distance(
            False,
            "Die ursprüngliche Wortfolge wurde weitgehend übernommen.",
            **metrics,
        )

    original_frame = _sentence_frame(original_tokens)
    candidate_frame = _sentence_frame(candidate_tokens)
    frame_similarity = 0.0
    if min(len(original_frame), len(candidate_frame)) >= 4:
        frame_similarity = SequenceMatcher(
            None, original_frame, candidate_frame, autojunk=True
        ).ratio()
        if frame_similarity >= 0.82:
            return _distance(
                False,
                "Das grammatische Fragegerüst blieb trotz Wortwechseln gleich.",
                **metrics,
            )

    if retained_bigram_ratio >= 0.78:
        return _distance(
            False,
            "Fast alle zusammenhängenden Wortgruppen stammen aus der Originalfrage.",
            **metrics,
        )

    if retained_bigram_ratio >= 0.54 and character_similarity >= 0.58:
        return _distance(
            False,
            "Zu viele zusammenhängende Wortgruppen stammen aus der Originalfrage.",
            **metrics,
        )

    shortest = min(len(original_tokens), len(candidate_tokens))
    longest = max(len(original_tokens), len(candidate_tokens))
    overlap_ratio = common_tokens / shortest
    if (
        shortest <= 6
        and longest <= shortest + 3
        and character_similarity >= 0.52
        and overlap_ratio >= 0.30
        and token_multiset_distance <= 6
    ):
        return _distance(
            False,
            "Die kurze Frage behält denselben sichtbaren Abrufhinweis.",
            **metrics,
        )

    if selected == "maximum":
        # ``maximum`` is deliberately a strict subset of ``distinct``. It must
        # first pass every default gate above, then show substantially lower
        # lexical, sequential and grammatical overlap.
        if token_multiset_distance <= 8 and common_tokens >= 3:
            return _distance(
                False,
                "Für die maximale Stufe wurden noch zu viele Wörter übernommen.",
                **metrics,
            )
        if character_similarity >= 0.70:
            return _distance(
                False,
                "Das sichtbare Satzbild ist für die maximale Stufe noch zu ähnlich.",
                **metrics,
            )
        if token_sequence_similarity >= 0.60:
            return _distance(
                False,
                "Die Wortfolge ist für die maximale Stufe noch zu ähnlich.",
                **metrics,
            )
        if frame_similarity >= 0.64:
            return _distance(
                False,
                "Das Fragegerüst ist für die maximale Stufe noch zu ähnlich.",
                **metrics,
            )
        if retained_bigram_ratio >= 0.34:
            return _distance(
                False,
                "Zu viele Wortgruppen wurden für die maximale Stufe übernommen.",
                **metrics,
            )
        if shortest <= 8 and overlap_ratio >= 0.45:
            return _distance(
                False,
                "Die kurze Frage teilt für die maximale Stufe zu viele Abrufhinweise.",
                **metrics,
            )
        return _distance(
            True,
            "Die Formulierung erfüllt die maximale Änderungsstufe.",
            **metrics,
        )

    return _distance(True, "Die Formulierung ist ausreichend verschieden.", **metrics)


def _tokens(value: str) -> tuple[str, ...]:
    without_media_labels = _MEDIA_LABEL_RE.sub(" ", value or "")
    return tuple(match.group(0).casefold() for match in _TOKEN_RE.finditer(without_media_labels))


def _retained_bigram_ratio(
    original: tuple[str, ...], candidate: tuple[str, ...]
) -> float:
    original_bigrams = Counter(zip(original, original[1:]))
    if not original_bigrams:
        return 0.0
    candidate_bigrams = Counter(zip(candidate, candidate[1:]))
    retained = sum((original_bigrams & candidate_bigrams).values())
    return retained / sum(original_bigrams.values())


def _sentence_frame(tokens: tuple[str, ...]) -> tuple[str, ...]:
    frame: list[str] = []
    for token in tokens:
        marker = (
            _FUNCTION_WORD_EQUIVALENTS.get(token, token)
            if token in _FUNCTION_WORDS
            else "*"
        )
        if marker == "*" and frame and frame[-1] == "*":
            continue
        frame.append(marker)
    return tuple(frame)


def _is_only_polite_wrapper_change(
    original: tuple[str, ...], candidate: tuple[str, ...]
) -> bool:
    """Detect a short prompt wrapper added around otherwise identical tokens."""

    shorter, longer = (original, candidate)
    if len(shorter) > len(longer):
        shorter, longer = longer, shorter
    if len(shorter) == len(longer):
        return False

    remaining = list(longer)
    for token in shorter:
        try:
            remaining.remove(token)
        except ValueError:
            return False
    return bool(remaining) and all(token in _POLITE_WRAPPER_WORDS for token in remaining)


def _distance(
    substantially_different: bool,
    reason: str,
    *,
    character_similarity: float = 0.0,
    token_sequence_similarity: float = 0.0,
    retained_bigram_ratio: float = 0.0,
    token_multiset_distance: int = 0,
) -> QuestionDistance:
    return QuestionDistance(
        substantially_different=substantially_different,
        reason=reason,
        character_similarity=character_similarity,
        token_sequence_similarity=token_sequence_similarity,
        retained_bigram_ratio=retained_bigram_ratio,
        token_multiset_distance=token_multiset_distance,
    )


__all__ = ["QuestionDistance", "assess_question_distance"]
