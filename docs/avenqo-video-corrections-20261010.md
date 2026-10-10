# Corrections constatées dans la vidéo du 10 octobre 2026

Périmètre autorisé : corriger les parcours existants, livrer sandbox puis production ; IA Central reste inclus sans crédits. Voice doit rester bloqué sans crédits ou abonnement actif. Paiement de validation demandé : Base 29,99 CAD par mois, fiche existante, mode Stripe test exclusivement.

## Changements

- Lecture audio : autoriser les fichiers audio blob dans la politique de contenu, MP3 explicite, refuser une réponse non audio au lieu de lancer un lecteur cassé.
- Solde partagé serveur : actualisation toutes les cinq secondes lorsque la page est visible, reprise immédiate au retour ; inclure les crédits achetés ; Facturation et Voice consomment le même état que la navigation. Ce mécanisme est une actualisation périodique, pas un flux serveur instantané.
- Voice : avant de lancer le transport IA, contrôler le solde. À zéro, répondre uniquement avec une annonce statique d’indisponibilité puis raccrocher. Ne pas révéler le solde privé à l’appelant. Garder les contrôles de NIP DTMF existants et les droits serveur.
- Facturation : permettre la souscription Base sur un compte non lié, préserver la devise fixe à Checkout, actualiser factures et statut à intervalle régulier et au retour du portail. Signaler une synchronisation Stripe indisponible au lieu de confondre une panne avec un historique vide. Ne pas montrer les factures de seed comme paiements réels.
- CRM : message d’erreur toujours non vide, pas de confirmation inventée ; actualiser le calendrier seulement après une mutation effectivement confirmée.
- Mes modules : six modules métier canoniques uniquement.
- Isolation : empêcher la réaffectation d’une facture existante à un autre tenant ; invalider les réponses de chargement Facturation lors du changement de compte.

## Validation et limitations

124 tests interface passent ; compilation Next réussie, 51 routes ; vérification ESLint sans erreurs sur les neuf fichiers d’interface concernés. Passe backend Voice/preview/facturation : 95 tests passent. Contrôle complémentaire des modifications de synchronisation en cours.

Le tarif de production Stripe inspecté est 2 999 centimes CAD, récurrent mensuel, livemode vrai. Le sandbox avait un ancien tarif 2 800 centimes USD ; un tarif test 2 999 centimes CAD a été créé et sa configuration CAD est préparée pour le prochain déploiement. Aucun paiement réel n’a été lancé.

La livraison, le paiement test, les factures après paiement et un appel avec solde positif doivent encore être vérifiés. Agents et Automatisations restent des aperçus ; ce lot ne termine pas le mandat global. Ne pas annoncer un appel fonctionnel sans essai téléphonique réel.


## Complément de validation avant paiement

Sandbox b494421 : frontend Vercel READY et backend Railway SUCCESS, même empreinte de code ; readiness database/storage/migrations ok. Essai IA Central avec vrai fournisseur : réponse 200 non vide, sans consommation du solde client. Stripe bloque la création du Checkout CAD sur la fiche sandbox existante car elle possède deux abonnements test actifs en USD. Accord demandé pour remplacer uniquement ces abonnements sandbox ; aucune mutation d’abonnement de production.

Correction complémentaire : une facture Stripe payée pour la création initiale d’un abonnement doit restaurer l’allocation incluse, comme un renouvellement. Les crédits achetés sont conservés ; la clé de renouvellement empêche le double crédit en cas de répétition de webhook. Trois tests complémentaires passent. Les nouvelles versions Stripe peuvent fournir la prochaine échéance sur l’item d’abonnement : ce champ est pris en charge.

## Livraison et contrôle du 10 octobre — suite

- Code 9c0b9d0 livré au sandbox (Railway 7075c8c8-7d60-44f1-8445-2393e1078339), puis en production (Railway 8b413b20-7d6a-4a90-942c-380196318305 ; Vercel dpl_zCSyeHT2iEP42zEqcQcGqGhgeL7Z). /health et /ready directs et via avenqo.ca confirment production, SHA, base/stockage/migrations OK. Bref 502 observé pendant le redémarrage, résolu après démarrage.
- CI 38067309768 : 477 tests backend, 312 tests Voice/facturation/auth, 124 tests web et 306 tests Flutter réussis ; compilation Next réussie.
- Session client Produits_Ero reconnectée : réponse réelle IA Central à zéro crédit, pack 6 500 crédits à 10 CAD et historique des opérations sans débit Central constatés dans le navigateur.
- Accord explicite obtenu pour remplacer les deux abonnements sandbox USD actifs. Ils sont annulés sans prorata ni paiement supplémentaire ; historique conservé ; aucun abonnement production modifié.
- Checkout test Base sur la fiche existante préparé : 2 999 centimes CAD par mois, livemode faux, affichage Environnement de test. Paiement encore ouvert/non payé ; la facture après paiement ne peut donc pas être déclarée vérifiée. URL privée conservée uniquement dans scratch.
- Le contrôle en production a détecté une erreur du graphique de consommation : catégorie Voice AI absente de l'agrégateur alors que les opérations Voice sont classifiées. Correction de la catégorie ; deux tests passent, dont 29 crédits Voice, 1 Copilot et exclusion de 999 crédits d'un autre tenant.
