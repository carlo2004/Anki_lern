from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from typing import List, Tuple

from .intensity import DEFAULT_REWRITE_INTENSITY, normalize_rewrite_intensity


_SPACE_RE = re.compile(r"[\t\r\f\v ]+")
_SOUND_RE = re.compile(r"\[sound:[^\]]+\]", re.IGNORECASE)
_TYPE_ANSWER_RE = re.compile(r"(?:\[\[type:|id\s*=\s*['\"]?typeans)", re.IGNORECASE)

# Bump this whenever the acceptance policy for generated questions changes.
# Including the policy in the card fingerprint makes variants created under an
# older, weaker policy fail closed without deleting the user's database.
VARIANT_POLICY_VERSION = "structural-rewrite-v4-hidden-front-visuals"


class _VisibleTextParser(HTMLParser):
    _BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "div", "dl", "dt", "dd",
        "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
        "tr", "ul",
    }
    _SKIP_TAGS = {"noscript", "script", "style", "template"}
    _VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        tag = tag.lower()
        if self.skip_depth:
            if tag not in self._VOID_TAGS:
                self.skip_depth += 1
            return
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        style = "".join(attr_map.get("style", "").casefold().split())
        hidden = (
            "hidden" in attr_map
            or "inert" in attr_map
            or attr_map.get("aria-hidden", "").casefold() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
            or "visibility:collapse" in style
        )
        if tag in self._SKIP_TAGS or hidden:
            if tag not in self._VOID_TAGS:
                self.skip_depth = 1
            return
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "img":
            alt = attr_map.get("alt", "").strip()
            # Machine-readable, language-neutral metadata must not bias the
            # model towards the add-on UI language.
            self.parts.append("[image: %s]" % alt if alt else "[image]")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_depth:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(value: str, max_chars: int = 12000) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(value or "")
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value or "")
    text = _SOUND_RE.sub(" [audio] ", text)
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + " … [content-truncated]"
    return text


def source_hash(source_html: str) -> str:
    # Rendered whitespace can be meaningful in code, cloze-like layouts and
    # regular expressions. Only normalize transport-level line endings.
    normalized = (source_html or "").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def variant_source_hash(
    question_html: str,
    answer_html: str,
    rewrite_intensity: object = DEFAULT_REWRITE_INTENSITY,
) -> str:
    """Fingerprint card content together with the selected rewrite policy.

    The default keeps the 0.2.2 fingerprint stable, so existing strict
    variants remain usable. Other levels are isolated from one another and
    cannot leak through the persistent cache after a settings change.
    """

    selected = normalize_rewrite_intensity(rewrite_intensity)
    policy = VARIANT_POLICY_VERSION
    if selected != DEFAULT_REWRITE_INTENSITY:
        policy += ":" + selected
    return source_hash(
        policy + "\0" + (question_html or "") + "\0" + (answer_html or "")
    )


def answer_without_question(question_text: str, answer_text: str) -> str:
    question = _SPACE_RE.sub(" ", question_text.replace("\n", " ")).strip()
    answer = answer_text.strip()
    single_line_answer = _SPACE_RE.sub(" ", answer.replace("\n", " ")).strip()
    if question and single_line_answer.casefold().startswith(question.casefold()):
        remainder = single_line_answer[len(question):].lstrip(" -–—:|\n")
        return remainder or answer
    return answer


def has_typed_answer(source_html: str) -> bool:
    return bool(_TYPE_ANSWER_RE.search(source_html or ""))


def has_front_media(source_html: str) -> bool:
    source = source_html or ""
    return bool(
        re.search(r"<\s*(?:img|audio|video|object|iframe)\b", source, re.IGNORECASE)
        or _SOUND_RE.search(source)
        or re.search(r"\{\{\s*tts\b", source, re.IGNORECASE)
    )


def normalized_for_comparison(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return _SPACE_RE.sub(" ", value).strip()
