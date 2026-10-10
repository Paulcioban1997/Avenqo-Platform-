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
