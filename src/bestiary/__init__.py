"""Bestiary — the interpretation layer for captured AI agents.

This package takes already-captured request records and does the *reading*:
it assigns a seven-rank taxonomy, groups specimens into species, and renders a
field guide. It contains no capture logic and no request scoring.

Two hooks let a real deployment supply the parts that live in the capture layer:

    from bestiary import fieldguide

    fieldguide.set_agent_kind_resolver(my_ua_table.lookup)
    fieldguide.set_inconsistency_detector(my_session_checks.fingerprint_check)

Without them the package runs on the fields already present in the record
schema, which is what the bundled synthetic corpus demonstrates.

Quick start::

    from bestiary import fieldguide
    from bestiary.models import Event, Session

    tax = fieldguide.classify_session(session, events)
    print(tax.binomial)   # e.g. Curiosus perplexitybotensis
"""

from __future__ import annotations

from .models import ArtRecord, Event, Session, TokenRecord
from .taxonomy import Taxonomy, classify_species, configure_machine_endpoints, latinize

__version__ = "0.1.0"

__all__ = [
    "ArtRecord",
    "Event",
    "Session",
    "Taxonomy",
    "TokenRecord",
    "classify_species",
    "configure_machine_endpoints",
    "latinize",
    "__version__",
]
