# AVENQO — RAPPORT D'AUDIT DE PRODUCTION ET PRÉPARATION AU LANCEMENT (P0)

> **Date d'exécution :** 8 Octobre 2026  
> **Branche Git :** `main`  
> **Organisation / Dépôt :** `Paulcioban1997/Avenqo-Platform-`  
> **Environnements :** Production (`avenqo.ca`, `api.avenqo.ca`) / Staging / CI GitHub Actions  
> **Auteurs :** Équipe d'ingénierie senior Avenqo (PMC Solutions AI)

---

## 1. RÉSUMÉ EXÉCUTIF & MATRICE DE STATUT STRICTE

Conformément aux exigences de rigueur, chaque composant est qualifié selon la nomenclature stricte :
- **OPÉRATIONNEL — TEST RÉEL RÉUSSI** : Vérifié avec trafic / intégration réelle sans simulation.
- **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** : Couvert et passant avec succès dans la suite automatisée (unitaire / intégration).
- **CONFIGURÉ MAIS NON TESTÉ** : Câblé au niveau code / variables, mais non validé en conditions réelles ou test dédié.
- **BLOQUÉ** : Dépendance externe, secret manquant ou permission bloquant l'exécution.
- **NON IMPLÉMENTÉ** : Déclaré dans l'interface ou le catalogue mais sans moteur backend actif.

| Composant / Fonctionnalité | Statut Strict | Détails & Preuves |
| :--- | :--- | :--- |
| **Voice AI — Media Streaming Telnyx (Inbound/Outbound)** | **OPÉRATIONNEL — TEST RÉEL RÉUSSI** | Appels réels Telnyx décrochés (Call #7), audio bidirectionnel PCMU 8kHz, STT Whisper / Deepgram et TTS OpenAI actifs. |
| **Voice AI — Routage contextuel & conservation des outils** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Correction de l'incident « Allô, est-ce que vous avez fini ? » (`test_voice_crm_end_to_end.py` PASS). Outils toujours exposés sur `/voice`. |
| **Voice AI — Ancre temporelle (date/heure/fuseau tenant)** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Injection de `Current date and time` dans le prompt système pour résoudre « aujourd'hui », « demain », « 14h ». |
| **Voice AI — Règle anti-attente verbale LLM** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Instruction stricte obligeant l'appel d'outil immédiat au lieu de « Je vais vérifier, un instant ». |
| **CRM AI — Vérification des disponibilités (`check_availability`)** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Respect des horaires d'ouverture, détection des conflits et suggestions réelles (`suggested_slots`). |
| **CRM AI — Réservation & persistance PostgreSQL** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Création du client à la volée sur appel vocal et enregistrement transactionnel de `CRMAppointment`. |
| **CRM AI — Google Calendar (Free/Busy & Synchro)** | **CONFIGURÉ MAIS NON TESTÉ** | Connecteur `backend/app/services/google_calendar_service.py` prêt, nécessite le consentement OAuth actif du compte Google du tenant. |
| **Retail AI — Traitement analytique & KPI dynamiques** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `test_retail_active_source.py` et `test_sales_date_regressions.py` valident le calcul roulant sur 30 jours, 7 jours et aujourd'hui. |
| **Retail AI — Connecteur Shopify (OAuth & GraphQL Admin)** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `test_shopify_connector.py` et `test_commerce_sync_service.py` valident la synchro incrémentale, pagination et capture. |
| **Retail AI — Connecteur WooCommerce (REST v3)** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `test_commerce_sync_runner.py` valide la capture et la normalisation des commandes/produits. |
| **Retail AI — Mutation directe de stocks sur boutique réelle** | **CONFIGURÉ MAIS NON TESTÉ** | Connecteur d'écriture présent ; aucune boutique test autorisée connectée pour mutation en production. |
| **Infrastructure — CI GitHub Actions** | **OPÉRATIONNEL — TEST RÉEL RÉUSSI** | Workflows Web (Next.js Enterprise), Flutter et Backend Core validés en intégration continue. |
| **Infrastructure — Base de données PostgreSQL & Migrations** | **OPÉRATIONNEL — TEST RÉEL RÉUSSI** | Schémas Alembic à jour sur PostgreSQL Railway (`availability_test` et prod). |
| **Sécurité — Isolation multi-tenant stricte** | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Testé avec succès sur `CRMClient`, `CRMAppointment` et datasets (`test_multi_tenant_isolation_on_appointments`). |

---

## 2. PHASE 1 — CORRECTION DÉTAILLÉE DE L'INCIDENT VOICE AI + CRM AI

### 2.1 Description de l'incident réel observé (Call #7)
Lors d'un appel téléphonique entrant sur le numéro Telnyx d'une entreprise :
1. **Client :** « Bonjour, pouvez-vous me prendre un rendez-vous aujourd'hui à 14 h ? »  
   **Agent :** « Je vais vérifier la disponibilité pour un rendez-vous aujourd'hui à 14 h. Un instant, s'il vous plaît. »
2. **Client :** « Allô, est-ce que vous avez fini ? »  
   **Agent :** « Je suis désolée, mais je ne peux pas confirmer la disponibilité pour un rendez-vous à 14 h aujourd'hui. Avez-vous une autre heure en tête ? »
3. **Client :** « Pourquoi vous ne pouvez pas ? »  
   **Agent :** « Je n'ai pas accès à un calendrier ou à un système de rendez-vous pour le moment. »

### 2.2 Analyse des causes racines et preuves techniques
L'audit approfondi des traces de logs et du code source a mis en évidence **5 causes racines combinées** :

1. **Amnésie du routeur d'intentions sur réplique intermédiaire :**
   - Sur la phrase « Allô, est-ce que vous avez fini ? », le routeur `CentralAIIntentRouter` n'analysait que cette unique réplique isolée sans historique. Ne trouvant aucun mot-clé CRM (`rendez-vous`, `disponibilité`), il retournait `agent=None`.
   - La méthode `_tool_scope_for_request` retournait alors `frozenset()`, vidant complètement les outils (`available_tools_count=0`). L'agent répondait donc en `general_fallback`, affirmant n'avoir aucun accès au calendrier.
2. **Absence d'ancre temporelle dans les instructions LLM :**
   - Le système fournissait uniquement le nom du fuseau horaire (`company_timezone: America/Montreal`) sans indiquer la date ni l'heure courantes. Le LLM était incapable de traduire « aujourd'hui à 14h » en timestamp ISO 8601 pour appeler `check_availability`.
3. **Comportement verbal intermédiaire d'attente :**
   - Le modèle générait spontanément une phrase d'attente polie (« Je vais vérifier... ») au lieu d'invoquer immédiatement le tool call dans le premier tour d'exécution.
4. **Absence de suggestions de créneaux alternatifs :**
   - Lorsque `check_availability` renvoyait `BUSY` ou `OUTSIDE_WORKING_HOURS`, il ne fournissait aucune liste `suggested_slots`, laissant le LLM désemparé face à l'appelant.
5. **Résolution bloquante des appelants inconnus :**
   - `CreateAppointmentTool` exigeait la présence préalable du client dans la table `crm_clients`. Un nouvel appelant fournissant son nom et son courriel était rejeté avec une erreur d'inaccessibilité client.

### 2.3 Correctifs apportés dans le code de production
- **`backend/app/ai/central/service.py` :**
  - Ajout de la mémoire contextuelle dans le routeur : si `self._router.select(query)` échoue, les 4 derniers messages de la conversation sont analysés pour maintenir la continuité thématique.
  - Garantie de scope d'outils vocal : si la requête provient de `/voice` et que `crm` ou `retail` sont actifs, les outils autorisés sont systématiquement conservés même si `agent=None`.
- **`backend/app/ai/chat/chat_service.py` :**
  - Injection dynamique de `Current date and time: YYYY-MM-DD HH:MM (Jour)` dans le fuseau horaire du tenant.
  - Ajout d'une règle vocale stricte : interdiction des phrases d'attente verbales (« Je vais vérifier, un instant ») sans appel d'outil simultané.
- **`backend/app/services/crm_availability_service.py` :**
  - En cas de conflit (`BUSY`) ou hors horaires (`OUTSIDE_WORKING_HOURS`), intégration automatique de 3 créneaux réellement disponibles dans `suggested_slots`.
- **`backend/app/ai/tools/business/crm_tools.py` :**
  - Auto-inscription du client dans `crm_clients` lorsqu'un nouvel appelant transmet son nom et un courriel valide lors de la réservation vocale.

### 2.4 Validation par les tests automatisés
- **Suite dédiée :** `tests/backend/test_voice_crm_end_to_end.py`
  - `test_system_instruction_injects_current_date_and_time` : **PASSED**
  - `test_crm_check_availability_returns_suggested_slots_when_busy` : **PASSED**
  - `test_create_appointment_tool_auto_creates_new_client_and_books` : **PASSED**
  - `test_tool_scope_for_voice_call_never_drops_tools_when_agent_none` : **PASSED**
  - `test_multi_tenant_isolation_on_appointments` : **PASSED**
- **Suites de non-régression associées :**
  - `test_central_ai.py` (63 tests) : **PASSED**
  - `test_voice_call_7_language_lock.py` (17 tests) : **PASSED**
  - `test_telnyx_media.py` (112 tests) : **PASSED**

---

## 3. PHASE 2 — SYNCHRONISATION RETAIL AI & CONNECTEURS COMMERCE

### 3.1 Architecture de synchronisation
Avenqo implémente une chaîne d'ingestion Retail éprouvée :
1. **Connecteurs :** `ShopifyConnector` (GraphQL Admin 2024-07) et `WooCommerceConnector` (REST API v3).
2. **Synchronisation :** `CommerceSyncService` et `CommerceSyncRunner`.
3. **Capture brute :** `CommerceRawSnapshot` (stockage immuable des JSONs sources).
4. **Normalisation :** `NormalizedCommerceRecord` (format pivot Avenqo).
5. **Projection canonique :** `CanonicalRetailContext` -> `DatasetVersion` (Parquet / PostgreSQL).
6. **Requêtage Retail AI :** Outils `get_sales_summary`, `get_inventory_levels`, `get_top_products`.

### 3.2 Vérification des filtres temporels dynamiques
Le test `test_shopify_active_source_filters_all_retail_services` dans `tests/backend/test_retail_active_source.py` a été consolidé avec succès (commit `db647da`) :
- Calcul glissant sur les 30 derniers jours à partir de la date courante.
- Calcul sur les 7 derniers jours et sur aujourd'hui.
- Élimination des régressions d'écarts de dates fixes.

---

## 4. PHASE 3 — INFRASTRUCTURE ET OBSERVABILITÉ END-TO-END

### 4.1 GitHub Actions & CI
- **Workflows actifs :** `.github/workflows/ci.yml`
- **Frontend Web (Next.js Enterprise) :** Tests unitaires + build de production bundle -> **SUCCÈS**.
- **Frontend App (Flutter) :** Analyse statique + tests -> **SUCCÈS**.
- **Backend Core (FastAPI & AI Engine) :** Validation PostgreSQL 16 + suite de tests -> **SUCCÈS**.

### 4.2 Plateforme Cloud Railway (Backend & PostgreSQL)
- **Point d'accès API :** `https://api.avenqo.ca`
- **Serveur applicatif :** FastAPI sous Uvicorn / Gunicorn asynchrone.
- **Base de données :** PostgreSQL managé avec isolation de schéma par tenant.
- **Support WebSocket :** Actif pour le streaming audio Telnyx Media (`/v1/voice/media-stream`).

### 4.3 Vercel (Frontends)
- **Domaine public :** `https://avenqo.ca`
- **Routage :** Redirections propres vers Next.js et gestion des cookies d'authentification JWT sécurisés (`SameSite=Lax`, `Secure`).

---

## 5. INTÉGRATION UNIVERSELLE VOICE AI ↔ TOUS LES MODULES MÉTIER

### 5.1 Découverte Dynamique des Outils Métier
La sélection statique et codée en dur (`{"crm", "retail", "voice"}`) dans `backend/app/ai/central/service.py` a été remplacée par une **découverte dynamique** basée sur les modules activement souscrits par le tenant :
- **CRM AI :** `check_availability`, `list_available_slots`, `create_appointment`, `search_appointments`, `get_crm_metrics`, etc.
- **Retail AI :** `get_sales_summary`, `get_top_products`, `get_inventory_levels`, `forecast_sales`, etc.
- **Accounting AI :** `get_financial_overview`, `get_monthly_expenses`, `get_profit_margin`, `get_unpaid_invoices`, `get_expense_anomalies`, `get_cashflow_forecast`.
- **Cross-Agent Intelligence :** `get_cross_agent_business_health` (synthèse 360° quand CRM, Retail et Accounting sont activés).

### 5.2 Règles de Sécurité Téléphonique & Authentification par Rôle
| Rôle de l'Appelant | Mode de Vérification | Outils Accessibles | Opérations Interdites |
| :--- | :--- | :--- | :--- |
| **Appelant Externe / Public** | Numéro entrant non vérifié | `check_availability`, `list_available_slots`, `create_appointment` (avec recueil d'infos et confirmation) | Interdiction stricte : Données financières (`accounting`), métriques de vente (`retail`), listes de clients ou factures. Biaisés par `security_gate` et `ToolAuthorizationPolicy`. |
| **Client Enregistré** | NIP client DTMF vérifié | Consultation/modification de ses propres rendez-vous | Accès aux finances et aux données d'autres clients. |
| **Propriétaire / Collaborateur** | NIP de gestion DTMF vérifié | Métriques CRM, Retail et Accounting complètes selon son rôle RBAC | Opérations d'administration plateforme (facturation Avenqo, upgrade, suppression de tenant). |

### 5.3 Statut des Autres Modules du Catalogue
- **Accounting AI :** **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** (6 outils opérationnels dans `accounting_tools.py`, connectés et testés avec succès).
- **OCR, Media, Legal, Marketing, RH et Workflow :** **NON IMPLÉMENTÉ**
  - *Audit technique :* Aucun outil métier ou moteur d'exécution n'est déclaré dans `backend/app/ai/tools/business/` pour ces modules.
  - *Sécurité :* Ces modules sont strictement exclus du scope d'outils vocal pour éviter d'exposer des interfaces vides ou d'induire le LLM en erreur.

### 5.4 Changements de Sujet Pendant un Même Appel
La persistance d'exposition des outils métier autorisés permet désormais d'enchaîner sans friction :
1. *Tour 1 :* « Prends un rendez-vous demain à 14h » -> Exécution `check_availability` (CRM).
2. *Tour 2 :* « Combien de commandes avons-nous reçues aujourd'hui ? » -> Exécution `get_sales_summary` (Retail).
3. *Tour 3 :* « Quel est le montant des factures impayées ? » -> Exécution `get_unpaid_invoices` (Accounting).
Testé et validé par `test_voice_topic_switching_mid_call_preserves_cross_module_capabilities` dans `tests/backend/test_voice_crm_end_to_end.py`.

---

## 6. RECOMMANDATIONS POUR LE TEST VOCAL RÉEL EN PRODUCTION (CALL #8)

Pour valider en conditions réelles avec Telnyx et Google Calendar :
1. **Activer le module CRM & Voice** pour le tenant de test.
2. **Connecter un Google Calendar** de test via la page d'intégrations du tenant.
3. **Passer un appel téléphonique** au numéro Telnyx attribué.
4. **Scénario d'essai :**
   - « Bonjour, je voudrais réserver une consultation demain à 14h. »
   - L'agent doit vérifier le calendrier immédiatement et confirmer la disponibilité.
   - Fournir nom et courriel : « Je m'appelle Marc Tremblay, marc.tremblay@test-avenqo.ca. »
   - Confirmer explicitement : « Oui, je confirme. »
   - Vérifier l'apparition instantanée de l'événement dans le calendrier Google et dans le tableau CRM Avenqo.

---

## 7. VOICE AI — AUTHENTIFICATION PAR NIP ET AUTORISATIONS (PHASE P0)

### 7.1 Architecture de Sécurité & Modèle de Confiance
L'authentification téléphonique repose sur un principe **Fail-Closed strict à double barrière** :
1. **Barrière d'exposition du prompt (`_tool_scope_for_request`) :**
   Les outils privés (Retail, Accounting, CRM dossiers, Cross-Agent) ne sont jamais inclus dans la liste des outils transmis au LLM lorsqu'un appelant est externe/anonyme (`is_public_voice_caller(permissions)` est vrai). Seuls les outils publics de réservation (`check_availability`, `list_available_slots`, `create_appointment`) sont exposés.
2. **Barrière d'exécution serveur (`ToolAuthorizationPolicy.authorize`) :**
   Même si un LLM hallucine ou reçoit une injection de prompt tentant d'exécuter un outil privé sans session téléphonique active vérifiée, la passerelle serveur intercepte l'appel et lève immédiatement `ToolAuthorizationError("Caller authentication is required for this tool.")`.

### 7.2 Cryptographie & Gestion des Identifiants
- **Faible entropie compensée :** Le NIP vocal est composé de 6 à 12 chiffres. Sa faible entropie par rapport à un mot de passe alphanumérique est protégée par un poivre HMAC SHA-256 (`auth_jwt_secret`) combiné à l'identifiant du tenant et du collaborateur, puis haché avec Argon2id (`pin_hash`).
- **Validation anti-trivialité :** Les NIP triviaux (séquences ascendantes `123456`, descendantes `654321`, ou répétitions `111111`, `121212`, `123123`) sont rejetés à la saisie.
- **Protection anti-bruteforce (Lockout) :** Verrouillage automatique (`locked_until` fixé à +15 minutes) dès 5 tentatives infructueuses consécutives.
- **Réauthentification forte :** La création ou modification de NIP depuis l'interface web exige la saisie du mot de passe de compte web actuel. Un NIP identique au mot de passe web est strictement refusé.
- **Confidentialité absolue :** Aucun NIP n'apparaît en clair dans les logs, la base de données, les schémas d'API ou les audits (`redact_voice_secrets`).

### 7.3 Cycle de Vie des Sessions Vocales
- **Sessions éphémères révocables (`VoiceAuthSession`) :** Créées lors de la validation DTMF Telnyx (`verify_gather`), avec expiration automatique (TTL 10 minutes) et associées à un `call_id` unique (non réutilisable pour un autre appel).
- **Révocation sur raccrochage :** Le webhook Telnyx `call.hangup` révoque immédiatement toute session active liée à l'appel.
- **Révocation mid-call :** Si un collaborateur est désactivé (`User.is_active = False`), si son adhésion est révoquée (`CompanyMembership.is_active = False`) ou si son accès téléphonique est coupé (`VoiceCallerCredential.enabled = False`), la session est instantanément invalidée en plein appel.

### 7.4 Matrice d'Évaluation des 17 Exigences

| # | Exigence du Cahier des Charges | Statut Réglementaire | Justification & Preuve Technique |
| :- | :--- | :--- | :--- |
| **1** | Création du NIP avec validation de complexité | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `validate_voice_pin` vérifie 6-12 chiffres et rejette les suites triviales (`test_1_voice_pin_validation_complexity_and_nontrivial`). |
| **2** | Confirmation du NIP et rejet si identique au mot de passe | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `VoicePinRequest` valide la confirmation et lève une erreur si identique au mot de passe (`test_2`). |
| **3** | NIP incorrect et échec d'authentification | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `verify_gather` échoue, incrémente les échecs et retourne `caller_authentication_failed` (`test_3`). |
| **4** | Réinitialisation sécurisée par réauthentification forte | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `PUT /voice/auth/pin` exige le mot de passe actuel vérifié via `verify_password` (`test_4`). |
| **5** | Verrouillage (lockout) après 5 tentatives erronées | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Verrouillage avec `locked_until > now`, bloquant même le bon NIP tant que le délai n'est pas écoulé (`test_5`). |
| **6** | Réinitialisation invalidant les sessions actives antérieures | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `set_pin` révoque immédiatement toute `VoiceAuthSession` active liée à l'utilisateur (`test_6`). |
| **7** | Révocation manuelle API et sur raccrochage | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Validé via `POST /voice/auth/sessions/revoke` et événement `call.hangup` (`test_7`). |
| **8** | Employé désactivé / accès coupé mid-call | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `valid_session(call)` vérifie en temps réel `is_active` et `credential.enabled` (`test_8`). |
| **9** | Permissions retirées pendant l'appel bloquant les outils | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `ToolAuthorizationPolicy` intersecte les permissions et bloque l'exécution (`test_9`). |
| **10** | Désactivation de module masquant les outils | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `_tool_scope_for_request` filtre selon les modules actifs souscrits du tenant (`test_10`). |
| **11** | Accès aux finances (Retail/Accounting) bloqué pour appelant externe | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Dual Gate : masqué au LLM et rejeté par `ToolAuthorizationError` au serveur (`test_11`). |
| **12** | Isolation multi-tenant stricte | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Cloisonnement strict par `company_id`, un NIP du Tenant A ne peut s'authentifier sur le Tenant B (`test_12`). |
| **13** | Appel interrompu invalidant la session immédiatement | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `ended_at` vérifié dans `valid_session`, annulant l'accès (`test_13`). |
| **14** | NIP absent des logs et de l'API | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | `redact_voice_secrets`, stockage haché Argon2id + HMAC pepper, audit sans secret (`test_14`). |
| **15** | Protection contre la réutilisation de session | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Session liée au `call_id` unique, rejet sur appel ultérieur (`test_15`). |
| **16** | Cross-Agent 360° sans contournement de permissions | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Les permissions de chaque outil sous-jacent restent obligatoires et strictes (`test_16`). |
| **17** | Rejet serveur fail-closed en cas d'invocation directe LLM | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Barrière d'exécution `ToolAuthorizationPolicy` inviolable (`test_17`). |

### 7.5 Interface Utilisateur Web (Next.js)
- **Onboarding (`/onboarding`) :** Étape dédiée « Sécurisez votre assistant vocal Avenqo » avec saisie de NIP à 6 chiffres, confirmation, bouton « Configurer plus tard » avec avertissement explicite de restriction aux outils publics.
- **Paramètres (`/settings`) :** Section « Sécurité Voice AI » comprenant :
  - Statut en temps réel du NIP (Actif / Verrouillé / Non configuré).
  - Numéro de téléphone de liaison masqué.
  - Commutateur d'activation de l'accès téléphonique privé.
  - Bouton de révocation immédiate de toutes les sessions téléphoniques actives.
  - Modal de modification avec réauthentification forte par mot de passe.
  - Tableau de contrôle des collaborateurs (réservé aux Propriétaires et Administrateurs) avec toggle d'accès par membre.
  - Journal des événements de sécurité récents (appels, tentatives DTMF, succès/échecs).
- **Validation frontend :** Compilation Next.js 16.3.0 (`npm run build`) validée sans aucune erreur (49 routes générées).

---

## 8. RÉSOLUTION DE L'INCIDENT P0 (APPEL RÉEL DU 8 OCTOBRE 2026)

### 8.1 Analyse des Causes Racines
1. **Incident 1 — Refus d'authentification par NIP :**
   - *Symptôme :* À la question « Est-ce qu'il y a une authentification sécurisée avec un NIP ? », l'agent vocal répondait de manière générique : « Je ne peux pas traiter d'informations sensibles comme un NIP. »
   - *Cause racine :* L'instruction de garde-fou du LLM interdisait de manipuler des NIP ou données sensibles à l'oral sans aiguiller vers le flux DTMF sécurisé. De plus, `security_gate()` dans `PublicInboundConversation` ne reconnaissait pas les demandes d'information ou de déclenchement du NIP téléphonique et laissait la requête passer au modèle conversationnel ou RAG.
   - *Correctif :*
     - Ajout de motifs d'interception stricts dans `security_gate()` : « authentification sécurisée avec un NIP », « taper mon nip », « entrer mon code », etc.
     - Si un NIP est configuré sur le tenant : l'agent invite explicitement à composer le NIP sur le pavé numérique du téléphone (DTMF) et rappelle : « Ne prononcez jamais votre NIP à voix haute. »
     - Si aucun NIP n'est configuré : l'agent informe que l'authentification est disponible et oriente vers le portail web (*Voice AI → Paramètres → Sécurité*).
     - Si une question métier privée est posée (ex. « Combien de commandes aujourd'hui ? »), la requête initiale est mémorisée dans `pending_auth_query`. Dès validation du NIP via DTMF, l'authentification est acquise et la requête métier initiale est réexécutée automatiquement sans nécessiter que l'utilisateur repose sa question.

2. **Incident 2 — Données Retail périmées / 0 commande reporté à tort :**
   - *Symptôme :* À la question « Combien de commandes avons-nous reçues aujourd'hui ? » posée le 8 octobre 2026, l'agent annonçait : « Aujourd'hui, nous n'avons reçu aucune commande. Les données sont à jour jusqu'au 5 octobre. »
   - *Cause racine :* Dans `BusinessMetricsService.sales_summary()`, lorsque la date demandée (8 octobre) dépassait la date de dernière synchronisation de la base (5 octobre), la requête SQL retournait naturellement 0 ligne, ce qui était faussement interprété comme 0 vente réelle.
   - *Correctif :*
     - Validation temporelle de couverture de données : si `period_start > max_transaction_date` (ou `last_sync_at`), `data_covered` passe à `False`, `orders` et `revenue` sont mis à `None`.
     - Message de couverture explicite généré : « Les données disponibles s'arrêtent au 5 octobre ; je ne peux pas confirmer les commandes du 8 octobre. »
     - Instruction système stricte pour le LLM et l'agent vocal : interdiction formelle d'affirmer « aucune commande reçue » ou « 0 commande » lorsque la période demandée n'est pas couverte par les données synchronisées.

### 8.2 Matrice d'Évaluation des Tests de Non-Régression P0 (18 à 23)

| # | Test de Non-Régression | Statut | Résultat & Preuve Technique |
| :- | :--- | :--- | :--- |
| **18** | Incident 1 : Déclenchement DTMF à la demande de NIP | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | « Est-ce qu'il y a une authentification sécurisée avec un NIP ? » déclenche `auth_required=True` avec invite au clavier numérique (`test_18`). |
| **19** | Incident 1 : Orientation portail si aucun NIP n'est configuré | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Répond que l'authentification est disponible et oriente vers le portail sans bloquer (`test_19`). |
| **20** | Incident 1 : Reprise automatique de la question en suspens après NIP | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | La question métier mémorisée est transmise et exécutée avec permissions complètes (`test_20`). |
| **21** | Incident 2 : Blocage des métriques privées pour appelant externe non-authentifié | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | « Combien de commandes avons-nous reçues aujourd'hui ? » exige l'authentification préalable (`test_21`). |
| **22** | Incident 2 : Rapprochement date demandée vs dernière synchro (Non-couverture) | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Pour le 8 octobre avec synchro au 5 octobre, `data_covered=False`, retournant le message de couverture et non 0 (`test_22`). |
| **23** | Incident 2 : Réponse pour période valide couverte | **VALIDÉ PAR TEST AUTOMATISÉ UNIQUEMENT** | Pour le 5 octobre (couvert), `data_covered=True` et les métriques réelles sont retournées avec précision (`test_23`). |

### 8.3 Synthèse d'Exécution des Suites de Tests
- `tests/backend/test_voice_auth_pin_security.py` : **23/23 tests réussis (100%)**
- `tests/backend/test_voice_crm_end_to_end.py` : **7/7 tests réussis (100%)**
- `tests/backend/test_telnyx_media.py` : **112/112 tests réussis (100%)**
- **Total validé : 142/142 tests automatisés sans aucun échec.**


