# Sandbox Avenqo — vérification préalable au déploiement

Date : 10 octobre 2026. Version autorisée : `fb0119dee34d026bde0b61b845ecd2211ace4903`, uniquement sous condition d'isolation et d'absence de secrets compromis. Cette condition échoue. Aucun déploiement Railway ni migration distante exécutés ; aucune fusion main, révocation ou modification de secret réel. Les contrôles de production ont uniquement lu la configuration et les métadonnées PostgreSQL, sans lire ou modifier les fiches clients.

## Incident GitGuardian #38085296

Signal : Generic Password, commit Cursor `0e71573`, `tests/backend/test_workspace_os.py`. Les cinq usages du littéral correspondent au mot de passe de la fixture d'inscription `tests/backend/test_auth.py`. Ils sont utilisés par un TestClient local, une base temporaire et un enregistreur de notifications, sans connexion à un compte hébergé.

Comparaison privée du candidat avec toutes les variables lisibles des services API et PostgreSQL, dans sandbox et production : aucune correspondance. Cette vérification ne certifie pas tous les services externes ou un usage historique inconnu. Le contexte de création de comptes locaux constitue la preuve de la nature fictive de la valeur signalée.

Correction : suppression des cinq littéraux de ce fichier et utilisation de `non_sensitive_test_password`, fixture générée en mémoire pour chaque test. Le compte MFA est inscrit et connecté avec cette même valeur éphémère. Aucun secret n'est lu depuis l'environnement par cette fixture. Aucun filtre global de secrets ni exemption des tests ajouté.

Les tests invitation/quota et MFA/connexion/récupération passent : 2 réussites. Le contrôle des secrets du code courant et la vérification du diff passent. Le commit historique reste présent ; une correction courante ne supprime pas l'occurrence historique. Aucun incident GitGuardian n'a été marqué résolu. La classification faux positif doit être examinée dans GitGuardian ; les incidents de secrets réels restent indépendants et ouverts.

## Isolation : résultats réels et blocages

| Contrôle | Résultat |
| --- | --- |
| Environnement Railway et configuration ENVIRONMENT | Sandbox confirmé |
| PostgreSQL sandbox / production | Instances distinctes, identifiants système comparés par empreinte ; mot de passe sandbox distinct |
| Mot de passe PostgreSQL sandbox / historique d'exposition contrôlé | Aucune correspondance dans les fichiers connus de l'incident ; ne constitue pas une nouvelle certification de tout l'historique |
| Métadonnées de migration des deux environnements | `0048_billing_test_documents` ; aucune migration appliquée |
| Volume d'artefacts API | Distinct de la production |
| Identifiant logique de volume PostgreSQL Railway | Identique entre environnements ; insuffisant pour conclure à une instance partagée. Les métadonnées PostgreSQL prouvent deux clusters distincts |
| CONNECTOR_ENCRYPTION_KEYS sandbox | **Échec : clé présente dans l'historique exposé et partagée avec la production** |
| AUTH_JWT_SECRET | **Échec d'isolation : partagé avec la production** ; ne pas faire de rotation aveugle, la MFA dépend de ce secret |
| FRONTEND_URL sandbox | **Pointe vers avenqo.ca** ; parcours hébergé sandbox non isolé de bout en bout |
| Autres secrets partagés | SHOPIFY_CLIENT_SECRET, OPENAI_API_KEY, GOOGLE_AI_API_KEY, SMTP_PASSWORD ; présence commune, sans preuve supplémentaire d'exposition de ces valeurs |
| Stripe sandbox | Clé TEST confirmée ; aucun paiement créé |
| Telnyx sandbox | TELNYX_API_KEY manquante |
| Google Calendar sandbox | Configuration OAuth client manquante |

La rotation de CONNECTOR_ENCRYPTION_KEYS doit préserver le déchiffrement existant par transition contrôlée et rechiffrement vérifié. La séparation de AUTH_JWT_SECRET nécessite de traiter les sessions et les secrets MFA sandbox, avec retour arrière explicite ; elle ne doit pas toucher à la production. Séparer les identifiants fournisseurs partagés et les destinations de retour avant de certifier l'isolation des essais. Ces changements réels ne sont pas inclus dans l'autorisation conditionnelle de déploiement du seul code.

## Tests exécutés et non exécutés

| Vérification | Statut / limites |
| --- | --- |
| API sandbox existante `/health` et `/api/v1/health` | HTTP 200 ; concerne la version existante, pas fb0119d |
| Lecture PostgreSQL réelle des métadonnées | Réussie en transaction READ ONLY, sans fiches clients |
| Nouvelle fixture : invitation / quota | Réussie localement |
| Nouvelle fixture : MFA / connexion / récupération | Réussie localement |
| Contrôle des secrets du code courant / diff | Réussi localement |
| Inscription et MFA sur fb0119d hébergé | Non exécutés : déploiement bloqué |
| Abonnements Base et Professional, Stripe TEST, webhook et PDF | Non exécutés : déploiement et parcours isolé bloqués |
| Isolation multi-tenant, CRM et Retail sur fb0119d hébergé | Non exécutés : déploiement bloqué |
| Google Calendar réel | Non exécuté : déploiement bloqué, configuration OAuth manquante ; connexion utilisateur à prévoir |
| Voice réel | Non exécuté : déploiement bloqué, clé Telnyx manquante ; aucun appel ni débit déclenché |
| Migrations 0049/0050 sur sandbox hébergé | Non exécutées : déploiement bloqué. Les validations déjà réussies sur restauration PostgreSQL isolée restent documentées dans le rapport de staging |

## Statut des incidents et suite

- PostgreSQL #38085288 : **ouvert**. L'ancien identifiant de production n'a pas été révoqué ; aucune rotation de production effectuée.
- WooCommerce #38085290 : **ouvert**. Les webhooks du magasin test avaient été confirmés actifs avec la valeur exposée ; aucune rotation/révocation effectuée dans cette phase.
- CONNECTOR_ENCRYPTION_KEYS exposée : **ouvert**, utilisation sandbox reconfirmée.
- Generic Password #38085296 : valeur fictive de test, occurrences courantes remplacées par fixture éphémère ; historique conservé, contrôle GitGuardian encore à revalider. Aucun incident fermé.

Prochaine étape nécessaire : autoriser et préparer séparément l'assainissement des secrets et des destinations **sandbox seulement**, avec conservation des données et des secrets MFA. Puis refaire le contrôle préalable et déployer uniquement une version explicitement autorisée. La correction de fixture est un commit ultérieur à fb0119d ; l'autorisation de fb0119d n'autorise pas implicitement une autre version. La source Railway préparée reste épinglée sur fb0119d, sans application.
