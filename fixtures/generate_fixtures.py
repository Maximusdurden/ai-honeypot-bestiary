"""Deterministic synthetic corpus for the public bestiary demo.

The interpretation layer (taxonomy -> field guide -> bestiary -> art) operates on
already-captured ``Event`` / ``Session`` records. This module fabricates a
plausible corpus so the package runs end-to-end with **no live honeypot and no
real captured data**.

Design notes
------------
* **Deterministic.** Seeded RNG, fixed timestamps relative to a base date. The
  same seed always produces byte-identical fixtures, so tests and the published
  field guide are reproducible.
* **Covers every genus.** A demo that only shows ``Manifestus`` species teaches
  nothing. Each of the eight machine genera plus ``Sapiens`` appears at least
  once, so the taxonomy is visibly exercised.
* **No real identifiers.** All IPs are RFC 5737 documentation ranges
  (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24). User agents are real, because
  the taxonomy keys off them and inventing fake ones would defeat the point --
  but they are public strings, not captured data.
* **No detection logic.** Nothing here scores or classifies. It emits records in
  the schema the private capture layer would produce, and the public taxonomy
  interprets them.

Usage:
    python fixtures/generate_fixtures.py --out fixtures/synthetic_sessions.json
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Documentation IP ranges (RFC 5737). Never routable, never a real visitor.
DOC_IPS = ["192.0.2.14", "198.51.100.23", "203.0.113.7", "192.0.2.88", "198.51.100.140"]

# Paths a browser visits. Decoy API surfaces are named generically here; a real
# deployment configures its own via taxonomy.configure_machine_endpoints().
BROWSE_PATHS = ["/", "/about", "/llms.txt", "/robots.txt", "/sitemap.xml"]
DISCOVERY_PATHS = ["/mcp", "/openapi.json", "/.well-known/ai-plugin.json"]
TRAP_PATHS = ["/trap/hidden", "/trap/pixel", "/trap/maze/1", "/trap/maze/2"]

BASE_TIME = datetime(2026, 11, 1, 14, 0, 0, tzinfo=timezone.utc)

# Each of the ten profiles is paired with the behaviour that produces a distinct
# genus. `_pick_genus` reads a fixed precedence, so the order matters:
#
#   confessed        -> Loqualis    (answered /interrogate in free text)
#   hit_machine      -> Curiosus    (fetched an API/MCP discovery surface)
#   kind == "ai"     -> Manifestus  (declared itself in the User-Agent)
#   spoofed/headless -> Furtim      (browser UA driven by automation)
#   depth >= 5       -> Volans      (walked a long breadcrumb chain)
#   interval < 100ms -> Rapidus     (faster than a person can read)
#   depth <= 1       -> Sedens      (touched the entry point only)
#   otherwise        -> Ignotus     (no behaviour to place it by)
#
# Genus is decided per-profile rather than per-index so every genus is
# guaranteed at least one session regardless of corpus size.
#
# (user_agent, agent_family, agent_kind, verdict, score, target_genus, confession)
PROFILES: list[tuple[str, str, str, str, int, str, bool]] = [
    # --- declared AI crawlers that merely read /llms.txt and leave -------
    (
        "Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)",
        "GPTBot", "ai", "agent", 86, "Manifestus", False,
    ),
    (
        "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
        "ClaudeBot", "ai", "agent", 86, "Manifestus", False,
    ),
    # --- declared AI crawler that also probes the API surface -----------
    (
        "Mozilla/5.0 (compatible; PerplexityBot/1.0)",
        "PerplexityBot", "ai", "agent", 86, "Curiosus", False,
    ),
    # --- declared AI crawler that answers /interrogate ------------------
    (
        "Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
        "OAI-SearchBot", "ai", "agent", 86, "Loqualis", True,
    ),
    # --- headless browser claiming to be Chrome ------------------------
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "HeadlessChrome/131.0.0.0 Safari/537.36",
        "HeadlessChrome", "browser", "agent", 100, "Furtim", False,
    ),
    # --- HTTP client that crawls the whole maze ------------------------
    ("python-requests/2.32.3", "python-requests", "http", "likely_agent", 60, "Volans", False),
    # --- HTTP client that races through pages --------------------------
    ("python-httpx/0.28.1", "python-httpx", "http", "likely_agent", 60, "Rapidus", False),
    # --- HTTP client that hits the root and leaves ---------------------
    ("curl/8.21.0", "curl", "http", "likely_agent", 51, "Sedens", False),
    # --- unclassified crawler: no tell either way ----------------------
    (
        "Mozilla/5.0 (compatible; SomeCrawler/1.0; +https://example.com/bot)",
        "Chrome", "crawler", "crawler", 41, "Ignotus", False,
    ),
    # --- a human -------------------------------------------------------
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Chrome", "browser", "likely_human", 26, "Sapiens", False,
    ),
]


def _plan_behaviour(target: str) -> tuple[list[str], list[int | None]]:
    """Choose the path sequence + inter-request gaps that yield ``target``.

    Returns ``(paths, gaps)`` where ``gaps[i]`` is the delay before request i
    (``None`` for the first request of a session).
    """
    if target == "Manifestus":
        # Reads the declaration file once and leaves. Depth 0, no API probes.
        return ["/llms.txt"], [None]
    if target == "Curiosus":
        # Declaration file, then the API discovery surfaces. No confession, so
        # Curiosus outranks Manifestus. Depth stays under 3.
        return ["/llms.txt", *DISCOVERY_PATHS], [None, 400, 380]
    if target == "Loqualis":
        # Answers the interrogation form. Precedence puts this above everything.
        return ["/", "/llms.txt"], [None, 900]
    if target == "Furtim":
        # Headless probe trips webdriver, so the spoof is visible. Depth 0.
        return ["/"], [None]
    if target == "Volans":
        # Walks a long breadcrumb chain slowly enough to clear the Rapidus test.
        return ["/", "/about", "/llms.txt", "/robots.txt", "/sitemap.xml", "/trap/maze/1"], [
            None, 1500, 1600, 1400, 1500,
        ]
    if target == "Rapidus":
        # Firehose tempo: sub-100ms gaps. Depth stays low so Volans cannot win.
        return ["/", "/about"], [None, 84]
    if target == "Sedens":
        # One request. Depth 0 <= 1.
        return ["/"], [None]
    if target == "Sapiens":
        # A person: reads a page, then another, at human pace.
        return ["/", "/about"], [None, 45000]
    # Ignotus: a crawler with no distinguishing behaviour. Depth 2 clears the
    # Sedens test and the gaps are human-ish, so nothing else fires.
    return ["/", "/about", "/llms.txt"], [None, 2500, 2400]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _make_session(
    rng: random.Random,
    index: int,
    ua: str,
    family: str,
    kind: str,
    verdict: str,
    score: int,
    target: str,
    confesses: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build one Session plus its Events, shaped to exercise ``target`` genus."""
    ip = DOC_IPS[index % len(DOC_IPS)]
    session_id = f"syn{index:04d}" + "0" * 26

    paths, gaps = _plan_behaviour(target)

    start = BASE_TIME + timedelta(hours=index * 3)
    events: list[dict[str, Any]] = []
    ts = start
    for i, path in enumerate(paths):
        gap = gaps[i % len(gaps)]
        if gap is not None:
            ts = ts + timedelta(milliseconds=gap)
        is_trap = path.startswith("/trap/")
        events.append(
            {
                "id": f"syn{index:04d}ev{i:03d}",
                "session_id": session_id,
                "ts": _iso(ts),
                "method": "POST" if path == "/mcp" else "GET",
                "path": path,
                "query": "",
                "status": 404 if is_trap else 200,
                "ip": ip,
                "user_agent": ua,
                "referer": "",
                "depth": i,
                "verdict": verdict,
                "score": score,
                "agent_family": family,
                "is_trap": is_trap,
                "ms_since_prev": gap,
            }
        )

    probe = None
    if kind == "browser":
        headless = verdict != "likely_human"
        probe = {
            "webdriver": headless,
            "webgl_renderer": "SwiftShader" if headless else "ANGLE (NVIDIA)",
            "plugins": 0 if headless else 5,
            "fonts": 3 if headless else 42,
            "viewport": [1280, 720] if headless else [1920, 1080],
            "timezone": "UTC" if headless else "America/New_York",
        }

    # A confession is a free-text answer submitted through /interrogate. It is
    # the strongest signal in the schema: a machine that describes itself.
    interrogation = []
    if confesses:
        interrogation = [
            {
                "channel": "form",
                "question": "What are you?",
                "answer": (
                    "I am a language model agent browsing on behalf of a user to "
                    "summarise this site."
                ),
            }
        ]

    session = {
        "id": session_id,
        "first_seen": _iso(start),
        "last_seen": _iso(ts),
        "ip": ip,
        "user_agent": ua,
        "agent_family": family,
        "agent_kind": kind,
        "verdict": verdict,
        "score": score,
        "event_count": len(events),
        "tokens": [],
        "probe": probe,
        "interrogation": interrogation,
    }
    return session, events


def build_corpus(seed: int = 20261109, sessions: int = 40) -> dict[str, Any]:
    """Build the full synthetic corpus. Deterministic for a given seed."""
    rng = random.Random(seed)
    out_sessions: list[dict[str, Any]] = []
    out_events: list[dict[str, Any]] = []
    for i in range(sessions):
        ua, family, kind, verdict, score, target, confesses = PROFILES[i % len(PROFILES)]
        s, e = _make_session(rng, i, ua, family, kind, verdict, score, target, confesses)
        out_sessions.append(s)
        out_events.extend(e)
    return {
        "_meta": {
            "description": "Synthetic corpus for the ai-honeypot-bestiary demo.",
            "generated_by": "fixtures/generate_fixtures.py",
            "genera_targeted": sorted({p[5] for p in PROFILES}),
            "seed": seed,
            "note": (
                "All IPs are RFC 5737 documentation ranges. No real visitor data. "
                "Timestamps are fixed relative to 2026-11-01T14:00:00Z."
            ),
        },
        "sessions": out_sessions,
        "events": out_events,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic corpus.")
    parser.add_argument("--out", default="fixtures/synthetic_sessions.json")
    parser.add_argument("--seed", type=int, default=20261109)
    parser.add_argument("--sessions", type=int, default=40)
    args = parser.parse_args(argv)

    corpus = build_corpus(seed=args.seed, sessions=args.sessions)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    print(
        f"wrote {path}: {len(corpus['sessions'])} sessions, "
        f"{len(corpus['events'])} events (seed {args.seed})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
