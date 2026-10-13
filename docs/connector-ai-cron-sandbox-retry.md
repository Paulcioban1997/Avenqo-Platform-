# Sandbox connector AI cron : retries bornés

Incident 13 octobre 2026, 11 h 45 Montréal : l'API remplaçait ses instances. Les logs HTTP Railway montrent un 502 causé par connection dial timeout vers l'instance amont. L'API répond 200 après le remplacement. Le cron réussi de 11 h 40 annonçait claimed=0. Un redéploiement du cron, démarré à 11 h 48 indépendamment de ce travail, est observé ; ce correctif n'est pas déployé.

Le client actuel abandonne au premier HTTPError. Correctif : uniquement environnement Railway Sandbox exact et endpoint HTTPS /internal/connector-ai/evaluate attendu. 502/503/504 peuvent être rejoués au maximum 3 fois, backoff 1 puis 2 secondes, aucun nouveau retry après 20 secondes. Le premier timeout reste 60 secondes ; un premier appel long ne sera pas rejoué hors fenêtre. Pas de retry pour auth, 500, timeout réseau, réponse JSON invalide ou autre URL/opération.

Sécurité métier : ce n'est pas une politique générique de retry POST ni une clé d'idempotence fictive. L'API évalue une file durable avec unicité par tenant/source/dataset/génération et claims verrouillés. Baux minimum 30 secondes, Sandbox actuellement 900 secondes ; fenêtre de retries 20 secondes. Une évaluation terminée n'est plus sélectionnée, une claim active n'est pas reprise et un échec transitoire est repoussé de 5 minutes. Test réel SQLite isolé : première requête traite et commit, réponse proxy simulée 502, deuxième requête claimed=0, dispatcher appelé une seule fois. Ne pas prétendre exactly-once universel après expiration d'un bail ou changement des règles serveur.

Logs JSON : event, attempt, http_status/error_class, backoff et claimed uniquement. Aucun token, URL, body ou texte brut d'exception. Échec définitif code sortie 1, succès 0. Le calendrier */5 * * * *, les secrets, la base et les autres services restent inchangés.

Validation : 28 tests locaux, file d'évaluation et auth inclus. Lecture seule Sandbox : aucun doublon de génération d'évaluation ni de training associé à un connecteur détecté. Aucun POST réel d'évaluation lancé pour tester le correctif ; aucun entraînement forcé.

Déploiement futur : seulement avenqo-connector-ai-cron, environnement e5adc24d-23b9-4275-84de-91a7801649b8, projet 062bbe91-68e7-4e79-8de7-cffeb8a5f5cd. Épingler le commit de la branche séparée après revue, conserver commande python -m backend.app.services.connector_ai_cron_trigger et calendrier. Vérifier absence d'autres changements en attente. Autorisation explicite avant déploiement ; pas de merge staging-sandbox/main car ces branches peuvent déployer plusieurs services.

Cette branche reste locale : aucune publication ne doit déclencher un déploiement Vercel automatique. Si une PR est demandée, ajouter au préalable la protection deploymentEnabled=false pour la branche aux trois configurations Vercel et vérifier les sources Railway.
