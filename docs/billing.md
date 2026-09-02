# Facturation Stripe Avenqo

## ResponsabilitÃ©s

La facturation est isolÃ©e du catalogue des modules IA. Stripe gÃ¨re le client, l'abonnement, les paiements, les factures et le portail. Avenqo conserve un snapshot local tenant-scoped pour afficher l'Ã©tat et l'historique.

Les modules restent dans `company_modules`. Ils n'importent jamais le SDK Stripe et n'appellent jamais Stripe directement.

## Plans

| Code | Nom | Parcours |
| --- | --- | --- |
| `demo` | Demo | Stripe Checkout |
| `professional` | Professional | Stripe Checkout |
| `enterprise` | Enterprise | Contact commercial / sur devis |
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

La lecture de l'abonnement exige une session authentifiée. Les mutations et les factures exigent `billing:manage`; le catalogue et le webhook restent publics. Le tenant provient toujours du JWT. Le webhook vérifie la signature Stripe et mémorise chaque `event.id` pour assurer l'idempotence.

## Configuration

Les variables sont listÃ©es dans `backend/.env.example`:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_DEMO`
- `STRIPE_PRICE_PROFESSIONAL`
- `STRIPE_PRICE_CREDIT_DEMO`
- `STRIPE_PRICE_CREDIT_PROFESSIONAL`

Enterprise n'a pas de Price ID fixe et ne peut pas ouvrir de Checkout self-service.

Les Prices de crédits sont des paiements uniques configurés dans Stripe:

- Demo: 6 500 crédits supplémentaires pour 10 USD.
- Professional: 25 000 crédits supplémentaires pour 25 USD.

Les crédits achetés s'accumulent pendant la période de facturation. Après le paiement réussi de la facture de renouvellement (`invoice.paid` avec `billing_reason=subscription_cycle`), Avenqo remet l'usage mensuel et le solde acheté à zéro, puis démarre la nouvelle allocation incluse.

## Réglages Stripe Dashboard requis

- Activer Adaptive Pricing / les devises localisées pour les Prices Demo, Professional et leurs deux packs de crédits utilisés par Checkout. Stripe reste la source autoritaire du montant et de la devise facturés.
- Dans les réglages d'emails clients, activer l'envoi des factures finalisées et des reçus de paiement réussi.
- Dans la configuration du Customer Portal, autoriser l'annulation d'abonnement en fin de période de facturation.
- Abonner l'endpoint webhook aux événements `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated` et `customer.subscription.deleted`.

Stripe crée automatiquement les factures récurrentes des abonnements. Avenqo en conserve un snapshot tenant-scoped (montants, devise, offre, période, état et liens Stripe) après réception du webhook signé.

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
