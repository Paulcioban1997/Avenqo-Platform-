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
- Vérifier l'événement exact après DELETE Google : cancelled, 404 ou 410 requis ; un événement encore actif ou une vérification réseau en échec ne constitue pas un succès.
- Conserver calendar_id et event_id dans l'audit d'annulation avant de libérer la liaison active.
- Refuser l'annulation d'un événement lié si sa connexion Calendar est indisponible.
- Empêcher un changement de calendrier ou de compte Google tant que des événements Google restent liés, pour éviter une suppression sur le mauvais calendrier.

## Contre-vérification de l'annulation

Après le signalement de visibilité persistante par le propriétaire, recherche API sur les quatre calendriers accessibles du compte autorisé, puis GET par ID exact : un seul événement correspond au titre, à la description fictive, à sa création et à son horaire.
ID `pjloasb0tpk0f5de9thitslt24`, calendrier principal ; statut Google `cancelled` depuis `2026-10-13T22:51:26.497Z`.
Suppression idempotente limitée à cet ID, après vérification de l'identité : DELETE retourne 410 Gone ; GET retourne 200 avec status cancelled. Google conserve une trace annulée, ce qui n'est pas un événement actif.
La recherche du titre exact dans Google Calendar affiche « Aucun résultat trouvé ». Aucun échec de suppression initiale n'est démontré pour cet événement précis ; la cause de l'ancienne visibilité signalée n'est pas établie.
Les autres rendez-vous n'ont pas été modifiés.

Déconnexion applicative réelle de Produits_Ero suivie d'une reconnexion OAuth avec intervention du propriétaire sur l'avertissement Google : connexion rétablie.
La révocation côté Google n'est pas lancée : Google documente qu'elle invalide les scopes et jetons de tous les clients du même projet pour l'utilisateur concerné. Le projet `avenqo-509823` contient le client Sandbox et un client Avenqo préexistant ; un projet Google séparé est nécessaire pour garantir un essai de révocation sans impact potentiel sur Production.
Source : https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke

## Ordre de livraison préparé

- PR #48 : `71512cb`, déjà déployée en Sandbox, migration 0054.
- PR #49 : `32ae194`, migration 0055, encore non déployée.
- PR #50 : intégration de #49 et durcissement Calendar, sans nouvelle migration ; doit suivre #49. Les seuls conflits d'intégration étaient les trois fichiers vercel.json et leurs exclusions de déploiement, réunies sans supprimer de protection.
- Tests locaux sur l'intégration : 124 PASS, 1 ignoré (Calendar, CRM, appels longs et permissions Voice).
- Sauvegarde Sandbox fraîche restaurée en PostgreSQL isolé, répétition 0054 → 0055 et préservation vérifiée des données CRM, connexions chiffrées, utilisateurs et configurations Voice ; aucune migration sur la base active.
- Aucun déploiement, achat de numéro ni appel audio déclenché par ces opérations.

## Tests et limites

Tests existants Calendar/CRM/Voice CRM : 86 PASS, 1 ignoré. Nouveaux tests ciblés : 16 PASS.
L'isolation multi-tenant, les callbacks rejoués, les erreurs de disponibilité et le refresh sont couverts automatiquement ; cette validation ne constitue pas un appel audio réel.
La connexion Google du propriétaire reste active. La déconnexion applicative existante ne révoque pas le consentement Google : aucun test de révocation réelle n'a été effectué. Une révocation côté Google peut affecter d'autres autorisations du même utilisateur/client ; elle doit être explicitement ciblée et suivie d'une reconnexion si requise.
Le compte OAuth en mode test ne certifie pas l'ouverture commerciale à tous les futurs clients. Les exigences de publication et vérification Google restent à valider avant Production.
