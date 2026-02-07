from app.db.session import SessionLocal
from app.db.models.watchlist import Watchlist
from app.db.models.watchlist_match import WatchlistMatch
from app.models.notice import ProcurementNotice
from app.services.notification_service import send_watchlist_notification

db = SessionLocal()

w = db.query(Watchlist).first()
matches = db.query(WatchlistMatch).filter(
    WatchlistMatch.watchlist_id == w.id
).all()

print(f'Watchlist: {w.name}')
print(f'Matches found: {len(matches)}')

if matches:
    match_data = []
    for m in matches:
        notice = db.query(ProcurementNotice).filter(
            ProcurementNotice.id == m.notice_id
        ).first()
        
        if notice:
            match_data.append({
                'title': notice.title or 'N/A',
                'buyer': notice.organisation_names,
                'deadline': notice.deadline,
                'link': f'https://procurewatch.app/notices/{notice.id}'
            })
    
    print(f'Sending email with {len(match_data)} notices...')
    send_watchlist_notification(w, match_data, to_address='test@procurewatch.local')
    print('Email sent!')
else:
    print('No matches to notify')

db.close()
