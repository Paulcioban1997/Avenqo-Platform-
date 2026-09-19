# AVENQO — Point de Reprise Technique (Handoff)

**Date** : 2026-09-19  
**Branche** : `main`  
**Dernier commit** : `ea2f4fc` — *fix(retail): support plural entities and Shopify variants in retail endpoints and register Shopify connector*  
**Changements non commités** : Aucun (dépôt propre, `git status` clean).

---

## 1. Environnements Réellement Utilisés et Chaîne de Production

### Frontend Vercel (Production)
- **Domaine** : `https://avenqo.ca` (redirection `app.avenqo.ca` et `www.avenqo.ca` vers `avenqo.ca`).
- **Déploiement actif** : `dpl_4gjuFB35669jETE9miYH1BPVqbDi` (Next.js 16.3, 44 langues, responsive, dark/light theme).
- **Routage API** : Vercel proxy (`/api/v1/:path*`) redirige vers `process.env.BACKEND_API_URL` configuré sur le backend Railway de production (`https://api.avenqo.ca`).
- **Preuve vérifiée** : `curl -s https://avenqo.ca/api/v1/health` renvoie HTTP 200 `{"status":"healthy","application":"Avenqo","version":"0.1.0","environment":"production"}`.

### Backend Railway (Production)
- **Projet** : `alert-tenderness` (ID: `062bbe91-68e7-4e79-8de7-cffeb8a5f5cd`).
- **Environnement** : `production` (ID: `b9b03d41-2a67-4aab-a6f6-32939d8b81e0`).
- **Service** : `Avenqo-Platform-` (ID: `24a2afc3-36f8-46d0-b79d-b323755a83f3`).
- **Domaines** : `api.avenqo.ca` (custom domain port 8000) et `avenqo-platform-production.up.railway.app`.
- **Base de données associée** : Service `Postgres` managé dans l'environnement `production`.
- **Révision Alembic appliquée** : `0019_enterprise_quotes` (vérifié par `SELECT version_num FROM alembic_version`).
- **Table `enterprise_quotes`** : Présente et vérifiée en base (`['alembic_version', 'enterprise_quotes']`).
- **Variables configurées** :
  - `EMAIL_PROVIDER=smtp`
  - `SMTP_HOST=smtp.gmail.com`
  - `FRONTEND_URL=https://avenqo.ca`
  - `STRIPE_SECRET_KEY` : Clé live Stripe (`sk_live_...`) avec `STRIPE_PRICE_PROFESSIONAL=price_1U8VnyGuYLaLvT3Yvfw5QFWh`.

### Backend Railway (Sandbox / Test)
- **Projet** : `alert-tenderness`.
- **Environnement** : `sandbox` (ID: `e5adc24d-23b9-4275-84de-91a7801649b8`).
- **Domaine** : `avenqo-platform-sandbox.up.railway.app`.
- **Base associée** : Base `Postgres` sandbox contenant les connexions de test autorisées (`Produits_Ero`).
- **Variables configurées** :
  - `EMAIL_PROVIDER=smtp`, `SMTP_HOST=smtp.gmail.com`, `FRONTEND_URL=https://avenqo.ca`.
  - `STRIPE_SECRET_KEY` : Clé test Stripe (`sk_test_...`), `STRIPE_PRICE_PROFESSIONAL=price_1UBIeTK4vojCzpX2hr7TBD2e` (49.00 USD/mois).

### Boutique WooCommerce Test
- **Projet Railway** : `Avenqo Woo Test`.
- **Domaine** : `https://wordpress-production-7219.up.railway.app`.

---

## 2. Résultats Vérifiés et Preuves Non Sensibles

| Parcours / Fonction | Environnement | Statut | Preuve Technique |
|---|---|:---:|---|
| **Chaîne de Production** | Vercel Prod & Railway Prod | **PASS** | `avenqo.ca/api/v1/health` -> HTTP 200, `environment: production`. Alembic `0019_enterprise_quotes` appliqué en base. Table `enterprise_quotes` existante. |
| **Envoi Courriel Application** | Railway Prod & Sandbox (SMTP) | **PASS** | Transport SMTP Gmail (`smtp.gmail.com:587`). `POST /api/v1/auth/resend-verification` retourne HTTP 200 `{"email_delivery_configured": true}`. Jeton `EMAIL_VERIFICATION` généré en base pointant vers `https://avenqo.ca/verify-email`. |
| **Ouverture Lien Mail** | Boîte personnelle externe | **BLOQUÉ** | Requiert l'ouverture manuelle du message dans la boîte de messagerie personnelle autorisée. |
| **Session Stripe Test** | Stripe API Mode Test | **PASS** | Session Checkout `cs_test_a15AZ...` générée avec succès pour le plan Professional (49 USD/mois), associée à l'entreprise et client Stripe. |
| **Paiement Stripe Test** | Stripe Checkout (Navigateur) | **BLOQUÉ** | L'iframe de paiement sécurisée de Stripe bloque la saisie automatisée synthétique. Saisie de carte test requise par l'utilisateur. |
| **Catalogue Shopify** | Connecteur Avenqo & Base | **PASS** | 17 produits Shopify importés sans doublon, 26 items d'inventaire, 5 commandes, 3 clients. Produits identifiables : `The 3p Fulfilled Snowboard` (SKU: `sku-hosted-1`, Prix: 2629.95 USD, Stock: 15), `The Multi-managed Snowboard` (SKU: `sku-managed-1`, Prix: 629.95 USD, Stock: 100). |
| **Affichage WooCommerce dans Retail** | API Retail & Base | **PASS** | `Avenqo Headphones X` (ID 14), prix 245, stock **45** visible dans `/api/v1/retail/products` et `/api/v1/retail/inventory`, 0 doublon. |
| **Catalogue Retail Unifié** | API Retail (`/retail/products`) | **PASS** | Total 18 produits (17 Shopify + 1 WooCommerce) avec stocks, prix, devises, SKUs et statuts d'inventaire. |

---

## 3. Blocages Précis et Actions Utilisateur Strictement Nécessaires

1. **Courriel de vérification (Action utilisateur requise)** :
   - Un courriel de vérification avec lien vers `https://avenqo.ca/verify-email?token=...` a été expédié avec succès vers l'adresse autorisée (`ciomir@gmail.com`).
   - **Action** : Ouvrir la boîte mail et cliquer sur le lien de confirmation pour valider l'adresse.

2. **Paiement Stripe Test (Action utilisateur requise)** :
   - La session Checkout de test pour le plan Professional ($49/mois) est prête.
   - **Action** : Ouvrir le lien de test Stripe actif, renseigner la carte test Stripe standard (`4242 4242 4242 4242`, date future, CVC `123`) et valider. Dès réception du webhook Stripe, le quatrième module et le plan Professional sont activés.

---

## 4. Prochaines Commandes et Tâches

1. **Vérification post-clic courriel** :
   ```bash
   # Vérifier en base que email_verified_at est bien renseigné
   railway run --service Postgres --environment production python -c "from sqlalchemy import create_engine, text; import os; c = create_engine(os.environ['DATABASE_PUBLIC_URL']).connect(); print(c.execute(text(\"SELECT email, email_verified_at FROM users WHERE email='ciomir@gmail.com'\")).fetchall())"
   ```

2. **Vérification post-paiement Stripe** :
   ```bash
   # Vérifier le statut de l'abonnement et l'activation du 4e module
   railway run --service Postgres --environment sandbox python -c "from sqlalchemy import create_engine, text; import os; c = create_engine(os.environ['DATABASE_PUBLIC_URL']).connect(); print(c.execute(text(\"SELECT plan_code, status, stripe_subscription_id FROM billing_accounts WHERE company_id='9c97cb94-e9f9-46fb-afd4-8a1d21019cff'\")).fetchall())"
   ```

---

## 5. Décisions Produit en Attente
- Validation finale du passage de 3 à 6 modules après activation du webhook Stripe en environnement de production ou sandbox selon le canal commercial retenu.
- Décision sur l'opportunité d'enregistrer des identifiants API Shopify permanents (client ID / secret) dans Railway production si de futurs marchands doivent connecter leur boutique via OAuth en libre-service sans passer par une intégration personnalisée.
