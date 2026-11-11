# Incident 2026-11-11 — exposition `printenv` Postgres Production

État : **ouvert — préparation rotation**. Aucune rotation Production n’a encore été exécutée.
Aucune valeur secrète n’est reproduite dans ce document.

## Faits (sans valeurs)

Lors du diagnostic Alembic P0, une commande `railway ssh` vers le service
**Postgres / environment production** a exécuté un filtre du type
`printenv | awk …` destiné à lister uniquement les **noms** de variables.
La sortie a malgré tout inclus des **valeurs** pour au moins :

| Variable / canal | Nature |
|---|---|
| `POSTGRES_PASSWORD` | Mot de passe rôle `postgres` (superutilisateur) |
| `PGPASSWORD` | Même secret, formulaire client `psql` |
| `DATABASE_PUBLIC_URL` | URL PostgreSQL publique contenant utilisateur + mot de passe + hôte proxy Railway |

Autres clés listées sans preuve d’exposition de valeur dans ce même événement :
`PGPORT`, `PGUSER`, `PGDATABASE`, `PGHOST`, `PGDATA`, `POSTGRES_USER`, `POSTGRES_DB`,
`PG_MAJOR`, `PG_VERSION`, et une entrée `DATABASE_URL` apparemment vide dans ce filtre.

## Visibilité / persistance

| Canal | Risque |
|---|---|
| Sortie outil agent / terminal local Cursor | **Confirmé** — valeurs présentes dans le transcript de session |
| Chat utilisateur / rapports | Doit rester **sans valeurs** (règle respectée dans les réponses) |
| Git / PR / CI logs | **Non observé** pour cet incident (pas de commit de secrets) |
| Railway dashboard logs | Non vérifié exhaustivement ; traiter comme potentiellement capturé |
| Partage / captures d’écran / backups de transcript | Possible si la session a été exportée |

Hypothèse opérationnelle : le secret **`postgres` Production via proxy public**
doit être considéré **compromis jusqu’à révocation**, même si l’accès a été limité
à la session agent.

## Périmètre de rotation (coordonné)

Ne pas éditer seulement `POSTGRES_PASSWORD` dans Railway : sur une base déjà
initialisée, cela **ne change pas** le mot de passe serveur (voir
`docs/incident-38085288-rotation.md`).

Ordre recommandé (GO explicite requis avant exécution) :

1. **Sauvegarde fraîche** vérifiée (`verify_backup`) + preuve de fraîcheur.
2. Inventaire des consommateurs qui utilisent le secret `postgres` / URL publique :
   - service Postgres Railway (variables natives),
   - éventuels scripts/ops locaux ou CLI ayant mémorisé l’URL publique,
   - **pas** l’API `avenqo_app` ni `BACKUP_DATABASE_URL` / `avenqo_backup` si
     leurs mots de passe sont distincts (à confirmer sans les afficher).
3. Générer un **nouveau** mot de passe `postgres` via le mécanisme supporté
   Railway (régénération qui synchronise serveur + variables), **ou**
   `ALTER ROLE postgres PASSWORD …` puis mise à jour des variables dépendantes
   dans la même fenêtre.
4. Mettre à jour uniquement les variables / outils qui consomment encore l’ancien
   secret ; redémarrer les jobs qui casseraient (ops manuels, pas l’API app si
   elle reste sur `avenqo_app`).
5. Preuve de **refus** de l’ancienne URL/mot de passe ; preuve de succès de la
   nouvelle connexion admin locale/socket ou nouvelle URL.
6. Vérifier `/api/v1/health`, `/api/v1/ready`, cron backup, et qu’aucune
   migration n’utilise encore l’ancien secret.

## Non-objectifs de cette rotation

- Ne pas toucher `DATABASE_URL` de l’API (`avenqo_app`) sauf preuve qu’il
  partage le même mot de passe (improbables d’après le diagnostic 2026-11-11).
- Ne pas toucher Stripe, Telnyx, JWT, MFA, clés connecteurs.
- Ne pas réécrire l’historique Git pour cet incident (pas de secret commité).
- Ne pas désactiver le rôle `postgres` requis par l’admin Railway.

## Critère de clôture

Incident clos seulement après : nouveau secret actif, ancien secret refusé,
API/backups/`/ready` OK, et confirmation qu’aucun consommateur restant n’utilise
l’URL publique compromise.
