# Arrêt du premier appel Sandbox — préparation non déployée

Branche codex/avenqo-voice-sandbox-call-limits-20261013, basée sur PR #43.

- Garage fictif 96f25272-f659-4323-b158-4fc76d761a92, config dd5c1f24-353f-4f68-a6f8-743c02011152.
- Limite Base existante : 1 appel simultané, verrou PostgreSQL du tenant avant admission. Ne pas remplacer cela par un compteur local.
- Correctif candidat : limite 90 secondes de la session WebSocket média Sandbox, incluant son ouverture Realtime. Fermeture audio et règlement du ledger même en cas d'annulation. Tentative de hangup Telnyx bornée à 5 secondes, uniquement après autorisation du ticket et du tenant.
- Arrêt manuel candidat : request_stop(), idempotent, aucun hangup si ticket/tenant non autorisé. Pas de nouvel endpoint HTTP public. En attendant, arrêt humain possible en raccrochant le téléphone ; les événements stop/hangup existants sont traités et testés sans fournisseur.
- Production ne reçoit pas cette limite média. Ses paramètres ne sont pas modifiés.
- La limite démarre à l'ouverture de la session média, pas au premier événement téléphonique. Elle ne constitue donc pas encore une garantie de durée totale de l'appel de 90 secondes.
- Un backend hors service ne peut pas exécuter son watchdog : obtenir/tester un arrêt fournisseur indépendant avant de prétendre garantir une durée ou une dépense totale.
- Le délai de propagation des dépenses, le tarif SIP du compte et le change empêchent de certifier un plafond cumulé exact de 2 CAD.
- Journal existant VoiceUsageLedger : conserver les ids call/request/response, unités STT/Realtime/Central et crédits avant/après. Ne pas publier transcription, NIP ou credentials. Réconcilier les montants avec Telnyx/OpenAI après l'essai, sans masquer les usages manquants.
- Des tests contractuels avec fournisseurs simulés prouvent admission, arrêt, règlement du ledger et isolation ; aucun ne certifie le son réel ou le coût réel.
- Les trois fichiers Vercel désactivent les déploiements Git de cette branche. Aucune publication, fusion ou livraison fait partie de cette préparation locale.

Avant activation : clé OpenAI distincte Sandbox, coût du compte vérifié, autorisation de déploiement, validation du candidat, autorisation séparée de streaming et d'un appel payant. Conserver le retour numéro Production déjà préparé.
