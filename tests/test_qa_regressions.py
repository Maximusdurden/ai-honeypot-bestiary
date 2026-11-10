"""Regression tests for defects found by adversarial QA review.

Each test here corresponds to a specific bug that the original 235-test suite
did not catch. They exist so the same defect cannot silently return.
"""

from __future__ import annotations

import pytest

from bestiary import art, bestiary, visual_dna
from bestiary.fieldguide import Specimen, build_specimen
from bestiary.models import Event, Session
from bestiary.taxonomy import classify_species


def _tax(family: str = "GPTBot") -> object:
    return classify_species(
        agent_family=family, agent_kind="ai", score=90, verdict="agent"
    )


# --------------------------------------------------------------------------
# BUG-1: a ``generated`` record with an empty image_url is not a portrait.
# --------------------------------------------------------------------------
class _EmptyUrlStore:
    def __init__(self, signature: str) -> None:
        self.record = art.ArtRecord(
            signature=signature, status=art.STATUS_GENERATED, image_url=""
        )

    def get_art(self, signature):
        return self.record

    def list_art(self, *, strict: bool = False):
        return [self.record]

    def upsert_art(self, record):
        self.record = record


class _CountingProvider:
    name = "counting"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return b"\x89PNG fake"


def test_generated_record_without_url_is_regenerated(monkeypatch):
    tax = _tax()
    store = _EmptyUrlStore(tax.signature)
    provider = _CountingProvider()
    monkeypatch.setattr(art, "store_blob", lambda *a, **k: ("https://x/y.png", "p/y.png"))

    record = art.ensure_art(tax.signature, tax, store=store, provider=provider)

    assert provider.calls == 1, "a broken record must be regenerated"
    assert record.status == art.STATUS_GENERATED
    assert record.image_url == "https://x/y.png"


# --------------------------------------------------------------------------
# BUG-2: a store read failure must FAIL CLOSED, never generate.
# --------------------------------------------------------------------------
class _BrokenReadStore:
    def get_art(self, signature):
        raise RuntimeError("db down")

    def list_art(self):
        return []

    def upsert_art(self, record):
        raise AssertionError("must not write when the cache is unreadable")


def test_store_read_failure_aborts_generation(monkeypatch):
    tax = _tax()
    provider = _CountingProvider()
    monkeypatch.setattr(art, "store_blob", lambda *a, **k: ("u", "p"))

    with pytest.raises(art.StoreUnavailable):
        art.ensure_art(tax.signature, tax, store=_BrokenReadStore(), provider=provider)

    assert provider.calls == 0, "must not spend money when cache state is unknown"


# --------------------------------------------------------------------------
# BUG-3: the cost cap must FAIL CLOSED when the store is unhealthy.
# --------------------------------------------------------------------------
class _BrokenListStore:
    def get_art(self, signature):
        return None

    def list_art(self):
        raise RuntimeError("db down")

    def upsert_art(self, record):
        pass


def test_count_generated_raises_on_store_failure():
    with pytest.raises(art.StoreUnavailable):
        art.count_generated(_BrokenListStore())


def test_cap_failure_prevents_generation(monkeypatch):
    tax = _tax()
    provider = _CountingProvider()
    monkeypatch.setattr(art, "store_blob", lambda *a, **k: ("u", "p"))

    with pytest.raises(art.StoreUnavailable):
        art.ensure_art(tax.signature, tax, store=_BrokenListStore(), provider=provider)

    assert provider.calls == 0


# --------------------------------------------------------------------------
# BUG-4: Family and Species must influence the prompt.
# --------------------------------------------------------------------------
def test_two_species_in_same_genus_differ_in_prompt():
    """GPTBot and OAI-SearchBot share kingdom/phylum/class/order/genus."""
    a = _tax("GPTBot")
    b = _tax("OAI-SearchBot")

    assert a.signature != b.signature
    assert a.genus == b.genus
    assert a.order == b.order
    assert visual_dna.build_prompt(a) != visual_dna.build_prompt(b)


@pytest.mark.parametrize(
    "rank,left,right",
    [
        ("kingdom", "Machina", "Dubia"),
        ("phylum", "Agentia", "Crawlera"),
        ("taxon_class", "LlmAgentia", "ScriptaClientia"),
        ("order", "OpenAI", "Anthropic"),
        ("family", "GPTBot", "ClaudeBot"),
        ("genus", "Manifestus", "Furtim"),
        ("species", "gptbotensis", "claudebotensis"),
    ],
)
def test_every_rank_changes_the_prompt(rank, left, right):
    base = {
        "kingdom": "Machina",
        "phylum": "Agentia",
        "taxon_class": "LlmAgentia",
        "order": "OpenAI",
        "family": "GPTBot",
        "genus": "Manifestus",
        "species": "gptbotensis",
        "diagnostic_characters": [],
    }
    other = dict(base)
    other[rank] = right
    base[rank] = left

    assert visual_dna.build_prompt(base) != visual_dna.build_prompt(other), (
        f"changing {rank} must change the prompt"
    )


def test_prompt_is_deterministic():
    tax = _tax()
    assert visual_dna.build_prompt(tax) == visual_dna.build_prompt(tax)


def test_prompt_has_no_none_leak():
    tax = classify_species(
        agent_family=None, agent_kind="unknown", score=0, verdict="unknown"
    )
    prompt = visual_dna.build_prompt(tax)
    assert "None" not in prompt
    assert "{" not in prompt and "}" not in prompt


# --------------------------------------------------------------------------
# BUG-6: stats must be derived from real telemetry, not constants.
# --------------------------------------------------------------------------
def _session(sid: str = "s1") -> Session:
    return Session(
        id=sid,
        first_seen="2026-01-01T00:00:00+00:00",
        last_seen="2026-01-01T00:10:00+00:00",
        ip="1.2.3.4",
        user_agent="python-requests/2.32",
        agent_family="python-requests",
        verdict="agent",
        score=80,
        event_count=3,
    )


def _event(sid: str, path: str, **kw) -> Event:
    base = dict(
        id=f"{sid}-{path}-{kw.get('ts', '')}",
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
        reasons=[],
        agent_family="python-requests",
    )
    base.update(kw)
    return Event(**base)


def test_specimen_carries_telemetry_fields():
    events = [
        _event("s1", "/", ts="2026-01-01T00:00:00+00:00"),
        _event("s1", "/trap/hidden", ts="2026-01-01T00:05:00+00:00", is_trap=True),
        _event("s1", "/trap/pixel", ts="2026-01-01T00:05:00+00:00", is_trap=True),
    ]
    spec = build_specimen(_session(), events)

    assert spec.trap_hits == 2
    assert spec.first_seen == "2026-01-01T00:00:00+00:00"
    assert spec.last_seen == "2026-01-01T00:05:00+00:00"


def test_attack_reflects_trap_hits_on_a_real_specimen():
    """The original bug: Attack was always 30 because Specimen lacked trap_hits."""
    quiet = build_specimen(_session("a"), [_event("a", "/")])
    trapped = build_specimen(
        _session("b"),
        [
            _event("b", "/"),
            _event("b", "/trap/hidden", is_trap=True),
            _event("b", "/trap/pixel", is_trap=True),
        ],
    )

    assert bestiary.build_stats(quiet)["attack"] == 30
    assert bestiary.build_stats(trapped)["attack"] == 80


def test_defense_reflects_session_duration_on_a_real_specimen():
    """The original bug: Defense was always 30 because Specimen lacked timestamps."""
    short = build_specimen(
        _session("a"),
        [
            _event("a", "/", ts="2026-01-01T00:00:00+00:00"),
            _event("a", "/x", ts="2026-01-01T00:00:10+00:00"),
        ],
    )
    long = build_specimen(
        _session("b"),
        [
            _event("b", "/", ts="2026-01-01T00:00:00+00:00"),
            _event("b", "/x", ts="2026-01-01T01:00:00+00:00"),
        ],
    )

    assert bestiary.build_stats(short)["defense"] == 30
    assert bestiary.build_stats(long)["defense"] > 30


def test_speed_reflects_inter_request_interval_on_a_real_specimen():
    """The original bug: Speed was always 120 because Specimen lacked min_interval_ms."""
    slow = build_specimen(
        _session("a"),
        [
            _event("a", "/", ts="2026-01-01T00:00:00+00:00"),
            _event("a", "/x", ts="2026-01-01T00:00:10+00:00", ms_since_prev=10000),
        ],
    )
    fast = build_specimen(
        _session("b"),
        [
            _event("b", "/", ts="2026-01-01T00:00:00+00:00"),
            _event("b", "/x", ts="2026-01-01T00:00:00.05+00:00", ms_since_prev=50),
        ],
    )

    assert bestiary.build_stats(fast)["speed"] > bestiary.build_stats(slow)["speed"]


def test_stats_are_not_all_identical_across_species():
    """Guard against the whole stat block collapsing to constants."""
    a = build_specimen(_session("a"), [_event("a", "/")])
    b = build_specimen(
        _session("b"),
        [
            _event("b", "/", ts="2026-01-01T00:00:00+00:00"),
            _event("b", "/trap/hidden", ts="2026-01-01T02:00:00+00:00",
                   is_trap=True, ms_since_prev=30),
        ],
    )
    stats_a = bestiary.build_stats(a)
    stats_b = bestiary.build_stats(b)
    assert stats_a != stats_b


# --------------------------------------------------------------------------
# BUG-8: the kill switch must actually stop generation.
# --------------------------------------------------------------------------
def test_art_disabled_skips_generation(monkeypatch, tmp_path):
    from bestiary.config import Settings

    tax = _tax()
    provider = _CountingProvider()
    monkeypatch.setattr(art, "store_blob", lambda *a, **k: ("u", "p"))

    from bestiary.store_sqlite import SQLiteStore

    store = SQLiteStore(str(tmp_path / "art.db"))
    settings = Settings(
        store="sqlite",
        sqlite_path=str(tmp_path / "art.db"),
        secret_key="k",
        public_base_url="http://x",
        canary="c",
        max_events_per_session=500,
        tarpit_max_depth=200,
        daily_page_budget=1000,
        rate_limit_per_minute=100,
        retention_days=90,
        admin_token="",
        project="",
        region="us-east1",
        service="s",
        art_enabled=False,
    )

    record = art.ensure_art(
        tax.signature, tax, store=store, settings=settings, provider=provider
    )

    assert provider.calls == 0
    assert record.status == art.STATUS_SKIPPED
    assert "disabled" in record.error


# --------------------------------------------------------------------------
# BUG-9: --force must not bypass the cost cap for NEW species.
# --------------------------------------------------------------------------
def test_force_does_not_bypass_cap(monkeypatch, tmp_path):
    from bestiary.config import Settings
    from bestiary.store_sqlite import SQLiteStore

    tax = _tax()
    provider = _CountingProvider()
    monkeypatch.setattr(art, "store_blob", lambda *a, **k: ("u", "p"))

    store = SQLiteStore(str(tmp_path / "cap.db"))
    # Pretend the cap is already reached.
    store.upsert_art(
        art.ArtRecord(
            signature="other", status=art.STATUS_GENERATED, image_url="https://x/y.png"
        )
    )
    settings = Settings(
        store="sqlite",
        sqlite_path=str(tmp_path / "cap.db"),
        secret_key="k",
        public_base_url="http://x",
        canary="c",
        max_events_per_session=500,
        tarpit_max_depth=200,
        daily_page_budget=1000,
        rate_limit_per_minute=100,
        retention_days=90,
        admin_token="",
        project="",
        region="us-east1",
        service="s",
        art_enabled=True,
        art_max_species=1,
    )

    record = art.ensure_art(
        tax.signature,
        tax,
        force=True,
        store=store,
        settings=settings,
        provider=provider,
    )

    assert provider.calls == 0, "force must not license new spend past the cap"
    assert record.status == art.STATUS_SKIPPED
