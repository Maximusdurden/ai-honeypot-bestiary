"""Art generation: idempotency, human skip, caps, failure handling.

The critical test is ``test_ensure_art_called_twice_calls_provider_once``:
a second ``ensure_art`` must make **zero** provider calls.
"""

from __future__ import annotations

import dataclasses

import pytest

from bestiary import art
from bestiary.config import get_settings
from bestiary.models import ArtRecord
from bestiary.taxonomy import classify_species


class FakeProvider:
    """Counts calls and returns deterministic fake PNG bytes."""

    name = "fake/model"

    def __init__(self, data: bytes = b"\x89PNG\r\n\x1a\nfake", fail: bool = False):
        self.calls = 0
        self.prompts: list[str] = []
        self._data = data
        self._fail = fail

    def generate(self, prompt: str) -> bytes:
        self.calls += 1
        self.prompts.append(prompt)
        if self._fail:
            raise art.ProviderError("boom")
        return self._data


@pytest.fixture()
def settings(tmp_path):
    base = get_settings()
    return dataclasses.replace(
        base,
        art_bucket="",
        art_max_species=50,
        art_model="fake/model",
        openrouter_api_key="test-key",
    )


@pytest.fixture(autouse=True)
def _no_blob_io(monkeypatch, tmp_path):
    """Keep blobs on disk inside tmp_path; never touch GCS."""

    def fake_store_blob(signature, data, settings=None):
        target = tmp_path / "art" / f"{signature}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"/bestiary/art/{signature}.png", f"bestiary/{signature}.png"

    monkeypatch.setattr(art, "store_blob", fake_store_blob)


def _tax(**kw):
    base = dict(
        agent_family="python-requests",
        agent_kind="http",
        score=60,
        verdict="likely_agent",
    )
    base.update(kw)
    return classify_species(**base)


def _human_tax():
    return classify_species(
        agent_family="Chrome",
        agent_kind="browser",
        score=5,
        verdict="human",
    )


# ------------------------------------------------------------ idempotency
def test_ensure_art_called_twice_calls_provider_once(sqlite_store, settings):
    tax = _tax()
    provider = FakeProvider()

    first = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings, provider=provider
    )
    second = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings, provider=provider
    )

    assert provider.calls == 1, "art must be generated exactly once per species"
    assert first.status == art.STATUS_GENERATED
    assert second.status == art.STATUS_GENERATED
    assert first.image_url == second.image_url
    assert first.generated_at == second.generated_at


def test_second_call_returns_cached_record_without_provider(sqlite_store, settings):
    tax = _tax()
    art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings,
        provider=FakeProvider(),
    )
    # A provider that explodes proves it is never consulted.
    class Exploding:
        name = "explode"

        def generate(self, prompt):  # pragma: no cover - must not run
            raise AssertionError("provider must not be called on a cache hit")

    cached = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings,
        provider=Exploding(),
    )
    assert cached.status == art.STATUS_GENERATED


def test_force_regenerates(sqlite_store, settings):
    tax = _tax()
    provider = FakeProvider()
    art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings, provider=provider
    )
    art.ensure_art(
        tax.signature, tax, force=True, store=sqlite_store, settings=settings,
        provider=provider,
    )
    assert provider.calls == 2


def test_prompt_is_stored_for_reproducibility(sqlite_store, settings):
    tax = _tax()
    record = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings,
        provider=FakeProvider(),
    )
    assert record.prompt_text
    assert record.prompt_version >= 1
    assert record.model_used == "fake/model"


# ----------------------------------------------------------------- humans
def test_humans_are_rendered_by_default(sqlite_store, settings):
    """Humans get a persona portrait, not a creature."""
    tax = _human_tax()
    assert tax.kingdom == "Humana"
    provider = FakeProvider()

    record = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings, provider=provider
    )

    assert record.status == art.STATUS_GENERATED
    assert provider.calls == 1
    assert record.image_url


def test_human_prompt_uses_a_persona_not_a_creature(sqlite_store, settings):
    tax = _human_tax()
    record = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings,
        provider=FakeProvider(),
    )
    prompt = record.prompt_text.lower()
    # A person must not be described with creature anatomy.
    for banned in ("carapace", "sensor eyes", "manipulators", "abdomen"):
        assert banned not in prompt
    assert "person" in prompt


def test_humans_can_still_be_skipped_by_config(sqlite_store, settings):
    """HONEYPOT_ART_RENDER_HUMANS=0 restores the old behaviour."""
    tax = _human_tax()
    provider = FakeProvider()
    off = dataclasses.replace(settings, art_render_humans=False)

    record = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=off, provider=provider
    )

    assert record.status == art.STATUS_SKIPPED
    assert provider.calls == 0
    assert record.image_url == ""


def test_human_skip_is_persisted(sqlite_store, settings):
    tax = _human_tax()
    off = dataclasses.replace(settings, art_render_humans=False)
    art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=off,
        provider=FakeProvider(),
    )
    stored = sqlite_store.get_art(tax.signature)
    assert stored is not None
    assert stored.status == art.STATUS_SKIPPED


# -------------------------------------------------------------------- cap
def test_cap_enforced(sqlite_store, settings):
    capped = dataclasses.replace(settings, art_max_species=1)
    first, second = _tax(agent_family="GPTBot", agent_kind="ai"), _tax(
        agent_family="curl", agent_kind="http"
    )
    provider = FakeProvider()

    a = art.ensure_art(
        first.signature, first, store=sqlite_store, settings=capped, provider=provider
    )
    b = art.ensure_art(
        second.signature, second, store=sqlite_store, settings=capped, provider=provider
    )

    assert a.status == art.STATUS_GENERATED
    assert b.status == art.STATUS_SKIPPED
    assert b.error == "cap_reached"
    assert provider.calls == 1


def test_cap_does_not_block_cached_species(sqlite_store, settings):
    capped = dataclasses.replace(settings, art_max_species=1)
    tax = _tax()
    provider = FakeProvider()
    art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=capped, provider=provider
    )
    again = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=capped, provider=provider
    )
    assert again.status == art.STATUS_GENERATED
    assert provider.calls == 1


def test_count_generated(sqlite_store, settings):
    assert art.count_generated(sqlite_store) == 0
    tax = _tax()
    art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings,
        provider=FakeProvider(),
    )
    assert art.count_generated(sqlite_store) == 1


# ---------------------------------------------------------------- failure
def test_failure_is_recorded_and_not_retried(sqlite_store, settings):
    tax = _tax()
    provider = FakeProvider(fail=True)

    first = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings, provider=provider
    )
    assert first.status == art.STATUS_FAILED
    assert "boom" in first.error
    assert provider.calls == 1

    # A second call retries only because the record is not "generated"; the
    # point is that nothing retries *automatically* inside one invocation.
    second = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings, provider=provider
    )
    assert second.status == art.STATUS_FAILED
    assert provider.calls == 2


def test_failure_does_not_mark_generated(sqlite_store, settings):
    tax = _tax()
    art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings,
        provider=FakeProvider(fail=True),
    )
    assert art.count_generated(sqlite_store) == 0


def test_empty_provider_output_is_a_failure(sqlite_store, settings):
    tax = _tax()
    record = art.ensure_art(
        tax.signature, tax, store=sqlite_store, settings=settings,
        provider=FakeProvider(data=b""),
    )
    assert record.status == art.STATUS_FAILED


# ---------------------------------------------------------------- storage
def test_public_url_uses_bucket_when_configured(settings):
    with_bucket = dataclasses.replace(settings, art_bucket="my-bucket")
    url = art.public_url("abc123", with_bucket)
    assert url == "https://storage.googleapis.com/my-bucket/bestiary/abc123.png"


def test_public_url_falls_back_to_local_route(settings):
    assert art.public_url("abc123", settings) == "/bestiary/art/abc123.png"


def test_object_path():
    assert art.object_path("deadbeef") == "bestiary/deadbeef.png"


# ------------------------------------------------------------- read paths
def test_art_for_never_generates(sqlite_store, settings):
    assert art.art_for("missing", sqlite_store) is None


def test_art_map_keys_by_signature(sqlite_store):
    sqlite_store.upsert_art(ArtRecord(signature="aaa", status="generated"))
    sqlite_store.upsert_art(ArtRecord(signature="bbb", status="skipped"))
    mapping = art.art_map(sqlite_store)
    assert set(mapping) == {"aaa", "bbb"}
    assert mapping["aaa"].status == "generated"


def test_art_for_survives_store_errors():
    class Broken:
        def get_art(self, signature):
            raise RuntimeError("db down")

    assert art.art_for("x", Broken()) is None


def test_art_map_survives_store_errors():
    class Broken:
        def list_art(self):
            raise RuntimeError("db down")

    assert art.art_map(Broken()) == {}
