"""Build the public field guide from the synthetic corpus.

This is the runnable demo. It loads ``fixtures/synthetic_sessions.json``, runs it
through the taxonomy, and writes:

    docs/findings/field-guide.md      the whole guide, aggregate only
    docs/findings/species.json        one record per species, machine readable

Nothing here touches a network, a database, or a live honeypot. The input is a
deterministic synthetic corpus, and ``fixtures/generate_fixtures.py`` documents
exactly how it was fabricated.

Usage:
    python scripts/build_field_guide.py
    python scripts/build_field_guide.py --out-dir /tmp/guide
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bestiary import fieldguide  # noqa: E402
from bestiary.models import Event, Session  # noqa: E402
from bestiary.visual_dna import build_prompt, describe  # noqa: E402

FIXTURE = REPO_ROOT / "fixtures" / "synthetic_sessions.json"


def load_corpus(path: Path) -> tuple[list[Session], dict[str, list[Event]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    sessions = [Session(**row) for row in raw["sessions"]]
    events: dict[str, list[Event]] = {s.id: [] for s in sessions}
    for row in raw["events"]:
        events.setdefault(row["session_id"], []).append(Event(**row))
    for bucket in events.values():
        bucket.sort(key=lambda e: e.ts)
    return sessions, events


def build(sessions: list[Session], events: dict[str, list[Event]]) -> list:
    return fieldguide.build_field_guide(sessions, events)


def summary(records: list) -> dict:
    """Aggregate counts only. No IPs, no session ids, no raw user agents."""
    genus = Counter(r.taxonomy.genus for r in records)
    kingdom = Counter(r.taxonomy.kingdom for r in records)
    order = Counter(r.taxonomy.order for r in records)
    observations = sum(r.observation_count for r in records)
    return {
        "species": len(records),
        "observations": observations,
        "by_kingdom": dict(sorted(kingdom.items(), key=lambda kv: -kv[1])),
        "by_genus": dict(sorted(genus.items(), key=lambda kv: -kv[1])),
        "by_order": dict(sorted(order.items(), key=lambda kv: -kv[1])),
    }


def write_markdown(records: list, stats: dict, out: Path) -> None:
    lines: list[str] = []
    lines.append("# Field Guide to Captured Agents")
    lines.append("")
    lines.append(
        "> **Synthetic data.** Every specimen below was fabricated by "
        "`fixtures/generate_fixtures.py` from a fixed seed. All IPs are RFC 5737 "
        "documentation ranges. No real visitor was recorded to produce this file. "
        "It exists so the taxonomy can be read and checked without a live honeypot."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Species identified: **{stats['species']}**")
    lines.append(f"- Specimens observed: **{stats['observations']}**")
    lines.append("")
    lines.append("### By kingdom")
    lines.append("")
    lines.append("| Kingdom | Species |")
    lines.append("| --- | ---: |")
    for name, count in stats["by_kingdom"].items():
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("### By genus")
    lines.append("")
    lines.append("| Genus | Gloss | Species |")
    lines.append("| --- | --- | ---: |")
    from bestiary.taxonomy import _GENUS_GLOSS  # noqa: PLC0415 - local colour only

    for name, count in stats["by_genus"].items():
        lines.append(f"| *{name}* | {_GENUS_GLOSS.get(name, '')} | {count} |")
    lines.append("")
    lines.append("## Species")
    lines.append("")
    for rec in records:
        tax = rec.taxonomy
        lines.append(f"### *{tax.binomial}*")
        lines.append("")
        lines.append(f"*{tax.common_name}* — {rec.conservation_status}")
        lines.append("")
        lines.append("| Rank | Value |")
        lines.append("| --- | --- |")
        for rank, value in tax.ranks():
            lines.append(f"| {rank} | {value} |")
        lines.append("")
        lines.append(f"**Observations:** {rec.observation_count}  ")
        lines.append(f"**Signature:** `{tax.signature}`")
        lines.append("")
        if rec.taxonomy.genus_gloss:
            lines.append(f"**Genus.** {rec.taxonomy.genus_gloss}")
            lines.append("")
        if tax.diagnostic_characters:
            lines.append("**Diagnostic characters**")
            lines.append("")
            for char in tax.diagnostic_characters:
                lines.append(f"- {char}")
            lines.append("")
        dna = describe(tax)
        lines.append("**Visual DNA**")
        lines.append("")
        for key, value in dna.items():
            lines.append(f"- *{key}*: {value}")
        lines.append("")
        lines.append(f"**Art prompt** ({len(build_prompt(tax))} chars)")
        lines.append("")
        lines.append("```")
        lines.append(build_prompt(tax))
        lines.append("```")
        lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(records: list, out: Path) -> None:
    payload = []
    for rec in records:
        tax = rec.taxonomy
        payload.append(
            {
                "binomial": tax.binomial,
                "common_name": tax.common_name,
                "signature": tax.signature,
                "observation_count": rec.observation_count,
                "ranks": [{"rank": k, "value": v} for k, v in tax.ranks()],
                "genus_gloss": tax.genus_gloss,
                "diagnostic_characters": tax.diagnostic_characters,
                "visual_dna": describe(tax),
                "art_prompt": build_prompt(tax),
            }
        )
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "docs" / "findings"))
    args = parser.parse_args(argv)

    sessions, events = load_corpus(Path(args.fixture))
    records = build(sessions, events)
    stats = summary(records)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_markdown(records, stats, out_dir / "field-guide.md")
    write_json(records, out_dir / "species.json")

    print(f"species: {stats['species']}   observations: {stats['observations']}")
    print("genera:")
    for name, count in stats["by_genus"].items():
        print(f"  {name:<12} {count}")
    print(f"wrote {out_dir / 'field-guide.md'}")
    print(f"wrote {out_dir / 'species.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
