"""Bestiary mechanics: type chart, stat formulas, dex numbers."""

from __future__ import annotations

import pytest

from bestiary import bestiary


# ------------------------------------------------------------- type chart
@pytest.mark.parametrize(
    "klass,expected",
    [
        ("LlmAgentia", "Psychic"),
        ("IndexCrawlera", "Normal"),
        ("AutomataBrowsera", "Ghost"),
        ("ScriptaClientia", "Steel"),
        ("Sapiena", "Fairy"),
        ("Incerta", "???"),
    ],
)
def test_type_chart(klass, expected):
    assert bestiary.type_for(klass) == expected


def test_unknown_class_is_unknown_type():
    assert bestiary.type_for("Nonexistent") == bestiary.UNKNOWN_TYPE
    assert bestiary.type_for(None) == bestiary.UNKNOWN_TYPE


def test_every_type_has_colors():
    for pokemon_type in bestiary.TYPE_BY_CLASS.values():
        bg, fg = bestiary.type_colors(pokemon_type)
        assert bg.startswith("#") and fg.startswith("#")


# ------------------------------------------------------------ dex numbers
def test_dex_number_is_stable():
    sig = "a1b2c3d4e5f60718"
    assert bestiary.dex_number(sig) == bestiary.dex_number(sig)


def test_dex_number_matches_formula():
    sig = "a1b2c3d4e5f60718"
    assert bestiary.dex_number(sig) == int(sig[:6], 16) % 1000


def test_dex_number_in_range():
    for sig in ("0000000000000000", "ffffffffffffffff", "0123456789abcdef"):
        assert 0 <= bestiary.dex_number(sig) < 1000


def test_dex_label_is_zero_padded():
    label = bestiary.dex_label("0000000000000000")
    assert label == "#000"
    assert len(label) == 4


def test_dex_number_handles_non_hex():
    assert isinstance(bestiary.dex_number("zzzzzz"), int)


# ------------------------------------------------------------------ level
@pytest.mark.parametrize(
    "score,expected",
    [(0, 1), (9, 1), (10, 2), (55, 6), (99, 10), (100, 11)],
)
def test_level_formula(score, expected):
    assert bestiary.level_for(score) == expected


def test_level_is_clamped():
    assert bestiary.level_for(-50) == 1
    assert bestiary.level_for(10_000) == 11


# ------------------------------------------------------------------ stats
def test_hp_formula():
    assert bestiary.build_stats({"event_count": 0})["hp"] == 20
    assert bestiary.build_stats({"event_count": 10})["hp"] == 60


def test_hp_is_clamped():
    assert bestiary.build_stats({"event_count": 10_000})["hp"] == 255


def test_attack_formula():
    assert bestiary.build_stats({"trap_hits": 0})["attack"] == 30
    assert bestiary.build_stats({"trap_hits": 2})["attack"] == 80


def test_attack_is_clamped():
    assert bestiary.build_stats({"trap_hits": 100})["attack"] == 255


def test_defense_from_session_duration():
    stats = bestiary.build_stats(
        {
            "first_seen": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-01T00:10:00+00:00",
        }
    )
    assert stats["defense"] == 50  # 30 + 10 minutes * 2


def test_defense_is_clamped():
    stats = bestiary.build_stats(
        {
            "first_seen": "2026-01-01T00:00:00+00:00",
            "last_seen": "2026-01-02T00:00:00+00:00",
        }
    )
    assert stats["defense"] == 255


def test_defense_zero_without_timestamps():
    assert bestiary.build_stats({})["defense"] == 30


def test_speed_formula():
    assert bestiary.build_stats({"min_interval_ms": 0})["speed"] == 255
    assert bestiary.build_stats({"min_interval_ms": 400})["speed"] == 155


def test_speed_has_floor_of_ten():
    assert bestiary.build_stats({"min_interval_ms": 10_000})["speed"] == 10


def test_special_from_confession():
    assert bestiary.build_stats({"confessed": True})["special"] == 200
    assert bestiary.build_stats({"confessed": False})["special"] == 60


def test_special_from_interrogation_list():
    stats = bestiary.build_stats({"interrogation": [{"framework": "LangChain"}]})
    assert stats["special"] == 200


def test_mcp_call_is_not_a_confession():
    stats = bestiary.build_stats({"interrogation": [{"channel": "mcp"}]})
    assert stats["special"] == 60


def test_all_stats_clamped_to_byte_range():
    stats = bestiary.build_stats(
        {
            "score": 100,
            "event_count": 99_999,
            "trap_hits": 99_999,
            "min_interval_ms": 0,
            "confessed": True,
        }
    )
    for key in bestiary.STAT_ORDER:
        assert 0 <= stats[key] <= 255


def test_build_stats_accepts_object():
    class Spec:
        score = 50
        event_count = 5
        trap_hits = 1
        min_interval_ms = 100
        interrogation = []
        first_seen = "2026-01-01T00:00:00+00:00"
        last_seen = "2026-01-01T00:05:00+00:00"

    stats = bestiary.build_stats(Spec())
    assert stats["level"] == 6
    assert stats["hp"] == 40
    assert stats["attack"] == 55


def test_stat_bars_shape():
    bars = bestiary.stat_bars(bestiary.build_stats({}))
    assert [b["key"] for b in bars] == list(bestiary.STAT_ORDER)
    assert all(0 <= b["pct"] <= 100 for b in bars)


def test_species_stats_picks_strongest_specimen():
    class Rec:
        specimens = [
            {"score": 20, "event_count": 1},
            {"score": 90, "event_count": 9},
        ]

    assert bestiary.species_stats(Rec())["level"] == 10


def test_species_stats_without_specimens():
    class Rec:
        specimens: list = []

    assert bestiary.species_stats(Rec())["level"] == 1
