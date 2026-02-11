# ProcureWatch v7 — Email Digest Alerts

## What's included

### New files
- `app/services/email_templates.py` — Professional HTML email templates (digest + welcome)
- `app/api/routes/admin_digest.py` — Admin endpoints for testing/previewing/triggering digests
- `scripts/cron_daily.py` — Unified cron: import → match → email digest
- `scripts/preview_digest.py` — Preview email template locally in browser

### Updated files
- `app/services/notification_service.py` — Uses new pro template instead of basic table

## Setup

### 1. Resend (email provider) — 5 minutes

1. Go to https://resend.com → Create free account (100 emails/day free)
2. Get your API key from Dashboard → API Keys
3. In Railway → web service → Variables, add:
   ```
   EMAIL_MODE=resend
   RESEND_API_KEY=re_xxxxxxxxxx
   EMAIL_FROM=alerts@procurewatch.eu
   APP_URL=https://procurewatch.eu
   ```

**Note:** With the free plan you can only send to your own email first.
To send to any address, verify your domain:
- Resend Dashboard → Domains → Add `procurewatch.eu`
- Add the DNS records Resend gives you (MX, SPF, DKIM)

### 2. Deploy the code

```bash
cd procurewatch
unzip -o procurewatch-v7-digest.zip
git add -A
git commit -m "feat: professional email digest alerts with Resend"
git push
```

### 3. Register the admin_digest router

In `app/main.py`, add:
```python
from app.api.routes.admin_digest import router as admin_digest_router
app.include_router(admin_digest_router, prefix="/api")
```

### 4. Test the digest

**Preview locally (no email sent):**
```bash
python scripts/preview_digest.py
```

**Send test email via API:**
```javascript
// In browser console on your app
fetch('/api/admin/digest/test?watchlist_id=YOUR_WATCHLIST_ID&to_email=you@gmail.com', {
  method: 'POST',
  headers: {'Authorization': 'Bearer ' + sessionStorage.getItem('pw_token')}
}).then(r => r.json()).then(console.log)
```

**Preview HTML via API (no send):**
```javascript
fetch('/api/admin/digest/preview?watchlist_id=YOUR_WATCHLIST_ID', {
  method: 'POST',
  headers: {'Authorization': 'Bearer ' + sessionStorage.getItem('pw_token')}
}).then(r => r.json()).then(d => {
  const w = window.open(); w.document.write(d.html); w.document.close();
})
```

### 5. Set up Railway cron (daily digest)

1. Railway Dashboard → your project → **New Service** → same repo
2. Settings:
   - **Start command:** `python scripts/cron_daily.py`
   - **Cron schedule:** `0 6 * * *` (06:00 UTC = 07:00 CET)
3. Variables → **Reference Variables** from web service, plus:
   ```
   DATABASE_URL  (same as web service)
   EMAIL_MODE=resend
   RESEND_API_KEY=re_xxxxxxxxxx
   EMAIL_FROM=alerts@procurewatch.eu
   ```

## How it works

```
06:00 UTC — cron_daily.py runs:
  ├── Step 1: Alembic migrations (idempotent)
  ├── Step 2: Import latest TED + BOSA (last 3 days)
  └── Step 3: For each enabled watchlist with notify_email:
      ├── Find new notices matching criteria since last_refresh_at
      ├── Store matches in watchlist_matches (dedup)
      ├── Send branded HTML digest email via Resend
      └── Update last_refresh_at
```

## Email template features

- Professional branded design (ProcureWatch header)
- Source badges (BOSA green, TED blue)
- Color-coded deadlines (red < 3 days, orange < 7 days, green > 7 days)
- Buyer name, CPV code, publication date
- Direct "Voir l'avis" links to original notices
- Responsive design (mobile-friendly)
- French UI text
- Footer with unsubscribe placeholder
