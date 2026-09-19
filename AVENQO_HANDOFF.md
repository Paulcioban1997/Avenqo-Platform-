# AVENQO — Point de Reprise Technique (Handoff)

**Date** : 2026-09-19  
**Branche** : `main`  
**Dernier commit déployé** : `020dd84` — *docs: add AVENQO_HANDOFF.md point de reprise* (inclut `ea2f4fc` *fix(retail): support plural entities and Shopify variants in retail endpoints and register Shopify connector*)  
**Changements non commités** : Aucun (`git status` propre).

---

## 1. État Final des Déploiements

| Plateforme / Service | Environnement | Statut Déploiement | Commit / Identifiant Déployé | Santé API |
|---|---|:---:|---|:---:|
| **Railway** (`alert-tenderness` / `Avenqo-Platform-`) | **production** | **SUCCESS** | `020dd84` (ID: `c5c9da98-6aa4-49d7-b5b5-42d18f9682b5`) | HTTP 200 `healthy` |
| **Railway** (`alert-tenderness` / `Avenqo-Platform-`) | **sandbox** | **SUCCESS** | Working tree `020dd84` (ID: `aa345d6a-5ddb-4d00-bcd0-c3af5414848c`) | HTTP 200 `healthy` |
| **Vercel** (`paulmircea15-9488s-projects` / `web`) | **production** | **READY** | `dpl_4gjuFB35669jETE9miYH1BPVqbDi` (`https://avenqo.ca`) | HTTP 200 `healthy` |
| **Railway** (`Avenqo Woo Test` / `wordpress`) | **production** | **SUCCESS** | `https://wordpress-production-7219.up.railway.app` | HTTP 200 `wc/v3` |

---

## 2. Données et Affichage Retail Vérifiés

Sur l'environnement connecté de test (`Produits_Ero` / `avenqo-platform-sandbox.up.railway.app`) :

- **Catalogue unifié** : **18 produits** au total exposés dans `/api/v1/retail/products` et `/api/v1/retail/inventory`.
- **Produits Shopify** : **17 produits** importés avec leurs variantes, devises (USD) et stocks réels, notamment :
  - `The 3p Fulfilled Snowboard` (SKU : `sku-hosted-1`, Prix : 2629.95 USD, Stock : **15**, Provider : `shopify`).
  - `The Multi-managed Snowboard` (SKU : `sku-managed-1`, Prix : 629.95 USD, Stock : **100**, Provider : `shopify`).
  - `The Inventory Not Tracked Snowboard` (SKU : `sku-untracked-1`, Prix : 949.95 USD, Stock : **0**, Provider : `shopify`).
  - `The Complete Snowboard` (Prix : 699.95 USD, Stock : **49**, Provider : `shopify`).
- **Produit WooCommerce** :
  - `Avenqo Headphones X` (ID : 14, Prix : 245.0, Stock : **45**, Provider : `woocommerce`).
- **Persistance après actualisation** : Vérifiée sur 3 requêtes consécutives espacées de 2 secondes. Les 18 items, le stock 45 de `Avenqo Headphones X` et les stocks Shopify demeurent strictement identiques sans perte ni duplication (0 doublon).

---

## 3. Précision sur les Comptes Courriel Utilisés

Pour éliminer toute ambiguïté sur les adresses relevées :
1. `paulmircea15@gmail.com` : Utilisé exclusivement lors du test initial de transport SMTP direct vers Gmail pour valider la connectivité TLS/port 587.
2. `gauffy95@gmail.com` : Compte propriétaire officiel de l'entreprise `Produits_Ero` en base de données. Ce compte possède déjà son champ `email_verified_at` renseigné (déjà vérifié), ce qui empêche le déclenchement d'un nouveau jeton de vérification par l'API sans le réinitialiser.
3. `ciomir@gmail.com` : Compte utilisateur existant en base dont l'email n'était pas encore vérifié (`email_verified_at: null`), utilisé pour valider l'appel réel `POST /api/v1/auth/resend-verification`. Le jeton `EMAIL_VERIFICATION` a été créé en base avec une URL pointant vers `https://avenqo.ca/verify-email`. Aucun courriel n'a été ou ne sera envoyé vers d'autres adresses.

---

## 4. Parcours Non Validés (En attente d'action utilisateur)

Ces deux parcours demeurent **NON VALIDÉS** et requièrent une intervention manuelle externe :

1. **Ouverture du lien reçu par courriel et connexion réussie (NON VALIDÉ)** :
   - L'envoi via SMTP applicatif a réussi et le lien a été généré vers `https://avenqo.ca/verify-email?token=...`.
   - **Blocage restant** : L'accès à la boîte de réception personnelle externe de l'utilisateur (`ciomir@gmail.com`) et le clic sur le lien pour finaliser la vérification ne peuvent pas être exécutés par l'agent.

2. **Paiement Stripe test, réception du webhook et possibilité d'activer le quatrième module (NON VALIDÉ)** :
   - La session Checkout de test pour le plan Professional (49 USD/mois) a été créée côté serveur et rattachée au client Stripe.
   - **Blocage restant** : La saisie des coordonnées de carte de test (`4242...`) dans l'iframe sécurisée Stripe Checkout est bloquée en mode automatisé headless et doit être complétée par l'utilisateur. Tant que le paiement n'est pas finalisé, le webhook `customer.subscription.created` n'est pas émis par Stripe et le 4e module ne bascule pas en mode actif.

---

## 5. Prochaines Actions à la Reprise
- Une fois le lien de courriel cliqué par l'utilisateur, vérifier la validation du compte :
  ```bash
  railway run --service Postgres --environment production python -c "from sqlalchemy import create_engine, text; import os; c = create_engine(os.environ['DATABASE_PUBLIC_URL']).connect(); print(c.execute(text(\"SELECT email, email_verified_at FROM users WHERE email='ciomir@gmail.com'\")).fetchall())"
  ```
- Une fois le paiement test Stripe finalisé par l'utilisateur sur la page Stripe, vérifier le plan et les modules :
  ```bash
  railway run --service Postgres --environment sandbox python -c "from sqlalchemy import create_engine, text; import os; c = create_engine(os.environ['DATABASE_PUBLIC_URL']).connect(); print(c.execute(text(\"SELECT plan_code, status, stripe_subscription_id FROM billing_accounts WHERE company_id='9c97cb94-e9f9-46fb-afd4-8a1d21019cff'\")).fetchall())"
  ```
