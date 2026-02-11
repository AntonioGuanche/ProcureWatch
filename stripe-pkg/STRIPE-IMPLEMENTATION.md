# ProcureWatch — Stripe Billing Integration

## Vue d'ensemble

Intégration Stripe Checkout + Customer Portal pour les plans :
- **Découverte** (0€) : 1 veille, 10 résultats, TED+BOSA, pas de digest
- **Pro** (49€/mois ou 39€/mois annuel) : 5 veilles, digest email, 20 résumés IA/mois, CSV
- **Business** (149€/mois ou 119€/mois annuel) : illimité, temps réel, API, 5 sièges

## Fichiers NOUVEAUX à créer

### 1. `alembic/versions/007_user_subscription_fields.py`
→ Voir fichier fourni (colonnes: plan, stripe_customer_id, stripe_subscription_id, subscription_status, subscription_ends_at)

### 2. `app/services/subscription.py`
→ Voir fichier fourni (définitions plans, limites, vérifications usage)

### 3. `app/api/routes/billing.py`
→ Voir fichier fourni (checkout, portal, webhook, subscription status)

### 4. `scripts/stripe_setup.py`
→ Voir fichier fourni (création produits + prix Stripe)

## Fichiers à MODIFIER

### 5. `app/models/user.py` — ajouter colonnes subscription

Après `is_admin`:
```python
    # ── Subscription / billing ──
    plan: Mapped[str] = mapped_column(
        String(20), default="free", server_default="free", nullable=False,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True,
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    subscription_status: Mapped[str] = mapped_column(
        String(30), default="none", server_default="none", nullable=False,
    )
    subscription_ends_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, comment="End of current billing period (UTC)",
    )
```

### 6. `app/core/config.py` — ajouter settings Stripe

Dans la classe Settings, ajouter :
```python
    # ── Stripe billing ──
    stripe_secret_key: str = Field("", validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field("", validation_alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_pro_monthly: str = Field("", validation_alias="STRIPE_PRICE_PRO_MONTHLY")
    stripe_price_pro_annual: str = Field("", validation_alias="STRIPE_PRICE_PRO_ANNUAL")
    stripe_price_business_monthly: str = Field("", validation_alias="STRIPE_PRICE_BUSINESS_MONTHLY")
    stripe_price_business_annual: str = Field("", validation_alias="STRIPE_PRICE_BUSINESS_ANNUAL")
    app_url: str = Field("https://app.procurewatch.eu", validation_alias="APP_URL")
```

### 7. `app/main.py` — enregistrer le router billing

Après les autres imports de routers :
```python
from app.api.routes.billing import router as billing_router
```

Et dans le montage :
```python
app.include_router(billing_router, prefix="/api")
```

### 8. `app/api/routes/auth.py` — ajouter plan dans UserOut

Modifier le schema UserOut :
```python
class UserOut(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool = False
    plan: str = "free"         # ← AJOUTER
```

Et dans l'endpoint `/me` :
```python
@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_admin=getattr(current_user, "is_admin", False),
        plan=getattr(current_user, "plan", "free"),   # ← AJOUTER
    )
```

### 9. `app/api/routes/watchlists_mvp.py` — enforcement des limites

Ajouter l'import :
```python
from app.services.subscription import check_watchlist_limit
```

Dans `post_watchlist` (création), ajouter avant `create_watchlist()` :
```python
    # Check plan limits
    limit_error = check_watchlist_limit(db, current_user)
    if limit_error:
        raise HTTPException(status_code=403, detail=limit_error)
```

### 10. `requirements.txt` — ajouter stripe

```
stripe>=8.0.0
```

### 11. `scripts/start.sh` — ajouter '007' aux versions valides

Mettre à jour la liste des versions dans le recovery script :
```
if ver and ver not in ('001', '002', '003', '004', '005', '006', '007'):
```

## Étapes de déploiement

### Étape 1 : Créer les produits Stripe (local)
```bash
pip install stripe
STRIPE_SECRET_KEY=sk_test_xxx python scripts/stripe_setup.py
```
→ Copier les Price IDs affichés

### Étape 2 : Configurer Railway
Ajouter les variables d'environnement :
```
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_PRO_MONTHLY=price_xxx
STRIPE_PRICE_PRO_ANNUAL=price_xxx
STRIPE_PRICE_BUSINESS_MONTHLY=price_xxx
STRIPE_PRICE_BUSINESS_ANNUAL=price_xxx
APP_URL=https://app.procurewatch.eu
```

### Étape 3 : Configurer le webhook Stripe
Dashboard Stripe → Developers → Webhooks → Add endpoint :
- URL : `https://api.procurewatch.eu/api/billing/webhook`
- Events :
  - `checkout.session.completed`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_failed`
- Copier le signing secret → `STRIPE_WEBHOOK_SECRET`

### Étape 4 : Déployer
```bash
git add -A
git commit -m "feat: Stripe billing integration (Pro 49€/mo, Business 149€/mo)"
git push railway main
```

### Étape 5 : Tester
1. Login → GET /api/billing/subscription → plan=free
2. POST /api/billing/checkout → redirect Stripe → use test card 4242424242424242
3. Webhook → user.plan=pro, subscription_status=active
4. Try create 6th watchlist → 403 (Pro limit = 5)
5. POST /api/billing/portal → manage subscription on Stripe

## Architecture Stripe

```
┌──────────────┐   POST /billing/checkout    ┌───────────────┐
│   Frontend   │ ─────────────────────────→  │  FastAPI       │
│   (Lovable)  │                             │  billing.py    │
│              │ ←──── checkout_url ────────  │                │
│              │                             └───────┬────────┘
│              │                                     │ stripe.checkout.Session.create()
│   redirect   │                                     ▼
│   ─────────→ │   ┌──────────────────────────────────────┐
│              │   │         Stripe Checkout               │
│              │   │  (hosted payment page, PCI compliant) │
│              │   └──────────┬───────────────────────────┘
│              │              │ payment success
│              │              ▼
│   redirect   │   ┌──────────────────────┐
│   ←──────────│   │  /billing?status=     │
│              │   │  success              │
│              │   └──────────────────────┘
│              │
│              │   Meanwhile, async:
│              │
│              │   ┌─────────────┐  webhook POST    ┌───────────────┐
│              │   │   Stripe    │ ───────────────→ │  /billing/     │
│              │   │   Server    │                   │  webhook       │
│              │   └─────────────┘                   │                │
│              │                                     │ → verify sig   │
│              │                                     │ → update user  │
│              │                                     │   plan + status│
│              │                                     └───────────────┘
└──────────────┘
```

## Sécurité

- **Pas de données carte** dans notre app (Stripe Checkout hébergé, PCI-DSS compliant)
- **Webhook signé** : vérification HMAC via `stripe.Webhook.construct_event()`
- **Grace period** : après annulation, accès maintenu jusqu'à fin de période payée
- **Past due** : en cas d'échec paiement, 3 tentatives auto par Stripe avant cancel
- **TVA** : `tax_id_collection=True` dans Checkout → Stripe gère la TVA UE automatiquement

## Notes importantes

- Les users existants restent sur `plan=free` (migration ajoute la colonne avec default)
- Le webhook ne nécessite pas d'auth (vérifié par signature Stripe)
- Le Customer Portal permet au user de : changer de carte, annuler, changer de plan
- `effective_plan()` dans subscription.py dégrade automatiquement en free si sub expirée
- Le cron digest continue d'envoyer aux users pro/business (check `limits.email_digest`)
