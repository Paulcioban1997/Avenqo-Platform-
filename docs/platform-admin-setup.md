# Bootstrap sécurisé du Platform Admin Avenqo

Ce document explique comment configurer le compte **Platform Admin**
(propriétaire d'Avenqo) sans jamais committer d'identifiants réels dans Git.

Le Platform Admin est un rôle indépendant des rôles tenant (owner/admin/...).
Il n'appartient à aucune entreprise cliente : il est rattaché à une entreprise
technique interne dédiée ("Avenqo (Platform)"), créée automatiquement par le
script de bootstrap.

## Étapes

1. Configurer `backend/.env` localement (ce fichier est ignoré par Git — voir
   `.gitignore`). Ne jamais modifier `backend/.env.example` avec de vraies
   valeurs.
2. Définir `PLATFORM_ADMIN_EMAIL=<email-du-propriétaire>`.
3. Définir `PLATFORM_ADMIN_PASSWORD=<mot-de-passe-du-propriétaire>` (doit
   respecter la politique de mot de passe standard : minuscule, majuscule,
   chiffre, caractère spécial, 10 caractères minimum).
4. Exécuter :
   ```bash
   python -m scripts.bootstrap_platform_admin
   ```
5. Vérifier le message de succès — le mot de passe et son hash ne sont
   **jamais** affichés, quel que soit le résultat.
6. Démarrer Avenqo normalement (backend + Flutter).
7. Se connecter via l'écran de connexion standard (Login) avec l'email et le
   mot de passe configurés à l'étape 2-3.
8. Confirmer la redirection automatique vers l'**Avenqo Admin Command
   Center** (`/admin`), visuellement distinct du workspace client (fond
   sombre, badge « PLATFORM »).

## Idempotence

Relancer `python -m scripts.bootstrap_platform_admin` est sans danger :

- Si le compte n'existe pas encore → il est créé, `is_platform_admin=true`.
- Si le compte existe déjà → son rôle `platform_admin` est simplement
  confirmé (aucun doublon, aucune donnée écrasée).

Chaque exécution écrit une entrée d'audit (`platform_admin_bootstrapped` ou
`platform_admin_confirmed`) via `AuditLogService`.

## Sécurité

- Les identifiants réels ne doivent **jamais** apparaître dans : code Python,
  code Dart, tests automatisés, README, documentation, configuration
  versionnée, migrations, scripts de seed committés.
- `backend/.env.example` ne contient que des clés vides
  (`PLATFORM_ADMIN_EMAIL=`, `PLATFORM_ADMIN_PASSWORD=`).
- Le Platform Admin ne devient **jamais** automatiquement membre d'une
  entreprise cliente existante — la séparation platform/tenant est stricte.
- Toutes les routes `/api/v1/admin/*` restent protégées côté backend par
  `require_platform_admin`, indépendamment de toute protection frontend.
