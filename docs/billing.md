# Facturation Stripe Avenqo

## ResponsabilitÃ©s

La facturation est isolÃ©e du catalogue des modules IA. Stripe gÃ¨re le client, l'abonnement, les paiements, les factures et le portail. Avenqo conserve un snapshot local tenant-scoped pour afficher l'Ã©tat et l'historique.

Les modules restent dans `company_modules`. Ils n'importent jamais le SDK Stripe et n'appellent jamais Stripe directement.

## Plans

| Code | Nom | Parcours |
| --- | --- | --- |
| `demo` | Demo | Stripe Checkout |
| `professional` | Professional | Stripe Checkout |
| `enterprise` | Enterprise | Stripe Checkout |
| `custom_enterprise` | Custom Enterprise | Contact commercial |

Les Price IDs Stripe sont configurÃ©s par environnement. Aucun Price ID n'est codÃ© en dur.

## Routes

| MÃ©thode | Route | ResponsabilitÃ© |
| --- | --- | --- |
| GET | `/api/v1/billing/plans` | Catalogue public des plans |
| GET | `/api/v1/billing/subscription` | Abonnement du tenant courant |
| POST | `/api/v1/billing/checkout` | CrÃ©er une session Checkout |
| POST | `/api/v1/billing/change-plan` | Upgrade ou downgrade avec prorata |
| POST | `/api/v1/billing/cancel` | Annuler en fin de pÃ©riode |
| POST | `/api/v1/billing/portal` | Ouvrir le portail Stripe |
| GET | `/api/v1/billing/invoices` | Historique des factures du tenant |
| POST | `/api/v1/billing/webhook` | Synchroniser les Ã©vÃ©nements signÃ©s |

Toutes les routes sauf le catalogue et le webhook exigent `billing:manage`. Le tenant provient toujours du JWT. Le webhook vÃ©rifie la signature Stripe et mÃ©morise chaque `event.id` pour assurer l'idempotence.

## Configuration

Les variables sont listÃ©es dans `backend/.env.example`:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_DEMO`
- `STRIPE_PRICE_PROFESSIONAL`
- `STRIPE_PRICE_ENTERPRISE`

## Validation

Les tests automatisÃ©s utilisent un fournisseur en mÃ©moire et ne rÃ©alisent aucun appel rÃ©seau:

```powershell
pytest tests/backend/test_billing.py -q
```

La validation externe finale doit Ãªtre exÃ©cutÃ©e avec un compte Stripe en Test Mode et Stripe CLI:

```powershell
stripe listen --forward-to localhost:8000/api/v1/billing/webhook
```

Cette validation doit confirmer Checkout, upgrade, downgrade, annulation, portail et rÃ©ception des factures avant le passage Ã  la Phase 4.
