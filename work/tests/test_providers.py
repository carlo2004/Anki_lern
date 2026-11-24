from __future__ import annotations

import base64
import json
import sys
import unittest
from unittest import mock
from pathlib import Path
from typing import List, Optional, Union


WORK_ROOT = Path(__file__).resolve().parents[1]
if str(WORK_ROOT) not in sys.path:
    sys.path.insert(0, str(WORK_ROOT))

from fragevariator.core.providers import (  # noqa: E402
    ANTHROPIC_MESSAGES_URL,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MAX_IMAGES,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_RESPONSE_BYTES,
    GEMINI_INTERACTIONS_URL,
    OPENAI_RESPONSES_URL,
    REPHRASE_JSON_SCHEMA,
    XAI_RESPONSES_URL,
    ErrorKind,
    HttpRequest,
    HttpResponse,
    ImageInput,
    ProviderClient,
    ProviderError,
    ProviderName,
    RephraseTask,
    ResponseTooLargeError,
    TransportNetworkError,
    TransportTimeoutError,
    generate_json,
    normalize_provider,
)
from fragevariator.core.models import ProviderSettings  # noqa: E402
from fragevariator.core.prompt import response_schema  # noqa: E402


VALID_VALUE = {
    "core_aspect": "Die Hauptstadt von Frankreich",
    "rephrased_question": "Welche Stadt ist der Regierungssitz Frankreichs?",
    "is_equivalent": True,
    "warning": "",
}
VALID_TEXT = json.dumps(VALID_VALUE, ensure_ascii=False, separators=(",", ":"))

PNG_BYTES = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG_BYTES = base64.b64decode(
    b"/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////"
    b"//////////////////////////////////////////2wBDAf//////////////////////////////"
    b"////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QA"
    b"FQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF/"
    b"/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/a"
    b"AAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAA"
    b"AAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMB"
    b"AIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAA"
    b"AAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q=="
) + b"\xff\xd9"

GENERIC_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}


def response(status: int, value: object, headers: Optional[dict] = None) -> HttpResponse:
    if isinstance(value, bytes):
        body = value
    else:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return HttpResponse(status_code=status, headers=headers or {}, body=body)


def openai_response(text: str = VALID_TEXT) -> HttpResponse:
    return response(
        200,
        {
            "id": "resp_openai_1",
            "status": "completed",
            "output": [
                {"id": "reasoning_1", "type": "reasoning", "summary": []},
                {
                    "id": "message_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                },
            ],
            "usage": {"input_tokens": 31, "output_tokens": 22, "total_tokens": 53},
        },
        {"X-Request-Id": "req-openai-1"},
    )


def anthropic_response(text: str = VALID_TEXT) -> HttpResponse:
    return response(
        200,
        {
            "id": "msg_anthropic_1",
            "type": "message",
            "role": "assistant",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 30, "output_tokens": 20},
        },
        {"request-id": "req-anthropic-1"},
    )


def gemini_response(text: str = VALID_TEXT) -> HttpResponse:
    obsolete = dict(VALID_VALUE)
    obsolete["rephrased_question"] = "Dieser frühere Schritt darf nicht verwendet werden."
    return response(
        200,
        {
            "id": "interaction_gemini_1",
            "object": "interaction",
            "status": "completed",
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": json.dumps(obsolete)}],
                },
                {"type": "thought", "content": []},
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": text}],
                },
            ],
            "usage": {"total_input_tokens": 30, "total_output_tokens": 20},
        },
        {"x-goog-request-id": "req-gemini-1"},
    )


class FakeTransport:
    def __init__(self, *items: Union[HttpResponse, BaseException]) -> None:
        self.items: List[Union[HttpResponse, BaseException]] = list(items)
        self.requests: List[HttpRequest] = []
        self.timeouts: List[float] = []

    def send(self, request: HttpRequest, timeout_seconds: float) -> HttpResponse:
        self.requests.append(request)
        self.timeouts.append(timeout_seconds)
        if not self.items:
            raise AssertionError("FakeTransport queue is empty")
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class ProviderContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = RephraseTask(
            original_front="Was ist die Hauptstadt von Frankreich?",
            original_back="Paris",
            language="de",
            context="Geografie",
        )

    def _call(self, provider: str, result: HttpResponse, key: str = "secret-test-key"):
        transport = FakeTransport(result)
        client = ProviderClient(
            provider,
            key,
            "test-model",
            transport=transport,
            timeout_seconds=17,
            max_retries=0,
        )
        parsed = client.rephrase(self.task)
        return parsed, transport.requests[0], transport.timeouts[0]

    def _call_json_with_images(self, provider: str, result: HttpResponse):
        transport = FakeTransport(result)
        images = (
            ImageInput.from_bytes(PNG_BYTES, "image/png"),
            ImageInput.from_base64(base64.b64encode(JPEG_BYTES), "image/jpeg"),
        )
        parsed = ProviderClient(
            provider,
            "secret-test-key",
            "test-model",
            transport=transport,
            max_retries=0,
        ).generate_json(
            "custom system",
            "custom user",
            GENERIC_SCHEMA,
            images=images,
        )
        return parsed, json.loads(transport.requests[0].body), images

    def test_openai_responses_contract_and_parser(self) -> None:
        result, request, timeout = self._call("openai", openai_response())
        body = json.loads(request.body)

        self.assertEqual(request.url, OPENAI_RESPONSES_URL)
        self.assertEqual(request.headers["Authorization"], "Bearer secret-test-key")
        self.assertEqual(timeout, 17)
        self.assertFalse(body["store"])
        self.assertEqual(body["max_output_tokens"], DEFAULT_MAX_OUTPUT_TOKENS)
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(body["text"]["format"]["schema"], REPHRASE_JSON_SCHEMA)
        self.assertNotIn(b"secret-test-key", request.body)
        sent_card = json.loads(body["input"][1]["content"])
        self.assertEqual(sent_card["original_back"], "Paris")
        self.assertEqual(result.rephrased_question, VALID_VALUE["rephrased_question"])
        self.assertEqual(result.request_id, "req-openai-1")
        self.assertEqual(result.response_id, "resp_openai_1")
        self.assertEqual(result.usage["total_tokens"], 53)

    def test_reasoning_override_only_applies_to_verified_openai_presets(self) -> None:
        for model, effort in (
            ("gpt-5.6-luna", "none"),
            ("gpt-6-luna", "none"),
            ("gpt-6.1-terra", "none"),
            ("gpt-6.2-sol", "low"),
            ("custom-model", None),
        ):
            with self.subTest(model=model):
                transport = FakeTransport(openai_response())
                ProviderClient(
                    "openai", "secret-test-key", model, transport=transport,
                    max_retries=0,
                ).rephrase(self.task)
                body = json.loads(transport.requests[0].body)
                self.assertEqual(body["model"], model)
                if effort is None:
                    self.assertNotIn("reasoning", body)
                else:
                    self.assertEqual(body["reasoning"], {"effort": effort})

    def test_xai_responses_contract_and_parser(self) -> None:
        result, request, _ = self._call("xai", openai_response())
        body = json.loads(request.body)

        self.assertEqual(request.url, XAI_RESPONSES_URL)
        self.assertEqual(request.headers["Authorization"], "Bearer secret-test-key")
        self.assertFalse(body["store"])
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertEqual(body["text"]["format"]["name"], "anki_rephrase_v1")
        self.assertEqual(result.provider, "xai")
        self.assertTrue(result.is_equivalent)

    def test_reasoning_override_is_low_for_verified_xai_presets(self) -> None:
        for model in ("grok-4.5", "grok-4.6", "grok-4.7"):
            with self.subTest(model=model):
                transport = FakeTransport(openai_response())
                ProviderClient(
                    "xai", "secret-test-key", model, transport=transport,
                    max_retries=0,
                ).rephrase(self.task)
                body = json.loads(transport.requests[0].body)
                self.assertEqual(body["reasoning"], {"effort": "low"})

    def test_anthropic_messages_contract_and_parser(self) -> None:
        result, request, _ = self._call("anthropic", anthropic_response())
        body = json.loads(request.body)

        self.assertEqual(request.url, ANTHROPIC_MESSAGES_URL)
        self.assertEqual(request.headers["x-api-key"], "secret-test-key")
        self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("store", body)
        self.assertEqual(body["max_tokens"], DEFAULT_MAX_OUTPUT_TOKENS)
        output_format = body["output_config"]["format"]
        self.assertEqual(output_format["type"], "json_schema")
        self.assertEqual(output_format["schema"], REPHRASE_JSON_SCHEMA)
        self.assertNotIn(b"secret-test-key", request.body)
        sent_card = json.loads(body["messages"][0]["content"])
        self.assertEqual(sent_card["language"], "de")
        self.assertEqual(result.request_id, "req-anthropic-1")

    def test_claude_thinking_settings_respect_each_models_contract(self) -> None:
        for model, thinking in (
            ("claude-sonnet-5", "disabled"),
            ("claude-sonnet-5-20260630", "disabled"),
            ("claude-haiku-5-5", "disabled"),
            ("claude-sonnet-5-5", "between_tools"),
            ("claude-sonnet-5-5-20260928", "between_tools"),
        ):
            with self.subTest(model=model):
                transport = FakeTransport(anthropic_response())
                ProviderClient(
                    "anthropic", "secret-test-key", model, transport=transport,
                    max_retries=0,
                ).rephrase(self.task)
                body = json.loads(transport.requests[0].body)
                self.assertEqual(body["thinking"], {"type": thinking})
                self.assertEqual(
                    body["output_config"]["format"]["schema"], REPHRASE_JSON_SCHEMA
                )

    def test_gemini_v1_interactions_contract_and_last_model_output(self) -> None:
        result, request, _ = self._call("gemini", gemini_response())
        body = json.loads(request.body)

        self.assertEqual(request.url, GEMINI_INTERACTIONS_URL)
        self.assertEqual(request.headers["x-goog-api-key"], "secret-test-key")
        self.assertFalse(body["store"])
        self.assertEqual(body["generation_config"]["max_output_tokens"], DEFAULT_MAX_OUTPUT_TOKENS)
        self.assertEqual(
            body["response_format"],
            {
                "type": "text",
                "mime_type": "application/json",
                "schema": REPHRASE_JSON_SCHEMA,
            },
        )
        self.assertNotIn(b"secret-test-key", request.body)
        self.assertEqual(result.rephrased_question, VALID_VALUE["rephrased_question"])
        self.assertEqual(result.request_id, "req-gemini-1")

    def test_gemini_live_presets_use_compatible_thinking_with_images(self) -> None:
        image = ImageInput.from_bytes(PNG_BYTES, "image/png")
        for model, thinking in (
            ("gemini-3.5-flash-lite", "minimal"),
            ("gemini-3.6-flash", "minimal"),
            ("gemini-3.8-flash", "low"),
            ("gemini-4-hydrogen", "low"),
        ):
            with self.subTest(model=model):
                transport = FakeTransport(gemini_response('{"value":"ok"}'))
                result = ProviderClient(
                    "gemini", "secret-test-key", model, transport=transport,
                    max_retries=0,
                ).generate_json(
                    "system", "card text", GENERIC_SCHEMA, images=(image,)
                )
                body = json.loads(transport.requests[0].body)
                self.assertEqual(body["model"], model)
                self.assertEqual(body["generation_config"]["thinking_level"], thinking)
                self.assertEqual(body["input"][0]["type"], "user_input")
                self.assertEqual(body["input"][0]["content"][1]["mime_type"], "image/png")
                self.assertEqual(result, {"value": "ok"})

    def test_responses_parser_concatenates_split_output_text(self) -> None:
        split = len(VALID_TEXT) // 2
        payload = {
            "id": "resp_split",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": VALID_TEXT[:split]},
                        {"type": "output_text", "text": VALID_TEXT[split:]},
                    ],
                }
            ],
        }
        result, _, _ = self._call("openai", response(200, payload))
        self.assertEqual(result.core_aspect, VALID_VALUE["core_aspect"])

    def test_false_equivalence_is_returned_for_safe_caller_rejection(self) -> None:
        value = dict(VALID_VALUE)
        value["is_equivalent"] = False
        value["warning"] = "Die Antwortbreite ist nicht eindeutig."
        result, _, _ = self._call(
            "anthropic",
            anthropic_response(json.dumps(value, ensure_ascii=False)),
        )
        self.assertFalse(result.is_equivalent)
        self.assertTrue(result.warning)

    def test_provider_aliases(self) -> None:
        self.assertEqual(normalize_provider("Claude"), ProviderName.ANTHROPIC)
        self.assertEqual(normalize_provider("Google"), ProviderName.GEMINI)
        self.assertEqual(normalize_provider("Grok"), ProviderName.XAI)

    def test_generic_json_api_uses_custom_prompts_and_schema(self) -> None:
        output_text = '{"value":"ok"}'
        fixtures = {
            "openai": openai_response(output_text),
            "xai": openai_response(output_text),
            "anthropic": anthropic_response(output_text),
            "gemini": gemini_response(output_text),
        }
        for provider, fixture in fixtures.items():
            with self.subTest(provider=provider):
                transport = FakeTransport(fixture)
                result = ProviderClient(
                    provider,
                    "key",
                    "model",
                    transport=transport,
                    max_retries=0,
                ).generate_json("custom system", "custom user", GENERIC_SCHEMA)
                body = json.loads(transport.requests[0].body)
                self.assertEqual(result, {"value": "ok"})
                if provider in ("openai", "xai"):
                    self.assertEqual(body["input"][0]["content"], "custom system")
                    self.assertEqual(body["input"][1]["content"], "custom user")
                    self.assertEqual(body["text"]["format"]["schema"], GENERIC_SCHEMA)
                elif provider == "anthropic":
                    self.assertEqual(body["system"], "custom system")
                    self.assertEqual(body["messages"][0]["content"], "custom user")
                    self.assertEqual(body["output_config"]["format"]["schema"], GENERIC_SCHEMA)
                else:
                    self.assertEqual(body["system_instruction"], "custom system")
                    self.assertEqual(body["input"], "custom user")
                    self.assertEqual(body["response_format"]["schema"], GENERIC_SCHEMA)

    def test_flashcard_response_schema_reaches_every_adapter_unchanged(self) -> None:
        schema = response_schema(1)
        output_text = json.dumps(
            {
                "status": "unsupported",
                "core_aspect": "",
                "is_equivalent": False,
                "is_substantially_different": False,
                "change_strategy": "none",
                "variants": [],
                "warnings": [],
                "unsupported_reason": "Keine sichere strukturelle Variante.",
            },
            ensure_ascii=False,
        )
        fixtures = {
            "openai": openai_response(output_text),
            "xai": openai_response(output_text),
            "anthropic": anthropic_response(output_text),
            "gemini": gemini_response(output_text),
        }

        for provider, fixture in fixtures.items():
            with self.subTest(provider=provider):
                transport = FakeTransport(fixture)
                result = ProviderClient(
                    provider,
                    "key",
                    "model",
                    transport=transport,
                    max_retries=0,
                ).generate_json("system", "user", schema)
                body = json.loads(transport.requests[0].body)

                self.assertEqual(result["status"], "unsupported")
                if provider in ("openai", "xai"):
                    sent_schema = body["text"]["format"]["schema"]
                elif provider == "anthropic":
                    sent_schema = body["output_config"]["format"]["schema"]
                else:
                    sent_schema = body["response_format"]["schema"]
                self.assertEqual(sent_schema, schema)

    def test_openai_multimodal_inline_contract(self) -> None:
        result, body, images = self._call_json_with_images(
            "openai", openai_response('{"value":"ok"}')
        )

        self.assertEqual(result, {"value": "ok"})
        self.assertFalse(body["store"])
        content = body["input"][1]["content"]
        self.assertEqual(content[0], {"type": "input_text", "text": "custom user"})
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["detail"], "high")
        self.assertEqual(
            content[1]["image_url"],
            "data:image/png;base64,{}".format(images[0].to_base64()),
        )
        self.assertEqual(
            content[2]["image_url"],
            "data:image/jpeg;base64,{}".format(images[1].to_base64()),
        )
        self.assertEqual(body["text"]["format"]["schema"], GENERIC_SCHEMA)

    def test_xai_multimodal_inline_contract(self) -> None:
        result, body, images = self._call_json_with_images(
            "xai", openai_response('{"value":"ok"}')
        )

        self.assertEqual(result, {"value": "ok"})
        self.assertFalse(body["store"])
        content = body["input"][1]["content"]
        self.assertEqual(content[-1], {"type": "input_text", "text": "custom user"})
        self.assertEqual(
            [block["type"] for block in content[:-1]],
            ["input_image", "input_image"],
        )
        self.assertTrue(all(block["detail"] == "high" for block in content[:-1]))
        self.assertEqual(
            content[1]["image_url"],
            "data:image/jpeg;base64,{}".format(images[1].to_base64()),
        )

    def test_anthropic_multimodal_inline_contract(self) -> None:
        result, body, images = self._call_json_with_images(
            "anthropic", anthropic_response('{"value":"ok"}')
        )

        self.assertEqual(result, {"value": "ok"})
        self.assertNotIn("store", body)
        content = body["messages"][0]["content"]
        self.assertEqual(content[-1], {"type": "text", "text": "custom user"})
        self.assertEqual(
            content[0],
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": images[0].to_base64(),
                },
            },
        )
        self.assertEqual(content[1]["source"]["media_type"], "image/jpeg")
        self.assertEqual(content[1]["source"]["data"], images[1].to_base64())

    def test_gemini_multimodal_inline_contract(self) -> None:
        result, body, images = self._call_json_with_images(
            "gemini", gemini_response('{"value":"ok"}')
        )

        self.assertEqual(result, {"value": "ok"})
        self.assertFalse(body["store"])
        self.assertEqual(
            body["input"],
            [
                {
                    "type": "user_input",
                    "content": [
                        {"type": "text", "text": "custom user"},
                        {
                            "type": "image",
                            "data": images[0].to_base64(),
                            "mime_type": "image/png",
                            "resolution": "high",
                        },
                        {
                            "type": "image",
                            "data": images[1].to_base64(),
                            "mime_type": "image/jpeg",
                            "resolution": "high",
                        },
                    ],
                }
            ],
        )
        self.assertEqual(body["response_format"]["schema"], GENERIC_SCHEMA)

    def test_public_generate_json_facade_uses_provider_settings(self) -> None:
        settings = ProviderSettings(
            provider="anthropic",
            model="claude-test",
            api_key="memory-only-key",
            timeout_seconds=41,
            max_retries=1,
        )
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        with mock.patch("fragevariator.core.providers.ProviderClient") as client_class:
            client_class.return_value.generate_json.return_value = {"ok": True}
            result = generate_json(settings, "system", "user", schema)

        self.assertEqual(result, {"ok": True})
        client_class.assert_called_once_with(
            "anthropic",
            "memory-only-key",
            "claude-test",
            timeout_seconds=41,
            max_retries=1,
        )
        client_class.return_value.generate_json.assert_called_once_with("system", "user", schema)

    def test_public_generate_json_facade_forwards_images(self) -> None:
        settings = ProviderSettings(
            provider="openai",
            model="test-model",
            api_key="memory-only-key",
        )
        images = [ImageInput.from_bytes(PNG_BYTES, "image/png")]
        with mock.patch("fragevariator.core.providers.ProviderClient") as client_class:
            client_class.return_value.generate_json.return_value = {"value": "ok"}
            result = generate_json(
                settings,
                "system",
                "user",
                GENERIC_SCHEMA,
                images=images,
            )

        self.assertEqual(result, {"value": "ok"})
        client_class.return_value.generate_json.assert_called_once_with(
            "system", "user", GENERIC_SCHEMA, images=images
        )


class ProviderValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = RephraseTask("Frage?", "Antwort")

    def _parse_openai_text(self, text: str) -> None:
        transport = FakeTransport(openai_response(text))
        ProviderClient(
            "openai",
            "key",
            "model",
            transport=transport,
            max_retries=0,
        ).rephrase(self.task)

    def test_structured_output_requires_exact_schema_and_types(self) -> None:
        cases = {
            "invalid JSON": "not-json",
            "missing field": json.dumps(
                {
                    "core_aspect": "A",
                    "rephrased_question": "Q?",
                    "is_equivalent": True,
                }
            ),
            "extra field": json.dumps({**VALID_VALUE, "unexpected": "x"}),
            "integer boolean": json.dumps({**VALID_VALUE, "is_equivalent": 1}),
            "empty question": json.dumps({**VALID_VALUE, "rephrased_question": "  "}),
            "duplicate key": (
                '{"core_aspect":"A","core_aspect":"B",'
                '"rephrased_question":"Q?","is_equivalent":true,"warning":""}'
            ),
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(ProviderError) as caught:
                    self._parse_openai_text(text)
                self.assertEqual(caught.exception.kind, ErrorKind.INVALID_RESPONSE)
                self.assertFalse(caught.exception.retryable)

    def test_outer_response_requires_unique_json_object(self) -> None:
        outer = b'{"status":"completed","status":"completed","output":[]}'
        transport = FakeTransport(HttpResponse(200, {}, outer))
        with self.assertRaises(ProviderError) as caught:
            ProviderClient("openai", "key", "model", transport=transport).rephrase(self.task)
        self.assertEqual(caught.exception.kind, ErrorKind.INVALID_RESPONSE)

    def test_refusal_incomplete_and_cancelled_are_distinct(self) -> None:
        refusal = response(
            200,
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "No"}],
                    }
                ],
            },
        )
        incomplete = response(
            200,
            {
                "id": "msg_1",
                "stop_reason": "max_tokens",
                "content": [{"type": "text", "text": "{"}],
            },
        )
        cancelled = response(200, {"id": "i_1", "status": "cancelled", "steps": []})
        cases = (
            ("openai", refusal, ErrorKind.REFUSAL),
            ("anthropic", incomplete, ErrorKind.INCOMPLETE),
            ("gemini", cancelled, ErrorKind.CANCELLED),
        )
        for provider, raw, kind in cases:
            with self.subTest(provider=provider):
                with self.assertRaises(ProviderError) as caught:
                    ProviderClient(
                        provider,
                        "key",
                        "model",
                        transport=FakeTransport(raw),
                        max_retries=0,
                    ).rephrase(self.task)
                self.assertEqual(caught.exception.kind, kind)

    def test_input_and_header_validation(self) -> None:
        with self.assertRaises(ValueError):
            RephraseTask(" ", "Antwort")
        with self.assertRaises(ValueError):
            ProviderClient("openai", "key\r\nInjected: yes", "model")
        with self.assertRaises(ValueError):
            ProviderClient("openai", "key", "model\nInjected")
        with self.assertRaises(ValueError):
            ProviderClient("unknown", "key", "model")

    def test_image_input_accepts_raw_and_strict_base64(self) -> None:
        png = ImageInput.from_bytes(PNG_BYTES, " IMAGE/PNG ")
        jpeg = ImageInput.from_base64(
            base64.b64encode(JPEG_BYTES),
            "image/jpeg",
        )

        self.assertEqual(png.data, PNG_BYTES)
        self.assertEqual(png.mime_type, "image/png")
        self.assertEqual(png.to_base64(), base64.b64encode(PNG_BYTES).decode("ascii"))
        self.assertEqual(jpeg.data, JPEG_BYTES)
        self.assertEqual(jpeg.mime_type, "image/jpeg")

    def test_image_input_rejects_unsafe_mime_base64_and_size(self) -> None:
        with self.assertRaises(ValueError):
            ImageInput.from_bytes(PNG_BYTES, "image/gif")
        with self.assertRaises(ValueError):
            ImageInput.from_bytes(PNG_BYTES, "image/jpeg")
        with self.assertRaises(ValueError):
            ImageInput.from_base64(b"not valid base64!", "image/png")
        with self.assertRaises(ValueError):
            ImageInput.from_base64(
                b"data:image/png;base64," + base64.b64encode(PNG_BYTES),
                "image/png",
            )
        with self.assertRaises(ValueError):
            ImageInput.from_bytes(
                b"\x89PNG\r\n\x1a\n" + b"x" * DEFAULT_MAX_IMAGE_BYTES,
                "image/png",
            )

    def test_generate_json_validates_the_image_sequence_before_sending(self) -> None:
        transport = FakeTransport(openai_response('{"value":"ok"}'))
        client = ProviderClient(
            "openai",
            "key",
            "model",
            transport=transport,
            max_retries=0,
        )
        image = ImageInput.from_bytes(PNG_BYTES, "image/png")

        with self.assertRaises(TypeError):
            client.generate_json("system", "user", GENERIC_SCHEMA, images=image)
        with self.assertRaises(TypeError):
            client.generate_json("system", "user", GENERIC_SCHEMA, images=[object()])
        with self.assertRaises(ValueError):
            client.generate_json(
                "system",
                "user",
                GENERIC_SCHEMA,
                images=[image] * (DEFAULT_MAX_IMAGES + 1),
            )
        self.assertEqual(transport.requests, [])


class ProviderFailureAndRetryTests(unittest.TestCase):
    def test_cancelled_before_first_send_makes_no_request(self) -> None:
        transport = FakeTransport(openai_response())
        client = ProviderClient(
            "openai",
            "key",
            "model",
            transport=transport,
            max_retries=0,
            cancelled=lambda: True,
        )
        with self.assertRaises(InterruptedError):
            client.rephrase(RephraseTask("Frage?", "Antwort"))
        self.assertEqual(transport.requests, [])

    def test_cancelled_during_backoff_prevents_retry_send(self) -> None:
        state = {"cancelled": False}
        transport = FakeTransport(
            response(503, {"error": {"message": "temporary"}}),
            openai_response(),
        )

        def cancel_in_backoff(_seconds: float) -> None:
            state["cancelled"] = True

        client = ProviderClient(
            "openai",
            "key",
            "model",
            transport=transport,
            max_retries=1,
            sleeper=cancel_in_backoff,
            cancelled=lambda: state["cancelled"],
        )
        with self.assertRaises(InterruptedError):
            client.rephrase(RephraseTask("Frage?", "Antwort"))
        self.assertEqual(len(transport.requests), 1)

    def setUp(self) -> None:
        self.task = RephraseTask("Frage?", "Antwort")

    def test_retries_only_explicit_transient_http_responses(self) -> None:
        rate_limited = response(
            429,
            {"error": {"type": "rate_limit_error", "message": "Too many requests"}},
            {"Retry-After": "2", "X-Request-Id": "req-rate"},
        )
        unavailable = response(
            503,
            {"error": {"type": "server_error", "message": "Temporarily unavailable"}},
        )
        transport = FakeTransport(rate_limited, unavailable, openai_response())
        delays: List[float] = []
        client = ProviderClient(
            "openai",
            "key",
            "model",
            transport=transport,
            max_retries=2,
            sleeper=delays.append,
            random_fn=lambda: 0.0,
        )

        result = client.rephrase(self.task)

        self.assertTrue(result.is_equivalent)
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(delays, [2.0, 1.0])

    def test_quota_429_is_not_retried(self) -> None:
        quota = response(
            429,
            {
                "error": {
                    "code": "insufficient_quota",
                    "message": "You exceeded your current quota.",
                }
            },
        )
        transport = FakeTransport(quota, openai_response())
        with self.assertRaises(ProviderError) as caught:
            ProviderClient(
                "openai",
                "key",
                "model",
                transport=transport,
                max_retries=2,
                sleeper=lambda _: self.fail("quota must not sleep"),
            ).rephrase(self.task)
        self.assertEqual(caught.exception.kind, ErrorKind.QUOTA)
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(len(transport.requests), 1)

    def test_api_key_is_redacted_from_http_error(self) -> None:
        api_key = "super-secret-key"
        unauthorized = response(
            401,
            {
                "error": {
                    "code": "invalid_api_key",
                    "message": "Authorization: Bearer {} was rejected".format(api_key),
                }
            },
            {"X-Request-ID": "req-auth-1"},
        )
        with self.assertRaises(ProviderError) as caught:
            ProviderClient(
                "xai",
                api_key,
                "model",
                transport=FakeTransport(unauthorized),
                max_retries=0,
            ).rephrase(self.task)
        error = caught.exception
        self.assertEqual(error.kind, ErrorKind.AUTH)
        self.assertEqual(error.request_id, "req-auth-1")
        self.assertNotIn(api_key, str(error))
        self.assertIn("[REDACTED]", str(error))

    def test_gemini_invalid_api_key_uses_auth_error_for_400_and_403(self) -> None:
        cases = (
            (400, "API_KEY_INVALID", "API key not valid. Please pass a valid API key."),
            (403, "INVALID_ARGUMENT", "The API key is invalid."),
        )
        for status, code, message in cases:
            with self.subTest(status=status):
                invalid_key = response(
                    status,
                    {"error": {"status": code, "message": message}},
                )
                with self.assertRaises(ProviderError) as caught:
                    ProviderClient(
                        "gemini",
                        "bad-key",
                        "gemini-test-model",
                        transport=FakeTransport(invalid_key),
                        max_retries=0,
                    ).rephrase(self.task)
                self.assertEqual(caught.exception.kind, ErrorKind.AUTH)
                self.assertFalse(caught.exception.retryable)

    def test_timeout_and_network_errors_are_not_automatically_retried(self) -> None:
        cases = (
            (TransportTimeoutError("late"), ErrorKind.TIMEOUT),
            (TransportNetworkError("connection reset"), ErrorKind.NETWORK),
        )
        for failure, kind in cases:
            with self.subTest(kind=kind):
                transport = FakeTransport(failure, openai_response())
                with self.assertRaises(ProviderError) as caught:
                    ProviderClient(
                        "openai",
                        "key",
                        "model",
                        transport=transport,
                        max_retries=2,
                        sleeper=lambda _: self.fail("transport errors must not sleep"),
                    ).rephrase(self.task)
                self.assertEqual(caught.exception.kind, kind)
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(len(transport.requests), 1)

    def test_response_too_large_is_rejected(self) -> None:
        transport = FakeTransport(ResponseTooLargeError("large"), openai_response())
        with self.assertRaises(ProviderError) as caught:
            ProviderClient("openai", "key", "model", transport=transport).rephrase(self.task)
        self.assertEqual(caught.exception.kind, ErrorKind.INVALID_RESPONSE)
        self.assertEqual(len(transport.requests), 1)

        oversized = HttpResponse(200, {}, b"x" * (DEFAULT_MAX_RESPONSE_BYTES + 1))
        with self.assertRaises(ProviderError) as caught_body:
            ProviderClient(
                "openai", "key", "model", transport=FakeTransport(oversized)
            ).rephrase(self.task)
        self.assertEqual(caught_body.exception.kind, ErrorKind.INVALID_RESPONSE)

    def test_http_status_mapping_and_non_retryable_redirect(self) -> None:
        cases = (
            (403, ErrorKind.PERMISSION),
            (404, ErrorKind.MODEL_NOT_FOUND),
            (408, ErrorKind.TIMEOUT),
            (422, ErrorKind.BAD_REQUEST),
            (302, ErrorKind.INVALID_RESPONSE),
        )
        for status, kind in cases:
            with self.subTest(status=status):
                transport = FakeTransport(response(status, b"not-json"), openai_response())
                with self.assertRaises(ProviderError) as caught:
                    ProviderClient(
                        "openai",
                        "key",
                        "model",
                        transport=transport,
                        max_retries=2,
                    ).rephrase(self.task)
                self.assertEqual(caught.exception.kind, kind)
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(len(transport.requests), 1)

    def test_transient_error_after_retry_budget_preserves_retryable_flag(self) -> None:
        unavailable = response(529, {"error": {"type": "overloaded_error"}})
        transport = FakeTransport(unavailable, unavailable)
        with self.assertRaises(ProviderError) as caught:
            ProviderClient(
                "anthropic",
                "key",
                "model",
                transport=transport,
                max_retries=1,
                sleeper=lambda _: None,
                random_fn=lambda: 0,
            ).rephrase(self.task)
        self.assertEqual(caught.exception.kind, ErrorKind.UNAVAILABLE)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(len(transport.requests), 2)


if __name__ == "__main__":
    unittest.main()
