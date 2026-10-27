# CONTRAT DE LICENCE PRIVÉE DU MOTEUR AVENQO CENTRAL
**RÉFÉRENCE CONTRACTUELLE : AVENQO-LIC-PRIVEE-2026-V1**
*(BROUILLON SOUMIS À VALIDATION JURIDIQUE PAR UN AVOCAT QUÉBÉCOIS — USAGE PRÉ-COMMERCIAL)*

---

### ENTRE LES PARTIES :

**1. LE CONCÉDANT :**
**PMC SOLUTIONS AI INC.**, société par actions dûment constituée en vertu des lois du Québec, ayant son siège social au Québec, Canada, représentée par ses dirigeants autorisés (ci-après désignée « **PMC Solutions AI** » ou le « **Concédant** »).

**ET**

**2. LE LICENCIÉ :**
L'entreprise cliente, identifiée lors de l'enregistrement de l'entente par son entité légale, son représentant dûment mandaté et son identifiant de tenant Avenqo (ci-après désignée le « **Licencié** »).

---

### PRÉAMBULE
Le Concédant est le concepteur, développeur et propriétaire exclusif de la technologie logicielle propriétaire dénommée **Avenqo Central Engine** (le « **Moteur Central AI** »), intégrant des mécanismes d'orchestration multi-agents, de raisonnement commercial contextualisé et d'isolation de données d'affaires.
Le Licencié souhaite bénéficier d'une licence privée d'exploitation du Moteur Central AI pour l'intégrer au sein de ses processus d'affaires internes ou d'un environnement applicatif réservé.

---

### ARTICLE 1 — CARACTÈRE STRICTEMENT NON EXCLUSIF DE LA LICENCE
1.1 **Principe de Non-Exclusivité** : La présente licence est octroyée à titre **STRICTEMENT NON EXCLUSIF**. Le Concédant conserve l'entière liberté de concéder des licences identiques, similaires ou équivalentes à toute tierce partie, concurrente ou non du Licencié, sans restriction de territoire ou d'industrie.
1.2 **Portée restreinte** : Aucune exclusivité sectorielle, géographique ou temporelle n'est accordée, sauf convention expresse distincte conclue sous forme d'un avenant d'exclusivité dûment paraphé et assujetti à des redevances spécifiques substantielles.

---

### ARTICLE 2 — DROITS CONCÉDÉS ET RESTRICTIONS D'USAGE
2.1 **Droits accordés** : Le Concédant concède au Licencié, sous réserve du paiement intégral des redevances applicables, un droit personnel, non transférable, sans droit de sous-licence, d'interrogation, d'intégration par interface de programmation (API) et d'exploitation du Moteur Central AI pour les besoins opérationnels internes de son organisation.
2.2 **Restrictions impératives** : Il est formellement interdit au Licencié de :
- Rétro-ingénier, décompiler ou désassembler tout ou partie des modèles ou binaires du Moteur Central AI ;
- Tenter d'extraire les poids neuronaux, matrices d'embeddings ou algorithmes de prompt engineering propriétaires ;
- Revendre, sous-louer, redistribuer ou offrir le Moteur en marque blanche à des tiers sans accord commercial préalable ;
- Utiliser le Moteur pour développer ou entraîner un modèle concurrent direct de PMC Solutions AI Inc.

---

### ARTICLE 3 — ISOLATION ET TRAITEMENT DES DONNÉES D'AFFAIRES
3.1 **Cloisonnement du Contexte Privé** : Chaque instance ou exécution du Moteur Central AI est contrainte par un contexte de tenant étanche (`TenantContext`), empêchant toute contamination croisée d'informations entre clients.
3.2 **Confidentialité des inférences** : Les requêtes soumises au Moteur et les synthèses générées demeurent la propriété confidentielle du Licencié. Le Concédant ne conserve aucune mémoire partagée des données du Licencié au-delà de la session transactionnelle d'audit.

---

### ARTICLE 4 — MODALITÉS FINANCIÈRES ET REDEVANCES
4.1 **Redevance de Licence** : Le Licencié s'acquitte d'une redevance forfaitaire mensuelle ou annuelle selon l'annexe commerciale convenue, complétée des frais d'exécution inférentielle basés sur la consommation de crédits IA.
4.2 **Devise et Paiement** : Les montants sont libellés et payables en Dollars Canadiens (CAD). Les paiements sont exigibles dès réception de facture ou par débit préautorisé via les adaptateurs de paiement sécurisés.

---

### ARTICLE 5 — AUDIT ET RESPECT DES QUOTAS
5.1 **Journal d'Audit Immuable** : Le Concédant maintient un registre horodaté des appels API et de la volumétrie d'inférence. En cas de dépassement des limites convenues, le Concédant applique un mécanisme d'étranglement ou de suspension fail-closed afin de protéger l'intégrité de l'infrastructure.

---

### ARTICLE 6 — GARANTIES ET DÉGAGEMENT DE RESPONSABILITÉ
6.1 Le Moteur Central AI est fourni « en l'état » pour l'assistance à la prise de décision. Le Concédant garantit que le Moteur opère conformément aux spécifications techniques documentées, mais ne garantit pas que les inférences générées soient exemptes d'erreurs d'interprétation contextuelle humaine.
6.2 Le Licencié demeure ultimement responsable de la validation de ses décisions d'affaires et de la vérification de l'exactitude des recommandations émises par l'intelligence artificielle.

---

### ARTICLE 7 — DURÉE, RÉSILIATION ET CONSÉQUENCES
7.1 La présente licence prend effet à la date de signature électronique pour une durée déterminée d'un (1) an, renouvelable d'accord mutuel.
7.2 En cas de violation par le Licencié des restrictions prévues à l'Article 2, la licence est révoquée de plein droit, sans mise en demeure préalable ni remboursement des redevances échues.

---

### ARTICLE 8 — DROIT APPLICABLE
La présente entente est régie exclusivement par les lois de la province de Québec et les lois du Canada applicables. Les tribunaux de la province de Québec, district de Montréal, ont compétence exclusive pour entendre tout différend.
