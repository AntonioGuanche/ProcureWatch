# ProcureWatch v7b — Digest consolidé + Design landing page

## Changements clés

### 1. Design email = design landing page
- Palette Navy #1B2D4F + Teal #10b981 (identique à la landing)
- Google Fonts Inter
- Header arrondi (border-radius 16px) avec dégradé navy
- Cards notices avec pills source (BOSA vert, TED bleu)
- Deadlines colorées : rouge < 3j, orange < 7j, vert > 7j
- Layout responsive, compatible Outlook/Gmail/Apple Mail

### 2. Digest consolidé (anti-spam)
**Avant :** 1 email par watchlist → si l'utilisateur a 5 veilles, il reçoit 5 emails
**Maintenant :** 1 seul email par utilisateur regroupant TOUTES ses veilles actives

L'email affiche :
- Greeting personnalisé avec le nombre total d'opportunités
- Sections par veille (nom + keywords pills + notices)
- Séparateurs visuels gradient teal → gris entre les sections

### Fichiers

| Fichier | Rôle |
|---|---|
| `app/services/email_templates.py` | Templates HTML (consolidated digest + welcome) |
| `app/services/notification_service.py` | Service email (consolidated + single watchlist) |
| `app/services/watchlist_matcher.py` | Matcher revu : groupe par user_email → 1 email |
| `app/api/routes/admin_digest.py` | Endpoints admin (test, preview, run-all) |
| `scripts/cron_daily.py` | Cron unifié : import → match → digest consolidé |
| `scripts/preview_digest.py` | Preview local (sample 3 watchlists / réel via DB) |

## Setup

### 1. Deploy
```bash
cd procurewatch
unzip -o procurewatch-v7b-digest.zip
git add -A
git commit -m "feat: consolidated email digest with landing page design"
git push
```

### 2. Resend (100 emails/jour gratuit)
Dans Railway → Variables :
```
EMAIL_MODE=resend
RESEND_API_KEY=re_xxxxxxxxxx
EMAIL_FROM=alerts@procurewatch.eu
APP_URL=https://procurewatch.eu
```

### 3. Router admin_digest
Dans `app/main.py` :
```python
from app.api.routes.admin_digest import router as admin_digest_router
app.include_router(admin_digest_router, prefix="/api")
```

### 4. Railway cron
- Nouveau service → même repo
- Commande: `python scripts/cron_daily.py`
- Schedule: `0 6 * * *` (07h CET)
- Mêmes variables que le web service

## Comment ça marche

```
06:00 UTC — cron_daily.py :
  ├── Alembic migrations
  ├── Import TED + BOSA (3 derniers jours)
  └── Pour chaque utilisateur avec des veilles actives :
      ├── Matcher toutes ses veilles
      ├── Grouper les résultats
      └── Envoyer 1 seul email consolidé
```
