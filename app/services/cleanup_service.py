"""
Cleanup script: remove duplicate BOSA notices (same dossier_id, keep newest).
Can be run as admin endpoint or standalone script.
"""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def cleanup_bosa_duplicates(db: Session, dry_run: bool = True) -> dict:
    """
    Find BOSA notices with the same dossier_id and keep only the one
    with the most recent publication_date (or created_at as tiebreaker).

    Returns stats: {total_duplicates, groups, deleted_ids, kept_ids}
    """
    # Find dossier_ids with more than 1 notice
    dupe_query = text("""
        SELECT dossier_id, COUNT(*) as cnt
        FROM notices
        WHERE source = 'BOSA_EPROC'
          AND dossier_id IS NOT NULL
          AND dossier_id != ''
        GROUP BY dossier_id
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
    """)

    dupes = db.execute(dupe_query).fetchall()

    stats = {
        "duplicate_groups": len(dupes),
        "total_extra_rows": sum(row[1] - 1 for row in dupes),
        "deleted_ids": [],
        "kept_ids": [],
        "dry_run": dry_run,
    }

    if not dupes:
        logger.info("No duplicates found")
        return stats

    logger.info("Found %d dossier groups with duplicates (%d extra rows)",
                len(dupes), stats["total_extra_rows"])

    for dossier_id, count in dupes:
        # Get all notices for this dossier, newest first
        notices_query = text("""
            SELECT id, source_id, publication_date, created_at
            FROM notices
            WHERE source = 'BOSA_EPROC' AND dossier_id = :did
            ORDER BY publication_date DESC NULLS LAST, created_at DESC
        """)
        notices = db.execute(notices_query, {"did": dossier_id}).fetchall()

        # Keep the first (newest), delete the rest
        keep_id = notices[0][0]
        delete_ids = [n[0] for n in notices[1:]]

        stats["kept_ids"].append(str(keep_id))
        stats["deleted_ids"].extend(str(d) for d in delete_ids)

        if not dry_run and delete_ids:
            # Delete related lots and additional CPV first
            placeholders = ",".join(f":id{i}" for i in range(len(delete_ids)))
            id_params = {f"id{i}": did for i, did in enumerate(delete_ids)}
            db.execute(text(
                f"DELETE FROM notice_lots WHERE notice_id IN ({placeholders})"
            ), id_params)
            db.execute(text(
                f"DELETE FROM notice_cpv_additional WHERE notice_id IN ({placeholders})"
            ), id_params)
            db.execute(text(
                f"DELETE FROM notices WHERE id IN ({placeholders})"
            ), id_params)

    if not dry_run:
        db.commit()
        logger.info("Deleted %d duplicate notices", len(stats["deleted_ids"]))
    else:
        logger.info("DRY RUN: would delete %d duplicate notices", len(stats["deleted_ids"]))

    return stats
