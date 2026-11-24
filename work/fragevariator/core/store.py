from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from .models import GeneratedVariants, StoredVariants


_VARIANTS_TABLE = "card_variants"
_PREPARED_TABLE = "prepared_variants"


class VariantStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.recovered_from: Path | None = None
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._initialize()
        except sqlite3.DatabaseError as exc:
            if not self._is_corruption_error(exc):
                raise
            self.recovered_from = self._quarantine_corrupt_database()
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # QueryOp callbacks can overlap with profile warm-up and live review.
        # Serializing this tiny add-on database avoids self-inflicted "locked"
        # failures while leaving Anki's collection completely independent.
        with self._lock:
            connection = self._connect()
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            integrity = connection.execute("PRAGMA quick_check(1)").fetchone()
            if integrity is not None and str(integrity[0]).casefold() != "ok":
                raise sqlite3.DatabaseError(
                    "variant cache integrity check failed"
                )
            connection.execute(f"""CREATE TABLE IF NOT EXISTS {_VARIANTS_TABLE} (
                profile_key TEXT NOT NULL, card_id INTEGER NOT NULL, note_id INTEGER NOT NULL,
                source_hash TEXT NOT NULL, question_preview TEXT NOT NULL, core_aspect TEXT NOT NULL,
                variants_json TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
                updated_at TEXT NOT NULL, uses_front_image INTEGER NOT NULL DEFAULT 0,
                front_visual_mode TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (profile_key, card_id))""")
            connection.execute(f"""CREATE TABLE IF NOT EXISTS {_PREPARED_TABLE} (
                profile_key TEXT NOT NULL, card_id INTEGER NOT NULL, note_id INTEGER NOT NULL,
                source_hash TEXT NOT NULL, question_preview TEXT NOT NULL, core_aspect TEXT NOT NULL,
                variants_json TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
                updated_at TEXT NOT NULL, uses_front_image INTEGER NOT NULL DEFAULT 0,
                front_visual_mode TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (profile_key, card_id))""")
            for table in (_VARIANTS_TABLE, _PREPARED_TABLE):
                columns = {
                    str(row[1])
                    for row in connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                }
                if "uses_front_image" not in columns:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN "
                        "uses_front_image INTEGER NOT NULL DEFAULT 0"
                    )
                if "front_visual_mode" not in columns:
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN "
                        "front_visual_mode TEXT NOT NULL DEFAULT ''"
                    )

    @staticmethod
    def _is_corruption_error(exc: sqlite3.DatabaseError) -> bool:
        code = getattr(exc, "sqlite_errorcode", None)
        try:
            primary_code = int(code) & 0xFF
        except (TypeError, ValueError):
            primary_code = -1
        corruption_codes = {
            int(value)
            for value in (
                getattr(sqlite3, "SQLITE_CORRUPT", None),
                getattr(sqlite3, "SQLITE_NOTADB", None),
            )
            if value is not None
        }
        if primary_code in corruption_codes:
            return True
        message = " ".join(str(exc).casefold().split())
        return any(
            marker in message
            for marker in (
                "database disk image is malformed",
                "file is not a database",
                "integrity check failed",
            )
        )

    def _quarantine_corrupt_database(self) -> Path:
        """Move a broken cache aside and return its recoverable backup path."""

        if not self.path.is_file():
            raise sqlite3.DatabaseError("corrupt variant cache is missing")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        collision = 1
        while backup.exists():
            backup = self.path.with_name(
                f"{self.path.name}.corrupt-{stamp}-{collision}"
            )
            collision += 1
        self.path.replace(backup)
        # Sidecars are meaningful only together with their original database.
        # Preserve them beside the quarantined file when possible; failure to
        # move an optional sidecar must not block creation of a healthy cache.
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            try:
                if sidecar.exists():
                    sidecar.replace(Path(str(backup) + suffix))
            except OSError:
                pass
        return backup

    def save_generated(self, profile_key: str, generated: GeneratedVariants) -> None:
        self.save_many(profile_key, [generated])

    def save_many(
        self, profile_key: str, generated_items: Iterable[GeneratedVariants]
    ) -> int:
        return self._save_many(_VARIANTS_TABLE, profile_key, generated_items)

    def save_prepared_many(
        self, profile_key: str, generated_items: Iterable[GeneratedVariants]
    ) -> int:
        """Persist one-use variants prepared for live or offline review."""

        return self._save_many(_PREPARED_TABLE, profile_key, generated_items)

    def _save_many(
        self,
        table: str,
        profile_key: str,
        generated_items: Iterable[GeneratedVariants],
    ) -> int:
        items = list(generated_items)
        if not items:
            return 0
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._connection() as connection:
            for generated in items:
                connection.execute(f"""INSERT INTO {table}
                (profile_key,card_id,note_id,source_hash,question_preview,core_aspect,variants_json,provider,model,updated_at,uses_front_image,front_visual_mode)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(profile_key,card_id) DO UPDATE SET
                note_id=excluded.note_id,source_hash=excluded.source_hash,question_preview=excluded.question_preview,
                core_aspect=excluded.core_aspect,variants_json=excluded.variants_json,provider=excluded.provider,
                model=excluded.model,updated_at=excluded.updated_at,uses_front_image=excluded.uses_front_image,
                front_visual_mode=excluded.front_visual_mode""",
                (profile_key,generated.card_id,generated.note_id,generated.source_hash,generated.original_question[:500],
                 generated.core_aspect,json.dumps(generated.variants,ensure_ascii=False),generated.provider,generated.model,
                 timestamp,1 if generated.uses_front_image else 0,str(generated.front_visual_mode or "")))
        return len(items)

    def list_for_profile(self, profile_key: str) -> List[StoredVariants]:
        return self._list_for_profile(_VARIANTS_TABLE, profile_key)

    def list_prepared_for_profile(self, profile_key: str) -> List[StoredVariants]:
        return self._list_for_profile(_PREPARED_TABLE, profile_key)

    def _list_for_profile(
        self, table: str, profile_key: str
    ) -> List[StoredVariants]:
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM {table} WHERE profile_key=? ORDER BY card_id",
                (profile_key,),
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def get(self, profile_key: str, card_id: int) -> Optional[StoredVariants]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM card_variants WHERE profile_key=? AND card_id=?", (profile_key,card_id)).fetchone()
        return self._row_to_model(row) if row else None

    def list_for_cards(self, profile_key: str, card_ids: Iterable[int]) -> List[StoredVariants]:
        return self._list_for_cards(_VARIANTS_TABLE, profile_key, card_ids)

    def list_prepared_for_cards(
        self, profile_key: str, card_ids: Iterable[int]
    ) -> List[StoredVariants]:
        return self._list_for_cards(_PREPARED_TABLE, profile_key, card_ids)

    def _list_for_cards(
        self, table: str, profile_key: str, card_ids: Iterable[int]
    ) -> List[StoredVariants]:
        ids = [int(card_id) for card_id in card_ids]
        if not ids: return []
        placeholders = ",".join("?" for _ in ids)
        with self._connection() as connection:
            rows = connection.execute(f"SELECT * FROM {table} WHERE profile_key=? AND card_id IN (%s) ORDER BY card_id" % placeholders, [profile_key]+ids).fetchall()
        return [self._row_to_model(row) for row in rows]

    def delete_cards(self, profile_key: str, card_ids: Iterable[int]) -> int:
        return self._delete_cards(_VARIANTS_TABLE, profile_key, card_ids)

    def delete_prepared_cards(
        self, profile_key: str, card_ids: Iterable[int]
    ) -> int:
        return self._delete_cards(_PREPARED_TABLE, profile_key, card_ids)

    def _delete_cards(
        self, table: str, profile_key: str, card_ids: Iterable[int]
    ) -> int:
        ids = [int(card_id) for card_id in card_ids]
        if not ids: return 0
        placeholders = ",".join("?" for _ in ids)
        with self._connection() as connection:
            cursor = connection.execute(f"DELETE FROM {table} WHERE profile_key=? AND card_id IN (%s)" % placeholders, [profile_key]+ids)
            return int(cursor.rowcount)

    def delete_profile(self, profile_key: str) -> int:
        with self._connection() as connection:
            total = 0
            for table in (_VARIANTS_TABLE, _PREPARED_TABLE):
                cursor = connection.execute(
                    f"DELETE FROM {table} WHERE profile_key=?", (profile_key,)
                )
                total += int(cursor.rowcount)
            return total

    def delete_prepared_profile(self, profile_key: str) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                f"DELETE FROM {_PREPARED_TABLE} WHERE profile_key=?", (profile_key,)
            )
            return int(cursor.rowcount)

    def count(self, profile_key: str) -> int:
        with self._connection() as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {_VARIANTS_TABLE} WHERE profile_key=?", (profile_key,)).fetchone()
        return int(row[0]) if row else 0

    def prepared_count(self, profile_key: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM {_PREPARED_TABLE} WHERE profile_key=?",
                (profile_key,),
            ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> StoredVariants:
        try:
            decoded = json.loads(row["variants_json"])
        except (TypeError, json.JSONDecodeError):
            decoded = []
        variants = decoded if isinstance(decoded, list) else []
        return StoredVariants(row["profile_key"],int(row["card_id"]),int(row["note_id"]),row["source_hash"],
            row["question_preview"],row["core_aspect"],[v for v in variants if isinstance(v,str)],row["provider"],row["model"],row["updated_at"],
            bool(row["uses_front_image"]) if "uses_front_image" in row.keys() else False,
            str(row["front_visual_mode"]) if "front_visual_mode" in row.keys() else "")
