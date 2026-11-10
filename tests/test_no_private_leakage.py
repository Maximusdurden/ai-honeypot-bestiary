"""Guard: the public package must not leak the private deployment.

This is the most important test in the repo. The whole point of splitting the
honeypot into two packages is that the *capture* layer stays private while the
*interpretation* layer is publishable. That split is only real if something
fails loudly when private material creeps in.

The check is deliberately paranoid and file-oriented: it scans every tracked
source, doc, and data file for the exact kinds of strings that would constitute
a leak, and it also asserts that high-risk files are simply absent.

If you are adding a file and this test fails, do not add an allow-list entry
unless you are certain the string is generic. Most failures here are real.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files and directories that are never published.
SKIP_DIRS = {
    ".git", "venv", ".venv", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "build", "dist", "artifacts",
}

# Only scan text-ish files. Everything here is expected to be small.
SCAN_SUFFIXES = {".py", ".md", ".toml", ".cfg", ".ini", ".txt", ".json", ".yaml", ".yml"}

# --------------------------------------------------------------------------
# Patterns that must never appear.
# --------------------------------------------------------------------------
FORBIDDEN: list[tuple[str, str]] = [
    # Deployment identifiers are detected by *shape*, not by literal value.
    #
    # Hardcoding the real project IDs here would defeat the purpose: this file is
    # published, so listing them would leak exactly what it is meant to protect.
    # Shape matching also catches any future deployment, not just this one.
    (r"[a-z0-9-]*run\.app", "Cloud Run hostname"),
    # A persona-derived project id, e.g. `name-personal-sandbox`. This is a
    # shape, not a literal: it catches any project following that convention
    # without naming the real one in a published file.
    (r"[a-z0-9-]+-personal-sandbox", "persona-named GCP project id"),
    # A Cloud Run revision looks like `service-00019-fr9`. The bare service name
    # is fine; a numeric revision suffix is not.
    (r"\b[a-z][a-z0-9-]{3,}-\d{3,}-[a-z0-9]{3,}\b", "Cloud Run service revision"),
    # GCS bucket names are deployment-specific. The generic
    # `storage.googleapis.com` host is fine, and so is a one-hyphen placeholder
    # like `your-bucket`; a real project bucket has several hyphen segments.
    (
        r"storage\.googleapis\.com/[a-z0-9]+(?:-[a-z0-9]+){2,}",
        "GCS bucket object URL",
    ),
    # Credentials and webhooks.
    (r"discord(app)?\.com/api/webhooks", "Discord webhook URL"),
    (r"hooks\.slack\.com", "Slack webhook URL"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"sk-or-v1-[0-9a-f]{32,}", "OpenRouter API key"),
    (r"ghp_[0-9A-Za-z]{36}", "GitHub token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    # This project's own secrets, by name and by shape.
    #
    # The canary shape is `zqx-NNNN-word`. The lookahead skips an explicitly
    # illustrative placeholder so documentation can show the shape without
    # tripping the guard, while any realistic token still fails.
    (r"zqx-\d{4}-(?!example)[a-z]+", "tracking canary token"),
    (r"dev-insecure-key", "old hardcoded signing key"),
    (r"HONEYPOT_ADMIN_TOKEN\s*=\s*\S+", "admin token assignment"),
    (r"HONEYPOT_SECRET_KEY\s*=\s*\S+", "secret key assignment"),
    # Detector internals that would give away how scoring works. The public
    # package may *name* these concepts in prose, but not carry the tables.
    (r"SEC_FETCH_HEADER_ORDER", "header-order spoof detector"),
    (r"_HEADLESS_UA_PATTERNS", "headless UA pattern table"),
    (r"_SCORE_RULES", "per-request scoring rule table"),
    (r"_BOT_UA_LOOKUP", "user-agent classification table"),
]

# A 32+ char base64url-ish token assigned to something secret-looking.
GENERIC_SECRET = re.compile(
    r"(?i)(token|secret|password|api_?key|webhook)\s*[:=]\s*['\"][A-Za-z0-9_\-]{24,}['\"]"
)

# Strings that are fine even though they match a broad pattern.
ALLOW = [
    # Documentation placeholders are the whole point of .env.example.
    "EXAMPLE-CANARY-REPLACE-ME",
    "TEST-CANARY-0000",
    "test-key",
    # Generic placeholders used by tests and docs. None of these identify a
    # deployment; they are the "my-bucket" / "example.com" class of value.
    "my-bucket",
    "your-bucket",
    "example.com",
    "example.org",
]

# --------------------------------------------------------------------------
# Private deny-list.
# --------------------------------------------------------------------------
# Some identifiers cannot be recognised by shape -- a bare GCP project id looks
# like any other slug. Listing them here would mean publishing them, which is
# exactly what this file exists to prevent.
#
# So they live in `private_denylist.txt`, which is git-ignored. When present, the
# test checks them too. When absent, the shape rules still run. This gives a
# maintainer the strong check locally without weakening the published one.
DENYLIST_FILE = REPO_ROOT / "private_denylist.txt"


def _denylist() -> list[str]:
    if not DENYLIST_FILE.exists():
        return []
    out: list[str] = []
    for line in DENYLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


# This file necessarily contains the patterns it searches for, and the deny-list
# necessarily contains the values it denies, so both are excluded from the scan.
_SELF = Path(__file__).resolve()
_OWN_FILES = {_SELF, REPO_ROOT / "private_denylist.txt"}


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.resolve() in {p.resolve() for p in _OWN_FILES}:
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        out.append(path)
    return sorted(out)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


@pytest.mark.parametrize("pattern,label", FORBIDDEN, ids=[p[0] for p in FORBIDDEN])
def test_no_forbidden_string(pattern, label):
    """No file may contain a private identifier, credential, or detector table."""
    hits: list[str] = []
    for path in _iter_files():
        text = _read(path)
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Skip lines that are explicitly allowed.
            if any(token in line for token in ALLOW):
                continue
            if re.search(pattern, line):
                rel = path.relative_to(REPO_ROOT)
                hits.append(f"{rel}:{lineno}: {line.strip()[:120]}")
    assert not hits, f"found {label} ({len(hits)} hit(s)):\n" + "\n".join(hits)


def test_no_private_denylist_values():
    """Check literal identifiers that shape matching cannot catch.

    Skipped when no deny-list is present, which is the case in the published
    repo. A maintainer keeps one locally in a git-ignored file.
    """
    deny = _denylist()
    if not deny:
        pytest.skip("no private_denylist.txt present (expected in the public repo)")

    hits: list[str] = []
    for path in _iter_files():
        text = _read(path)
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for value in deny:
                if value in line:
                    rel = path.relative_to(REPO_ROOT)
                    hits.append(f"{rel}:{lineno}: contains a deny-listed value")
                    break
    assert not hits, f"deny-listed value found ({len(hits)} hit(s)):\n" + "\n".join(hits)


def test_no_generic_secret_assignments():
    """Catch anything shaped like a hardcoded credential."""
    hits: list[str] = []
    for path in _iter_files():
        text = _read(path)
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(token in line for token in ALLOW):
                continue
            if GENERIC_SECRET.search(line):
                rel = path.relative_to(REPO_ROOT)
                hits.append(f"{rel}:{lineno}: {line.strip()[:120]}")
    assert not hits, "possible hardcoded credential:\n" + "\n".join(hits)


def test_no_private_files_are_present():
    """High-risk files must not exist in the published tree at all."""
    forbidden_paths = [
        "canaries.json",
        ".env",
        "credentials",
        "service-account.json",
        "docs/field_guide.json",
        "docs/FIELD_GUIDE.md",
        "PLAN.md",
    ]
    present = [p for p in forbidden_paths if (REPO_ROOT / p).exists()]
    assert not present, f"private files present in public tree: {present}"


# Variable names that must never carry a value in `.env.example`. Non-secret
# settings (store backend, model name, limits) are documented with real defaults
# on purpose -- those are not credentials.
SECRET_KEYS = re.compile(
    r"(?i)(token|secret|password|api_?key|webhook|canary|credential|private)"
)


def test_env_example_holds_no_secrets():
    """`.env.example` documents secret variable names, never their values."""
    env = REPO_ROOT / ".env.example"
    if not env.exists():
        pytest.skip("no .env.example in this repo")
    offenders: list[str] = []
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if not value:
            continue
        if SECRET_KEYS.search(key):
            offenders.append(f"{key}={value}")
    assert not offenders, (
        "these secret-bearing variables carry a value in .env.example: "
        + ", ".join(offenders)
    )
