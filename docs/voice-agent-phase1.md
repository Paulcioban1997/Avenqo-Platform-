# Agent vocal Avenqo — Phase 1

Cette phase relie les numéros Telnyx des commerces aux agents Retell et réutilise le CRM/RDV Avenqo. Elle n'ajoute aucun champ aux tables `companies` ou `billing_accounts` et ne modifie aucun tarif.

## Prérequis fournisseurs

La préparation Call Control ne nécessite aucun achat, réservation ni appel de test. Le webhook entrant et les événements `call.initiated`, `call.answered`, `call.bridged`, `call.hangup` partagent `POST https://api.avenqo.ca/api/v1/voice/telnyx/webhook`, au format Telnyx API v2. Une application Call Control Avenqo peut servir plusieurs tenants: seul le numéro appelé, lié à un `VoicePhoneNumber` Telnyx ACTIVE et à sa configuration du même tenant, détermine le tenant. `TELNYX_VOICE_CONNECTION_ID` doit correspondre à la connexion signée reçue.

Signature Ed25519, timestamp fini et fenêtre anti-replay sont vérifiés avant traitement. Les événements sont dédupliqués par ID dans le journal Voice, sans corps brut. Un appel entrant n'attribue jamais un rôle à partir du Caller ID. Sans destination vocale prête, la réception est acquittée `READY_FOR_OWNER_ACTION`, sans commande Telnyx. Une fois configuré, `call.initiated` demande `answer` avec un `command_id` stable; seul `call.answered` permet le transfert, également dédupliqué. Un hangup termine l'accès aux outils sans écraser le résultat métier d'un rendez-vous.

Il n'existe pas encore de WebSocket média Telnyx, de collecteur DTMF/NIP ou de webhook SMS opérateur. Ces événements sont acquittés sans stockage ni transmission au LLM. Le WebSocket `/api/v1/ai/voice/sessions/{id}/stream` est celui du navigateur authentifié, pas un endpoint média à fournir à Telnyx. Les appels récents sont lisibles côté tenant dans `GET /api/v1/voice/status`. Ne pas inventer de callback supplémentaire.

1. Créer manuellement une application Voice API / Call Control et lui donner le webhook ci-dessus, méthode POST, API version 2. Ne pas associer ou acheter de numéro pendant cette préparation. Tout numéro sélectionné ultérieurement devra appartenir exactement à un tenant et être assigné explicitement dans Avenqo.
2. Créer un agent entrant Retell pour chaque commerce. Configurer son SIP trunk d'entrée vers le numéro Telnyx et récupérer l'URI SIP de terminaison Retell.
3. Configurer dans l'agent Retell les six fonctions `check_availability`, `book_appointment`, `reschedule_appointment`, `cancel_appointment`, `transfer_to_human` et `get_business_info`, plus `take_message` pour enregistrer les messages hors horaires. Les POST vont vers les chemins correspondants ci-dessous et envoient `X-Avenqo-Voice-Key` avec la clé dédiée du tenant. Le JSON commun est `{ "call_id": "...", "action_id": "...", "arguments": { ... } }`.
4. Dans le prompt Retell, utiliser les instructions renvoyées par `get_business_info`, annoncer le message de consentement avant l'enregistrement, demander une confirmation explicite de la réservation, et utiliser `transfer_to_human` avec `uncertain: true` après une deuxième incertitude consécutive.

## Variables Railway

Ajouter dans les variables du service backend, sans les committer :

- `TELNYX_API_KEY` : clé API Telnyx avec Call Control et Messaging.
- `TELNYX_PUBLIC_KEY` : clé publique Ed25519 du webhook Telnyx, encodée en Base64.
- `TELNYX_VOICE_CONNECTION_ID` : ID de l'application Call Control autorisée pour les numéros Avenqo.
- `TELNYX_MESSAGING_PROFILE_ID` : profil SMS si l'expéditeur l'exige.
- `RETELL_API_KEY` : clé API Retell.
- `RETELL_API_BASE_URL` : optionnel, défaut `https://api.retellai.com`.
- `RETELL_SIP_DOMAIN` : domaine SIP Retell autorisé, défaut `sip.retellai.com`.
- `RATE_LIMIT_WEBHOOK_PER_MINUTE` : limite technique des webhooks, défaut 120.

Le point d'entrée d'appel vérifie la signature Ed25519 et le timestamp Telnyx avant toute action. Les identifiants Telnyx et Retell restent dans le gestionnaire de secrets Railway; chaque tenant reçoit séparément une clé d'outil `avqv_...`, stockée uniquement sous forme hashée et révélée une seule fois à la création/rotation.

## Configurer un commerce

Activer d'abord le module Voice depuis les contrôles d'entitlements existants, puis s'authentifier avec un compte tenant autorisé (`modules:manage`). Créer la configuration :

```http
POST /api/v1/voice/config
Authorization: Bearer <session-du-tenant>
Content-Type: application/json
```

```json
{
  "business_name": "Commerce exemple",
  "timezone_name": "America/Toronto",
  "opening_hours": {
    "monday": {"open": "09:00", "close": "17:00"},
    "tuesday": {"open": "09:00", "close": "17:00"},
    "wednesday": {"open": "09:00", "close": "17:00"},
    "thursday": {"open": "09:00", "close": "17:00"},
    "friday": {"open": "09:00", "close": "17:00"}
  },
  "services": [{"name": "Consultation", "duration_minutes": 30, "price": 80, "currency": "CAD"}],
  "transfer_phone": "+15145550199",
  "telnyx_phone_number": "+15145550100",
  "preferred_language": "fr",
  "retell_agent_id": "agent_xxx",
  "retell_sip_uri": "sip:agent_xxx@sip.retellai.com",
  "enabled": true
}
```

Copier la propriété `voice_api_key` retournée immédiatement dans la configuration des fonctions Retell. La clé ne sera pas retournée par `GET /voice/config`; utiliser `POST /voice/config/rotate-key` pour la renouveler.

## Endpoints et garantie de réservation

- Telnyx : `POST /api/v1/voice/telnyx/webhook` — signature Ed25519 et fraîcheur vérifiées avant résolution du numéro vers son tenant.
- Retell : `POST /api/v1/voice/retell/webhook` — clé du tenant vérifiée; transcriptions et résumés sont journalisés et reliés au CRM/RDV.
- Fonctions Retell : `POST /api/v1/voice/tools/{check_availability|book_appointment|reschedule_appointment|cancel_appointment|transfer_to_human|get_business_info|take_message}`.
- Une réservation nécessite `confirmed: true`; un appel terminé ne peut plus réserver. Les appels d'outils sont idempotents par `action_id`.
- Le conflit est revérifié dans le `CRMService` existant sous un advisory lock transactionnel Postgres partagé par les créations et déplacements CRM/Voice. Cette garantie traverse les workers Railway.
- Le SMS de confirmation est envoyé par Telnyx après la fin de l'appel si un RDV existe; son statut et le contenu sont consignés dans `crm_communications`. Résumé/transcription sont attachés au RDV comme note CRM.
- Hors horaires, la disponibilité retourne `next_opening` et `take_message`; `take_message` consigne le message dans les notes et communications CRM. Une réservation non confirmée ne crée aucun RDV.

## Migration et simulation

La migration `0022_voice_inbound_agent` ajoute uniquement les tables `voice_business_configs`, `voice_calls` et `voice_tool_actions`, avec clés étrangères tenant-scopées. Déployer les variables fournisseur, sauvegarder la base, puis appliquer `alembic upgrade head` avant de router les appels.

Une simulation HTTP de dix interactions, sans appel téléphonique réel ni réservation, est disponible :

```powershell
$env:VOICE_API_KEY = '<clé tenant créée une seule fois>'
$env:VOICE_AGENT_ID = '<agent Retell du tenant>'
$env:VOICE_TEST_SERVICE_NAME = 'Consultation'
C:\Python-Projects\.venv\Scripts\python.exe scripts\simulate_voice_calls.py
```

Le script refuse toute URL non locale sauf `--allow-production`; il crée des journaux d'appels synthétiques, donc utiliser un tenant de test. Un véritable appel/SMS, la latence opérateur <800 ms et le parcours Telnyx↔Retell ne sont certifiables qu'après configuration des comptes fournisseurs et d'un numéro pilote réel.