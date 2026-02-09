"""
Cleanup: remove duplicate BOSA notices (same title + cpv + org, keep newest).
"""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def cleanup_bosa_duplicates(db: Session, dry_run: bool = True) -> dict:
    """
    Find BOSA notices with the same title + cpv_main_code + source
    and keep only the one with the most recent publication_date.
    """
    # Find duplicate groups by title + cpv
    dupe_query = text("""
        SELECT title, cpv_main_code, COUNT(*) as cnt
        FROM notices
        WHERE source = 'BOSA_EPROC'
          AND title IS NOT NULL
          AND title != ''
        GROUP BY title, cpv_main_code
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
    """)

    dupes = db.execute(dupe_query).fetchall()

    stats = {
        "duplicate_groups": len(dupes),
        "total_extra_rows": sum(row[2] - 1 for row in dupes),
        "sample_groups": [],
        "deleted_count": 0,
        "dry_run": dry_run,
    }

    if not dupes:
        logger.info("No duplicates found")
        return stats

    logger.info("Found %d groups with duplicates (%d extra rows)",
                len(dupes), stats["total_extra_rows"])

    # Show top 5 duplicate groups as samples
    for title, cpv, count in dupes[:5]:
        stats["sample_groups"].append({
            "title": (title[:80] + "...") if title and len(title) > 80 else title,
            "cpv": cpv,
            "count": count,
        })

    if not dry_run:
        # Delete all but the newest per group in one efficient query
        delete_query = text("""
            DELETE FROM notice_lots
            WHERE notice_id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY title, cpv_main_code
                               ORDER BY publication_date DESC NULLS LAST,
                                        created_at DESC NULLS LAST
                           ) as rn
                    FROM notices
                    WHERE source = 'BOSA_EPROC'
                      AND title IS NOT NULL AND title != ''
                ) ranked WHERE rn > 1
            );

            DELETE FROM notice_cpv_additional
            WHERE notice_id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY title, cpv_main_code
                               ORDER BY publication_date DESC NULLS LAST,
                                        created_at DESC NULLS LAST
                           ) as rn
                    FROM notices
                    WHERE source = 'BOSA_EPROC'
                      AND title IS NOT NULL AND title != ''
                ) ranked WHERE rn > 1
            );

            DELETE FROM notices
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY title, cpv_main_code
                               ORDER BY publication_date DESC NULLS LAST,
                                        created_at DESC NULLS LAST
                           ) as rn
                    FROM notices
                    WHERE source = 'BOSA_EPROC'
                      AND title IS NOT NULL AND title != ''
                ) ranked WHERE rn > 1
            );
        """)
        # SQLAlchemy text() doesn't support multiple statements easily
        # Split into separate executions
        ranked_subquery = """
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY title, cpv_main_code
                           ORDER BY publication_date DESC NULLS LAST,
                                    created_at DESC NULLS LAST
                       ) as rn
                FROM notices
                WHERE source = 'BOSA_EPROC'
                  AND title IS NOT NULL AND title != ''
            ) ranked WHERE rn > 1
        """

        r1 = db.execute(text(
            f"DELETE FROM notice_lots WHERE notice_id IN ({ranked_subquery})"
        ))
        r2 = db.execute(text(
            f"DELETE FROM notice_cpv_additional WHERE notice_id IN ({ranked_subquery})"
        ))
        r3 = db.execute(text(
            f"DELETE FROM notices WHERE id IN ({ranked_subquery})"
        ))
        db.commit()

        stats["deleted_count"] = r3.rowcount
        logger.info("Deleted %d duplicate notices", r3.rowcount)

    return stats
