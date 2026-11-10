"""Canonical species portraits: provider, storage, idempotency, and caps.

The hard rule: **art is generated exactly once per species and never
regenerated on read.** A species must look identical forever, or it stops being
a species. ``ensure_art`` therefore returns the cached record and makes zero
provider calls on a second invocation.

Generation is an explicit, capped CLI action (``scripts/generate_art.py``).
Nothing here is ever called from a page handler.

Provider pattern is lifted from the proven
``picture-test/starry_generate.py``:

1. ``POST /api/v1/images/generations`` with ``response_format=b64_json``
2. fallback ``POST /api/v1/chat/completions``, reading ``message.images[0]``
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from . import visual_dna
from .config import Settings, get_settings
from .models import ArtRecord
from .store import Store, get_store

log = logging.getLogger(__name__)

OPENROUTER_IMAGES_URL = "https://openrouter.ai/api/v1/images/generations"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# Rough per-image cost in USD, used only for the CLI estimate.
ESTIMATED_COST_PER_IMAGE = 0.04

HUMAN_KINGDOM = "Humana"

STATUS_PENDING = "pending"
STATUS_GENERATED = "generated"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


class ArtProvider(Protocol):
    """Anything that can turn a prompt into PNG bytes."""

    name: str

    def generate(self, prompt: str) -> bytes: ...


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce an image."""


# --------------------------------------------------------------------------
# provider
# --------------------------------------------------------------------------
class OpenRouterProvider:
    """OpenRouter image generation, with the chat-completions fallback."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-2.5-flash-image",
        *,
        timeout: float = 180.0,
        referer: str = "https://github.com/ai-honeypot",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.referer = referer
        self.name = model

    # -- internals -----------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.referer,
        }

    @staticmethod
    def _decode(item: Any) -> bytes | None:
        """Pull PNG bytes out of a b64_json / data-URL / url item."""
        if isinstance(item, str):
            if item.startswith("data:image"):
                item = item.split(",", 1)[1]
            try:
                return base64.b64decode(item)
            except Exception:
                return None
        if isinstance(item, dict):
            if item.get("b64_json"):
                try:
                    return base64.b64decode(item["b64_json"])
                except Exception:
                    return None
            url = item.get("url")
            if isinstance(url, str) and url.startswith("data:image"):
                return OpenRouterProvider._decode(url)
            if isinstance(url, str) and url.startswith("http"):
                import requests

                resp = requests.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.content
        return None

    def _via_images_endpoint(self, prompt: str) -> bytes | None:
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        resp = requests.post(
            OPENROUTER_IMAGES_URL,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            log.warning(
                "images endpoint returned %s: %s", resp.status_code, resp.text[:300]
            )
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        items = data.get("data") or []
        if not items:
            return None
        return self._decode(items[0])

    def _via_chat_endpoint(self, prompt: str) -> bytes | None:
        import requests

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests.post(
            OPENROUTER_CHAT_URL,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            log.warning(
                "chat endpoint returned %s: %s", resp.status_code, resp.text[:300]
            )
            return None
        try:
            data = resp.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            return None

        images = message.get("images") or []
        if images:
            decoded = self._decode(images[0])
            if decoded:
                return decoded

        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    decoded = self._decode(part.get("image_url") or {})
                    if decoded:
                        return decoded
        return None

    # -- public --------------------------------------------------------
    def generate(self, prompt: str) -> bytes:
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        data = self._via_images_endpoint(prompt)
        if data:
            return data
        data = self._via_chat_endpoint(prompt)
        if data:
            return data
        raise ProviderError("both image endpoints failed")


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------
def object_path(signature: str) -> str:
    """GCS object path for one portrait."""
    return f"bestiary/{signature}.png"


def local_art_path(signature: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.art_dir / f"{signature}.png"


def public_url(signature: str, settings: Settings | None = None) -> str:
    """Where the portrait is served from, given the current configuration."""
    settings = settings or get_settings()
    if settings.art_bucket:
        # Standard public-object URL for a GCS bucket. The bucket is configured at
        # deploy time, never baked in, so nothing here names a deployment.
        return f"https://storage.googleapis.com/{settings.art_bucket}/{object_path(signature)}"
    return f"/bestiary/art/{signature}.png"


def store_blob(
    signature: str, data: bytes, settings: Settings | None = None
) -> tuple[str, str]:
    """Persist PNG bytes. Returns ``(image_url, image_path)``.

    With ``HONEYPOT_ART_BUCKET`` set the blob goes to GCS; otherwise it lands in
    ``data/art/`` and is served by ``/bestiary/art/{signature}.png``.
    """
    settings = settings or get_settings()
    path = object_path(signature)

    if settings.art_bucket:
        from google.cloud import storage  # imported lazily

        client = storage.Client(project=settings.project or None)
        blob = client.bucket(settings.art_bucket).blob(path)
        blob.upload_from_string(data, content_type="image/png")
        return public_url(signature, settings), path

    target = local_art_path(signature, settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return public_url(signature, settings), path


# --------------------------------------------------------------------------
# idempotency + caps
# --------------------------------------------------------------------------
class StoreUnavailable(RuntimeError):
    """Raised when the art cache cannot be read.

    Generation must FAIL CLOSED: if we cannot prove a species has no portrait,
    we must not generate one. Returning 0 here would silently disable the cost
    cap and allow duplicate spend.
    """


def count_generated(store: Store | None = None) -> int:
    """How many species already have a portrait.

    Raises ``StoreUnavailable`` rather than returning 0 on failure — a silent 0
    makes the cap look unreached and lets generation proceed unbounded.
    """
    store = store or get_store()
    try:
        # strict=True: a failed read must not look like an empty collection,
        # or the cap silently disappears.
        records = store.list_art(strict=True)
        return sum(1 for r in records if r.status == STATUS_GENERATED)
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed error
        log.exception("could not count generated art")
        raise StoreUnavailable(f"cannot read art cache: {exc}") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kingdom(taxonomy: Any) -> str:
    if isinstance(taxonomy, dict):
        return str(taxonomy.get("kingdom") or "")
    return str(getattr(taxonomy, "kingdom", "") or "")


def ensure_art(
    signature: str,
    taxonomy: Any,
    *,
    force: bool = False,
    store: Store | None = None,
    settings: Settings | None = None,
    provider: ArtProvider | None = None,
) -> ArtRecord:
    """Return the canonical portrait for ``signature``, generating at most once.

    Order of checks matters:

    1. Cached ``generated`` record and not ``force`` -> return it, no API call.
    2. ``Humana`` kingdom and ``art_render_humans`` off -> ``skipped``.
    3. Cap reached -> ``skipped`` with reason ``cap_reached``, no API call.
    4. Otherwise generate. Failure is recorded and **not** retried automatically.
    """
    store = store or get_store()
    settings = settings or get_settings()

    # A read failure must abort, not fall through to generation. If the cache
    # state is unknown we cannot prove this species is unrendered, and
    # generating would overwrite an existing portrait and double the spend.
    try:
        existing = store.get_art(signature)
    except Exception as exc:  # noqa: BLE001
        raise StoreUnavailable(f"cannot read art cache: {exc}") from exc

    # A record is only a usable cache hit if it actually has an image. A
    # ``generated`` row with an empty URL is a broken record, not a portrait.
    if (
        existing
        and existing.status == STATUS_GENERATED
        and existing.image_url
        and not force
    ):
        return existing

    prompt = visual_dna.build_prompt(taxonomy)
    record = ArtRecord(
        signature=signature,
        status=STATUS_PENDING,
        prompt_version=visual_dna.PROMPT_VERSION,
        prompt_text=prompt,
        model_used=settings.art_model,
    )

    # --- global kill switch -------------------------------------------
    # HONEYPOT_ART_ENABLED=0 disables generation entirely without touching the
    # cache, so an operator can stop spend instantly.
    if not settings.art_enabled:
        record.status = STATUS_SKIPPED
        record.error = "art generation disabled"
        store.upsert_art(record)
        return record

    # --- humans -------------------------------------------------------
    # Humans ARE rendered (they get a persona portrait, not a creature). Set
    # HONEYPOT_ART_RENDER_HUMANS=0 to restore the old skip behaviour.
    if _kingdom(taxonomy) == HUMAN_KINGDOM and not settings.art_render_humans:
        record.status = STATUS_SKIPPED
        record.error = "humans are not rendered"
        store.upsert_art(record)
        return record

    # --- cap ----------------------------------------------------------
    # ``force`` regenerates an EXISTING portrait; it must not license unbounded
    # new spend. Only a cached record may bypass the cap.
    if count_generated(store) >= settings.art_max_species:
        record.status = STATUS_SKIPPED
        record.error = "cap_reached"
        store.upsert_art(record)
        return record

    # --- generate -----------------------------------------------------
    provider = provider or OpenRouterProvider(
        settings.openrouter_api_key, settings.art_model
    )
    try:
        data = provider.generate(prompt)
        if not data:
            raise ProviderError("provider returned no image data")
        image_url, image_path = store_blob(signature, data, settings)
    except Exception as exc:  # noqa: BLE001 - record, never retry
        log.warning("art generation failed for %s: %s", signature, exc)
        record.status = STATUS_FAILED
        record.error = str(exc)[:500]
        store.upsert_art(record)
        return record

    record.status = STATUS_GENERATED
    record.image_url = image_url
    record.image_path = image_path
    record.model_used = getattr(provider, "name", settings.art_model)
    record.generated_at = _now()
    record.error = ""
    store.upsert_art(record)
    return record


def art_for(signature: str, store: Store | None = None) -> ArtRecord | None:
    """Read-only lookup used by page handlers. Never generates."""
    store = store or get_store()
    try:
        return store.get_art(signature)
    except Exception:  # pragma: no cover - defensive
        log.exception("could not read art for %s", signature)
        return None


def art_map(store: Store | None = None) -> dict[str, ArtRecord]:
    """All art records keyed by signature. Never generates."""
    store = store or get_store()
    try:
        return {r.signature: r for r in store.list_art()}
    except Exception:  # pragma: no cover - defensive
        log.exception("could not list art")
        return {}
