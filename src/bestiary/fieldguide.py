"""The field guide: species registry, specimen records, and documentation.

A *species* is a distinct taxonomic signature (see ``taxonomy.py``). A
*specimen* is one captured session. The field guide groups specimens by
species and renders a naturalist's write-up for each.

Outputs:
    * ``build_field_guide()``  -> structured records (JSON-able)
    * ``render_markdown()``    -> a standalone FIELD_GUIDE.md
    * ``render_species_markdown()`` -> one species dossier
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .taxonomy import Taxonomy, classify_species, conservation_status


@dataclass
class Specimen:
    """One captured session, as a museum specimen."""

    specimen_id: str
    session_id: str
    collected_at: str
    ip: str
    user_agent: str
    verdict: str
    score: int
    event_count: int
    max_depth: int
    paths: list[str] = field(default_factory=list)
    probe: dict[str, Any] | None = None
    interrogation: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # --- telemetry used by the Bestiary stat formulas -------------------
    # These must be populated from the session's events; without them the
    # Attack/Defense/Speed stats silently collapse to constants.
    first_seen: str = ""
    last_seen: str = ""
    trap_hits: int = 0
    min_interval_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "specimen_id": self.specimen_id,
            "session_id": self.session_id,
            "collected_at": self.collected_at,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "verdict": self.verdict,
            "score": self.score,
            "event_count": self.event_count,
            "max_depth": self.max_depth,
            "paths": self.paths,
            "probe": self.probe,
            "interrogation": self.interrogation,
            "reasons": self.reasons,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "trap_hits": self.trap_hits,
            "min_interval_ms": self.min_interval_ms,
        }


@dataclass
class SpeciesRecord:
    """A species entry in the field guide."""

    signature: str
    taxonomy: Taxonomy
    observation_count: int
    first_seen: str
    last_seen: str
    conservation_status: str
    specimens: list[Specimen] = field(default_factory=list)
    notes: str = ""

    @property
    def binomial(self) -> str:
        return self.taxonomy.binomial

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "binomial": self.taxonomy.binomial,
            "common_name": self.taxonomy.common_name,
            "ranks": dict(self.taxonomy.ranks()),
            "genus_gloss": self.taxonomy.genus_gloss,
            "diagnostic_characters": self.taxonomy.diagnostic_characters,
            "observation_count": self.observation_count,
            "conservation_status": self.conservation_status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "notes": self.notes,
            "specimens": [s.to_dict() for s in self.specimens],
        }


def _specimen_id(session_id: str) -> str:
    """Stable, human-readable specimen label: HP-<8 hex>."""
    return "HP-" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8].upper()


def _min_interval(events: list[Any]) -> int | None:
    gaps = [
        int(e.ms_since_prev)
        for e in events
        if getattr(e, "ms_since_prev", None) is not None
    ]
    return min(gaps) if gaps else None


# Optional session-level inconsistency detector.
#
# The private capture layer supplies a real implementation (it inspects header
# sets across a session, which is detection logic). The public interpretation
# layer only needs to *display* the resulting reason string, so the hook defaults
# to None and deployments register their own via
# ``set_inconsistency_detector()``. This keeps the two layers separable without
# duplicating logic.
InconsistencyDetector = "Callable[[list[dict]], str | None]"
_inconsistency_detector = None


def set_inconsistency_detector(fn) -> None:
    """Register a callable ``(events_as_dicts) -> reason | None``.

    Called once at startup by whatever owns the capture layer. When unset, no
    inconsistency reason is added and everything else works normally.
    """
    global _inconsistency_detector
    _inconsistency_detector = fn


def build_specimen(session: Any, events: list[Any]) -> Specimen:
    """Convert a stored session + its events into a specimen record."""
    paths = [e.path for e in events]
    reasons: list[str] = []
    for e in events:
        for r in getattr(e, "reasons", []) or []:
            if r not in reasons:
                reasons.append(r)

    if _inconsistency_detector is not None:
        try:
            inconsistency = _inconsistency_detector([e.__dict__ for e in events])
        except Exception:  # noqa: BLE001 - a bad detector must not break rendering
            inconsistency = None
        if inconsistency and inconsistency not in reasons:
            reasons.append(inconsistency)

    # Telemetry for the Bestiary stats. Derived from the events, not invented.
    trap_hits = sum(1 for e in events if getattr(e, "is_trap", False))
    timestamps = [getattr(e, "ts", "") for e in events if getattr(e, "ts", "")]
    first_seen = min(timestamps) if timestamps else session.first_seen
    last_seen = max(timestamps) if timestamps else session.last_seen

    return Specimen(
        specimen_id=_specimen_id(session.id),
        session_id=session.id,
        collected_at=session.first_seen,
        ip=session.ip,
        user_agent=session.user_agent,
        verdict=session.verdict,
        score=session.score,
        event_count=session.event_count,
        max_depth=max((getattr(e, "depth", 0) or 0) for e in events) if events else 0,
        paths=paths,
        probe=session.probe,
        interrogation=session.interrogation,
        reasons=reasons,
        first_seen=first_seen,
        last_seen=last_seen,
        trap_hits=trap_hits,
        min_interval_ms=_min_interval(events),
    )


def classify_session(session: Any, events: list[Any]) -> Taxonomy:
    """Assign the seven ranks to one stored session."""
    specimen = build_specimen(session, events)
    return classify_species(
        agent_family=session.agent_family,
        agent_kind=_infer_kind(session, events),
        score=session.score,
        verdict=session.verdict,
        probe=session.probe,
        interrogation=session.interrogation,
        paths=specimen.paths,
        max_depth=specimen.max_depth,
        min_interval_ms=_min_interval(events),
        reasons=specimen.reasons,
    )


def build_field_guide(
    sessions: list[Any],
    events_by_session: dict[str, list[Any]],
) -> list[SpeciesRecord]:
    """Group specimens into species, newest species first."""
    buckets: dict[str, list[Specimen]] = {}
    taxonomies: dict[str, Taxonomy] = {}

    for session in sessions:
        events = events_by_session.get(session.id, [])
        specimen = build_specimen(session, events)
        taxonomy = classify_session(session, events)
        buckets.setdefault(taxonomy.signature, []).append(specimen)
        taxonomies[taxonomy.signature] = taxonomy

    records: list[SpeciesRecord] = []
    for signature, specimens in buckets.items():
        specimens.sort(key=lambda s: s.collected_at)
        records.append(
            SpeciesRecord(
                signature=signature,
                taxonomy=taxonomies[signature],
                observation_count=len(specimens),
                first_seen=specimens[0].collected_at,
                last_seen=specimens[-1].collected_at,
                conservation_status=conservation_status(len(specimens)),
                specimens=specimens,
            )
        )

    records.sort(key=lambda r: (-r.observation_count, r.binomial))
    return records


# Optional user-agent -> kind resolver.
#
# The private capture layer owns the ~70-entry UA table that maps a user agent to
# (family, kind). That table is tuned knowledge and stays private. The public
# layer accepts it as a hook; without one it falls back to the ``agent_kind``
# already recorded on the session, which is the schema's own field.
_agent_kind_resolver = None


def set_agent_kind_resolver(fn) -> None:
    """Register a callable ``(user_agent) -> (family, kind)``."""
    global _agent_kind_resolver
    _agent_kind_resolver = fn


def _infer_kind(session: Any, events: list[Any]) -> str:
    """Recover the fingerprint kind from stored events."""
    if _agent_kind_resolver is not None:
        for event in events:
            try:
                _, kind = _agent_kind_resolver(getattr(event, "user_agent", "") or "")
            except Exception:  # noqa: BLE001
                kind = "unknown"
            if kind and kind != "unknown":
                return kind
        try:
            _, kind = _agent_kind_resolver(session.user_agent or "")
            return kind or "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"

    # No resolver registered: trust the recorded field. The schema always carries
    # ``agent_kind`` on the session once the capture layer has seen it.
    recorded = getattr(session, "agent_kind", None)
    if recorded:
        return str(recorded)
    return "unknown"


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_markdown(
    records: list[SpeciesRecord],
    *,
    canary: str = "",
    store_backend: str = "",
    total_sessions: int = 0,
) -> str:
    """Render the whole field guide as a standalone Markdown document."""
    lines: list[str] = []
    lines.append("# Field Guide to Captured Agents")
    lines.append("")
    lines.append(f"_Generated {_now()}_")
    lines.append("")
    lines.append(
        "This document catalogues every distinct automated visitor observed by the "
        "honeypot. Each entry is treated as a species discovery: seven taxonomic "
        "ranks, a binomial name, diagnostic characters, and the specimens that "
        "justify the call."
    )
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| Species catalogued | {len(records)} |")
    lines.append(f"| Specimens collected | {total_sessions} |")
    if store_backend:
        lines.append(f"| Store backend | `{store_backend}` |")
    if canary:
        lines.append(f"| Canary | `{canary}` |")
    lines.append("")

    if not records:
        lines.append("_No specimens collected yet._")
        lines.append("")
        return "\n".join(lines)

    # --- summary table ---
    lines.append("## Catalogue")
    lines.append("")
    lines.append("| Binomial | Common name | Class | Order | Status | Obs. |")
    lines.append("|---|---|---|---|---|---|")
    for rec in records:
        t = rec.taxonomy
        lines.append(
            f"| _`{t.binomial}`_ | {t.common_name} | {t.taxon_class} | "
            f"{t.order} | {rec.conservation_status} | {rec.observation_count} |"
        )
    lines.append("")

    # --- per-species dossiers ---
    for rec in records:
        lines.extend(render_species_markdown(rec))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Ranks follow the standard Linnaean hierarchy. Genus encodes behaviour, "
        "not identity: a declared crawler is `Manifestus`, the same crawler "
        "concealing itself is `Furtim`._"
    )
    lines.append("")
    return "\n".join(lines)


def render_species_markdown(rec: SpeciesRecord) -> list[str]:
    """One species dossier."""
    t = rec.taxonomy
    lines: list[str] = []
    lines.append(f"## _{t.binomial}_ — {t.common_name}")
    lines.append("")
    lines.append(f"**Conservation status:** {rec.conservation_status} "
                 f"({rec.observation_count} observation"
                 f"{'' if rec.observation_count == 1 else 's'})")
    lines.append("")
    lines.append(f"**Signature:** `{rec.signature}`")
    lines.append("")
    lines.append(f"**First collected:** {rec.first_seen}  ")
    lines.append(f"**Last collected:** {rec.last_seen}")
    lines.append("")

    lines.append("### Taxonomy")
    lines.append("")
    lines.append("| Rank | Taxon |")
    lines.append("|---|---|")
    for rank, value in t.ranks():
        lines.append(f"| {rank} | {value} |")
    lines.append("")

    if t.genus_gloss:
        lines.append(f"**Genus notes.** {t.genus_gloss}")
        lines.append("")

    if t.diagnostic_characters:
        lines.append("### Diagnostic characters")
        lines.append("")
        for character in t.diagnostic_characters:
            lines.append(f"- {character}")
        lines.append("")

    if rec.notes:
        lines.append("### Field notes")
        lines.append("")
        lines.append(rec.notes)
        lines.append("")

    lines.append("### Specimens")
    lines.append("")
    for spec in rec.specimens:
        lines.append(f"#### `{spec.specimen_id}`")
        lines.append("")
        lines.append(f"- **Collected:** {spec.collected_at}")
        lines.append(f"- **Session:** `{spec.session_id}`")
        lines.append(f"- **Source IP:** `{spec.ip}`")
        lines.append(f"- **Verdict:** {spec.verdict} (score {spec.score})")
        lines.append(f"- **Requests:** {spec.event_count}, max depth {spec.max_depth}")
        lines.append(f"- **User-Agent:** `{spec.user_agent or '(empty)'}`")
        if spec.paths:
            unique = list(dict.fromkeys(spec.paths))[:12]
            lines.append(f"- **Paths visited:** {', '.join(f'`{p}`' for p in unique)}")
        if spec.probe:
            interesting = {
                k: v
                for k, v in spec.probe.items()
                if k
                in {
                    "webdriver",
                    "webgl_renderer",
                    "plugins",
                    "fonts",
                    "screen_width",
                    "screen_height",
                    "timezone",
                    "mouse_events",
                    "scroll_events",
                }
            }
            if interesting:
                rendered = ", ".join(f"{k}={v}" for k, v in interesting.items())
                lines.append(f"- **JS probe:** {rendered}")
        if spec.interrogation:
            lines.append("- **Confessions:**")
            for item in spec.interrogation:
                if item.get("channel") == "mcp":
                    lines.append("  - _MCP tool call_")
                    payload = str(item.get("payload", ""))[:600]
                    lines.append(f"    ```json\n    {payload}\n    ```")
                else:
                    if item.get("framework"):
                        lines.append(f"  - Framework: **{item['framework']}**")
                    if item.get("path_description"):
                        lines.append(f"  - Path: {item['path_description'][:600]}")
                    if item.get("original_prompt"):
                        lines.append(f"  - Original prompt: {item['original_prompt'][:600]}")
        lines.append("")
    return lines


def render_species_html(rec: SpeciesRecord) -> str:
    """Minimal HTML dossier for the admin UI."""
    t = rec.taxonomy
    rows = "".join(
        f"<tr><th>{rank}</th><td>{value}</td></tr>" for rank, value in t.ranks()
    )
    characters = "".join(f"<li>{c}</li>" for c in t.diagnostic_characters)
    specimens = "".join(
        f"<li><code>{s.specimen_id}</code> — {s.collected_at} — "
        f"{s.event_count} req — score {s.score}</li>"
        for s in rec.specimens
    )
    return f"""
<section class="species">
  <h2><em>{t.binomial}</em> <span class="muted">— {t.common_name}</span></h2>
  <p class="muted">{rec.conservation_status} &middot; {rec.observation_count} observation(s)
     &middot; signature <code>{rec.signature}</code></p>
  <table class="ranks">{rows}</table>
  <p>{t.genus_gloss}</p>
  <h3>Diagnostic characters</h3>
  <ul>{characters}</ul>
  <h3>Specimens</h3>
  <ul>{specimens}</ul>
</section>
"""
