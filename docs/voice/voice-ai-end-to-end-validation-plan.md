# Plan de Validation Avenqo Voice AI — De Bout en Bout (Sandbox & Pré-Production)

> **STATUT** : CONDITION OBLIGATOIRE PRÉ-PRODUCTION (PR #61)  
> **DÉCISION ACTUELLE** : **NO-GO LIVE CALLS** — Aucun appel payant, aucune modification de webhook ni aucun déploiement sans accord explicite du propriétaire.  
> **APPLICATION** : Tout déploiement futur en Production d'Avenqo est strictement conditionné par la démonstration réussie et vérifiée de ce plan sur Sandbox.

---

## 1. Cadre de Sécurité et Gardes-Fous Préalables

1. **Aucun appel payant préalable** : Aucune commande générant des coûts (Telnyx Voice, SIP, OpenAI Realtime, Twilio) n'est exécutée sans autorisation écrite préalable spécifiant le numéro et le budget.
2. **Cloisonnement strict des environnements** :
   - Railway Sandbox (`alert-tenderness`, env `e5adc24d-23b9-4275-84de-91a7801649b8`) dispose de ses propres variables, secrets et URL de webhook.
   - Les clés d'API (Telnyx, OpenAI), numéros de téléphone et webhooks Sandbox sont **strictement disjoints** de la Production.
3. **Plafond financier et garde-fou temporel** :
   - Plafond d'essai Sandbox fixé à **2 CAD** (ou spend limit OpenAI dédié de 0,75 USD sur projet de test `avenqo-sandbox-voice`).
   - Timeout strict physique et applicatif : Watchdog 90 secondes dès le premier événement signé `call.initiated` / `call.answered`.
   - Limite de concurrence : `inbound.channel_limit = 1`.

---

## 2. Les 10 Exigences de Validation Technique

### Exigence 1 — Configuration Telnyx Sandbox, Webhooks, Numéros & WebSocket
- **Vérification de l'application Telnyx** :
  - `Call Control Application` dédiée Sandbox (ex. Connection ID `3069110156336826311`).
  - Webhook URL : `https://avenqo-platform-sandbox.up.railway.app/api/v1/voice/telnyx/webhook`.
  - Version d'API webhook : `2`.
  - Signature Ed25519 : clé publique `TELNYX_PUBLIC_KEY` configurée dans Railway Sandbox pour authentifier l'entête `telnyx-signature-ed25519` et l'horodatage `telnyx-timestamp`. Rejet strict (HTTP 401) en cas de signature invalide ou expirée (> 300s).
- **Routage et routes FastAPI** :
  - Route Webhook : `POST /api/v1/voice/telnyx/webhook` avec rate-limiting par IP.
  - Route WebSocket Media Stream : `wss://avenqo-platform-sandbox.up.railway.app/api/v1/voice/telnyx/media/{call_id}`.
  - Attribution du numéro : Résolution déterministe via la table `voice_phone_numbers` où `status = 'ACTIVE'` et liaison stricte à `VoiceBusinessConfig` et `company_id`.

### Exigence 2 — Pipeline Audio Bidirectionnel
- **Chaîne audio validée de bout en bout** :
  1. *Téléphonie* : Réception de l'appel entrant sur Telnyx -> Événement signé `call.initiated` -> Ordre `answer` avec commande de streaming média.
  2. *Streaming Média* : Connexion WebSocket bidirectionnelle Telnyx Media Stream (`G.711 PCMU` 8kHz 160 octets / 20ms).
  3. *Décodage / Réordonnancement* : `TelnyxAudioReorderBuffer` et `TelnyxAudioCodec` convertissent le flux PCMU en PCM linéaire 16-bit 24kHz pour le moteur IA.
  4. *Transcription (STT)* : Détection de parole (`speech_started`), streaming vers le modèle de transcription (`gpt-4o-mini-transcribe` ou OpenAI Realtime STT).
  5. *Raisonnement & Orchestration (LLM / Central AI)* : Contexte métier localisé (`_localized_system_instruction`), outillage métier CRM, injection de l'heure/date du tenant.
  6. *Synthèse Vocale (TTS)* : Génération audio via Realtime ou TTS standard, encodage en paquets PCMU.
  7. *Retour Audio Outbound* : Envoi cadencé des frames audio sur le WebSocket vers Telnyx et écoute fluide par l'appelant.

### Exigence 3 — Test Réel d'Appel Entrant (Avec Accord Explicite)
- **Protocole du test réel** :
  - Numéro de test attribué au tenant test (ex. `Produits_Ero` ou `Garage Montréal QA`).
  - Accord écrit formalisé avant l'appel (couvrant les micro-frais Telnyx + OpenAI).
  - Déroulé : L'opérateur compose le numéro Sandbox depuis son téléphone.
  - Vérification de l'accueil vocal personnalisé (`voice_greeting`), de la clarté acoustique, de la latence (< 1200ms par turn) et du raccrochage naturel en fin de dialogue.

### Exigence 4 — Création de Rendez-vous CRM et Synchronisation Calendrier
- **Scénario métier conversationnel** :
  - Phrase test : *« Bonjour, je voudrais prendre rendez-vous demain à 14 h pour mon véhicule. »*
  - Résolution temporelle : Fuseau tenant (ex. `America/Montreal`), pas d'heure UTC implicite.
  - Consultation de disponibilité : Appel de `check_availability` / `list_slots`.
  - Recueil des informations : Nom, prénom, courriel, téléphone de l'appelant. Si nouveau client, création automatique idempotente dans `CRMClient`.
  - Confirmation explicite avant réservation : L'IA énonce date et heure exactes et attend l'assentiment.
  - Création du rendez-vous dans `CRMAppointment` lié au `company_id` exact.
  - Synchronisation calendrier externe (Google Calendar / Microsoft Outlook) :
    - Si compte OAuth connecté (`CRMCalendarConnection` avec `sync_status = 'connected'`) : création de l'événement distant et assignation de `external_event_id`.
    - Si OAuth non configuré ou en échec : maintien du rendez-vous local CRM avec `calendar_synced = False`, annonce vocale honnête à l'appelant (*« Votre rendez-vous est bien noté dans Avenqo »* sans fausse promesse de synchro).

### Exigence 5 — Matrice Multilingue (Français, Anglais, Roumain & Autres Langues)
- **Validation linguistique stricte** :
  - **Français (`fr-CA` / `fr-FR`)** : Langue par défaut du système, gestion du québécois et du français standard, salutations et confirmations CRM validées.
  - **Anglais (`en-US` / `en-GB`)** : Salutations *« Hello, how can I help you today? »*, réservation fluide.
  - **Roumain (`ro-RO`)** : Langue Tier-1 STT/TTS (`_TIER_1_AUDIO_LOCALES`). Salutations *« Bună ziua, cu ce vă pot ajuta astăzi? »*, gestion des caractères diacritiques et flux conversationnel CRM.
  - **Autres langues de la plateforme** : Comportement fail-closed honnête via `RegionLanguageResolver`. Si une langue n'est pas certifiée en audio temps réel, repli propre selon la politique de locale définie sans crash ni hallucination.

### Exigence 6 — Isolation Multi-Tenant Stricte (Central AI & Voice AI)
- **Cloisonnement total des données** :
  - Résolution de session basée uniquement sur `VoicePhoneNumber` actif du tenant.
  - Application du contexte tenant : `TenantContext(company_id)`.
  - Politiques PostgreSQL RLS : Le rôle applicatif `avenqo_app` applique `FORCE ROW LEVEL SECURITY`. Les requêtes SQL de Central AI et Voice AI sont strictement bornées à `company_id = current_setting('app.current_tenant_id')`.
  - Test d'intrusion / fuite : Vérification qu'un appel sur le numéro de l'Entreprise A ne peut ni voir, ni modifier les disponibilités, clients, stocks ou configurations de l'Entreprise B.

### Exigence 7 — Résilience, Interruptions, Appels Simultanés & Quotas
- **Gestion des événements perturbateurs** :
  - *Barge-in (interruption vocale)* : Événement `speech_started` ou touche DTMF -> émission immédiate de l'événement `clear` sur le WebSocket, incrément d'époque (`self.epoch += 1`), coupure du son sortant.
  - *Déconnexion inopinée* : Raccrochage réseau de l'appelant -> capture de `call.hangup`, libération immédiate du worker et du pool SQL.
  - *Appels simultanés* : Telnyx borne à `inbound.channel_limit = 1` en Sandbox. Au niveau Avenqo, rejet immédiat si la limite de canaux souscrite est atteinte.
  - *Quotas et consommation de crédits* :
    - Réservation de crédits au début du turn via `AIUsageService.claim_credit_reservation`.
    - Règlement (`settle_reservation`) ou libération (`release_reservation`) unitaire dans `TenantAICreditLedgerEntry`.
    - Solde de crédits insuffisant -> Message d'indisponibilité poli et clôture propre de l'appel sans génération payante.

### Exigence 8 — Confidentialité, Journaux & Respect des Droits
- **Zero-Leak Logging** :
  - Masquage systématique des NIP / PIN DTMF via `redact_voice_secrets`.
  - Aucune transcription brute intégrale, aucune clé d'API, aucun token OAuth dans les logs applicatifs Railway.
  - Télémétrie anonymisée : seuls les compteurs d'images (`inbound_frames`, `outbound_frames`), durées et codes d'erreur abstraits sont journalisés.
  - Enregistrements audio désactivés par défaut sur Sandbox (`record_call = False`).

### Exigence 9 — Préparation Hermétique de la Configuration Production
- **Séparation totale Sandbox / Production** :
  - Pas de mutualisation des numéros Telnyx : les numéros de Production doivent être commandés et assignés exclusivement sur l'application Telnyx Production.
  - URL de webhook Production : `https://api.avenqo.ca/api/v1/voice/telnyx/webhook`.
  - Clés d'API Telnyx et OpenAI distinctes, rattachées aux organisations et projets de production, avec leurs propres plafonds de dépenses (Spend Limits).
  - Clé publique Ed25519 Telnyx spécifique à l'application Production.

### Exigence 10 — Procédure de Validation Production & Plan de Rollback
- **Mise en service contrôlée (Canary / Smoke test)** :
  1. Déploiement du code sur Production avec `TELNYX_MEDIA_ENABLED=false` et `TELNYX_MEDIA_INBOUND_ENABLED=false`.
  2. Vérification des routes de santé `/health` et `/ready`.
  3. Activation ciblée du flag sur un numéro pilote interne appartenant à Avenqo.
  4. Réalisation d'un appel pilote unique supervisé en direct.
  5. Validation de la création CRM et des traces dans la base.
- **Rollback immédiat en cas d'incident** :
  - *Palier 1 (Immédiat, sans redéploiement)* : Bascule des variables d'environnement `TELNYX_MEDIA_INBOUND_ENABLED=false` dans Railway Production -> Rejet propre des appels entrants ou routage vers messagerie.
  - *Palier 2 (Routage Telnyx)* : Réassignation instantanée du numéro de test vers le Call Control Connection de secours ou déconnexion du webhook via l'API Telnyx.
  - *Palier 3 (Applicatif)* : Retour au commit de release précédent via Railway rollback si une anomalie logicielle est détectée.

---

## 3. Matrice de qualification GO / NO-GO

| Étape | Description | Statut requis pour GO Sandbox | Statut requis pour GO Production |
|---|---|:---:|:---:|
| 1 | Tests unitaires & intégration Voice AI locaux (176 tests) | **PASS (100%)** | **PASS (100%)** |
| 2 | Sauvegarde PostgreSQL Sandbox chiffrée `age` & restaurée sur test | **VALIDÉE** | **VALIDÉE** |
| 3 | Déploiement Sandbox PR #61 & migration RLS 0060/0061 | **GO PRÉALABLE** | **RÉUSSI** |
| 4 | Diagnostic Telnyx Sandbox & validation webhook/WS en simulation | **VERT** | **VERT** |
| 5 | Test d'appel réel Sandbox entrant (Français, CRM appointment) | **VERT (Sous accord)** | **PRÉ-REQUIS OBLIGATOIRE** |
| 6 | Test multilingue Sandbox (Anglais, Roumain) | **VERT (Sous accord)** | **PRÉ-REQUIS OBLIGATOIRE** |
| 7 | Audit d'isolation des données entre entreprises test | **ZÉRO FUITE** | **ZÉRO FUITE** |
| 8 | Clés et numéros Production distincts configurés | N/A | **VÉRIFIÉ** |
| 9 | Procédure de rollback Production testée | N/A | **TESTÉE** |

> **CONCLUSION** : Toute décision de mise en Production reste **BLOCKED** tant que les étapes 1 à 7 n'ont pas été pleinement déroulées et validées sur l'environnement Sandbox.
