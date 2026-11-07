# Premier appel Sandbox : arrêt, limites et livraison contrôlée

## Candidat
Branche codex/avenqo-voice-sandbox-call-limits-20261013, basée sur PR #43 et commit local 3ad758d. Aucun fichier Alembic modifié. API Sandbox actuellement épinglée à 9d05eb3, Production suit main : publier cette branche ne change aucune de ces sources. Les trois configurations Vercel désactivent explicitement son déploiement Git.

## Durée totale et limites exactes
Le délai de 90 secondes part désormais de VoiceCall.started_at (premier événement signé enregistré par Avenqo), pas de l'ouverture média. Le watchdog est programmé dès call.initiated pour le seul garage fictif ; aucune session média n'est nécessaire. Une reconnexion média reçoit seulement le temps restant. Une terminaison Telnyx échouée reste signalée et ne met pas ended_at à une fausse valeur, afin de permettre une reprise.
Ce départ serveur ne mesure pas la sonnerie antérieure à la livraison du webhook. Une latence réseau ou une panne peut retarder l'arrêt : ce n'est pas une garantie universelle de 90 secondes physiques.

## Protection indépendante préparée — non activée
- Dans l'application Telnyx Sandbox seulement : proposer first_command_timeout=true, first_command_timeout_secs=15, conserver inbound.channel_limit=1. Ajouter call_cost_in_webhooks=true pour les relevés. Toute application de ce lot nécessite un accord ; aucun champ n'a été modifié.
- Ce first-command timeout protège l'absence de commande initiale, sans prouver une limite totale après réponse.
- Le SDK officiel expose time_limit_secs sur dial/transfer, mais pas sur answer. Ne pas envoyer un champ non documenté et ne pas transférer/créer un autre leg pour contourner cette limitation.
- scripts/voice_sandbox_watchdog.py prépare un worker séparé de l'API, utilisant seulement la configuration Sandbox. Mode sec par défaut ; --execute exige une approbation distincte. Contrôle du garage, du numéro, de la connexion et verrou du call avant hangup. Exécution toutes les secondes proposée. Ce worker peut survivre à la panne API mais dépend encore de PostgreSQL, Railway et Telnyx ; aucune infrastructure nouvelle n'a été déployée.
- Un arrêt strict géré par Telnyx pour ce leg entrant reste BLOCKED jusqu'à confirmation du fournisseur et test réel autorisé. Aucun message à Telnyx n'a été envoyé.

## OpenAI indépendant
L'interface connectée affiche seulement Avenqo-Project, proj_b7xBKmxOt3AsV79doy8iCuv1, sans spend limit. Ne pas modifier ce projet existant.
Organization settings > Projects > Create : Avenqo Sandbox. Sélectionner le nouveau projet avant API Keys > Create new secret key ; nom avenqo-sandbox-voice, de préférence compte de service dédié. Ne pas créer de clé admin d'organisation. Saisir la clé directement dans OPENAI_API_KEY du seul service API Sandbox, pas dans chat/Git/logs. L'activation de la variable et tout redéploiement exigent un accord séparé.
Project settings > Limits > Spend : proposer 0,75 USD, Enforce a hard limit, alerte basse si acceptée. Autoriser gpt-realtime-2.1, gpt-4o-mini-transcribe et le modèle Central réellement configuré ; conserver gpt-4o-mini-tts seulement si le parcours utilise le fallback TTS. Vérifier l'accès à chaque modèle par lecture avant génération. Le hard limit n'est pas instantané : aucune garantie globale 2 CAD.

## Coûts et crédits
Tarifs publics : Telnyx Voice API 0,002 USD/min + SIP entrant, streaming 0,0035 USD/min. Realtime 32/64 USD par million tokens audio input/output, texte 4/24 USD par million. Ajouter transcription et modèle Central utilisés, éventuel fallback TTS, taxes/change et frais du compte. Pour 90 secondes, Voice API+streaming seuls = 0,00825 USD, hors SIP et IA : ce n'est pas une estimation totale.
VoiceUsageLedger journalise l'usage OpenAI et les crédits, pas la facture Telnyx. L'application Telnyx a call_cost_in_webhooks=false ; le routeur actuel ne traite pas call.cost. Il faut soit préparer un consommateur signé/tenant-isolé, soit réconcilier le relevé Telnyx après appel, sans prétendre à un total réel instantané.
Limites conservatrices proposées : un essai, concurrence 1, aucun transfert/enregistrement/appel sortant, 6 réponses courtes maximum, max_output_tokens explicite côté Realtime ET Central, réserve avant génération, aucune reprise automatique payante. Ces limites de tokens et le plafond cumulé ne sont pas encore appliqués par ce candidat.

## Recette après autorisations séparées
1. Confirmer SHA Sandbox, streaming désactivé tant que non autorisé, clé dédiée, tenant garage, budget et surveillance.
2. Capturer nombre de rendez-vous garage, solde crédits et relevés fournisseurs avant appel.
3. Après GO streaming puis GO payant : un seul appel entrant, chronomètre depuis sonnerie ; phrase « Bonjour, je voudrais prendre rendez-vous demain à 14 h pour mon véhicule. »
4. Résoudre date/heure America/Montreal, disponibilité, nom fictif et confirmation explicite avant création. Vérifier oralement créneau exact. Sans OAuth : CRM local uniquement.
5. Vérifier appointment_id/company_id, créneau ensuite occupé, aucun doublon. Refus de données Retail/Accounting ou autre entreprise.
6. Raccrocher à 90 secondes au plus tard si arrêt automatique non confirmé. Observer fermeture média/Reatime, ledger réglé, fin Telnyx réelle. Échec fournisseur doit rester visible.
7. Corréler call/request/response ids, usage STT/Realtime/Central et crédits avant/après ; aucune transcription, NIP, clé dans logs. Réconcilier coûts après stabilisation des relevés.
8. Français, anglais et espagnol ne sont certifiés qu'après leurs essais réels distincts. Espagnol demeure hors liste Realtime actuelle fr/en. Ne pas changer le tenant du numéro durant ce premier test.

Google Calendar OAuth est optionnel pour la réservation CRM locale ; ne pas annoncer de synchronisation sans OAuth opérationnel. Conserver la procédure privée TELNYX_ROUTING_ROLLBACK.md ; aucun retour en Production sans accord, sauf anomalie couverte par le retour de sécurité.

Sources : https://developers.telnyx.com/api-reference/call-commands/answer-call ; https://github.com/team-telnyx/telnyx-node/blob/master/src/resources/calls/actions.ts ; https://support.telnyx.com/en/articles/4374050-configuring-call-control-texml-applications-voice-api ; https://developers.openai.com/api/docs/models/gpt-realtime-2.1 ; https://developers.openai.com/api/docs/guides/spend-limits ; https://telnyx.com/pricing/voice-api
