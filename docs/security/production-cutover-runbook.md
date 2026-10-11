# Bascule des secrets Avenqo — procédure exécutable après autorisation

Cette procédure remplace les anciens ordres de rotation. Aucune valeur secrète ne doit apparaître dans la commande, les sorties, Git ou un document partagé. Aucun service ni aucune base ne doit être supprimé ou recréé. Les étapes de production nécessitent l'approbation explicite du propriétaire.

## Préparation effectuée

- PR27 : MFA_ENCRYPTION_KEYS séparée de AUTH_JWT_SECRET, avec double lecture Fernet, écriture primaire et ancien comportement conservé si aucune clé MFA explicite n'est configurée.
- `scripts/rotate_mfa_secrets.py` : dry-run par défaut, application atomique avec confirmation d'environnement, verrouillage des lignes et erreurs masquées. Préserve l'activation MFA et les codes de récupération.
- `scripts/rotate_connector_secrets.py` : transition atomique des magasins commerce/calendar, déjà testée avec restauration réelle.
- Nouvelles variables sandbox `SANDBOX_ROTATION_CONNECTOR_NEXT`, `SANDBOX_ROTATION_JWT_NEXT`, `SANDBOX_ROTATION_MFA_NEXT`, `SANDBOX_ROTATION_MFA_LEGACY`, `SANDBOX_ROTATION_WOO_NEXT` stockées dans Railway, sans changement des variables actives et sans déploiement déclenché.
- Sur PostgreSQL local isolé : trois données chiffrées réellement rechiffrées, lecture avec la nouvelle clé seule, sauvegarde avant/après, restauration et comptages des86 tables conservés. Le moteur MFA a été exécuté sur une table temporaire PostgreSQL, sans modification des comptes existants.
- Avec les nouvelles clés sur API et PostgreSQL locaux réels : deux inscriptions/connexions, MFA, création/lecture CRM, refus inter-entreprises, six lectures Retail et trois lectures facturation. Jeton signé par l'ancien secret partagé refusé401. Les notifications et paiements sont des fixtures ; aucun paiement Stripe ni appel fournisseur réel revendiqué.

Preuves sans secrets : `docs/security/evidence/sandbox-key-transition-20261010.json`.

## Consommateurs à basculer

| Identifiant | Consommateurs confirmés | Remplacement |
| --- | --- | --- |
| Ancien PostgreSQL exposé, incident38085288 | Postgres production6f290d34…, API24a2afc3…, sauvegarde95b8c1d8… | Propriétaire NOLOGIN, API limitée, migrateur distinct, sauvegarde SELECT+BYPASSRLS, accès administratif neuf |
| CONNECTOR_ENCRYPTION_KEYS exposée | API production et sandbox ; commerce_connections et crm_calendar_connections | Clés distinctes par environnement ; nouvelle/ancienne puis nouvelle seule |
| AUTH_JWT_SECRET partagé, sans preuve de publication de sa valeur | API des deux environnements ; signature de sessions et ancien chiffrement MFA | Signature distincte ; clé MFA dédiée et maintien temporaire du déchiffrement historique |
| Secret WooCommerce exposé, incident38085290 | Huit webhooks actifs de la boutique Avenqo Woo Test, vers le sandbox | Nouvelle signature, transition bornée sur la connexion concernée, conservation des IDs/topics/destinations |
| Jetons tiers déchiffrables avec DB+clé exposées | Jetons Shopify, clés API WooCommerce, OAuth Calendar stockés dans les magasins chiffrés | Renouvellement/réautorisation par boutique ou calendrier ; rechiffrer ne révoque pas ces jetons |

Les deux crons sandbox94d672b3… et00d0f7c9… n'ont pas de DATABASE_URL directe dans l'inventaire. Vérifier leurs appels internes après bascule. Les noms PostgreSQL de variables sont DATABASE_URL, DATABASE_PUBLIC_URL, PGPASSWORD et POSTGRES_PASSWORD selon le service ; ne pas conserver une valeur compromise comme valeur de secours.

## Ordre de bascule

1. Figer la version approuvée de PR27 et la liste des consommateurs ; préserver la configuration précédente dans un stockage privé. Nouvelle archive PostgreSQL et sauvegarde des artefacts, contrôle d'intégrité et restauration isolée. Relever migration, comptages, politiques RLS et états de connexion avant intervention.
2. Créer les nouveaux rôles PostgreSQL sans supprimer l'ancien. Transférer uniquement les objets applicatifs au propriétaire NOLOGIN dans une transaction, conserver extensions/objets administratifs. Accorder les privilèges courants et futurs. L'API n'a ni SUPERUSER, ni BYPASSRLS, ni appartenance à postgres. Le migrateur peut SET ROLE propriétaire. La sauvegarde reste sans écriture, avec BYPASSRLS requis pour les tables FORCE RLS.
3. Valider les nouvelles connexions, puis basculer API, migrateur et sauvegarde. Tester `/api/v1/ready`, migrations, authentification, RLS, écriture/lecture et pg_dump/restore avec les nouveaux comptes. Conserver l'ancien accès jusqu'au succès de tous les consommateurs. Avec une seule réplique API, prévoir une brève fenêtre contrôlée ; ne pas promettre zéro interruption.
4. Pour MFA, dériver **en mémoire privée** la clé historique du secret de session actuel selon le code existant. Configurer MFA_ENCRYPTION_KEYS avec nouvelle clé dédiée en premier et clé historique en second, puis valider un compte MFA existant. Ce déchiffrement temporaire ne doit jamais devenir un mécanisme d'acceptation des anciens JWT.
5. Configurer CONNECTOR_ENCRYPTION_KEYS nouvelle/ancienne et vérifier toutes les lectures avant écriture. Exécuter les deux dry-runs ci-dessous. Toute donnée indéchiffrable arrête la phase sans révocation ni suppression.

   ```text
   python scripts/rotate_connector_secrets.py
   python scripts/rotate_mfa_secrets.py
   ```

6. Après autorisation de l'environnement concerné, appliquer puis valider les deux transitions. La base et le code doivent être cohérents ; ne pas exécuter l'outil MFA sur une révision qui ne contient pas ses colonnes.

   ```text
   python scripts/rotate_connector_secrets.py --apply --confirm-environment production
   python scripts/rotate_mfa_secrets.py --apply --confirm-environment production
   ```

7. Vérifier toutes les lignes avec chaque clé nouvelle seule, puis retirer les anciennes clés des variables actives et des workers. Vérifier à nouveau les connecteurs et la MFA. Tourner AUTH_JWT_SECRET seulement après cette séparation, avec reconnexion annoncée et test du refus d'un ancien jeton. Ne pas accorder de double lecture JWT avec le secret de production dans le sandbox.
8. Woo Test : vérifier la version qui accepte une ancienne signature maximum, sauvegarder la configuration privée des huit hooks et de la connexion. Configurer la nouvelle signature primaire et l'ancienne signature réellement utilisée par le fournisseur comme précédente. La signature actuellement stockée côté Avenqo différait de celle des hooks ; ne pas présumer qu'elle est la bonne précédente. Mettre à jour les hooks existants, conserver topics/destinations/IDs, vérifier livraisons réelles et idempotence, retirer l'ancienne signature puis prouver son refus. Les nouvelles clés API WooCommerce et OAuth/Shopify demandent des opérations fournisseurs distinctes.
9. Une fois tous les nouveaux consommateurs et sauvegardes validés, renouveler le mot de passe de l'ancien login PostgreSQL et les variables administratives Railway indispensables avec remplacement fonctionnel. Vérifier que l'ancien mot de passe est refusé. Identifier puis fermer les anciennes sessions encore ouvertes dans une fenêtre contrôlée, sans interrompre les nouveaux consommateurs. Ne pas retirer le login administratif Railway ou ses variables aveuglément.
10. Confirmer l'absence de l'ancien identifiant/ancienne clé dans les configurations actives, références partagées, jobs et déploiements de retour arrière. Révoquer les jetons tiers potentiellement déchiffrés. Fermer chaque incident uniquement avec sa preuve de révocation/refus et de bon fonctionnement. Le nettoyage Git reste une opération indépendante, sans force-push automatique.

## Retour arrière

- Avant révocation PostgreSQL : corriger d'abord les privilèges du nouveau rôle. Revenir au code compatible en conservant les nouveaux identifiants ; le recours temporaire à l'ancien accès prolonge l'exposition et exige une décision explicite.
- Après révocation PostgreSQL : utiliser le nouvel accès administratif pour réparer les droits ou créer un autre accès neuf. Ne jamais rétablir le mot de passe exposé.
- Chiffrement : conserver les nouvelles clés et la sauvegarde pré-transition dans le stockage privé. Une configuration double lecture permet un retour au code compatible pendant la transition ; revenir à l'ancienne clé seule après rechiffrement détruirait la lisibilité. Aucun retour vers un code ignorant MFA_ENCRYPTION_KEYS après séparation des sessions.
- Erreur de rotation atomique : rollback global ; aucune ligne partiellement validée ne doit être commitée. Restauration complète uniquement en dernier recours autorisé, avec traitement des écritures intervenues depuis la sauvegarde.
- WooCommerce : préserver les nouvelles signatures ; réparer le consommateur/la destination. Ne pas réactiver automatiquement une signature exposée après son retrait.
- Migrations0049/0050 : préserver les tables ajoutées ; aucun downgrade destructif ni suppression de base dans le retour arrière.

## État des incidents et accès encore nécessaires

38085288 (PostgreSQL), 38085290 (WooCommerce) et l'exposition Fernet restent ouverts : aucune révocation de production effectuée. 38085296 est un mot de passe fictif de test, supprimé du code courant et remplacé par une fixture éphémère ; son occurrence historique reste visible et GitGuardian doit confirmer la classification de faux positif. Aucun incident fermé, aucun scanner désactivé.

La configuration active du sandbox utilise encore les anciens secrets partagés tant que les nouvelles variables ne sont pas activées. Railway héberge maintenant fb0119d, déploiement bac26d09…, constaté sans activation par cet agent ; cette version ne contient pas la nouvelle séparation MFA. Ne pas y basculer AUTH_JWT_SECRET avant de déployer la version compatible et de préparer les données MFA.

Restent à autoriser : fenêtre de bascule/rotation/révocation de production et version exacte à déployer ; opérations fournisseurs sur les boutiques/calendriers concernés ; éventuelle réécriture Git séparée. Accès GitGuardian nécessaire pour classifier38085296. Les tests externes sandbox restent limités par Telnyx absent, OAuth Calendar absent et le FRONTEND_URL vers avenqo.ca ; aucun succès de paiement ou d'appel réel n'est annoncé.
