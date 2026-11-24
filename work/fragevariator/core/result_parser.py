from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from .intensity import DEFAULT_REWRITE_INTENSITY, normalize_rewrite_intensity
from .text import normalized_for_comparison
from .similarity import assess_question_distance
from ..i18n import tr


class GenerationParseError(ValueError):
    pass


class UnsupportedCardError(ValueError):
    pass


_INTERNAL_CONTENT_MARKER_RE = re.compile(
    r"\[(?:image(?:\s*:[^\]\r\n]*)?|audio|content-truncated)\]",
    re.IGNORECASE,
)
_HIDDEN_VISUAL_REFERENCE_RE = re.compile(
    r"(?:\b(?:"
    r"abbildung|bild|diagramm|grafik|screenshot|oben|unten|gezeigt|dargestellt|"
    r"image|picture|figure|diagram|screenshot|above|below|shown|displayed|"
    r"imagen|figura|gr[aá]fic[oa]|diagrama|captura|arriba|abajo|mostrad[oa]|"
    r"image|figure|sch[eé]ma|graphique|capture|dessus|dessous|montr[eé]e?|"
    r"изображени\w*|рисунк\w*|схем\w*|график\w*|скриншот\w*|"
    r"показан\w*|выше|ниже"
    r")\b|ci[- ]dessus|ci[- ]dessous)",
    re.IGNORECASE,
)


def _extract_json_object(raw: str) -> Dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        raise GenerationParseError(tr("parse.empty_response"))
    text = raw.strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise GenerationParseError(tr("parse.invalid_json"))


def _clean_string(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value).strip()
    return value[:max_length].rstrip()


def _clean_generated_content(value: Any, max_length: int) -> str:
    cleaned = _clean_string(value, max_length)
    cleaned = _INTERNAL_CONTENT_MARKER_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def parse_generation(
    raw: Any,
    original_question: str,
    answer_text: str,
    requested_count: int,
    intensity: object = DEFAULT_REWRITE_INTENSITY,
    *,
    front_image_present: bool = False,
) -> Dict[str, Any]:
    selected_intensity = normalize_rewrite_intensity(intensity)
    data = raw if isinstance(raw, dict) else _extract_json_object(raw)
    status = _clean_string(data.get("status"), 32).casefold()
    if status == "unsupported":
        reason = _clean_string(data.get("unsupported_reason"), 500)
        # A reason supplied by the model describes this particular card and
        # remains in the card's language.  Only Variator's fallback is UI text.
        raise UnsupportedCardError(reason or tr("parse.unsupported_default"))
    if status not in ("", "ok"):
        raise GenerationParseError(tr("parse.unknown_status", status=status))
    if type(data.get("is_equivalent")) is not bool:
        raise GenerationParseError(tr("parse.missing_equivalence_check"))
    if data["is_equivalent"] is not True:
        raise UnsupportedCardError(tr("parse.equivalence_unconfirmed"))
    if type(data.get("answer_not_revealed")) is not bool:
        raise GenerationParseError(tr("parse.missing_answer_leak_check"))
    if data["answer_not_revealed"] is not True:
        raise UnsupportedCardError(tr("parse.answer_revealed"))
    if type(data.get("is_substantially_different")) is not bool:
        raise GenerationParseError(tr("parse.missing_distance_check"))
    if data["is_substantially_different"] is not True:
        raise UnsupportedCardError(tr("parse.distance_unconfirmed"))
    change_strategy = _clean_string(data.get("change_strategy"), 64).casefold()
    if change_strategy not in {
        "completion_prompt",
        "changed_voice",
        "changed_perspective",
        "reordered_structure",
        "other",
    }:
        raise GenerationParseError(tr("parse.missing_change_strategy"))
    front_visual_mode = _clean_string(
        data.get("front_visual_mode"), 32
    ).casefold()
    self_contained = data.get(
        "variant_is_self_contained_without_front_visual"
    )
    if front_image_present:
        if front_visual_mode != "replace" or type(self_contained) is not bool:
            raise GenerationParseError(tr("parse.missing_visual_contract"))
        if self_contained is not True:
            raise GenerationParseError(tr("parse.inconsistent_visual_contract"))
    else:
        # Backward compatibility for text-only responses created by extensions
        # using the pre-visual contract. Production provider calls always use
        # the strict response schema and therefore explicitly return both.
        if not front_visual_mode:
            front_visual_mode = "none"
        if self_contained is None:
            self_contained = True
        if front_visual_mode != "none" or self_contained is not True:
            raise GenerationParseError(tr("parse.inconsistent_visual_contract"))
    core_aspect = _clean_generated_content(data.get("core_aspect"), 800)
    if not core_aspect:
        raise GenerationParseError(tr("parse.missing_core_aspect"))
    raw_variants = data.get("variants")
    if not isinstance(raw_variants, list):
        raise GenerationParseError(tr("parse.missing_variants"))
    comparable_original = _INTERNAL_CONTENT_MARKER_RE.sub(
        "", original_question or ""
    ).strip()
    original_norm = normalized_for_comparison(comparable_original)
    variants: List[str] = []
    rejected_as_too_similar = False
    rejected_for_answer_leak = False
    rejected_for_hidden_visual_reference = False
    seen = {original_norm} if original_norm else set()
    for item in raw_variants:
        if isinstance(item, dict):
            item = item.get("question", "")
        question = _clean_generated_content(item, 1200)
        normalized = normalized_for_comparison(question)
        if len(normalized) < 3 or normalized in seen:
            continue
        if original_norm:
            distance = assess_question_distance(
                comparable_original, question, selected_intensity
            )
            if not distance.substantially_different:
                rejected_as_too_similar = True
                continue
        elif not front_image_present:
            rejected_as_too_similar = True
            continue
        if front_image_present and _HIDDEN_VISUAL_REFERENCE_RE.search(question):
            rejected_for_hidden_visual_reference = True
            continue
        if _candidate_leaks_answer(original_question, answer_text, question):
            rejected_for_answer_leak = True
            continue
        if any(
            not assess_question_distance(
                existing, question, selected_intensity
            ).substantially_different
            for existing in variants
        ):
            rejected_as_too_similar = True
            continue
        seen.add(normalized)
        variants.append(question)
        if len(variants) >= requested_count:
            break
    if not variants:
        if rejected_for_answer_leak:
            raise UnsupportedCardError(tr("parse.answer_leak_local"))
        if rejected_for_hidden_visual_reference:
            raise UnsupportedCardError(tr("parse.hidden_visual_reference"))
        if rejected_as_too_similar:
            raise UnsupportedCardError(tr("parse.too_similar_local"))
        raise GenerationParseError(tr("parse.no_usable_question"))
    warnings: List[str] = []
    raw_warnings = data.get("warnings", [])
    if isinstance(raw_warnings, list):
        warnings.extend(w for w in (_clean_string(v, 500) for v in raw_warnings) if w)
    if len(variants) < requested_count:
        warnings.append(
            tr(
                "parse.partial_variants",
                actual=len(variants),
                requested=requested_count,
            )
        )
    answer_norm = normalized_for_comparison(answer_text)
    if 2 <= len(answer_norm.split()) <= 8 and len(answer_norm) <= 100:
        if any(answer_norm and answer_norm in normalized_for_comparison(v) and answer_norm not in original_norm for v in variants):
            warnings.append(tr("parse.possible_answer_leak"))
    return {
        "core_aspect": core_aspect,
        "variants": variants,
        "warnings": list(dict.fromkeys(warnings)),
        "front_visual_mode": front_visual_mode,
        "variant_is_self_contained_without_front_visual": self_contained,
    }


_LEAK_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_LEAK_STOP_WORDS = {
    "aber", "als", "auch", "auf", "aus", "bei", "das", "dass", "dem", "den",
    "der", "des", "die", "durch", "ein", "eine", "einer", "eines", "fuer", "für",
    "im", "in", "ist", "mit", "oder", "sind", "und", "von", "was", "welche",
    "welcher", "welches", "werden", "wird", "zu", "zum", "zur", "and", "are",
    "as", "at", "by", "for", "from", "in", "is", "of", "on", "or", "the",
    "to", "what", "which", "with",
    # Spanish function words.  These must not become supposed answer clues
    # merely because a rewrite uses a different grammatical construction.
    "algo", "ante", "aunque", "bajo", "cada", "como", "contra", "cual",
    "cuál", "cuando", "cuándo", "desde", "dentro", "donde", "dónde",
    "durante", "entre", "esta", "está", "estas", "este", "estos", "fuera",
    "hacia", "hasta", "para", "pero", "porque", "quien", "quién",
    "quienes", "según", "sobre", "toda", "todas", "todo", "todos", "tras",
    "unas", "unos",
    # French function words.
    "ainsi", "alors", "après", "aucun", "aucune", "avec", "avant", "cette",
    "chez", "comme", "dans", "depuis", "donc", "dont", "elle", "elles",
    "entre", "leur", "leurs", "mais", "même", "nous", "parce", "pendant",
    "pour", "pourtant", "quand", "quel", "quelle", "quelles", "quels",
    "sans", "selon", "sont", "sous", "tout", "tous", "très", "votre", "vous",
    # Russian function words and common relative forms.
    "более", "было", "быть", "ведь", "весь", "вдоль", "вместо", "внутри",
    "возле", "вокруг", "даже", "если", "есть", "когда", "которая", "которые",
    "который", "которых", "между", "может", "однако", "очень", "перед",
    "после", "потому", "почти", "свой", "среди", "также", "только", "через",
    "чтобы", "этой", "этот", "этих",
}


def _candidate_leaks_answer(original: str, answer: str, candidate: str) -> bool:
    """Reject answer words newly copied into a generated retrieval cue."""

    original_roots = set(_content_roots(original))
    answer_roots = [root for root in _content_roots(answer) if root not in original_roots]
    if not answer_roots:
        return False
    candidate_roots = set(_content_roots(candidate))
    leaked = set(answer_roots) & candidate_roots
    if len(leaked) >= 2:
        return True
    if leaked:
        only = next(iter(leaked))
        if any(char.isdigit() for char in only) or len(only) >= 8:
            return True

    answer_norm = normalized_for_comparison(answer)
    candidate_norm = normalized_for_comparison(candidate)
    if (
        answer_norm
        and answer_norm not in normalized_for_comparison(original)
        and len(answer_norm) <= 160
        and answer_norm in candidate_norm
    ):
        return True
    return False


def _content_roots(value: str) -> List[str]:
    roots: List[str] = []
    for match in _LEAK_TOKEN_RE.finditer(value or ""):
        token = match.group(0).casefold()
        if token in _LEAK_STOP_WORDS or len(token) < 4:
            continue
        roots.append(_light_root(token))
    return roots


def _light_root(token: str) -> str:
    for suffix in (
        "ungen", "ation", "ieren", "ischen", "ischer", "isches",
        "ern", "en", "er", "es", "e", "s",
    ):
        if token.endswith(suffix) and len(token) - len(suffix) >= 5:
            return token[: -len(suffix)]
    return token
