# Avenqo — suivi unique de stabilité

Mis à jour le 7 novembre 2026. `PASS` signifie qu'un parcours réel a été observé ; un test de code seul est indiqué séparément. La Production n'a subi aucune modification pendant cet audit.

| Priorité | Problème | Cause racine vérifiée | Correctif | Tests effectués | Statut réel | PR associée | Risque de régression |
|---|---|---|---|---|---|---|---|
| P0 | Sauvegarde quotidienne PostgreSQL échoue | Le rôle `avenqo_app` est soumis à RLS sur `accounting_invoices` ; `pg_dump` sort avec code 1 | Diagnostic expurgé et support d'un identifiant de sauvegarde distinct, verrouillé sur la même base. Création du rôle et configuration Railway restent à autoriser. | Reproduction réelle `pg_dump` en Production ; 49 tests locaux de sauvegarde PASS ; sauvegarde administrative ponctuelle et restauration isolée PASS | **FAIL** pour le cron automatique ; sauvegarde ponctuelle vérifiée | PR dédiée à ouvrir ; transition #93 arrêtée | Moyen : ne pas élargir le rôle applicatif ni utiliser `--enable-row-security` qui omettrait des lignes |
| P0 | Le cron ne sauvegarde pas les artefacts du volume API | Le volume `/data/artifacts` n'est pas monté dans le conteneur du cron | Préparer une capture depuis le service détenteur du volume ou une coordination sûre, sans déplacer le volume | Sauvegarde ponctuelle réelle de 61 fichiers vers S3 ; restauration et SHA de chaque fichier PASS | **FAIL** pour l'automatisation quotidienne complète | PR dédiée à prévoir | Élevé : une sauvegarde SQL seule donnerait une fausse impression de reprise complète |
| P1 | Erreur `pg_dump` non exploitable | Le service masquait entièrement `stderr` et ne rendait que le code de sortie | Catégorisation sans valeur sensible ; suppression du dump partiel | Tests RLS, privilèges, version, authentification, DNS, timeout et confidentialité PASS | **À DÉPLOYER** ; aucun changement Production | PR dédiée à ouvrir | Faible : le texte exact du fournisseur reste masqué intentionnellement |
| P1 | Transition de la PR #93 suspendue | Précondition de sauvegarde automatique non satisfaite ; sauvegarde ponctuelle seule | Ne pas reprendre migration 0074 ni fusion avant décision de bascule et vérifications requises | Backup ID `20261107T162834350977Z`, 3 objets S3 intègres, restauration PostgreSQL 18 isolée à 0073 | **BLOQUÉE** ; aucune migration ni fusion | #93 | Élevé si la bascule démarre avant un chemin de sauvegarde durable |
| P1 | CRM / Google Calendar et connexion Preview signalés antérieurement | État actuel non revalidé dans cette phase | Aucun correctif nouveau avant reproduction sur versions réellement déployées | Aucun test supplémentaire dans cette phase | **NON VÉRIFIÉ** | PR antérieures à réconcilier | Moyen : risque de dupliquer des correctifs existants |
| P2 | Autres modules et parcours commerciaux | Aucun défaut actuel établi dans cette phase | Audit ciblé après stabilisation P0, en commençant par les parcours utilisés par les clients | Aucun test E2E supplémentaire dans cette phase | **NON VÉRIFIÉ** | À déterminer | Inconnu |

## Gate de clôture P0

Le cron devra produire une sauvegarde SQL et artefacts, stockée durablement, puis une restauration isolée vérifiée à partir de **son propre artefact**. La sauvegarde ponctuelle déjà validée ne remplace pas cette preuve.

Les restrictions Gate 2 Produits_Ero, Stripe Live, signatures légales, migration 0074 et déploiement Production demeurent en vigueur.
