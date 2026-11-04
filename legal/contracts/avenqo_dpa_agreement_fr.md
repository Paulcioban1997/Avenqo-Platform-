# ACCORD DE TRAITEMENT DES DONNÉES PERSONNELLES (DPA)
**RÉFÉRENCE CONTRACTUELLE : AVENQO-DPA-2026-V1**
*(CONFORME À LA LOI 25 DU QUÉBEC ET À LA LPRPDE / PIPEDA DU CANADA)*

---

### ENTRE LES SOUSSIGNÉS :

**1. LE FOURNISSEUR (SOUS-TRAITANT) :**
**PMC SOLUTIONS AI** (entreprise en cours d'incorporation au Québec, Canada), exploitant la plateforme technologique **Avenqo**, représentée par ses fondateurs autorisés (avec mise à jour contractuelle formelle dès immatriculation officielle au Registraire des entreprises du Québec) (ci-après désignée « **PMC Solutions AI** » ou le « **Sous-traitant** »).

**ET**

**2. LE CLIENT (RESPONSABLE DU TRAITEMENT) :**
L'entreprise cliente **{{COMPANY_NAME}}**, identifiée par son identifiant unique de locataire `{{COMPANY_ID}}`, représentée par **{{SIGNATORY_NAME}}**, agissant en qualité de **{{SIGNATORY_TITLE}}** (ci-après désignée le « **Client** » ou le « **Responsable du traitement** »).

---

### 1. OBJET ET CHAMP D'APPLICATION
Le présent Accord de traitement des données (« DPA ») régit le traitement des renseignements personnels et des données d'entreprise effectué par PMC Solutions AI pour le compte du Client dans le cadre de l'utilisation de la plateforme infonuagique Avenqo (Forfait : **{{SUBSCRIPTION_PLAN}}**, Modules actifs : **{{ACTIVE_MODULES}}**).

### 2. CONFORMITÉ AUX LOIS SUR LA PROTECTION DE LA VIE PRIVÉE
Les Parties s'engagent à respecter l'ensemble des lois applicables en matière de protection des renseignements personnels, notamment :
- La *Loi sur la protection des renseignements personnels dans le secteur privé* (Québec, RLRQ c. P-39.1, modifiée par la **Loi 25**).
- La *Loi sur la protection des renseignements personnels et les documents électroniques* (Canada, **LPRPDE / PIPEDA**).
- Le cas échéant, le *Règlement Général sur la Protection des Données* (UE 2016/679, **RGPD**).

### 3. PROPRIÉTÉ EXCLUSIVE ET INSTRUCTIONS DE TRAITEMENT
1. **Propriété exclusive :** Le Client conserve la propriété entière, exclusive et inaliénable de toutes les données personnelles et commerciales téléversées, synchronisées ou traitées via Avenqo.
2. **Instructions documentées :** Le Sous-traitant traite les données personnelles exclusivement sur instruction documentée du Client et aux seules fins de fournir les services souscrits.
3. **Interdiction d'entraînement de modèles publics :** Le Sous-traitant s'interdit formellement d'utiliser les données personnelles du Client pour entraîner ou affiner des modèles d'intelligence artificielle publics ou mutualisés entre entreprises.

### 4. MESURES DE SÉCURITÉ ET CHIFFREMENT
Le Sous-traitant applique des mesures techniques et organisationnelles de premier ordre :
- **Chiffrement au repos :** Chiffrement matériel AES-256 de toutes les bases de données et pièces jointes.
- **Chiffrement en transit :** Protocoles TLS 1.3 obligatoires pour tous les flux API et webhooks.
- **Isolation multi-tenant stricte :** Chaque enregistrement est cloisonné par `company_id` sans possibilité de fuite inter-entreprises.

### 5. NOTIFICATION DES INCIDENTS DE CONFIDENTIALITÉ (LOI 25)
En cas d'incident de sécurité présentant un risque de préjudice sérieux pour les personnes concernées, le Sous-traitant s'engage à :
1. Aviser le Client par écrit avec diligence raisonnable (sous un délai maximal de **48 heures**).
2. Prendre immédiatement toutes les mesures raisonnables pour atténuer les risques et limiter la portée de l'incident.
3. Collaborer pleinement avec le Client pour répondre aux obligations légales de déclaration envers la Commission d'accès à l'information du Québec (CAI) ou le Commissariat à la protection de la vie privée du Canada.

### 6. RESTITUTION ET SUPPRESSION DES DONNÉES
À l'expiration ou à la résiliation de l'abonnement du Client, le Sous-traitant s'engage, au choix du Client, à :
1. Permettre l'exportation complète de ses données dans un format structuré et standard (CSV, JSON, PDF).
2. Supprimer de manière sécurisée et irréversible toutes les copies des données du Client conservées sur ses serveurs de production, sous réserve des obligations légales de conservation fiscale (7 ans au Canada).

---

### DATE DE PRISE D'EFFET ET VERSIONS
- **Date d'entrée en vigueur :** {{EFFECTIVE_DATE}}
- **Version contractuelle :** {{CONTRACT_VERSION}}
- **Statut légal :** DOCUMENT CONTRACTUEL SOUMIS À VALIDATION JURIDIQUE AVANT UTILISATION COMMERCIALE

---

**POUR LE CLIENT (RESPONSABLE DU TRAITEMENT) :**  
Dénomination : {{COMPANY_NAME}}  
Signataire autorisé : {{SIGNATORY_NAME}}  
Titre / Fonction : {{SIGNATORY_TITLE}}  
Date : {{EFFECTIVE_DATE}}  

**POUR PMC SOLUTIONS AI (SOUS-TRAITANT) :**  
Représentant autorisé : Mircea Paul Cioban  
Titre : Fondateur, PMC Solutions AI  
Date : {{EFFECTIVE_DATE}}  
