# P0 — Export indépendant de `/data/artifacts` sans Railway Pro

Statut : procédure préparée et testée avec fichiers fictifs. **Aucune étape de production ci-dessous n'a été exécutée.** L'approbation du propriétaire est requise avant les étapes P2 à P5.

## Identité et limites

- Projet `062bbe91-68e7-4e79-8de7-cffeb8a5f5cd`, environnement Production `b9b03d41-2a67-4aab-a6f6-32939d8b81e0`, service API `24a2afc3-36f8-46d0-b79d-b323755a83f3`.
- Volume `bb60eade-4548-48d0-a8f6-0e7eeb238c6e`, instance `c3d2d236-4721-4b48-af51-73a1bfff682b`, monté à `/data/artifacts`; dernier relevé : 135,487488 Mo utilisés, état READY, aucune sauvegarde native.
- Le service est déjà CRASHED. `railway volume files` a échoué par timeout SFTP et `railway ssh` a refusé l'accès car aucun conteneur ne tourne. `railway volume browse` utilise le même chemin d'accès. SCP/SFTP traversent également le conteneur en cours d'exécution. Réessayer une fois si Railway change de comportement, mais ne pas multiplier les tentatives identiques.
- Railway n'expose pas un montage simultané sûr du même volume sur un autre service. **Ne jamais détacher, déplacer, cloner par montage concurrent, restaurer ni supprimer le volume.** Le conteneur temporaire doit être un *nouveau déploiement du service API existant*, avec son montage inchangé.
- La garantie « lecture seule » est au niveau du programme : l'exporteur ne crée, ne modifie et ne supprime aucun chemin sous `/data/artifacts`. Le montage Railway reste techniquement accessible en écriture ; aucune promesse de montage système `ro` n'est faite.

## Préparation locale, sans production

Exécuter depuis `C:\Python-Projects\Avenqo-artifact-export-prep` :

```powershell
git status --short --branch
python -m pytest -q tests/backend/test_artifact_volume_export.py
python -m compileall -q scripts/export_artifact_volume.py
git rev-parse HEAD
```

Conserver le SHA du commit final de cette branche. Ne pas modifier la branche RC1 ni la branche `main`. Le `backend/Dockerfile.artifact-export` ne copie que l'exporteur ; il n'inclut pas `backend/docker-entrypoint.sh`, FastAPI, Alembic, les connecteurs, Stripe ou Telnyx. `railway.json` supprime la commande de prédéploiement, le healthcheck HTTP, le cron et les redémarrages. **Ce fichier est propre à la branche d'export ; il ne doit jamais être fusionné dans une branche applicative.**

## P1 — Préparer la clé hors de Railway

Sur le poste du propriétaire, créer un dossier privé **hors du dépôt et hors des dossiers synchronisés automatiquement**, puis générer une nouvelle paire RSA 3072 avec une phrase de passe saisie à l'invite, jamais dans le chat, un commit ou une ligne de commande :

```powershell
$secureDir = Join-Path $env:USERPROFILE 'Avenqo-Private-Exports'
New-Item -ItemType Directory -Path $secureDir -Force | Out-Null
python scripts/export_artifact_volume.py keygen-local --private-key (Join-Path $secureDir 'volume-private.pem') --public-key (Join-Path $secureDir 'volume-public.pem')
```

L'outil refuse d'écraser une clé existante. Le fichier privé est chiffré. Le conserver avec sa phrase de passe dans deux emplacements contrôlés par le propriétaire. **Ne jamais télécharger la clé privée vers Railway ni GitHub.** Le contenu de la clé publique seulement peut être encodé pour la variable Railway :

```powershell
$recipientPublicB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $secureDir 'volume-public.pem')))
```

`$recipientPublicB64` est une clé *publique* ; la saisir directement dans l'interface Railway, sans la publier dans le chat. La création de cette variable Production n'est pas autorisée par le mandat actuel.

## P2 — Contrôles avant intervention Production (après nouvelle autorisation)

```powershell
railway volume list --project 062bbe91-68e7-4e79-8de7-cffeb8a5f5cd --environment b9b03d41-2a67-4aab-a6f6-32939d8b81e0 --service 24a2afc3-36f8-46d0-b79d-b323755a83f3 --json
railway deployment list --project 062bbe91-68e7-4e79-8de7-cffeb8a5f5cd --environment b9b03d41-2a67-4aab-a6f6-32939d8b81e0 --service 24a2afc3-36f8-46d0-b79d-b323755a83f3 --limit 5 --json
```

Dans Railway, confirmer : le même volume et chemin, source et configuration de service actuelles sauvegardées pour retour arrière, aucune modification en attente sur d'autres services, bucket S3 Production existant `avenqo-backups-u7bgklgz2`, variables existantes `ARTIFACT_ROOT`, `BACKUP_S3_ENDPOINT_URL`, `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY`, `ENVIRONMENT` présentes et pointant vers Production. Ne révéler aucune valeur secrète. Vérifier le nom du bucket et le domaine HTTPS ; si un point ne correspond pas, **NO-GO**. Le script valide aussi les identifiants Railway du projet, de l'environnement et du service et force SigV4 avec région de signature `auto` sans toucher à la région physique.

Vérifier depuis un contexte autorisé que les identifiants S3 existants permettent un `HeadBucket`/`ListObjectsV2` en lecture seule. Si ce contrôle échoue, arrêter ; aucune rotation improvisée de clé.

## P3 — Intervention unique sur le service API existant (après nouvelle autorisation)

1. Dans Railway Production, ajouter **uniquement** `ARTIFACT_EXPORT_RECIPIENT_PUBLIC_KEY_B64` au service `Avenqo-Platform-`, avec la clé publique encodée. Ne changer aucune autre variable, aucun secret existant, aucune liaison de volume, aucune région, aucun autre service.
2. Contrôler avant application le lot exact : un seul service API Production, une variable publique supplémentaire et le déploiement local de la branche d'export. Si le lot diffère ou si Railway refuse, arrêter.
3. Déployer localement ce commit précis depuis le worktree après `git rev-parse HEAD` et `git status --short` propres. Cette commande **est un déploiement Production et reste interdite sans nouvelle approbation** :

```powershell
railway up --project 062bbe91-68e7-4e79-8de7-cffeb8a5f5cd --environment b9b03d41-2a67-4aab-a6f6-32939d8b81e0 --service 24a2afc3-36f8-46d0-b79d-b323755a83f3 --message 'P0 read-only encrypted artifact export'
```

4. Vérifier dans les Build Logs que `backend/Dockerfile.artifact-export` a réellement été utilisé. Si l'image ou la commande effective diffère, interrompre avant l'exécution ; ne pas tenter de la « réparer » par modification de secrets. Le script termine normalement avec un code 0 ; un état Railway `COMPLETED` est attendu pour cette tâche ponctuelle, et ne signifie **pas** que l'API est rétablie.
5. Le seul objet nouveau attendu est `avenqo-backups-u7bgklgz2/p0-volume-export/v1/<horodatage>-<UUID>.avq`. Le journal JSON doit annoncer `uploaded_and_remote_sha256_verified`, `file_count > 0`, `source_bytes > 0`, tailles de l'archive et empreintes SHA-256. Le fichier tar en clair n'existe que sur disque éphémère du conteneur pendant l'exécution ; il est supprimé par le dossier temporaire à la fin normale. Le script ne touche ni à PostgreSQL ni aux anciennes archives.

## P4 — Vérifier et conserver une deuxième copie indépendante

Depuis l'interface du bucket Railway, télécharger **l'objet `.avq` exact annoncé par les logs** sur le poste du propriétaire. Aucun identifiant S3 n'est copié dans le terminal. Puis comparer l'empreinte locale à `cipher_sha256` du journal :

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\CHEMIN\VERS\archive.avq'
```

Conserver la copie `.avq` sur un disque chiffré ou dans un stockage contrôlé par le propriétaire **hors du workspace Railway** ; vérifier la taille, la somme SHA-256 et la possibilité de relire cette copie. Le bucket Railway est indépendant du volume, mais pas du compte Railway ; cette deuxième copie est nécessaire avant les migrations. Aucun fournisseur ni espace gratuit n'est supposé disponible sans vérification.

Dans un dossier **neuf et isolé du dépôt et des services Railway**, lancer :

```powershell
python scripts/export_artifact_volume.py restore-local --archive 'C:\CHEMIN\VERS\archive.avq' --private-key (Join-Path $secureDir 'volume-private.pem') --target 'C:\CHEMIN\VERS\restauration-isolee'
```

La phrase de passe est demandée sans affichage. La commande refuse un dossier cible déjà existant, authentifie l'archive, déchiffre, valide le manifeste, la taille et le SHA-256 de **chaque fichier**. Comparer `files_verified` et `directories_verified` à l'inventaire du journal d'export. Conserver les deux copies chiffrées et la clé privée protégée. Ne jamais restaurer sur le volume Production.

## GO / NO-GO et retour à l'état initial

**GO pour la future reprise V1** seulement si l'export Production a un code 0, l'objet S3 est présent et relisible, son SHA-256 distant et local correspondent, la restauration isolée vérifie tous les fichiers, une deuxième copie chiffrée hors Railway est conservée et aucune archive existante n'a disparu. Ces preuves sont distinctes de la restauration PostgreSQL déjà testée.

**Arrêt immédiat** si l'identité service/volume/bucket ne correspond pas, l'image effective n'est pas l'exporteur, l'export voit des liens ou fichiers spéciaux, un fichier change pendant la lecture, le total dépasse 500 Mo ou 50 000 fichiers, S3 refuse l'accès, le hash distant diffère, la restauration isolée échoue ou le lot Railway inclut un autre service. Conserver tous les fichiers et objets existants ; ne rien supprimer pour recommencer.

En cas d'échec, ne pas relancer automatiquement et ne pas réactiver l'ancien `docker-entrypoint.sh` qui peut modifier propriétaires et droits du volume. L'API était déjà CRASHED avant l'export. Sauvegarder la configuration antérieure du service et préparer son rétablissement dans l'intervention V1 approuvée séparément ; ne pas exécuter de migration ni de redémarrage applicatif avant un export validé. Le volume et le bucket ne sont jamais détachés, remplacés ou effacés.

**Coût estimatif** : l'archive de 135,49 Mo représente environ 0,135 Go avant compression/chiffrement ; à $0,015/Go-mois, stockage autour de $0,002/mois, et à $0,05/Go d'egress service pour l'upload, autour de $0,007, plus quelques minutes de CPU/RAM. Les montants réels dépendent de la taille compressée, de la facturation Railway, du second stockage et de la durée du job. Pas de changement de forfait Pro ni de GPU. Aucune dépense n'a été engagée dans cette préparation.
