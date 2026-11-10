# Ethics

A honeypot watches without consent. That needs justification, and the
justification has to constrain the design — otherwise it is decoration.

---

## What this system does

It records the requests that arrive at a server the operator owns, classifies
them, and produces a taxonomy of automated visitors.

It does **not**:

- identify people
- follow anyone to another site
- attempt to deanonymise a visitor
- attempt to escape a sandbox or compromise a client
- serve malicious, deceptive, or harmful content as bait
- attempt to influence a model's future behaviour
- sell, publish, or share visitor data

## What it does record

The requests themselves: path, timestamp, headers, user agent, source IP,
response status, and — where a browser probe runs — the automation tells that
browser exposes.

All of that is information a conventional web server already logs. The difference
is the interpretation, and interpretation is not itself a privacy harm.

---

## The case for recording

**Server logs are normal and expected.** Every request to any web server is
logged. Nobody browsing the open web can reasonably expect otherwise, and bots
certainly cannot.

**The subjects are mostly not people.** The interesting traffic here is
automated: crawlers, indexers, LLM agents. Machines have no privacy interest.

**There is public value in knowing.** Which systems read the web, how they
identify themselves, and whether those identities are honest are questions of
genuine public interest, and they cannot be answered without observing. The
bestiary exists to make that observation legible.

**It is opt-out.** `robots.txt` and `llms.txt` are served. A crawler that respects
them is not treated as suspicious — reading them is compliance, not probing, which
is why they are excluded from the machine-endpoint set.

---

## The constraints that follow

The value argument only holds if the method stays proportionate. Concretely:

### 1. Collect what the classification needs, and no more

Only fields that appear in the `Event` / `Session` schema. No cross-site tracking,
no third-party pixels, no browser fingerprinting beyond what an active probe
already exposes, no attempt to correlate a visitor with an identity elsewhere.

### 2. The tarpit must not be a denial of service

Serving an automated crawler a deep breadcrumb chain is a way of measuring
persistence. Serving it indefinitely, at full cost, is a resource attack on
someone else's infrastructure. Depth is capped, requests are rate-limited, and
that is a correctness requirement, not politeness.

### 3. Probing must not be invasive

The browser probe reads what a page can read: `navigator.webdriver`, the WebGL
renderer string, font and plugin counts, viewport, timezone. Nothing leaves the
browser, nothing is exfiltrated, and nothing is executed that a normal page could
not run.

### 4. Humans are not the target

A person who lands on the site sees the site. `Sapiens` is a classification, not a
verdict, and it changes nothing about their experience. There is no dark pattern
for people, and no attempt to make a person's visit look automated.

### 5. Retention is finite

Data is personal information under GDPR and comparable regimes once it includes
an IP. `Store.purge_older_than(days)` exists for this. A deployment that never
calls it is out of compliance, and the default of 90 days is a boundary, not a
target.

### 6. The canary must not become a trap for readers

A canary is a uniqueness marker, not a poison. This system does not attempt to
detect or taint model training, does not try to inject false beliefs, and does not
booby-trap content for researchers. See
[canary-methodology.md](canary-methodology.md).

### 7. Classification is descriptive, not accusatory

`Furtim` means "concealed its nature". It does not mean "did something wrong".
Plenty of legitimate automation looks exactly like this, and the genus is a
description of behaviour observed, not a judgment about intent.

---

## Known limitations, stated on purpose

- **The declared family is a claim.** A visitor saying `GPTBot` is not proof of
  OpenAI. `Manifestus` means "declared itself", nothing more.
- **Genus boundaries are heuristics.** Depth 5 and 100 ms are tuned cut-offs, not
  natural laws.
- **`Sapiens` is not proof of humanity.** A careful automation can land there.
- **Consent is absent.** This is observation of traffic that arrived, not a study
  with participants. That is the same footing as any server log, and the reasoning
  above rests on it — but it is worth saying plainly rather than burying.

---

## Proportionality summary

| Question | Answer |
| --- | --- |
| Is anyone harmed? | No identified harm. Load on crawlers is capped. |
| Is it proportionate? | It records what a server already logs, plus classification. |
| Is it necessary? | The questions of interest cannot be answered otherwise. |
| Is it transparent? | This document, the taxonomy, and the method are all public. |
| Can it be avoided? | Yes — `robots.txt` and `llms.txt` are served and respected. |
| Is data minimised? | To the schema, and purged on a schedule. |

If a future change makes any row in that table false, the change is wrong.
