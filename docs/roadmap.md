# Roadmap officielle Avenqo

Les phases sont sÃ©quentielles. Une phase doit Ãªtre architecturÃ©e, codÃ©e, testÃ©e, documentÃ©e et validÃ©e avant le dÃ©but de la suivante.

| Phase | Domaine | Ã‰tat |
| --- | --- | --- |
| 2 | Authentification Enterprise FastAPI | ValidÃ©e |
| 3 | Stripe | ImplÃ©mentÃ©e: 49 tests passent; validation Stripe Test Mode requise |
| 4 | Client Flutter/Dart multiplateforme | En dÃ©veloppement |
| 5 | ParitÃ© fonctionnelle mobile, web et desktop | IntÃ©grÃ©e Ã  la Phase 4 |
| 6 | Gestion avancÃ©e des entreprises | Ã€ venir |
| 7 | Marketplace IA | Ã€ venir |
| 8 | Importation des donnÃ©es | Ã€ venir |
| 9 | ExÃ©cution du AI Engine | Ã€ venir, uniquement aprÃ¨s import de donnÃ©es |
| 10 | Notebooks R&D | Suspendue jusqu'Ã  la Phase 10 |
| 11 | DÃ©ploiement | Ã€ venir |
| 12 | Production | Ã€ venir |

## Client multiplateforme

Avenqo utilise une seule application Flutter/Dart dans `frontend/` pour le Web,
Android, iOS, Windows, macOS et Linux. Toutes les plateformes partagent la mÃªme
API, les mÃªmes routes, les mÃªmes rÃ´les, les mÃªmes permissions, les mÃªmes modules
et les mÃªmes workflows. Il n'existe ni client React ni version mobile simplifiÃ©e.

## AI Engine

Le AI Engine existant reste dormant. Il ne dÃ©marre qu'aprÃ¨s l'import de donnÃ©es propres Ã  une entreprise en Phase 8. Les notebooks ne contiennent jamais le code de production.


