"""Admin endpoints — aggregator router.

Sub-routers:
  admin_import       Import, bulk-import, import-runs, scheduler
  admin_enrichment   Backfill, data-quality, merge/cleanup, watchlists, rescore, email
  admin_bosa         BOSA diagnostics, awards, workspace API, XML parsing
  admin_ted          TED CPV fix, TED CAN enrich
  admin_documents    Document pipeline, stats, BOSA document crawler
"""
from fastapi import APIRouter

from app.api.routes.admin_import import router as import_router
from app.api.routes.admin_enrichment import router as enrichment_router
from app.api.routes.admin_bosa import router as bosa_router
from app.api.routes.admin_ted import router as ted_router
from app.api.routes.admin_documents import router as documents_router

# Aggregate all sub-routers into a single router for main.py
# Each sub-router already has prefix="/admin" and auth dependencies.
router = APIRouter()
router.include_router(import_router)
router.include_router(enrichment_router)
router.include_router(bosa_router)
router.include_router(ted_router)
router.include_router(documents_router)
