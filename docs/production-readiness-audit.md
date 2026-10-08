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

## 5. RECOMMANDATIONS POUR LE TEST VOCAL RÉEL EN PRODUCTION (CALL #8)

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
