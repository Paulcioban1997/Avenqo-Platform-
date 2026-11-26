# Déploiement Avenqo

La [référence d'architecture](ARCHITECTURE.md) décrit les clients, les flux et le rôle du backend. Le [guide de production](production-deployment.md) documente la cible de production indépendamment de la procédure sandbox.

## Cibles sandbox

| Composant | Configuration dans le dépôt |
| --- | --- |
| FastAPI | Railway. L'image utilise `backend/Dockerfile`. `railway.json` déclare la commande de démarrage et `/api/v1/health`. L'URL attendue est `https://avenqo-platform-sandbox.up.railway.app`. |
| Next.js | `web/` est la racine du SaaS Web. Le resolver utilise l'API Railway sandbox en Preview, en mode `AVENQO_ENVIRONMENT=sandbox` et sur les branches sandbox reconnues par Vercel. `render.yaml` décrit aussi un service Web sandbox sur la branche d'intégration. |
| Flutter | Client natif et parcours Web existants. `frontend/vercel-build.sh` utilise le resolver de cible pour les builds Flutter Web Vercel. Pour un build sandbox manuel, utiliser `--dart-define=API_BASE_URL=https://avenqo-platform-sandbox.up.railway.app/api/v1`. Pour un client Web sur une autre origine, configurer CORS côté API avec l'origine exacte. |
| PostgreSQL et stockage | Base, volumes, sauvegardes et comptes fournisseurs propres à la sandbox. Vérifier l'identité de l'environnement et la branche réellement déployée avant de lancer les migrations ou les essais d'intégration. |

La branche d'intégration du Blueprint est `integration/avenqo-sandbox-latest-20261113`. La configuration de la console de chaque fournisseur détermine le déclencheur réel du déploiement. Vérifier le SHA publié et l'identité de l'API. Une réponse de santé seule ne valide pas la version, la base ou les fournisseurs.

## Vérification sandbox

1. Vérifier les résultats GitHub Actions pour le SHA candidat. Le workflow CI couvre Next.js, Flutter, FastAPI, le scan des secrets et la répétition des migrations sur une base isolée. Pour Falcon Cloud Security, inspecter les étapes du run. Le SBOM peut être généré même si les scans Falcon ont été ignorés.
2. Après déploiement, vérifier la route de santé Railway, puis les routes publiques `/`, `/login`, `/register` et la redirection `/signup` sur l'origine sandbox Next.js. Confirmer que les appels `/api/v1` et le renouvellement de session ciblent la même API.
3. Utiliser deux tenants de test et des rôles distincts pour vérifier l'authentification, les permissions, les droits d'abonnement et le refus des données d'un autre tenant. Vérifier CRM, Accounting, Retail, facturation et crédits avec les mêmes données de test sur les clients pris en charge.
4. Vérifier séparément les intégrations configurées, dont Google Calendar, Stripe en mode test et Voice. Pour Voice, distinguer simulation et appel réel, et vérifier l'ordre des tours de parole, le contexte et la limite des permissions.

