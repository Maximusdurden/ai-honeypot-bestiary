"""Prompt uniqueness must be auditable before art exists.

QA found that ``prompt_text`` was empty for every species until art had been
generated, which made it impossible to detect a prompt collision without
spending money. The prompt is now computed on demand from the corpus, so a
collision is detectable for free.

The original version of this file drove a FastAPI test client. This package is
the interpretation layer and has no HTTP surface, so the same assertions now run
against records built directly from the synthetic corpus.
"""

from __future__ import annotations

from collections import Counter

from bestiary import visual_dna


def _prompts(species_records) -> list[tuple[str, str, int]]:
    """(binomial, prompt_text, prompt_version) for every species."""
    return [
        (rec.taxonomy.binomial, visual_dna.build_prompt(rec.taxonomy), visual_dna.PROMPT_VERSION)
        for rec in species_records
    ]


def test_prompt_text_is_populated_without_art(species_records):
    """A prompt must exist before a cent is spent on generation."""
    assert species_records, "fixture corpus produced no species"
    for rec in species_records:
        prompt = visual_dna.build_prompt(rec.taxonomy)
        assert prompt.strip(), f"{rec.taxonomy.binomial} has an empty prompt"
        # Long enough to be a real instruction, not a placeholder.
        assert len(prompt) > 200, f"{rec.taxonomy.binomial} prompt looks truncated"


def test_all_prompts_are_unique(species_records):
    prompts = _prompts(species_records)
    assert len(prompts) >= 3, "need several species to make this meaningful"

    counts = Counter(text for _, text, _ in prompts)
    duplicates = {t: n for t, n in counts.items() if n > 1}
    assert not duplicates, f"{len(duplicates)} prompt(s) shared by multiple species"


def test_same_genus_species_have_different_prompts(species_records):
    """Two declared AI crawlers share every rank above species.

    GPTBot and ClaudeBot are both ``Manifestus``, so their prompts differ only
    because the visual DNA is derived from the species signature. That is the
    property worth protecting: a shared genus must not mean a shared portrait.
    """
    manifestus = [r for r in species_records if r.taxonomy.genus == "Manifestus"]
    assert len(manifestus) >= 2, "corpus needs two Manifestus species"

    prompts = {r.taxonomy.binomial: visual_dna.build_prompt(r.taxonomy) for r in manifestus}
    assert len(set(prompts.values())) == len(prompts), (
        f"same-genus species share a prompt: {sorted(prompts)}"
    )


def test_prompt_version_is_reported(species_records):
    assert visual_dna.PROMPT_VERSION >= 1
    assert isinstance(visual_dna.PROMPT_VERSION, int)


def test_every_genus_appears_in_the_corpus(species_records):
    """The demo must visibly exercise the whole taxonomy.

    A public corpus that only shows ``Manifestus`` teaches a reader nothing about
    the classification scheme, so this is a fixture requirement, not a nicety.
    """
    expected = {
        "Curiosus", "Furtim", "Ignotus", "Loqualis", "Manifestus",
        "Rapidus", "Sedens", "Volans", "Sapiens",
    }
    seen = {r.taxonomy.genus for r in species_records}
    assert seen == expected, f"missing genera: {sorted(expected - seen)}"
