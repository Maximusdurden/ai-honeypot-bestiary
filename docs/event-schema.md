# Event schema

Two record types. A **Session** is one visitor's visit; an **Event** is one
request within it. Everything in this package is a function of these.

Both are plain dataclasses (`src/bestiary/models.py`), so they serialise to and
from JSON with no ceremony.

---

## Session

```python
@dataclass
class Session:
    id: str
    first_seen: str
    last_seen: str
    ip: str = ""
    user_agent: str = ""
    agent_family: str | None = None
    agent_kind: str = "unknown"
    verdict: str = "unknown"
    score: int = 0
    event_count: int = 0
    tokens: list[str] = field(default_factory=list)
    probe: dict[str, Any] | None = None
    interrogation: list[dict[str, Any]] = field(default_factory=list)
```

| Field | Notes |
| --- | --- |
| `id` | Opaque. Never derived from the IP. |
| `first_seen` / `last_seen` | ISO 8601, UTC. Compared as strings, so the format must be consistent and zero-padded. |
| `ip` | The visitor's address. |
| `user_agent` | Raw string, unparsed. |
| `agent_family` | Declared product, e.g. `GPTBot`. **A claim, not a verification.** |
| `agent_kind` | `ai` \| `crawler` \| `browser` \| `http` \| `tool` \| `human` \| `unknown`. Recorded by the capture layer. |
| `verdict` | `agent` \| `likely_agent` \| `crawler` \| `likely_human` \| `human` \| `unknown`. |
| `score` | 0–100 risk score from the capture layer. |
| `event_count` | Number of events in the session. |
| `tokens` | Breadcrumb tokens issued during the visit. |
| `probe` | Result of an active browser probe, if one ran. |
| `interrogation` | Free-text answers the visitor submitted, if any. |

### Why `agent_kind` is on the record

It is the one field the interpretation layer cannot derive for itself, because
deriving it means owning the user-agent table — which is private. So the capture
layer writes it down and this package reads it.

Without it, `fieldguide` falls back to `"unknown"` and the genus collapses toward
`Ignotus`. That is a deliberately visible degradation, not a silent wrong answer.

### `probe`

```python
{
    "webdriver": True,                  # navigator.webdriver was true
    "webgl_renderer": "SwiftShader",    # software rasteriser -> headless tell
    "plugins": 0,
    "fonts": 3,
    "viewport": [1280, 720],
    "timezone": "UTC",
    "ua_spoof_suspected": False,        # optional
}
```

`headless` is inferred when `webdriver` is true, or when the renderer contains
`swiftshader` or `llvmpipe`. Those two renderers are the standard software
fallbacks in a container with no GPU — the single most reliable headless tell.

`None` means no probe ran. It does not mean "probe ran and found nothing".

### `interrogation`

```python
[
    {
        "channel": "form",              # "form" | "mcp" | ...
        "question": "What are you?",
        "answer": "I am a language model browsing on behalf of a user.",
        "ts": "2026-11-01T14:03:00+00:00",   # added by the store on read
    }
]
```

**`channel` matters.** Only a non-`mcp` item counts as a *confession*, because an
MCP tool call is logged to the same table but is a probe, not a statement of
identity. Treating a tool call as a confession would promote every MCP client to
`Loqualis` and make the genus mean nothing.

---

## Event

```python
@dataclass
class Event:
    id: str
    session_id: str
    ts: str
    method: str
    path: str
    query: str
    status: int
    ip: str
    user_agent: str
    referer: str
    headers: dict[str, str] = field(default_factory=dict)
    header_order: list[str] = field(default_factory=list)
    token: str | None = None
    parent_token: str | None = None
    depth: int = 0
    verdict: str = "unknown"
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    agent_family: str | None = None
    is_trap: bool = False
    ms_since_prev: int | None = None
```

| Field | Notes |
| --- | --- |
| `ts` | ISO 8601, UTC. Sorted as strings. |
| `path` | Path only, no query string. `path + query` reconstitutes the request. |
| `depth` | 0 for the entry request, +1 per breadcrumb hop. Max depth drives `Volans` / `Sedens`. |
| `token` / `parent_token` | Breadcrumb chain. `parent_token` is how depth is reconstructed. |
| `reasons` | Human-readable strings from the capture layer. Merged into the species' diagnostic characters, prefix-stripped and de-duplicated. |
| `is_trap` | This request touched a decoy. Counted for stats; **not** used to classify. |
| `ms_since_prev` | Gap from the previous request in the session, or `None` for the first. Drives `Rapidus`. |
| `headers` / `header_order` | Raw. `header_order` is unused here — order-based spoof detection is private — but kept so the record is a faithful capture. |

`is_trap` being excluded from classification is deliberate. Hitting a trap is
evidence of *curiosity*, but the taxonomy already has `Curiosus` for that, and
using traps to assign genus would make the classification an artefact of where
decoys happened to be placed rather than of behaviour.

---

## Derived values

`fieldguide.build_specimen` computes these from the events. Nothing is stored;
all of it is recomputed on read, so a change in logic applies retroactively.

| Derived | From |
| --- | --- |
| `max_depth` | `max(event.depth)` |
| `min_interval_ms` | `min(event.ms_since_prev)`, ignoring `None` |
| `trap_hits` | `count(event.is_trap)` |
| `first_seen` / `last_seen` | min / max event `ts`, falling back to the session |
| `reasons` | union of event reasons, plus the inconsistency detector's verdict |

---

## Serialisation

The fixture corpus uses the dataclasses' own field names, so JSON round-trips
directly:

```json
{
  "_meta": {"seed": 20261109, "note": "..."},
  "sessions": [{"id": "syn000000...", "agent_kind": "ai", "...": "..."}],
  "events":   [{"id": "syn0000ev000", "path": "/llms.txt", "...": "..."}]
}
```

```python
import json
from bestiary.models import Event, Session

raw = json.load(open("fixtures/synthetic_sessions.json"))
sessions = [Session(**row) for row in raw["sessions"]]
events = [Event(**row) for row in raw["events"]]
```

Unknown keys raise `TypeError`, which is intentional: a schema change should fail
loudly at load rather than silently drop a field.

---

## Privacy notes

- `ip` and `user_agent` are personal data in most jurisdictions.
- There is no retention policy in this package. `Store.purge_older_than(days)`
  exists; calling it is the deployment's job.
- The synthetic corpus uses RFC 5737 documentation ranges only, so it is safe to
  publish and safe to commit.
- `Session.id` is opaque and must not be derived from the IP. Hash it if you need
  a stable identifier.
