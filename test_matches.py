from app.db.session import SessionLocal
from app.db.models.watchlist_match import WatchlistMatch
from app.models.notice import ProcurementNotice

db = SessionLocal()

matches = db.query(WatchlistMatch).all()
print(f'Total matches: {len(matches)}')
print()

for m in matches:
    notice = db.query(ProcurementNotice).filter(
        ProcurementNotice.id == m.notice_id
    ).first()
    
    if notice:
        title = notice.title[:60] if notice.title else 'N/A'
        print(f'Notice: {title}...')
        print(f'  CPV: {notice.cpv_main_code}')
        print(f'  Pub date: {notice.publication_date}')
        print(f'  Source: {notice.source}')
        print(f'  Matched on: {m.matched_on}')
        print()

db.close()
