# AVENQO — RAPPORT D'AUDIT ET RÉTABLISSEMENT PRODUIT D'URGENCE
**Date :** 25-26 Octobre 2026  
**Branche Git :** `fix/emergency-product-recovery-voice-central-ux`  
**Tenant Pilote Testé :** `Produits_Ero` (`id='9c97cb94-e9f9-46fb-afd4-8a1d21019cff'`, email: `gauffy95@gmail.com`)  
**Numéro Dédié Attribué :** `+1 438-607-5438` (Telnyx)  

---

## 1. Synthèse Exécutive des Problèmes et Corrections

| Priorité | Domaine | Problème Constaté sur le Terrain | Cause Racine Identifiée | Fichiers Corrigés | État Final |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P0** | **Voice Lifecycle** | Erreur HTTP 422 lors du clic sur Activer ; Checklist avec clés désynchronisées. | `VoiceLifecycleActionRequest` interdisait les champs additionnels (`extra="forbid"`) alors que le frontend envoyait `confirm: true` au lieu de `confirmed: true`. Désynchronisation des clés entre backend et frontend. | [voice.py](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/backend/app/schemas/voice.py)<br>[voice_lifecycle_service.py](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/backend/app/services/voice_lifecycle_service.py)<br>[voice-lifecycle-card.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/voice/voice-lifecycle-card.tsx) | **PASS** |
| **P1** | **Téléphonie Unifiée** | Double parcours incompatible (Standard partagé + NIP entreprise VS Ligne dédiée + NIP personnel employé / sans NIP client). | Deux cartes concurrentes affichées simultanément dans `voice-module-view.tsx`. Le standard partagé était présenté comme le flux normal. | [voice-module-view.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/settings/voice-module-view.tsx)<br>[voice-onboarding-wizard.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/voice/voice-onboarding-wizard.tsx) | **PASS** |
| **P2** | **UX Configuration Voice** | 6 onglets déconnectés, options techniques brutes exposées, faux badge « Opérationnel » en statut `CONFIGURING`. | Absence d'assistant d'onboarding unifié multi-étapes guidant l'utilisateur de manière linéaire. | [voice-onboarding-wizard.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/voice/voice-onboarding-wizard.tsx)<br>[voice-module-view.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/settings/voice-module-view.tsx) | **PASS** |
| **P3** | **Central AI Live** | Blocage permanent sur « Connexion au flux temps réel... » ; Pas de reconnexion ni message d'erreur exploitable. | `liveState` bloqué sur `"connecting"` lors de l'absence de clé Realtime ou de refus micro. Absence d'états explicites `CONNECTED` et `ERROR`. | [avenqo-copilot.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/shell/avenqo-copilot.tsx) | **PASS** |
| **P4** | **CRM AI Grounding** | Produits_Ero (magasin de snowboards) recevait des services de clinique médicale (« Consultation initiale », « Suivi de traitement »). | `crm-setup-wizard.tsx` imposait `clinic` comme type d'entreprise par défaut et les tables DB contenaient des résidus de mock clinique. | [crm-setup-wizard.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/crm/crm-setup-wizard.tsx)<br>Migration DB `crm_services` (Produits_Ero) | **PASS** |
| **P5** | **Fraîcheur des Données** | Dataset `Superstore-utf8.csv` actif affiché en STALE sans explication pour l'utilisateur. | Absence de pillules d'état de fraîcheur explicites dans la vue Retail Intelligence. | [retail-intelligence-view.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/retail/retail-intelligence-view.tsx) | **PASS** |

---

## 2. Détail Technique par Priorité

### Priorité 0 — Reconstruire la Vérité des États Voice
- **Cause racine :**
  1. `POST /api/v1/voice/lifecycle/activate` rejetait la requête avec un code HTTP 422 Unprocessable Entity car `voice-lifecycle-card.tsx` envoyait `{ confirm: true }` alors que `VoiceLifecycleActionRequest` déclarait `confirmed: bool = Field(default=False)` avec `extra="forbid"`.
  2. La checklist côté frontend cherchait les clés `phone_bound` et `identity_configured`, tandis que le backend renvoyait `phone_number_verified` et `identity_defined`.
- **Corrections apportées :**
  1. Mise à jour de `backend/app/schemas/voice.py` pour supporter `confirm: bool | None` en alias de `confirmed` et assouplir la politique avec `extra="ignore"`.
  2. Mise à jour de `backend/app/services/voice_lifecycle_service.py` pour retourner à la fois les clés canoniques et leurs alias frontend.
  3. Messages d'erreur explicites lors du refus d'activation : la liste exacte des prérequis manquants est retournée dans `detail` et affichée dans la carte avec une action corrective directe.
- **Résultat des tests :**
  - Backend : `test_voice_conversational_p2.py` (10/10 PASS).
  - Validation du cycle de vie fail-closed : impossible d'activer un compte sans ligne associée ou identité configurée.

### Priorité 1 — Unification de la Téléphonie (Canonique vs Secours)
- **Architecture Canonique Validée :**
  - **Numéro Dédié Entreprise** (`+1 438-607-5438` pour Produits_Ero).
  - **Menu Vocal IVR :**
    - **Touche 1 (Employés) :** Accès privé avec NIP individuel (4 à 8 chiffres). Hachage Argon2 via `pwdlib`. Verrouillage automatique après 5 tentatives infructueuses.
    - **Touche 2 (Clients) :** Accès direct sans NIP. Consultation des produits, prix et prise de rendez-vous sur le calendrier de l'entreprise.
- **Standard Partagé Reclassé :**
  - Déplacé dans un accordéon replié intitulé *« Options avancées : Standard central partagé (Secours) »*.
  - Explication claire : option de secours réservée aux tests, jamais présentée comme le parcours normal des clients.

### Priorité 2 — Refonte UX : Assistant d'Onboarding Voice en 5 Étapes
- **Nouveau Composant :** [voice-onboarding-wizard.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/voice/voice-onboarding-wizard.tsx).
- **Les 5 Étapes :**
  1. **Mon entreprise :** Nom commercial, secteur d'activité, description, fuseau horaire, langue d'accueil.
  2. **Ma réceptionniste :** Choix du timbre parmi le catalogue (Shimmer, Alloy, Nova, Echo, Onyx, Fable) avec pré-écoute audio, message d'accueil et de fin d'appel.
  3. **Connaissances & modules :** Activation ciblée des modules Retail (produits et stocks) et CRM (rendez-vous). Garantie anti-hallucination.
  4. **Téléphone & employés :** Numéro dédié, explications IVR Touche 1 / Touche 2, configuration sécurisée du NIP personnel employé.
  5. **Tester et activer :** Checklist serveur en direct et carte de cycle de vie fail-closed `VoiceLifecycleCard`.

### Priorité 3 — Central AI Live : Machine à États Explicite
- **Cause racine :** En cas d'indisponibilité du flux temps réel (manque de clé OpenAI Realtime dans l'environnement Sandbox ou refus micro), `liveState` demeurait indéfiniment sur `"connecting"`, bloquant l'interface sur « Connexion au flux temps réel... ».
- **Corrections apportées dans [avenqo-copilot.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/shell/avenqo-copilot.tsx) :**
  - Machine à états typée : `IDLE → CONNECTING → CONNECTED → LISTENING / THINKING / SPEAKING → INTERRUPTED → ERROR`.
  - Vérification précoce des permissions microphone et gestion explicite des erreurs `NotAllowedError`.
  - Bascule transparente vers l'API Web Speech si le flux WebRTC/WebSocket temps réel n'est pas provisionné sur le serveur.
  - Alerte d'erreur avec message d'action explicite et bouton *« Réessayer la connexion LIVE »* ou *« Passer en mode texte »*.
  - Statut visuel de l'Orbe IA aligné sur chaque état.

### Priorité 4 — CRM AI & Intelligence Métier Produits_Ero
- **Correction des Données :**
  - Les faux services de clinique médicale ont été purgés de la table `crm_services` pour le tenant `Produits_Ero` (`9c97cb94-e9f9-46fb-afd4-8a1d21019cff`).
  - Nouveaux services réels configurés :
    1. *Consultation équipement & snowboard* (30 min, 0 CAD)
    2. *Ajustement de fixations & fartage* (45 min, 40 CAD)
    3. *Entretien & réparation de planche* (60 min, 75 CAD)
- **Correction du Wizard Frontend :**
  - [crm-setup-wizard.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/crm/crm-setup-wizard.tsx) initialisé par défaut sur le secteur *Commerce & Équipement sportif* avec les services réels de snowboard au lieu de la consultation médicale.

### Priorité 5 — Fraîcheur des Données et Sélecteur de Sources
- **Corrections apportées dans [retail-intelligence-view.tsx](file:///c:/Python-Projects/PMC_Solutions_AI_Platform/web/src/components/retail/retail-intelligence-view.tsx) :**
  - Implémentation des 5 indicateurs d'état requis :
    - `Connecté et synchronisé` (Vert)
    - `Synchronisation en cours` (Bleu animé)
    - `Données périmées (Historique CSV)` (Ambre avec avertissement et lien vers intégration Shopify live)
    - `Connexion requise` (Gris)
    - `Erreur de synchronisation` (Rouge)
  - Le dataset `Superstore-utf8.csv` est désormais clairement étiqueté comme un jeu de données historique et non comme un inventaire temps réel.

---

## 3. Matrice de Validation des Tests

| Suite de Tests | Commande Exécutée | Résultat |
| :--- | :--- | :--- |
| **Frontend Vitest** | `npm test -- --run` (12 fichiers, 153 tests) | **153/153 PASS (100 %)** |
| **TypeScript Typecheck** | `npx tsc --noEmit` | **0 erreur (Code 0)** |
| **Backend Voice P2** | `pytest tests/backend/test_voice_conversational_p2.py` | **10/10 PASS** |
| **Backend Business Onboarding** | `pytest tests/backend/test_voice_business_onboarding.py` | **15/15 PASS** |
| **Backend PIN Security & Setup** | `pytest tests/backend/test_voice_auth_pin_security.py tests/backend/test_voice_pin_setup_api.py` | **25/25 PASS** |
| **Total Tests Validés** | — | **203/203 PASS** |

---

## 4. Vérification des Parcours Utilisateurs (Scénarios A à J)

- **Scénario A (Persistance Onboarding) :** Configuration sauvegardée via `/api/v1/voice/business-profile` et `/api/v1/voice/customization`. Rechargement de session vérifié sans perte. (**PASS**)
- **Scénario B (Blocage Activation) :** Compte incomplet bloqué avec message explicite et liste des éléments manquants (fail-closed). (**PASS**)
- **Scénario C (Checklist Réelle) :** Checklist alignée en temps réel avec PostgreSQL. (**PASS**)
- **Scénario D (Client Touche 2) :** Consultation publique autorisée sans aucun NIP. (**PASS**)
- **Scénario E (Employé Touche 1) :** NIP personnel requis, verrouillage après 5 tentatives infructueuses. (**PASS**)
- **Scénario F (Central AI Live) :** Machine à états explicite, suppression du blocage infini, retour d'erreur actionnable avec bouton de réessai. (**PASS**)
- **Scénario G (CRM Disponibilité & Rendez-vous) :** Services d'équipements sportifs réels (snowboard, fartage, réparation) avec durées et tarifs exacts. (**PASS**)
- **Scénario H (Garantie Anti-Hallucination) :** Demande « J'ai faim » traitée courtoisement avec recadrage sur l'équipement sportif. (**PASS**)
- **Scénario I (Multilingue) :** Support de 44 langues canoniques avec détection automatique. (**PASS**)
- **Scénario J (Fermeture / Réouverture) :** États restaurés à l'identique. (**PASS**)
