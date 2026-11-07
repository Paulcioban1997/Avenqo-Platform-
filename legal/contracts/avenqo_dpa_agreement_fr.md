# ACCORD DE TRAITEMENT DES DONNÉES PERSONNELLES (DPA)
**RÉFÉRENCE CONTRACTUELLE : AVENQO-DPA-2026-V1.1-FR**
**STATUT DU DOCUMENT : SOUMIS À RÉVISION JURIDIQUE (UNDER_REVIEW / LEGAL_REVIEW_REQUIRED)**
*(PROJET DESTINÉ À L'EXAMEN DU FONDATEUR ET D'UN AVOCAT DU BARREAU DU QUÉBEC — NON APPROUVÉ POUR LA SIGNATURE CLIENT)*

---

### ENTRE LES PARTIES SOUSSIGNÉES :

**1. LE SOUS-TRAITANT :**
**PMC SOLUTIONS AI** (entreprise en cours d'incorporation au Québec, Canada, représentée par Mircea Paul Cioban, fondateur), ayant son établissement d'affaires au Québec, Canada, exploitant la plateforme technologique **Avenqo** (ci-après désignée « **PMC Solutions AI** » ou le « **Sous-traitant** »).
*Note d'incorporation : Dès la délivrance officielle du certificat de constitution par le Registraire des entreprises du Québec (REQ), les droits et obligations du Sous-traitant aux présentes seront automatiquement transférés à PMC Solutions AI Inc.*

**ET**

**2. LE RESPONSABLE DU TRAITEMENT :**
L'entreprise cliente **{{COMPANY_NAME}}**, ayant son établissement d'affaires à {{COMPANY_ADDRESS}} (Identifiant Unique Locataire : `{{COMPANY_ID}}`), représentée par {{SIGNATORY_NAME}}, agissant en qualité de {{SIGNATORY_TITLE}} dûment mandaté(e) (ci-après désignée le « **Client** » ou le « **Responsable du traitement** »).

(Le Sous-traitant et le Responsable du traitement étant individuellement désignés une « **Partie** » et conjointement les « **Parties** »).

---

### ARTICLE 1 — OBJET ET PORTÉE DU TRAITEMENT
Le présent Accord de traitement des données (« DPA ») encadre les opérations de traitement de renseignements personnels et de données commerciales effectuées par PMC Solutions AI pour le compte du Client dans le cadre de la fourniture des services infonuagiques Avenqo (Forfait : **{{SUBSCRIPTION_PLAN}}**, Modules actifs : **{{ACTIVE_MODULES}}**).

---

### ARTICLE 2 — CONFORMITÉ LÉGISLATIVE APPLICABLE
Les Parties s'engagent à exécuter leurs obligations respectives en conformité avec :
1. La *Loi sur la protection des renseignements personnels dans le secteur privé* (Québec, RLRQ c. P-39.1, modifiée par la **Loi 25**).
2. La *Loi sur la protection des renseignements personnels et les documents électroniques* (Canada, **LPRPDE / PIPEDA**).
3. Le cas échéant pour les résidents européens, le *Règlement Général sur la Protection des Données* (UE 2016/679, **RGPD**).

---

### ARTICLE 3 — RÔLES ET INSTRUCTIONS DOCUMENTÉES
3.1 **Propriété exclusive des données** : Le Client conserve la titularité exclusive, inaliénable et entière de l'ensemble des données d'entreprise et renseignements personnels confiés à Avenqo.
3.2 **Instructions du Client** : Le Sous-traitant traite les données personnelles exclusivement sur instruction documentée du Client, aux seules fins de l'exécution, de la maintenance et de la sécurisation des services souscrits.
3.3 **Proscription absolue d'entraînement de modèles publics d'IA** : Le Sous-traitant s'interdit formellement d'utiliser les données personnelles ou commerciales du Client pour entraîner, affiner ou enrichir des modèles d'intelligence artificielle publics, mutualisés ou accessibles à des tiers sans le consentement exprès écrit du Client.

---

### ARTICLE 4 — SOUS-TRAITANTS ULTÉRIEURS ET HÉBERGEMENT
4.1 **Liste des sous-traitants autorisés** : Le Client autorise expressément le recours aux sous-traitants techniques suivants, indispensables à l'exploitation d'Avenqo :
- **Vercel Inc.** (Hébergement et déploiement de l'interface utilisateur web et fonctions Edge - États-Unis / International).
- **Railway Corp.** (Hébergement des serveurs d'application backend et bases de données PostgreSQL - États-Unis / Canada).
- **Cloudflare Inc.** (Réseau de diffusion de contenu CDN, DNS, chiffrement Edge et protection anti-DDoS - International / Canada).
- **Stripe Payments Canada / Stripe Inc.** (Passerelle de facturation et traitement sécurisé des paiements - Canada / États-Unis).
- **Resend Inc.** (Infrastructure d'expédition des courriels transactionnels et notifications - États-Unis).
- **Anthropic PBC / OpenAI LLC / Google LLC** (Fournisseurs de modèles d'IA pour les inférences avancées de Central AI - États-Unis, sous engagement contractuel de non-utilisation des données pour l'entraînement).
- **Telnyx LLC** (Téléphonie infonuagique et passerelle de télécommunications SIP pour le module Voice AI - États-Unis / Canada).
- **Retell AI (Retell Inc.)** (Moteur d'orchestration vocale conversationnelle et de traitement de flux audio en temps réel - États-Unis).
4.2 **Transferts transfrontaliers (Loi 25)** : Le Client reconnaît que certains sous-traitants ultérieurs opèrent des infrastructures aux États-Unis ou à l'international. Le Sous-traitant s'assure que ces transferts font l'objet d'accords contractuels imposant des mesures de protection comparables à celles requises au Québec et au Canada.

---

### ARTICLE 5 — SÉCURITÉ DE L'INFORMATION ET SAUVEGARDES
Le Sous-traitant applique des mesures techniques et organisationnelles conformes aux standards reconnus :
- **Chiffrement au repos** : Chiffrement matériel AES-256 appliqué aux bases de données, disques persistants et volumes d'archivage.
- **Chiffrement en transit** : Utilisation obligatoire des protocoles TLS 1.3 pour l'ensemble des flux réseau web et des appels API.
- **Cloisonnement multi-tenant** : Isolation logique et physique rigoureuse des tables et requêtes par identifiant d'entreprise (`company_id`) via Row-Level Security (RLS).
- **Sauvegardes régulières** : Sauvegardes automatisées quotidiennes des bases de données de production conservées dans des environnements chiffrés isolés.

---

### ARTICLE 6 — GESTION ET NOTIFICATION DES INCIDENTS DE CONFIDENTIALITÉ (LOI 25)
6.1 **Délai d'avis (48 heures)** : En cas d'incident de sécurité avéré présentant un risque de préjudice sérieux pour les personnes concernées, le Sous-traitant s'engage à notifier le Client par écrit dans un délai maximal de **quarante-huit (48) heures** suivant sa confirmation.
6.2 **Atténuation immédiate** : Le Sous-traitant prend sans délai toutes les mesures correctives raisonnables pour neutraliser la brèche, limiter l'impact et préserver l'intégrité des systèmes.
6.3 **Coopération légale** : Le Sous-traitant collabore activement avec le Client afin de lui permettre d'accomplir ses obligations légales d'avis auprès de la Commission d'accès à l'information du Québec (CAI), du Commissariat à la protection de la vie privée du Canada (CPVP) ou des personnes touchées.

---

### ARTICLE 7 — CONSERVATION, RESTITUTION ET SUPPRESSION DES DONNÉES
7.1 **Durée de conservation opérationnelle** : Les données personnelles ne sont conservées que pendant la durée de l'abonnement actif du Client.
7.2 **Délai de réversibilité** : À compter de la résiliation de l'abonnement, le Client bénéficie d'une fenêtre de trente (30) jours pour exporter ses données au format structuré standard (CSV/JSON).
7.3 **Suppression définitive et purge des sauvegardes** : À l'expiration du délai de réversibilité, le Sous-traitant procède à la suppression irréversible des données de production opérationnelles dans un délai maximal de soixante (60) jours. Les sauvegardes chiffrées automatisées de sécurité sont soumises à un cycle de rétention tournant avec écrasement automatique et purge définitive dans un délai maximal de trente (30) jours suivant l'effacement de production. Les pièces comptables et factures demeurent conservées selon l'obligation fiscale légale de sept (7) ans au Canada.

---

### ARTICLE 8 — RESPONSABILITÉ ET CONTACT
La responsabilité du Sous-traitant dans le cadre du présent DPA est soumise aux plafonds et stipulations de l'Article 8 du Contrat d'Abonnement SaaS principal (MSA), sous réserve expresse de l'article 1474 du Code civil du Québec.  
Personne désignée responsable de la protection des renseignements personnels : Mircea Paul Cioban (privacy@avenqo.ca).

---

### CONFORMITÉ LINGUISTIQUE (QUÉBEC)
Conformément aux exigences de la *Charte de la langue française* (Loi 96), les Parties attestent que la version française du présent accord a été consultée préalablement à toute version traduite.

---

**POUR LE CLIENT (RESPONSABLE DU TRAITEMENT) :**  
Dénomination : {{COMPANY_NAME}}  
Signataire autorisé : {{SIGNATORY_NAME}}  
Titre / Fonction : {{SIGNATORY_TITLE}}  
Date : {{EFFECTIVE_DATE}}  
Signature : {{SIGNATURE_BLOCK_CLIENT}}

**POUR PMC SOLUTIONS AI (SOUS-TRAITANT) :**  
Dénomination : PMC SOLUTIONS AI (entreprise en cours d'incorporation au Québec, Canada)  
Représentant : Mircea Paul Cioban  
Titre : Fondateur  
Date : {{EFFECTIVE_DATE}}  
Contresignature autorisée :  
`[En attente de contresignature autorisée par PMC Solutions AI]`
