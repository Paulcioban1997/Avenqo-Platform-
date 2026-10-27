# Intégration locale PR #33 / PR #37 — 11 octobre 2026

## Périmètre et références figées

- PR #33 : `d11ecaf16c0ccd9a0fb2a8abe6f5e5c05aa96a71`.
- PR #37 : `4e6f1cfa33879786480995637ffaa9e276b92ff7`.
- Main : `ba2dda1bcff47a3c748acad7d1c306ef53db1bd0`.
- Branche locale : `codex/avenqo-pr33-pr37-validation-20261011`.
- Assemblage préparé dans un worktree distinct, sans publication, déploiement,
  modification des PR existantes, des bases déployées ou des secrets.

## Résolution des quatre conflits

| Fichier | Résolution préparée |
| --- | --- |
| `.github/workflows/ci.yml` | Conserver la suite sécurité, les contrôles Stripe/sauvegardes et les timeouts de #37 ; ajouter la couverture multilingue de #33 à Voice Master, une seule fois. |
| `backend/app/voice/service.py` | Utiliser `mark_voice_call_booked` de #33, puis conserver le déclenchement idempotent `voice_appointment` de #37. |
| `backend/app/voice/telnyx_media.py` | Conserver `complete_media_hangup`, les états terminaux, la limite d'attente du drainage audio et l'identité du ledger de #33 ; préserver les autorisations et la fermeture de socket de #37. |
| `tests/backend/test_voice_inbound_e2e.py` | Conserver les cinq scénarios de #33, la réception bornée et la protection contre une deuxième lecture après fermeture de #37. |

Un test supplémentaire vérifie ensemble le marqueur de réservation, le tenant,
l'automatisation et l'absence d'un deuxième déclenchement lors d'une répétition.
Les autres changements de #33 (CRM, outils IA, crédits et synchronisation du
calendrier) s'intègrent sans conflit textuel ; ils font partie des validations.

La première validation a aussi révélé un blocage intermittent du nettoyage
audio. La trace montre `_execute_turns` avec une annulation en attente, retourné
sur une file vide. Le candidat ajoute un garde après l'exécution d'un tour pour
propager cette annulation au lieu de repartir dans la file. Un test reproduit
cette condition ; trois répétitions du scénario de conversation avec des tenants
neufs et le test d'automatisation passent. Un ancien drainage non borné réutilise
désormais le helper de #37. Ce correctif additionnel n'est présent dans aucune
des deux PR : il reste à faire examiner et valider dans la CI du candidat.

## Migrations et séparation des environnements

La chaîne reste `0048_billing_test_documents` →
`0049_workspace_security_and_business_os` → `0050_mfa_recovery_and_lockout`,
avec une seule tête. Aucun fichier Alembic n'a été modifié par cet assemblage.
Le correctif #37 agrandissant `alembic_version.version_num` est préservé : les
identifiants de révision dépassent la largeur PostgreSQL habituelle de 32.

La répétition PostgreSQL utilise exclusivement un conteneur local neuf,
accessible sur loopback, sans volume existant ni données de client. Le test crée
sa propre base, passe par 0048, ajoute un témoin, applique 0050 deux fois et
vérifie le témoin et les colonnes MFA. Les tests applicatifs utilisent des bases
SQLite temporaires et des fournisseurs simulés ; aucun appel payant n'est prévu.
Les fichiers frontend, Railway, Vercel et migrations restent identiques à #37.

## Résultats

| Vérification | Résultat et preuve |
| --- | --- |
| Voice, CRM, IA Central, crédits, PIN et migrations | PASS : 300 tests dans `pr33-pr37-final-suite.log`, 216,04 secondes. |
| Contrats Voice Agent | PASS : 74 tests terminés dans le premier lot, `pr33-pr37-integration-tests.log`. Ce lot a ensuite rencontré le blocage audio décrit ci-dessus ; les 300 autres tests ont été rejoués après correction. |
| Régressions propres à l'intégration | PASS : 5 tests, dont trois conversations indépendantes, annulation et automatisation idempotente, `pr33-pr37-cleanup-final.log`. |
| Authentification, MFA, chiffrement, plans et isolation | PASS : 121 tests ; les deux tests PostgreSQL initialement ignorés ont ensuite été exécutés sur la base locale isolée : 2 PASS. Preuves : `pr33-pr37-security-tests.log` et `pr33-pr37-postgres-security.log`. |
| PostgreSQL 0048 → 0050 | PASS : test réel inclus dans les 300, témoin conservé, colonnes MFA présentes et deuxième upgrade sans erreur. |
| Secrets et structure CI | PASS : Gitleaks local sans fuite, garde de secrets, graphe Alembic et registration des suites CI. Aucun conflit non résolu. |
| Frontend et Flutter | Fichiers inchangés par rapport à #37 ; contrôle individuel #467 vert. Pas de nouveau build de l'assemblage. |
| CI GitHub / GitGuardian de l'assemblage | NON EXÉCUTÉE : branche locale non publiée, afin de ne déclencher aucun déploiement automatique. Les contrôles individuels ne remplacent pas ceux du futur SHA commun. |

Les journaux sont conservés dans le dossier privé de preuves du workspace.
Les 374 contrôles applicatifs ci-dessus ont été exécutés en deux lots ; ils ne
constituent pas une nouvelle exécution GitHub Actions complète. Aucun échec ne
subsiste dans les suites rejouées après le correctif. Les avertissements pytest
préexistants sur les marques async restent visibles.

## Ordre recommandé, après autorisation seulement

1. Préparer une fenêtre contrôlée et empêcher qu'une fusion ne déclenche un
   déploiement Production non approuvé. Les réglages ne sont pas modifiés ici.
2. Fusionner #33 vers main en premier : ses correctifs Voice/CRM n'ajoutent pas
   de migration au schéma 0048.
3. Réconcilier ensuite #37 avec ce nouveau main en appliquant les quatre
   résolutions présentes dans cette branche. Ne pas remplacer un fichier
   conflictuel entier par une seule version. Réexécuter la CI et GitGuardian
   sur le SHA réconcilié avant de fusionner #37.
4. Fusionner #37 seulement après ce résultat vert et l'accord du propriétaire.
   Un déploiement Sandbox puis Production exige une autorisation distincte.

Le worktree local fournit le résultat attendu de cette séquence, pas une
autorisation de fusion ni un déploiement de l'assemblage.

## Risques et conditions restantes

- La CI Linux/GitGuardian doit encore contrôler le futur SHA publié de
  réconciliation ; les tests locaux ne la remplacent pas.
- `railway.json` exécute `alembic upgrade head` avant le démarrage de l'API.
  Avec #37, un démarrage autorisé en Production appliquerait 0049/0050. Une
  sauvegarde récente et restaurable, ainsi que les droits SQL nécessaires à
  l'élargissement de la table de version, restent requis avant cette opération.
- Le retour arrière privilégié est applicatif en conservant les ajouts de
  schéma. Un downgrade supprimant les colonnes MFA n'est pas automatique.
- Les scénarios Telnyx/OpenAI/Google sont simulés : la validation d'un appel
  réel et de Google Calendar nécessite des accès Sandbox, un budget et un accord.
- #33 garde la réservation CRM lors d'un échec Google Calendar et expose cet
  échec dans la réponse immédiate. Le signal détaillé de synchronisation est
  porté par l'instance Python et n'est pas persisté ; un rechargement ultérieur
  peut perdre la distinction entre échec et calendrier non configuré.
- La rotation et la révocation des anciens secrets Production restent un
  chantier séparé. Aucun incident n'est déclaré résolu par cet assemblage.
