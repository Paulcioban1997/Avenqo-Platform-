# Incident 2026-11-11 — exposition `printenv` Postgres Production

État : **fermé — rotation exécutée 2026-11-12**. Aucune valeur secrète n’est reproduite dans ce document.

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

## Rotation exécutée (GO 2026-11-11 / exécution 2026-11-12)

Préconditions :

- Sauvegarde fraîche `20261112T000433544750Z` — verify=ok, révision `0076`, artefacts présents
- Consommateurs distincts confirmés : API `avenqo_app`, backup `avenqo_backup` (mots de passe distincts)
- Continuité API : non impactée (n’utilise pas le secret `postgres`)

Actions :

1. `ALTER ROLE postgres` via socket local Unix (service Postgres)
2. Mise à jour Railway (service Postgres, `--skip-deploys`) : `POSTGRES_PASSWORD`, `PGPASSWORD`, `DATABASE_PUBLIC_URL`
3. Preuve TCP : nouveau mot de passe accepté ; **ancien mot de passe refusé**
4. Socket local `postgres` : OK
5. Post-checks : `/ready` ready+migrations=ok ; `/health` healthy ; backup verify=ok

## Critère de clôture

| Critère | Statut |
|---|---|
| Nouveau secret actif | OK |
| Ancien secret refusé | OK |
| API `/ready` `/health` | OK |
| Sauvegardes | OK |
| Pas de secret dans Git/chat | OK |
