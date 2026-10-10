# Mandat Avenqo — progression et preuves

Date : 2026-10-10. Branche : `codex/avenqo-master-20261010`.
Point de retour local : `codex/avenqo-before-master-20261010` (`548499e`).

## Correctifs signalés par captures — 10 octobre

- Autorisation explicite du propriétaire : déployer en sandbox et production. IA Central doit répondre même sans crédits ou abonnement actif ; pack 6 500 crédits à 10 CAD.
- Production avant ce lot : frontend `dpl_2T4Qan17t5RAYnFwtxCGvykBFLf7`, backend `3b5e96ed-fba2-4fb0-ae5d-b56178f2adb5`, code `672d087`. Retour possible sur ces versions.
- IA Central : suppression du verrou d'abonnement de son endpoint, prise en charge serveur des coûts fournisseur sans débit client. Contexte limité à la requête et au tenant ; limites de débit, identité, droits, isolation, idempotence et budgets par requête conservés. Aucun crédit ni abonnement artificiellement attribué. Sans abonnement actif, réponses générales réelles sans exécution des outils métier.
- NIP personnel : parcours accessible sans abonnement, réauthentification obligatoire, numéro canadien normalisé, doublons de routes PIN supprimés. Aucun numéro professionnel activé automatiquement. Les anciens helpers restent uniquement pour compatibilité des tests.
- Crédits additionnels : catalogue CAD ; Checkout en CAD au montant serveur approuvé, même si l'ancien prix Stripe est USD. Produit existant réutilisé ; prix et achats historiques préservés. Lecture Stripe réelle confirme l'ancien pack à 1 000 cents USD et son produit actif.
- Facturation : consommation exacte du journal, historique trié par date, auteur réel limité au tenant, auteur inconnu affiché « — ». Voice identifié comme Voice.
- Paramètres : affichage limité aux six modules métier canoniques. Retrait du faux numéro de version et de la promesse permanente « En ligne » du panneau Central.
- Validation initiale : 123 tests frontend et build réussis ; 6 tests Central/NIP via services et routes HTTP réussis ; historique (1), Checkout CAD depuis prix CAD/USD (2), conversation Voice dix tours (1) réussis. Régressions complètes en cours avant livraison.
- Blocage commercial distinct : le compte client observé n'a pas d'abonnement Stripe lié actif et a épuisé son allocation. Le fonctionnement gratuit d'IA Central est autorisé ; cela n'autorise pas l'activation payante des modules ni un achat de crédits.
- NIP de production : aucun PIN personnel saisi ou remplacé par l'agent. La validation finale de son secret appartient au propriétaire.
- Déploiement de ce lot et preuve navigateur : à compléter après vérification effective.

## État vérifié avant intervention

- Dépôt GitHub : Paulcioban1997/Avenqo-Platform-, main et branche feature à 548499e.
- Vercel : projet web, production READY dpl_3ochXF6WSGrfqvDLnbLM2xUz5ESX, commit 73b8747, domaine avenqo.ca confirmé.
- Railway : alert-tenderness, production b9b03d41-2a67-4aab-a6f6-32939d8b81e0, service 24a2afc3-36f8-46d0-b79d-b323755a83f3.
- Déploiement actif Railway cb93fed6-f713-45b1-9482-ef4d8e7afa32, SUCCESS, sans SHA dans ses métadonnées. /health annonce d3d51ca : empreinte potentiellement périmée, ne prouve pas le contenu de l'image.
- Push main 548499e : déploiement Railway SKIPPED. Le code GitHub n'est donc pas automatiquement le code en production.
- Volumes PostgreSQL et artefacts présents. Aucune modification de données de production effectuée.
- Session Produits_Ero ouverte par le propriétaire dans le navigateur intégré. Tableau de bord accessible ; aucun détail métier recopié ici.

## Matrice initiale et travail restant

| Fonctionnalité | État initial constaté | Validation nécessaire |
|---|---|---|
| Authentification | Accessible en navigateur | Régression cookies, refresh, changement d'entreprise |
| Droits multi-tenant | Partiels : administrateur plateforme peut changer librement d'entreprise | Supprimer l'accès implicite, tester rôles et sessions |
| Plans et modules | Base 2 / Pro 5 dans catalogue ; Pro 20 000 crédits ; interface indique encore 3 / 6 | Réconcilier 25 000 crédits sans modifier les abonnements existants |
| Navigation | Six modules dispersés ; sécurité absente | Pages opérationnelles et états issus du serveur |
| Dashboard / Retail | Pages et API présentes, dashboard accessible | Comparaison périodes, provenance, fraîcheur, doublons |
| CRM | Code et API présents | Réservations et calendrier de test autorisé |
| Voice | Code et API présents | Persistance, catalogue réel, simulation, Telnyx signé, quotas |
| Comptabilité | Page et API présents | Permissions, calculs, validation humaine |
| Marketing / OCR | À inspecter | Pipeline réel, permissions, erreurs, approbations |
| Agents | Aperçu ModulePreview | Cycle versionné et exécutions réelles à implémenter |
| Automatisations | Aperçu ModulePreview | Constructeur, moteur, versions, simulation à implémenter |
| IA Central | Copilot et routes présents | Contexte isolé, sources, quotas et fallback |
| Centre de sécurité | Absent de la navigation et des routes | Sessions, révocation, audit, rôles ; MFA non pris en charge |
| Confiance / support / fiabilité | Confiance publique présente | Fonctions privées et preuves à établir |
| Facturation | Code présent avec fallback trompeur et quotas 3 / 6 | Erreurs explicites, prix réels, factures sans numéros inventés |
| Administration | Page et API présents | Accès support autorisé temporaire ; données confidentielles protégées |
| Internationalisation | Catalogues présents | 44 langues, interpolations et nouvelles pages |
| Déploiement | Frontend et backend désynchronisés | Tests critiques puis livraison contrôlée, validation navigateur |

## Règles de reprise

## Lot 1 — implémenté et vérifié localement, livraison en cours

- Centre de sécurité réel `/security` : sessions privées, révocation immédiate, audit filtré, MFA explicitement indisponible.
- Consentement support Retail en lecture seule : destinataire plateforme identifié, 5–60 minutes, expiration et révocation ; aucun accès consenti pendant les essais du compte client.
- Changement d'entreprise limité aux adhésions explicites, rôle de destination, renouvellement des cookies, révocation des anciennes sessions.
- Page `/workspace/modules` alimentée par les droits serveur, IA Central présentée comme incluse.
- Facturation : limites 2/5, packs canoniques sans doublons, aucune offre fabriquée si chargement échoue, retrait des interpolations visibles constatées sur le compte autorisé.
- Voice : persistance relue après sauvegarde, effacement des messages possible, aucune sauvegarde après chargement échoué, catalogue selon modèle, voix choisie préservée, erreur 503 au lieu d'un faux audio silencieux.
- Identité de livraison : manifeste de commit intégré dans le paquet backend afin de ne pas réutiliser une ancienne variable Git.
- Aucun changement de schéma ou migration nouvelle. Aucun paiement, appel, réservation ou envoi marketing effectué.

Validation : 122 tests frontend réussis et build Next réussi (51 routes) ; 37 tests facturation/modules/plans réussis ; 53 tests authentification/isolation réussis dans la passe principale, ancien scénario RH/six modules corrigé et retesté (1 réussite) ; Centre sécurité (5), accès administratif explicite (2), Voice fournisseur simulé (2), empreinte de livraison (1) réussis.

Limites : ce lot ne termine pas le mandat intégral. Agents et Automatisations restent des aperçus. Crédit Pro 25 000, Enterprise contractuel, MFA, couverture 44 langues des nouvelles pages et validation métier complète des six modules restent à traiter. Aucune livraison en production ne peut encore être annoncée.

Référence fournisseur du correctif Voice : [documentation officielle de synthèse vocale OpenAI](https://developers.openai.com/api/docs/guides/text-to-speech).

Travailler par lots testés. Ne pas déclarer les pages d'aperçu fonctionnelles.
Ne pas lancer de paiement, appel facturé, envoi marketing ou réservation réelle pendant une simulation.
Ne pas déployer si l'isolation critique ou une migration échoue.
Préserver les comptes et abonnements existants ; réconciliation sensible avant changement de capacité en production.
Maintenir ce document avec fichiers, routes, tests, commit et état de livraison réellement observés.
