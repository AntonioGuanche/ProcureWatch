#!/usr/bin/env python3
"""Generate a preview HTML of the digest email with realistic Belgian procurement data.

Usage: python scripts/preview_digest.py
Output: digest_preview.html
"""
import sys
import os
import importlib.util

# Direct import to avoid full app dependency chain (sqlalchemy etc.)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
_spec = importlib.util.spec_from_file_location(
    "email_templates",
    os.path.join(_project_root, "app", "services", "email_templates.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build_consolidated_digest_html = _mod.build_consolidated_digest_html

from datetime import datetime, timedelta

now = datetime.now()

watchlist_results = [
    {
        "watchlist_name": "IT & Développement logiciel",
        "watchlist_keywords": "logiciel,software,développement,informatique,SaaS",
        "matches": [
            {
                "title": "Marché de services pour le développement et la maintenance d'applications web pour le SPF Finances",
                "buyer": "SPF Finances",
                "deadline": now + timedelta(days=2),
                "link": "https://enot.publicprocurement.be/tender/12345",
                "app_link": "https://procurewatch.eu/search?notice=abc-123",
                "source": "BOSA",
                "publication_date": now - timedelta(days=5),
                "cpv": "72212000",
                "notice_type": "CONTRACT_NOTICE",
                "estimated_value": 450000,
                "region": "BE100",
                "is_new": True,
            },
            {
                "title": "Fourniture de licences logicielles Microsoft et services cloud associés",
                "buyer": "Ville de Bruxelles",
                "deadline": now + timedelta(days=6),
                "link": "https://enot.publicprocurement.be/tender/12346",
                "app_link": "https://procurewatch.eu/search?notice=abc-124",
                "source": "BOSA",
                "publication_date": now - timedelta(days=3),
                "cpv": "48000000",
                "notice_type": "CONTRACT_NOTICE",
                "estimated_value": 1250000,
                "region": "BE100",
                "is_new": True,
            },
            {
                "title": "Attribution - Plateforme de gestion documentaire pour la Région wallonne",
                "buyer": "SPW - Service Public de Wallonie",
                "deadline": None,
                "link": "https://enot.publicprocurement.be/tender/12340",
                "app_link": "https://procurewatch.eu/search?notice=abc-125",
                "source": "BOSA",
                "publication_date": now - timedelta(days=1),
                "cpv": "72212200",
                "notice_type": "CONTRACT_AWARD_NOTICE",
                "estimated_value": 320000,
                "region": "BE35",
                "is_new": False,
            },
            {
                "title": "Consultance en cybersécurité et audit des systèmes d'information",
                "buyer": "SNCB / NMBS",
                "deadline": now + timedelta(days=18),
                "link": "https://ted.europa.eu/notice/2025/S/12345",
                "app_link": "https://procurewatch.eu/search?notice=abc-126",
                "source": "TED",
                "publication_date": now - timedelta(days=2),
                "cpv": "72150000",
                "notice_type": "CONTRACT_NOTICE",
                "estimated_value": 2800000,
                "region": "BE100",
                "is_new": True,
            },
        ],
    },
    {
        "watchlist_name": "Construction & Rénovation",
        "watchlist_keywords": "construction,rénovation,bâtiment,travaux,HVAC",
        "matches": [
            {
                "title": "Travaux de rénovation énergétique des bâtiments communaux - Lot 2 : HVAC",
                "buyer": "Commune d'Aalst",
                "deadline": now + timedelta(days=12),
                "link": "https://enot.publicprocurement.be/tender/22001",
                "app_link": "https://procurewatch.eu/search?notice=def-201",
                "source": "BOSA",
                "publication_date": now - timedelta(days=4),
                "cpv": "45331000",
                "notice_type": "CONTRACT_NOTICE",
                "estimated_value": 185000,
                "region": "BE231",
                "is_new": True,
            },
            {
                "title": "Construction d'une nouvelle école maternelle - commune de Namur",
                "buyer": "Ville de Namur",
                "deadline": now + timedelta(days=25),
                "link": "https://enot.publicprocurement.be/tender/22002",
                "app_link": "https://procurewatch.eu/search?notice=def-202",
                "source": "BOSA",
                "publication_date": now - timedelta(days=7),
                "cpv": "45214100",
                "notice_type": "CONTRACT_NOTICE",
                "estimated_value": 3500000,
                "region": "BE352",
                "is_new": False,
            },
            {
                "title": "Accord-cadre pour travaux d'entretien des voiries régionales en Province de Liège",
                "buyer": "SPW Mobilité et Infrastructures",
                "deadline": now + timedelta(days=4),
                "link": "https://ted.europa.eu/notice/2025/S/22003",
                "app_link": "https://procurewatch.eu/search?notice=def-203",
                "source": "TED",
                "publication_date": now - timedelta(days=6),
                "cpv": "45233141",
                "notice_type": "COMPETITION",
                "estimated_value": 8200000,
                "region": "BE33",
                "is_new": True,
            },
        ],
    },
]

html = build_consolidated_digest_html(
    user_name="Antonio",
    watchlist_results=watchlist_results,
    app_url="https://procurewatch.eu",
)

output_path = "digest_preview.html"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ Preview generated: {output_path}")
print(f"   {sum(len(wr['matches']) for wr in watchlist_results)} notices across {len(watchlist_results)} watchlists")
