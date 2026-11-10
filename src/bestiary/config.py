"""Configuration loaded from environment (with a tiny .env loader)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    store: str
    sqlite_path: str
    secret_key: str
    public_base_url: str
    canary: str
    max_events_per_session: int
    tarpit_max_depth: int
    daily_page_budget: int
    rate_limit_per_minute: int
    retention_days: int
    admin_token: str
    project: str
    region: str
    service: str
    # --- Bestiary / art ---
    art_enabled: bool = True
    art_model: str = "google/gemini-2.5-flash-image"
    art_bucket: str = ""
    art_max_species: int = 50
    # Humans get a persona portrait (researcher, gamer, sysadmin...). Set 0 to
    # restore the old "never render humans" behaviour.
    art_render_humans: bool = True
    bestiary_public: bool = False
    discord_webhook_url: str = ""
    openrouter_api_key: str = ""
    # Where the bestiary is actually served. Defaults to public_base_url, but
    # can be overridden so a LOCAL run does not emit links to the production
    # host, where its species do not exist (they would 404).
    bestiary_base_url: str = ""
    # Allow Discord notifications from a non-Firestore (local) run. Off by
    # default: a local run would announce species production has never seen.
    notify_local: bool = False

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_token)

    @property
    def bestiary_url(self) -> str:
        """Base URL for bestiary links: explicit override, else public base."""
        return (self.bestiary_base_url or self.public_base_url or "").rstrip("/")

    @property
    def art_dir(self) -> Path:
        """Local fallback directory for generated portraits."""
        return PROJECT_ROOT / "data" / "art"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        store=os.environ.get("HONEYPOT_STORE", "sqlite").strip().lower(),
        sqlite_path=os.environ.get(
            "HONEYPOT_SQLITE_PATH", str(PROJECT_ROOT / "data" / "honeypot.db")
        ),
        # No default. This package renders and signs nothing, but a shared
        # signer is what makes signed URLs forgeable, so a missing key is an
        # error at use time rather than a silent fallback to a public string.
        secret_key=os.environ.get("HONEYPOT_SECRET_KEY", ""),
        public_base_url=os.environ.get(
            "HONEYPOT_PUBLIC_BASE_URL", "http://localhost:8080"
        ).rstrip("/"),
        # Deliberately EMPTY, never a real phrase. The canary is a research
        # instrument: a committed or defaulted value gets scraped into training
        # corpora, after which a hit in a model's output no longer proves that
        # THIS page was ingested. scripts/deploy_cloud.ps1 generates it at
        # deploy time and stores it in Secret Manager.
        canary=os.environ.get("HONEYPOT_CANARY", "").strip(),
        max_events_per_session=_int("HONEYPOT_MAX_EVENTS_PER_SESSION", 500),
        tarpit_max_depth=_int("HONEYPOT_TARPIT_MAX_DEPTH", 200),
        daily_page_budget=_int("HONEYPOT_DAILY_PAGE_BUDGET", 200_000),
        rate_limit_per_minute=_int("HONEYPOT_RATE_LIMIT_PER_MINUTE", 120),
        retention_days=_int("HONEYPOT_RETENTION_DAYS", 90),
        admin_token=os.environ.get("HONEYPOT_ADMIN_TOKEN", "").strip(),
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip(),
        region=os.environ.get("HONEYPOT_REGION", "us-east1").strip(),
        service=os.environ.get("HONEYPOT_SERVICE", "ai-honeypot").strip(),
        art_enabled=_bool("HONEYPOT_ART_ENABLED", True),
        art_model=os.environ.get(
            "HONEYPOT_ART_MODEL", "google/gemini-2.5-flash-image"
        ).strip()
        or "google/gemini-2.5-flash-image",
        art_bucket=os.environ.get("HONEYPOT_ART_BUCKET", "").strip(),
        art_max_species=_int("HONEYPOT_ART_MAX_SPECIES", 50),
        art_render_humans=_bool("HONEYPOT_ART_RENDER_HUMANS", True),
        bestiary_public=_bool("HONEYPOT_BESTIARY_PUBLIC", False),
        discord_webhook_url=(
            os.environ.get("HONEYPOT_DISCORD_WEBHOOK_URL", "").strip()
            or os.environ.get("CONNECTOR_HUB_DISCORD_WEBHOOK_URL", "").strip()
        ),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", "").strip(),
        bestiary_base_url=os.environ.get("HONEYPOT_BESTIARY_BASE_URL", "").strip(),
        notify_local=_bool("HONEYPOT_NOTIFY_LOCAL", False),
    )
