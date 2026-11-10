"""Generate species portraits — dry by default, on purpose.

Portrait generation costs real money per image, so this script does the honest
thing: it prints the exact prompt it *would* send and spends nothing unless you
pass ``--live``.

    python scripts/generate_art.py                 # show the prompts
    python scripts/generate_art.py --species Sedens
    python scripts/generate_art.py --live          # actually call the API

``--live`` requires ``OPENROUTER_API_KEY`` in the environment and writes PNGs to
``data/art/<signature>.png``. Nothing is written anywhere else.

Images are cached by species signature, so re-running is free: a signature whose
PNG already exists on disk is skipped and reported as cached.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bestiary import art  # noqa: E402
from bestiary.models import Event, Session  # noqa: E402
from bestiary.taxonomy import Taxonomy, classify_species  # noqa: E402
from bestiary.visual_dna import PROMPT_VERSION, build_prompt  # noqa: E402
import bestiary.fieldguide as fieldguide  # noqa: E402

FIXTURE = REPO_ROOT / "fixtures" / "synthetic_sessions.json"


def load_species(fixture: Path) -> list[tuple[Taxonomy, int]]:
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    sessions = [Session(**row) for row in raw["sessions"]]
    events: dict[str, list[Event]] = {s.id: [] for s in sessions}
    for row in raw["events"]:
        events.setdefault(row["session_id"], []).append(Event(**row))
    records = fieldguide.build_field_guide(sessions, events)
    return [(r.taxonomy, r.observation_count) for r in records]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "art"))
    parser.add_argument(
        "--species",
        default="",
        help="Only this binomial genus (e.g. Sedens). Default: every species.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually call the image API and spend money. Off by default.",
    )
    args = parser.parse_args(argv)

    species = load_species(Path(args.fixture))
    if args.species:
        species = [(t, n) for t, n in species if t.genus.lower() == args.species.lower()]
        if not species:
            print(f"no species matched --species {args.species!r}", file=sys.stderr)
            return 2

    out_dir = Path(args.out)
    mode = "LIVE" if args.live else "DRY RUN"
    print(f"{mode} — {len(species)} species, prompt version {PROMPT_VERSION}")
    print(f"output directory: {out_dir}")
    print()

    cached = skipped = generated = failed = 0
    provider = None
    if args.live:
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            print("OPENROUTER_API_KEY is not set; refusing to run --live", file=sys.stderr)
            return 2
        model = os.environ.get("HONEYPOT_ART_MODEL", "google/gemini-2.5-flash-image")
        provider = art.OpenRouterProvider(api_key=key, model=model)
        print(f"provider: {model}")
        print()

    for tax, observations in species:
        target = out_dir / f"{tax.signature}.png"
        if target.exists():
            cached += 1
            print(f"  cached    {tax.binomial} ({tax.signature})")
            continue
        if not args.live:
            skipped += 1
            prompt = build_prompt(tax)
            print(f"  would run {tax.binomial} ({tax.signature}) — {len(prompt)} chars, obs={observations}")
            continue
        prompt = build_prompt(tax)
        try:
            data = provider.generate(prompt)
        except Exception as exc:  # noqa: BLE001 - report, do not crash the run
            failed += 1
            print(f"  FAILED    {tax.binomial}: {exc}")
            continue
        if not data:
            failed += 1
            print(f"  empty     {tax.binomial}: provider returned nothing")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        generated += 1
        print(f"  generated {tax.binomial} ({tax.signature}) — {len(data)} bytes")

    print()
    print(f"generated={generated} cached={cached} skipped={skipped} failed={failed}")
    if not args.live:
        print()
        print("This was a dry run. Nothing was sent and nothing was spent.")
        print("Re-run with --live and OPENROUTER_API_KEY set to generate for real.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
