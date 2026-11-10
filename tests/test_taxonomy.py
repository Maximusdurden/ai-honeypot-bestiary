"""Taxonomic classification."""

from __future__ import annotations

from bestiary.taxonomy import classify_species, conservation_status, latinize


def test_latinize_basic():
    assert latinize("GPTBot") == "gptbotensis"
    assert latinize("ClaudeBot") == "claudebotensis"
    # trailing 's' is stripped so the epithet does not double up
    assert latinize("python-requests") == "pyrequestensis"
    assert latinize("curl") == "curlensis"
    assert latinize(None) == "incognita"
    assert latinize("") == "incognita"


def test_latinize_vowel_ending():
    # 'y' is not in the vowel set, so it takes the plain -ensis suffix
    assert latinize("Scrapy") == "scrapyensis"
    # a true vowel ending takes -nsis
    assert latinize("Opera") == "operansis"


def test_declared_ai_crawler_is_manifestus():
    t = classify_species(
        agent_family="GPTBot",
        agent_kind="ai",
        score=86,
        verdict="agent",
    )
    assert t.kingdom == "Machina"
    assert t.phylum == "Agentia"
    assert t.taxon_class == "LlmAgentia"
    assert t.order == "OpenAI"
    assert t.family == "GPTBot"
    assert t.genus == "Manifestus"
    assert t.binomial == "Manifestus gptbotensis"
    assert t.common_name == "Declared GPTBot"


def test_confession_beats_declaration():
    """A visitor that confesses is Loqualis even if it declared itself."""
    t = classify_species(
        agent_family="GPTBot",
        agent_kind="ai",
        score=90,
        verdict="agent",
        interrogation=[{"framework": "LangChain"}],
    )
    assert t.genus == "Loqualis"
    assert t.binomial == "Loqualis gptbotensis"


def test_machine_endpoint_prober_is_curiosus():
    t = classify_species(
        agent_family="python-httpx",
        agent_kind="http",
        score=80,
        verdict="agent",
        paths=["/mcp", "/"],
    )
    assert t.genus == "Curiosus"
    assert t.order == "Python"


def test_headless_browser_is_furtim():
    t = classify_species(
        agent_family="Chrome",
        agent_kind="browser",
        score=70,
        verdict="likely_agent",
        probe={"webdriver": True, "webgl_renderer": "Google SwiftShader"},
    )
    assert t.genus == "Furtim"
    assert t.phylum == "Browsera"
    assert t.taxon_class == "AutomataBrowsera"


def test_deep_roamer_is_volans():
    t = classify_species(
        agent_family="Scrapy",
        agent_kind="crawler",
        score=60,
        verdict="likely_agent",
        max_depth=8,
    )
    assert t.genus == "Volans"
    assert t.phylum == "Crawlera"


def test_fast_mover_is_rapidus():
    t = classify_species(
        agent_family="curl",
        agent_kind="http",
        score=55,
        verdict="likely_agent",
        max_depth=2,
        min_interval_ms=40,
    )
    assert t.genus == "Rapidus"


def test_shallow_visitor_is_sedens():
    t = classify_species(
        agent_family="curl",
        agent_kind="http",
        score=50,
        verdict="likely_agent",
        max_depth=0,
        min_interval_ms=5000,
    )
    assert t.genus == "Sedens"


def test_human_is_humana():
    t = classify_species(
        agent_family="Chrome",
        agent_kind="browser",
        score=5,
        verdict="human",
    )
    assert t.kingdom == "Humana"
    assert t.phylum == "Hominidae"
    assert t.taxon_class == "Sapiena"
    # Humans must not be given a machine-behaviour genus.
    assert t.genus == "Sapiens"
    assert t.binomial == "Sapiens chromensis"
    assert t.common_name == "Ordinary Chrome"


def test_unknown_is_dubia():
    t = classify_species(
        agent_family=None,
        agent_kind="unknown",
        score=15,
        verdict="likely_human",
    )
    # likely_human maps to Humana; a truly unknown verdict maps to Dubia
    t2 = classify_species(
        agent_family=None,
        agent_kind="unknown",
        score=0,
        verdict="unknown",
    )
    assert t2.kingdom == "Dubia"
    assert t2.phylum == "Incerta"


def test_signature_is_stable_and_distinct():
    a = classify_species(agent_family="GPTBot", agent_kind="ai", score=80, verdict="agent")
    b = classify_species(agent_family="GPTBot", agent_kind="ai", score=80, verdict="agent")
    c = classify_species(agent_family="ClaudeBot", agent_kind="ai", score=80, verdict="agent")
    assert a.signature == b.signature
    assert a.signature != c.signature
    assert len(a.signature) == 16


def test_diagnostic_characters_are_cleaned():
    t = classify_species(
        agent_family="python-requests",
        agent_kind="http",
        score=80,
        verdict="agent",
        reasons=["+45 User-Agent is an HTTP library", "+8 Sends Connection header"],
    )
    assert "User-Agent is an HTTP library" in t.diagnostic_characters
    assert not any(c.startswith("+") for c in t.diagnostic_characters)


def test_conservation_status():
    assert conservation_status(1) == "Singular"
    assert conservation_status(2) == "Rare"
    assert conservation_status(5) == "Uncommon"
    assert conservation_status(20) == "Common"
    assert conservation_status(100) == "Abundant"


def test_ranks_are_ordered():
    t = classify_species(agent_family="GPTBot", agent_kind="ai", score=80, verdict="agent")
    names = [r for r, _ in t.ranks()]
    assert names == [
        "Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"
    ]
