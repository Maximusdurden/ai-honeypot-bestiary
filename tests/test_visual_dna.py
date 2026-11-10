"""Visual DNA: determinism and complete rank coverage."""

from __future__ import annotations

import pytest

from bestiary import visual_dna
from bestiary.taxonomy import classify_species


def _tax(**kw):
    base = dict(
        agent_family="python-requests",
        agent_kind="http",
        score=60,
        verdict="likely_agent",
    )
    base.update(kw)
    return classify_species(**base)


def test_prompt_is_deterministic():
    tax = _tax()
    assert visual_dna.build_prompt(tax) == visual_dna.build_prompt(tax)


def test_prompt_is_deterministic_across_instances():
    a = _tax()
    b = _tax()
    assert a.signature == b.signature
    assert visual_dna.build_prompt(a) == visual_dna.build_prompt(b)


def test_prompt_has_no_none_leaks():
    prompt = visual_dna.build_prompt(_tax())
    assert "None" not in prompt
    assert "{" not in prompt
    assert "}" not in prompt


def test_prompt_accepts_dict_input():
    tax = _tax()
    as_dict = {
        "signature": tax.signature,
        "kingdom": tax.kingdom,
        "phylum": tax.phylum,
        "taxon_class": tax.taxon_class,
        "order": tax.order,
        "family": tax.family,
        "genus": tax.genus,
        "species": tax.species,
        "diagnostic_characters": tax.diagnostic_characters,
    }
    assert visual_dna.build_prompt(as_dict) == visual_dna.build_prompt(tax)


def test_prompt_version_is_positive_int():
    assert isinstance(visual_dna.PROMPT_VERSION, int)
    assert visual_dna.PROMPT_VERSION >= 1


@pytest.mark.parametrize(
    "kingdom,expected",
    [
        ("Machina", "robot"),
        ("Humana", "person"),
        ("Dubia", "cloud-like"),
    ],
)
def test_every_kingdom_maps(kingdom, expected):
    prompt = visual_dna.build_prompt({"kingdom": kingdom})
    assert expected in prompt


@pytest.mark.parametrize(
    "phylum,expected",
    [
        ("Agentia", "manipulators"),
        ("Crawlera", "indexing"),
        ("Browsera", "helmet-like head"),
        ("Clientia", "geometric chassis"),
        ("Hominidae", "human body plan"),
        ("Incerta", "soft-edged"),
    ],
)
def test_every_phylum_maps(phylum, expected):
    assert expected in visual_dna.build_prompt({"phylum": phylum})


@pytest.mark.parametrize(
    "klass,expected",
    [
        ("LlmAgentia", "pearlescent"),
        ("IndexCrawlera", "felt"),
        ("AutomataBrowsera", "frosted glass"),
        ("ScriptaClientia", "enamel"),
        ("Sapiena", "soft skin"),
        ("Incerta", "cotton"),
    ],
)
def test_every_class_maps(klass, expected):
    assert expected in visual_dna.build_prompt({"taxon_class": klass})


@pytest.mark.parametrize(
    "order,expected",
    [
        ("OpenAI", "emerald"),
        ("Anthropic", "coral"),
        ("Google", "yellow"),
        ("Python", "royal blue"),
        ("curl", "silver"),
        ("Scrapy", "olive"),
        ("Chromium", "cyan"),
        ("Perplexity", "turquoise"),
        ("Meta", "violet"),
    ],
)
def test_every_order_maps(order, expected):
    assert expected in visual_dna.build_prompt({"order": order})


def test_unknown_order_falls_back_to_pastel():
    assert "pastel" in visual_dna.build_prompt({"order": "Nonexistent"})


@pytest.mark.parametrize(
    "genus,expected",
    [
        ("Manifestus", "proudly"),
        ("Furtim", "peeking"),
        ("Loqualis", "chattering"),
        ("Curiosus", "leaning forward"),
        ("Volans", "stretching upward"),
        ("Rapidus", "mid-hop"),
        ("Sedens", "sitting comfortably"),
        ("Sapiens", "natural stance"),
        ("Ignotus", "tilting its head"),
    ],
)
def test_every_genus_maps(genus, expected):
    assert expected in visual_dna.build_prompt({"genus": genus})


def test_accessories_from_diagnostic_characters():
    prompt = visual_dna.build_prompt(
        {"diagnostic_characters": ["Exhibited headless-browser tells"]}
    )
    assert "blank visor" in prompt


def test_accessories_default_when_no_characters():
    assert "unreadable expression" in visual_dna.build_prompt({})


def test_accessories_are_deterministic_and_deduplicated():
    chars = ["Requested a trap path", "Exhibited headless-browser tells"]
    first = visual_dna.accessories_for(chars)
    assert first == visual_dna.accessories_for(list(reversed(chars)))
    assert first.count("blank visor") == 1


def test_describe_covers_every_attribute():
    described = visual_dna.describe(_tax())
    assert set(described) == {
        "form",
        "body_shape",
        "body_plan",
        "limbs",
        "legs",
        "eyes",
        "locomotion",
        "material",
        "palette",
        "posture",
        "accessories",
    }
    assert all(isinstance(v, str) and v for v in described.values())


# ------------------------------------------------------------- morphology
def test_morphology_is_deterministic():
    sig = "91d3ed6e2ef7ed62"
    assert visual_dna.morphology_for(sig) == visual_dna.morphology_for(sig)


def test_morphology_handles_empty_signature():
    morph = visual_dna.morphology_for("")
    assert morph["body_shape"] == visual_dna._BODY_DEFAULT
    assert morph["limbs"] == visual_dna._LIMBS_DEFAULT


def test_every_trait_value_is_reachable():
    """Each trait must actually vary, not silently collapse to one value."""
    sigs = ["%016x" % i for i in range(4000)]
    morphs = [visual_dna.morphology_for(s) for s in sigs]
    assert len({m["body_shape"] for m in morphs}) == len(visual_dna._BODY_SHAPE)
    assert len({m["limbs"] for m in morphs}) == len(visual_dna._LIMBS)
    assert len({m["legs"] for m in morphs}) == len(visual_dna._LEGS)
    assert len({m["eyes"] for m in morphs}) == len(visual_dna._EYES)
    assert len({m["locomotion"] for m in morphs}) == len(visual_dna._LOCOMOTION)


def test_traits_are_independent():
    """Traits must not move together, or species become recolours.

    If the traits were drawn from one byte, every species with six arms would
    also share the same eye count. Check that the combination space is large.
    """
    sigs = ["%016x" % i for i in range(4000)]
    combos = {
        tuple(visual_dna.morphology_for(s).values()) for s in sigs
    }
    assert len(combos) > 1000


def test_morphology_differs_for_similar_signatures():
    """Signatures differing by one character must not share anatomy."""
    a = visual_dna.morphology_for("aaaaaaaaaaaaaaaa")
    b = visual_dna.morphology_for("aaaaaaaabaaaaaaa")
    assert a != b


def test_build_for_is_the_body_shape_trait():
    sig = "c1e1cc6913ad64da"
    assert visual_dna.build_for(sig) == visual_dna.morphology_for(sig)["body_shape"]


def test_species_sharing_ranks_still_differ_by_signature():
    """Two species identical in every rank must still get distinct prompts."""
    base = {
        "kingdom": "Machina",
        "phylum": "Agentia",
        "taxon_class": "LlmAgentia",
        "order": "OpenAI",
        "family": "GPTBot",
        "genus": "Manifestus",
        "species": "gptbotensis",
    }
    a = visual_dna.build_prompt({**base, "signature": "aaaaaaaaaaaaaaaa"})
    b = visual_dna.build_prompt({**base, "signature": "bbbbbbbbbbbbbbbb"})
    assert a != b


def test_prompt_is_not_over_cute():
    """Guard the v4 midpoint: no chibi/adorable wording may creep back in."""
    prompt = visual_dna.build_prompt(_tax()).lower()
    for banned in ("chibi", "adorable", "cute", "wholesome", "not scary"):
        assert banned not in prompt


def test_prompt_keeps_an_unsettling_edge():
    prompt = visual_dna.build_prompt(_tax()).lower()
    assert "unsettling" in prompt
    assert "alien" in prompt


# ------------------------------------------------------------------ humans
def _human_tax(**kw):
    base = dict(
        agent_family="Chrome",
        agent_kind="browser",
        score=26,
        verdict="likely_human",
    )
    base.update(kw)
    return classify_species(**base)


def test_human_prompt_describes_a_person():
    prompt = visual_dna.build_prompt(_human_tax())
    assert "a person" in prompt
    assert "portrait" in prompt.lower()


def test_human_prompt_has_no_creature_anatomy():
    """A person must not be described with carapaces or sensor eyes."""
    prompt = visual_dna.build_prompt(_human_tax()).lower()
    for banned in (
        "carapace",
        "sensor eyes",
        "manipulators",
        "abdomen",
        "chitin",
        "stubby legs",
        "centipede",
    ):
        assert banned not in prompt


def test_human_prompt_uses_human_props_not_creature_features():
    tax = _human_tax(reasons=["+30 navigator.webdriver is true"])
    prompt = visual_dna.build_prompt(tax).lower()
    assert "webcam covered with a strip of tape" in prompt
    assert "blank visor" not in prompt
    assert "extra eyes" not in prompt


def test_human_persona_is_deterministic():
    tax = _human_tax()
    assert visual_dna.human_for(tax.signature) == visual_dna.human_for(tax.signature)


def test_human_personas_vary_across_signatures():
    personas = {
        visual_dna.human_for("%016x" % i)["persona"] for i in range(2000)
    }
    assert len(personas) == len(visual_dna._HUMAN_PERSONA)


def test_human_traits_are_independent():
    combos = {
        tuple(visual_dna.human_for("%016x" % i).values()) for i in range(2000)
    }
    assert len(combos) > 500


def test_human_prompt_sentences_are_capitalised():
    """The accessories clause starts a sentence, so it must not be lowercase."""
    prompt = visual_dna.build_prompt(_human_tax())
    for sentence in prompt.split(". "):
        stripped = sentence.strip()
        if stripped:
            assert stripped[0].isupper(), f"lowercase sentence start: {stripped[:40]}"


def test_describe_uses_human_traits_for_humans():
    described = visual_dna.describe(_human_tax())
    assert "persona" in described
    assert "attire" in described
    assert "limbs" not in described


def test_different_species_differ_in_prompt():
    a = _tax(agent_family="GPTBot", agent_kind="ai", score=90)
    b = _tax(agent_family="python-requests", agent_kind="http", score=60)
    assert visual_dna.build_prompt(a) != visual_dna.build_prompt(b)
