# Livraison Avenqo Sandbox → Production

## Candidat et périmètre

Branche isolée `codex/avenqo-release-sandbox-20261011`, base sécurité95f3032, réconciliée avec main ba2dda1. Aucune fusion vers main. Production n'est pas modifiée.

- PR31 : environnement de sauvegarde obligatoire, préfixes S3 distincts, rétention limitée au préfixe de l'environnement, archives plates anciennes conservées. Surveillance séparée par environnements GitHub sandbox/production ; une configuration absente fait échouer le contrôle au lieu de le sauter. Accès des deux buckets à configurer séparément, sans recopier de secrets production dans sandbox.
- PR32 : normalisation des objets Stripe Price avant validation de la mensualité. Base2999 et Professional4999 cents CAD, quotas2/5, crédits6500/20000 conservés.
- PR33 : état appointment_booked préservé au raccrochage, tests conversation française/CRM. Fixture de raccrochage corrigée. Ces fournisseurs simulés ne prouvent pas un appel Telnyx réel.
- PR34 : traitement modern/legacy des taxes déjà présent sur la base sécurité conservé ; tests complémentaires importés. Facture PDF doit reprendre uniquement les montants réellement enregistrés par Stripe.
- PR35 : fichiers0049/0050 identiques à la base sécurité, conservés. Graphe0048→0049→0050 unique, sans downgrade. Correction supplémentaire : élargissement non destructif de alembic_version.version_num à128 caractères sur PostgreSQL pour les identifiants historiques longs ; répétition réelle sur une nouvelle base locale isolée.
- PR36 : quotas officiels2/5 et alias Demo validés ; catalogue Flutter de la base sécurité déjà conforme conservé.
- Main : correction Telnyx speak premium avec voix nommées et repli anglais conservée, ainsi que l'accueil tolérant aux erreurs TTS. Les contrôles NIP, concurrence, permissions et consommation de la base sécurité restent présents.
- Sécurité PR27 : séparation MFA/session et compatibilité temporaire des clés conservées. Aucun secret réel remplacé ou révoqué par cette livraison sandbox.

## Portes de validation Sandbox

1. Aucun secret nouveau dans les fichiers/staged changes ; contrôles GitHub du SHA final.
2. Sauvegarde sandbox dédiée vérifiée et restaurable. Preuve antérieure du11octobre : archive20261011T180125640641Z,85 comptages de tables identiques après restauration et déchiffrement MFA réussi. C'est une archive manuelle ; le passage cron du12octobre07:00UTC reste à vérifier séparément.
3. Répétition PostgreSQL0048→0050 avec données témoins conservées ; migration head répétée sans changement. Aucun accès à une base active pendant cette répétition.
4. Backend sandbox épinglé au SHA candidat ; frontend preview de cette branche avec BACKEND_API_URL exclusivement sandbox. Jamais de transaction via une preview pointant vers production.
5. Santé/ready : version exacte, PostgreSQL, artifacts et migrations. Authentification, sessions, MFA, refus multi-tenant, CRM/Retail et chiffrement des9 connecteurs.
6. Deux entreprises synthétiques distinctes : Checkout Stripe TEST Base/Professional, carte de test, webhook signé, droits2/5, factures dans /billing et PDF, échec de paiement et idempotence. Renouvellement à simuler avec Stripe Test Clock sur un client test dédié ; ne pas avancer un client existant sans autorisation.
7. Taxes : adresse et inscriptions fictives exclusivement sandbox ; confirmer calcul TPS/TVQ et concordance Checkout/facture/PDF. Production nécessite les inscriptions fiscales réelles et données de l'émetteur ; ne jamais inventer de numéro fiscal ni ajouter de taxes à une facture payée.
8. Voice réel : quatre variables Telnyx sandbox dédiées et numéro lié manquants. Aucun secret production recopié. Préparer FR bidirectionnel, audio entendu, interruption, NIP DTMF, refus sans crédits et rendez-vous CRM. Google Calendar demande OAuth test dédié. Aucun appel payant ni achat de numéro sans accord sur numéro, destinataire et plafond de coût.

## Livraison Production, après nouvel accord explicite

1. Figer les SHA backend/frontend validés et les résultats E2E. Recontrôler l'absence de commits Cursor nouveaux, la compatibilité main et tous les contrôles. Ne pas annoncer une fonctionnalité disponible si son fournisseur réel reste bloqué.
2. Avant toute bascule, créer une sauvegarde Production récente append-only de la base ET préserver les artifacts du volume API. Vérifier SHA256, restaurer dans une base isolée sans appels externes, comparer les tables, les9 connecteurs concernés et les données MFA. Les anciennes archives ne sont ni renommées ni supprimées.
3. Faire approuver séparément les rotations PostgreSQL, CONNECTOR_ENCRYPTION_KEYS, MFA/session et WooCommerce ; les anciens identifiants compromis sont encore actifs. Nouveau rôle PostgreSQL avec droits adaptés pour API/migrations/sauvegardes ; transition progressive de chaque consommateur, nouvelles écritures/déchiffrement vérifiés avant révocation. Anciennes clés de lecture maintenues seulement pendant la transition et stratégie de restauration des archives documentée. Aucun incident réel résolu avant refus effectif de l'ancien accès et santé des consommateurs.
4. Railway Production suit main et lance actuellement `alembic upgrade head` au démarrage. Une fusion peut donc déclencher une migration automatiquement : accord de fusion, accord de déploiement et migration doivent être coordonnés, pas dissociés par accident. Ne rien fusionner avant sauvegarde/restauration et fenêtre approuvée. Vérifier Vercel, branche de production, variables API et déploiement automatique avant publication. Le frontend actuel sur avenqo.ca est4547f25 ; il doit être livré avec le backend compatible, sans promotion d'une preview configurée sandbox.
5. Appliquer uniquement la migration additive0048→0050 prévue (incluant version_num élargie si nécessaire). Vérifier version head, données, permissions, artifacts et absence d'erreurs avant ouverture commerciale. Ne jamais lancer de downgrade0049/0050 sur les données actives.
6. Déployer backend puis frontend production sur les SHA approuvés et leurs variables production, vérifier /health et /ready, authentification/MFA, lecture CRM/Retail, droits et PDF depuis avenqo.ca. Les endpoints de lecture susceptibles de remettre à zéro un solde sont des écritures et exigent la fenêtre autorisée.
7. StripeLIVE : vérifier devise/prix/mensualité, inscriptions TPS/TVQ réellement actives, webhook live et provenance des factures ; un paiement réel de validation et son éventuel remboursement demandent montant/client/accord distincts. Tester renouvellements via TEST avant LIVE. Voice réel exige son autorisation payante et ses conditions de confidentialité.

## Retour arrière

- Sandbox : réépingler l'API à95f3032 et restaurer la preview précédente. Conserver le schéma0050 et les clés actives : aucune révocation ni downgrade. Backup : revenir au build/configuration sandbox antérieurs en conservant le bucket dédié et toutes les archives.
- Production : conserver les IDs de déploiements API/Vercel avant bascule et leur configuration, mais vérifier d'abord leur compatibilité avec les nouvelles colonnes et clés. Ne pas revenir à un ancien code qui ignore MFA_ENCRYPTION_KEYS après des écritures chiffrées avec la nouvelle clé.
- Une restauration de sauvegarde remplace des écritures récentes : elle exige un accord spécifique et une réconciliation des paiements/webhooks. Un rollback de code compatible est privilégié ; aucune restauration automatique sur production.
- Avant révocation, retour temporaire du consommateur à son ancienne configuration seulement dans la fenêtre autorisée. Après révocation, ne jamais réactiver le secret compromis : corriger avec les nouveaux accès et les clés de lecture de transition autorisées.

## Décisions restant au propriétaire

Accès Telnyx/OAuth sandbox et budget de l'appel ; inscriptions fiscales réelles avant activation commerciale ; fenêtre et périmètre de rotation des secrets Production ; fusion/release Production du SHA validé ; paiement LIVE de contrôle distinct. Le feu vert Production doit être demandé lorsque les portes critiques sont franchies, avec les éventuelles fonctions encore indisponibles nommées explicitement.
