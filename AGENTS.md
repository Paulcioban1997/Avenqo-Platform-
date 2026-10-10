# Avenqo — règles permanentes pour les agents

Avenqo est une plateforme SaaS B2B **déjà déployée** (PMC Solutions AI).
Ce dépôt n’est pas une copie d’apprentissage ni RetailSenseAI.

- GitHub : `Paulcioban1997/Avenqo-Platform-`
- Production : `https://avenqo.ca` (Next.js / Vercel) et `https://api.avenqo.ca` (FastAPI / Railway)

## Autorisations

Tu peux modifier le code, ajouter des tests, créer des migrations non destructives
et committer sur une branche dédiée lorsque le propriétaire l’a demandé.

Exigent une autorisation explicite séparée :

- rotation réelle des secrets de production
- modification des variables Railway / Vercel de production
- opérations destructives sur les données
- changement d’abonnements Stripe existants
- modifications DNS ou téléphoniques
- fusion vers `main`
- déploiement en production
- force-push ou réécriture d’historique

## Sécurité

- Ne jamais afficher, copier ou committer de secrets.
- Ne jamais mélanger les données entre entreprises ; le `company_id` vient
  uniquement du contexte serveur (JWT / session).
- Ne jamais remplacer une fonctionnalité réelle par une maquette.
- Ne jamais annoncer comme disponible un module qui n’est pas opérationnel.
- Ne jamais supprimer une entreprise, une base ou un abonnement actif.

## Catalogue commercial à préserver

| Offre | Prix | Modules | Crédits / mois | Utilisateurs | Sites | Voice |
|---|---|---|---|---|---|---|
| Base | 29,99 CAD | 2 max | 6 500 | 3 | 1 | 1 agent, 1 appel |
| Professional | 49,99 CAD | 5 max | 20 000 | 10 | 3 | 3 agents, 2 appels |
| Enterprise | Sur devis | Contrat | Contrat | Contrat | Contrat | Contrat |

IA Central est inclus. La limite de modules est un maximum, pas une obligation.

## Qualité

- Implémenter réellement, tester, puis seulement déclarer terminé.
- Préférer étendre les services existants plutôt que d’en inventer un parallèle.
- Les migrations doivent être additives et compatibles SQLite (tests) / PostgreSQL (prod).
