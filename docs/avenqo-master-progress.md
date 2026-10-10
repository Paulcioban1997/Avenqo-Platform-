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
- Livraison finale vérifiée : code `5e904e8592943916fe82654b89b30df40d763c5a`, sandbox Railway `8fe4a8de-1dbc-49ba-894f-cb02d4d2137a`, production Railway `e82233ba-b2b7-4cfc-af52-19d7aa7ca833` SUCCESS, production Vercel `dpl_HnEFakn4u695KaREeQKzecP4B6Uf` READY avec aliases avenqo.ca/www. /health et /ready, direct et via frontend, confirment le code et l'environnement production ; base, stockage et migrations OK.
- CI finale du code livré : run `38064926962` réussi (477 tests backend, 309 tests Voice/facturation/auth, 123 tests web, build Next, contrôles Flutter). Test HTTP renforcé après CI : deux tests réussis, avec abonnement explicitement inactif et une source Retail connectée ; une réponse générale ne revendique pas cette source.
- Vérification réelle sandbox : compte QA isolé, abonnement Base inactif et zéro crédit ; vraie réponse fournisseur reçue, allocation et crédits achetés inchangés, sécurité/modules/NIP accessibles, pack 6 500 crédits à 1 000 cents CAD. Aucun achat effectué.
- Vérification navigateur production : réponse réelle du panneau supérieur IA Central sur le compte client à zéro crédit, sans faux badge de certification ; carte 6 500 crédits à 10 CAD et opérations Central à coût nul visibles. Preuves locales ignorées : scratch/avenqo-central-production.png et scratch/avenqo-credits-cad-production.png.
- Le test réel a révélé un verrou supplémentaire sur le montage global des routes : il a été supprimé pour les conversations et Central, puis réappliqué aux messages/stream des assistants payants. Les tests prouvent que ceux-ci restent bloqués pour un abonnement inactif.
- Validation NIP client encore en attente : formulaire production ouvert et remis au propriétaire, qui doit saisir et soumettre lui-même ses secrets. Le service et le parcours HTTP ont été testés ; aucun NIP client n'a été changé par l'agent.

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

## Livraison du lot factures, packs et Central vocal — 10 octobre 2026

Code réellement livré : 566ccd6d22a42da12f3692a186e281753e32ec7d. CI38073192089 réussie (483 backend,316 Voice/facturation/auth,124 web,306 Flutter). Vercel production dpl_4RSHP6iJ2d7aVdm5jJFvyJpsYr28 READY ; Railway production5ad18dc3-cbe8-4d1b-a373-9239c7df2096 SUCCESS ; sandbox b6a2c403-ac1b-437f-ab6a-1e0046ead5eb. Health/readiness directs et viaavenqo.ca validés ; base, stockage et migrations OK.

- Facture PDF native Avenqo : toutes les charges persistées, prix CAD, statut payé, solde réel, suppléments et utilisation informative. Facture sandbox réellement payée29.99CAD rendue et inspectée. Les factures test ne sont pas copiées dans la production.
- Packs1000/10CAD,4000/35CAD,10000/80CAD hors taxes ; Enterprise sur devis. Catalogue et administration versionnés, montants historiques préservés, achats volontaires, aucune allocation incluse modifiée et aucun dépassement automatique. OFFRES COMMERCIALES DÉSACTIVÉES : Anthropic401, rotation de clé sécurisée demandée. Réconcilier les coûts réels fournisseur, PSTN, hébergement, Central gratuit et frais avant activation.
- IA Central : bouton mobile haut-droite vérifié en production, réponse texte réelle à zérocrédit ; deux échanges vocaux avec transcriptions et réponses audio réelles dans même session sandbox, solde0inchangé. Écoute sur appareil client encore à confirmer (question pendante). Accueil téléphonique toujours soumis aux crédits et droits, essai réel avec solde positif et NIP non vérifié.

### Prochain lot indépendant : terminer les modules, sans simulations présentées comme fonctionnelles

Marketing actuellement simule la génération avec setTimeout et affiche3.4%/4.2x sans données source (`web/src/components/marketing/marketing-view.tsx`). Aucune API métier Marketing dédiée ni agent Marketing exécutable dans le registre. À remplacer par brouillons persistés, vrai fournisseur IA, limites/permissions/quota côté serveur, segmentation uniquement de modules autorisés, calendrier, historique et approbation avant envoi. Ne pas router ces opérations payantes par le Central inclus pour contourner les quotas du module.

OCR, Agents et Automatisations utilisent encore ModulePreview (`web/src/app/{ocr,agents,automations}/page.tsx`). À implémenter selon mandat : import/extraction/vérification/export OCR, cycle versionné agents Brouillon→Test→Approbation→Publication→Surveillance, workflows conditionnels/simulation/idempotence/publication. Aucune action externe irreversible pendant simulation. Ne pas présenter ces aperçus comme opérationnels.

Rapport détaillé et preuves du lot conservés dans `output/avenqo-release-20261010.md` et `scratch/avenqo-video-final-handoff.md`. Une reprise conserve les derniers choix client (source Superstore, modules Retail et Voice) et ne refait pas le paiement test déjà terminé.

## Lot affichage de la facture test dans /billing — 10 octobre 2026

Demande propriétaire : présenter XVMNAYLP-0006 dans la section Factures actuelle avec téléchargement PDF. Archive séparée `billing_test_documents`, strictement liée au tenant, PDF natif sandbox avec badge TEST et empreinte SHA256. Aucun changement des factures comptables, des totaux fiscaux, du solde ni de l'abonnement de production. Import opérationnel unique vérifiant le propriétaire commun aux deux environnements ; aucune clé sandbox ou autorisation inter-environnement ajoutée au serveur production. API lecture protégée `billing:manage`, téléchargement privé/no-store, accès autre tenant 404, accès anonyme 401. Tests ciblés isolation/exclusion des totaux réussis ; migration additive/bootstrap/rejeu réussie ; 124 tests web et build Next réussis. Livraison à vérifier.

Livraison vérifiée : code `4547f25d1369c362217359f5ea046f686f349bf7`.

- Railway sandbox : `4c4acddb-d929-493b-ac93-bc05f51bdf85` SUCCESS ; production : `bb855723-6fd3-4941-b6d9-880b815d887c` SUCCESS.
- Vercel production : `dpl_EtjvF7RwfkULNjSo4BUB7xknDjrB` READY ; preview : `dpl_AL5Nn8NhRoGdNnMLgUKV58CrJF1z` READY.
- Readiness via avenqo.ca : même commit, migrations, base et stockage OK. 28 tests facturation et 124 web réussis ; build et TypeScript réussis.
- Compte propriétaire Produits_Ero : XVMNAYLP-0006 visible dans Factures, marquée TEST, 29,99 CAD, bouton Télécharger le PDF. Le clic a téléchargé `C:/Users/paulm/Downloads/facture-avenqo-TEST-XVMNAYLP-0006.pdf`. Empreinte identique au PDF archivé ; rendu visuel inspecté.
- Les UUID d'entreprise sont identiques dans le clone sandbox. L'import vérifie l'environnement, le même propriétaire actif et l'absence de cette facture dans le registre comptable de production. Les crédits et l'abonnement de production restent inchangés.
- Preuve écran : `scratch/billing-invoice-pdf-production.jpg`.

Observabilité : aucune ligne contenant error dans les journaux de cette livraison Railway. Accès aux logs runtime Vercel refusé 403 ; CLI non installée. Aucun drain Vercel configuré. Ne pas interpréter le refus comme une absence d'erreurs ; la vérification fonctionnelle du client et du téléchargement est réussie. CI globale 38081364798 encore en cours à ce point.

CI globale 38081364798 : SUCCESS ; backend, contrats Voice/facturation/auth, web et Flutter réussis pour le commit 4547f25.

## Fiscal billing preparation — 2026-10-10
- Persist modern Stripe `total_taxes` and legacy tax components with actual amounts, tax labels/rates and automatic-tax metadata; webhook and invoice sync share the same normalization.
- Native PDF details TPS/TVH/TVQ when recorded components reconcile with the invoice total. No historical paid invoice is recalculated. Issuer tax IDs remain unset unless configured with real values.
- New Checkout automatic-tax path requests customer billing address and requires active Stripe Tax settings, registrations, classification and exclusive pricing. `STRIPE_AUTOMATIC_TAX_ENABLED` defaults false and was verified unset in sandbox and production before release.
- Actual sandbox inspection: TaxSettings pending; head office unset; no registrations; no automatic tax enabled. Explicit approval for fictitious sandbox address/registrations requested under Stripe tax skill. No live registration or tax setting changed.
- Review PDF `output/pdf/Simulation-Taxes-PMC-Solutions-AI.pdf`: two clearly marked hypothetical, unpaid scenarios (QC 29.99 + 1.50 TPS + 2.99 TVQ = 34.48 CAD; ON 29.99 + 3.90 TVH = 33.89 CAD). Both pages rendered and inspected. This is not a real Stripe calculation or issued invoice.
- Validation: billing/tax suite 35 passed; final tax suite 8 passed; modern-tax webhook/PDF focused checks 2 passed. Actual sandbox tax calculation remains pending authorization/configuration. Included subscription credits and existing subscriptions preserved.

## Fiscal deployment and authorized sandbox setup — 2026-10-10
- User explicitly authorized fictitious sandbox fiscal setup and actual production deployment. Production backend 9c1e21e0dc2fd99a9854419410948aefdd5c0b3a delivered successfully (Railway 0fa89aa4-a453-44cf-a3e2-52e73f0cf883); direct API and avenqo.ca proxy readiness database/storage/migrations OK. Frontend remains 4547f25; no frontend changes in this release.
- Sandbox deployment ba1694bc-9906-48bc-9212-c7354a7bf58e SUCCESS, then a second same-code deploy 77bed7ec-7af3-4294-9e33-651ebd949060 applies the corrected CAD Professional mapping. Previously Professional sandbox incorrectly resolved an old USD49 monthly price; new exclusive CAD49.99 price price_1UP7KuK4vojCzpX2O5BiSPw0 created idempotently. Production already resolves CAD29.99 Base and CAD49.99 Professional; no live price changed.
- Sandbox fictitious head office Ottawa, marked SIMULATION, exclusive default tax behavior; existing empty settings verified before mutation. Active sandbox-only registrations taxreg_1UP7LKK4vojCzpX2Hgx1ZxMR (CA standard GST/HST) and taxreg_1UP7LKK4vojCzpX2K6uabK3p (QC provincial QST), livemode false. No government registration or live registration created.
- Eight ACTUAL Stripe Tax calculations compare SaaS business txcd_10103001 and AIaaS cloud business txcd_10105002 for Base/Professional in QC/ON. Both candidates retrieved canonically from Stripe TaxCodes API. Every component is standard_rated, none not_collecting. Totals: Base QC3448/ON3389 cents; Professional QC5748/ON5649 cents. Actual calculation result sheet output/pdf/Resultats-Stripe-Tax-Avenqo-Sandbox.pdf rendered and visually inspected.
- Separate sandbox QA tenants qa-tax-base-sandbox-20261010 and qa-tax-professional-sandbox-20261010 created; existing client not modified. Category confirmation requested under Stripe skill; no category selected/default configured, automatic tax flags remain false, no payment created in this fiscal test and no renewal tested yet. Earlier paid XVMNAYLP-0006 remains unchanged.
- Production Stripe Tax inspection: active head-office settings, inferred_by_currency and txcd_99999999 defaults, ZERO registrations. Preserved all existing settings. Actual collection cannot be claimed/activated before real registrations and classification/exclusive defaults are confirmed.
- CI38085453766 SUCCESS: 483 core backend, 318 Voice/billing/auth, 124 web, Flutter passed. Final local tax suite8 passed. Actual production owner refreshed /billing and downloaded original TEST PDF again, SHA a8a94b23a5eafcb52257eef922f33657629b14ba5c4f31b39e0224310ac5515c unchanged. Screenshot scratch/tax-release-billing-production.jpg. Broad module/Voice/cost reconciliation blockers remain as above.
- Final sandbox follow-up 77bed7ec-7af3-4294-9e33-651ebd949060 SUCCESS, localized Professional CAD49.99 mapping confirmed in running settings, readiness9c1e21e OK. Automatic-tax flag still false. No invoice/card payment/renewal created during these fiscal tests. Preserve pending category confirmation.

## GitGuardian incident 38085288 — local remediation, rotation pending
- Confirmed the exposed PostgreSQL password still matches production Postgres, API and daily backup. Sandbox uses a different password. Incident OPEN until old authentication is demonstrably rejected. No database, volume, live credential or connector key was changed.
- Audited reachable fetched refs/tags (11,315 objects; 54 credential-shaped PostgreSQL URL occurrences including fixtures), current scripts and runtime consumers without displaying secret values. Vercel variable inventory unavailable; external forks/caches and GitGuardian incident closure are not verified.
- Removed literal database credentials from four operational scripts and privileged fake-session creation from dataset verification. Explicit environment configuration now required; fixtures deliberately fictional.
- Added pinned Gitleaks, staged local guard and CI checks. Local hook activated. Connector re-encryption covers both commerce/calendar stores, validates primary-key reads and rolls back the entire transaction on any failure; JSON and CSV key ordering verified.
- Local focused suite: 11 passed, 1 PostgreSQL integration test skipped (Docker daemon unavailable). Broader preceding suite: 110 passed, 1 skipped. PostgreSQL 18 migration/data preservation/old-login revocation will be verified in isolated GitHub CI before any live action.
- Production encrypted stores: 3 readable rows. Sandbox: 8 readable commerce rows and 1 non-Fernet calendar credential requiring safe restoration/reauthorization before complete rotation. Shared production/sandbox encryption keys confirmed; no key exposure asserted.
- Detailed progressive Railway PostgreSQL rotation, connector compatibility/re-encryption and offline Git history cleanup plan: docs/incident-38085288-rotation.md. Explicit production rotation authorization and separate history publication authorization required. No force push performed.

- Follow-up hardening: configuration import/validation errors in connector rotation CLI are suppressed with a generic message; 13 local security tests passed, 1 isolated PostgreSQL test pending CI. GitHub secret names audit: repository empty; 3 of 13 environments readable and empty, 10 unreadable. No claim of exhaustive hosted secret audit.

- PostgreSQL18 integration and connector tests passed in GitHub CI38087402735 (a42e834), with old disposable login effectively rejected after revocation. Web and Flutter jobs succeeded; global backend still running at this point. Additional Railway READ ONLY in-memory cipher rotation verified all 3 production payloads and 8 sandbox commerce payloads; sandbox malformed calendar still unreadable and preserved. No persistent key/data change.
- Further local incident fix: backup and restore password removed from pg_dump/psql arguments; child environment supplies authentication. 3 targeted privacy tests passed, including both simulated calls and parameter preservation. Actual PostgreSQL backup restoration is still required before live rotation.

- Supplemental scan of all63 large/binary history objects using UTF8/UTF16/binary strings found no additional PostgreSQL URL; compressed archives not unpacked. Production backup20261010T070137253149Z (2127888 bytes) SHA256 verified read-only from backup storage via API container; actual PostgreSQL restore remains unverified prerequisite. Cron stopped between runs, not restarted. Local backup suite29 passed; latest privacy suite3 passed. Final CI38087737202 critical security/Web/Flutter successful, backend Voice suite still running. Explicit production PostgreSQL and connector-key rotations requested separately; no answer assumed.


Validation finale du code1c52d96099d3cbaf6b732c692fcedf392685b0bc : CI38087737202 SUCCESS, quatre jobs réussis (sécurité, backend/Voice/facturation, web, Flutter).40 tests de sécurité réussis avec PostgreSQL18, aucun ignoré. URL : https://github.com/Paulcioban1997/Avenqo-Platform-/actions/runs/38087737202 . Les notes ci-dessus « en cours » sont historiques ; cette validation finale les remplace. Aucun mot de passe ou clé de production n’a été changé ni révoqué. Autorisations de rotation toujours attendues ; restauration réelle de sauvegarde toujours préalable. Les correctifs locaux sont publiés en PR24, sans déploiement de ce correctif de sécurité.

## Follow-up verification — actual restoration and least-privilege API

- Real production backup20261010T070137253149Z restored into a NEW local PostgreSQL18.6 database on an internal Docker network, checksum verified. All75 COPY tables /4588 rows match the dump, Alembic0046, zero unvalidated foreign keys, all ORM tables present. No Railway data/credentials changed by this test.
- New local NOLOGIN owner, separate API DML, migration and read-only backup roles verified, including current migration role/default privileges. New backup created using read-only login and restored into a SECOND NEW isolated local database, original counts preserved. Local administrator password rotated; old local password rejected while new API/backup users continued working.
- Actual FastAPI health/readiness, registration/verification/login, account/organizations/subscription/credit/invoice-history reads and logout passed with the new non-superuser API login. External calls blocked; fictitious Stripe configuration only, no real payment claim.
- Sandbox malformed calendar was a known revoked E2E marker. Repaired only that disconnected test fixture by preserving its value encrypted; no OAuth token or reconnection. All9 sandbox connector payloads now pass READ ONLY in-memory re-encryption verification. Real calendar still requires OAuth authorization.
- Follow-up local security/backup/calendar suite41 passed. Restore psql now uses ON_ERROR_STOP and a single transaction to avoid false success or partial writes after SQL error; target connection no longer printed after success.
- Cursor planned branch feat/avenqo-platform-security-and-business-os still not published, actual branch not confirmed. Candidate fix/ci-voice-auth-contracts-20261010 has conflicts in4 scripts and3 tests; it is NOT confirmed as Cursor master work. PR24 remains draft, no merge or production deployment, no production secret rotation. Exact Cursor branch/commit verification remains the readiness gate before asking for real rotation authorization.
- Full evidence, staged procedure, risks and rollback: docs/incident-38085288-rotation.md. Private restore artifacts/local temporary credentials excluded from Git; existing databases/volumes preserved. GitGuardian incident remains OPEN until production credential revoked and old connection rejected.
- Publishing063ef26 unexpectedly triggered three automatic Vercel previews through the existing Git integration. GitHub deployment metadata confirms production_environment=false for all three (web, avenqo-platform-ohw6, avenqo_platform). No further push is performed during this no-deployment authorization window. Local PostgreSQL container and localhost proxy have been stopped, existing test databases/volume and private artifacts retained.
- Final CI38089233548 for063ef262bd679cd7e2778400bb881cafeee61192 SUCCESS: security/PostgreSQL transition, backend/Voice/billing, web and Flutter all passed. Exact Cursor branch remains unconfirmed; PR24 stays draft and unmerged, production credentials unchanged. Final evidence notes kept locally without another push to avoid automatic previews.
- Cursor coordination update: user confirms exact branch feat/avenqo-platform-security-and-business-os is still LOCAL, announced SHA5ef986972d0b757888f89071e5d2192b9419b3ca. Publication requested from Cursor after secret checks. Branch/SHA not yet obtainable on origin; no compatibility claim for unavailable commits or local0049/workspace/web changes.
- Independent graph audit confirms main0046 and PR24 chain0046->0047->0048, single head, zero missing parents/duplicate revisions/cycles. PostgreSQL copy at0048 confirms new tables owned by NOLOGIN owner, API DML without superuser/CREATE and backup read-only; three commercial offers remain disabled.
- Actual new API login credit accounting test on isolated clone passed: PostgreSQL reservation lock, included/purchased debit, usage/provider ledger writes, idempotent settlement and cancelled reservation release. Provider cost simulated, no outbound calls/real payment/production changes. Candidate0048/0049 combination remains a gate until publication and isolated migration rehearsal.

## Cursor published branch and refreshed secret audit — 2026-10-10

- Fetched exact Cursor SHA5ef986972d0b757888f89071e5d2192b9419b3ca; 25 ahead/0 behind fetched main. Non-mutating merge simulation against PR24/063ef26 has four conflicts in operational scripts. Published0047/0048 identical,0049 absent. Uncommitted Cursor Workspace/MFA/web changes not available. Published security router still reports MFA unsupported.
- Combined private snapshot:33 security/migration/rotation/backup tests passed;40 business/auth/Central/Voice-PIN tests passed;76 CRM/calendar/security passed,1 skipped. Actual combined FastAPI works against isolated restored PostgreSQL with new non-superuser API credentials. Full mixed Voice suite stalled and was stopped; no complete Voice validation claimed.
- Refreshed all5983 blobs/11551 reachable objects: six actual production PostgreSQL password occurrences in five historical files, seven active connector-key occurrences in three files, six Woo webhook candidate occurrences in two tests. Known-secret scan includes large/binary blobs; external forks/caches and unpacking compressed archives remain outside scope.
- IMPORTANT correction to earlier key-exposure statement: historical Fernet key matches the active production AND sandbox key. Current published PR24 tests still contain it; working-tree follow-up removes it. Cursor removed the Fernet literals but retains the real Woo webhook secret in both old tests.
- Woo incident38085290 confirmed active by READ ONLY MySQL query: all8 active hooks in Avenqo Woo Test use exposed signing secret, all target current sandbox connection. Avenqo's stored secret differs. No hook or secret changed. Local bounded old/new HMAC verifier and tests prepared, not deployed.
- Extended local/Gitleaks guards cover literal connector keys and Woo signing secrets; current tracked working snapshot reports zero findings. Local tests require explicit external E2E opt-in, secrets loaded only from configuration. No new push to avoid automatic Vercel previews, no merge/deployment/production secret mutation. Incidents remain OPEN.
- Detailed compatibility, evidence, phased rotation and rollback: docs/security/pr24-cursor-compatibility-20261010.md. Resolve script conflicts, inspect future0049 and finish Voice regressions before final execution authorization.
- Voice follow-up: bounded combined run completed202 passing tests before180-second timeout, including all112 media and45 number tests. Standalone agent file74 passed in107.18s, speak contracts9 passed. All four targeted files now have passing results; original mixed-suite stall still unexplained. Final current working-tree guard/Woo/E2E tests24 passed,18 deliberately skipped external tests. No publication or real-secret change.

## Staging integration of Cursor c63ffee — 2026-10-10

- Local staging branch codex/avenqo-security-staging-20261010 created from PR24. Security follow-up preserved in12b6bf2. Cursor latest published SHA c63ffeee6ac29c28e9643a1bd479913009b9cd96 integrated locally; four operational script conflicts resolved with explicit environment credentials and authorized API dataset verification. No remote publication/main merge/deployment.
- Additive0049->0050 actually upgraded the existing isolated restored PostgreSQL18.6 copy using separate migration login. All78 preexisting table counts preserved,8 new forced-RLS tables owned correctly, foreign keys validated. New backup fails with SELECT-only role; isolated backup role BYPASSRLS (still SELECT-only/non-superuser) makes complete pg_dump succeed. Real role change only in local disposable environment.
- Tenant RLS context reapplied per transaction and bound for identity-only routes. PostgreSQL non-superuser test passed after commit/rollback and pool reuse. MFA active reenrollment refused; user row locking prevents recovery-code/lockout races. Real local API0050 confirms task creation/read, login history, MFA/TOTP and exactly one successful concurrent recovery-code consumption.
- New/changed validation:18 Workspace/entitlement/Outlook tests,3 MFA/identity tests,14 CLI/guard tests,11 provider-probe/migration tests,5 changed Telnyx media cases,1 real PostgreSQL RLS test passed. Web TypeScript passed. Prior successful restore and unchanged suites not rerun.
- Cursor CLI now CSV/JSON-compatible, generic errors, explicit environment confirmation and canonical atomic writer. Terminal key generation disabled; no actual new production keys generated. Woo transition preserved.
- Real read-only sandbox provider probe: Stripe account GET200; Telnyx API key absent in sandbox, no request/call made. No payment created; new staging checkout/media/calendar still require hosted staging and authorized provider setup. Detailed consumers/access/authorization matrix and live-test scenarios: docs/security/staging-rotation-and-live-tests-20261010.md. Incidents remain OPEN; real secrets unchanged.
