# Validation manuelle du propriétaire — Avenqo V1

Checklist à exécuter manuellement par le propriétaire avant toute validation
publique. Ne remplace pas les tests automatisés (backend + Flutter), mais
valide l'expérience réelle bout en bout.

## Compte client normal

- [ ] Ouvrir le site Avenqo.
- [ ] Créer un premier compte de test réel (signup).
- [ ] Vérifier l'email si la vérification est activée.
- [ ] Se connecter (login).
- [ ] Créer une organisation.
- [ ] Confirmer qu'un workspace (tenant) est bien provisionné.
- [ ] Confirmer l'arrivée sur le Client Dashboard (pas l'interface admin).
- [ ] Vérifier que le Business Copilot répond dans le workspace.
- [ ] Vérifier que Avenqo Support (IA support) répond.
- [ ] Vérifier l'écran de facturation (plans affichés : Demo / Professional /
      Enterprise — jamais « Free »/« Starter »).
- [ ] Se déconnecter puis se reconnecter (session persistante).
- [ ] Tester un mot de passe incorrect (message clair, pas d'exception brute).
- [ ] Tester un email déjà utilisé au signup (message clair).

## Compte Platform Admin (propriétaire)

- [ ] Préparer le compte owner Platform Admin (voir
      `docs/platform-admin-setup.md`) via `backend/.env` +
      `python -m scripts.bootstrap_platform_admin`.
- [ ] Promouvoir/confirmer ce compte en `platform_admin` de façon sécurisée
      (jamais d'identifiants en dur dans le code).
- [ ] Se connecter avec ce compte via l'écran de connexion normal.
- [ ] Vérifier la redirection automatique vers l'Avenqo Admin Command Center
      (`/admin`).
- [ ] Confirmer que l'interface admin est visuellement distincte du workspace
      client (fond sombre, badge « PLATFORM »).
- [ ] Parcourir Overview, Companies, Company detail, Audit Logs.
- [ ] Confirmer qu'un compte client normal ne peut pas ouvrir `/admin`
      manuellement (redirection vers `/dashboard`, aucune donnée admin
      chargée).
- [ ] Confirmer que le Platform Admin n'est PAS automatiquement membre de
      chaque tenant existant.

## Vérifications techniques

- [ ] `flutter test` → 0 échec.
- [ ] `flutter analyze` → aucune nouvelle erreur/avertissement.
- [ ] `flutter build web --release` → succès.
- [ ] Suite backend complète (`pytest tests/backend tests/security
      tests/payments`) → 0 échec.
- [ ] `/api/v1/admin/*` refuse un utilisateur normal et un tenant admin (401/403),
      autorise uniquement `is_platform_admin=true`.
