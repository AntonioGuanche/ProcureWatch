from app.db.session import SessionLocal
from app.models.watchlist_match import WatchlistMatch
from app.models.notice import ProcurementNotice

db = SessionLocal()

# Prendre 5 matches aléatoires
matches = db.query(WatchlistMatch).limit(5).all()

for m in matches:
    notice = db.query(ProcurementNotice).filter(
        ProcurementNotice.id == m.notice_id
    ).first()
    
    if notice:
        print(f'Title: {notice.title}')
        print(f'Buyer: {notice.organisation_names}')
        print(f'Matched on: {m.matched_on}')
        print('---')

db.close()
