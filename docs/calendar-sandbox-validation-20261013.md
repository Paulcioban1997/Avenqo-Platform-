# CRM–Google Calendar : validation Sandbox du 13 octobre 2026

API déployée : `71512cbbf83a934eed581bf6da21cf6c7742b27e`, Alembic `0054_voice_provisioning`.
La Production, les paiements, Telnyx et le streaming n'ont pas été modifiés.

## Preuves réelles

- Trois variables OAuth chargées dans le processus Railway Sandbox ; callback exact `/api/v1/crm/calendar/google/callback` sur le domaine Sandbox.
- Connexion depuis la preview, compte sélectionné et consentement effectués par le propriétaire de Produits_Ero.
- Callback, échange de code et stockage chiffré vérifiés. Refresh token présent ; rafraîchissement Google réel réussi, nouveau token stocké chiffré.
- Liste des calendriers et free/busy Google réels réussis, sans publication des événements personnels.
- Création depuis l'interface CRM d'une fiche fictive Test Calendar Sandbox et d'un seul rendez-vous `QA Calendar Sandbox 20261013`.
- Création : 15 octobre 2026 à 09:00–09:30 Montréal = 13:00–13:30 UTC ; événement vérifié directement par l'API Google.
- Modification depuis CRM : 09:30–10:00 Montréal = 13:30–14:00 UTC ; événement Google mis à jour vérifié.
- Annulation depuis CRM : statut CRM cancelled, aucun événement test actif dans Google. Historique CRM conservé.
- Un premier essai le 14 octobre à 14:00 a été refusé car Google indiquait GOOGLE_BUSY. Aucun rendez-vous n'a été créé sur le créneau occupé.

## Correctifs proposés, non déployés

- Ne plus reprendre les corps d'erreur Google ou détails des exceptions réseau dans les messages/logs publics. Conserver le statut HTTP utile et la cause interne.
- Renvoyer 409/APPOINTMENT_CONFLICT et un message utile pour les conflits CRM_BUSY et GOOGLE_BUSY, en création et modification.
- Désactiver les déploiements automatiques Vercel pour cette branche de correction.

## Tests et limites

Tests existants Calendar/CRM/Voice CRM : 86 PASS, 1 ignoré. Nouveaux tests ciblés : 16 PASS.
L'isolation multi-tenant, les callbacks rejoués, les erreurs de disponibilité et le refresh sont couverts automatiquement ; cette validation ne constitue pas un appel audio réel.
La connexion Google du propriétaire reste active. La déconnexion applicative existante ne révoque pas le consentement Google : aucun test de révocation réelle n'a été effectué. Une révocation côté Google peut affecter d'autres autorisations du même utilisateur/client ; elle doit être explicitement ciblée et suivie d'une reconnexion si requise.
Le compte OAuth en mode test ne certifie pas l'ouverture commerciale à tous les futurs clients. Les exigences de publication et vérification Google restent à valider avant Production.
