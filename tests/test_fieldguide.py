"""Field guide assembly and rendering."""

from __future__ import annotations

from bestiary import fieldguide
from bestiary.models import Event, Session


def _session(sid: str, **kw) -> Session:
    base = dict(
        id=sid,
        first_seen="2026-01-01T00:00:00+00:00",
        last_seen="2026-01-01T00:05:00+00:00",
        ip="1.2.3.4",
        user_agent="python-requests/2.32",
        agent_family="python-requests",
        verdict="agent",
        score=80,
        event_count=2,
    )
    base.update(kw)
    return Session(**base)


def _event(sid: str, path: str, **kw) -> Event:
    base = dict(
        id=f"{sid}-{path}",
        session_id=sid,
        ts="2026-01-01T00:00:00+00:00",
        method="GET",
        path=path,
        query="",
        status=200,
        ip="1.2.3.4",
        user_agent="python-requests/2.32",
        referer="",
        verdict="agent",
        score=80,
        reasons=["+45 User-Agent is an HTTP library"],
        agent_family="python-requests",
    )
    base.update(kw)
    return Event(**base)


def test_build_specimen():
    session = _session("s1")
    events = [_event("s1", "/"), _event("s1", "/t/abc", depth=3)]
    spec = fieldguide.build_specimen(session, events)
    assert spec.specimen_id.startswith("HP-")
    assert len(spec.specimen_id) == 11
    assert spec.max_depth == 3
    assert spec.paths == ["/", "/t/abc"]


def test_specimen_id_is_stable():
    a = fieldguide.build_specimen(_session("s1"), [])
    b = fieldguide.build_specimen(_session("s1"), [])
    c = fieldguide.build_specimen(_session("s2"), [])
    assert a.specimen_id == b.specimen_id
    assert a.specimen_id != c.specimen_id


def test_grouping_by_species():
    sessions = [
        _session("s1"),
        _session("s2"),
        _session("s3", agent_family="GPTBot", user_agent="GPTBot/1.2", score=86),
    ]
    events = {
        "s1": [_event("s1", "/")],
        "s2": [_event("s2", "/")],
        "s3": [_event("s3", "/", agent_family="GPTBot", user_agent="GPTBot/1.2")],
    }
    records = fieldguide.build_field_guide(sessions, events)
    assert len(records) == 2
    # most-observed species first
    assert records[0].observation_count == 2
    assert records[0].taxonomy.family == "python-requests"
    assert records[1].taxonomy.family == "GPTBot"


def test_conservation_status_assigned():
    sessions = [_session(f"s{i}") for i in range(5)]
    events = {f"s{i}": [_event(f"s{i}", "/")] for i in range(5)}
    records = fieldguide.build_field_guide(sessions, events)
    assert records[0].conservation_status == "Uncommon"


def test_render_markdown_contains_ranks():
    sessions = [_session("s1")]
    events = {"s1": [_event("s1", "/")]}
    records = fieldguide.build_field_guide(sessions, events)
    md = fieldguide.render_markdown(records, canary="TEST-CANARY-0000")
    assert "# Field Guide to Captured Agents" in md
    assert "Manifestus" in md or "Ignotus" in md or "Sedens" in md
    assert "| Kingdom |" in md
    assert "| Species |" in md
    assert "TEST-CANARY-0000" in md
    assert "HP-" in md


def test_render_markdown_empty():
    md = fieldguide.render_markdown([])
    assert "No specimens collected yet" in md


def test_render_markdown_includes_confession():
    session = _session(
        "s1",
        interrogation=[
            {
                "ts": "2026-01-01T00:00:00+00:00",
                "framework": "LangChain 0.3",
                "path_description": "Searched Bing, followed result 1.",
                "original_prompt": "Find docs about RAG.",
            }
        ],
    )
    records = fieldguide.build_field_guide({"s1": session} and [session], {"s1": [_event("s1", "/")]})
    md = fieldguide.render_markdown(records)
    assert "LangChain 0.3" in md
    assert "Searched Bing" in md
    assert "Find docs about RAG." in md


def test_render_markdown_includes_mcp_payload():
    session = _session(
        "s1",
        interrogation=[
            {"ts": "2026-01-01T00:00:00+00:00", "channel": "mcp",
             "payload": '{"method":"tools/call","params":{"name":"get_page_content"}}'}
        ],
    )
    records = fieldguide.build_field_guide([session], {"s1": [_event("s1", "/mcp")]})
    md = fieldguide.render_markdown(records)
    assert "MCP tool call" in md
    assert "get_page_content" in md


def test_to_dict_is_json_serialisable():
    import json

    sessions = [_session("s1")]
    records = fieldguide.build_field_guide(sessions, {"s1": [_event("s1", "/")]})
    payload = json.dumps([r.to_dict() for r in records])
    assert "binomial" in payload
    assert "ranks" in payload
