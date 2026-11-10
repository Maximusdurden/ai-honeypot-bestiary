"""Visual DNA: a deterministic mapping from taxonomy to an image prompt.

Every rank drives exactly one visual attribute, so the same species always
yields the same prompt and therefore a consistent portrait. This module is
**pure**: no I/O, no randomness, no clock. That makes it trivially testable and
means a prompt can be reproduced from a signature alone.

    Kingdom  -> overall form
    Phylum   -> body plan
    Class    -> material / texture
    Order    -> palette
    Family   -> markings
    Genus    -> posture / expression
    Species  -> pattern
    Diagnostic characters -> accessories

Family and Species are included deliberately: without them two distinct
species sharing kingdom/phylum/class/order/genus (e.g. ``GPTBot`` and
``OAI-SearchBot``) would render byte-identical prompts and therefore
indistinguishable portraits.

Image models are non-deterministic, so identical prompts do not guarantee
identical bytes. That is precisely why art is generated once and cached
forever (see ``app/art.py``).
"""

from __future__ import annotations

import hashlib
from typing import Any

# Bump when the mapping or template changes. Stored on every ArtRecord so a
# stale portrait can be identified without diffing prompts.
#
# v4: restyled to sit between v2 (19th-century plate, "slightly uncanny") and
# v3 (chibi collectible-card, "adorable"). The silhouette is now derived from
# the signature so species cannot converge on one body plan.
PROMPT_VERSION = 5

# Kingdom value that marks a human visitor. Humans get their own prompt branch.
HUMAN_KINGDOM = "Humana"

# --- Kingdom -> overall form ---------------------------------------------
# Rounded and readable, but not friendly. These are organisms under study, not
# pets: the taxonomy is the joke, the creature should look like it is watching.
_KINGDOM_FORM: dict[str, str] = {
    "Machina": "a small robot organism of uncertain origin",
    "Humana": "a solitary person",
    "Dubia": "a soft, cloud-like organism",
}
_KINGDOM_DEFAULT = "a soft, cloud-like organism"

# --- Phylum -> body plan -------------------------------------------------
# Deliberately COUNT-FREE: limb and eye counts come from the signature-derived
# morphology, so a phylum that also specified "four arms" would contradict it.
# Phylum describes the arrangement; morphology supplies the numbers.
_PHYLUM_BODY: dict[str, str] = {
    "Agentia": "a tool-bearing frame with manipulators mounted on a central hub",
    "Crawlera": "a plump low frame built for indexing, with sensor eyes set wide",
    "Browsera": "a rounded helmet-like head mounted on a small chassis",
    "Clientia": "a chunky geometric chassis",
    "Hominidae": "a small human body plan",
    "Incerta": "a wobbly, soft-edged outline",
}
_PHYLUM_DEFAULT = "a wobbly, soft-edged outline"

# --- Class -> material / texture -----------------------------------------
_CLASS_MATERIAL: dict[str, str] = {
    "LlmAgentia": "pearlescent chitin, faintly translucent and lit from within",
    "IndexCrawlera": "layered felt and paper, dry and fibrous",
    "AutomataBrowsera": "smooth frosted glass over something darker",
    "ScriptaClientia": "polished enamel with hard edges",
    "Sapiena": "soft skin and hair",
    "Incerta": "loose cotton-like fibre",
}
_CLASS_DEFAULT = "loose cotton-like fibre"

# --- Signature -> morphology ---------------------------------------------
# Kingdom/Phylum/Class are shared by most machine species, so without this
# every agent would share one silhouette and differ only in colour.
#
# Each trait is drawn INDEPENDENTLY from its own digest byte, so the traits
# combine multiplicatively rather than moving together. A single draw would
# give 8 body plans; independent draws give 8 x 7 x 6 x 6 x 5 = 10,080
# distinct morphologies, which is what makes species read as different
# creatures rather than recolours.
#
# Derived from the signature, so a species keeps its anatomy forever.
_BODY_SHAPE: tuple[str, ...] = (
    "a tall narrow body",
    "a low wide body, almost crouched",
    "an asymmetrical body, one side heavier than the other",
    "a compact dense body under a thick carapace",
    "a bulbous body with a swollen translucent abdomen",
    "an angular faceted body, like cut stone",
    "a smooth serpentine body with no visible joints",
    "a segmented body of stacked rings",
)

# (count phrase, limb description). Counts are deliberately odd and specific:
# "three arms" reads as a different animal than "four arms".
_LIMBS: tuple[tuple[str, str], ...] = (
    ("no arms at all", "no arms at all"),
    ("a single arm", "a single long arm ending in a cluster of fine manipulators"),
    ("two arms", "two long arms ending in three-fingered hands"),
    ("three arms", "three thin arms of unequal length"),
    ("four arms", "four short arms ending in fine manipulators"),
    ("six arms", "six spindly arms fringing the body"),
    ("a fringe of many small arms", "a fringe of many small arms along its underside"),
)

_LEGS: tuple[tuple[str, str], ...] = (
    ("no legs, resting on a flat base", "no legs, resting on a flat base"),
    ("two legs", "two thick legs"),
    ("three legs", "three thin jointed legs"),
    ("four legs", "four stubby legs"),
    ("six legs", "six insect-like legs"),
    ("many legs", "a centipede-like row of many small legs"),
    ("wheels instead of legs", "two small wheels instead of legs"),
    ("a single coiled tail instead of legs", "a single coiled tail it balances on"),
)

_EYES: tuple[str, ...] = (
    "no eyes at all, only a smooth sensor plate",
    "a single large central eye",
    "two small close-set eyes",
    "three eyes in a triangle",
    "four eyes in a row",
    "five eyes scattered unevenly",
    "a cluster of many small bead-like eyes",
    "two eyes on short stalks",
)

_LOCOMOTION: tuple[str, ...] = (
    "standing still",
    "mid-stride",
    "hovering slightly off the ground",
    "coiled and ready to spring",
    "clinging to a surface",
)

_BODY_DEFAULT = _BODY_SHAPE[0]
_LIMBS_DEFAULT = _LIMBS[4][1]
_LEGS_DEFAULT = _LEGS[3][1]
_EYES_DEFAULT = _EYES[2]
_LOCOMOTION_DEFAULT = _LOCOMOTION[0]

# --- Humans -------------------------------------------------------------
# A person is not a creature: limb/eye counts and carapaces read as nonsense on
# a human. Humans get their own trait set, drawn from the same signature, so
# each human species is a recognisably different KIND of person rather than a
# generic figure. The archetypes are deliberately unglamorous — this is a
# honeypot, and the humans who show up are the ones who poke at robots.
_HUMAN_PERSONA: tuple[str, ...] = (
    "a research scientist in the middle of an experiment",
    "a data analyst surrounded by dashboards",
    "a basement-dwelling gamer mid-session",
    "a sysadmin who has not slept properly",
    "a graduate student running out of funding",
    "a security researcher taking notes",
    "a hobbyist tinkerer with a soldering iron",
    "a night-shift operator watching a wall of screens",
    "a librarian of obscure datasets",
    "a self-taught programmer debugging at 3am",
)

_HUMAN_BUILD: tuple[str, ...] = (
    "lanky and slightly stooped",
    "short and round",
    "tall and gaunt",
    "average build, hunched over a keyboard",
    "wiry and restless",
    "broad and heavy-set",
)

_HUMAN_ATTIRE: tuple[str, ...] = (
    "a rumpled lab coat over a band t-shirt",
    "a hoodie with the hood up",
    "a cardigan and thick-rimmed glasses",
    "a worn flannel shirt with rolled sleeves",
    "a faded company polo shirt",
    "a bathrobe over pyjamas",
    "a fleece vest with too many pockets",
    "a plain t-shirt and cargo trousers",
)

_HUMAN_PROPS: tuple[str, ...] = (
    "holding a mug of coffee that has gone cold",
    "surrounded by tangled cables",
    "with a laptop tucked under one arm",
    "wearing headphones around the neck",
    "with a mechanical keyboard within reach",
    "with a stack of printed papers",
    "with a phone in one hand and a pen in the other",
    "with sticky notes stuck to everything nearby",
)

_HUMAN_SETTING: tuple[str, ...] = (
    "in a cluttered home office",
    "in a dim basement lit only by monitors",
    "in a university lab",
    "at a standing desk",
    "in a server room humming with fans",
    "in a small apartment kitchen converted into a workspace",
)

_HUMAN_PERSONA_DEFAULT = _HUMAN_PERSONA[0]
_HUMAN_BUILD_DEFAULT = _HUMAN_BUILD[0]
_HUMAN_ATTIRE_DEFAULT = _HUMAN_ATTIRE[0]
_HUMAN_PROPS_DEFAULT = _HUMAN_PROPS[0]
_HUMAN_SETTING_DEFAULT = _HUMAN_SETTING[0]

# Diagnostic characters -> HUMAN props. The creature rules produce things like
# "a smooth blank visor where a face should be" and "extra eyes along its
# brow", which on a person reads as a monster rather than a researcher.
_HUMAN_ACCESSORY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("headless", "webdriver", "swiftshader", "llvmpipe"), "a webcam covered with a strip of tape"),
    (("trap",), "a notebook of scribbled URLs"),
    (("confess", "free-text", "account of its own"), "a half-written message on the screen behind them"),
    (("depth", "roam", "breadcrumb"), "a browser with far too many tabs open"),
    (("fast", "rapid", "interval"), "a keyboard worn smooth from use"),
    (("spoof", "sec-fetch"), "a second monitor angled away from view"),
    (("machine-discovery", "mcp", "openapi"), "a printed API specification on the desk"),
)

_HUMAN_ACCESSORY_DEFAULT = "a distracted, faintly suspicious expression"


def human_accessories_for(diagnostic_characters: list[str]) -> str:
    """Human props derived from diagnostic characters. Deterministic."""
    haystack = " ".join(diagnostic_characters).lower()
    found: list[str] = []
    for needles, accessory in _HUMAN_ACCESSORY_RULES:
        if accessory in found:
            continue
        if any(needle in haystack for needle in needles):
            found.append(accessory)
    if not found:
        # Capitalised: this clause starts a sentence in _HUMAN_TEMPLATE.
        return _HUMAN_ACCESSORY_DEFAULT[:1].upper() + _HUMAN_ACCESSORY_DEFAULT[1:]
    if len(found) == 1:
        return f"They have {found[0]}"
    return "They have " + ", ".join(found[:-1]) + f", and {found[-1]}"

# --- Order -> palette ----------------------------------------------------
# Saturated, cheerful colours. Each vendor gets a distinct, recognisable hue
# family so species are easy to tell apart at a glance.
_ORDER_PALETTE: dict[str, str] = {
    "OpenAI": "vivid emerald green with cream and gold accents",
    "Anthropic": "warm coral, peach, and terracotta",
    "Google": "bright primary blue, red, yellow, and green",
    "Python": "sunny yellow and royal blue",
    "curl": "soft silver and sky blue",
    "Scrapy": "fresh olive green and mustard",
    "Chromium": "electric cyan and chrome with magenta highlights",
    "Perplexity": "turquoise and mint",
    "Meta": "violet and indigo with pink accents",
    "Microsoft": "azure blue and lime green",
    "Apple": "rose pink and pearl white",
    "Mozilla": "orange and deep purple",
    "Amazon": "amber and teal",
    "ByteDance": "hot pink and black",
    "CommonCrawl": "warm sand and rust",
    "Node.js": "lime green and charcoal",
    "Go": "bright cyan and white",
    "Square": "crimson and cream",
    "Apache": "scarlet and gold",
    "Postman": "vivid orange and navy",
}
_ORDER_DEFAULT = "a cheerful rainbow of pastel colours"

# --- Family -> markings --------------------------------------------------
# A short distinguishing mark per known family. Unknown families fall back to a
# deterministic mark derived from the family name, so every family differs.
_FAMILY_MARKING: dict[str, str] = {
    "GPTBot": "a spiral sigil on the brow",
    "OAI-SearchBot": "a magnifying-glass sigil on the brow",
    "ChatGPT-User": "a speech-bubble sigil on the brow",
    "ClaudeBot": "a radial sunburst sigil on the brow",
    "Claude-User": "a small crescent sigil on the brow",
    "Claude-SearchBot": "a compass sigil on the brow",
    "PerplexityBot": "a knotwork sigil on the brow",
    "Google-Extended": "a four-colour chevron on the brow",
    "Googlebot": "a four-colour chevron on the brow",
    "Applebot-Extended": "a bitten-fruit sigil on the brow",
    "python-requests": "a coiled serpent sigil on the brow",
    "python-httpx": "a paired-arrow sigil on the brow",
    "httpx": "a paired-arrow sigil on the brow",
    "aiohttp": "a wave sigil on the brow",
    "curl": "a curled-horn sigil on the brow",
    "wget": "a downward-arrow sigil on the brow",
    "Scrapy": "a web sigil on the brow",
    "HeadlessChrome": "a blank oval where a face should be",
    "Chrome": "a smooth unmarked brow",
    "Firefox": "a flame sigil on the brow",
    "Safari": "a compass-needle sigil on the brow",
    "Edge": "a wave-crest sigil on the brow",
    "Go-http-client": "a gopher sigil on the brow",
    "node-fetch": "a hexagon sigil on the brow",
    "undici": "a hexagon sigil on the brow",
    "axios": "a hexagon sigil on the brow",
}

# --- Species -> pattern --------------------------------------------------
# Deterministic pattern chosen from the species epithet's first letter, so two
# species in the same family still differ.
_SPECIES_PATTERNS: tuple[str, ...] = (
    "fine concentric rings",
    "a scatter of small dots",
    "narrow vertical striations",
    "a faint hexagonal lattice",
    "soft mottled patches",
    "thin diagonal hatching",
    "a single broad band",
    "delicate branching veins",
)

# --- Genus -> posture / expression ---------------------------------------
_GENUS_POSTURE: dict[str, str] = {
    "Manifestus": "standing proudly, watchful and unreadable",
    "Furtim": "peeking from behind its own hands",
    "Loqualis": "chattering with a wide open mouth",
    "Curiosus": "leaning forward with bright inquisitive eyes",
    "Volans": "stretching upward with a long segmented tail",
    "Rapidus": "mid-hop with faint motion trails",
    "Sedens": "sitting comfortably, perfectly still",
    "Sapiens": "in a relaxed natural stance",
    "Ignotus": "tilting its head curiously",
}
_GENUS_DEFAULT = "tilting its head curiously"

# --- Diagnostic characters -> accessories --------------------------------
# Matched case-insensitively as substrings against each diagnostic character.
_ACCESSORY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("headless", "webdriver", "swiftshader", "llvmpipe"), "a smooth blank visor where a face should be"),
    (("trap",), "a few extra eyes along its brow"),
    (("confess", "free-text", "account of its own"), "a thin speech bubble floating beside it"),
    (("depth", "roam", "breadcrumb"), "a long segmented tail"),
    (("fast", "rapid", "interval"), "faint motion trails around its feet"),
    (("spoof", "sec-fetch"), "a slightly-too-large borrowed shell"),
    (("machine-discovery", "mcp", "openapi"), "a small brass key on a chain"),
)

_ACCESSORY_DEFAULT = "a calm, unreadable expression"

_TEMPLATE = (
    "A creature illustration for a field guide to machine life, rendered as a "
    "luminous scientific plate. The creature is {form} with {body_shape}, "
    "built as {body_plan}. It has {limbs} and {legs}, and {eyes}. "
    "Its surface is {material}. "
    "Its palette is {palette}, lit by a single vivid accent. It is marked with "
    "{markings} and patterned with {pattern}. It is {locomotion}, {posture}. "
    "{accessories} "
    "Rounded, readable silhouette with an unsettling edge: joints in the wrong "
    "places, an expression that gives nothing away. Fine ink linework over deep "
    "shadow, bioluminescent highlights, soft volumetric glow, rich saturated "
    "colour against darkness. Centered, full body, three-quarter view, dark "
    "atmospheric background, no text, no border, no frame. "
    "Style: speculative-naturalist illustration, elegant and quietly alien, "
    "beautiful rather than frightening."
)

# Humans get their own template: no carapaces, no limb counts, no sensor eyes.
# Same plate style, so a person still belongs in the same book as the machines.
_HUMAN_TEMPLATE = (
    "A portrait for a field guide to machine life, rendered as a luminous "
    "scientific plate. The subject is {persona}: a person, {human_build}, "
    "wearing {attire}, {props}, {setting}. "
    "Their palette is {palette}, lit by a single vivid accent. {accessories}. "
    "Ordinary and specific rather than idealised: tired eyes, real posture, "
    "clothing that has been worn too long. Fine ink linework over deep shadow, "
    "soft volumetric glow, rich saturated colour against darkness. Centered, "
    "full body, three-quarter view, dark atmospheric background, no text, no "
    "border, no frame. Style: speculative-naturalist illustration, elegant and "
    "quietly observed, never a caricature."
)


def _rank(taxonomy: Any, *names: str) -> str:
    """Read a rank from a Taxonomy, a dict, or a SpeciesRecord-like object."""
    for name in names:
        if isinstance(taxonomy, dict):
            value = taxonomy.get(name)
        else:
            value = getattr(taxonomy, name, None)
        if value:
            return str(value)
    return ""


def _taxon_class(taxonomy: Any) -> str:
    """``Class`` is a Python keyword, so the dataclass calls it ``taxon_class``."""
    return _rank(taxonomy, "taxon_class", "class_", "class")


def _diagnostic_characters(taxonomy: Any) -> list[str]:
    if isinstance(taxonomy, dict):
        raw = taxonomy.get("diagnostic_characters") or []
    else:
        raw = getattr(taxonomy, "diagnostic_characters", None) or []
    return [str(c) for c in raw if c]


def accessories_for(diagnostic_characters: list[str]) -> str:
    """Map diagnostic characters to a short accessory clause.

    Deterministic: rules are evaluated in a fixed order and each accessory is
    emitted at most once, so the same characters always produce the same text.
    """
    haystack = " ".join(diagnostic_characters).lower()
    found: list[str] = []
    for needles, accessory in _ACCESSORY_RULES:
        if accessory in found:
            continue
        if any(needle in haystack for needle in needles):
            found.append(accessory)
    if not found:
        return _ACCESSORY_DEFAULT
    if len(found) == 1:
        return f"It bears {found[0]}."
    return "It bears " + ", ".join(found[:-1]) + f", and {found[-1]}."


def marking_for(family: str) -> str:
    """Distinguishing brow mark for a family.

    Known families use a curated mark; unknown families get a deterministic
    mark derived from the name so no two families collide.
    """
    if not family:
        return "no distinguishing mark"
    known = _FAMILY_MARKING.get(family)
    if known:
        return known
    # Deterministic fallback: pick a pattern slot from the name's hash.
    index = sum(ord(c) for c in family) % len(_SPECIES_PATTERNS)
    return f"a {family.lower()} glyph on the brow ({_SPECIES_PATTERNS[index]})"


def pattern_for(species: str) -> str:
    """Deterministic body pattern derived from the species epithet."""
    if not species:
        return _SPECIES_PATTERNS[0]
    index = sum(ord(c) for c in species) % len(_SPECIES_PATTERNS)
    return _SPECIES_PATTERNS[index]


def _digest(signature: str) -> bytes:
    """Stable 32-byte digest of a signature.

    A real digest rather than a character sum: a sum collides for signatures
    that differ only by permutation, which is exactly the case we must
    separate. ``hashlib`` is used instead of ``hash()`` because ``hash()`` is
    salted per process and would change the art between runs.
    """
    return hashlib.sha256(signature.encode("utf-8")).digest()


def morphology_for(signature: str) -> dict[str, str]:
    """Deterministic anatomy for one species, drawn from its signature.

    Each trait reads a DIFFERENT byte of the digest, so the traits are
    independent: a species with six arms is not thereby more likely to have
    many eyes. That independence is what produces genuinely different
    creatures instead of a handful of recoloured ones.
    """
    if not signature:
        return {
            "body_shape": _BODY_DEFAULT,
            "limbs": _LIMBS_DEFAULT,
            "legs": _LEGS_DEFAULT,
            "eyes": _EYES_DEFAULT,
            "locomotion": _LOCOMOTION_DEFAULT,
        }
    d = _digest(signature)
    return {
        "body_shape": _BODY_SHAPE[d[0] % len(_BODY_SHAPE)],
        "limbs": _LIMBS[d[1] % len(_LIMBS)][1],
        "legs": _LEGS[d[2] % len(_LEGS)][1],
        "eyes": _EYES[d[3] % len(_EYES)],
        "locomotion": _LOCOMOTION[d[4] % len(_LOCOMOTION)],
    }


def build_for(signature: str) -> str:
    """Backwards-compatible alias for the body-shape trait."""
    return morphology_for(signature)["body_shape"]


def human_for(signature: str) -> dict[str, str]:
    """Deterministic persona for a human species, drawn from its signature.

    Reads different digest bytes per trait, so persona, build, attire, props and
    setting vary independently — two humans are unlikely to be the same person.
    """
    if not signature:
        return {
            "persona": _HUMAN_PERSONA_DEFAULT,
            "human_build": _HUMAN_BUILD_DEFAULT,
            "attire": _HUMAN_ATTIRE_DEFAULT,
            "props": _HUMAN_PROPS_DEFAULT,
            "setting": _HUMAN_SETTING_DEFAULT,
        }
    d = _digest(signature)
    return {
        "persona": _HUMAN_PERSONA[d[5] % len(_HUMAN_PERSONA)],
        "human_build": _HUMAN_BUILD[d[6] % len(_HUMAN_BUILD)],
        "attire": _HUMAN_ATTIRE[d[7] % len(_HUMAN_ATTIRE)],
        "props": _HUMAN_PROPS[d[8] % len(_HUMAN_PROPS)],
        "setting": _HUMAN_SETTING[d[9] % len(_HUMAN_SETTING)],
    }


def build_prompt(taxonomy: Any) -> str:
    """Render the versioned prompt for one species. Pure and deterministic."""
    kingdom = _rank(taxonomy, "kingdom")
    phylum = _rank(taxonomy, "phylum")
    klass = _taxon_class(taxonomy)
    order = _rank(taxonomy, "order")
    family = _rank(taxonomy, "family")
    genus = _rank(taxonomy, "genus")
    species = _rank(taxonomy, "species")

    signature = _rank(taxonomy, "signature")
    palette = _ORDER_PALETTE.get(order, _ORDER_DEFAULT)
    accessories = accessories_for(_diagnostic_characters(taxonomy))

    if kingdom == HUMAN_KINGDOM:
        return _HUMAN_TEMPLATE.format(
            palette=palette,
            accessories=human_accessories_for(_diagnostic_characters(taxonomy)),
            **human_for(signature),
        )

    morph = morphology_for(signature)
    return _TEMPLATE.format(
        form=_KINGDOM_FORM.get(kingdom, _KINGDOM_DEFAULT),
        body_shape=morph["body_shape"],
        body_plan=_PHYLUM_BODY.get(phylum, _PHYLUM_DEFAULT),
        limbs=morph["limbs"],
        legs=morph["legs"],
        eyes=morph["eyes"],
        locomotion=morph["locomotion"],
        material=_CLASS_MATERIAL.get(klass, _CLASS_DEFAULT),
        palette=palette,
        markings=marking_for(family),
        pattern=pattern_for(species),
        posture=_GENUS_POSTURE.get(genus, _GENUS_DEFAULT),
        accessories=accessories,
    )


def describe(taxonomy: Any) -> dict[str, str]:
    """The individual visual attributes, for debugging and the CLI summary."""
    kingdom = _rank(taxonomy, "kingdom")
    phylum = _rank(taxonomy, "phylum")
    klass = _taxon_class(taxonomy)
    order = _rank(taxonomy, "order")
    genus = _rank(taxonomy, "genus")
    signature = _rank(taxonomy, "signature")
    described = {
        "form": _KINGDOM_FORM.get(kingdom, _KINGDOM_DEFAULT),
        "body_plan": _PHYLUM_BODY.get(phylum, _PHYLUM_DEFAULT),
        "material": _CLASS_MATERIAL.get(klass, _CLASS_DEFAULT),
        "palette": _ORDER_PALETTE.get(order, _ORDER_DEFAULT),
        "posture": _GENUS_POSTURE.get(genus, _GENUS_DEFAULT),
        "accessories": accessories_for(_diagnostic_characters(taxonomy)),
    }
    if kingdom == HUMAN_KINGDOM:
        described.update(human_for(signature))
    else:
        described.update(morphology_for(signature))
    return described
