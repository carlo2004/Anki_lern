"""GUI-thread renderer for complete, transient card-front screenshots."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from aqt.qt import QBuffer, QSize, Qt, QTimer
from aqt.theme import theme_manager
from aqt.utils import qconnect
from aqt.webview import AnkiWebView, AnkiWebViewKind

from .core.models import CardSnapshot
from .core.visual import (
    attach_front_screenshot,
    fitted_capture_size,
    mark_front_screenshot_failed,
)


_CAPTURE_BODY = """
<div id="_mark" hidden></div>
<div id="_flag" hidden></div>
<div id="qa" dir="auto"></div>
"""
_CAPTURE_WIDTH = 1120
_CAPTURE_HEIGHT = 760
_MAX_CAPTURE_WIDTH = 1600
_MAX_CAPTURE_HEIGHT = 2048
_MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
_READY_POLL_MS = 80
_MAX_READY_POLLS = 50


@dataclass
class _CaptureRequest:
    snapshots: list[CardSnapshot]
    success: Callable[[list[CardSnapshot]], None]
    cancelled: Callable[[], bool]
    output: list[CardSnapshot] = field(default_factory=list)
    index: int = 0


class FrontScreenshotService:
    """Serialize WebEngine captures so live lookahead remains lightweight."""

    def __init__(self, main_window: Any) -> None:
        self.mw = main_window
        self._pending: deque[_CaptureRequest] = deque()
        self._active_request: _CaptureRequest | None = None
        self._active_capture: _SingleFrontCapture | None = None
        self._epoch = 0

    def capture_snapshots(
        self,
        snapshots: Sequence[CardSnapshot],
        *,
        success: Callable[[list[CardSnapshot]], None],
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        items = list(snapshots)
        if not any(item.front_screenshot_required for item in items):
            success(items)
            return
        self._pending.append(
            _CaptureRequest(
                snapshots=items,
                success=success,
                cancelled=cancelled or (lambda: False),
            )
        )
        self._pump()

    def cancel_all(self) -> None:
        self._epoch += 1
        self._pending.clear()
        self._active_request = None
        active = self._active_capture
        self._active_capture = None
        if active is not None:
            active.cancel()

    def _pump(self) -> None:
        if self._active_request is not None:
            return
        if not self._pending:
            return
        self._active_request = self._pending.popleft()
        self._advance()

    def _advance(self) -> None:
        request = self._active_request
        if request is None:
            self._pump()
            return
        if request.cancelled():
            self._finish_request(request, request.snapshots)
            return
        if request.index >= len(request.snapshots):
            self._finish_request(request, request.output)
            return

        snapshot = request.snapshots[request.index]
        request.index += 1
        if snapshot.unsupported_reason or not snapshot.front_screenshot_required:
            request.output.append(snapshot)
            self._advance()
            return

        epoch = self._epoch

        def captured(data: bytes, mime_type: str) -> None:
            if self._active_request is not request or self._epoch != epoch:
                return
            self._active_capture = None
            try:
                request.output.append(
                    attach_front_screenshot(snapshot, data, mime_type)
                )
            except Exception:
                request.output.append(mark_front_screenshot_failed(snapshot))
            self._advance()

        def failed() -> None:
            if self._active_request is not request or self._epoch != epoch:
                return
            self._active_capture = None
            request.output.append(mark_front_screenshot_failed(snapshot))
            self._advance()

        try:
            self._active_capture = _SingleFrontCapture(
                self.mw,
                snapshot,
                captured=captured,
                failed=failed,
                cancelled=request.cancelled,
            )
            self._active_capture.start()
        except Exception:
            self._active_capture = None
            failed()

    def _finish_request(
        self,
        request: _CaptureRequest,
        snapshots: list[CardSnapshot],
    ) -> None:
        if self._active_request is not request:
            return
        self._active_request = None
        try:
            request.success(list(snapshots))
        finally:
            self._pump()


class _SingleFrontCapture:
    """Render one original question in an off-screen reviewer-sized webview."""

    def __init__(
        self,
        main_window: Any,
        snapshot: CardSnapshot,
        *,
        captured: Callable[[bytes, str], None],
        failed: Callable[[], None],
        cancelled: Callable[[], bool],
    ) -> None:
        self.mw = main_window
        self.snapshot = snapshot
        self._captured = captured
        self._failed = failed
        self._cancelled = cancelled
        self._view: AnkiWebView | None = None
        self._finished = False
        self._polls = 0
        self._viewport_size = (_CAPTURE_WIDTH, _CAPTURE_HEIGHT)

    def start(self) -> None:
        reviewer = getattr(self.mw, "reviewer", None)
        if reviewer is None:
            self._finish_failed()
            return

        view = AnkiWebView(kind=AnkiWebViewKind.PREVIEWER)
        self._view = view
        view.setWindowFlag(Qt.WindowType.Tool, True)
        view.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        width, height = self._capture_size(reviewer)
        self._viewport_size = (width, height)
        view.resize(QSize(width, height))
        # WebEngine paints only exposed views reliably. Keeping this tiny tool
        # window far outside the virtual desktop avoids flashes and focus loss.
        view.move(-32000, -32000)
        view.show()
        qconnect(view.loadFinished, self._on_loaded)
        view.stdHtml(
            _CAPTURE_BODY,
            css=["css/reviewer.css"],
            js=[
                "js/mathjax.js",
                "js/vendor/mathjax/tex-chtml-full.js",
                "js/reviewer.js",
            ],
            context=reviewer,
        )

    def cancel(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._cleanup()

    def _capture_size(self, reviewer: Any) -> tuple[int, int]:
        current = getattr(reviewer, "web", None)
        width = _CAPTURE_WIDTH
        height = _CAPTURE_HEIGHT
        try:
            width = int(current.width())
            height = int(current.height())
        except Exception:
            pass
        return fitted_capture_size(
            width,
            height,
            width,
            height,
            max_width=_MAX_CAPTURE_WIDTH,
            max_height=_MAX_CAPTURE_HEIGHT,
        )

    def _on_loaded(self, ok: bool = True) -> None:
        if self._finished:
            return
        if not ok or self._cancelled():
            self._finish_failed()
            return
        view = self._view
        if view is None:
            self._finish_failed()
            return
        try:
            question = self.mw.prepare_card_text_for_display(
                self.snapshot.source_html
            )
            body_class = theme_manager.body_classes_for_card_ord(
                self.snapshot.card_ordinal
            )
        except Exception:
            self._finish_failed()
            return

        script = r"""
(() => {
  const qa = document.getElementById("qa");
  if (!qa) return false;
  document.body.className += " " + __BODY_CLASS__;
  qa.innerHTML = __QUESTION__;
  qa.setAttribute("dir", "auto");
  window.scrollTo(0, 0);
  window.__fvFrontReady = false;
  window.__fvBrokenVisual = false;
  window.__fvPendingVisuals = 0;
  const waits = [];
  const waitForImage = (image) => {
    if (image.complete) {
      if (image.naturalWidth <= 0) window.__fvBrokenVisual = true;
      return;
    }
    waits.push(new Promise((resolve) => {
      window.__fvPendingVisuals += 1;
      const finish = () => {
        window.__fvPendingVisuals = Math.max(0, window.__fvPendingVisuals - 1);
        resolve();
      };
      image.addEventListener("load", finish, {once: true});
      image.addEventListener("error", () => {
        window.__fvBrokenVisual = true;
        finish();
      }, {once: true});
    }));
  };
  for (const image of qa.querySelectorAll("img")) {
    waitForImage(image);
  }
  // Normal <img> elements are not enough for overlay cards: the meaningful
  // screenshot can live in a CSS background/mask. Preload local card-media
  // URLs so the capture cannot race Chromium's paint.
  const cssUrls = new Set();
  const urlPattern = /url\(\s*(['"]?)(.*?)\1\s*\)/g;
  for (const node of [qa, ...qa.querySelectorAll("*")]) {
    const style = getComputedStyle(node);
    for (const property of [
      "backgroundImage", "borderImageSource", "listStyleImage", "maskImage"
    ]) {
      const value = style[property] || "";
      let match;
      while ((match = urlPattern.exec(value)) !== null) {
        try {
          const resolved = new URL(match[2], document.baseURI);
          if (
            resolved.origin === location.origin ||
            resolved.hostname === "127.0.0.1" ||
            resolved.hostname === "localhost"
          ) cssUrls.add(resolved.href);
        } catch (_) {}
      }
      urlPattern.lastIndex = 0;
    }
  }
  for (const url of Array.from(cssUrls).slice(0, 16)) {
    const image = new Image();
    image.src = url;
    waitForImage(image);
  }
  if (document.fonts?.ready) waits.push(document.fonts.ready);
  if (window.MathJax?.typesetPromise) {
    try { waits.push(window.MathJax.typesetPromise([qa])); } catch (_) {}
  }
  const timeout = new Promise((resolve) => setTimeout(resolve, 2500));
  Promise.race([Promise.allSettled(waits), timeout]).then(() => {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      window.__fvFrontReady = true;
    }));
  });
  return true;
})()
""".replace("__BODY_CLASS__", json.dumps(body_class)).replace(
            "__QUESTION__", json.dumps(question)
        )
        view.evalWithCallback(script, self._after_inserted)

    def _after_inserted(self, inserted: Any) -> None:
        if self._finished:
            return
        if inserted is not True:
            self._finish_failed()
            return
        QTimer.singleShot(_READY_POLL_MS, self._poll_ready)

    def _poll_ready(self) -> None:
        if self._finished:
            return
        if self._cancelled():
            self._finish_failed()
            return
        view = self._view
        if view is None:
            self._finish_failed()
            return
        self._polls += 1
        script = r"""
(() => {
  const qa = document.getElementById("qa");
  const images = qa ? Array.from(qa.querySelectorAll("img")) : [];
  const rect = qa ? qa.getBoundingClientRect() : null;
  const documentElement = document.documentElement;
  const body = document.body;
  return {
    ready: Boolean(window.__fvFrontReady),
    imagesReady: images.every((image) => image.complete),
    brokenImages: Boolean(window.__fvBrokenVisual) || images.some((image) => image.complete && image.naturalWidth <= 0),
    pendingVisuals: Number(window.__fvPendingVisuals || 0),
    hasContent: Boolean(qa && (qa.innerText.trim() || qa.querySelector("img,svg,canvas,math,table,mjx-container"))),
    contentWidth: Math.ceil(Math.max(
      rect ? rect.right : 0,
      qa ? qa.scrollWidth : 0,
      body ? body.scrollWidth : 0,
      documentElement ? documentElement.scrollWidth : 0
    )),
    contentHeight: Math.ceil(Math.max(
      rect ? rect.bottom : 0,
      qa ? qa.scrollHeight : 0,
      body ? body.scrollHeight : 0,
      documentElement ? documentElement.scrollHeight : 0
    ))
  };
})()
"""
        view.evalWithCallback(script, self._on_ready_state)

    def _on_ready_state(self, state: Any) -> None:
        if self._finished:
            return
        if not isinstance(state, dict):
            self._finish_failed()
            return
        if state.get("brokenImages"):
            # Source-image fallbacks are more trustworthy than a Chromium
            # screenshot containing a broken-image placeholder.
            self._finish_failed()
            return
        if (
            state.get("ready")
            and state.get("imagesReady")
            and not state.get("pendingVisuals")
            and state.get("hasContent")
        ):
            view = self._view
            if view is None:
                self._finish_failed()
                return
            width, height = fitted_capture_size(
                self._viewport_size[0],
                self._viewport_size[1],
                state.get("contentWidth"),
                state.get("contentHeight"),
                max_width=_MAX_CAPTURE_WIDTH,
                max_height=_MAX_CAPTURE_HEIGHT,
            )
            try:
                if (width, height) != self._viewport_size:
                    view.resize(QSize(width, height))
                    self._viewport_size = (width, height)
                view.update()
            except Exception:
                self._finish_failed()
                return
            # Give Chromium one final paint after the DOM and fonts settle.
            QTimer.singleShot(140, self._capture)
            return
        if self._polls >= _MAX_READY_POLLS:
            self._finish_failed()
            return
        QTimer.singleShot(_READY_POLL_MS, self._poll_ready)

    def _capture(self) -> None:
        if self._finished or self._cancelled():
            self._finish_failed()
            return
        view = self._view
        if view is None:
            self._finish_failed()
            return
        try:
            pixmap = view.grab()
            if pixmap.isNull() or pixmap.width() < 2 or pixmap.height() < 2:
                raise ValueError("empty screenshot")
            png = self._encode(pixmap, "PNG")
            mime_type = "image/png"
            data = png
            if len(png) > _MAX_SCREENSHOT_BYTES:
                data = self._encode(pixmap, "JPG", quality=88)
                mime_type = "image/jpeg"
            # High-DPI displays can double the physical pixel dimensions.  If
            # compression alone is insufficient, scale progressively instead
            # of discarding an otherwise valid visual card.
            scaled = pixmap
            while (
                len(data) > _MAX_SCREENSHOT_BYTES
                and scaled.width() > 640
                and scaled.height() > 360
            ):
                scaled = scaled.scaled(
                    QSize(
                        max(640, int(scaled.width() * 0.75)),
                        max(360, int(scaled.height() * 0.75)),
                    ),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                data = self._encode(scaled, "JPG", quality=86)
                mime_type = "image/jpeg"
            if not data or len(data) > _MAX_SCREENSHOT_BYTES:
                raise ValueError("screenshot too large")
        except Exception:
            self._finish_failed()
            return
        self._finished = True
        self._cleanup()
        self._captured(data, mime_type)

    @staticmethod
    def _encode(pixmap: Any, image_format: str, quality: int = -1) -> bytes:
        buffer = QBuffer()
        if not buffer.open(QBuffer.OpenModeFlag.WriteOnly):
            return b""
        try:
            if not pixmap.save(buffer, image_format, quality):
                return b""
            return bytes(buffer.data())
        finally:
            buffer.close()

    def _finish_failed(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._cleanup()
        self._failed()

    def _cleanup(self) -> None:
        view = self._view
        self._view = None
        if view is None:
            return
        try:
            view.hide()
            view.cleanup()
            view.deleteLater()
        except Exception:
            pass


__all__ = ["FrontScreenshotService"]
