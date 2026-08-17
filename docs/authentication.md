# Authentification Enterprise Avenqo

## Architecture

- FastAPI expose le contrat sous `/api/v1/auth`.
- `Company` est le tenant et `User` est un employÃ© de ce tenant.
- Le client ne fournit jamais de `company_id` pour une opÃ©ration protÃ©gÃ©e.
- Le JWT d'accÃ¨s expire aprÃ¨s 15 minutes par dÃ©faut.
- Le refresh token expire aprÃ¨s 30 jours par dÃ©faut, est hachÃ© en base et tourne Ã  chaque utilisation.
- Logout, reset de mot de passe et dÃ©sactivation d'un employÃ© rÃ©voquent la session serveur.
- Les mots de passe sont hachÃ©s avec Argon2.
- Les jetons de vÃ©rification et de reset sont Ã  usage unique et stockÃ©s sous forme d'empreinte SHA-256.

## Routes publiques

| MÃ©thode | Route | ResponsabilitÃ© |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | CrÃ©er une entreprise et son propriÃ©taire |
| POST | `/api/v1/auth/email/verify` | VÃ©rifier une adresse email |
| POST | `/api/v1/auth/email/resend` | Renvoyer la vÃ©rification sans rÃ©vÃ©ler le compte |
| POST | `/api/v1/auth/login` | Ã‰mettre un JWT et un refresh token |
| POST | `/api/v1/auth/refresh` | Faire tourner le refresh token et renouveler le JWT |
| POST | `/api/v1/auth/password/forgot` | Demander un reset sans rÃ©vÃ©ler le compte |
| POST | `/api/v1/auth/password/reset` | Modifier le mot de passe et rÃ©voquer les sessions |

## Routes protÃ©gÃ©es

| MÃ©thode | Route | Permission |
| --- | --- | --- |
| GET | `/api/v1/auth/me` | Utilisateur authentifiÃ© |
| POST | `/api/v1/auth/logout` | Utilisateur authentifiÃ© |
| GET | `/api/v1/employees` | `users:manage` |
| POST | `/api/v1/employees` | `users:manage` |
| PATCH | `/api/v1/employees/{employee_id}` | `users:manage` |

Un administrateur ne peut pas attribuer le rÃ´le `admin`, modifier un autre administrateur ou modifier le propriÃ©taire. Seul le propriÃ©taire peut administrer les comptes `admin`. Le rÃ´le `owner` ne peut pas Ãªtre attribuÃ© par cette API.

## Configuration

Copier les variables documentÃ©es dans `backend/.env.example`. En production, `AUTH_JWT_SECRET` doit Ãªtre remplacÃ© et `SMTP_HOST` doit Ãªtre configurÃ©, sinon l'application refuse de dÃ©marrer.

## Validation locale

```powershell
pytest tests/backend/test_auth.py -q
```

Le seed dÃ©mo exige un secret fourni par l'environnement:

```powershell
$env:AVENQO_DEMO_PASSWORD = "<demo-password>"
python -m scripts.seed_demo
Remove-Item Env:AVENQO_DEMO_PASSWORD
```
