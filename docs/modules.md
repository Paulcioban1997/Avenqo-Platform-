# Modules

The platform will be organized into independent modules so each product line can evolve without tightly coupling the rest of the system.

## Modules Avenqo

- RetailSenseAI, premier module officiel
- CRM AI
- Accounting AI
- Analytics AI
- Marketing AI
- OCR AI
- Document AI
- Knowledge Base AI
- Voice AI
- Workflow AI
- Sales AI
- Customer Support AI
- Marketplace, sans implÃ©mentation pour le moment

## Module ownership model

```text
Platform -> Module -> Principal Agent -> Tasks -> AI Engine
```

Tasks are reusable definitions. Each module selects its own set, while
training pipelines and resulting models remain isolated by company.

Le catalogue exÃ©cutable actuel contient uniquement :

- RetailSenseAI
- Accounting AI
- CRM AI

RetailSenseAI est un module natif de Avenqo. Son agent principal valide les
tÃ¢ches disponibles puis dÃ©lÃ¨gue la rÃ©solution des modÃ¨les et les prÃ©dictions
Ã  l'AI Engine partagÃ©. Il ne contient aucun modÃ¨le prÃ©entraÃ®nÃ©.

The stable module code is `retail`. This code is used by company
subscriptions, jobs, model paths, and API authorization even if the visible
module name changes in the future.

Avant une prÃ©diction, une ingestion ou un entraÃ®nement, l'agent exige un
droit d'accÃ¨s actif pour l'entreprise. Cette protection
commune Ã©vite que chaque module implÃ©mente ses propres rÃ¨gles d'abonnement.

Les secteurs comme garage, restaurant ou clinique seront des profils de
configuration composant plusieurs modules. Ils ne possÃ¨dent aucun code de
module spÃ©cifique.

