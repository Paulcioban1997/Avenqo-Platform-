# Avenqo — compatibilité PR24 / Cursor et préparation de rotation

État au 10 octobre 2026. Rapport local, sans publication, fusion, déploiement ni changement de secret réel pendant cette phase. Les incidents restent ouverts. Ce rapport remplace les anciennes notes indiquant que la branche Cursor est indisponible ou que l’exposition de la clé de chiffrement n’est pas démontrée.

## Références réellement comparées

| Référence | Commit |
| --- | --- |
| PR24, branche codex/avenqo-master-20261010 | 063ef262bd679cd7e2778400bb881cafeee61192 |
| origin/feat/avenqo-platform-security-and-business-os | 5ef986972d0b757888f89071e5d2192b9419b3ca |
| origin/main récupéré | 7f838debd40c87ff7349fcfea14cd5df0b53918a |
| Ancêtre commun PR24 / Cursor | 4547f25d1369c362217359f5ea046f686f349bf7 |

La branche Cursor publiée correspond au SHA communiqué, avec 25 commits d’avance et aucun retard sur main récupéré. Ses modifications locales non committées ne sont pas incluses dans ce contrôle.

La combinaison a été simulée sans fusion de branche. Quatre conflits de contenu apparaissent :

- scripts/audit_db_diff.py
- scripts/inspect_db_schema.py
- scripts/run_migrations.py
- scripts/verify_prod_dataset.py

Pour les tests de combinaison uniquement, la copie isolée conserve les versions PR24 de ces quatre scripts : configuration explicite par environnement, absence de secret littéral et absence de fabrication de session privilégiée. Ce choix n’a été appliqué à aucune branche publiée. Une résolution finale doit conserver ces protections et examiner les besoins opérationnels de Cursor.

## Migrations et modules

| Domaine | Résultat vérifié | Limite / action restante |
| --- | --- | --- |
| Alembic 0047 / 0048 | Fichiers identiques dans les deux références ; chaîne 0046 → 0047 → 0048, une seule tête | Ne pas modifier rétroactivement ces révisions déjà appliquées aux copies de test |
| Migration 0049 | Absente de la branche publiée | Attendre son contenu, vérifier parent, objets, droits, conservation des données et répétition sur copie restaurée |
| CRM, authentification, sécurité, Workspace publiés | Fichiers comparés identiques entre ces deux HEAD ; tests CRM et sécurité réussis | Aucun résultat sur les nouveaux changements locaux de Cursor |
| MFA | Le routeur publié indique mfa_supported=False | Ne pas annoncer une MFA fonctionnelle à partir de ce SHA ; inspecter sa future migration et ses flux |
| Voice | Différences dans routers/voice.py et voice/providers.py ; contrôles ciblés média, numéro, agent et réponse Telnyx réussis | L’arrêt prolongé de la première suite mixte reste inexpliqué ; aucune preuve d’appel réel après bascule |
| Rotation des connecteurs | Deux implémentations proposées ; lecture Fernet compatible | Choisir une seule procédure, avec comportement d’erreur et retrait de clé clairement défini |

La procédure Cursor par lots conserve les lignes illisibles et peut reprendre ; celle de la PR24 verrouille et vérifie les deux magasins dans une transaction atomique. Pour les volumes observés (3 charges production, 9 sandbox), privilégier la procédure atomique PR24. Les essais du CLI Cursor montrent aussi : CSV accepté, liste JSON rejetée, exception de connexion propagée ; son chemin de génération affiche une clé selon la lecture du code. Ce chemin n’a pas été exécuté. Ne pas utiliser ce CLI tel quel pour la rotation réelle ; éviter toute impression de clé et exiger une confirmation d’environnement avant écriture.

## Secrets : preuves et état de révocation

### PostgreSQL — incident 38085288

Le mot de passe exposé correspond toujours aux configurations PostgreSQL, API et sauvegarde quotidienne de production Railway. La sandbox utilise un autre mot de passe. Le cron de sauvegarde est arrêté entre exécutions ; il n’a pas été redémarré pour cet audit.

Le scan des références récupérées couvre 11 551 objets, dont tous les 5 983 blobs, sans exclusion liée à la taille ou au contenu binaire pour la recherche des secrets connus. Six occurrences du mot de passe effectivement utilisé sont présentes dans cinq fichiers historiques : audit_db_diff.py, e2e_prod_smoke_test.py, inspect_db_schema.py, run_migrations.py et verify_prod_dataset.py. Les 91 URL PostgreSQL ressemblant à des identifiants comprennent aussi des fixtures ; elles ne représentent pas 91 secrets actifs. Aucun exemplaire du mot de passe connu n’a été retrouvé aux deux HEAD comparés.

Limites : forks, caches externes et références non récupérées non accessibles ; archives compressées non décompressées. L’incident n’est pas résolu : l’ancien accès fonctionne encore.

### CONNECTOR_ENCRYPTION_KEYS — exposition confirmée

Une clé présente dans l’historique correspond à une clé encore active en production ET en sandbox. Sept occurrences historiques dans AVENQO_HANDOFF.md et les deux tests phase8_5 / phase8_9 ont été trouvées. Le HEAD publié de PR24 contient encore cette clé dans les deux tests ; Cursor l’a retirée de ces tests. Les deux fichiers du dossier de travail ont maintenant été corrigés localement pour lire la configuration explicitement et désactiver les essais externes sans opt-in.

Cette découverte remplace l’ancien constat « aucune exposition de clé démontrée ». Les secrets PostgreSQL et de chiffrement exposés ensemble augmentent le risque d’accès aux identifiants des connecteurs. Une rotation de chiffrement ne révoque pas les tokens OAuth ou clés des services tiers : leur examen et, si nécessaire, leur renouvellement demandent une opération distincte autorisée.

### WooCommerce — incident 38085290

Le secret de signature candidat des anciens tests est réel et encore utilisé. Une lecture MySQL en transaction READ ONLY dans le projet Railway Avenqo Woo Test confirme qu’il signe les huit webhooks actifs. Ce projet de magasin de test possède un environnement nommé production ; ce nom ne désigne pas la production Avenqo. Les huit destinations pointent vers le connecteur WooCommerce sandbox actuel.

Le secret enregistré actuellement dans ce connecteur Avenqo est différent. Cela établit une incompatibilité de signature, sans prétendre avoir provoqué ou mesuré une livraison HTTP réelle. Aucun webhook, identifiant, statut ou secret distant n’a été modifié. Le champ secret est en écriture seule dans l’API officielle : sa non-présence dans une réponse GET ne prouve pas sa révocation. [Documentation WooCommerce v3](https://developer.woocommerce.com/docs/apis/rest-api/v3/webhooks/).

Six occurrences historiques de cette valeur ont été retrouvées dans les deux tests. Elle subsiste dans un test du HEAD PR24 et dans les deux tests du HEAD Cursor ; les exemplaires actuels du dossier de travail sont remplacés par une valeur explicitement fictive. L’incident reste ouvert jusqu’au remplacement effectif chez WooCommerce, au retrait de l’acceptation de l’ancien secret et aux vérifications de livraison.

## Corrections préparées localement

- Suppression des clés réelles des tests ; lecture CSV/JSON de l’environnement et opt-in obligatoire pour les essais externes.
- Gardes locales et Gitleaks étendues aux clés Fernet littérales et aux secrets de signature WooCommerce codés en dur ; messages limités aux chemins et numéros de ligne.
- Vérification WooCommerce permettant temporairement la clé principale et une seule ancienne clé explicitement configurée dans les identifiants chiffrés. Types invalides, configuration excessive et absence de clé principale sont refusés. Après retrait de l’ancienne clé, son HMAC est rejeté.

Ces changements ne sont ni publiés ni déployés. Le code actuel en service ne bénéficie donc pas encore de la transition WooCommerce préparée. Le dernier push antérieur avait déclenché trois aperçus Vercel automatiques ; aucune nouvelle publication n’est faite tant que les effets de publication ne sont pas autorisés.

## Vérifications exécutées

| Vérification | Résultat |
| --- | --- |
| Copie combinée : sécurité, migrations, CLI, sauvegardes et chiffrement | 33 tests réussis |
| Copie combinée : droits, abonnement, Central et NIP Voice | 40 tests réussis |
| Copie combinée : CRM, calendrier et sécurité | 76 réussis, 1 ignoré |
| Tests locaux WooCommerce, gardes et anciens E2E après derniers changements | 24 réussis, 18 ignorés volontairement car essais externes non activés |
| Copie combinée : contrats Telnyx speak modifiés | 9 tests réussis |
| Copie combinée : fichier complet test_voice_agent.py exécuté séparément | 74 tests réussis, 107,18 secondes |
| Scan Gitleaks des fichiers suivis actuels avec règles étendues | Aucun résultat signalé ; ne garantit pas l’absence de secret de tout format |
| Grande suite mixte CRM / Voice | Progression suspendue, processus local arrêté ; résultat complet non validé |
| Relance Voice bornée à 180 secondes sur copie combinée | 202 tests terminés avec succès avant la limite : 112 média Telnyx, 45 numéro Voice, 45 agent Voice ; aucun échec signalé, exécution globale incomplète |
| Deux reproductions ciblées Voice autour de la suspension | 2 puis 6 tests réussis ; suspension non reproduite, cause non établie |

La CI38089233548 du commit publié 063ef26 est réussie. Elle ne valide pas les nouvelles corrections locales ni une fusion réelle avec Cursor. Les tests de combinaison ont été réalisés sur une copie privée de la simulation, avant les derniers ajustements locaux des gardes et signatures. La relance Voice a progressé jusqu’à sa limite de temps ; elle ne démontre pas que cette nouvelle exécution était bloquée. Les quatre fichiers ciblés couvrent 240 tests ayant signalé leur succès sur ces exécutions : média112, numéro45, agent74 et speak9, sans compter deux fois les45 tests agent déjà exécutés avant la limite. Le premier arrêt prolongé de la suite mixte reste sans cause établie.

Une sauvegarde réelle de production a été restaurée dans une nouvelle base PostgreSQL18.6 locale isolée : 75 tables COPY, 4 588 lignes conformes au dump, contraintes vérifiées. Des rôles locaux distincts propriétaire NOLOGIN, API DML, migrateur et sauvegarde SELECT ont été testés. Les migrations réelles jusqu’à 0048 réussissent avec ces droits. Une sauvegarde créée par le nouveau compte en lecture seule a été restaurée dans une deuxième base neuve, avec préservation des comptages.

Le vrai serveur FastAPI de la copie combinée fonctionne avec le nouvel utilisateur non administrateur : disponibilité, inscription/connexion, compte, organisations, abonnement, solde et historique des factures, déconnexion. La consommation de crédits incluse/achetée, les réservations, écritures de journaux, idempotence et restitution ont également été testées avec PostgreSQL réel. Fournisseurs simulés, appels externes bloqués, aucun paiement réel.

La réparation du calendrier sandbox préserve une fixture E2E révoquée sous chiffrement et exige une réautorisation ; elle n’a créé aucun token OAuth. Neuf charges sandbox et trois production sont lisibles et passent une rotation en mémoire sans écriture. Le conteneur et le proxy locaux sont arrêtés ; volumes et preuves privées conservés hors Git.

## Séquence proposée après vérifications et autorisations

1. Résoudre les quatre scripts dans une branche de préparation ; appliquer les suppressions de secrets sur les deux lignes de développement. Inspecter les changements locaux Cursor dès leur publication, notamment 0049, MFA et Workspace. Revalider la suite groupée dont l’arrêt prolongé reste inexpliqué et refaire le scan des références finales. Aucun merge ni push implicite.
2. Inventorier de nouveau tous les consommateurs Railway et hébergés, sauvegardes et références d’environnement ; accès Vercel incomplets à compléter. Vérifier une sauvegarde récente et les possibilités de redéploiement contrôlé. Obtenir les autorisations explicites séparées PostgreSQL, chiffrement, WooCommerce et déploiement.
3. PostgreSQL : créer des utilisateurs neufs aux droits minimaux sur la base existante, sans supprimer/recréer la base. Vérifier API, migrations, sauvegarde et restauration avant bascule. Basculer progressivement API/migrateur/sauvegarde, surveiller erreurs et connexions. Révoquer l’ancien accès seulement lorsque tous les consommateurs sont vérifiés ; prouver que l’ancienne authentification est refusée. Les sessions déjà établies doivent aussi être inventoriées et drainées/terminées de manière contrôlée.
4. Chiffrement : produire des clés neuves distinctes par environnement par un canal secret ; introduire la nouvelle clé en tête avec l’ancienne temporairement en lecture. Rechiffrer atomiquement les deux magasins, vérifier que la nouvelle clé seule déchiffre chaque charge, puis retirer l’ancienne de l’application. Conserver la récupération des anciennes archives dans un stockage protégé distinct ; ne pas prétendre révoquer cryptographiquement les copies déjà exposées.
5. WooCommerce : activer le vérificateur transitoire sur sandbox autorisé, configurer nouvelle clé principale et ancienne temporaire pour la bonne connexion, mettre à jour les huit webhooks existants sans changer IDs, topics ou destinations. Vérifier signatures et livraisons réelles, laisser une fenêtre bornée pour les événements en vol, retirer l’ancienne et prouver son refus. Ne pas supprimer/recréer les webhooks.
6. Nettoyage de l’historique après révocation : préparer une réécriture hors du dépôt de travail et la liste des références affectées ; coordination des clones/branches/PR avec Cursor. Aucun force-push automatique. Retester et actualiser les incidents seulement après preuves de révocation et de bon fonctionnement.

## Risques et retour arrière

La transition avec deux comptes réduit l’interruption, mais une réplique API unique et les redéploiements Railway ne permettent pas de garantir zéro coupure. Risques principaux : consommateur oublié, droits sur objets futurs, incompatibilité 0049, connexions persistantes, cron non vérifié après bascule et ancien secret de webhook conservé trop longtemps.

Avant révocation, conserver un chemin de retour au code précédent avec les nouveaux accès ; corriger les droits en priorité. Le retour à l’ancien mot de passe reste techniquement possible pendant la fenêtre de transition mais prolonge son exposition. Après révocation, ne jamais le réactiver : utiliser un accès administratif neuf pour réparer les permissions. Pour le chiffrement, conserver la liste ordonnée des clés pendant la transition et les archives originales ; toute restauration doit être testée en environnement isolé. Pour WooCommerce, la double vérification couvre le changement de signature, mais doit être retirée à l’issue de la validation.

La préparation de PostgreSQL et les preuves de restauration sont acquises. La compatibilité publiée est démontrée sur les domaines testés, dont les quatre fichiers Voice ciblés. La0049 non publiée, la résolution finale des conflits et la vérification de la suite groupée empêchent encore d’annoncer l’exécution prête sans réserve. Aucun incident n’est déclaré résolu.
