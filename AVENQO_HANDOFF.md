# AVENQO — Point de Reprise Technique (Handoff)

**Date** : 2026-09-20  
**Branche** : `main`  
**Environnement actif** : Production (`api.avenqo.ca` / `avenqo.ca`)

---

## 1. Conservation des Fichiers & Stockage Persistant

### 1.1 Cause racine vérifiée de la perte des fichiers
- En environnement **sandbox**, un volume (`avenqo-platform--volume`) était attaché à `/data/artifacts` avec `ARTIFACT_ROOT=/data/artifacts`.
- En environnement **production**, le service Railway `Avenqo-Platform-` n'avait **aucun volume attaché** (`volumes: []`).
- La variable `ARTIFACT_ROOT` n'était pas définie en production, ce qui faisait basculer le code sur le chemin par défaut `var/artifacts`.
- Les fichiers bruts et nettoyés étaient enregistrés directement sur le système de fichiers **éphémère** du conteneur Docker. À chaque nouveau déploiement ou redémarrage du conteneur, l'ensemble des fichiers était irrémédiablement effacé.

### 1.2 Correctifs de stockage appliqués en Production
1. **Création et montage du volume persistant Railway** :
   - Nom : `avenqo-platform--volume-nU6W`
   - ID : `bb60eade-4548-48d0-a8f6-0e7eeb238c6e`
   - Service : `Avenqo-Platform-` (Production)
   - Point de montage conteneur : `/data/artifacts`
   - Taille : 5 000 Mo (extensible)
2. **Configuration de la variable d'environnement** :
   - `ARTIFACT_ROOT=/data/artifacts` définie sur le service production Railway.
3. **Permissions au démarrage** :
   - `backend/docker-entrypoint.sh` valide automatiquement l'appartenance `avenqo:avenqo` et les permissions `2770` sur `$ARTIFACT_ROOT` avant le passage à l'utilisateur applicatif non-privilégié.

---

## 2. Dataset Orphelin & Fichiers Manquants

### 2.1 Traitement du dataset orphelin (Avenqo_Plan_de_Montage_Complet.xlsx)
- **Recherche de copie autorisée** :
  - Sauvegardes S3 (`avenqo-backups-u7bgklgz2`) : contiennent uniquement les dumps SQL PostgreSQL quotidiens de 07:00 UTC, aucun artefact fichier.
  - Stockage local de l'espace de travail : Le fichier source original a été retrouvé sur `C:\Users\paulm\OneDrive\Desktop\Avenqo\Avenqo_Plan_de_Montage_Complet.xlsx`.
  - **Vérification de l'intégrité** : Le hash SHA256 calculé (`f37ddf4916425681beec92863e9df1cd81cdf78db7de0479a1af65345fadfce0`) correspond **exactement** au checksum enregistré dans la table `dataset_versions` (version 18, 8 lignes, 10 colonnes).
- **Restauration** :
  - Le fichier a été téléversé directement sur le volume persistant de production à son emplacement canonique : `/company_datasets/9c97cb94-e9f9-46fb-afd4-8a1d21019cff/datasets/7d757146-97b7-43e5-8e84-f1aa0ab5afcd/v1/raw/Avenqo_Plan_de_Montage_Complet.xlsx`.
  - La base de données PostgreSQL de production a été mise à jour pour pointer vers ce chemin persistant.

### 2.2 Transparence et gestion des datasets sans source physique
- Aucun dataset n'est masqué silencieusement en cas de fichier manquant.
- Le schéma `DatasetResponse` intègre désormais explicitement `source_missing: bool` et `source_missing_message: str | None`.
- La route `GET /api/v1/datasets` renvoie les entrées dégradées avec `pipeline_status: "source_missing"`.
- **Interface UI (`connections-view.tsx`)** :
  - Statut explicite affiché dans le tableau : badge ambre **« Fichier source indisponible »**.
  - Action directe : bouton **« Réimporter »** permettant de relancer immédiatement l'import du fichier.
  - Modale d'aperçu : bandeau d'alerte informant que le fichier doit être réimporté pour relancer les prédictions et l'analyse.

---

## 2. Dataset Orphelin, Fichiers Manquants & Sauvegardes Étendues

### 2.1 Traitement du dataset orphelin (Avenqo_Plan_de_Montage_Complet.xlsx)
- **Recherche de copie autorisée** :
  - Sauvegardes S3 initiales (`avenqo-backups-u7bgklgz2`) : contenaient uniquement les dumps SQL PostgreSQL quotidiens de 07:00 UTC, aucun artefact fichier.
  - Stockage local de l'espace de travail : Le fichier source original a été retrouvé sur `C:\Users\paulm\OneDrive\Desktop\Avenqo\Avenqo_Plan_de_Montage_Complet.xlsx`.
  - **Vérification de l'intégrité** : Le hash SHA256 calculé (`f37ddf4916425681beec92863e9df1cd81cdf78db7de0479a1af65345fadfce0`) correspond **exactement** au checksum enregistré dans la table `dataset_versions` (version 18, 8 lignes, 10 colonnes).
- **Restauration** :
  - Le fichier a été téléversé directement sur le volume persistant de production à son emplacement canonique : `/company_datasets/9c97cb94-e9f9-46fb-afd4-8a1d21019cff/datasets/7d757146-97b7-43e5-8e84-f1aa0ab5afcd/v1/raw/Avenqo_Plan_de_Montage_Complet.xlsx`.
  - La base de données PostgreSQL de production a été mise à jour pour pointer vers ce chemin persistant.

### 2.2 Transparence et gestion des datasets sans source physique
- Aucun dataset n'est masqué silencieusement en cas de fichier manquant.
- Le schéma `DatasetResponse` intègre désormais explicitement `source_missing: bool` et `source_missing_message: str | None`.
- La route `GET /api/v1/datasets` renvoie les entrées dégradées avec `pipeline_status: "source_missing"`.
- **Interface UI (`connections-view.tsx`)** :
  - Statut explicite affiché dans le tableau : badge ambre **« Fichier source indisponible »**.
  - Action directe : bouton **« Réimporter »** permettant de relancer immédiatement l'import du fichier.
  - Modale d'aperçu : bandeau d'alerte informant que le fichier doit être réimporté pour relancer les prédictions et l'analyse.

### 2.3 Extension du système de sauvegarde aux fichiers originaux et traités
- Le service `BackupService` (`backend/app/services/backup_service.py`) a été étendu pour archiver l'intégralité du répertoire `$ARTIFACT_ROOT` (`_artifacts.tar.gz`) lors de chaque exécution de sauvegarde (locale et S3).
- **Intégrité cryptographique** : Les métadonnées `.json` enregistrent désormais l'empreinte SHA256 (`artifacts_checksum_sha256`) et la taille en octets de l'archive d'artefacts.
- **Restauration isolée validée** : La méthode `restore_artifacts(backup_id, target_dir)` restaure les fichiers originaux et traités dans un répertoire cible étanche sans écraser les données existantes. Testée et validée par `scripts/verify_artifact_backup.py` avec 100% de concordance des sommes de contrôle SHA256 sur les données brutes (`raw/`) et nettoyées (`cleaned/`).

---

## 3. Connexions Boutiques & Déploiements en Production

### 3.1 Clés de chiffrement, endpoints et sécurité WooCommerce
Pour que le formulaire de connexion WooCommerce et Shopify fonctionne en production, les variables d'environnement requises ont été injectées sur Railway Production :
- `CONNECTOR_ENCRYPTION_KEYS=03rZtfwgwKsrVQ3vzJ3srsLtiJHrwqrfW2z7ojGiV2E=` (chiffrement AES des Consumer Keys / Secrets des clients)
- `WOOCOMMERCE_CALLBACK_URI=https://api.avenqo.ca/api/v1/connectors/woocommerce/callback`
- `WOOCOMMERCE_WEBHOOK_URI=https://api.avenqo.ca/api/v1/connectors/woocommerce/webhook`
- `WOOCOMMERCE_APP_NAME=Avenqo`
- **Sécurité localhost** : `WOOCOMMERCE_ALLOW_INSECURE_LOCALHOST=false` (confirmé et strictement désactivé sur l'environnement de production Railway).
- `SHOPIFY_*` (Client ID, Secret, Redirect URI, Webhook URI, Scopes)

### 3.2 Déploiement Frontend Vercel (Production)
- **Projet** : `web` (`paulmircea15-9488s-projects/web`)
- **Déploiement Vercel ID** : `dpl_59FSM4K3WCRXbRUsqu5kog5r5nAg`
- **Domaine alias** : `https://avenqo.ca` (et `https://www.avenqo.ca`)
- **Statut Vercel** : **READY (Production)**
- **Commit inclus** : `ce4352c` (inclut les badges dynamiques de [connections-view.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/connections/connections-view.tsx), l'action « Réimporter » et la gestion des statuts de connexion).

### 3.3 Badges et formulaires dans l'interface (`connections-view.tsx`)
Les cartes de connexion reflètent fidèlement l'état réel :
- **Etsy** : badge **« Bientôt disponible »**, bouton désactivé (l'API Etsy n'étant pas implémentée côté backend, aucun faux espoir n'est affiché).
- **Shopify & WooCommerce** :
  - **Non connecté** (badge gris neutre) lorsque l'organisation n'a pas encore lié de boutique, avec mention « Disponible ».
  - **Synchronisation** (badge bleu animé avec spinner) dès qu'un cycle d'extraction est en cours.
  - **Erreur** (badge rouge avec icône d'alerte) si les clés API sont rejetées ou expirées.
  - **Connecté / Disponible** (badge vert avec coche) lorsque la boutique est activement liée.
- **Formulaire WooCommerce** :
  - Accessible via le bouton « Connecter » → saisie de l'URL, Consumer Key (`ck_...`) et Consumer Secret (`cs_...`).
  - La validation envoie les données à `POST /api/v1/connectors/woocommerce/manual`.
  - Le backend chiffre les clés, enregistre la connexion, et planifie **immédiatement la synchronisation initiale en arrière-plan** (`runner.run_reserved`).

---

## 4. Blocages & Actions Utilisateur — NON VALIDÉS (Vérifications Externes Requises)

Les points suivants restent explicitement **NON VALIDÉS** et requièrent une intervention directe de l'utilisateur :

### 4.1 Vérification email — NON VALIDÉ
- **Compte** : `ciomir@gmail.com`
- **Jeton** : généré via le flux applicatif normal `resend_verification()`.
- **Lien** : pointe vers `https://avenqo.ca/verify-email?token=...` (Production).
- **Action requise** : Ouverture de la boîte de réception `ciomir@gmail.com` et clic sur le lien de confirmation.

### 4.2 Parcours Stripe test — NON VALIDÉ
- **Compte propriétaire (`gauffy95@gmail.com`)** : est **Enterprise** en production (`cus_produits_ero_prod`). Ne **JAMAIS** modifier ce compte pour des tests de paiement.
- **Compte de test** : `ciomir@gmail.com` (disponible en **sandbox** avec BillingAccount `bcbf5e02-ad99-4623-a6f4-87dfe30f036b` et `sk_test_...`).
- **Action requise** : Initier le test Demo → Professional avec la carte de test Stripe (`4242...`) dans l'environnement sandbox uniquement.

### 4.3 Connexion effective d'une boutique en Production — NON VALIDÉ
- L'infrastructure et les formulaires sont prêts et sécurisés.
- **Action requise** : Saisie par le propriétaire de ses vraies clés API WooCommerce ou autorisation OAuth Shopify depuis [avenqo.ca/connections](https://avenqo.ca/connections).

---

## 5. État des Vérifications Visuelles (Quota Navigateur Épuisé)

En raison de l'épuisement du quota de sessions automatisées du navigateur, les vérifications visuelles suivantes **ne sont pas déclarées réussies** et doivent être constatées directement par l'utilisateur :
1. L'affichage du badge « Fichier source indisponible » et du bouton « Réimporter » sur les datasets orphelins dans `https://avenqo.ca/connections`.
2. L'affichage des badges réels (« Non connecté » sur WooCommerce et Shopify, « Bientôt disponible » sur Etsy).
3. L'ouverture de la modale WooCommerce et la soumission du formulaire de connexion.
4. L'affichage de la grille de produits dans le module Retail AI suite à la synchronisation d'une vraie boutique.

