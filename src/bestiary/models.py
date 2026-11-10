"""Plain data records shared by every store backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    id: str
    session_id: str
    ts: str
    method: str
    path: str
    query: str
    status: int
    ip: str
    user_agent: str
    referer: str
    headers: dict[str, str] = field(default_factory=dict)
    header_order: list[str] = field(default_factory=list)
    token: str | None = None
    parent_token: str | None = None
    depth: int = 0
    verdict: str = "unknown"
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    agent_family: str | None = None
    is_trap: bool = False
    ms_since_prev: int | None = None


@dataclass
class Session:
    id: str
    first_seen: str
    last_seen: str
    ip: str = ""
    user_agent: str = ""
    agent_family: str | None = None
    # What the capture layer inferred about *what kind* of visitor this is:
    # one of ai | crawler | browser | http | tool | human | unknown.
    #
    # The private capture layer derives this from its user-agent table; the
    # public package reads the recorded value so the interpretation layer can
    # run without that table.
    agent_kind: str = "unknown"
    verdict: str = "unknown"
    score: int = 0
    event_count: int = 0
    tokens: list[str] = field(default_factory=list)
    probe: dict[str, Any] | None = None
    interrogation: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TokenRecord:
    token: str
    parent: str | None
    depth: int
    session_id: str
    created_at: str


@dataclass
class ArtRecord:
    """One canonical portrait for one species.

    Art is generated exactly once per taxonomic signature and cached forever.
    ``status`` is one of ``pending`` | ``generated`` | ``failed`` | ``skipped``.
    """

    signature: str
    status: str = "pending"
    image_url: str = ""
    image_path: str = ""
    prompt_version: int = 1
    prompt_text: str = ""
    model_used: str = ""
    generated_at: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "status": self.status,
            "image_url": self.image_url,
            "image_path": self.image_path,
            "prompt_version": self.prompt_version,
            "prompt_text": self.prompt_text,
            "model_used": self.model_used,
            "generated_at": self.generated_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtRecord":
        return cls(
            signature=str(data.get("signature") or ""),
            status=str(data.get("status") or "pending"),
            image_url=str(data.get("image_url") or ""),
            image_path=str(data.get("image_path") or ""),
            prompt_version=int(data.get("prompt_version") or 1),
            prompt_text=str(data.get("prompt_text") or ""),
            model_used=str(data.get("model_used") or ""),
            generated_at=str(data.get("generated_at") or ""),
            error=str(data.get("error") or ""),
        )
