"""Shared fixtures for the public bestiary test suite.

Deliberately no FastAPI ``client`` fixture: this package is the interpretation
layer, and the tests exercise it directly rather than through HTTP. That keeps
the suite honest about what the public code actually contains.

Every fixture here is offline. Nothing reaches the network, GCS, or a store on
disk outside ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bestiary import fieldguide
from bestiary.models import Event, Session
from bestiary.store_sqlite import SQLiteStore

FIXTURE_FILE = Path(__file__).resolve().parent.parent / "fixtures" / "synthetic_sessions.json"


@pytest.fixture(scope="session")
def corpus() -> dict:
    """The synthetic corpus, loaded once."""
    return json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def corpus_sessions(corpus) -> list[Session]:
    return [Session(**row) for row in corpus["sessions"]]


@pytest.fixture(scope="session")
def corpus_events(corpus_sessions, corpus) -> dict[str, list[Event]]:
    """Events keyed by session id, matching what a store would return."""
    out: dict[str, list[Event]] = {s.id: [] for s in corpus_sessions}
    for row in corpus["events"]:
        out.setdefault(row["session_id"], []).append(Event(**row))
    for events in out.values():
        events.sort(key=lambda e: e.ts)
    return out


@pytest.fixture(scope="session")
def species_records(corpus_sessions, corpus_events):
    """The field guide built from the synthetic corpus."""
    return fieldguide.build_field_guide(corpus_sessions, corpus_events)


@pytest.fixture()
def sqlite_store(tmp_path):
    """A throwaway SQLite store per test."""
    store = SQLiteStore(str(tmp_path / "test.db"))
    yield store
    close = getattr(store, "close", None)
    if close is not None:
        close()


@pytest.fixture()
def seeded_store(sqlite_store, corpus_sessions, corpus_events):
    """A store preloaded with the synthetic corpus."""
    for session in corpus_sessions:
        for event in corpus_events.get(session.id, []):
            sqlite_store.record_event(event)
        if session.probe:
            sqlite_store.record_probe(session.id, session.probe)
        for item in session.interrogation:
            sqlite_store.record_interrogation(session.id, item)
    return sqlite_store
