# Checklist de release — Avenqo

À exécuter avant toute mise en production réelle (au-delà de cette Phase 34).
Cocher chaque ligne manuellement ; ne jamais déclarer une release prête si
une case reste non cochée sans justification écrite.

## Tests automatisés

- [ ] `python -m pytest tests/backend -q` → 0 échec
- [ ] `python -m pytest tests/security -q` → 0 échec
- [ ] `python -m pytest tests/payments -q` → 0 échec
- [ ] `flutter analyze` → 0 erreur
- [ ] `flutter test` → 0 échec
- [ ] `flutter build web --release --dart-define=API_BASE_URL=<url prod>` → build réussi

## Sécurité

- [ ] `ENVIRONMENT=production` positionné → `/docs`, `/redoc`, `/openapi.json` retournent 404
- [ ] `AUTH_JWT_SECRET` réel (≠ valeur de développement), ≥32 caractères, stocké dans un secret manager
- [ ] `ALLOWED_HOSTS` restreint aux domaines réels (pas `*`)
- [ ] `CORS_ORIGINS` restreint aux domaines frontend réels
- [ ] En-têtes de sécurité présents sur une requête réelle (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`)
- [ ] Aucun secret présent dans `git status` / historique du commit de release
- [ ] `GET /api/v1/ready` retourne `status: "ready"` sur l'environnement cible

## Isolation multi-tenant

- [ ] Suite `tests/security/test_idor_and_isolation.py` verte
- [ ] Revue manuelle : un utilisateur d'une entreprise ne peut pas accéder aux
      conversations/factures/employés d'une autre entreprise via manipulation d'ID

## Base de données

- [ ] Stratégie de migration documentée et acceptée pour cette release (voir
      `docs/production-deployment.md` §4 — actuellement `create_all()`, pas
      d'Alembic : confirmer que c'est acceptable pour CETTE release précise)
- [ ] Sauvegarde de la base effectuée juste avant le déploiement
- [ ] Procédure de restauration testée au moins une fois (voir
      `docs/backup-and-disaster-recovery.md`)

## Configuration & secrets

- [ ] Tous les secrets injectés via variables d'environnement / secret manager
      (jamais un fichier `.env` commité)
- [ ] Clés Stripe/AI en mode production (pas les clés de test)
- [ ] Webhook Stripe pointant vers l'URL de production et signature vérifiée

## Rollback

- [ ] Image précédente conservée et redéployable en < 5 minutes
- [ ] Vérifié qu'aucune migration de schéma cassante n'a eu lieu depuis la dernière release stable

## Décision finale

- [ ] Rapport **PHASE 34 COMPLETED** relu, verdict `READY`/`NOT READY` accepté par le responsable produit avant tout déploiement réel
