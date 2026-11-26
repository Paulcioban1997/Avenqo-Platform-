# Architecture Avenqo

## Interfaces et contrat commun

| Interface | Responsabilité | Entrée API et session |
| --- | --- | --- |
| Next.js (`web/`) | Interface SaaS Web principale. Site public, inscription, authentification, espace de travail, modules métier et administration. | `/api/v1` sur la même origine via la réécriture Next.js. Le proxy et les routes `/api/auth/*` gèrent les cookies de session HttpOnly et transmettent l'authentification à FastAPI. |
| Flutter (`frontend/`) | Client mobile et bureau. Le client Flutter Web reste disponible pour les parcours existants qui en dépendent. | Même contrat `/api/v1` via `API_BASE_URL`. Les applications natives utilisent des jetons Bearer avec stockage sécurisé. Le client Web peut utiliser les cookies sur l'origine configurée. |
| FastAPI (`backend/`) | Autorité pour les identités, les permissions et rôles, les abonnements, les crédits IA, les calculs financiers et l'accès aux données d'une organisation. | Application `backend.main:app`. Le routeur dans `backend/app/api/router.py` expose `/api/v1`. Les tâches internes ont des routes séparées. |

L'API déduit l'organisation de la session authentifiée. Les dépendances FastAPI vérifient l'identité, les rôles et, selon le parcours, l'abonnement et l'accès au module. Les services et dépôts SQL filtrent les données par organisation. Les politiques PostgreSQL s'appliquent aux tables qui les déclarent. Les interfaces utilisent les résultats de l'API pour l'affichage, les contrôles de navigation et les erreurs. Une permission affichée côté client ne donne aucun droit d'accès serveur.

### Parcours présents dans les deux clients

| Parcours | Next.js | Flutter |
| --- | --- | --- |
| Connexion et espace de travail | `/login`, `/register`, `/workspace`, `/dashboard` | Authentification, navigation et tableau de bord |
| CRM, Retail et comptabilité | `/crm`, `/retail`, `/accounting` | Écrans CRM, Retail et comptabilité |
| Abonnement, crédits IA et administration | `/billing`, `/admin`, vues de l'espace | Facturation, crédits et console administrateur |
| Assistants IA et voix | Agents et module `/voice` | Assistant et contrôleur vocal Central AI |

Les recouvrements maintiennent des parcours existants. Avant de retirer un écran, tracer les liens, redirections, WebViews, configurations OAuth et clients distribués qui en dépendent. Valider son remplacement avec les mêmes rôles, abonnements et données avant de désactiver la route.

## Modules et agents

Le catalogue sous `modules/registry.py` décrit la disponibilité dans le code. Les API et contrôles d'accès sont sous `backend/app/routers/` et `backend/app/services/`. La disponibilité dans le catalogue, les tests locaux et l'activation réelle dans un environnement sont trois vérifications distinctes.

| Module | État dans le candidat sandbox et validation pertinente |
| --- | --- |
| Retail | Déclaré disponible. API et écrans dans les deux clients. Tests de source active, connecteurs et isolation des données. |
| CRM | Déclaré disponible. API et écrans CRM. L'agenda CRM et le retour OAuth Google ont leurs propres tests. Une synchronisation avec un compte réel dépend de sa configuration. |
| Accounting | Déclaré disponible. API, écrans et agent métier. Tests de classification, permissions et sélection de la source active. |
| OCR / Documents et Legal | Déclarés disponibles. Routes de traitement documentaire et exports. Tester les fichiers autorisés, les droits de lecture et les sorties sur des données de test. |
| Marketing, Media, Workflow Automation et AI Agents | Déclarés disponibles. L'exécution dépend du module activé, du tenant et, selon la tâche, du fournisseur. Vérifier chaque intégration avant de la déclarer validée dans un environnement. |
| Voice | Déclaré disponible et soumis aux droits du module. Simulations Telnyx, tests de tours de parole et d'isolation distincts d'un appel réel. |
| HR | Déclaré disponible. Tests de permissions et de cloisonnement des équipes. |
| Trading | Déclaré disponible. Vérification des sources de marché à distinguer des tests locaux. |
| Appointments | Module autonome au statut `coming_soon`. La planification fait partie du CRM. |

Central AI et les assistants passent par les services Python et le moteur `shared/ai_engine/`. Le serveur sélectionne un fournisseur et autorise les outils embarqués dans le contexte du tenant. Il enregistre l'usage et débite les crédits suivant les règles applicables. Les agents CRM, RetailSense et Accounting utilisent l'API métier et le moteur commun. Les clients n'obtiennent pas d'identifiants fournisseurs.

## Données et services externes

| Flux | Traitement et stockage |
| --- | --- |
| Import ou synchronisation | FastAPI attribue la source à une organisation, valide le fichier ou le connecteur, maintient les métadonnées, puis transmet le jeu de données au moteur d'IA. |
| Prédiction ou génération | Les services résolvent la source autorisée et le modèle. Les données, résultats et artefacts sont associés à l'organisation et, le cas échéant, au module et à la version du modèle. |
| Facturation et crédits | Stripe Checkout et les webhooks passent par FastAPI. L'API applique les droits d'abonnement et maintient les écritures de crédits IA. |
| Agenda et téléphonie | Google Calendar passe par OAuth avec état signé et lié au tenant. Les appels et webhooks Telnyx et les intégrations Retell passent par les services Voice configurés. Les actions métier restent soumises aux permissions de l'appelant. |
| Fournisseurs IA et données | Les adaptateurs incluent OpenAI, Anthropic et Google/Gemini, ainsi que les connecteurs commerce Shopify et WooCommerce. Les fournisseurs sont sélectionnés côté serveur. Leur configuration et leurs capacités actives peuvent varier par environnement. |

PostgreSQL est le moteur des environnements hébergés. Alembic versionne les migrations. SQLite est utilisé pour des tests locaux. Redis et Qdrant couvrent les usages qui les configurent, tels que la limitation de débit ou la mémoire vectorielle. Les artefacts de données et modèles utilisent le stockage configuré côté serveur. Les emplacements locaux comme `var/models/{company_id}/` et `artifacts/company_datasets/` ne font pas partie des sources suivies.

## Déploiement et preuves

| Environnement | Routage et contrôle |
| --- | --- |
| Local | Next.js et Flutter utilisent FastAPI local par défaut. Un client Flutter Web servi sur une origine distincte requiert une URL d'API et une configuration CORS cohérentes. |
| Sandbox | Railway héberge l'API configurée sur `https://avenqo-platform-sandbox.up.railway.app`. Next.js Preview et les cibles explicitement sandbox utilisent cette même origine. `render.yaml` décrit une interface Next.js sandbox. L'environnement Railway, la base, les fournisseurs de test et les webhooks sont à vérifier indépendamment. |
| Production | Cible documentée hors du périmètre des validations sandbox. Next.js est l'interface principale. L'API, les données et les identifiants ont leur propre configuration. |

Le pipeline GitHub Actions teste Next.js, Flutter et FastAPI et vérifie les secrets et les migrations. La génération de SBOM est distincte de l'analyse CrowdStrike Falcon Cloud Security, qui exige des identifiants configurés et des étapes exécutées. Une exécution locale, un état vert de la CI ou une réponse de la route de santé ne remplace pas la vérification authentifiée des parcours sandbox. Voir le [guide de déploiement](deployment.md).

## Dossiers de travail

| Dossier | Usage et conservation |
| --- | --- |
| `scratch/` | Copies de travail et traces transitoires ignorées par Git. Les exports de diagnostic ou sauvegardes éventuelles dépendent de leur usage et de leur rétention. |
| `var/` | Données d'exécution, base locale, modèles, sauvegardes et autres états. Ignoré par Git. |
| `artifacts/` | Sorties générées, jeux de données et SBOM. Ignoré par Git. |
| `loadtest/` | Sources suivies pour les tests de charge sur répliques et services isolés. La configuration de simulation et les scripts sont conservés. |
| `services/voice_speech/` | Worker ASR/TTS expérimental sandbox avec tests et scripts de référence. Les fichiers `__pycache__/` restent des caches ignorés. |
