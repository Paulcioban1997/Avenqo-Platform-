# ADR-003 - ExpÃ©rience mÃ©tier et administration PMC sÃ©parÃ©e

## Statut

AcceptÃ© le 5 aoÃ»t 2026.

## Contexte

Avenqo s'adresse aux dirigeants d'entreprise. Les mÃ©canismes d'analyse, d'entraÃ®nement,
de sÃ©lection et de suivi internes ne constituent pas le produit visible. Les rÃ´les
`owner` et `admin` existants sont des rÃ´les propres Ã  une entreprise cliente; ils ne
doivent jamais donner accÃ¨s aux outils internes de PMC Solutions AI.

## DÃ©cision

Le client Avenqo expose uniquement des concepts mÃ©tier: ventes, clients, produits,
recommandations, alertes, rapports, connexions et assistant. Les rÃ©sultats sont formulÃ©s
en constats, impacts et actions proposÃ©es. Les Ã©tats sans information disponible invitent
Ã  connecter un outil mÃ©tier et ne prÃ©sentent ni valeur fictive ni erreur technique.

L'assistant conversationnel utilise un endpoint mÃ©tier tenant-isolÃ©. Une requÃªte HTTP ne
dÃ©clenche jamais directement un entraÃ®nement. Si les informations de l'entreprise ne sont
pas prÃªtes, l'assistant indique honnÃªtement l'Ã©tape mÃ©tier requise.

L'administration PMC sera une application sÃ©parÃ©e du client Flutter, servie sur une origine
distincte et sous le prÃ©fixe `/api/v1/pmc-admin`. Elle nÃ©cessitera une identitÃ© plateforme
distincte de `UserRole`; aucun rÃ´le d'une entreprise cliente ne pourra satisfaire cette
autorisation. Cette surface pourra prÃ©senter diagnostics, modÃ¨les, expÃ©riences et Ã©lÃ©ments
de dÃ©veloppement. Elle ne sera ajoutÃ©e qu'avec audit des accÃ¨s, authentification renforcÃ©e
et journalisation dÃ©diÃ©e.

## Vocabulaire interdit dans le client

Les libellÃ©s et rÃ©ponses destinÃ©s aux dirigeants ne contiennent pas les termes techniques
listÃ©s dans les tests Flutter, notamment les noms de donnÃ©es internes, mÃ©thodes de recherche,
mesures d'Ã©valuation, bibliothÃ¨ques, carnets, moteur interne et fichiers produits par celui-ci.

## ConsÃ©quences

- Les routes Flutter sont organisÃ©es par domaine mÃ©tier, pas par capacitÃ© technique.
- Les APIs publiques retournent des contrats mÃ©tier stables, indÃ©pendants des implÃ©mentations.
- Les endpoints de diagnostic ne sont pas rÃ©utilisÃ©s pour construire le client.
- La prÃ©sence d'une fonctionnalitÃ© dans le backend ne suffit pas Ã  la rendre accessible au client.
- Toute future administration PMC doit introduire une identitÃ© plateforme explicite avant ses routes.
