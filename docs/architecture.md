# Architecture

This package reads records. It does not produce them. Everything below follows
from that one boundary.

```
      CAPTURE LAYER  (private)              INTERPRETATION LAYER  (this repo)
 ┌──────────────────────────────┐      ┌──────────────────────────────────────┐
 │  request  ──► score ──► verdict│─────►│  Event / Session records             │
 │  UA table, header order,      │      │    │                                 │
 │  spoof checks, tarpit,        │      │    ├─► taxonomy.classify_species      │
 │  interrogation, canary        │      │    ├─► fieldguide.build_field_guide   │
 └──────────────────────────────┘      │    ├─► bestiary  (aggregate stats)    │
                                        │    └─► visual_dna → art               │
                                        └──────────────────────────────────────┘
                                                     │
                                                     ▼
                                          field guide + species portraits
```

## Why the boundary sits there

The interesting engineering in a honeypot is the *capture* side: deciding what a
request is, spotting a spoof, catching a lie. That knowledge is also the part
that degrades the moment it is published, because the people writing crawlers
read too.

The interpretation side is the opposite. Classification *given* evidence,
grouping, naming, and rendering are genuinely reusable, and publishing them makes
the work legible without teaching anyone how to evade detection.

So the split is drawn at the record schema. This package consumes `Event` and
`Session` and never asks how they were filled in.

## The record schema

```
Session                          Event
├── id                           ├── id
├── first_seen, last_seen        ├── session_id, ts
├── ip                           ├── method, path, query, status
├── user_agent                   ├── ip, user_agent, referer
├── agent_family                 ├── headers, header_order
├── agent_kind   ai|crawler|     ├── token, parent_token, depth
│                browser|http|   ├── verdict, score, reasons
│                tool|human      ├── agent_family
├── verdict, score               ├── is_trap
├── event_count, tokens          └── ms_since_prev
├── probe        {webdriver, webgl_renderer, ...}
└── interrogation [{channel, question, answer}]
```

`agent_kind` is the one field the interpretation layer genuinely cannot derive
for itself, because deriving it means owning the user-agent table. It is recorded
by the capture layer and read here.

## The four hooks

The private pieces are injected rather than vendored:

| Hook | Registers | Without it |
| --- | --- | --- |
| `fieldguide.set_agent_kind_resolver(fn)` | `(user_agent) -> (family, kind)` | falls back to the recorded `agent_kind` |
| `fieldguide.set_inconsistency_detector(fn)` | `(events) -> reason \| None` | no inconsistency reason is added |
| `store_sqlite.set_session_summarizer(fn)` | `(events) -> (score, verdict)` | uses the strongest verdict an event already carried |
| `store_sqlite.set_verdict_thresholds(table)` | `[(score, label)]` | generic bands, used only for filtering |

Each fallback is chosen so the package stays *honest* rather than merely
functional. Without a summarizer it does not invent a session score; it reports
the strongest verdict already present in the data. A reader can always tell the
difference between "the analysis says X" and "the upstream evidence said X".

The hooks are wrapped in `try/except`. A broken detector degrades rendering; it
does not break the site.

## Data flow

1. **Ingest.** Sessions and events are read from a `Store` (`SQLiteStore` ships
   here; the private deployment uses Firestore behind the same interface).
2. **Specimen.** `fieldguide.build_specimen` attaches derived telemetry to one
   session: max depth, trap hits, minimum inter-request interval, first/last seen,
   and reasons collected from its events. Everything is *derived from the events*,
   never invented.
3. **Taxonomy.** `taxonomy.classify_species` assigns seven ranks. The signature is
   `sha256` over the rank tuple, so it is stable across processes and machines.
4. **Grouping.** `build_field_guide` buckets specimens by signature, producing one
   `SpeciesRecord` per species with an observation count and conservation status.
5. **Visual DNA.** `visual_dna.build_for(signature)` draws morphology from the
   digest; `build_prompt` composes the image prompt.
6. **Art.** `art.ensure_art` generates once per signature and caches. A cached
   species never calls the provider again.

## Determinism

Three things have to be stable or the bestiary is incoherent:

- **Signature** — `sha256`, explicitly not `hash()`, which is salted per process.
- **Morphology** — five traits drawn from five different digest bytes, so
  independent and reproducible.
- **Corpus** — fixed seed and fixed base timestamp.

A species captured today must look the same in a year. That is a hard requirement,
not a preference, because the whole appeal is that a specimen is recognisable.

## Storage

```
Store (interface)
├── SQLiteStore      local, tests, single-node
└── (Firestore)      private deployment, serverless
```

Both answer the same questions: `list_sessions`, `get_session`, `get_events`,
art records by signature, aggregate counts. Nothing in the interpretation layer
knows which backend is behind the interface.

Art blobs go to disk locally or to object storage in a deployment; `art.store_blob`
returns `(image_url, image_path)` either way, and `art.art_for` is a pure read that
**never** triggers generation. A request for a missing portrait 404s; it does not
start spending money.

## What this package deliberately does not do

- Score requests
- Classify user agents
- Detect header-order or fingerprint spoofing
- Tarpit, trap, or rate-limit
- Notify anyone of anything
- Hold a canary value

Each of those is a one-line add via a hook, which is the point.
