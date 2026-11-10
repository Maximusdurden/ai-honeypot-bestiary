# Taxonomy

Seven ranks, applied to a web request instead of a beetle.

This document is the reference. For a worked example of all nine genera, read
[docs/findings/field-guide.md](findings/field-guide.md), which is generated from
the synthetic corpus.

---

## The ranks

### Kingdom — is it a machine?

| Kingdom | Assigned when |
| --- | --- |
| `Humana` | verdict is `human` or `likely_human` |
| `Machina` | inferred AI, a confession, an API probe, a crawler, a browser driven by automation, or an HTTP client |
| `Dubia` | nothing above fired |

`Dubia` is not a failure state. A visitor that leaves no evidence is genuinely
ambiguous, and pretending otherwise would be the failure.

### Phylum / Class — broad lineage

| Kingdom | Phylum | Class | Meaning |
| --- | --- | --- | --- |
| `Machina` | `Agentia` | `LlmAgentia` | an LLM agent: declared, confessed, or probing |
| `Machina` | `Crawlera` | `IndexCrawlera` | an index crawler |
| `Machina` | `Browsera` | `AutomataBrowsera` | a browser under automation |
| `Machina` | `Clientia` | `ScriptaClientia` | a bare HTTP client |
| `Humana` | `Hominidae` | `Sapiena` | a person |
| `Dubia` | `Incerta` | `Incerta` | undetermined |

Note the ordering: a request that *probes an API surface* is classified as an LLM
agent even if its user agent says `python-requests`. Behaviour outranks the
string, which is the whole thesis.

### Order — vendor or framework lineage

Keyed off the declared family. `GPTBot` and `OAI-SearchBot` are both `OpenAI`;
`python-requests` and `python-httpx` are both `Python`. Roughly seventy families
are mapped, spanning LLM vendors, browser automation, HTTP clients, search
crawlers, social unfurlers, and browsers.

Unknown families fall to `Incerta` rather than being guessed at.

### Family — the declared product

`GPTBot`, `ClaudeBot`, `PerplexityBot`, `HeadlessChrome`, `python-requests`,
`curl`, `Chrome`… the product name as declared. **Not verified.** A family is a
claim, and the genus exists precisely because claims are unreliable.

### Genus — how it behaved

The interesting rank. Assigned by strict precedence:

```
1. confessed ..................... Loqualis
2. hit a machine endpoint ........ Curiosus
3. agent_kind == "ai" ............ Manifestus
4. spoofed or headless ........... Furtim
5. depth >= 5 .................... Volans
6. interval < 100 ms ............. Rapidus
7. depth <= 1 .................... Sedens
8. otherwise ..................... Ignotus
```

Humans skip this entirely and are always `Sapiens`, because behavioural machine
genera read as nonsense applied to a person.

| Genus | Precedence | Gloss |
| --- | ---: | --- |
| *Loqualis* | 1 | Submits free-text descriptions of its own provenance when asked. |
| *Curiosus* | 2 | Probes machine-discovery surfaces (MCP, OpenAPI, plugin manifests). |
| *Manifestus* | 3 | Announces its identity in the User-Agent string. |
| *Furtim* | 4 | Conceals its nature behind a browser User-Agent or headless tells. |
| *Volans* | 5 | Roams deep into the breadcrumb chain. |
| *Rapidus* | 6 | Moves between pages faster than a human can read them. |
| *Sedens* | 7 | Stays near the entry point. |
| *Ignotus* | 8 | Insufficient evidence to place behaviourally. |
| *Sapiens* | — | A genuine browser: consistent headers, no automation tells. |

#### Why this precedence

**Confession beats everything.** A machine that has just written a sentence about
what it is has given the strongest evidence obtainable. Nothing else should
outrank that.

**A probe beats a declaration.** `Curiosus` outranks `Manifestus` because a
declared bot that *also* fetches `/openapi.json` is doing something the plain
declaration does not explain. Declaration is free; curiosity is a choice.

**A spoof beats a declaration.** `Furtim` outranks a declaration because claiming
to be Chrome while tripping `webdriver` is a lie, and a lie is more informative
than a claim.

**Depth before speed before shallowness.** These three are mutually exclusive in
practice: `Volans` has to have depth ≥ 5 to win, which by definition means it is
not `Sedens`. Ordering depth above speed means a fast deep crawler is filed as
deep-roaming — the more distinctive trait.

**`Sedens` is depth ≤ 1, not depth 1.** Two requests — a page and an asset — is
still "stood in the doorway".

#### What counts as a machine endpoint

`Curiosus` requires probing something that only an *integrating* agent would want:

```
/mcp
/openapi.json
/.well-known/ai-plugin.json
```

Deliberately **excluded**: `/llms.txt` and `/robots.txt`. Those are standard
discovery files that well-behaved crawlers are *supposed* to read. Fetching them
is compliance, not probing, and treating it as suspicion would punish good
behaviour.

A deployment can replace this set:

```python
from bestiary.taxonomy import configure_machine_endpoints
configure_machine_endpoints({"/mcp", "/openapi.json", "/.well-known/ai-plugin.json"})
```

### Species — the epithet

The family, latinised:

| Family | Species |
| --- | --- |
| `GPTBot` | `gptbotensis` |
| `PerplexityBot` | `perplexitybotensis` |
| `python-requests` | `pyrequestensis` |
| `python-httpx` | `pyhttpxensis` |
| `curl` | `curlensis` |
| `HeadlessChrome` | `headlesschromensis` |

Rules: lowercase, strip non-letters, drop a trailing `s`, then add `-ensis`, or
`-nsis` after a vowel. A handful of aliases keep names pronounceable
(`python-requests` → `pyrequests`). An empty or unparseable name becomes
`incognita` rather than an exception.

Binomial: `Genus species`. E.g. **`Curiosus perplexitybotensis`**.

---

## Diagnostic characters

Every classification records *why*. A species without its reasons is unfalsifiable.

Examples as rendered:

- `Declared "GPTBot" in the User-Agent`
- `Fetched /mcp (machine discovery surface)`
- `Answered interrogation: "What are you?"`
- `Headless rendering stack (SwiftShader)`
- `Inconsistent fingerprint: 3 request(s) sent Sec-Fetch headers, 2 did not`

The last one is session-level, not request-level: any single-request view sees a
browser, and only the sequence reveals a script that impersonates one sometimes.
That is why it is a hook — detecting it belongs to the capture layer, but
*displaying* it belongs here.

---

## Conservation status

Abundance, not endangerment:

| Status | Observations |
| --- | ---: |
| `Abundant` | ≥ 100 |
| `Common` | ≥ 20 |
| `Uncommon` | ≥ 5 |
| `Rare` | ≥ 2 |
| `Singular` | 1 |

---

## Signature

```
signature = sha256(kingdom | phylum | class | order | family | genus | species)
```

Truncated to 16 hex characters for display. It is the identity of a species: it
groups observations, keys the portrait cache, and keys the art record.

**It must be `sha256`.** Python's built-in `hash()` is salted per interpreter
process, so signatures would change between restarts and every species would get
a new portrait every deploy. This is not theoretical — it was a bug.

Because the signature covers the full rank tuple, a change in behaviour splits a
family into two species. `GPTBot` that declares itself is
`Manifestus gptbotensis`; `GPTBot` caught spoofing is `Furtim gptbotensis`. Same
family, same epithet, different genus, different species. That is intended: the
bestiary is a record of *behaviour encountered*, not a registry of names.

---

## Limits, stated plainly

- **The family is a claim.** Nothing here verifies that the entity behind
  `GPTBot` is OpenAI. A genus mitigates this; it does not solve it.
- **Genus is a heuristic.** The cut-offs (depth 5, 100 ms) are tuned, not derived.
  They are also configurable, because a site with three pages and a site with
  thirty thousand need different numbers.
- **`Ignotus` is common and should be.** Most traffic is unremarkable.
- **`Sapiens` is a label, not a proof.** A careful enough automation could land
  there. Nothing here claims otherwise.
- **The taxonomy is descriptive, not normative.** `Furtim` means "concealed its
  nature", not "did something wrong". Plenty of legitimate tooling looks exactly
  like this.
