# Incident 2026-10-10 — secrets exposés dans le dépôt public et rotation

Aucune valeur secrète ne figure dans ce document. Les empreintes affichées par les
outils sont des SHA-256 tronqués, non réversibles.

## 1. Constat

Le dépôt `Paulcioban1997/Avenqo-Platform-` est **public**. `python scripts/scan_git_history_secrets.py`
(qui n'affiche que le type, le fichier et le commit) relève :

| Secret | Fichiers | Première apparition publique |
|---|---|---|
| `CONNECTOR_ENCRYPTION_KEYS` (clé Fernet primaire de production) | `AVENQO_HANDOFF.md`, `tests/test_phase8_5_validation.py`, `tests/test_phase8_9_final_user_journey.py` | 2026-09-12 (`7b7c447`) |
| URL PostgreSQL Railway avec mot de passe (`*.proxy.rlwy.net`) | `scripts/audit_db_diff.py`, `scripts/e2e_prod_smoke_test.py`, `scripts/inspect_db_schema.py`, `scripts/run_migrations.py`, `scripts/verify_prod_dataset.py` | 2026-09-25 (`99b0107`) |

Toutes les branches distantes contiennent ces commits. L'arbre courant est propre
(`tests/security/test_no_committed_secrets.py` l'impose désormais en CI).

**Impact à supposer :** la combinaison URL de base + clé permet de lire la base et de
déchiffrer `commerce_connections.encrypted_credentials` (clés WooCommerce `ck_`/`cs_`,
jetons Shopify) et `crm_calendar_connections.encrypted_credentials` (jetons Google
Calendar). Les deux secrets sont considérés **compromis**. Rotation de la clé seule ne
suffit pas : les identifiants tiers déjà déchiffrables doivent aussi être renouvelés.

## 2. Ordre des opérations (production — autorisation du propriétaire requise)

Chaque étape marquée 🔒 modifie la production et n'est exécutée qu'après accord explicite.

1. 🔒 **Mot de passe PostgreSQL** : régénérer les identifiants du service Postgres Railway
   (production, et sandbox si c'est la même URL), puis mettre à jour `DATABASE_URL` des
   services API, cron de sauvegarde et Telnyx media. Vérifier `/ready`. Consulter les
   journaux de connexion Postgres Railway depuis le 2026-09-25 pour des IP inconnues.
2. **Sauvegarde** : `python scripts/backup_db.py` (dump + artefacts vers S3) avant tout rechiffrement.
3. **Nouvelle clé** : `python scripts/rotate_connector_keys.py generate`. La clé est
   imprimée une seule fois sur stdout ; la copier directement dans Railway, jamais ailleurs.
4. 🔒 **Coexistence** : `CONNECTOR_ENCRYPTION_KEYS=<nouvelle>,<ancienne>` sur l'API et
   les workers, redéploiement. À partir de ce moment toute écriture utilise la nouvelle clé
   et toute ligne existante reste lisible.
5. **État** : `python scripts/rotate_connector_keys.py status` (lecture seule) avec les
   mêmes variables : nombre de lignes par empreinte de clé et lignes indéchiffrables.
6. **Simulation** : `python scripts/rotate_connector_keys.py rotate` (aucune écriture).
7. 🔒 **Rechiffrement** : `python scripts/rotate_connector_keys.py rotate --apply`.
   Lots verrouillés (`SELECT … FOR UPDATE`), validés un par un ; chaque ligne est relue
   avec la seule nouvelle clé et comparée au texte clair d'origine avant écriture.
   Relançable sans effet de bord : les lignes déjà rechiffrées sont ignorées.
8. **Vérification** : `python scripts/rotate_connector_keys.py verify` → code 0 uniquement
   si aucune ligne ne dépend encore de l'ancienne clé et aucune n'est indéchiffrable.
9. 🔒 **Renouvellement des identifiants tiers** (l'ancienne clé ayant pu déchiffrer les données) :
   - WooCommerce : chaque marchand révoque la clé REST dans *WooCommerce → Réglages →
     Avancé → API REST* et reconnecte sa boutique depuis `/connections`.
   - Shopify : désinstaller/réinstaller l'application ou révoquer les jetons depuis le
     Partner Dashboard, puis reconnexion OAuth ; faire tourner `SHOPIFY_CLIENT_SECRET`.
   - Google Calendar : révoquer les jetons (console Google Cloud ou reconnexion
     utilisateur) et faire tourner `GOOGLE_CALENDAR_CLIENT_SECRET` si nécessaire.
   Prévenir les marchands concernés (obligation de notification selon la Loi 25 /
   LPRPDE à évaluer avec le conseiller juridique).
10. 🔒 **Retrait de l'ancienne clé** : seulement après `verify` = 0 et validation
    fonctionnelle (une synchronisation WooCommerce/Shopify et une lecture Google Calendar
    réussies), `CONNECTOR_ENCRYPTION_KEYS=<nouvelle>`.

### Retour arrière

Tant que l'ancienne clé reste configurée : remettre `<ancienne>,<nouvelle>` puis
`rotate --apply` rechiffre tout avec l'ancienne. Restauration complète possible depuis
la sauvegarde de l'étape 2. Ne jamais retirer une clé tant que `verify` ne renvoie pas 0.

## 3. Nettoyage de l'historique Git (🔒 force-push requis)

La réécriture n'annule pas l'exposition (dépôt public, clones et caches possibles) :
elle vient **après** les rotations, jamais à leur place.

1. Prévenir les collaborateurs et agents (Codex, Copilot, Cursor) ; geler les branches.
2. Clone miroir neuf : `git clone --mirror https://github.com/Paulcioban1997/Avenqo-Platform-.git`.
3. Créer **hors du dépôt** un fichier `replacements.txt` contenant une ligne
   `<valeur exacte>==>[REDACTED]` par secret (clé Fernet et chaque URL PostgreSQL).
4. `git filter-repo --replace-text ../replacements.txt` puis vérifier avec
   `python scripts/scan_git_history_secrets.py` sur le miroir (code retour 0 attendu).
5. 🔒 `git push --force --mirror` ; supprimer les branches obsolètes (`copilot/*`, `sandbox/*`).
6. Demander à GitHub Support la purge des vues en cache et des références de PR.
7. Chaque poste de travail reclone ; les anciennes copies locales sont supprimées.
8. Détruire `replacements.txt`.

Envisager de rendre le dépôt privé : il contient aussi des identifiants de tenants,
des adresses courriel de clients et des noms d'hôte d'infrastructure.
