# Deployment

Ce document a été remplacé par une documentation de déploiement production
détaillée à l'issue de la Phase 34 — voir :

- [docs/production-deployment.md](production-deployment.md) — configuration,
  Docker, base de données, frontend, rate limiting, observabilité, TLS, rollback.
- [docs/release-checklist.md](release-checklist.md) — checklist manuelle avant
  toute mise en production réelle.
- [docs/backup-and-disaster-recovery.md](backup-and-disaster-recovery.md) —
  stratégie de sauvegarde et scénarios de reprise après sinistre.

`backend/Dockerfile` (image de production) et `docker-compose.yml`
(environnement de développement local uniquement) sont disponibles à la
racine du dépôt. `.github/workflows/ci.yml` exécute les tests backend et
Flutter à chaque push/PR sur `main`.

