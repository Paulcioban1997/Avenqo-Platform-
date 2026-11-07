# AVENQO — RAPPORT D'AUDIT ET RÉTABLISSEMENT PRODUIT D'URGENCE (PR #72)
**Date :** 25-26 Octobre 2026  
**Branche Git :** `fix/emergency-product-recovery-voice-central-ux`  
**Tenant Pilote :** `Produits_Ero` (`id='9c97cb94-e9f9-46fb-afd4-8a1d21019cff'`, email: `gauffy95@gmail.com`)  
**Numéro Dédié Attribué :** `+1 438-607-5438` (Telnyx)  
**PR GitHub :** [#72](https://github.com/Paulcioban1997/Avenqo-Platform-/pull/72) (empilée sur PR #71 / #70 / #69)

---

## 1. Synthèse des Points Audités et Corrigés

| Priorité | Domaine | Problème Constaté | Cause Racine & Correction | Fichiers Impactés | Statut |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Audit CRM** | **Services & Tarifs Commerciaux** | Modification directe non validée de `crm_services` avec création de tarifs snowboard. | **Restauration stricte des données antérieures** (`Consultation initiale`, `Suivi de traitement`) en DB. Suppression du service fictif. Déplacement des services de snowboard dans des **fixtures de test non publiées** (`tests/fixtures/test_sporting_goods_services.json`). | [test_sporting_goods_services.json](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/tests/fixtures/test_sporting_goods_services.json)<br>PostgreSQL `crm_services` | **PASS** |
| **P0** | **Contrat d'Activation Voice** | Erreur 422 masquée ou assouplie par `extra="ignore"`. | **Standardisation stricte du contrat Pydantic** : champ canonique `confirmed: bool = True`, alias rétrocompatible `confirm`, et interdiction formelle des champs inconnus (`extra="forbid"`). | [voice.py](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/backend/app/schemas/voice.py)<br>[voice.py router](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/backend/app/routers/voice.py)<br>[test_voice_conversational_p2.py](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/tests/backend/test_voice_conversational_p2.py) | **PASS** |
| **P1** | **Téléphonie Unifiée** | Double standard concurrent (partagé vs dédié). | Architecture canonique : numéro dédié `+1 438-607-5438` → IVR Touche 1 (employés, NIP personnel Argon2id, verrouillage 5 échecs) / Touche 2 (clients, sans NIP). Ancien standard relégué dans une section avancée repliée. | [voice-module-view.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/settings/voice-module-view.tsx)<br>[voice-onboarding-wizard.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/voice/voice-onboarding-wizard.tsx) | **PASS** |
| **P2** | **UX Configuration Voice** | Complexité excessive, faux badges verts en `CONFIGURING`. | Nouvel assistant d'onboarding unifié en 5 étapes. Synchronisation exclusive avec le statut serveur `VoiceLifecycleCard`. Bouton d'activation désactivé tant que la checklist est incomplète. | [voice-onboarding-wizard.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/voice/voice-onboarding-wizard.tsx)<br>[voice-lifecycle-card.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/voice/voice-lifecycle-card.tsx) | **PASS** |
| **P3** | **Central AI Live vs Fallback** | Blocage sur flux temps réel ; Risque de confusion entre streaming bidirectionnel et simple microphone. | **Machine à états explicite** (`idle` → `connecting` → `connected` → `listening`/`speaking` → `error`). **Distinction totale et transparente** : lorsque seul le microphone local fonctionne, l'interface affiche explicitement `Mode Dictée Vocale (Web Speech) — DICTÉE (NON-REALTIME)` et ne prétend jamais être en flux 24 kHz Realtime. | [avenqo-copilot.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/shell/avenqo-copilot.tsx) | **PASS** |
| **P5** | **Fraîcheur des Données Retail** | Dataset `Superstore-utf8.csv` actif affiché en STALE sans avertissement. | 5 indicateurs clairs (`Connecté`, `Synchronisation en cours`, `Données périmées (Historique CSV)`, `Connexion requise`, `Erreur`). Notice transparente précisant que le CSV est un historique et non un inventaire en temps réel. | [retail-intelligence-view.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/retail/retail-intelligence-view.tsx) | **PASS** |

---

## 2. Détail Technique des Validations Récentes

### 1. Audit et Restauration de `crm_services`
- **État antérieur retrouvé :** Deux services historiques créés le 2026-10-18 :
  1. `63be1de8-b411-46e5-a99c-ee038548ede9` : `Consultation initiale` (60 min, 90.00 CAD, `is_active=True`)
  2. `7a09243a-f5a8-4153-ae1a-d19c45d4e7fd` : `Suivi de traitement` (30 min, 50.00 CAD, `is_active=True`)
- **Actions correctives exécutées :**
  - Restauration exacte des noms et tarifs historiques dans PostgreSQL pour le locataire `Produits_Ero`.
  - Suppression de la ligne `67e46faa-0de3-4fa7-9ec5-b146cdc133af` (service de réparation créé lors de l'audit précédent).
  - Isolement des services d'équipement de snowboard dans un fichier de fixtures de test non publiées : [`tests/fixtures/test_sporting_goods_services.json`](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/tests/fixtures/test_sporting_goods_services.json).
  - Aucun tarif commercial non autorisé n'est publié.

### 2. Standardisation Stricte de l'API d'Activation
- **Schéma Pydantic :**
  ```python
  class VoiceLifecycleActionRequest(BaseModel):
      reason: str | None = Field(default=None, max_length=500)
      confirmed: bool = Field(default=True, description="Confirmation explicite pour l'action du cycle de vie.")
      confirm: bool | None = Field(default=None, description="Alias déprécié pour confirmed (compatibilité ascendante).")

      model_config = ConfigDict(extra="forbid")

      @model_validator(mode="before")
      @classmethod
      def resolve_confirmed_alias(cls, data: Any) -> Any:
          if isinstance(data, dict):
              data_copy = dict(data)
              if "confirmed" not in data_copy and "confirm" in data_copy:
                  data_copy["confirmed"] = bool(data_copy.get("confirm"))
              return data_copy
          return data
  ```
- **Contrôles vérifiés :**
  - `{ "confirmed": true }` -> Valide.
  - `{ "confirm": true }` -> Valide par rétrocompatibilité avec mapping automatique.
  - `{ "confirmed": false }` -> Rejeté par le endpoint avec HTTP 400 (`Confirmation explicite requise`).
  - `{ "confirmed": true, "extra_field": "val" }` -> Rejeté par Pydantic (`extra="forbid"`).

### 3. Vérité de la Source Voice et Verrouillage d'Activation
- Source de vérité unique : `GET /api/v1/voice/lifecycle/status`.
- Le bouton `Activer l'agent vocal pour le public` dans `VoiceLifecycleCard` est désactivé avec `disabled={busy || !lifecycle?.can_activate || !canManage}`.
- Le backend `VoiceLifecycleService.activate` vérifie l'ensemble des prérequis serveur et renvoie un rejet HTTP 400 fail-closed avec la liste précise des éléments manquants si une tentative d'activation manuelle contournait l'interface.

### 4. Transparence du Fallback Web Speech API dans Central AI
- Lorsque le flux WebRTC / OpenAI Realtime 24 kHz n'est pas actif mais que le microphone de l'utilisateur est disponible via Web Speech API :
  - L'état `isFallbackMode` passe à `true`.
  - Le badge passe de `FR · 24 kHz (REALTIME)` à `DICTÉE (NON-REALTIME)` (ambre).
  - Le titre passe à `Mode Dictée Vocale (Web Speech)`.
  - Une bannière explicative s'affiche : *« Mode dictée vocale locale actif : transcription via le microphone de votre navigateur (sans conversation audio bidirectionnelle temps réel). »*

---

## 3. Matrice de Validation des Tests Automatisés

| Suite de Tests | Commande Exécutée | Résultat |
| :--- | :--- | :--- |
| **Frontend TypeScript Typecheck** | `npx tsc --noEmit` | **0 erreur (Code 0)** |
| **Frontend Vitest** | `npm test -- --run` (12 suites, 153 tests) | **153/153 PASS (Code 0)** |
| **Backend Voice P2 (Lifecycle, Contrats, Grounding)** | `pytest tests/backend/test_voice_conversational_p2.py` | **11/11 PASS (Code 0)** |
| **Backend Business Onboarding (Profils, Horaires, Facturation)** | `pytest tests/backend/test_voice_business_onboarding.py` | **15/15 PASS (Code 0)** |
| **Backend Sécurité NIP & Authentification** | `pytest tests/backend/test_voice_auth_pin_security.py` | **23/23 PASS (Code 0)** |
| **Backend API Configuration NIP** | `pytest tests/backend/test_voice_pin_setup_api.py` | **2/2 PASS (Code 0)** |
| **Total Global** | — | **204/204 PASS (100 %)** |

---

## 4. Garde-Fous de Déploiement Respectés
- **Branche :** `fix/emergency-product-recovery-voice-central-ux`.
- **Aucune fusion vers `main` exécutée.**
- **Aucun déploiement Sandbox ou Production sans accord formel.**
- **Numéro Telnyx `+1 438-607-5438` maintenu en mode sécurisé (aucun appel facturable engagé).**
