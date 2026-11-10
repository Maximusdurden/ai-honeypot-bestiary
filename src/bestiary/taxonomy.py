"""Taxonomic classification of captured agents — a field guide for the wild.

Every distinct automated visitor is treated as a species discovery. We assign
the seven standard ranks, mint a binomial Latin name, and record the diagnostic
characters that justify the call.

    Kingdom   Machina | Humana | Dubia
    Phylum    Agentia | Crawlera | Browsera | Clientia | Hominidae | Incerta
    Class     LlmAgentia | IndexCrawlera | AutomataBrowsera | ScriptaClientia
              | Sapiena | Incerta
    Order     vendor / framework lineage (OpenAI, Anthropic, Python, ...)
    Family    the declared product (GPTBot, python-requests, ...)
    Genus     behavioural grouping (Manifestus, Furtim, Loqualis, ...)
    Species   latinised family epithet (gptbotensis, pyrequestensis, ...)

The genus is the interesting part: it encodes *how* the visitor behaved, not
what it claimed to be. A GPTBot that announces itself is ``Manifestus``; the
same UA string arriving with a spoofed browser fingerprint is ``Furtim``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# Order (vendor / framework lineage) keyed by the declared family.
# --------------------------------------------------------------------------
_ORDER_BY_FAMILY: dict[str, str] = {
    # --- LLM vendors ---
    "GPTBot": "OpenAI",
    "OAI-SearchBot": "OpenAI",
    "ChatGPT-User": "OpenAI",
    "ClaudeBot": "Anthropic",
    "Claude-User": "Anthropic",
    "Claude-SearchBot": "Anthropic",
    "anthropic-ai": "Anthropic",
    "PerplexityBot": "Perplexity",
    "Perplexity-User": "Perplexity",
    "Google-Extended": "Google",
    "Googlebot": "Google",
    "Applebot-Extended": "Apple",
    "MistralAI-User": "Mistral",
    "cohere-ai": "Cohere",
    "YouBot": "You.com",
    "DuckAssistBot": "DuckDuckGo",
    "meta-externalagent": "Meta",
    "facebookexternalhit": "Meta",
    "Amazonbot": "Amazon",
    "Bytespider": "ByteDance",
    "CCBot": "CommonCrawl",
    "Diffbot": "Diffbot",
    "ImagesiftBot": "Imagesift",
    "Omgilibot": "Omgili",
    "Timpibot": "Timpi",
    "PanguBot": "Pangu",
    "AI2Bot": "AI2",
    "Webz.io": "Webz.io",
    # --- browser automation ---
    "Playwright": "Playwright",
    "Puppeteer": "Puppeteer",
    "Selenium": "Selenium",
    "HeadlessChrome": "Chromium",
    "PhantomJS": "PhantomJS",
    "Scrapy": "Scrapy",
    # --- HTTP clients ---
    "python-requests": "Python",
    "python-httpx": "Python",
    "httpx": "Python",
    "aiohttp": "Python",
    "python-urllib": "Python",
    "curl": "curl",
    "wget": "GNU",
    "Go-http-client": "Go",
    "node-fetch": "Node.js",
    "undici": "Node.js",
    "axios": "Node.js",
    "OkHttp": "Square",
    "Apache-HttpClient": "Apache",
    "libwww-perl": "Perl",
    "GuzzleHttp": "PHP",
    "RestSharp": ".NET",
    "PostmanRuntime": "Postman",
    "Insomnia": "Insomnia",
    # --- search crawlers ---
    "Bingbot": "Microsoft",
    "YandexBot": "Yandex",
    "BaiduSpider": "Baidu",
    "AhrefsBot": "Ahrefs",
    "SemrushBot": "Semrush",
    "MJ12bot": "Majestic",
    "DotBot": "Moz",
    "PetalBot": "Huawei",
    # --- social / messaging ---
    "LinkedInBot": "LinkedIn",
    "Slackbot": "Slack",
    "Discordbot": "Discord",
    "TelegramBot": "Telegram",
    "WhatsApp": "Meta",
    "Twitterbot": "X",
    # --- browsers ---
    "Chrome": "Google",
    "Firefox": "Mozilla",
    "Safari": "Apple",
    "Edge": "Microsoft",
    "Opera": "Opera",
}

# Readability aliases so binomials stay pronounceable.
_ALIASES = {
    "python-requests": "pyrequests",
    "python-httpx": "pyhttpx",
    "python-urllib": "pyurllib",
    "go-http-client": "gohttp",
    "node-fetch": "nodefetch",
    "apache-httpclient": "apachehttp",
    "libwww-perl": "libwwwperl",
    "headlesschrome": "headlesschrome",
    "meta-externalagent": "metaexternal",
    "facebookexternalhit": "facebookexternal",
}

# Genus -> the adjective used in the common name.
_GENUS_ADJECTIVE = {
    "Loqualis": "Talkative",
    "Curiosus": "Inquisitive",
    "Manifestus": "Declared",
    "Furtim": "Stealthy",
    "Volans": "Deep-roaming",
    "Rapidus": "Swift",
    "Sedens": "Shallow",
    "Ignotus": "Unidentified",
    "Sapiens": "Ordinary",
}

# Genus -> a one-line ecological gloss for the field guide.
_GENUS_GLOSS = {
    "Loqualis": "Submits free-text descriptions of its own provenance when asked.",
    "Curiosus": "Probes machine-discovery surfaces (MCP, OpenAPI, plugin manifests).",
    "Manifestus": "Announces its identity in the User-Agent string.",
    "Furtim": "Conceals its nature behind a browser User-Agent or headless tells.",
    "Volans": "Roams deep into the breadcrumb chain.",
    "Rapidus": "Moves between pages faster than a human can read them.",
    "Sedens": "Stays near the entry point.",
    "Ignotus": "Insufficient evidence to place behaviourally.",
    "Sapiens": "A genuine browser: consistent headers, no automation tells.",
}

# Genera that only make sense for a machine. Used to keep human binomials sane.
_MACHINE_GENERA = {
    "Loqualis", "Curiosus", "Manifestus", "Furtim",
    "Volans", "Rapidus", "Sedens", "Ignotus",
}

# Endpoints that only an *integrating* agent would call. Deliberately excludes
# /llms.txt and /robots.txt: those are standard discovery files that
# well-behaved crawlers are supposed to read, so fetching them is not probing.
# Paths that count as "machine discovery" -- probing an API surface rather than
# browsing a page. The genus Curiosus is reserved for visitors that hit these.
#
# NOTE: the live deployment's exact set is deliberately not published. It is a
# configuration surface, not an architectural constant: any deployment picks its
# own decoy endpoints, and a published list would tell a crawler exactly which
# paths to avoid. Override with configure_machine_endpoints().
_MACHINE_ENDPOINTS: set[str] = {
    "/mcp",
    "/openapi.json",
    "/.well-known/ai-plugin.json",
}


def configure_machine_endpoints(paths: "set[str] | list[str] | tuple[str, ...]") -> None:
    """Replace the set of paths treated as machine-discovery probes.

    Deployments should call this at startup with their own decoy endpoints so
    the interpretation layer stays deployment-agnostic.
    """
    global _MACHINE_ENDPOINTS
    _MACHINE_ENDPOINTS = {str(p) for p in paths if str(p).strip()}

_REASON_PREFIX = re.compile(r"^\+\d+\s+")


@dataclass
class Taxonomy:
    kingdom: str
    phylum: str
    taxon_class: str
    order: str
    family: str
    genus: str
    species: str
    binomial: str
    common_name: str
    signature: str
    diagnostic_characters: list[str] = field(default_factory=list)
    genus_gloss: str = ""

    def ranks(self) -> list[tuple[str, str]]:
        return [
            ("Kingdom", self.kingdom),
            ("Phylum", self.phylum),
            ("Class", self.taxon_class),
            ("Order", self.order),
            ("Family", self.family),
            ("Genus", self.genus),
            ("Species", self.species),
        ]


def latinize(name: str | None) -> str:
    """Turn a product name into a plausible Latin species epithet."""
    if not name:
        return "incognita"
    key = name.strip().lower()
    stem = _ALIASES.get(key) or re.sub(r"[^a-z]", "", key)
    if not stem:
        return "incognita"
    if stem.endswith("s"):
        stem = stem[:-1]
    if stem[-1] in "aeiou":
        return stem + "nsis"
    return stem + "ensis"


def _pick_genus(
    *,
    agent_kind: str,
    confessed: bool,
    hit_machine: bool,
    spoofed: bool,
    headless: bool,
    max_depth: int,
    min_interval_ms: int | None,
) -> str:
    """Behavioural genus, most salient trait first."""
    if confessed:
        return "Loqualis"
    if hit_machine:
        return "Curiosus"
    if agent_kind == "ai":
        return "Manifestus"
    if spoofed or headless:
        return "Furtim"
    if max_depth >= 5:
        return "Volans"
    if min_interval_ms is not None and min_interval_ms < 100:
        return "Rapidus"
    if max_depth <= 1:
        return "Sedens"
    return "Ignotus"


def _clean_reasons(reasons: list[str]) -> list[str]:
    out: list[str] = []
    for reason in reasons:
        cleaned = _REASON_PREFIX.sub("", reason).strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def classify_species(
    *,
    agent_family: str | None,
    agent_kind: str,
    score: int,
    verdict: str,
    probe: dict[str, Any] | None = None,
    interrogation: list[dict[str, Any]] | None = None,
    paths: list[str] | None = None,
    max_depth: int = 0,
    min_interval_ms: int | None = None,
    reasons: list[str] | None = None,
) -> Taxonomy:
    """Assign the seven ranks to one captured visitor."""
    paths = paths or []
    interrogation = interrogation or []
    probe = probe or {}

    # A *confession* is a free-text account submitted through /interrogate.
    # An MCP tool call is logged to the same table but is a probe, not a
    # confession, so it must not promote the visitor to Loqualis.
    confessed = any(item.get("channel") != "mcp" for item in interrogation)
    hit_machine = bool(set(paths) & _MACHINE_ENDPOINTS)  # noqa: F821 - module global
    renderer = str(probe.get("webgl_renderer") or "").lower()
    headless = bool(probe.get("webdriver")) or "swiftshader" in renderer or "llvmpipe" in renderer
    spoofed = bool(probe.get("ua_spoof_suspected"))

    # --- Kingdom / Phylum / Class -------------------------------------
    if verdict in {"human", "likely_human"}:
        kingdom, phylum, klass = "Humana", "Hominidae", "Sapiena"
    elif agent_kind == "ai" or confessed or hit_machine:
        kingdom, phylum, klass = "Machina", "Agentia", "LlmAgentia"
    elif agent_kind == "crawler":
        kingdom, phylum, klass = "Machina", "Crawlera", "IndexCrawlera"
    elif agent_kind == "browser" or headless:
        kingdom, phylum, klass = "Machina", "Browsera", "AutomataBrowsera"
    elif agent_kind in {"http", "tool"}:
        kingdom, phylum, klass = "Machina", "Clientia", "ScriptaClientia"
    else:
        kingdom, phylum, klass = "Dubia", "Incerta", "Incerta"

    # --- Order / Family ------------------------------------------------
    family = agent_family or "Incerta"
    order = _ORDER_BY_FAMILY.get(family, "Incerta")

    # --- Genus / Species ----------------------------------------------
    if kingdom == "Humana":
        # Behavioural machine genera would read as nonsense for a person.
        genus = "Sapiens"
    else:
        genus = _pick_genus(
            agent_kind=agent_kind,
            confessed=confessed,
            hit_machine=hit_machine,
            spoofed=spoofed,
            headless=headless,
            max_depth=max_depth,
            min_interval_ms=min_interval_ms,
        )
    species = latinize(agent_family)
    binomial = f"{genus} {species}"

    adjective = _GENUS_ADJECTIVE.get(genus, "Unidentified")
    common_name = f"{adjective} {agent_family or 'visitor'}"

    signature = hashlib.sha256(
        f"{kingdom}|{phylum}|{klass}|{order}|{family}|{genus}".encode("utf-8")
    ).hexdigest()[:16]

    # --- Diagnostic characters ----------------------------------------
    characters = _clean_reasons(reasons or [])
    if confessed:
        characters.append("Submitted a free-text account of its own provenance")
    if hit_machine:
        characters.append("Requested a machine-discovery endpoint")
    if headless:
        characters.append("Exhibited headless-browser tells")
    if spoofed:
        characters.append("Browser User-Agent without Sec-Fetch headers")

    return Taxonomy(
        kingdom=kingdom,
        phylum=phylum,
        taxon_class=klass,
        order=order,
        family=family,
        genus=genus,
        species=species,
        binomial=binomial,
        common_name=common_name,
        signature=signature,
        diagnostic_characters=characters,
        genus_gloss=_GENUS_GLOSS.get(genus, ""),
    )


def conservation_status(observation_count: int) -> str:
    """How common is this species in the wild?"""
    if observation_count >= 100:
        return "Abundant"
    if observation_count >= 20:
        return "Common"
    if observation_count >= 5:
        return "Uncommon"
    if observation_count >= 2:
        return "Rare"
    return "Singular"
