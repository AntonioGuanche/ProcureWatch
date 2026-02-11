#!/usr/bin/env python3
"""Preview the consolidated digest email template locally.

Usage:
    python scripts/preview_digest.py                    # sample data
    python scripts/preview_digest.py --user-email X     # real data from DB
"""
import argparse
import sys
import tempfile
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.email_templates import build_consolidated_digest_html


def preview_sample():
    """Preview with sample multi-watchlist data."""
    watchlist_results = [
        {
            "watchlist_name": "IT & Digital",
            "watchlist_keywords": "informatique, digital, logiciel, cloud",
            "matches": [
                {
                    "title": "Marché de fournitures informatiques pour le SPF Finances – Infrastructure cloud et licences",
                    "buyer": "SPF Finances",
                    "deadline": (datetime.now() + timedelta(days=3)).date(),
                    "link": "https://ted.europa.eu/notice/123456",
                    "source": "TED_EU",
                    "publication_date": (datetime.now() - timedelta(days=1)).date(),
                    "cpv": "30200000",
                },
                {
                    "title": "Services de conseil en transformation digitale pour la Région wallonne",
                    "buyer": "Service Public de Wallonie",
                    "deadline": (datetime.now() + timedelta(days=1)).date(),
                    "link": "https://ted.europa.eu/notice/456789",
                    "source": "TED_EU",
                    "publication_date": (datetime.now() - timedelta(days=2)).date(),
                    "cpv": "72000000",
                },
                {
                    "title": "Développement et maintenance d'une plateforme web pour le registre national",
                    "buyer": "SPF Intérieur",
                    "deadline": (datetime.now() + timedelta(days=18)).date(),
                    "link": "https://ted.europa.eu/notice/789012",
                    "source": "TED_EU",
                    "publication_date": datetime.now().date(),
                    "cpv": "72200000",
                },
            ],
        },
        {
            "watchlist_name": "Construction & Rénovation",
            "watchlist_keywords": "travaux, rénovation, électricité, bâtiment",
            "matches": [
                {
                    "title": "Travaux de rénovation du bâtiment communal – Lot 2 : Électricité",
                    "buyer": "Commune de Schaerbeek",
                    "deadline": (datetime.now() + timedelta(days=14)).date(),
                    "link": "https://enot.publicprocurement.be/notice/789",
                    "source": "BOSA_EPROC",
                    "publication_date": datetime.now().date(),
                    "cpv": "45310000",
                },
                {
                    "title": "Accord-cadre pour travaux de toiture – Arrondissement de Liège",
                    "buyer": "Province de Liège",
                    "deadline": (datetime.now() + timedelta(days=21)).date(),
                    "link": "https://ted.europa.eu/notice/321654",
                    "source": "TED_EU",
                    "publication_date": (datetime.now() - timedelta(days=3)).date(),
                    "cpv": "45260000",
                },
            ],
        },
        {
            "watchlist_name": "Nettoyage & Entretien",
            "watchlist_keywords": "nettoyage, entretien, espaces verts",
            "matches": [
                {
                    "title": "Nettoyage des locaux administratifs – Zones Bruxelles-Est",
                    "buyer": "CPAS de Bruxelles",
                    "deadline": (datetime.now() + timedelta(days=9)).date(),
                    "link": "https://enot.publicprocurement.be/notice/555",
                    "source": "BOSA_EPROC",
                    "publication_date": datetime.now().date(),
                    "cpv": "90910000",
                },
            ],
        },
    ]

    html_content = build_consolidated_digest_html(
        user_name="Antonio",
        watchlist_results=watchlist_results,
        app_url="https://procurewatch.eu",
    )

    tmp = Path(tempfile.mktemp(suffix=".html"))
    tmp.write_text(html_content, encoding="utf-8")
    total = sum(len(wr["matches"]) for wr in watchlist_results)
    print(f"Preview ({total} matches, {len(watchlist_results)} watchlists) → {tmp}")
    webbrowser.open(f"file://{tmp}")


def preview_from_db(user_email: str):
    """Preview with real data grouped by user."""
    from app.db.session import SessionLocal
    from app.models.watchlist import Watchlist
    from app.models.watchlist_match import WatchlistMatch
    from app.models.notice import ProcurementNotice as Notice
    from app.services.watchlist_matcher import _notice_to_email_dict

    db = SessionLocal()
    try:
        watchlists = (
            db.query(Watchlist)
            .filter(Watchlist.notify_email == user_email, Watchlist.enabled == True)
            .all()
        )
        if not watchlists:
            print(f"No enabled watchlists with notify_email={user_email}")
            return

        wl_results = []
        for wl in watchlists:
            matches = (
                db.query(Notice)
                .join(WatchlistMatch, WatchlistMatch.notice_id == Notice.id)
                .filter(WatchlistMatch.watchlist_id == wl.id)
                .order_by(Notice.publication_date.desc().nullslast())
                .limit(10)
                .all()
            )
            if matches:
                wl_results.append({
                    "watchlist_name": wl.name,
                    "watchlist_keywords": wl.keywords or "",
                    "matches": [_notice_to_email_dict(n) for n in matches],
                })

        html_content = build_consolidated_digest_html(
            user_name=user_email.split("@")[0],
            watchlist_results=wl_results,
        )
    finally:
        db.close()

    tmp = Path(tempfile.mktemp(suffix=".html"))
    tmp.write_text(html_content, encoding="utf-8")
    total = sum(len(wr["matches"]) for wr in wl_results)
    print(f"Preview ({total} matches, {len(wl_results)} watchlists) → {tmp}")
    webbrowser.open(f"file://{tmp}")


def main():
    parser = argparse.ArgumentParser(description="Preview consolidated digest email")
    parser.add_argument("--user-email", default=None, help="Load real data for this user email")
    args = parser.parse_args()

    if args.user_email:
        preview_from_db(args.user_email)
    else:
        preview_sample()


if __name__ == "__main__":
    main()
