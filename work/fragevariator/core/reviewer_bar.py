"""Small, isolated UI contract for the reviewer's original-question control."""

from __future__ import annotations

import json

from ..i18n import tr


# Deprecated controller messages retained for one release so older imports do
# not fail while the controller uses a native-sized, non-resizing toolbar.
RESIZE_MESSAGE = "fragevariator:resize-original-bar"
KEEP_FOCUS_RESIZE_MESSAGE = f"{RESIZE_MESSAGE}:keep-focus"

# The bottom webview owns only the native-sized toggle. The controller handles
# this message and toggles inline context in the *main* reviewer webview.
TOGGLE_ORIGINAL_MESSAGE = "fragevariator:toggle-original"


def parse_original_toggle_message(message: str) -> tuple[bool, int] | None:
    """Return the requested visibility and card id for a toolbar message."""

    prefix = TOGGLE_ORIGINAL_MESSAGE + ":"
    if not isinstance(message, str) or not message.startswith(prefix):
        return None
    try:
        desired, raw_card_id = message[len(prefix):].split(":", 1)
        card_id = int(raw_card_id)
    except (TypeError, ValueError):
        return None
    if desired not in {"show", "hide"} or card_id <= 0:
        return None
    return desired == "show", card_id


_BOTTOM_BAR_TEMPLATE = r"""
<script>
(() => {
  if (window.frageVariatorOriginalBarInstalled) return;
  window.frageVariatorOriginalBarInstalled = true;
  const state = { available: false, open: false, cardId: "" };
  const labels = {
    show: __SHOW_ORIGINAL_LABEL__,
    hide: __HIDE_ORIGINAL_LABEL__
  };
  const toggleMessage = __TOGGLE_ORIGINAL_MESSAGE__;

  function removeButton() {
    document.getElementById("fv-original-button")?.remove();
    // Clean up the separate table cell used by Variator <= 0.5.11 when a
    // running reviewer reloads the add-on without rebuilding the whole bar.
    document.getElementById("fv-original-cell")?.remove();
  }

  function findButtonPlacement() {
    const middle = document.getElementById("middle");
    if (!middle) return null;
    const buttons = Array.from(middle.querySelectorAll("button")).filter(
      (button) => button.id !== "fv-original-button"
    );
    if (!buttons.length) return null;
    const answerButton = buttons.find((button) => {
      const command = button.getAttribute("onclick") || "";
      return button.id === "ansbut"
        || command.includes('pycmd("ans")')
        || command.includes("pycmd('ans')");
    });
    const anchor = answerButton || buttons[0];
    const host = anchor.parentElement;
    if (!host) return null;
    const firstSiblingButton = Array.from(host.children).find(
      (element) => element.tagName === "BUTTON"
        && element.id !== "fv-original-button"
    );
    return {
      host,
      before: firstSiblingButton || anchor,
      geometryReference: answerButton || firstSiblingButton || anchor,
    };
  }

  function matchButtonGeometry(button, reference) {
    if (!reference) return;
    const referenceStyle = getComputedStyle(reference);
    // Copy CSS dimensions together with their box model. A bounding rectangle
    // already includes padding, borders and transforms: assigning it as a CSS
    // content height adds those again (Anki uses content-box by default).
    // Matching vertical insets also keeps the text baseline aligned when a
    // bottom-bar add-on customizes the answer button. Width/colours stay native.
    for (const property of [
      "height", "boxSizing", "paddingTop", "paddingBottom",
      "borderTopWidth", "borderBottomWidth", "fontFamily", "fontSize",
      "fontWeight", "lineHeight", "verticalAlign",
    ]) {
      button.style[property] = referenceStyle[property];
    }
  }

  function updateButton(button) {
    const label = state.open ? labels.hide : labels.show;
    // Avoid retriggering the #middle MutationObserver when Anki has not
    // actually changed the control.
    if (button.textContent !== label) button.textContent = label;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.setAttribute("aria-expanded", state.open ? "true" : "false");
  }

  function ensureButton() {
    if (!state.available) {
      removeButton();
      return;
    }
    const placement = findButtonPlacement();
    if (!placement) return;
    let button = document.getElementById("fv-original-button");
    if (!button) {
      button = document.createElement("button");
      button.id = "fv-original-button";
      button.type = "button";
      button.addEventListener("click", () => {
        state.open = !state.open;
        updateButton(button);
        if (typeof pycmd === "function") {
          const desired = state.open ? "show" : "hide";
          pycmd(`${toggleMessage}:${desired}:${state.cardId}`);
        }
      });
    }
    if (button.parentElement !== placement.host
        || button.nextElementSibling !== placement.before) {
      placement.host.insertBefore(button, placement.before);
    }
    matchButtonGeometry(button, placement.geometryReference);
    updateButton(button);
  }

  window.frageVariatorSetOriginal = (value, cardId = "") => {
    state.available = typeof value === "boolean"
      ? value
      : Boolean(typeof value === "string" && value.trim());
    state.cardId = String(cardId);
    state.open = false;
    ensureButton();
  };
  window.frageVariatorSetOriginalOpen = (open) => {
    state.open = state.available && Boolean(open);
    const button = document.getElementById("fv-original-button");
    if (button) updateButton(button);
  };
  window.frageVariatorHideOriginal = (expectedCardId = "") => {
    if (expectedCardId && state.cardId !== String(expectedCardId)) return false;
    state.available = false;
    state.open = false;
    state.cardId = "";
    removeButton();
    return true;
  };
  window.frageVariatorSetLabels = (show, hide) => {
    if (typeof show === "string") labels.show = show;
    if (typeof hide === "string") labels.hide = hide;
    const button = document.getElementById("fv-original-button");
    if (button) updateButton(button);
  };

  function initialize() {
    const middle = document.getElementById("middle");
    if (middle) {
      new MutationObserver(ensureButton).observe(middle, {
        childList: true,
        subtree: true,
      });
    }
    ensureButton();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
</script>
"""


def bottom_bar_head() -> str:
    """Return a native Anki bottom-bar control in the selected UI language."""

    labels = {
        "__HIDE_ORIGINAL_LABEL__": tr("reviewer.hide_original"),
        "__SHOW_ORIGINAL_LABEL__": tr("reviewer.show_original"),
        "__TOGGLE_ORIGINAL_MESSAGE__": TOGGLE_ORIGINAL_MESSAGE,
    }
    rendered = _BOTTOM_BAR_TEMPLATE
    for marker, label in labels.items():
        rendered = rendered.replace(marker, json.dumps(label, ensure_ascii=True))
    return rendered


# Kept for compatibility with callers that imported the original constant.
# The controller uses ``bottom_bar_head()`` so a Settings change takes effect
# without restarting Anki.
BOTTOM_BAR_HEAD = bottom_bar_head()


def set_original_script(original_fragment: str, card_id: int | None = None) -> str:
    """Expose availability to the bottom bar without copying card data there."""

    available = "true" if (original_fragment or "").strip() else "false"
    encoded_card_id = json.dumps(
        "" if card_id is None else str(int(card_id)),
        ensure_ascii=True,
    )
    return (
        "if (window.frageVariatorSetOriginal) { "
        f"window.frageVariatorSetOriginal({available}, {encoded_card_id}); }}"
    )


def _card_id_text(card_id: int | None) -> str:
    """Return a positive card id or a fail-closed sentinel."""

    try:
        value = int(card_id) if card_id is not None else 0
    except (TypeError, ValueError):
        value = 0
    return str(value if value > 0 else 0)


def set_original_inline_script(card_id: int | None) -> str:
    """Install resilient controls for the server-rendered front context.

    The original HTML is deliberately ignored here. ``render_question()`` has
    already embedded its sanitized fragment in a valid top-level section. The
    observer is intentional: Anki schedules card rendering and add-on hook
    JavaScript separately, and image-heavy cards can make the section arrive
    after this controller. A requested state is therefore retained and applied
    as soon as the card DOM exists.
    """

    encoded_card_id = json.dumps(_card_id_text(card_id), ensure_ascii=True)
    return r"""
(() => {
  const expectedCardId = __CARD_ID__;
  if (typeof window.frageVariatorDisposeOriginalInline === "function") {
    window.frageVariatorDisposeOriginalInline();
  }
  let desiredOpen = false;
  let disposed = false;
  let lastRegion = null;
  let lastAppliedOpen = false;
  const findRegion = () => document.querySelector(
    `[data-fv-original-front="${expectedCardId}"]`
  );
  const ownsRequest = (cardId) => String(cardId) === expectedCardId;
  const applyState = () => {
    if (disposed) return false;
    const region = findRegion();
    if (!region) {
      lastRegion = null;
      lastAppliedOpen = false;
      return false;
    }
    const shouldScroll = desiredOpen
      && (region !== lastRegion || !lastAppliedOpen);
    region.hidden = !desiredOpen;
    region.style.setProperty(
      "display", desiredOpen ? "block" : "none", "important"
    );
    region.style.setProperty("visibility", "visible", "important");
    region.style.setProperty("opacity", "1", "important");
    region.setAttribute("aria-hidden", desiredOpen ? "false" : "true");
    lastRegion = region;
    lastAppliedOpen = desiredOpen;
    if (shouldScroll) {
      requestAnimationFrame(() => {
        if (!disposed && desiredOpen && region.isConnected) {
          region.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
      });
    }
    return true;
  };
  const observer = new MutationObserver(applyState);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  applyState();
  window.frageVariatorSetOriginalInlineOpen = (open, cardId) => {
    if (!ownsRequest(cardId)) return false;
    desiredOpen = Boolean(open);
    applyState();
    return desiredOpen;
  };
  window.frageVariatorToggleOriginalInline = (cardId) => {
    if (!ownsRequest(cardId)) return false;
    return window.frageVariatorSetOriginalInlineOpen(!desiredOpen, cardId);
  };
  window.frageVariatorHideOriginalInline = (cardId) => {
    return window.frageVariatorSetOriginalInlineOpen(false, cardId);
  };
  window.frageVariatorClearOriginalInline = (cardId) => {
    if (!ownsRequest(cardId)) return false;
    findRegion()?.remove();
    window.frageVariatorDisposeOriginalInline();
    return true;
  };
  window.frageVariatorDisposeOriginalInline = () => {
    if (disposed) return;
    disposed = true;
    observer.disconnect();
    delete window.frageVariatorSetOriginalInlineOpen;
    delete window.frageVariatorToggleOriginalInline;
    delete window.frageVariatorHideOriginalInline;
    delete window.frageVariatorClearOriginalInline;
    delete window.frageVariatorDisposeOriginalInline;
  };
})();
""".replace("__CARD_ID__", encoded_card_id)


def _scoped_inline_call(function_name: str, card_id: int | None, *args: str) -> str:
    encoded_card_id = json.dumps(_card_id_text(card_id), ensure_ascii=True)
    arguments = ", ".join((*args, encoded_card_id))
    return (
        f"if (window.{function_name}) {{ "
        f"window.{function_name}({arguments}); }}"
    )


def toggle_original_inline_script(card_id: int | None) -> str:
    return _scoped_inline_call("frageVariatorToggleOriginalInline", card_id)


def show_original_inline_script(card_id: int | None) -> str:
    return _scoped_inline_call(
        "frageVariatorSetOriginalInlineOpen", card_id, "true"
    )


def hide_original_inline_script(card_id: int | None) -> str:
    return _scoped_inline_call(
        "frageVariatorSetOriginalInlineOpen", card_id, "false"
    )


def clear_original_inline_script(card_id: int | None) -> str:
    return _scoped_inline_call("frageVariatorClearOriginalInline", card_id)


def hide_original_script(card_id: int | None) -> str:
    encoded_card_id = json.dumps(_card_id_text(card_id), ensure_ascii=True)
    return (
        "if (window.frageVariatorHideOriginal) { "
        f"window.frageVariatorHideOriginal({encoded_card_id}); }}"
    )


# Deprecated unscoped constants now fail closed (card id 0 can never own a
# rendered review card). Controller code always uses the scoped helpers.
TOGGLE_ORIGINAL_INLINE_SCRIPT = toggle_original_inline_script(0)
SHOW_ORIGINAL_INLINE_SCRIPT = show_original_inline_script(0)
HIDE_ORIGINAL_INLINE_SCRIPT = hide_original_inline_script(0)
CLEAR_ORIGINAL_INLINE_SCRIPT = clear_original_inline_script(0)
COLLAPSE_ORIGINAL_BUTTON_SCRIPT = (
    "if (window.frageVariatorSetOriginalOpen) { "
    "window.frageVariatorSetOriginalOpen(false); }"
)


def retranslate_script() -> str:
    """Update an already-open reviewer bar after a UI-language change."""

    labels = (tr("reviewer.show_original"), tr("reviewer.hide_original"))
    encoded = ", ".join(json.dumps(label, ensure_ascii=True) for label in labels)
    return (
        "if (window.frageVariatorSetLabels) { "
        "window.frageVariatorSetLabels(%s); }" % encoded
    )


def retranslate_inline_script(card_id: int | None = None) -> str:
    """Update inline original-question context after a language change."""

    encoded = json.dumps(tr("reviewer.original"), ensure_ascii=True)
    selector = json.dumps(
        '[data-fv-original-front="%s"]' % _card_id_text(card_id),
        ensure_ascii=True,
    )
    return (
        "(() => { "
        f"const region = document.querySelector({selector}); "
        'const heading = region?.querySelector(".fv-answer-label"); '
        f"if (heading) {{ heading.textContent = {encoded}; "
        f"region.setAttribute('aria-label', {encoded}); }} "
        "})();"
    )


# Python-level compatibility aliases for add-on integrations importing the
# former names. They now provide the inline, non-overlay behavior.
def set_original_overlay_script(
    _original_fragment: str,
    card_id: int | None = None,
) -> str:
    return set_original_inline_script(card_id)


def retranslate_overlay_script() -> str:
    return retranslate_inline_script()


TOGGLE_ORIGINAL_OVERLAY_SCRIPT = TOGGLE_ORIGINAL_INLINE_SCRIPT
HIDE_ORIGINAL_OVERLAY_SCRIPT = HIDE_ORIGINAL_INLINE_SCRIPT
CLEAR_ORIGINAL_OVERLAY_SCRIPT = CLEAR_ORIGINAL_INLINE_SCRIPT


HIDE_ORIGINAL_SCRIPT = hide_original_script(0)


__all__ = [
    "BOTTOM_BAR_HEAD",
    "bottom_bar_head",
    "CLEAR_ORIGINAL_INLINE_SCRIPT",
    "CLEAR_ORIGINAL_OVERLAY_SCRIPT",
    "COLLAPSE_ORIGINAL_BUTTON_SCRIPT",
    "HIDE_ORIGINAL_INLINE_SCRIPT",
    "HIDE_ORIGINAL_OVERLAY_SCRIPT",
    "HIDE_ORIGINAL_SCRIPT",
    "clear_original_inline_script",
    "hide_original_inline_script",
    "hide_original_script",
    "KEEP_FOCUS_RESIZE_MESSAGE",
    "RESIZE_MESSAGE",
    "SHOW_ORIGINAL_INLINE_SCRIPT",
    "TOGGLE_ORIGINAL_MESSAGE",
    "TOGGLE_ORIGINAL_INLINE_SCRIPT",
    "TOGGLE_ORIGINAL_OVERLAY_SCRIPT",
    "retranslate_inline_script",
    "retranslate_overlay_script",
    "retranslate_script",
    "parse_original_toggle_message",
    "set_original_inline_script",
    "set_original_overlay_script",
    "set_original_script",
    "show_original_inline_script",
    "toggle_original_inline_script",
]
