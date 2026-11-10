"""SQLite backend — local dev and tests."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import ArtRecord, Event, Session, TokenRecord
from .store import Store


# --------------------------------------------------------------------------
# session scoring hook
# --------------------------------------------------------------------------
#
# A store that only *reads* records still has to reconstruct a Session, and a
# Session carries an aggregate score and verdict. The real scorer lives in the
# capture layer (it is risk scoring, i.e. detection logic). This package accepts
# it as a hook and falls back to a neutral passthrough, so reading a store never
# invents a verdict it cannot justify.
_summarizer = None


def set_session_summarizer(fn) -> None:
    """Register a callable ``(events_as_dicts) -> (score, verdict)``."""
    global _summarizer
    _summarizer = fn


def _summarize(events: list[Event]) -> tuple[int, str]:
    """Aggregate per-event scores, or report what the events already say.

    Without a registered summarizer the honest answer is the strongest verdict
    any single event already carried -- not a number this package made up.
    """
    if not events:
        return 0, "unknown"
    if _summarizer is not None:
        try:
            return _summarizer([e.__dict__ for e in events])
        except Exception:  # noqa: BLE001 - a bad hook must not break reads
            pass
    score = max((int(e.score or 0) for e in events), default=0)
    verdict = next((e.verdict for e in events if e.verdict != "unknown"), "unknown")
    return score, verdict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    visitor_id    TEXT,
    ts            TEXT NOT NULL,
    day           TEXT NOT NULL,
    method        TEXT,
    path          TEXT,
    query         TEXT,
    status        INTEGER,
    ip            TEXT,
    user_agent    TEXT,
    referer       TEXT,
    headers       TEXT,
    header_order  TEXT,
    token         TEXT,
    parent_token  TEXT,
    depth         INTEGER DEFAULT 0,
    verdict       TEXT,
    score         INTEGER DEFAULT 0,
    reasons       TEXT,
    agent_family  TEXT,
    is_trap       INTEGER DEFAULT 0,
    ms_since_prev INTEGER
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_day ON events(day);
CREATE INDEX IF NOT EXISTS idx_events_verdict ON events(verdict);

CREATE TABLE IF NOT EXISTS tokens (
    token      TEXT PRIMARY KEY,
    parent     TEXT,
    depth      INTEGER,
    session_id TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tokens_session ON tokens(session_id);

CREATE TABLE IF NOT EXISTS probes (
    session_id TEXT PRIMARY KEY,
    ts         TEXT,
    data       TEXT
);

CREATE TABLE IF NOT EXISTS interrogations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    ts         TEXT,
    data       TEXT
);
CREATE INDEX IF NOT EXISTS idx_interro_session ON interrogations(session_id);

CREATE TABLE IF NOT EXISTS art (
    signature      TEXT PRIMARY KEY,
    status         TEXT NOT NULL DEFAULT 'pending',
    image_url      TEXT DEFAULT '',
    image_path     TEXT DEFAULT '',
    prompt_version INTEGER DEFAULT 1,
    prompt_text    TEXT DEFAULT '',
    model_used     TEXT DEFAULT '',
    generated_at   TEXT DEFAULT '',
    error          TEXT DEFAULT ''
);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SQLiteStore(Store):
    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.commit()

    # --- writes -------------------------------------------------------
    def record_event(self, event: Event) -> None:
        day = event.ts[:10]
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO events
                   (id, session_id, visitor_id, ts, day, method, path, query, status,
                    ip, user_agent, referer, headers, header_order, token, parent_token,
                    depth, verdict, score, reasons, agent_family, is_trap, ms_since_prev)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.id,
                    event.session_id,
                    getattr(event, "visitor_id", None),
                    event.ts,
                    day,
                    event.method,
                    event.path,
                    event.query,
                    event.status,
                    event.ip,
                    event.user_agent,
                    event.referer,
                    json.dumps(event.headers),
                    json.dumps(event.header_order),
                    event.token,
                    event.parent_token,
                    event.depth,
                    event.verdict,
                    event.score,
                    json.dumps(event.reasons),
                    event.agent_family,
                    1 if event.is_trap else 0,
                    event.ms_since_prev,
                ),
            )
            self._conn.commit()

    def record_token(self, record: TokenRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tokens (token, parent, depth, session_id, created_at)"
                " VALUES (?,?,?,?,?)",
                (
                    record.token,
                    record.parent,
                    record.depth,
                    record.session_id,
                    record.created_at,
                ),
            )
            self._conn.commit()

    def record_probe(self, session_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO probes (session_id, ts, data) VALUES (?,?,?)",
                (session_id, _utcnow().isoformat(), json.dumps(data)),
            )
            self._conn.commit()

    def record_interrogation(self, session_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO interrogations (session_id, ts, data) VALUES (?,?,?)",
                (session_id, _utcnow().isoformat(), json.dumps(data)),
            )
            self._conn.commit()

    # --- reads --------------------------------------------------------
    def get_token(self, token: str) -> TokenRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tokens WHERE token = ?", (token,)
            ).fetchone()
        if not row:
            return None
        return TokenRecord(
            token=row["token"],
            parent=row["parent"],
            depth=row["depth"],
            session_id=row["session_id"],
            created_at=row["created_at"],
        )

    def get_events(self, session_id: str, limit: int = 500) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY ts ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_session(self, session_id: str) -> Session | None:
        events = self.get_events(session_id)
        if not events:
            return None
        with self._lock:
            probe_row = self._conn.execute(
                "SELECT data FROM probes WHERE session_id = ?", (session_id,)
            ).fetchone()
            interro_rows = self._conn.execute(
                "SELECT ts, data FROM interrogations WHERE session_id = ? ORDER BY ts",
                (session_id,),
            ).fetchall()
        score, verdict = _summarize(events)
        tokens = [e.token for e in events if e.token]
        return Session(
            id=session_id,
            first_seen=events[0].ts,
            last_seen=events[-1].ts,
            ip=events[-1].ip,
            user_agent=events[-1].user_agent,
            agent_family=next((e.agent_family for e in events if e.agent_family), None),
            agent_kind=next(
                (getattr(e, "agent_kind", "") for e in events if getattr(e, "agent_kind", "")),
                "unknown",
            ),
            verdict=verdict,
            score=score,
            event_count=len(events),
            tokens=tokens,
            probe=json.loads(probe_row["data"]) if probe_row else None,
            interrogation=[
                {"ts": r["ts"], **json.loads(r["data"])} for r in interro_rows
            ],
        )

    def list_sessions(
        self, limit: int = 50, offset: int = 0, verdict: str | None = None
    ) -> list[Session]:
        with self._lock:
            if verdict:
                rows = self._conn.execute(
                    """SELECT session_id FROM events
                       WHERE session_id IN (
                           SELECT session_id FROM events GROUP BY session_id
                           HAVING MAX(score) >= ?
                       )
                       GROUP BY session_id
                       ORDER BY MAX(ts) DESC LIMIT ? OFFSET ?""",
                    (_verdict_floor(verdict), limit, offset),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT session_id FROM events GROUP BY session_id
                       ORDER BY MAX(ts) DESC LIMIT ? OFFSET ?""",
                    (limit, offset),
                ).fetchall()
        out: list[Session] = []
        for row in rows:
            session = self.get_session(row["session_id"])
            if session:
                out.append(session)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total_events = self._conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
            total_sessions = self._conn.execute(
                "SELECT COUNT(DISTINCT session_id) c FROM events"
            ).fetchone()["c"]
            by_verdict = {
                r["verdict"]: r["c"]
                for r in self._conn.execute(
                    "SELECT verdict, COUNT(DISTINCT session_id) c FROM events GROUP BY verdict"
                ).fetchall()
            }
            by_family = {
                r["agent_family"]: r["c"]
                for r in self._conn.execute(
                    """SELECT agent_family, COUNT(DISTINCT session_id) c FROM events
                       WHERE agent_family IS NOT NULL GROUP BY agent_family
                       ORDER BY c DESC LIMIT 20"""
                ).fetchall()
            }
            traps = self._conn.execute(
                "SELECT COUNT(*) c FROM events WHERE is_trap = 1"
            ).fetchone()["c"]
            interro = self._conn.execute(
                "SELECT COUNT(*) c FROM interrogations"
            ).fetchone()["c"]
        return {
            "total_events": total_events,
            "total_sessions": total_sessions,
            "by_verdict": by_verdict,
            "by_family": by_family,
            "trap_hits": traps,
            "interrogations": interro,
        }

    def pages_today(self) -> int:
        day = _utcnow().date().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) c FROM events WHERE day = ?", (day,)
            ).fetchone()
        return int(row["c"])

    def purge_older_than(self, days: int) -> int:
        cutoff = (_utcnow() - timedelta(days=days)).isoformat()
        with self._lock:
            cur = self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM tokens WHERE created_at < ?", (cutoff,))
            self._conn.execute("DELETE FROM interrogations WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount

    def export_sessions(
        self, limit: int = 500
    ) -> list[tuple[Session, list[Event]]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT session_id FROM events GROUP BY session_id
                   ORDER BY MAX(ts) DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        out: list[tuple[Session, list[Event]]] = []
        for row in rows:
            sid = row["session_id"]
            session = self.get_session(sid)
            if session:
                out.append((session, self.get_events(sid)))
        return out

    # --- art ----------------------------------------------------------
    def get_art(self, signature: str) -> ArtRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM art WHERE signature = ?", (signature,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_art(row)

    def upsert_art(self, record: ArtRecord) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO art
                   (signature, status, image_url, image_path, prompt_version,
                    prompt_text, model_used, generated_at, error)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    record.signature,
                    record.status,
                    record.image_url,
                    record.image_path,
                    record.prompt_version,
                    record.prompt_text,
                    record.model_used,
                    record.generated_at,
                    record.error,
                ),
            )
            self._conn.commit()

    def list_art(self, *, strict: bool = False) -> list[ArtRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM art ORDER BY signature ASC"
            ).fetchall()
        return [self._row_to_art(r) for r in rows]

    # --- helpers ------------------------------------------------------
    @staticmethod
    def _row_to_art(row: sqlite3.Row) -> ArtRecord:
        return ArtRecord(
            signature=row["signature"],
            status=row["status"] or "pending",
            image_url=row["image_url"] or "",
            image_path=row["image_path"] or "",
            prompt_version=int(row["prompt_version"] or 1),
            prompt_text=row["prompt_text"] or "",
            model_used=row["model_used"] or "",
            generated_at=row["generated_at"] or "",
            error=row["error"] or "",
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        event = Event(
            id=row["id"],
            session_id=row["session_id"],
            ts=row["ts"],
            method=row["method"],
            path=row["path"],
            query=row["query"],
            status=row["status"],
            ip=row["ip"],
            user_agent=row["user_agent"],
            referer=row["referer"],
            headers=json.loads(row["headers"] or "{}"),
            header_order=json.loads(row["header_order"] or "[]"),
            token=row["token"],
            parent_token=row["parent_token"],
            depth=row["depth"] or 0,
            verdict=row["verdict"] or "unknown",
            score=row["score"] or 0,
            reasons=json.loads(row["reasons"] or "[]"),
            agent_family=row["agent_family"],
            is_trap=bool(row["is_trap"]),
            ms_since_prev=row["ms_since_prev"],
        )
        event.visitor_id = row["visitor_id"]  # type: ignore[attr-defined]
        return event


# Score thresholds that separate verdict bands, lowest first.
#
# The real table is tuned against captured traffic and therefore lives in the
# capture layer. This copy exists only so ``list_sessions(verdict=...)`` can turn
# a band name into a numeric floor. Register the deployment's own table with
# ``set_verdict_thresholds()`` to filter by its real cut-offs.
_THRESHOLDS: list[tuple[int, str]] = [
    (0, "unknown"),
    (20, "likely_human"),
    (40, "crawler"),
    (60, "likely_agent"),
    (80, "agent"),
]


def set_verdict_thresholds(thresholds: list[tuple[int, str]]) -> None:
    """Replace the verdict bands with a deployment's real thresholds."""
    global _THRESHOLDS
    _THRESHOLDS = sorted(((int(t), str(v)) for t, v in thresholds), key=lambda p: p[0])


def _verdict_floor(verdict: str) -> int:
    for threshold, label in _THRESHOLDS:
        if label == verdict:
            return threshold
    return 0
