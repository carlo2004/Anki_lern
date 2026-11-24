from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, Literal, Optional


ENVIRONMENT_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "xai": "XAI_API_KEY",
}

_DPAPI_PREFIX = "dpapi-v1:"
SecretSource = Literal["environment", "session", "device", "missing"]


class SecretStoreError(OSError):
    """The local secret store exists but cannot be used safely."""


class SecretProtectionError(SecretStoreError):
    """A remembered secret exists but cannot be used safely."""


def persistent_storage_is_protected() -> bool:
    """Return whether persistent secrets use an OS account-bound protector.

    Windows ships DPAPI as part of the operating system, so Variator can use it
    without bundling a password manager or another dependency. Other systems
    keep the previous profile-file fallback; the setup dialog describes that
    limitation instead of promising encryption that is not actually available.
    """

    return sys.platform == "win32"


def _windows_dpapi(payload: bytes, entropy: bytes, *, protect: bool) -> bytes:
    """Protect or unprotect *payload* with the current Windows user account."""

    if sys.platform != "win32":
        raise OSError("Windows DPAPI is not available on this platform")

    # Imported lazily so this module remains importable on macOS/Linux and in
    # Anki's lightweight test environments.
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    def make_blob(data: bytes) -> tuple[DataBlob, object]:
        buffer = ctypes.create_string_buffer(data)
        blob = DataBlob(
            len(data),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        return blob, buffer

    input_blob, input_buffer = make_blob(payload)
    entropy_blob, entropy_buffer = make_blob(entropy)
    output_blob = DataBlob()
    crypt32 = ctypes.windll.crypt32
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN: no OS prompt during review.

    if protect:
        succeeded = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        )
    else:
        succeeded = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        )

    # Keep both buffers alive until the native function returned.
    del input_buffer, entropy_buffer
    if not succeeded:
        raise OSError("Windows could not protect the API key")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32 = ctypes.windll.kernel32
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(output_blob.pbData)


def _encode_persistent_secret(secret: str, storage_key: str) -> str:
    if not persistent_storage_is_protected():
        return secret
    protected = _windows_dpapi(
        secret.encode("utf-8"),
        storage_key.encode("utf-8"),
        protect=True,
    )
    return _DPAPI_PREFIX + base64.b64encode(protected).decode("ascii")


def _decode_persistent_secret(value: str, storage_key: str) -> str:
    if not value.startswith(_DPAPI_PREFIX):
        # Backward compatibility for Variator <= 0.4 and for platforms without
        # an OS-backed protector that is available without extra dependencies.
        return value
    if not persistent_storage_is_protected():
        raise SecretProtectionError(
            "A remembered Windows-protected API key cannot be read on this system"
        )
    try:
        protected = base64.b64decode(
            value[len(_DPAPI_PREFIX) :], validate=True
        )
        clear = _windows_dpapi(
            protected,
            storage_key.encode("utf-8"),
            protect=False,
        )
        return clear.decode("utf-8")
    except (OSError, ValueError, UnicodeError) as exc:
        # A copied, damaged, or differently owned secret is unavailable. Never
        # forward the ciphertext itself as an API key or silently treat it as
        # an ordinary empty setup.
        raise SecretProtectionError(
            "A remembered API key could not be decrypted with Windows DPAPI"
        ) from exc


class SecretStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._session: Dict[str, str] = {}
        self._session_only: set[str] = set()
        self._legacy_protection_error: OSError | None = None
        self._migrate_all_legacy_values()

    def get(self, provider: str, scope: str = "") -> Optional[str]:
        env = ENVIRONMENT_KEYS.get(provider)
        if env and os.environ.get(env):
            return os.environ[env].strip()

        storage_key = self._storage_key(provider, scope)
        session_value = self._session.get(storage_key)
        if session_value:
            return session_value

        values = self._read()
        raw_value = values.get(storage_key)
        if not raw_value:
            return None
        if (
            persistent_storage_is_protected()
            and not raw_value.startswith(_DPAPI_PREFIX)
            and self._legacy_protection_error is not None
        ):
            raise SecretProtectionError(
                "A remembered API key could not be protected with Windows DPAPI"
            ) from self._legacy_protection_error
        clear_value = _decode_persistent_secret(raw_value, storage_key)

        # Transparently protect old clear-text values when first read on
        # Windows. A failed migration is non-fatal and never deletes the key.
        if (
            clear_value
            and persistent_storage_is_protected()
            and not raw_value.startswith(_DPAPI_PREFIX)
        ):
            try:
                self._write(self._protected_values(values))
                self._legacy_protection_error = None
            except OSError as exc:
                self._legacy_protection_error = exc
                raise SecretProtectionError(
                    "A remembered API key could not be protected with Windows DPAPI"
                ) from exc
        return clear_value or None

    def source_kind(self, provider: str, scope: str = "") -> SecretSource:
        env = ENVIRONMENT_KEYS.get(provider)
        if env and os.environ.get(env):
            return "environment"
        storage_key = self._storage_key(provider, scope)
        session_value = self._session.get(storage_key)
        if session_value and storage_key in self._session_only:
            return "session"
        raw_value = self._read().get(storage_key)
        legacy_unprotected = bool(
            raw_value
            and persistent_storage_is_protected()
            and not raw_value.startswith(_DPAPI_PREFIX)
        )
        if (
            raw_value
            and not legacy_unprotected
            and _decode_persistent_secret(raw_value, storage_key)
        ):
            return "device"
        if session_value:
            return "session"
        return "missing"

    def is_persisted(self, provider: str, scope: str = "") -> bool:
        return self.source_kind(provider, scope) == "device"

    def source_label(self, provider: str, scope: str = "") -> str:
        """Backward-compatible German label; new UI code uses source_kind()."""

        env = ENVIRONMENT_KEYS.get(provider)
        labels = {
            "environment": (
                "Umgebungsvariable %s" % env if env else "Umgebungsvariable"
            ),
            "session": "nur diese Anki-Sitzung",
            "device": "auf diesem Gerät gespeichert",
            "missing": "nicht hinterlegt",
        }
        return labels[self.source_kind(provider, scope)]

    def set(
        self,
        provider: str,
        api_key: str,
        persist: bool,
        scope: str = "",
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            return
        storage_key = self._storage_key(provider, scope)
        self._session[storage_key] = key
        self._session_only.add(storage_key)
        if not persist:
            return
        values = self._read()
        if persistent_storage_is_protected():
            values = self._protected_values(values)
        values[storage_key] = _encode_persistent_secret(key, storage_key)
        self._write(values)
        self._legacy_protection_error = None
        self._session_only.discard(storage_key)

    def delete(self, provider: str, scope: str = "") -> None:
        storage_key = self._storage_key(provider, scope)
        self._session.pop(storage_key, None)
        self._session_only.discard(storage_key)
        values = self._read()
        if storage_key in values:
            del values[storage_key]
            self._write(values)

    def clear_session(self, scope: str = "") -> None:
        prefix = self._scope_prefix(scope)
        for key in list(self._session):
            if key.startswith(prefix):
                self._session.pop(key, None)
                self._session_only.discard(key)

    def clear_all(self) -> None:
        self._session.clear()
        self._session_only.clear()
        if self.path.exists():
            self._write({})

    @staticmethod
    def _scope_prefix(scope: str) -> str:
        digest = hashlib.sha256((scope or "default").encode("utf-8")).hexdigest()
        return "profile:%s:" % digest

    @classmethod
    def _storage_key(cls, provider: str, scope: str) -> str:
        return cls._scope_prefix(scope) + str(provider).casefold()

    def _read(self) -> Dict[str, str]:
        with self._lock:
            try:
                raw = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return {}
            except OSError as exc:
                raise SecretStoreError(
                    "The remembered API key store could not be read"
                ) from exc
            try:
                data = json.loads(raw)
            except (ValueError, TypeError) as exc:
                raise SecretStoreError(
                    "The remembered API key store is damaged"
                ) from exc
        if not isinstance(data, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in data.items()
        ):
            raise SecretStoreError(
                "The remembered API key store has an invalid format"
            )
        return dict(data)

    def _protected_values(self, values: Dict[str, str]) -> Dict[str, str]:
        protected: Dict[str, str] = {}
        for storage_key, value in values.items():
            protected[storage_key] = (
                value
                if value.startswith(_DPAPI_PREFIX)
                else _encode_persistent_secret(value, storage_key)
            )
        return protected

    def _migrate_all_legacy_values(self) -> None:
        if not persistent_storage_is_protected():
            return
        try:
            values = self._read()
        except SecretStoreError:
            # Keep the add-on available. The first explicit connection/setup
            # access reports the localized problem, and persistent writes also
            # fail instead of overwriting a damaged multi-provider store.
            return
        if not any(
            value and not value.startswith(_DPAPI_PREFIX)
            for value in values.values()
        ):
            return
        try:
            self._write(self._protected_values(values))
        except OSError as exc:
            # Never silently use an unprotected legacy key on Windows. The
            # caller will ask for the key again and can keep it session-only.
            self._legacy_protection_error = exc

    def _write(self, values: Dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with self._lock:
            temporary.write_text(
                json.dumps(values, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(str(temporary), str(self.path))


__all__ = [
    "ENVIRONMENT_KEYS",
    "SecretProtectionError",
    "SecretStore",
    "SecretStoreError",
    "SecretSource",
    "persistent_storage_is_protected",
]
