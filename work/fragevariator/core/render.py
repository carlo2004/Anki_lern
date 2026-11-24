from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from ..i18n import tr
from .text import html_to_text


_STYLE = """<style>
.fv-media{display:flex;flex-wrap:wrap;justify-content:center;gap:.65rem;margin:0 0 1rem}.fv-media img{display:block;max-width:100%;max-height:70vh;object-fit:contain}
.fv-answer-original{max-width:52rem;margin:1.15rem auto 0;padding:.55rem .75rem;text-align:left;border-left:2px solid rgba(120,130,145,.32);background:rgba(120,130,145,.06);border-radius:.2rem;clear:both}
.fv-answer-original[data-fv-original-front][hidden]{display:none!important}
.fv-answer-original img{display:block;max-width:100%;max-height:55vh;object-fit:contain;margin:.35rem auto}
.fv-answer-label{font:500 .7rem/1.3 system-ui,sans-serif;color:#667085;margin-bottom:.25rem;letter-spacing:.01em}
.nightMode .fv-answer-label,.night_mode .fv-answer-label{color:#aeb7c4}
.fv-answer-question{font:inherit;color:inherit}
.fv-answer-prompt{display:block!important;margin:0 auto 1rem!important;padding:0!important;clear:both;text-align:inherit;color:inherit;font:inherit}
</style>"""

_MAX_TEMPLATE_STYLE_CHARS = 128_000
_MAX_QUESTION_SHELL_DEPTH = 12
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_VISIBLE_ANSWER_MARKUP = re.compile(
    r"<(?:a|anki-mathjax|audio|canvas|iframe|img|math|object|svg|video)\b",
    re.IGNORECASE,
)

_QUESTION_SHELL_TAGS = {
    "article", "b", "blockquote", "caption", "center", "code", "dd", "div", "dl",
    "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "i",
    "kbd", "li", "main", "ol", "p", "pre", "ruby", "rt", "s",
    "section", "small", "span", "strong", "sub", "sup", "table", "tbody",
    "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
_QUESTION_SKIP_TAGS = {
    "canvas", "iframe", "noscript", "object", "script", "style", "svg",
    "template",
}
_QUESTION_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
_QUESTION_CONTEXT_REQUIRED_TAGS = {
    "caption": {"table"},
    "dd": {"dl"},
    "dt": {"dl"},
    "li": {"ol", "ul"},
    "rt": {"ruby"},
    "tbody": {"table"},
    "td": {"tr"},
    "tfoot": {"table"},
    "th": {"tr"},
    "thead": {"table"},
    "tr": {"table", "tbody", "tfoot", "thead"},
}
_SAFE_STYLE_PROPERTIES = {
    "align-content", "align-items", "align-self", "background-color",
    "border", "border-color", "border-radius", "border-style", "border-width",
    "box-sizing", "color", "direction", "display", "flex", "flex-basis",
    "flex-direction", "flex-grow", "flex-shrink", "flex-wrap", "font",
    "font-family", "font-feature-settings", "font-kerning", "font-optical-sizing",
    "font-size", "font-stretch", "font-style", "font-variant", "font-weight",
    "gap", "grid-column", "grid-row", "justify-content", "justify-self",
    "letter-spacing", "line-height", "margin", "margin-block", "margin-block-end",
    "margin-block-start", "margin-bottom", "margin-inline", "margin-inline-end",
    "margin-inline-start", "margin-left", "margin-right", "margin-top", "max-width",
    "min-width", "overflow-wrap", "padding", "padding-block", "padding-block-end",
    "padding-block-start", "padding-bottom", "padding-inline", "padding-inline-end",
    "padding-inline-start", "padding-left", "padding-right", "padding-top",
    "tab-size", "text-align", "text-decoration", "text-indent", "text-transform",
    "text-underline-offset", "unicode-bidi", "vertical-align", "white-space",
    "width", "word-break", "word-spacing", "writing-mode",
}

_CSS_NUMBER = re.compile(
    r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(%?)"
)
_CSS_VISIBLE_GLOBAL_VALUES = {
    "inherit", "initial", "revert", "revert-layer", "unset",
}
_CSS_VISIBLE_DISPLAY_VALUES = {
    "-webkit-box", "-webkit-inline-box", "block", "contents", "flex",
    "flow-root", "grid", "inline", "inline-block", "inline-flex",
    "inline-grid", "inline-table", "list-item", "ruby", "ruby-base",
    "ruby-base-container", "ruby-text", "ruby-text-container", "run-in",
    "table", "table-caption", "table-cell", "table-column",
    "table-column-group", "table-footer-group", "table-header-group",
    "table-row", "table-row-group",
}
_CSS_VISIBLE_DISPLAY_COMBINATIONS = {
    "block flex", "block flow", "block flow-root", "block grid", "block ruby",
    "inline flex", "inline flow", "inline flow-root", "inline grid", "inline ruby",
    "block flow list-item", "block flow-root list-item",
    "inline flow list-item", "inline flow-root list-item",
}
_QUESTION_SHELL_RESET = (
    "position:static!important;inset:auto!important;"
    "transform:none!important;translate:none!important;rotate:none!important;"
    "scale:none!important;float:none!important;"
    "visibility:visible!important;opacity:1!important"
)
_QUESTION_FONT_RESET = "font-size:inherit!important"
_QUESTION_TEMPLATE_STYLE_PROPERTIES = {
    "background-color", "color", "direction", "font", "font-family",
    "font-feature-settings", "font-kerning", "font-optical-sizing",
    "font-size", "font-stretch", "font-style", "font-variant", "font-weight",
    "letter-spacing", "line-height", "overflow-wrap", "tab-size",
    "text-align", "text-decoration", "text-indent", "text-shadow",
    "text-transform", "text-underline-offset", "unicode-bidi", "vertical-align",
    "white-space", "word-break", "word-spacing", "writing-mode",
}
_SEMANTIC_DISPLAY = {
    "b": "inline", "caption": "table-caption", "code": "inline",
    "em": "inline", "font": "inline", "i": "inline", "img": "block",
    "kbd": "inline", "li": "list-item", "rt": "ruby-text",
    "ruby": "ruby", "s": "inline", "span": "inline", "strong": "inline",
    "sub": "inline", "summary": "list-item", "sup": "inline",
    "table": "table", "tbody": "table-row-group", "td": "table-cell",
    "tfoot": "table-footer-group", "th": "table-cell",
    "thead": "table-header-group", "tr": "table-row", "u": "inline",
}
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_IDENTIFIER_TEXT = r"[A-Za-z_][A-Za-z0-9_-]{0,63}"
_CSS_STATIC_COMPOUND = re.compile(
    r"(?:(?:[A-Za-z_][A-Za-z0-9_-]{0,63})|\*)?"
    r"(?:[.#][A-Za-z_][A-Za-z0-9_-]{0,63})*"
)
_SelectorAttributes = tuple[tuple[str, str | None], ...]
_SelectorTarget = tuple[str, str, frozenset[str], _SelectorAttributes]
_SelectorSpecificity = tuple[int, int, int]
_VisibilityRule = tuple[
    _SelectorTarget, str, bool, bool, _SelectorSpecificity, int, bool
]


def _plain_text_html(value: str) -> str:
    return html.escape(value, quote=False).replace("\n", "<br>")


class _LeadingStyleCollector(HTMLParser):
    """Collect only the template style blocks before the card's content.

    Anki prepends the note type's CSS to ``card.question()``.  Replacing the
    rendered front while dropping that CSS also drops the user's font size,
    alignment, colours and responsive rules.  Parsing the leading tags means
    no script, event attribute or question markup is copied into the variant.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.styles: list[str] = []
        self._current: list[str] | None = None
        self._stopped = False
        self._size = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _ = attrs
        if self._stopped:
            return
        if self._current is None and tag.casefold() == "style":
            self._current = []
            return
        # A style element is raw text in HTML, so a nested start tag here can
        # only occur after a literal closing </style>.  Do not copy it.
        self._stopped = True
        self._current = None

    def handle_endtag(self, tag: str) -> None:
        if self._stopped:
            return
        if tag.casefold() == "style" and self._current is not None:
            value = "".join(self._current).replace("\x00", "")
            remaining = _MAX_TEMPLATE_STYLE_CHARS - self._size
            if remaining > 0:
                value = value[:remaining]
                self.styles.append(value)
                self._size += len(value)
            self._current = None
            return
        self._stopped = True
        self._current = None

    def handle_data(self, data: str) -> None:
        if self._stopped:
            return
        if self._current is not None:
            self._current.append(data)
        elif data.strip():
            self._stopped = True

    def handle_comment(self, data: str) -> None:
        if self._current is not None:
            # Legacy note types sometimes wrap CSS in an HTML comment.
            self._current.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._current is not None:
            self._current.append("&%s;" % name)

    def handle_charref(self, name: str) -> None:
        if self._current is not None:
            self._current.append("&#%s;" % name)


def _leading_template_styles(original_html: str) -> list[str]:
    parser = _LeadingStyleCollector()
    try:
        parser.feed((original_html or "").lstrip("\ufeff"))
        parser.close()
    except Exception:
        return []
    return parser.styles


class _AllStyleCollector(HTMLParser):
    """Collect bounded CSS from every style element for visibility checks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.styles: list[str] = []
        self._current: list[str] | None = None
        self._size = 0

    def _finish_current(self) -> None:
        if self._current is None:
            return
        value = "".join(self._current).replace("\x00", "")
        remaining = _MAX_TEMPLATE_STYLE_CHARS - self._size
        if remaining > 0:
            value = value[:remaining]
            self.styles.append(value)
            self._size += len(value)
        self._current = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _ = attrs
        if tag.casefold() == "style" and self._current is None:
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "style":
            self._finish_current()

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)

    def handle_comment(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._current is not None:
            self._current.append("&%s;" % name)

    def handle_charref(self, name: str) -> None:
        if self._current is not None:
            self._current.append("&#%s;" % name)

    def finish(self) -> list[str]:
        self._finish_current()
        return self.styles


def _all_template_styles(original_html: str) -> list[str]:
    parser = _AllStyleCollector()
    try:
        parser.feed(original_html or "")
        parser.close()
    except Exception:
        return []
    return parser.finish()


def _template_styles_html(styles: list[str]) -> str:
    return "".join("<style>%s</style>" % value for value in styles)


def _leading_template_styles_html(original_html: str) -> str:
    return _template_styles_html(_leading_template_styles(original_html))


def _css_block_sequence(source: str) -> list[tuple[str, str]]:
    """Return every complete block at the current CSS nesting level."""

    blocks: list[tuple[str, str]] = []
    start = 0
    index = 0
    size = len(source)
    while index < size:
        if source.startswith("/*", index):
            closing = source.find("*/", index + 2)
            index = size if closing < 0 else closing + 2
            continue
        character = source[index]
        if character in {'"', "'"}:
            quote = character
            index += 1
            while index < size:
                if source[index] == "\\":
                    index += 2
                elif source[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            continue
        if character == ";":
            # Top-level @charset/@import/custom statements must not become
            # part of the selector that follows.
            start = index + 1
            index += 1
            continue
        if character != "{":
            index += 1
            continue

        prelude = _CSS_COMMENT.sub("", source[start:index]).strip()
        body_start = index + 1
        depth = 1
        index = body_start
        while index < size and depth:
            if source.startswith("/*", index):
                closing = source.find("*/", index + 2)
                index = size if closing < 0 else closing + 2
                continue
            character = source[index]
            if character in {'"', "'"}:
                quote = character
                index += 1
                while index < size:
                    if source[index] == "\\":
                        index += 2
                    elif source[index] == quote:
                        index += 1
                        break
                    else:
                        index += 1
                continue
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
            index += 1
        if depth:
            break
        if prelude:
            blocks.append((prelude, source[body_start:index - 1]))
        start = index
    return blocks


def _css_top_level_blocks(source: str) -> list[tuple[str, str]]:
    """Return non-at-rule blocks without descending into conditional CSS."""

    return [
        (prelude, body)
        for prelude, body in _css_block_sequence(source)
        if not prelude.startswith("@")
    ]


_CSS_DECLARATION_AT_RULES = {
    "@color-profile", "@counter-style", "@font-face", "@font-feature-values",
    "@page", "@property",
}


def _css_visibility_blocks(
    source: str,
    *,
    conditional: bool = False,
    depth: int = 0,
) -> list[tuple[str, str, bool]]:
    """Return ordinary rules, including rules nested in conditional at-rules.

    A card can hide answer or hint content only at a particular viewport size,
    colour scheme, or feature set.  Variator cannot reproduce WebEngine's full
    cascade while rendering a passive fragment, so nested rules are marked as
    conditional and may hide matching content but may never reveal it.
    """

    if depth >= 32:
        return []
    blocks: list[tuple[str, str, bool]] = []
    for prelude, body in _css_block_sequence(source):
        folded = prelude.lstrip().casefold()
        if folded.startswith("@"):
            at_name = folded.split(None, 1)[0]
            if (
                at_name in _CSS_DECLARATION_AT_RULES
                or at_name.endswith("keyframes")
            ):
                continue
            blocks.extend(
                _css_visibility_blocks(
                    body,
                    conditional=True,
                    depth=depth + 1,
                )
            )
            continue
        blocks.append((prelude, body, conditional))
        # CSS nesting is increasingly common in modern note templates.  Any
        # nested selector is context-dependent from our point of view.
        if "{" in body:
            blocks.extend(
                _css_visibility_blocks(
                    body,
                    conditional=True,
                    depth=depth + 1,
                )
            )
    return blocks


def _css_declaration_chunks(body: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    index = 0
    size = len(body)
    quote = ""
    parentheses = 0
    while index < size:
        if not quote and body.startswith("/*", index):
            closing = body.find("*/", index + 2)
            index = size if closing < 0 else closing + 2
            continue
        character = body[index]
        if quote:
            current.append(character)
            if character == "\\" and index + 1 < size:
                index += 1
                current.append(body[index])
            elif character == quote:
                quote = ""
        elif character in {'"', "'"}:
            quote = character
            current.append(character)
        elif character == "(":
            parentheses += 1
            current.append(character)
        elif character == ")":
            parentheses = max(0, parentheses - 1)
            current.append(character)
        elif character == ";" and not parentheses:
            chunks.append("".join(current))
            current = []
        else:
            current.append(character)
        index += 1
    chunks.append("".join(current))
    return chunks


def _css_selector_chunks(group: str) -> list[str]:
    """Split a selector list without splitting commas inside :is()/attrs."""

    chunks: list[str] = []
    current: list[str] = []
    quote = ""
    round_depth = 0
    square_depth = 0
    escaped = False
    for character in group:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\":
            current.append(character)
            escaped = True
            continue
        if quote:
            current.append(character)
            if character == quote:
                quote = ""
            continue
        if character in {'"', "'"}:
            quote = character
            current.append(character)
        elif character == "(":
            round_depth += 1
            current.append(character)
        elif character == ")":
            round_depth = max(0, round_depth - 1)
            current.append(character)
        elif character == "[":
            square_depth += 1
            current.append(character)
        elif character == "]":
            square_depth = max(0, square_depth - 1)
            current.append(character)
        elif character == "," and not round_depth and not square_depth:
            chunks.append("".join(current))
            current = []
        else:
            current.append(character)
    chunks.append("".join(current))
    return chunks


_CSS_VISIBLE_FONT_SIZE_KEYWORDS = {
    "xx-small", "x-small", "small", "medium", "large", "x-large",
    "xx-large", "xxx-large", "smaller", "larger",
}
_CSS_SYSTEM_FONT_KEYWORDS = {
    "caption", "icon", "menu", "message-box", "small-caption", "status-bar",
}


def _css_color_is_hidden(value: str) -> bool | None:
    compact = "".join(value.casefold().split())
    if compact == "transparent":
        return True
    if compact in _CSS_VISIBLE_GLOBAL_VALUES or compact == "currentcolor":
        return False
    if re.fullmatch(r"#[0-9a-f]{3}", compact):
        return False
    if re.fullmatch(r"#[0-9a-f]{4}", compact):
        return compact[-1] == "0"
    if re.fullmatch(r"#[0-9a-f]{6}", compact):
        return False
    if re.fullmatch(r"#[0-9a-f]{8}", compact):
        return compact[-2:] == "00"
    if re.fullmatch(r"[a-z-]+", compact):
        # CSS named colours are opaque except for the handled transparent
        # keyword. Unknown identifiers are invalid and cannot override a
        # previous valid declaration in the browser, so treating them as
        # visible preserves the previous cascade winner below.
        return False
    if "var(" in compact or "env(" in compact:
        return None
    function = re.fullmatch(r"([a-z-]+)\((.*)\)", compact, re.DOTALL)
    if function is None:
        return None
    name, arguments = function.groups()
    if name not in {
        "color", "color-mix", "hsl", "hsla", "hwb", "lab", "lch",
        "light-dark", "oklab", "oklch", "rgb", "rgba",
    }:
        return None
    if name in {"color-mix", "light-dark"}:
        # Resolving these requires the computed colour space/theme and can
        # legitimately yield a fully transparent result. Opaque/dynamic mixes
        # are left undecided so a normal CSS-variable theme does not suppress
        # the entire card, while an explicit transparent input fails closed.
        return True if "transparent" in arguments else None
    alpha = ""
    if "/" in arguments:
        alpha = arguments.rsplit("/", 1)[1]
    elif name in {"rgba", "hsla"} and "," in arguments:
        alpha = arguments.rsplit(",", 1)[1]
    if alpha:
        alpha = alpha.strip()
        constant_alpha = _css_constant_number(alpha)
        if constant_alpha is None:
            return None
        return constant_alpha <= 0
    return False


def _css_constant_length(value: str) -> tuple[float, str | None] | None:
    match = re.fullmatch(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))(px|pt|em|rem|vw|vh|%)?",
        value,
    )
    if match is not None:
        return float(match.group(1)), match.group(2)
    function = re.fullmatch(r"(calc|min|max|clamp)\((.*)\)", value)
    if function is None or "var(" in value or "env(" in value:
        return None
    function_name, expression = function.groups()
    if function_name == "calc":
        compact_expression = "".join(expression.split())
        token_matches = list(
            re.finditer(
                r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:px|pt|em|rem|vw|vh|%)?",
                compact_expression,
            )
        )
        if token_matches and "".join(
            match.group(0) for match in token_matches
        ) == compact_expression:
            parsed_terms = [
                re.fullmatch(
                    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))"
                    r"(px|pt|em|rem|vw|vh|%)?",
                    match.group(0),
                )
                for match in token_matches
            ]
            if all(term is not None for term in parsed_terms):
                concrete_terms = [term for term in parsed_terms if term is not None]
                nonzero_units = {
                    term.group(2)
                    for term in concrete_terms
                    if float(term.group(1)) != 0
                }
                if len(nonzero_units) <= 1:
                    unit = next(iter(nonzero_units), None)
                    total = sum(float(term.group(1)) for term in concrete_terms)
                    return total, unit
    else:
        arguments = [
            _css_constant_length(part.strip())
            for part in _css_selector_chunks(expression)
        ]
        if arguments and all(argument is not None for argument in arguments):
            concrete = [argument for argument in arguments if argument is not None]
            units = {unit for number, unit in concrete if number != 0}
            if len(units) <= 1:
                unit = next(iter(units), None)
                numbers = [number for number, _unit in concrete]
                if function_name == "min":
                    return min(numbers), unit
                if function_name == "max":
                    return max(numbers), unit
                if function_name == "clamp" and len(numbers) == 3:
                    return max(numbers[0], min(numbers[1], numbers[2])), unit
    return None


def _css_constant_number(value: str) -> float | None:
    constant = _css_constant_length(value)
    if constant is None:
        return None
    number, unit = constant
    if unit not in {None, "%"}:
        return None
    return number


def _css_sized_value_is_hidden(
    value: str,
    thresholds: dict[str | None, float],
) -> bool | None:
    constant = _css_constant_length(value)
    if constant is not None:
        number, unit = constant
        return number <= thresholds.get(unit, 0)
    function = re.fullmatch(r"(?:calc|min|max|clamp)\((.*)\)", value)
    if function is None or "var(" in value or "env(" in value:
        return None
    expression = function.group(1)
    terms = re.findall(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))(px|pt|em|rem|vw|vh|%)?",
        expression,
    )
    if not terms:
        return None
    return all(
        abs(float(number)) <= thresholds.get(unit or None, 0)
        for number, unit in terms
    )


def _css_length_is_offscreen(value: str) -> bool:
    constant = _css_constant_length(value)
    if constant is None:
        return False
    number, unit = constant
    thresholds = {
        None: 100, "px": 100, "pt": 75, "em": 10, "rem": 10,
        "vw": 10, "vh": 10, "%": 100,
    }
    return abs(number) >= thresholds[unit]


def _visibility_declarations(body: str) -> list[tuple[str, bool, bool]]:
    declarations: list[tuple[str, bool, bool]] = []
    for chunk in _css_declaration_chunks(body):
        if ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        name = name.strip().casefold()
        if name not in {
            "-webkit-text-fill-color", "bottom", "clip", "clip-path", "color",
            "content-visibility", "display", "filter", "font", "font-size",
            "height", "left", "max-height", "max-width", "opacity", "right",
            "scale", "text-indent", "top", "transform", "visibility", "width",
        }:
            continue
        value = value.strip()
        important_match = re.search(r"\s*!\s*important\s*$", value, re.IGNORECASE)
        important = important_match is not None
        if important_match is not None:
            value = value[:important_match.start()].strip()
        normalized = " ".join(value.casefold().split())
        if name == "display":
            if normalized == "none":
                hidden = True
            elif (
                normalized in _CSS_VISIBLE_GLOBAL_VALUES
                or normalized in _CSS_VISIBLE_DISPLAY_VALUES
                or normalized in _CSS_VISIBLE_DISPLAY_COMBINATIONS
            ):
                hidden = False
            else:
                # Unknown/dynamic values do not override an earlier proven
                # hidden declaration, but neither should a normal CSS variable
                # disable an otherwise visible screenshot card by itself.
                continue
        elif name == "visibility":
            if normalized in {"hidden", "collapse"}:
                hidden = True
            elif normalized == "visible" or normalized in _CSS_VISIBLE_GLOBAL_VALUES:
                hidden = False
            else:
                continue
        elif name == "opacity":
            match = _CSS_NUMBER.fullmatch(normalized)
            if match is None:
                if normalized in _CSS_VISIBLE_GLOBAL_VALUES:
                    hidden = False
                else:
                    constant_opacity = _css_constant_number(normalized)
                    if constant_opacity is None:
                        continue
                    hidden = constant_opacity <= 0
            else:
                numeric = float(normalized[:-1] if match.group(1) else normalized)
                hidden = numeric <= 0
        elif name in {"color", "-webkit-text-fill-color"}:
            color_hidden = _css_color_is_hidden(normalized)
            if color_hidden is None:
                continue
            hidden = color_hidden
        elif name == "content-visibility":
            if normalized == "hidden":
                hidden = True
            elif normalized in {"auto", "visible"} | _CSS_VISIBLE_GLOBAL_VALUES:
                hidden = False
            else:
                continue
        elif name in {"width", "height", "max-width", "max-height"}:
            if normalized in _CSS_VISIBLE_GLOBAL_VALUES or normalized in {"auto", "none"}:
                hidden = False
            else:
                sized_hidden = _css_sized_value_is_hidden(
                    normalized,
                    {
                        None: 0, "px": 0, "pt": 0, "em": 0, "rem": 0,
                        "vw": 0, "vh": 0, "%": 0,
                    },
                )
                if sized_hidden is None:
                    continue
                hidden = sized_hidden
        elif name in {"left", "right", "top", "bottom"}:
            if normalized in _CSS_VISIBLE_GLOBAL_VALUES or normalized == "auto":
                hidden = False
            else:
                if _css_constant_length(normalized) is None:
                    continue
                hidden = _css_length_is_offscreen(normalized)
        elif name == "scale":
            if normalized in _CSS_VISIBLE_GLOBAL_VALUES or normalized == "none":
                hidden = False
            else:
                constant_scale = _css_constant_number(normalized)
                if constant_scale is not None:
                    hidden = constant_scale <= 0
                    property_name = name
                    declarations.append((property_name, hidden, important))
                    continue
                factors = re.findall(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", normalized)
                if not factors or "var(" in normalized or "env(" in normalized:
                    continue
                hidden = any(float(value) == 0 for value in factors)
        elif name == "transform":
            if normalized in _CSS_VISIBLE_GLOBAL_VALUES or normalized == "none":
                hidden = False
            else:
                compact = "".join(normalized.split())
                if "var(" in compact or "env(" in compact:
                    continue
                scale_groups = re.findall(
                    r"scale(?:x|y|3d)?\(([^)]*)\)", compact
                )
                hidden = bool(
                    any(
                        (
                            _css_constant_number(group) is not None
                            and _css_constant_number(group) <= 0
                        )
                        or any(
                            float(value) == 0
                            for value in re.findall(
                                r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", group
                            )
                        )
                        for group in scale_groups
                    )
                    or any(
                        _css_length_is_offscreen(value)
                        for value in re.findall(
                            r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:px|pt|em|rem|vw|vh|%)",
                            compact,
                        )
                    )
                )
        elif name == "filter":
            if normalized in _CSS_VISIBLE_GLOBAL_VALUES or normalized == "none":
                hidden = False
            else:
                compact = "".join(normalized.split())
                hidden = bool(
                    re.search(r"opacity\((?:0(?:\.0+)?|0(?:\.0+)?%)\)", compact)
                )
        elif name in {"clip", "clip-path"}:
            if normalized in _CSS_VISIBLE_GLOBAL_VALUES or normalized in {"auto", "none"}:
                hidden = False
            else:
                compact = "".join(normalized.split())
                hidden = bool(
                    re.fullmatch(r"rect\(0(?:px)?,?0(?:px)?,?0(?:px)?,?0(?:px)?\)", compact)
                    or re.match(r"(?:circle|ellipse)\(0(?:px|%)?", compact)
                    or re.fullmatch(r"inset\(50%(?:50%){0,3}\)", compact)
                )
        elif name == "font-size":
            if (
                normalized in _CSS_VISIBLE_GLOBAL_VALUES
                or normalized in _CSS_VISIBLE_FONT_SIZE_KEYWORDS
            ):
                hidden = False
            else:
                sized_hidden = _css_sized_value_is_hidden(
                    normalized,
                    {
                        None: 0, "px": 1, "pt": 0.75, "em": 0.1,
                        "rem": 0.1, "vw": 0.1, "vh": 0.1, "%": 10,
                    },
                )
                if sized_hidden is None:
                    continue
                hidden = sized_hidden
        elif name == "font":
            if (
                normalized in _CSS_VISIBLE_GLOBAL_VALUES
                or normalized in _CSS_SYSTEM_FONT_KEYWORDS
            ):
                hidden = False
            else:
                keyword_match = re.search(
                    r"(?<![\w-])(?:xx-small|x-small|small|medium|large|x-large|"
                    r"xx-large|xxx-large|smaller|larger)(?=\s|/|$)",
                    normalized,
                )
                size_match = re.search(
                    r"(?<![\w.-])((?:\d+(?:\.\d*)?|\.\d+)"
                    r"(?:px|pt|em|rem|%)?)(?=\s|/|$)",
                    normalized,
                )
                function_match = re.search(
                    r"(?:calc|min|max|clamp)\([^)]*\)", normalized
                )
                if keyword_match is not None:
                    hidden = False
                elif function_match is not None:
                    sized_hidden = _css_sized_value_is_hidden(
                        function_match.group(0),
                        {
                            None: 0, "px": 1, "pt": 0.75, "em": 0.1,
                            "rem": 0.1, "vw": 0.1, "vh": 0.1, "%": 10,
                        },
                    )
                    if sized_hidden is None:
                        continue
                    hidden = sized_hidden
                elif size_match is None:
                    continue
                else:
                    size = size_match.group(1)
                    numeric_match = re.fullmatch(
                        r"(\d+(?:\.\d*)?|\.\d+)(px|pt|em|rem|%)?", size
                    )
                    assert numeric_match is not None
                    numeric = float(numeric_match.group(1))
                    unit = numeric_match.group(2)
                    thresholds = {
                        None: 0, "px": 1, "pt": 0.75,
                        "em": 0.1, "rem": 0.1, "%": 10,
                    }
                    hidden = numeric <= thresholds[unit]
        else:
            if normalized in _CSS_VISIBLE_GLOBAL_VALUES or normalized == "0":
                hidden = False
            else:
                if _css_constant_length(normalized) is None:
                    continue
                hidden = _css_length_is_offscreen(normalized)
        # ``font`` resets ``font-size`` and participates in the same cascade
        # slot for the only font characteristic relevant here.
        property_name = "font-size" if name == "font" else name
        declarations.append((property_name, hidden, important))
    return declarations


def _font_size_is_risky(raw_value: str) -> bool:
    value = re.sub(
        r"\s*!\s*important\s*$", "", raw_value, flags=re.IGNORECASE
    ).strip().casefold()
    compact = "".join(value.split())
    if compact in {"xx-small", "x-small", "smaller"}:
        return True
    if compact in {
        "inherit", "initial", "large", "larger", "medium", "revert",
        "revert-layer", "small", "unset", "x-large", "xx-large", "xxx-large",
    }:
        return False
    match = re.fullmatch(
        r"(\d+(?:\.\d*)?|\.\d+)(px|pt|em|rem|%)?", compact
    )
    if match is None:
        # Dynamic values can still resolve to a tiny font. Omitting one
        # presentation class is safer than reproducing an unreadable prompt.
        return True
    numeric = float(match.group(1))
    unit = match.group(2)
    if unit is None:
        # CSS accepts a unitless font-size only for zero. Non-zero values are
        # invalid and must not cancel an earlier valid tiny-font declaration.
        return True
    thresholds = {"px": 12, "pt": 9, "em": 0.75, "rem": 0.75, "%": 75}
    return numeric < thresholds[unit]


def _font_shorthand_is_risky(raw_value: str) -> bool:
    value = re.sub(
        r"\s*!\s*important\s*$", "", raw_value, flags=re.IGNORECASE
    ).strip().casefold()
    if value in _CSS_VISIBLE_GLOBAL_VALUES or value in {
        "caption", "icon", "menu", "message-box", "small-caption", "status-bar",
    }:
        return False
    numeric_size = re.search(
        r"(?<![\w.-])((?:\d+(?:\.\d*)?|\.\d+)(?:px|pt|em|rem|%))"
        r"(?=\s|/|$)",
        value,
    )
    if numeric_size is not None:
        return _font_size_is_risky(numeric_size.group(1))
    keyword_size = re.search(
        r"(?<![\w-])(xx-small|x-small|small|medium|large|x-large|"
        r"xx-large|xxx-large|larger|smaller)(?![\w-])",
        value,
    )
    if keyword_size is not None:
        return _font_size_is_risky(keyword_size.group(1))
    return True


def _risky_inline_font_properties(body: str) -> frozenset[str]:
    risky: set[str] = set()
    for chunk in _css_declaration_chunks(body):
        if ":" not in chunk:
            continue
        name, raw_value = chunk.split(":", 1)
        name = name.strip().casefold()
        if name == "font-size" and _font_size_is_risky(raw_value):
            risky.add(name)
        elif name == "font" and _font_shorthand_is_risky(raw_value):
            risky.add(name)
    return frozenset(risky)


def _unsafe_question_layout(body: str) -> frozenset[str]:
    """Return risky presentation categories in a declaration block."""

    risks: set[str] = set()
    for chunk in _css_declaration_chunks(body):
        if ":" not in chunk:
            continue
        name, raw_value = chunk.split(":", 1)
        name = name.strip().casefold()
        value = re.sub(
            r"\s*!\s*important\s*$", "", raw_value, flags=re.IGNORECASE
        ).strip().casefold()
        compact = "".join(value.split())
        if name == "position" and compact in {"absolute", "fixed", "sticky"}:
            risks.add("layout")
        if name in {
            "bottom", "inset", "inset-block", "inset-block-end",
            "inset-block-start", "inset-inline", "inset-inline-end",
            "inset-inline-start", "left", "right", "top",
        } and compact not in {"", "auto", "initial", "unset"}:
            risks.add("layout")
        if name in {"rotate", "scale", "transform", "translate"} and compact not in {
            "", "none", "initial", "unset",
        }:
            risks.add("layout")
        if name == "float" and compact not in {"", "none", "initial", "unset"}:
            risks.add("layout")
        if name == "font-size":
            if _font_size_is_risky(raw_value):
                risks.add("font-size")
        elif name == "font" and _font_shorthand_is_risky(raw_value):
            risks.add("font-size")
    return frozenset(risks)


def _terminal_visibility_selector(
    selector: str,
) -> tuple[_SelectorTarget, _SelectorSpecificity, bool] | None:
    """Return a static terminal target and the full selector specificity.

    The card body often supplies context that is outside ``card.question()``
    (for example ``.card div.hint``).  We therefore match the complete final
    compound locally, while retaining the whole selector's specificity for
    the CSS cascade.  Dynamic/conditional selectors remain unsupported so a
    rule such as ``.hint:hover`` cannot hide an ordinary visible prompt.
    """

    normalized = re.sub(r"\s*([>+~])\s*", r" \1 ", selector.strip())
    if not normalized:
        return None
    tokens = normalized.split()
    compounds: list[str] = []
    previous_was_combinator = False
    for token in tokens:
        if token in {">", "+", "~"}:
            if not compounds or previous_was_combinator:
                return None
            previous_was_combinator = True
            continue
        if not _CSS_STATIC_COMPOUND.fullmatch(token):
            return None
        # Two compounds without an explicit token represent the descendant
        # combinator introduced by whitespace in the original selector.
        compounds.append(token)
        previous_was_combinator = False
    if not compounds or previous_was_combinator:
        return None

    terminal = compounds[-1]
    identifier_matches = re.findall(r"#(" + _CSS_IDENTIFIER_TEXT + r")", terminal)
    class_matches = re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]{0,63})", terminal)
    if len(set(identifier_matches)) > 1:
        # A single HTML element cannot satisfy two different IDs.
        return None
    type_match = re.match(_CSS_IDENTIFIER_TEXT, terminal)
    target: _SelectorTarget = (
        type_match.group(0).casefold() if type_match is not None else "",
        identifier_matches[0] if identifier_matches else "",
        frozenset(class_matches),
        (),
    )
    identifier_count = sum(
        len(re.findall(r"#" + _CSS_IDENTIFIER_TEXT, compound))
        for compound in compounds
    )
    class_count = sum(
        len(re.findall(r"\." + _CSS_IDENTIFIER_TEXT, compound))
        for compound in compounds
    )
    type_count = sum(
        1
        for compound in compounds
        if compound and compound[0] not in {".", "#", "*"}
    )
    return (
        target,
        (identifier_count, class_count, type_count),
        len(compounds) > 1,
    )


def _possible_terminal_visibility_selectors(
    selector: str,
    *,
    depth: int = 0,
) -> list[tuple[_SelectorTarget, _SelectorSpecificity, bool]]:
    """Extract conservative terminal targets from unsupported selectors.

    Attribute, pseudo-class and outer-context selectors cannot be evaluated
    reliably against a detached card fragment.  Their final static tag/class/
    ID can still identify content that *might* be hidden, which is enough for
    the fail-closed visibility pass. A selector that cannot be narrowed safely
    becomes a wildcard target instead of allowing concealed content through.
    """

    source = selector.strip()
    if not source or depth >= 8:
        return []
    quote = ""
    square_depth = 0
    round_depth = 0
    terminal_start = 0
    for index, character in enumerate(source):
        if quote:
            if character == "\\":
                continue
            if character == quote:
                quote = ""
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "[":
            square_depth += 1
        elif character == "]":
            square_depth = max(0, square_depth - 1)
        elif character == "(":
            round_depth += 1
        elif character == ")":
            round_depth = max(0, round_depth - 1)
        elif not square_depth and not round_depth and (
            character.isspace() or character in ">+~"
        ):
            terminal_start = index + 1
    terminal = source[terminal_start:].strip()
    if terminal.startswith("&"):
        terminal = terminal[1:].lstrip()

    static: list[str] = []
    positive_groups: list[str] = []
    attributes: list[tuple[str, str | None]] = []
    unsupported_attribute = False
    index = 0
    while index < len(terminal):
        character = terminal[index]
        if character == "[":
            content_start = index + 1
            bracket_depth = 1
            index += 1
            while index < len(terminal) and bracket_depth:
                if terminal[index] == "[":
                    bracket_depth += 1
                elif terminal[index] == "]":
                    bracket_depth -= 1
                index += 1
            if bracket_depth:
                unsupported_attribute = True
                continue
            content = terminal[content_start:index - 1].strip()
            attribute_match = re.fullmatch(
                r"([A-Za-z_][A-Za-z0-9_.:-]{0,63})"
                r"(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|"
                r"([A-Za-z0-9_.:-]{0,128})))?",
                content,
            )
            if attribute_match is None:
                unsupported_attribute = True
                continue
            expected = next(
                (
                    value
                    for value in attribute_match.groups()[1:]
                    if value is not None
                ),
                None,
            )
            attributes.append((attribute_match.group(1).casefold(), expected))
            continue
        if character == ":":
            index += 1
            if index < len(terminal) and terminal[index] == ":":
                index += 1
            name_start = index
            while index < len(terminal) and (
                terminal[index].isalnum() or terminal[index] in "_-"
            ):
                index += 1
            name = terminal[name_start:index].casefold()
            if index < len(terminal) and terminal[index] == "(":
                arguments_start = index + 1
                parentheses = 1
                index += 1
                while index < len(terminal) and parentheses:
                    if terminal[index] == "(":
                        parentheses += 1
                    elif terminal[index] == ")":
                        parentheses -= 1
                    index += 1
                if name in {"is", "where"} and not parentheses:
                    positive_groups.append(terminal[arguments_start:index - 1])
            continue
        static.append(character)
        index += 1

    results: list[tuple[_SelectorTarget, _SelectorSpecificity, bool]] = []
    static_compound = "".join(static).strip()
    if unsupported_attribute:
        results.append((("", "", frozenset(), ()), (0, 0, 0), True))
    elif static_compound and static_compound != "*":
        parsed = _terminal_visibility_selector(static_compound)
        if parsed is not None:
            target, specificity, _needs_ancestor = parsed
            results.append(
                (
                    (target[0], target[1], target[2], tuple(attributes)),
                    specificity,
                    True,
                )
            )
    elif attributes:
        results.append(
            (("", "", frozenset(), tuple(attributes)), (0, len(attributes), 0), True)
        )
    for group in positive_groups if not unsupported_attribute else ():
        for option in _css_selector_chunks(group):
            direct = _terminal_visibility_selector(option.strip())
            if direct is not None:
                target, specificity, _needs_ancestor = direct
                results.append((target, specificity, True))
            else:
                results.extend(
                    _possible_terminal_visibility_selectors(
                        option,
                        depth=depth + 1,
                    )
                )
    if not results:
        results.append((("", "", frozenset(), ()), (0, 0, 0), True))
    deduplicated: list[tuple[_SelectorTarget, _SelectorSpecificity, bool]] = []
    seen: set[_SelectorTarget] = set()
    for result in results:
        if result[0] not in seen:
            deduplicated.append(result)
            seen.add(result[0])
    return deduplicated


def _fragment_visibility_target(target: _SelectorTarget) -> _SelectorTarget:
    """Map Anki's known outer card containers to the detached fragment."""

    tag, identifier, classes, attributes = target
    if tag in {"body", "html"} or identifier == "qa" or "card" in classes:
        return "", "", frozenset(), ()
    return target


def _selector_attributes_match(
    target_attributes: _SelectorAttributes,
    values: dict[str, str],
) -> bool:
    return all(
        name in values and (expected is None or values[name] == expected)
        for name, expected in target_attributes
    )


def _unsafe_question_shell_targets(
    styles: list[str],
) -> tuple[tuple[_SelectorTarget, frozenset[str]], ...]:
    winners: dict[
        _SelectorTarget,
        tuple[tuple[int, int, int, int, int], bool],
    ] = {}
    order = 0
    for stylesheet in styles:
        for selector_group, body in _css_top_level_blocks(stylesheet):
            declarations: list[tuple[bool, bool]] = []
            for chunk in _css_declaration_chunks(body):
                if ":" not in chunk:
                    continue
                name, raw_value = chunk.split(":", 1)
                name = name.strip().casefold()
                if name not in {"font", "font-size"}:
                    continue
                important = bool(
                    re.search(
                        r"\s*!\s*important\s*$", raw_value, re.IGNORECASE
                    )
                )
                risky = (
                    _font_shorthand_is_risky(raw_value)
                    if name == "font"
                    else _font_size_is_risky(raw_value)
                )
                declarations.append((risky, important))
            if not declarations:
                continue
            selectors: list[
                tuple[_SelectorTarget, _SelectorSpecificity, bool]
            ] = []
            for raw_selector in _css_selector_chunks(selector_group):
                parsed = _terminal_visibility_selector(raw_selector)
                if parsed is not None:
                    selectors.append(parsed)
            for risky, important in declarations:
                order += 1
                for target, specificity, needs_ancestor in selectors:
                    # We cannot prove that an arbitrary ancestor selector
                    # applies. Its risky result is respected conservatively;
                    # its safe result may not cancel a direct risky rule.
                    if needs_ancestor and not risky:
                        continue
                    priority = (
                        1 if important else 0,
                        specificity[0],
                        specificity[1],
                        specificity[2],
                        order,
                    )
                    if target not in winners or priority >= winners[target][0]:
                        winners[target] = (priority, risky)
    return tuple(
        (target, frozenset({"font-size"}))
        for target, (_priority, risky) in winners.items()
        if risky
    )


def _safe_question_template_styles_html(styles: list[str]) -> str:
    """Keep typography while dropping template rules that can move/hide UI."""

    rendered_rules: list[str] = []
    for stylesheet in styles:
        for selector_group, body in _css_top_level_blocks(stylesheet):
            selectors = [
                raw_selector.strip()
                for raw_selector in _css_selector_chunks(selector_group)
                if _terminal_visibility_selector(raw_selector) is not None
            ]
            if not selectors:
                continue
            declarations: list[str] = []
            for chunk in _css_declaration_chunks(body):
                if ":" not in chunk:
                    continue
                name, raw_value = chunk.split(":", 1)
                name = name.strip().casefold()
                value = raw_value.strip()
                folded = "".join(value.casefold().split())
                if (
                    name not in _QUESTION_TEMPLATE_STYLE_PROPERTIES
                    or not value
                    or len(value) > 500
                    or "url(" in folded
                    or "expression(" in folded
                    or "javascript:" in folded
                    or "@import" in folded
                    or "{" in value
                    or "}" in value
                ):
                    continue
                if name == "font-size" and _font_size_is_risky(value):
                    continue
                if name == "font" and _font_shorthand_is_risky(value):
                    continue
                declarations.append("%s:%s" % (name, value))
            if declarations:
                rendered_rules.append(
                    "%s{%s}" % (",".join(selectors), ";".join(declarations))
                )
    if not rendered_rules:
        return ""
    return "<style>%s</style>" % "".join(rendered_rules)


def _semantic_node_style(tag: str, *, reset_font: bool = True) -> str:
    display = _SEMANTIC_DISPLAY.get(tag, "block")
    style = "display:%s!important;%s" % (display, _QUESTION_SHELL_RESET)
    if reset_font:
        style += ";" + _QUESTION_FONT_RESET
    if tag == "img":
        style += (
            ";max-width:100%!important;max-height:55vh!important;"
            "object-fit:contain!important;margin:.35rem auto!important"
        )
    return style


def _template_visibility_rules(
    styles: list[str],
) -> list[_VisibilityRule]:
    rules: list[_VisibilityRule] = []
    order = 0
    for stylesheet in styles:
        for selector_group, body, conditional in _css_visibility_blocks(stylesheet):
            selectors: list[
                tuple[_SelectorTarget, _SelectorSpecificity, bool, bool]
            ] = []
            for raw_selector in _css_selector_chunks(selector_group):
                selector = _terminal_visibility_selector(raw_selector)
                if selector is not None:
                    target, specificity, needs_ancestor = selector
                    selectors.append(
                        (
                            _fragment_visibility_target(target),
                            specificity,
                            needs_ancestor,
                            conditional,
                        )
                    )
                else:
                    selectors.extend(
                        (
                            _fragment_visibility_target(target),
                            specificity,
                            needs_ancestor,
                            True,
                        )
                        for target, specificity, needs_ancestor
                        in _possible_terminal_visibility_selectors(raw_selector)
                    )
            if not selectors:
                continue
            for property_name, hidden, important in _visibility_declarations(body):
                order += 1
                for target, specificity, needs_ancestor, possible in selectors:
                    # card.question() does not include Anki's outer ``.card``
                    # element, so an ancestor-dependent selector can only be
                    # evaluated conservatively.  A hidden declaration is safe
                    # to apply to its terminal target.  A visible declaration
                    # from another ancestor context must never undo it.
                    if (needs_ancestor or possible) and not hidden:
                        continue
                    rules.append(
                        (
                            target,
                            property_name,
                            hidden,
                            important,
                            specificity,
                            order,
                            possible,
                        )
                    )
    return rules


def _hidden_by_template_css(
    tag: str,
    values: dict[str, str],
    rules: list[_VisibilityRule],
) -> bool:
    classes = set(values.get("class", "").split())
    identifier = values.get("id", "")
    winners: dict[str, tuple[tuple[int, int, int, int, int, int], bool]] = {}
    for (
        target,
        property_name,
        hidden,
        important,
        specificity,
        order,
        possible,
    ) in rules:
        target_tag, target_identifier, target_classes, target_attributes = target
        if (
            (target_tag and target_tag != tag)
            or (target_identifier and target_identifier != identifier)
            or not target_classes.issubset(classes)
            or not _selector_attributes_match(target_attributes, values)
        ):
            continue
        if possible and hidden:
            # Conditional/dynamic CSS can become active in WebEngine even if
            # it is inactive while this detached fragment is parsed. Nothing
            # less than omitting the potentially concealed node prevents a
            # hidden answer from being copied into the live question.
            return True
        priority = (
            1 if important else 0,
            0,
            specificity[0],
            specificity[1],
            specificity[2],
            order,
        )
        if property_name not in winners or priority >= winners[property_name][0]:
            winners[property_name] = (priority, hidden)

    inline_order = len(rules)
    for property_name, hidden, important in _visibility_declarations(values.get("style", "")):
        inline_order += 1
        priority = (1 if important else 0, 1, 0, 0, 0, inline_order)
        if property_name not in winners or priority >= winners[property_name][0]:
            winners[property_name] = (priority, hidden)
    return any(hidden for _priority, hidden in winners.values())


def _safe_class_names(raw: str) -> list[str]:
    return [
        token
        for token in raw.split()
        if _SAFE_IDENTIFIER.fullmatch(token)
    ][:12]


def _safe_inline_style(
    raw: str,
    blocked_properties: frozenset[str] = frozenset(),
) -> str:
    declarations: list[str] = []
    for declaration in raw.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        name = name.strip().casefold()
        value = value.strip()
        folded = "".join(value.casefold().split())
        if (
            name not in _SAFE_STYLE_PROPERTIES
            or name in blocked_properties
            or not value
            or len(value) > 300
            or "url(" in folded
            or "expression(" in folded
            or "javascript:" in folded
            or "@import" in folded
            or "!important" in folded
        ):
            continue
        declarations.append("%s:%s" % (name, value))
    return ";".join(declarations[:24])


def _safe_shell_element(
    tag: str,
    attrs: list[tuple[str, str | None]],
    unsafe_targets: tuple[tuple[_SelectorTarget, frozenset[str]], ...],
) -> tuple[str, tuple[tuple[str, str], ...]] | None:
    tag = tag.casefold()
    if tag not in _QUESTION_SHELL_TAGS:
        return None
    values = {name.casefold(): value or "" for name, value in attrs}
    safe: list[tuple[str, str]] = []

    original_classes = _safe_class_names(values.get("class", ""))
    original_class_set = set(original_classes)
    identifier = values.get("id", "").strip()
    removed_classes: set[str] = set()
    remove_identifier = False
    inline_risky_font_properties = _risky_inline_font_properties(
        values.get("style", "")
    )
    reset_font = bool(inline_risky_font_properties)
    for target, risks in unsafe_targets:
        target_tag, target_identifier, target_classes, target_attributes = target
        if (
            (target_tag and target_tag != tag)
            or (target_identifier and target_identifier != identifier)
            or not target_classes.issubset(original_class_set)
            or not _selector_attributes_match(target_attributes, values)
        ):
            continue
        if target_identifier:
            remove_identifier = True
        elif target_classes:
            # Break only the actual compound selector, preserving the other
            # presentation classes whenever possible.
            removed_classes.add(sorted(target_classes)[-1])
        elif "font-size" in risks:
            # A tag-only or universal rule cannot be broken by dropping a
            # class/ID, so neutralize only its unsafe tiny font.
            reset_font = True

    classes = [value for value in original_classes if value not in removed_classes]
    if classes:
        safe.append(("class", " ".join(classes)))
    if (
        _SAFE_IDENTIFIER.fullmatch(identifier)
        and identifier not in {"qa", "answer"}
        and not remove_identifier
    ):
        safe.append(("id", identifier))
    direction = values.get("dir", "").casefold()
    if direction in {"auto", "ltr", "rtl"}:
        safe.append(("dir", direction))
    language = values.get("lang", "").strip()
    if language and len(language) <= 35 and re.fullmatch(r"[A-Za-z0-9-]+", language):
        safe.append(("lang", language))
    align = values.get("align", "").casefold()
    if align in {"center", "justify", "left", "right", "start", "end"}:
        safe.append(("align", align))
    blocked_style_properties = inline_risky_font_properties
    style = _safe_inline_style(
        values.get("style", ""),
        blocked_style_properties,
    )
    if reset_font:
        style = style + (";" if style else "") + _QUESTION_FONT_RESET
    if style:
        safe.append(("style", style))
    if tag == "font":
        color = values.get("color", "").strip()
        if color and len(color) <= 40 and re.fullmatch(r"[#(),.%\w\s-]+", color):
            safe.append(("color", color))
        face = values.get("face", "").strip()
        if face and len(face) <= 100 and re.fullmatch(r"[\w\s,'\"-]+", face):
            safe.append(("face", face))
        size = values.get("size", "").strip()
        size_is_small = (
            (size.isdigit() and int(size) <= 2)
            or (size.startswith("-") and size[1:].isdigit())
        )
        if re.fullmatch(r"[+-]?[1-7]", size) and not size_is_small:
            safe.append(("size", size))
    if tag in {"td", "th"}:
        for name in ("colspan", "rowspan"):
            value = values.get(name, "").strip()
            if value.isdigit() and 1 <= int(value) <= 100:
                safe.append((name, value))
    return tag, tuple(safe)


class _ClosedDetailsFrame:
    def __init__(self, depth: int) -> None:
        self.depth = depth
        self.summary_seen = False
        self.active_summary_depth: int | None = None


class _InitialDetailsVisibility:
    """Track what native ``details`` elements expose before interaction."""

    def __init__(self) -> None:
        self._tags: list[str] = []
        self._closed: list[_ClosedDetailsFrame] = []

    def start(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        self_closing: bool = False,
    ) -> bool:
        tag = tag.casefold()
        depth = len(self._tags)
        visible = True
        for frame in self._closed:
            if frame.active_summary_depth is not None:
                continue
            if (
                tag == "summary"
                and depth == frame.depth + 1
                and not frame.summary_seen
            ):
                frame.summary_seen = True
                frame.active_summary_depth = depth
            else:
                visible = False

        values = {name.casefold(): value or "" for name, value in attrs}
        if not self_closing and tag not in _QUESTION_VOID_TAGS:
            self._tags.append(tag)
            if tag == "details" and "open" not in values:
                self._closed.append(_ClosedDetailsFrame(depth))
        elif tag == "summary":
            for frame in self._closed:
                if frame.active_summary_depth == depth:
                    frame.active_summary_depth = None
        return visible

    def end(self, tag: str) -> None:
        tag = tag.casefold()
        match_index: int | None = None
        for index in range(len(self._tags) - 1, -1, -1):
            if self._tags[index] == tag:
                match_index = index
                break
        if match_index is None:
            return
        for frame in self._closed:
            if (
                frame.active_summary_depth is not None
                and frame.active_summary_depth >= match_index
            ):
                frame.active_summary_depth = None
        self._closed = [
            frame for frame in self._closed if frame.depth < match_index
        ]
        del self._tags[match_index:]

    def data_visible(self) -> bool:
        return all(
            frame.active_summary_depth is not None
            for frame in self._closed
        )

    def complete(self) -> bool:
        return not self._tags and not self._closed


class _QuestionShellCollector(HTMLParser):
    """Find the presentation path around the main visible question text."""

    def __init__(
        self,
        visibility_rules: list[_VisibilityRule],
        unsafe_targets: tuple[tuple[_SelectorTarget, frozenset[str]], ...],
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._visibility_rules = visibility_rules
        self._unsafe_targets = unsafe_targets
        self._details_visibility = _InitialDetailsVisibility()
        self._stack: list[
            tuple[str, tuple[str, tuple[tuple[str, str], ...]] | None]
        ] = []
        self._skip_tags: list[str] = []
        self.best_path: tuple[
            tuple[str, tuple[tuple[str, str], ...]], ...
        ] = ()
        self._best_score = -1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        initially_visible = self._details_visibility.start(tag, attrs)
        if self._skip_tags:
            if tag not in _QUESTION_VOID_TAGS:
                self._skip_tags.append(tag)
            return
        values = {name.casefold(): value or "" for name, value in attrs}
        hidden = (
            "hidden" in values
            or "inert" in values
            or values.get("aria-hidden", "").casefold() == "true"
            or _hidden_by_template_css(tag, values, self._visibility_rules)
        )
        if tag in _QUESTION_SKIP_TAGS or hidden:
            if tag not in _QUESTION_VOID_TAGS:
                self._skip_tags.append(tag)
            return
        if tag not in _QUESTION_VOID_TAGS:
            self._stack.append(
                (
                    tag,
                    _safe_shell_element(
                        tag,
                        attrs,
                        self._unsafe_targets,
                    )
                    if initially_visible
                    else None,
                )
            )

    def handle_endtag(self, tag: str) -> None:
        self._details_visibility.end(tag)
        if self._skip_tags:
            for index in range(len(self._skip_tags) - 1, -1, -1):
                if self._skip_tags[index] == tag.casefold():
                    del self._skip_tags[index:]
                    break
            return
        tag = tag.casefold()
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._details_visibility.start(tag, attrs, self_closing=True)

    def handle_data(self, data: str) -> None:
        if self._skip_tags or not self._details_visibility.data_visible():
            return
        visible = " ".join(data.split())
        if not visible:
            return
        full_path = tuple(
            element
            for _tag, element in self._stack
            if element is not None
        )
        path = full_path[-_MAX_QUESTION_SHELL_DEPTH:]
        # Truncating a deep table/list path can otherwise leave an orphaned
        # <tr>, <td> or <li> at the document root. WebEngine then reparents it
        # and may move the following original-question section. Fall back to
        # a neutral shell whenever the retained path lacks a required parent.
        retained_tags: list[str] = []
        for tag, _attributes in path:
            required = _QUESTION_CONTEXT_REQUIRED_TAGS.get(tag)
            if required is not None and not any(
                ancestor in required for ancestor in retained_tags
            ):
                path = ()
                break
            retained_tags.append(tag)
        # Long text nodes are much more likely to contain the actual prompt
        # than short decorative headings such as "Question" or a card number.
        score = len(visible) + (20 if visible.endswith(("?", "？")) else 0)
        if score > self._best_score:
            # An empty path is intentional here: it records that this text
            # won, but needs the neutral fallback shell. Otherwise an earlier
            # short banner could remain selected after a deep table path was
            # rejected for structural safety.
            self.best_path = path
            self._best_score = score


def _question_shell_html(
    original_html: str,
    variant_html: str,
    visibility_rules: list[_VisibilityRule],
) -> str:
    parser = _QuestionShellCollector(
        visibility_rules,
        (),
    )
    try:
        parser.feed(original_html or "")
        parser.close()
    except Exception:
        parser.best_path = ()
    if not parser.best_path:
        neutral_style = _semantic_node_style("div")
        return (
            '<div data-fv-question="1" style="%s">%s</div>'
            % (neutral_style, variant_html)
        )

    starts: list[str] = []
    ends: list[str] = []
    for index, (tag, attributes) in enumerate(parser.best_path):
        values = list(attributes)
        if index == 0:
            values.append(("data-fv-question", "1"))
        node_reset = _semantic_node_style(tag, reset_font=False)
        style_index = next(
            (position for position, item in enumerate(values) if item[0] == "style"),
            None,
        )
        if style_index is None:
            values.append(("style", node_reset))
        else:
            name, style_value = values[style_index]
            separator = ";" if style_value and not style_value.endswith(";") else ""
            values[style_index] = (
                name,
                style_value + separator + node_reset,
            )
        rendered_attributes = "".join(
            ' %s="%s"' % (name, html.escape(value, quote=True))
            for name, value in values
        )
        starts.append("<%s%s>" % (tag, rendered_attributes))
        ends.append("</%s>" % tag)
    return "".join(starts) + variant_html + "".join(reversed(ends))


def _safe_image_source(src: str) -> bool:
    compact = src.strip()
    if compact.casefold().startswith("data:"):
        return compact.casefold().startswith(("data:image/png;base64,", "data:image/jpeg;base64,"))
    scheme = urlsplit(compact).scheme.casefold()
    return scheme in {"", "http", "https"}


class _AnswerSeparator(HTMLParser):
    """Locate Anki's answer marker while retaining its exact source span."""

    def __init__(self, source: str, *, top_level_only: bool) -> None:
        super().__init__(convert_charrefs=True)
        self._source = source
        self._top_level_only = top_level_only
        self._line_offsets = [0]
        self._line_offsets.extend(
            match.end() for match in re.finditer("\n", source)
        )
        self._stack: list[tuple[str, str]] = []
        self.span: tuple[int, int] | None = None
        self.ancestor_markup = ""

    def _record_if_answer(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if (
            self.span is not None
            or (self._top_level_only and self._stack)
            or tag.casefold() != "hr"
        ):
            return
        values = {name.casefold(): value or "" for name, value in attrs}
        if values.get("id", "").casefold() != "answer":
            return
        line, column = self.getpos()
        if line < 1 or line > len(self._line_offsets):
            return
        raw = self.get_starttag_text() or ""
        start = self._line_offsets[line - 1] + column
        if not raw or self._source[start:start + len(raw)] != raw:
            return
        self.span = (start, start + len(raw))
        self.ancestor_markup = "".join(
            opening
            for ancestor, opening in self._stack
            if ancestor not in {"html", "head", "body"}
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        self._record_if_answer(tag, attrs)
        if tag not in _QUESTION_VOID_TAGS:
            self._stack.append((tag, self.get_starttag_text() or "<%s>" % tag))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record_if_answer(tag.casefold(), attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break


def _top_level_answer_separator(answer_html: str) -> tuple[int, int] | None:
    parser = _AnswerSeparator(answer_html, top_level_only=True)
    try:
        parser.feed(answer_html)
        parser.close()
    except Exception:
        return None
    return parser.span


def _any_answer_separator(answer_html: str) -> tuple[int, int] | None:
    parser = _AnswerSeparator(answer_html, top_level_only=False)
    try:
        parser.feed(answer_html)
        parser.close()
    except Exception:
        return None
    return parser.span


def _nested_answer_separator(
    answer_html: str,
) -> tuple[int, int, str] | None:
    parser = _AnswerSeparator(answer_html, top_level_only=False)
    try:
        parser.feed(answer_html)
        parser.close()
    except Exception:
        return None
    if parser.span is None:
        return None
    return parser.span[0], parser.span[1], parser.ancestor_markup


class _SafeOriginalParser(HTMLParser):
    _ALLOWED_TAGS = {
        "b", "blockquote", "br", "caption", "code", "dd", "details", "div", "dl",
        "dt", "em", "hr", "i", "kbd", "li", "ol", "p", "pre", "ruby",
        "rt", "s", "span", "strong", "sub", "summary", "sup", "table",
        "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
    }
    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _SKIP_TAGS = {
        "canvas", "iframe", "noscript", "object", "script", "style", "svg",
        "template",
    }

    def __init__(
        self,
        visibility_rules: list[_VisibilityRule],
        *,
        initial_visibility_only: bool = False,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self._skip_tags: list[str] = []
        self._visibility_rules = visibility_rules
        self._initial_visibility_only = initial_visibility_only
        self._details_visibility = (
            _InitialDetailsVisibility() if initial_visibility_only else None
        )
        self._emitted_stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        initially_visible = (
            self._details_visibility.start(tag, attrs)
            if self._details_visibility is not None
            else True
        )
        if self._skip_tags:
            if tag not in self._VOID_TAGS:
                self._skip_tags.append(tag)
            return
        values = {name.casefold(): value or "" for name, value in attrs}
        hidden = (
            "hidden" in values
            or "inert" in values
            or values.get("aria-hidden", "").casefold() == "true"
            or _hidden_by_template_css(tag, values, self._visibility_rules)
        )
        if tag in self._SKIP_TAGS or hidden:
            if tag not in self._VOID_TAGS:
                self._skip_tags.append(tag)
            return
        if self._initial_visibility_only and not initially_visible:
            if tag not in self._VOID_TAGS:
                self._emitted_stack.append((tag, False))
            return
        if tag == "img":
            src = values.get("src", "").strip()
            if src and _safe_image_source(src):
                self.output.append(
                    '<img src="%s" alt="%s">'
                    % (
                        html.escape(src, quote=True),
                        html.escape(values.get("alt", "").strip(), quote=True),
                    )
                )
            return
        if tag not in self._ALLOWED_TAGS:
            if tag not in self._VOID_TAGS:
                self._emitted_stack.append((tag, False))
            return
        attributes: list[str] = []
        direction = values.get("dir", "").casefold()
        if direction in {"auto", "ltr", "rtl"}:
            attributes.append(' dir="%s"' % direction)
        if tag == "details" and "open" in values:
            attributes.append(" open")
        if tag in {"td", "th"}:
            for name in ("colspan", "rowspan"):
                value = values.get(name, "").strip()
                if value.isdigit() and 1 <= int(value) <= 100:
                    attributes.append(' %s="%s"' % (name, value))
        self.output.append("<%s%s>" % (tag, "".join(attributes)))
        if tag not in self._VOID_TAGS:
            self._emitted_stack.append((tag, True))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._details_visibility is not None:
            self._details_visibility.end(tag)
        if self._skip_tags:
            for index in range(len(self._skip_tags) - 1, -1, -1):
                if self._skip_tags[index] == tag:
                    del self._skip_tags[index:]
                    break
            return
        for index in range(len(self._emitted_stack) - 1, -1, -1):
            stack_tag, _emitted = self._emitted_stack[index]
            if stack_tag != tag:
                continue
            closing = self._emitted_stack[index:]
            del self._emitted_stack[index:]
            for closing_tag, emitted in reversed(closing):
                if emitted:
                    self.output.append("</%s>" % closing_tag)
            break

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._initial_visibility_only and tag.casefold() not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if (
            not self._skip_tags
            and (
                self._details_visibility is None
                or self._details_visibility.data_visible()
            )
        ):
            self.output.append(html.escape(data, quote=False))

    def initial_state_complete(self) -> bool:
        return (
            not self._skip_tags
            and not self._emitted_stack
            and (
                self._details_visibility is None
                or self._details_visibility.complete()
            )
        )

    def close_open_tags(self) -> None:
        """Balance malformed custom fragments in the non-initial view."""

        if self._initial_visibility_only:
            return
        for tag, emitted in reversed(self._emitted_stack):
            if emitted:
                self.output.append("</%s>" % tag)
        self._emitted_stack.clear()


def _safe_original_fragment(original_html: str, *, initially_visible_only: bool) -> str:
    visibility_rules = _template_visibility_rules(
        _all_template_styles(original_html)
    )
    parser = _SafeOriginalParser(
        visibility_rules,
        initial_visibility_only=initially_visible_only,
    )
    try:
        parser.feed(original_html or "")
        parser.close()
        if initially_visible_only and not parser.initial_state_complete():
            return ""
        parser.close_open_tags()
        return "".join(parser.output).strip()
    except Exception:
        # Fail closed. Falling back to all plain text could expose an answer or
        # hint that the card template deliberately hides with CSS.
        return ""


def safe_original_fragment(original_html: str) -> str:
    """Return passive, allow-listed card markup suitable for a second view."""

    return _safe_original_fragment(original_html, initially_visible_only=False)


def safe_initially_visible_fragment(original_html: str) -> str:
    """Return only passive card content visible before any user interaction."""

    return _safe_original_fragment(original_html, initially_visible_only=True)


class _ContextFragmentHardener(HTMLParser):
    """Give sanitized original markup semantic inline layout protection."""

    _ALLOWED_TAGS = _SafeOriginalParser._ALLOWED_TAGS | {"img"}
    _VOID_TAGS = _SafeOriginalParser._VOID_TAGS

    def __init__(self, *, omit_images: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.stack: list[str] = []
        self._omit_images = omit_images

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        if tag not in self._ALLOWED_TAGS:
            return
        if tag == "img" and self._omit_images:
            return
        values = {name.casefold(): value or "" for name, value in attrs}
        rendered: list[str] = [
            ' style="%s"' % html.escape(_semantic_node_style(tag), quote=True)
        ]
        direction = values.get("dir", "").casefold()
        if direction in {"auto", "ltr", "rtl"}:
            rendered.append(' dir="%s"' % direction)
        if tag == "details" and "open" in values:
            rendered.append(" open")
        if tag == "img":
            src = values.get("src", "").strip()
            if not src or not _safe_image_source(src):
                return
            rendered.append(' src="%s"' % html.escape(src, quote=True))
            rendered.append(
                ' alt="%s"'
                % html.escape(values.get("alt", "").strip(), quote=True)
            )
        if tag in {"td", "th"}:
            for name in ("colspan", "rowspan"):
                value = values.get(name, "").strip()
                if value.isdigit() and 1 <= int(value) <= 100:
                    rendered.append(' %s="%s"' % (name, value))
        if tag == "font":
            for name in ("color", "face", "size"):
                value = values.get(name, "").strip()
                if value:
                    rendered.append(
                        ' %s="%s"' % (name, html.escape(value, quote=True))
                    )
        self.output.append("<%s%s>" % (tag, "".join(rendered)))
        if tag not in self._VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] != tag:
                continue
            closing = self.stack[index:]
            del self.stack[index:]
            self.output.extend("</%s>" % value for value in reversed(closing))
            break

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        self.output.append(html.escape(data, quote=False))

    def finish(self) -> str:
        self.output.extend("</%s>" % value for value in reversed(self.stack))
        self.stack.clear()
        return "".join(self.output)


def _harden_context_fragment(
    original_fragment: str,
    *,
    omit_images: bool = False,
) -> str:
    sanitized = safe_original_fragment(original_fragment)
    if not sanitized:
        return ""
    parser = _ContextFragmentHardener(omit_images=omit_images)
    try:
        parser.feed(sanitized)
        parser.close()
        return parser.finish()
    except Exception:
        return ""


def _context_fragment_has_content(fragment: str) -> bool:
    """Return whether a context fragment contains something useful to reveal."""

    meaningful_text = (
        html_to_text(fragment)
        .replace("[image]", "")
        .replace("[audio]", "")
        .strip()
    )
    if meaningful_text:
        return True
    return bool(re.search(r"<(?:img|math|svg|video)\b", fragment, re.IGNORECASE))


def original_context_available(
    original_fragment: str,
    *,
    omit_images: bool = False,
) -> bool:
    """Return whether the front has useful original context to disclose.

    Front media is hidden during recall but remains useful inside the explicit
    Original disclosure, including for image-only cards.
    """

    hardened = _harden_context_fragment(
        original_fragment,
        omit_images=omit_images,
    )
    return _context_fragment_has_content(hardened)


def _original_context_html(
    original_fragment: str,
    *,
    front: bool,
    front_card_id: int | None = None,
    omit_images: bool = False,
) -> str:
    """Render one calm original-question context block.

    The front and back intentionally share the same presentation classes. The
    front receives a unique marker and starts hidden; reviewer JavaScript may
    target only that marker, so it can never hide or mutate the answer-side
    context accidentally.
    """

    hardened_fragment = _harden_context_fragment(
        original_fragment,
        omit_images=omit_images,
    )
    if not _context_fragment_has_content(hardened_fragment):
        return ""
    original_label = html.escape(tr("reviewer.original"), quote=True)
    if front:
        marker = "" if front_card_id is None else str(int(front_card_id))
        section_attributes = (
            ' class="fv-answer-original" data-fv-original-front="%s"'
            ' hidden aria-hidden="true"'
            ' style="display:none!important;%s"'
            ' aria-label="%s"'
            % (
                html.escape(marker, quote=True),
                _QUESTION_SHELL_RESET,
                original_label,
            )
        )
        label_attributes = ' class="fv-answer-label"'
    else:
        section_attributes = (
            ' class="fv-answer-original" style="%s" aria-label="%s"'
            % (_semantic_node_style("section", reset_font=False), original_label)
        )
        label_attributes = ' class="fv-answer-label"'
    label_style = (
        _semantic_node_style("div", reset_font=False)
        + ";font:500 .7rem/1.3 system-ui,sans-serif!important"
    )
    question_style = _semantic_node_style("div")
    return (
        '<section%s><div%s style="%s">%s</div>'
        '<div class="fv-answer-question" style="%s">%s</div></section>'
        % (
            section_attributes,
            label_attributes,
            label_style,
            original_label,
            question_style,
            hardened_fragment,
        )
    )


def render_question(
    variant: str,
    original_html: str,
    *,
    original_fragment: str | None = None,
    front_card_id: int | None = None,
) -> str:
    variant_html = _plain_text_html(variant)
    template_styles = _leading_template_styles(original_html)
    visibility_rules = _template_visibility_rules(
        _all_template_styles(original_html)
    )
    if original_fragment is None:
        original_fragment = safe_original_fragment(original_html)
    return (
        _STYLE
        + _safe_question_template_styles_html(template_styles)
        + _question_shell_html(original_html, variant_html, visibility_rules)
        + _original_context_html(
            original_fragment,
            front=True,
            front_card_id=front_card_id,
            omit_images=False,
        )
    )


def render_answer_context(
    answer_html: str,
    variant: str,
    original_html: str,
    original_already_present: bool,
    *,
    show_original: bool = True,
) -> str:
    # Anki scrolls its answer marker to the top when the back is revealed.
    # Keeping the generated prompt immediately after that marker makes the
    # same question remain visible at the top without pushing the answer out
    # of reach or exposing the photographed front again.
    variant_html = _plain_text_html(variant.strip())
    if variant_html:
        visibility_rules = _template_visibility_rules(
            _all_template_styles(original_html)
        )
        prompt_html = (
            '<section class="fv-answer-prompt" data-fv-answer-prompt="1">%s</section>'
            % _question_shell_html(
                original_html,
                variant_html,
                visibility_rules,
            )
        )
    else:
        prompt_html = ""

    # A harmless reviewer redraw must not duplicate a prompt that this hook
    # already inserted into the current back side.
    if 'data-fv-answer-prompt="1"' in answer_html:
        return answer_html

    context = (
        _original_context_html(
            safe_original_fragment(original_html),
            front=False,
        )
        if show_original
        else ""
    )
    comparison_html = prompt_html + context
    solution_html = answer_html
    answer_template_styles = ""
    if original_already_present:
        # The standard Anki back template is FrontSide, <hr id=answer>, Back.
        # For that well-defined form we can discard the duplicated FrontSide
        # and add one sanitized original after the answer.  Unknown custom
        # templates remain byte-for-byte unchanged instead of risking damage.
        separator = _top_level_answer_separator(answer_html)
        if separator is None:
            nested_separator = _nested_answer_separator(answer_html)
            if nested_separator is None:
                # A few custom templates repeat the exact front without an
                # answer anchor. Remove that exact occurrence when possible;
                # otherwise keep the template intact and place the generated
                # question before it rather than risking answer loss.
                exact_start = answer_html.find(original_html)
                if exact_start >= 0 and original_html:
                    exact_end = exact_start + len(original_html)
                    solution_html = (
                        comparison_html
                        + answer_html[:exact_start]
                        + answer_html[exact_end:]
                    )
                else:
                    solution_html = prompt_html + answer_html
                return _STYLE + solution_html
            separator_start, separator_end, ancestor_markup = nested_separator
            candidate = answer_html[separator_end:]
            if not html_to_text(candidate).strip() and not _VISIBLE_ANSWER_MARKUP.search(candidate):
                return answer_html
            answer_template_styles = _leading_template_styles_html(answer_html)
            solution_html = (
                ancestor_markup
                + answer_html[separator_start:separator_end]
                + comparison_html
                + candidate
            )
            return _STYLE + answer_template_styles + solution_html
        separator_start, separator_end = separator
        candidate = answer_html[separator_end:]
        if not html_to_text(candidate).strip() and not _VISIBLE_ANSWER_MARKUP.search(candidate):
            return answer_html
        answer_template_styles = _leading_template_styles_html(answer_html)
        # Keep Anki's answer anchor immediately before the content being
        # graded. Reviewer code scrolls this exact element into view, so the
        # generated question belongs immediately after it.
        solution_html = (
            answer_html[separator_start:separator_end]
            + comparison_html
            + candidate
        )
    else:
        separator = _any_answer_separator(answer_html)
        if separator is None:
            solution_html = comparison_html + answer_html
        else:
            _separator_start, separator_end = separator
            solution_html = (
                answer_html[:separator_end]
                + comparison_html
                + answer_html[separator_end:]
            )
    return _STYLE + answer_template_styles + solution_html
