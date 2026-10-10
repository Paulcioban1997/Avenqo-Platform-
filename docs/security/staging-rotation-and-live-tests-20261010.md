# Avenqo — staging, rotations et tests externes

Préparation du 10 octobre 2026. Branche locale : `codex/avenqo-security-staging-20261010`. Aucun push, fusion dans main, déploiement, changement de secret réel ou révocation effectué pendant cette préparation. Les bases et volumes existants sont conservés.

## Intégration réalisée

Cursor a été récupéré au dernier HEAD publié `c63ffeee6ac29c28e9643a1bd479913009b9cd96`, après le SHA précédemment contrôlé `5ef9869`. La branche de staging part de PR24/`063ef26`, conserve les corrections locales de sécurité du commit `12b6bf2`, et intègre Cursor localement.

Les quatre conflits ont été résolus avec les versions sécurisées PR24 :

| Script | Fonction conservée | Protection conservée |
| --- | --- | --- |
| audit_db_diff.py | Comparaison du schéma réel aux modèles, y compris Workspace/MFA importés | Configuration explicite par environnement |
| inspect_db_schema.py | Lecture du schéma et de la révision Alembic | Aucun identifiant codé en dur |
| run_migrations.py | Exécution Alembic avec surcharge ALEMBIC_DATABASE_URL | Configuration explicite et échappement des caractères % pour Alembic |
| verify_prod_dataset.py | Contrôle des données/export/nettoyage par API | Session autorisée fournie explicitement ; aucune session privilégiée créée dans la base, aucune donnée client affichée |

La fonctionnalité de vérification du dataset est conservée ; son ancien mécanisme de fabrication de JWT/session est supprimé. Aucune branche publiée ni la PR24 n’a été modifiée à distance.

## Migrations 0049 / 0050 : données et nouveaux rôles

Chaîne unique : `0048_billing_test_documents → 0049_workspace_security_and_business_os → 0050_mfa_recovery_and_lockout`. La0049 ajoute Workspace, documents, automatisations, événements de connexion, champs MFA et contexte RLS. La0050 ajoute les codes de récupération et le verrouillage de connexion. Leurs upgrades sont additifs ; les downgrades supprimeraient des tables/champs et ne font pas partie du retour arrière autorisé.

Les deux migrations ont été exécutées réellement sur la copie PostgreSQL18.6 déjà restaurée, avec le migrateur distinct et le propriétaire NOLOGIN. Résultats : head0050, comptages des78 tables préexistantes inchangés, contraintes étrangères validées, huit nouvelles tables avec RLS forcée et propriété correcte. La restauration précédente réussie n’a pas été répétée.

La RLS de Cursor utilisait des paramètres SET LOCAL perdus à commit/rollback. Staging conserve maintenant le contexte vérifié dans la session SQLAlchemy et le réinstalle à chaque transaction. Les routes utilisant uniquement l’identité, dont Workspace et sécurité, reçoivent également le company_id vérifié. Un test PostgreSQL avec rôle non administrateur prouve l’isolation après commit, rollback, changement d’entreprise et réutilisation de la même connexion du pool. Les paramètres restent locaux à la transaction.

**Sauvegarde :** le nouveau pg_dump échoue avec un compte SELECT simple après FORCE RLS. Sur la copie locale uniquement, l’ajout de BYPASSRLS au rôle de sauvegarde dédié permet un pg_dump complet à0050. Ce rôle reste sans écriture et sans superutilisateur. Il faut prévoir ce droit sur le compte de sauvegarde avant sa bascule réelle ; ne pas le donner à l’API. Contrôler aussi tous les comptes qui doivent lire plusieurs entreprises, notamment le migrateur pour d’éventuels futurs backfills.

La RLS utilise toujours le contexte de confiance de l’application et un bypass explicite. Elle ne remplace pas les filtres company_id ni les permissions. Un accès SQL direct autorisé à fixer le paramètre de bypass doit être traité comme sensible ; ne pas annoncer une protection universelle contre un administrateur ou une injection SQL.

## Sécurité finalisée dans staging

- Secrets littéraux des anciens tests retirés, protections de commit et Gitleaks conservées et étendues. Les essais externes anciens restent désactivés sans opt-in explicite.
- WooCommerce : ancienne et nouvelle signature acceptées temporairement uniquement pour une connexion explicitement configurée ; une ancienne clé maximum ; retrait effectif de l’ancienne après validation.
- Deux CLIs de chiffrement harmonisés sur le même writer atomique. CSV/JSON acceptés, erreurs sensibles masquées, environnement confirmé avant écriture. La commande historique generate n’affiche plus de clé et refuse l’opération ; création réelle via le gestionnaire de secrets autorisé. Les lectures status/verify restent disponibles.
- MFA : une nouvelle configuration ne peut pas désactiver une MFA active sans passer par la désactivation avec code actuel. Le verrou de ligne PostgreSQL sérialise les compteurs de verrouillage et la consommation des codes de récupération. Deux connexions concurrentes avec le même code ont donné exactement une acceptation et un refus sur PostgreSQL réel.
- Le secret MFA est dérivé de AUTH_JWT_SECRET dans le code Cursor. Il ne dépend pas de CONNECTOR_ENCRYPTION_KEYS et n’est pas rechiffré par sa rotation. Ne pas changer AUTH_JWT_SECRET dans cette opération : il faudrait un plan distinct de migration MFA et sessions.

## Preuves nouvelles — sans refaire les contrôles antérieurs réussis

| Contrôle | Résultat / périmètre |
| --- | --- |
| Upgrade PostgreSQL0049/0050 | Réussi, données préexistantes préservées |
| pg_dump après RLS avec nouveau rôle | Réussi avec BYPASSRLS en lecture seule ; échec préalable reproduit sans ce droit |
| Test PostgreSQL transaction/pool RLS | 1 réussi avec véritable connexion non administrateur |
| Workspace, entitlements et Outlook nouveaux/ modifiés par Cursor | 18 tests réussis |
| Régressions MFA/identité et scénario MFA ajouté par Cursor | 3 tests réussis |
| CLI de rotation et garde de secrets après harmonisation | 14 tests réussis |
| API réelle locale0050, nouveau compte API | Création/lecture de tâche, historique de connexion, MFA activation/TOTP, refus de réenrôlement et consommation concurrente unique réussis |
| TypeScript du nouveau web | Réussi, sans émission de fichiers |
| Gitleaks de la combinaison et nouveaux commits Cursor | Nouveaux commits : zéro résultat ; contrôle final de l’index effectué par le garde de commit |
| Probes en lecture seule et graphe/migrations SQLite | 11 tests réussis |
| Deux scénarios média Telnyx modifiés par Cursor | 5 variantes de tests réussies |
| Stripe sandbox externe en lecture seule | GET compte HTTP200 ; aucun paiement, abonnement ou carte créé |
| Telnyx sandbox externe | TELNYX_API_KEY absente : aucun appel API tenté, aucun appel téléphonique créé |

Les contrôles unitaires et l’API locale utilisent des fournisseurs bloqués/simulés. Le GET Stripe est une preuve externe limitée d’authentification ; il ne prouve pas un checkout, un webhook, une taxe, un renouvellement ou un PDF de staging. Les paiements de test antérieurs restent des preuves de leur ancien environnement. Aucun service de staging hébergé au nouveau commit n’est annoncé comme fonctionnel avant déploiement et tests réels.

## Consommateurs et conditions de bascule

Inventaire déjà vérifié, à recontrôler seulement pour les changements depuis cet inventaire et au moment d’exécution :

| Consommateur | Changement préparé | Validation avant retrait de l’ancien |
| --- | --- | --- |
| PostgreSQL Railway, projet alert-tenderness, prod et sandbox séparés | Propriétaire NOLOGIN, accès API/migration/sauvegarde distincts | Propriété des tables/types/séquences, extensions conservées, privilèges futurs, accès administratif neuf |
| API Railway, service24a2afc3-36f8-46d0-b79d-b323755a83f3 | DATABASE_URL API limité, ALEMBIC_DATABASE_URL migrateur | /ready, authentification/MFA, Workspace, droits, crédits, PDF, connecteurs |
| avenqo-daily-backup, service95b8c1d8-aa9a-4d88-9e12-401ffaefd997 | DATABASE_URL sauvegarde SELECT+BYPASSRLS | pg_dump réel après0050, intégrité et restauration d’une nouvelle archive sur cible isolée |
| Réconciliateurs sandbox94d672b3… et00d0f7c9… | Dépendent de l’API, pas d’URL PostgreSQL directe inventoriée | Appels internes autorisés et stabilité des tâches après bascule |
| Scripts opérationnels et CLI rotation | URL explicite, migrateur dédié pour DDL/rechiffrement | Dry-run sans valeurs sensibles ; refus d’erreur/configuration incomplet |
| Commerce et Google Calendar | CONNECTOR_ENCRYPTION_KEYS nouvelle primaire + ancienne lecture temporaire | Toutes les charges des deux magasins lisibles par nouvelle clé seule ; tokens tiers examinés séparément |
| Telnyx média/Voice dans le backend | Dépend de l’API/sa base, ne pas supposer un service DB séparé | Routage numéro→entreprise, contexte/DTMF NIP, droits, crédits et continuité du média |
| Woo Test, huit webhooks vers sandbox | Rotation en place ; mêmes événements et destinations, identifiants des webhooks conservés | Livraison réelle, HMAC nouveau accepté, ancien rejeté après période bornée |

Les identifiants PostgreSQL, la clé Fernet exposée et le secret des huit webhooks restent actifs. Les incidents GitGuardian ne sont pas résolus. L’exposition combinée PostgreSQL+Fernet impose également d’examiner les tokens Shopify/WooCommerce/Calendar déchiffrables ; aucun de ces tokens n’a été révoqué.

## Accès manquants et autorisations : distinction

| Domaine | Accès établi | Manque précis |
| --- | --- | --- |
| GitHub | Fetch et commits locaux ; branche Cursor publiée accessible | Publication staging/aperçus non autorisée ici. Dix environnements GitHub historiques restent non lisibles ; leur existence n’établit pas un consommateur actif. Vérifier lesquels sont encore utilisés avant bascule |
| Railway API/PostgreSQL | SSH et lectures de configuration/DB déjà réussis ; sauvegarde téléchargée et restaurée auparavant | Autorisation d’écriture, rotation et redéploiement contrôlé attendue. Droits de mutation à confirmer avant exécution sans mutation de test en production |
| Sauvegardes Railway | Lecture stockage et intégrité/restauration prouvées | Validation après bascule du cron, arrêté entre exécutions ; ne pas le réveiller sans accord si cela déclenche un déploiement |
| Vercel | Déploiements/aperçus connus | Inventaire des noms/références des variables par environnement et liaison staging→API staging non obtenu via accès actuel. CLI Vercel absent ici ; ne pas affirmer que tout consommateur potentiel est inventorié |
| Stripe | Authentification externe sandbox HTTP200, environnement existant | Nouveau staging hébergé et session client pour tester le checkout/webhook/PDF de ce commit. Production fiscale : inscriptions fiscales réellement actives et coordonnées légales à confirmer, aucune inscription fictive en live |
| Telnyx | Code/contrats préparés, preuves antérieures conservées | TELNYX_API_KEY absente du backend sandbox ; clé dédiée, connection_id, clé publique de signatures, routage du numéro et média vers staging à vérifier/configurer après accord. Numéro destinataire et budget pour appel réel à préciser |
| WooCommerce | API lecture et vérification MySQL des8 hooks réussies auparavant | Autorisation de modifier leur signature et preuve des droits d’édition avant rotation ; pas de suppression/recréation |
| Shopify | Connecteurs lisibles et preuves antérieures conservées | Boutique de test et scopes de lecture/écriture adaptés aux actions sélectionnées ; session OAuth à renouveler si tokens compromis/expirés. Pas de commande réelle sur une boutique cliente sans accord |
| Google Calendar | Chiffrement lisible ; fixture sandbox préservée | La fixture sandbox révoquée n’est pas un OAuth valide. Reconnexion interactive d’un calendrier de test autorisé ; créneau et règles de création/annulation à choisir. Ne transmettre aucun mot de passe/token dans le chat |

## Procédure d’exécution préparée

1. Fixer le SHA staging final, scanner ses fichiers et l’index ; conserver l’état actuel des environnements dans le canal privé. Publier/déployer uniquement après accord sur les effets Git/Vercel/Railway. Faire pointer le frontend staging vers le backend staging au même niveau de migrations ; ne pas le relier involontairement à la production.
2. Émettre les nouveaux comptes PostgreSQL distincts sur la base existante. Préparer propriétaire/privilèges par défaut, migrateur et sauvegarde SELECT+BYPASSRLS. Ne pas accorder BYPASSRLS à l’API. Vérifier les nouvelles connexions avant changement des consommateurs. Aucun transfert global REASSIGN OWNED de postgres.
3. Bascule sandbox d’abord, avec API/migrateur puis sauvegarde et tâches internes. Valider réellement les scénarios ci-dessous. La production est une autorisation indépendante. Prévoir une fenêtre contrôlée : une réplique API unique ne garantit pas zéro interruption.
4. Bascule PostgreSQL production : validation de chaque consommateur, puis seulement rotation de l’ancien accès administratif exposé, synchronisée avec le serveur et les variables Railway. L’édition seule de POSTGRES_PASSWORD ne change pas une base existante. Prouver le refus d’une nouvelle connexion ancienne et traiter les sessions encore ouvertes de façon ciblée autorisée.
5. Chiffrement : clés neuves distinctes par environnement dans le gestionnaire sécurisé, nouvelle en tête ; anciennes en lecture temporaire. Dry-run sur les deux magasins, écriture atomique avec verrouillage et comparaison des valeurs avant update, contrôle avec clé primaire seule. Retirer ensuite l’ancienne clé applicative et vérifier le redémarrage. Conserver la récupération des sauvegardes historiques dans un coffre distinct.
6. WooCommerce sandbox : déployer la double vérification bornée, configurer la nouvelle signature et l’ancienne temporaire pour la bonne connexion, mettre à jour les8 hooks existants. Vérifier événements réels et rejoués sans double traitement, retirer l’ancienne puis prouver son refus. Ne pas forger un succès de webhook à partir d’un test HMAC local.
7. Sauvegarde après bascule : créer et restaurer une archive récente avec le nouveau rôle sur une cible isolée, incluant les nouvelles tables RLS. Le succès antérieur à0049 ne remplace pas ce contrôle.
8. Révocation des tokens tiers éventuellement exposés : décisions séparées par compte/boutique/calendrier. Historique Git : nettoyage préparé après révocation, sans force-push automatique, avec coordination des clones Cursor.

Retour arrière : conserver les migrations additives ; aucune downgrade0049/0050 et aucune restauration sur la base active. Revenir au code précédent seulement s’il conserve les nouveaux droits et les protections MFA : un ancien serveur ignorant MFA ne peut pas être utilisé après activation de MFA pour des utilisateurs réels. Avant révocation, coexistence des accès pendant une fenêtre courte ; après révocation, réparer avec un nouvel accès administratif, jamais réactiver un secret exposé. Chiffrement : double lecture pendant transition, charges originales préservées jusqu’à vérification. WooCommerce : accepter les deux signatures seulement pendant la fenêtre prévue ; si une livraison échoue, arrêter le retrait de l’ancienne et corriger avant de continuer.

## Scénarios réels prêts à exécuter après mise à disposition de staging

| Scénario | Action externe réelle prévue | Preuve à recueillir sans secrets | Condition / limite |
| --- | --- | --- | --- |
| Stripe Base | Carte test, abonnement29,99 CAD/mois, taxes sandbox avec adresse/inscriptions fictives déjà autorisées | IDs test Checkout/Payment/Invoice, statut payé, lignes taxes, abonnement Avenqo et PDF téléchargeable dans /billing | Clé test uniquement ; ne remplacer aucun abonnement existant non autorisé |
| Stripe Professional | Même parcours49,99 CAD/mois ; limites/modules Professional | Paiement et webhook réels Stripe test, facture/PDF, crédits inclus20000, modules≤5 | Aucun débit réel ; ne changer aucune quantité de crédits incluse |
| Packs volontaires | Starter1000/10 CAD, Growth4000/35 CAD, Power10000/80 CAD, hors taxes | Paiement test, ajout exact une fois, consommation actualisée, facture/PDF | Commercialisation désactivée tant que rentabilité réelle multi-fournisseur non validée ; aucun dépassement automatique |
| Stripe idempotence/échec | Rejeu événement signé test et carte de refus | Zéro double crédit/double facture ; état d’échec honnête | Pas de facture payée inventée ni d’événement non signé accepté |
| Telnyx entrant + média | Appel réel au numéro staging, dialogue audible, saisie NIP au clavier DTMF | ID appel, événement signé vérifié, flux audio, NIP correct/incorrect, action autorisée, usage | Budget approuvé et numéro routé vers sandbox ; aucune réponse Voice quand crédits épuisés, blocage explicite comme demandé |
| IA Central web | Dialogue texte puis voix audible dans compte staging | Réponse réelle, audio reçu, permissions outils, crédits affichés | Central continue sans crédits selon règle utilisateur ; ne pas étendre cette exemption à Voice téléphone |
| Shopify/WooCommerce | Lecture réelle catalogue/commandes test, événement de boutique test, sync et rejeu | IDs d’événements, statut delivery, comptages avant/après, pas de doublon/tenant croisé | Mutations seulement dans boutique test désignée ; aucun email client/commande payante réel |
| Google Calendar | OAuth réel, disponibilité, création puis annulation d’un rendez-vous test | ID d’événement, présence dans le calendrier, rapprochement CRM, créneau libéré, fuseau Montréal | Calendrier/participant/créneau autorisés ; ne pas envoyer d’invitation à un tiers sans instruction explicite |
| Fin de rotation | Reconnexion neuve refusée pour ancien PG, charges lisibles sans ancienne Fernet, ancienne signature Woo refusée | Résultats négatifs et positifs, /ready, sauvegarde/restauration récente, erreurs surveillées | Incidents ouverts tant que ces preuves ne sont pas obtenues |

La matrice de preuve finale distingue : code/test local, accès externe en lecture seule, transaction fournisseur réelle en mode test, staging hébergé, puis production. Aucune de ces catégories ne remplace les autres.

## Décisions nécessitant l’autorisation du propriétaire

1. Publication de la branche staging et déploiements **sandbox/preview seulement**, avec leurs intégrations automatiques.
2. Rotations réelles **PostgreSQL, chiffrement et WooCommerce**, d’abord sandbox puis production séparément ; confirmation des droits et de la fenêtre de bascule, y compris sessions anciennes et compte de sauvegarde BYPASSRLS.
3. Provisionnement/routage Telnyx sandbox et **budget d’appel réel**, boutiques/calendrier de test et actions réversibles autorisées. Aucun débit Stripe réel demandé.
4. Renouvellement éventuel des tokens tiers exposables et, ultérieurement, nettoyage/publication de l’historique Git. Aucun force-push ni fusion main implicitement autorisé.

L’immatriculation de PMC Solutions AI et l’éligibilité fiscale de production ne sont pas déduites des tests fiscaux sandbox. Les règles commerciales et taxes de production doivent être confirmées avant activation payante internationale.
