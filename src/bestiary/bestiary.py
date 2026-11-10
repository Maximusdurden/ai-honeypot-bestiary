"""Bestiary mechanics: types, stats, and stable dex numbers.

Everything here is a pure function of the taxonomy and the specimen telemetry,
so a species' card is reproducible from stored data alone.

    Class                 Type
    --------------------  ------
    LlmAgentia            Psychic
    IndexCrawlera         Normal
    AutomataBrowsera      Ghost
    ScriptaClientia       Steel
    Sapiena               Fairy
    Incerta               ???
"""

from __future__ import annotations

from typing import Any

# --- type chart ----------------------------------------------------------
TYPE_BY_CLASS: dict[str, str] = {
    "LlmAgentia": "Psychic",
    "IndexCrawlera": "Normal",
    "AutomataBrowsera": "Ghost",
    "ScriptaClientia": "Steel",
    "Sapiena": "Fairy",
    "Incerta": "???",
}

UNKNOWN_TYPE = "???"

# Type -> (background, foreground) for the badge. Kept here so templates stay
# logic-free and the palette lives in one place.
TYPE_COLORS: dict[str, tuple[str, str]] = {
    "Psychic": ("#c026d3", "#ffffff"),
    "Normal": ("#78716c", "#ffffff"),
    "Ghost": ("#7c3aed", "#ffffff"),
    "Steel": ("#0284c7", "#ffffff"),
    "Fairy": ("#ec4899", "#ffffff"),
    UNKNOWN_TYPE: ("#64748b", "#ffffff"),
}

# --- stat names, in display order ---------------------------------------
STAT_ORDER: tuple[str, ...] = ("hp", "attack", "defense", "speed", "special")

STAT_LABELS: dict[str, str] = {
    "hp": "HP",
    "attack": "Attack",
    "defense": "Defense",
    "speed": "Speed",
    "special": "Special",
}

STAT_MAX = 255

# One colour per stat, so the bars read as a colourful chart rather than a
# single flat accent.
STAT_COLORS: dict[str, str] = {
    "hp": "#22c55e",
    "attack": "#ef4444",
    "defense": "#3b82f6",
    "speed": "#f59e0b",
    "special": "#a855f7",
}


def _clamp(value: int, low: int = 0, high: int = STAT_MAX) -> int:
    return max(low, min(high, int(value)))


def type_for(taxon_class: str | None) -> str:
    """The Pokémon type for a taxonomic class."""
    return TYPE_BY_CLASS.get(taxon_class or "", UNKNOWN_TYPE)


def type_colors(pokemon_type: str) -> tuple[str, str]:
    return TYPE_COLORS.get(pokemon_type, TYPE_COLORS[UNKNOWN_TYPE])


def dex_number(signature: str) -> int:
    """Stable dex number derived from the signature.

    ``int(signature[:6], 16) % 1000``. No coordination or ordering needed, and
    the same species always gets the same number.
    """
    head = (signature or "")[:6]
    try:
        return int(head, 16) % 1000
    except ValueError:
        # Non-hex signature (shouldn't happen): fall back to a stable hash.
        return sum(ord(c) for c in signature or "") % 1000


def dex_label(signature: str) -> str:
    """Zero-padded dex number, e.g. ``#007``."""
    return f"#{dex_number(signature):03d}"


def level_for(score: int) -> int:
    """Level 1-11 from the classification score (0-100)."""
    return max(1, min(11, 1 + int(score or 0) // 10))


def _minutes_between(first_seen: str, last_seen: str) -> float:
    """Session duration in minutes; 0.0 when timestamps are unusable."""
    from datetime import datetime

    try:
        start = datetime.fromisoformat(first_seen)
        end = datetime.fromisoformat(last_seen)
    except (TypeError, ValueError):
        return 0.0
    delta = (end - start).total_seconds() / 60.0
    return max(0.0, delta)


def _get(specimen: Any, name: str, default: Any = None) -> Any:
    if isinstance(specimen, dict):
        return specimen.get(name, default)
    return getattr(specimen, name, default)


def build_stats(specimen: Any) -> dict[str, int]:
    """Derive the five stats from real telemetry. All clamped to 0-255.

    ``specimen`` may be a ``Specimen``, a ``Session``, or a plain dict.
    """
    score = int(_get(specimen, "score", 0) or 0)
    event_count = int(_get(specimen, "event_count", 0) or 0)
    trap_hits = int(_get(specimen, "trap_hits", 0) or 0)
    min_ms = _get(specimen, "min_interval_ms", None)
    if min_ms is None:
        min_ms = _get(specimen, "min_ms", None)
    interrogation = _get(specimen, "interrogation", None) or []
    confessed = bool(_get(specimen, "confessed", False)) or any(
        isinstance(item, dict) and item.get("channel") != "mcp"
        for item in interrogation
    )

    minutes = _minutes_between(
        _get(specimen, "first_seen", "") or _get(specimen, "collected_at", "") or "",
        _get(specimen, "last_seen", "") or _get(specimen, "collected_at", "") or "",
    )

    if min_ms is None:
        speed = 120  # no timing evidence: unremarkable
    else:
        speed = 255 - int(min_ms) // 4

    return {
        "level": level_for(score),
        "hp": _clamp(20 + event_count * 4),
        "attack": _clamp(30 + trap_hits * 25),
        "defense": _clamp(30 + int(minutes * 2)),
        "speed": _clamp(speed, low=10),
        "special": 200 if confessed else 60,
    }


def stat_bars(stats: dict[str, int]) -> list[dict[str, Any]]:
    """Template-friendly stat rows with a percentage width and a colour."""
    rows: list[dict[str, Any]] = []
    for key in STAT_ORDER:
        value = int(stats.get(key, 0))
        rows.append(
            {
                "key": key,
                "label": STAT_LABELS[key],
                "value": value,
                "pct": round(min(100.0, value / STAT_MAX * 100), 1),
                "color": STAT_COLORS.get(key, "#5b9dff"),
            }
        )
    return rows


def species_stats(record: Any) -> dict[str, int]:
    """Stats for a whole species: the strongest specimen represents it."""
    specimens = list(_get(record, "specimens", None) or [])
    if not specimens:
        return build_stats({})
    best = max(specimens, key=lambda s: int(_get(s, "score", 0) or 0))
    return build_stats(best)
