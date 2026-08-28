# Déploiement Production — Avenqo (Phase 34 + Remédiation finale V1)

> Ce document décrit l'état RÉEL du support de déploiement à l'issue de la
> remédiation finale post-Phase 34 — y compris ses limites connues. Aucune
> affirmation ici ne doit être interprétée comme "prêt pour un lancement à
> grande échelle sans validation manuelle du propriétaire" ; voir
> `docs/release-checklist.md` et le rapport AVENQO V1 FINAL REMEDIATION
> COMPLETED pour le verdict de mise en production ("READY FOR MANUAL OWNER
> VALIDATION", explicitement PAS "READY FOR PUBLIC PRODUCTION").

## 1. Vue d'ensemble

| Composant | Techno | État Phase 34 |
|---|---|---|
| Backend | FastAPI + SQLAlchemy (Python 3.11) | Conteneurisable (`backend/Dockerfile`) |
| Base de données | SQLite (dev/test), pas de Postgres câblé | ⚠️ Limite — voir §4 |
| Frontend | Flutter Web | Build statique, URL API configurable au build |
| Reverse proxy / TLS | Non fourni par ce dépôt | À la charge de l'infrastructure d'hébergement |
| CI | `.github/workflows/ci.yml` | Tests backend + Flutter analyze/test |

## 2. Variables d'environnement (production)

Toutes les variables sont lues par `backend/app/config/settings.py`. **Aucun
secret réel ne doit jamais être commité** — utiliser le gestionnaire de
secrets de la plateforme d'hébergement (jamais `backend/.env` en production).

| Variable | Obligatoire en prod | Notes |
|---|---|---|
| `ENVIRONMENT=production` | Oui | Active la validation stricte au démarrage, désactive `/docs`/`/redoc`/`/openapi.json`, force `Strict-Transport-Security`. |
| `AUTH_JWT_SECRET` | Oui | ≥32 caractères, doit différer de la valeur de développement par défaut (le démarrage échoue sinon). |
| `SMTP_HOST` (+ `SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL`) | Non | Optionnel. Sans SMTP, les fonctionnalités email sont dégradées sans bloquer le démarrage. |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_DEMO`, `STRIPE_PRICE_PROFESSIONAL` | Oui | Requis pour la facturation self-service Demo/Professional. Enterprise reste sur devis, sans prix Stripe fixe. |
| `DATABASE_URL` | Oui | Doit être explicitement défini en production. Voir §4 — limite SQLite connue. |
| `FRONTEND_URL` | Oui | Origine HTTPS utilisée pour les retours Checkout/Customer Portal. |
| `ALLOWED_HOSTS` | Oui | Liste séparée par virgules (ex. `api.avenqo.ca`) ; `*` est refusé en production. |
| `CORS_ORIGINS` | Oui | Domaines HTTPS exacts du frontend (ex. `https://app.avenqo.ca`) ; les origines localhost sont refusées en production. |
| `RATE_LIMIT_*` | Optionnel | Voir §6 — limite technique par défaut raisonnable, ajustable. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_AI_API_KEY` | Selon fournisseurs actifs | Voir `AI_PRIMARY_PROVIDER`/`AI_FALLBACK_PROVIDER_*`. |

## 3. Démarrage / arrêt du backend

```bash
# Construction de l'image
docker build -f backend/Dockerfile -t avenqo-backend:latest .

# Démarrage (exemple — injecter les vraies variables via le secret manager)
docker run -p 8000:8000 --env-file /run/secrets/avenqo.env avenqo-backend:latest
```

Vérification de démarrage :
- `GET /api/v1/health` → doit retourner `200` avec `environment: "production"`.
- `GET /api/v1/ready` → doit retourner `status: "ready"` (sinon investiguer avant
  de router du trafic ; ne jamais ignorer un `degraded`).

Arrêt : envoyer `SIGTERM` (comportement par défaut de `docker stop` /
orchestrateur) ; Uvicorn termine les requêtes en cours avant de s'arrêter.

## 4. Base de données — migrations, honnêteté SQLite/PostgreSQL

**État actuel (remédiation finale)** : les migrations de schéma sont gérées
par **Alembic** (`alembic.ini` + `alembic/` à la racine du dépôt). Le schéma
n'est **plus jamais créé via `Base.metadata.create_all()` en production** —
`backend/main.py` (lifespan) ne l'appelle que si `ENVIRONMENT` n'est pas
`production`/`prod` (confort dev/test uniquement). En production, le schéma
DOIT être amené au bon état via `alembic upgrade head` avant le démarrage de
l'application (voir §9 — ordre de déploiement officiel).

- `alembic/versions/0001_baseline_schema.py` : schéma complet initial (26 tables).
- `alembic/versions/0002_audit_log_indexes.py` : exemple réel de migration
  incrémentale (ajout d'index sur `audit_log_entries`).
- Stratégie base EXISTANTE (déjà en production avant l'introduction
  d'Alembic) : `alembic stamp <revision_correspondant_au_schéma_actuel>` puis
  `alembic upgrade head` — ne rejoue JAMAIS le DDL des tables déjà présentes.
  Validé par `tests/backend/test_phase34_migrations.py::test_existing_database_baseline_stamp_strategy`.
- Stratégie base FRAÎCHE : `alembic upgrade head` directement depuis une base
  vide. Validé par les autres tests du même fichier.

**Honnêteté SQLite vs PostgreSQL (revue de la remédiation finale)** :

| Scénario | SQLite acceptable ? |
|---|---|
| Développement / tests / démo | ✅ Oui |
| Premier lancement V1, **mono-instance**, faible trafic concurrent | ✅ Oui, avec réserve (voir ci-dessous) |
| Déploiement **multi-instances** (plusieurs workers/replicas backend) | ❌ Non — SQLite ne garantit pas des écritures concurrentes fiables entre plusieurs processus applicatifs distincts |
| Fort trafic / haute disponibilité | ❌ Non |

`DATABASE_URL` est lu génériquement par SQLAlchemy (`create_engine(...)`) —
**aucun changement de code n'est requis** pour pointer vers PostgreSQL ; seul
un driver (ex. `psycopg`) devrait être ajouté à `requirements.txt` le jour où
ce choix est fait. Ce driver n'est **pas** ajouté préventivement dans cette
remédiation (pas d'infrastructure non requise à ce stade, conformément à la
consigne de ne pas anticiper de travaux hors périmètre).

**Conclusion honnête** : SQLite est acceptable pour un lancement V1
mono-instance à faible trafic, à condition que les sauvegardes régulières
(voir §10) soient en place. Ce n'est PAS un choix approprié pour un scale-out
multi-instances — dans ce cas, migrer vers PostgreSQL AVANT le scale-out.

## 5. Frontend (Flutter Web)

L'URL de l'API backend est configurable au build, jamais codée en dur :

```bash
flutter build web --release \
  --dart-define=API_BASE_URL=https://api.avenqo.ca/api/v1
```

Le résultat (`frontend/build/web`) est un ensemble de fichiers statiques —
servir derrière un CDN/reverse proxy avec HTTPS obligatoire.

## 6. Rate limiting — revue finale (remédiation)

Le limiteur (`backend/app/core/rate_limit.py`) est une fenêtre glissante
**en mémoire, par process**, exposé via l'interface `RateLimiter` (protocole
avec `hit()`/`reset()`) et injecté via `set_rate_limiter()`.

- **Architecture de déploiement prévue pour ce V1** : mono-instance (un seul
  processus/worker backend). Dans ce cas, **un rate limiting distribué N'EST
  PAS REQUIS** — le compteur en mémoire reflète fidèlement le trafic réel.
- Si un déploiement multi-instances devient nécessaire plus tard, chaque
  processus aurait son propre compteur (limite réelle = limite configurée ×
  nombre d'instances) — il faudra alors implémenter un `DistributedRateLimiter`
  (ex. Redis `INCR`+`EXPIRE`) conforme au protocole `RateLimiter` et l'activer
  via `set_rate_limiter(...)`, sans modifier les routes existantes.
- Aucune installation de Redis (ou autre infrastructure) n'a été ajoutée dans
  cette remédiation — non requise pour un lancement mono-instance.

## 7. Observabilité

- Chaque requête reçoit un `X-Request-ID` (généré ou repris de l'en-tête
  entrant), propagé dans tous les logs applicatifs via `contextvars`
  (y compris les logs de l'AI Gateway).
- Les exceptions non gérées sont désormais journalisées côté serveur
  (`logger.exception(...)`) sans jamais exposer de trace au client (réponse
  JSON générique `INTERNAL_SERVER_ERROR`).
- Aucun système d'agrégation de logs (ex. ELK, Datadog) n'est fourni par ce
  dépôt — à brancher côté infrastructure d'hébergement (stdout/stderr du
  conteneur suffit pour la plupart des plateformes gérées).

## 8. HTTPS / TLS

Ce dépôt ne termine pas TLS lui-même. `Strict-Transport-Security` est ajouté
automatiquement par `SecurityHeadersMiddleware` quand `ENVIRONMENT=production`,
en supposant que la terminaison TLS réelle est faite par le reverse
proxy/load balancer de la plateforme d'hébergement (ex. Cloud Run, Fly.io,
Render, nginx géré). S'assurer que ce composant redirige HTTP→HTTPS.

## 9. Ordre de déploiement officiel (remédiation finale)

1. Configurer l'environnement (`ENVIRONMENT=production`, toutes les variables §2).
2. Vérifier les secrets (aucun secret par défaut/dev, tous injectés via le
   gestionnaire de secrets de l'hébergeur).
3. Sauvegarde de la base de données si une mise à niveau (upgrade) est en
   cours (`python scripts/backup_db.py` — voir `docs/backup-and-disaster-recovery.md`).
4. Exécuter les migrations Alembic (`alembic upgrade head`).
5. Déployer le backend (nouvelle image/conteneur).
6. Vérifier `/api/v1/health` et `/api/v1/ready`.
7. Déployer le build Flutter (fichiers statiques).
8. Vérifier la configuration du webhook Stripe (URL, secret à jour).
9. Exécuter des tests de fumée (smoke tests) sur les parcours critiques.
10. Surveiller les logs/erreurs pendant la période suivant le déploiement.

## 10. Sauvegarde et restauration

Voir `docs/backup-and-disaster-recovery.md` pour la procédure complète
(création, vérification par somme de contrôle, restauration, inclusions et
exclusions, interaction avec les migrations).

## 11. Rollback

Avec Alembic en place, un rollback applicatif (redéployer l'image précédente)
N'EST PAS toujours sûr s'il a été accompagné d'une migration de schéma :

- `alembic downgrade <revision_précédente>` peut être destructif pour des
  migrations qui suppriment des colonnes/tables (perte de données écrites
  depuis la montée de version) — **ne jamais downgrade en production sans
  avoir d'abord pris une sauvegarde fraîche** (§10).
- En cas de doute sur la sécurité d'un downgrade, **préférer une restauration
  depuis la dernière sauvegarde valide** (`python scripts/restore_db.py`)
  plutôt qu'un `alembic downgrade` aveugle.
- Rollback applicatif seul (sans changement de schéma) : toujours sûr, revenir
  à l'image précédente suffit.
