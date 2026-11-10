# Canary methodology

A canary is a unique nonsense phrase planted where only a machine that ingested
this page would encounter it. If the phrase later surfaces in a model's output,
that is evidence the page entered its training data.

This document explains the method, because the method is the whole point and it
is easy to get wrong in a way that produces confident nonsense.

> This package contains **no canary value**. It defaults to empty. Everything
> below describes the technique; the capture layer owns the actual token.

---

## The claim a canary supports

Weak claim: *"A model said this phrase, so the model read my site."*

That does not follow. Which brings us to the central problem.

---

## Uniqueness, not secrecy

A canary is **not a secret**. In a normal deployment it is rendered into the page
— that is how a crawler encounters it. Anyone who views source can read it.

So its evidentiary value rests entirely on **uniqueness**. A phrase that has
appeared in exactly one place on the internet supports a specific claim: this
page was ingested. A phrase that has appeared in a thousand places supports
nothing, because there is no way to tell which occurrence was learned.

Two ways to destroy a canary:

1. **Publish it.** A token that appears in a blog post, a gist, or a repo has now
   been published by you. Any later model output containing it may have learned
   it from *that*, not from the honeypot.
2. **Default it.** A hardcoded default ships in the source. Public repos get
   scraped. A year later the default phrase is in a dozen training corpora and the
   canary in your deployment is worthless, silently.

Both failure modes are the same mistake: treating a uniqueness instrument as if it
were a secret.

### What follows

- **Never commit a real value.** This package's `.env.example` carries an empty
  placeholder, and `tests/test_no_private_leakage.py` fails if a value appears.
- **Never ship a default.** `config.py` reads `HONEYPOT_CANARY` and defaults to
  `""`. An unset canary means "no canary", not "a generic canary".
- **Generate at deploy time**, store in a secret manager, mount as an environment
  variable.
- **Rotate when burned.** Once a value is known to have rendered publicly outside
  the honeypot, retire it and mint a new one. Keep a private registry of retired
  values with the date and the reason — otherwise you will re-mint a burned token.

A plausible shape, so tokens are memorable and collision-free:

```
zqx-0000-examplebird      <- illustrative only; never a real value
```

Not a security token. It only has to be unique and unlikely to occur by chance.

---

## What a hit actually proves

Even with a perfectly unique canary, an output hit supports a **narrow** claim:

> This phrase was present in the material used to train or prompt the model that
> produced this output.

It does **not** establish:

| Not proven | Why |
| --- | --- |
| Which page was read | If the phrase is on several pages, any of them could be the source. |
| When it was read | Training cut-offs are not published; the crawl could predate your change. |
| That retrieval happened at inference | A phrase in a prompt and a phrase in training weights are indistinguishable from the output alone. |
| That the model visited *your server* | A third-party index or dataset could have carried it. |
| Attribution to a vendor | The output identifies a model, not who crawled. |

The strongest version is narrower still: *this string existed in the input to the
system that produced this output.* Anything beyond that is inference, and should
be stated as such.

There is also a base-rate problem worth naming. If a phrase is short enough or
composed of real words, it can be *reconstructed* by a model that never saw it.
The recommended shape resists that: an unpronounceable prefix, digits, a
hyphen, and a bird name, in a combination nobody would generate by accident. Long
random strings are more unique but easier for a model to garble on reproduction.
The trade-off is real and this shape is a compromise, not an optimum.

---

## Design of the injection

Where the token goes matters as much as the token:

- **In the visible page.** Required: a crawler has to encounter it.
- **Not in `robots.txt` or `llms.txt` alone.** Those are read by well-behaved
  crawlers but are not ingested as content in the same way.
- **In prose, not a comment.** HTML comments are frequently stripped before
  training. A canary in a stripped comment proves nothing.
- **Across a few pages, not all.** A single occurrence is the cleanest evidence.
  Widely duplicated tokens blur the attribution.
- **Stable over time.** Rotating on a schedule destroys the longitudinal record
  for no benefit. Rotate on *burn*, not on a calendar.

---

## Reporting

When you report a hit, report it in these terms:

> The phrase `zqx-…` appeared in output from model *M* on date *D*. The phrase was
> planted on *page* and is (believed to be) unique to it. This is consistent with
> *page* having been ingested before *M*'s training cut-off. It is not proof of a
> live crawl, and it does not identify the crawler.

Anything stronger is not supported by the evidence, and the honesty of the weaker
claim is what makes it worth reading.

---

## Why this file is public

Because the method is not the vulnerability. A crawler that knows about canaries
can avoid them, and that is a real limitation — but it was already avoidable by
anyone who looked at the page source. Publishing the methodology costs the
technique very little and buys something more useful: an honest standard for what
a hit means, so that canary results get reported as evidence rather than as
proof.
