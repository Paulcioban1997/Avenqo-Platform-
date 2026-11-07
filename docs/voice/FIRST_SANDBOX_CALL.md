# Premier appel Sandbox — préparation, aucun appel autorisé

Base déployée : 9d05eb37a20cfe4ff6f0a5485e92a8df980bbce7, Alembic 0053.
Cette branche ajoute des diagnostics et des tests ; elle ne change pas le routage
actif, les variables, les secrets, les migrations ni la logique Voice/CRM.

## Entreprises fictives

`scripts.voice_sandbox_scenarios.py` prépare uniquement de nouvelles entreprises
dans une session explicitement Sandbox/test. Le caller possède la transaction.
Trois agents logiques distincts, plan Base en trial fictif (aucun paiement) :

| Entreprise | Langue / fuseau | Modules | Actions Voice explicites |
|---|---|---|---|
| Garage Montréal QA | fr, Canada / America/Montreal | voice + crm | disponibilités, créneaux, création rendez-vous |
| Ecommerce QA | en / America/Toronto | voice + retail | produits, stocks seulement |
| Empresa QA | es / Europe/Madrid | voice + crm | disponibilités seulement |

Secondaires vides. Aucun numéro acheté ou associé automatiquement. Aucun calendrier
externe connecté. Le profil fr + pays CA vise le français canadien ; la qualité de
compréhension du québécois doit être évaluée pendant l'appel autorisé.
Les 44 langues d'interface ne constituent pas une certification téléphonique.
Le Sandbox Realtime autorise actuellement fr/en seulement : es reste audio BLOCKED.

## Configuration manuelle — ne pas appliquer sans accord

1. Railway → alert-tenderness → **sandbox** → **Avenqo-Platform-** → Variables.
   Conserver toutes les variables existantes. Vérifier l'environnement avant chaque
   saisie. Renseigner les clés directement dans Railway, jamais dans un chat/Git.
2. Telnyx Mission Control → Voice → Programmable Voice → Call Control Applications.
   Choisir une application réservée au Sandbox, jamais celle des clients Production.
   Sa configuration proposée :
   - webhook POST : https://avenqo-platform-sandbox.up.railway.app/api/v1/voice/telnyx/webhook
   - webhook API v2 ; aucune URL de secours Production ; inbound channel limit 1.
   - ne pas autoriser les appels sortants pour cet essai entrant.
   - relever l'Application/Connection ID → TELNYX_VOICE_CONNECTION_ID.
3. Telnyx → API Keys : clé réservée à cette utilisation → TELNYX_API_KEY.
   Telnyx → Keys & Credentials / Public Key : clé publique de vérification des
   signatures → TELNYX_PUBLIC_KEY. Ne pas copier automatiquement la clé Production.
4. Préparer TELNYX_MEDIA_STREAM_BASE_URL :
   wss://avenqo-platform-sandbox.up.railway.app/api/v1/voice/telnyx/media
   Le serveur ajoute /{call_id} : ne pas saisir d'ID ni de clé dans l'URL.
   TELNYX_MEDIA_ENABLED=true et TELNYX_MEDIA_INBOUND_ENABLED=true uniquement lors
   d'une activation Sandbox autorisée, après budget et routage vérifiés.
5. Telnyx → Numbers → My Numbers : identifier un numéro de test existant et confirmer
   qu'il n'est utilisé par aucun client Production. Son association à l'application
   Sandbox nécessite une autorisation téléphonique explicite. Aucun achat proposé.
   Le binding Avenqo doit associer ce numéro au config_id ET company_id du garage.
6. OpenAI Platform → projet distinct Sandbox → Settings → Limits et API keys.
   Vérifier que la clé Sandbox est rattachée à ce projet, le modèle gpt-realtime-2.1
   est accessible, fr/en sont autorisés. Ne pas modifier les limites du projet Production.
7. Retell est optionnel pour Telnyx media + OpenAI. RETELL_API_KEY est absent ;
   ne pas migrer de fournisseur ni activer SIP/Retell pour contourner Telnyx.
8. Google Cloud Console → APIs & Services → Credentials : client OAuth Web réservé
   au test, Calendar API activée, compte de test autorisé. L'URI de callback est
   https://avenqo-platform-sandbox.up.railway.app/api/v1/crm/calendar/google/callback
   → GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET et
   GOOGLE_CALENDAR_REDIRECT_URI dans Railway Sandbox ; ensuite connexion OAuth
   depuis le CRM de l'entreprise fictive uniquement. Sans connexion, le rendez-vous
   demeure CRM local, jamais annoncé comme synchronisé.

## Budget 2 CAD — BLOCKED tant que le plafond cumulé n'est pas démontré

Une limite de canaux borne la concurrence, pas la facture. Les timeouts STT/TTS et
Central AI existants ne sont pas une limite de durée totale ni un plafond financier.
La consultation gratuite du modèle ne prouve pas une négociation audio Realtime.

Avant tout appel : obtenir les tarifs exacts du compte (entrant, streaming, voix,
OpenAI STT/Realtime/TTS et taxes/change), puis borner le coût cumulé de tous les essais.
Exiger : arrêt de durée serveur/fournisseur testé avec horloge simulée, concurrence 1,
nombre total d'essais réservé atomiquement, bornes d'entrée/sortie IA, interdiction
des reprises qui recréent une session facturable et marge pour change/délai de mesure.
Un watchdog local seul ne suffit pas en cas de panne backend ; l'arrêt fournisseur
doit aussi être vérifié. Le code actuel ne prouve pas ce plafond : aucun GO payant.

OpenAI documente des hard limits mais leur propagation peut permettre un petit
dépassement ; une alerte ou un quota de crédits Avenqo ne garantit pas 2 CAD tous
fournisseurs confondus. Source :
https://developers.openai.com/api/docs/guides/spend-limits
Telnyx configuration :
https://support.telnyx.com/en/articles/4374050-configuring-call-control-texml-applications-voice-api

## Recette après autorisation explicite

Un appel entrant vers le numéro Sandbox, aucun appel sortant automatisé.
Phrase : « Bonjour, je voudrais prendre rendez-vous demain à 14 h pour mon véhicule. »
Résoudre demain à 14 h dans America/Montreal, jamais une heure UTC implicite.
Vérifier heures, ressources et disponibilité ; si occupé, proposer un vrai créneau.
Recueillir les informations et la confirmation explicite avant création idempotente.
Créer uniquement dans le company_id du garage ; confirmer oralement date/heure.
Vérifier que le nouveau créneau devient occupé et qu'un retry ne crée pas de doublon.
Sans OAuth, exiger calendar_synced=false / état non synchronisé.

Refuser les outils Retail/Accounting du garage et toutes les données étrangères.
Tester interruption audio, silence, erreur STT/TTS/Realtime, raccrochage et fermeture
de la session IA, sans transcription/NIP/clé dans les logs. NIP DTMF requis pour
les actions privées ; réservation publique distincte, permissions minimales.
Comparer crédits avant/après, coût fournisseur, durée et absence de débit après fin.
Crédits épuisés ou abonnement inactif : blocage Voice explicite, aucun accès gratuit
ajouté. Tester ces erreurs d'abord sans appels payants.

Arrêter si une URL Production, un binding étranger, une erreur de signature, une
perte audio, un débit non borné ou une création CRM ambiguë apparaît. Aucun rollback
de données actives ; aucun déploiement/merge depuis cette branche sans autorisation.
