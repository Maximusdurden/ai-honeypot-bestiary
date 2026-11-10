"""Store protocol + factory.

Two backends implement the same interface:

* ``SQLiteStore``    — local dev, tests, single-file durability
* ``FirestoreStore`` — Cloud Run production

The app never branches on backend; it calls ``get_store()``.
"""

from __future__ import annotations

import abc
from typing import Any

from .config import Settings, get_settings
from .models import ArtRecord, Event, Session, TokenRecord


class Store(abc.ABC):
    """Append-only event log plus session/token indexes."""

    # --- writes -------------------------------------------------------
    @abc.abstractmethod
    def record_event(self, event: Event) -> None: ...

    @abc.abstractmethod
    def record_token(self, record: TokenRecord) -> None: ...

    @abc.abstractmethod
    def record_probe(self, session_id: str, data: dict[str, Any]) -> None: ...

    @abc.abstractmethod
    def record_interrogation(self, session_id: str, data: dict[str, Any]) -> None: ...

    # --- reads --------------------------------------------------------
    @abc.abstractmethod
    def get_token(self, token: str) -> TokenRecord | None: ...

    @abc.abstractmethod
    def get_session(self, session_id: str) -> Session | None: ...

    @abc.abstractmethod
    def get_events(self, session_id: str, limit: int = 500) -> list[Event]: ...

    @abc.abstractmethod
    def list_sessions(
        self, limit: int = 50, offset: int = 0, verdict: str | None = None
    ) -> list[Session]: ...

    @abc.abstractmethod
    def stats(self) -> dict[str, Any]: ...

    @abc.abstractmethod
    def pages_today(self) -> int: ...

    @abc.abstractmethod
    def purge_older_than(self, days: int) -> int: ...

    @abc.abstractmethod
    def export_sessions(
        self, limit: int = 500
    ) -> list[tuple[Session, list[Event]]]:
        """Every session with its events, newest first. Used by the field guide."""

    # --- art (Bestiary portraits) --------------------------------------
    @abc.abstractmethod
    def get_art(self, signature: str) -> ArtRecord | None:
        """The cached portrait record for one species, or ``None``."""

    @abc.abstractmethod
    def upsert_art(self, record: ArtRecord) -> None:
        """Insert or replace the portrait record for ``record.signature``."""

    @abc.abstractmethod
    def list_art(self, *, strict: bool = False) -> list[ArtRecord]:
        """Every art record.

        ``strict=True`` re-raises read failures instead of returning ``[]``.
        The cost cap MUST use strict mode: an empty list caused by a transient
        database error is indistinguishable from "nothing generated yet", and
        treating it as the latter silently disables the cap.
        """
        """Every portrait record, ordered by signature."""

    def close(self) -> None:  # pragma: no cover - optional
        return None


def get_store(settings: Settings | None = None) -> Store:
    """Build the configured backend."""
    settings = settings or get_settings()
    if settings.store == "firestore":
        from .store_firestore import FirestoreStore

        return FirestoreStore(settings)
    from .store_sqlite import SQLiteStore

    return SQLiteStore(settings.sqlite_path)
