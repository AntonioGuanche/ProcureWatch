"""App-level connectors: BOSA e-Procurement + TED EU.

Canonical locations:
  app.connectors.bosa.*  — BOSA / e-Procurement
  app.connectors.ted.*   — TED / Tenders Electronic Daily

Legacy thin wrappers (eproc_connector, ted_connector) kept for
backward compat but delegate to packages above.
"""
from app.connectors.eproc_connector import fetch_publication_workspace
from app.connectors.ted_connector import search_ted_notices

__all__ = ["fetch_publication_workspace", "search_ted_notices"]
