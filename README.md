# ai-honeypot-bestiary

**A Linnaean taxonomy for the things crawling the web.**

When a bot hits a site, most analytics answer one question: *was it a bot?* This
package asks the more interesting ones. **What kind?** **How did it behave?**
**Does it lie about what it is?** And then, because a field guide without plates
is just a spreadsheet, it gives each newly identified species a portrait —
deterministically, from its own fingerprint, so the same species always looks
the same.

The output is a bestiary: species with binomial Latin names, seven taxonomic
ranks, diagnostic characters, conservation status, and one image each.

---

## What this is, and what it is not

This repository is the **interpretation layer**. It takes records that have
already been captured and does the reading: classification, species grouping,
field-guide rendering, portrait prompting.

It is **not** the honeypot. It contains:

- no request scoring
- no user-agent classification table
- no header-fingerprinting or spoof detection
- no tarpit, canary, or notification logic

Those live in the capture layer, which stays private. Two documented hooks let a
real deployment plug its own implementations in; without them the package runs on
the fields already present in the record schema. **The split is enforced by a
test**, not by good intentions — see [Publishing safely](#publishing-safely).

Because of that split, this repo ships with a **synthetic corpus** so it runs
end-to-end with nothing live behind it.

---

## Try it in thirty seconds

```bash
git clone https://github.com/Maximusdurden/ai-honeypot-bestiary
cd ai-honeypot-bestiary
python -m venv venv
venv/bin/pip install -e ".[dev]"        # Windows: venv\Scripts\pip

python scripts/build_field_guide.py     # writes docs/findings/field-guide.md
```

That reads `fixtures/synthetic_sessions.json`, classifies it, and writes a full
field guide. No network, no database, no API key.

To see the prompts it would send to an image model — and spend nothing:

```bash
python scripts/generate_art.py
```

It is a **dry run by default**. `--live` requires an API key and is the only way
to spend money.

```bash
pytest        # 191 tests; one skips without a private deny-list (see below)
```

---

## The taxonomy

Seven ranks, borrowed from Linnaeus and bent to the purpose:

| Rank | Meaning | Example |
| --- | --- | --- |
| **Kingdom** | Is it a machine, or a person? | `Machina` |
| **Phylum** | Broad lineage | `Agentia` |
| **Class** | What sort of thing | `LlmAgentia` |
| **Order** | Vendor or framework lineage | `Perplexity` |
| **Family** | The declared product | `PerplexityBot` |
| **Genus** | **How it behaved** | `Curiosus` |
| **Species** | Latinised family epithet | `perplexitybotensis` |

The genus is the part worth reading. It is assigned from *behaviour*, not from
what the visitor claims:

| Genus | Signal | Gloss |
| --- | --- | --- |
| *Loqualis* | answered a free-text interrogation | describes its own provenance |
| *Curiosus* | fetched an API or MCP discovery surface | probes machine surfaces |
| *Manifestus* | declared itself in the User-Agent | announces its identity |
| *Furtim* | browser UA driven by automation | conceals its nature |
| *Volans* | deep breadcrumb chain | roams deep |
| *Rapidus* | sub-100 ms between pages | faster than reading |
| *Sedens* | entry point only | stays near the door |
| *Ignotus* | nothing distinguishing | insufficient evidence |
| *Sapiens* | a genuine browser | ordinary |

Precedence matters and is deliberate: a *confession* outranks everything, because
a machine describing itself is the strongest evidence available. A spoof outranks
a declaration, because a spoof is a lie and a declaration is not.

Read the full worked guide: **[docs/findings/field-guide.md](docs/findings/field-guide.md)**
— ten species covering all nine genera, generated from the synthetic corpus.

---

## Visual DNA

A portrait is derived from the species signature, which is a hash. So the same
species always gets the same body, and different species reliably differ.

`morphology_for(signature)` draws five traits **independently**, each from a
different byte of the digest:

```
body shape   8 options
limbs        7 options
legs         8 options
eyes         8 options
locomotion   5 options
            ─────────────
            ~17,920 combinations
```

Drawing from one shared pool would make new species look like recolours. Drawing
independently is what makes a *Manifestus* with no arms and a smooth sensor plate
read as a different animal from a *Manifestus* with too many legs.

One detail that bit us: **use `hashlib`, never `hash()`.** Python's built-in hash
is salted per process, so a portrait generated today would not match the same
species generated tomorrow.

Humans get a different treatment. A human rendered with "extra eyes" and a blank
visor is a monster wearing a person, so `Humana` species get a persona template
instead — a build, an attire, a prop, a setting — sharing none of the creature
accessory rules.

### Prompt uniqueness is a test, not a hope

Two species with the same genus could easily collide on the same prompt, which
would produce two identical images and quietly break the whole premise. There is
a test asserting **every species gets a distinct prompt**, and it runs without
generating any art, so a collision is caught for free rather than after the bill.

---

## The corpus

`fixtures/synthetic_sessions.json` — 40 sessions, 10 species, all nine genera.

- **Deterministic.** Fixed seed, fixed base timestamp. Same bytes every run, so
  the published field guide is reproducible.
- **Fabricated.** All IPs are RFC 5737 documentation ranges (`192.0.2.0/24`,
  `198.51.100.0/24`, `203.0.113.0/24`). Nothing here is a real visitor.
- **Explained.** `fixtures/generate_fixtures.py` is the generator and documents
  every choice. Real user-agent strings appear because the taxonomy keys off
  them, and inventing fake ones would defeat the point.

Genus is assigned per profile rather than per index, so **the corpus covers every
genus regardless of size**. A demo showing only declared crawlers would teach a
reader nothing.

---

## Design notes

**Diagnostic characters, not scores.** Each species records *why* it was placed
where it was: "Declared 'GPTBot' in the User-Agent", "Fetched /mcp (machine
discovery surface)". A classification you cannot justify is a guess.

**Conservation status tracks abundance, not threat.** `Singular` through
`Abundant`. It is a joke that carries real information: how often this species
turns up.

**The canary is a research instrument.** The capture layer injects a unique
phrase so that if it later appears in a model's output, that is evidence the page
was ingested. It is **not** a secret — it is rendered on the page by design. Its
integrity therefore depends on *uniqueness*, never on secrecy, which is exactly
why a default value would destroy it: a defaulted or committed canary ends up in
training corpora and stops proving anything. This package defaults it to empty.

---

## Publishing safely

The private/public split is enforced by `tests/test_no_private_leakage.py`, in two
layers.

**Layer 1 — shape rules, published.** Nothing here names a real identifier,
because a published test that lists the values it bans leaks exactly what it is
meant to protect. Instead the rules match shapes:

- Cloud Run hostnames, revision suffixes, and persona-named project ids
- project-prefixed object-storage URLs
- credentials and webhooks by shape (Google API keys, OpenRouter keys, GitHub
  tokens, PEM private keys, Discord and Slack webhook URLs)
- this project's own canary shape
- detector tables, by name
- any 24+ character string assigned to something secret-shaped

**Layer 2 — literal deny-list, private.** Some identifiers cannot be recognised by
shape: a bare project id looks like any other slug. Those go in
`private_denylist.txt`, which is git-ignored. When the file is present the test
checks it; when it is absent — as it is here — that check skips and layer 1 still
runs.

This gives a maintainer the strong check locally without weakening the published
one. It is the single most important design decision in the repo, and it was
arrived at by watching layer 1 try to hardcode the real values and fail.

The guard is deliberately paranoid. Most failures are real. If you add a file and
it goes red, the fix is almost never an allow-list entry.

---

## Layout

```
src/bestiary/
  taxonomy.py       seven ranks, genus precedence, binomials
  fieldguide.py     specimens -> species -> rendered guide (hook: agent kind)
  bestiary.py       aggregate stats for the collection view
  visual_dna.py     signature -> traits -> prompt (deterministic)
  art.py            provider protocol, caching, cost accounting
  store.py          store interface
  store_sqlite.py   SQLite backend (hook: session scoring)
  config.py         settings from environment
fixtures/           synthetic corpus + generator
scripts/            build_field_guide.py, generate_art.py
tests/              191 tests, including the leakage guard
```

## License

MIT. See [LICENSE](LICENSE).

## Citing

See [CITATION.cff](CITATION.cff).
