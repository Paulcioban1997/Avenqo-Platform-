# CONTRAT D'ABONNEMENT SAAS AVENQO (MSA)
**RÉFÉRENCE CONTRACTUELLE : AVENQO-SAAS-2026-V1.1-FR**
**STATUT DU DOCUMENT : SOUMIS À RÉVISION JURIDIQUE (UNDER_REVIEW / LEGAL_REVIEW_REQUIRED)**
*(PROJET DESTINÉ À L'EXAMEN DU FONDATEUR ET D'UN AVOCAT DU BARREAU DU QUÉBEC — NON APPROUVÉ POUR LA SIGNATURE CLIENT)*

---

### ENTRE LES PARTIES SOUSSIGNÉES :

**1. LE FOURNISSEUR :**
**PMC SOLUTIONS AI** (entreprise en cours d'incorporation au Québec, Canada, représentée par Mircea Paul Cioban, fondateur), ayant son établissement d'affaires au Québec, Canada, exploitant la plateforme technologique **Avenqo** (ci-après désignée « **PMC Solutions AI** » ou le « **Fournisseur** »).
*Note d'incorporation : Dès la délivrance officielle du certificat de constitution par le Registraire des entreprises du Québec (REQ), les droits et obligations de PMC Solutions AI aux présentes seront automatiquement et de plein droit transférés à la personne morale PMC Solutions AI Inc., sans interruption de couverture contractuelle.*

**ET**

**2. LE CLIENT :**
L'entreprise cliente **{{COMPANY_NAME}}**, ayant son établissement d'affaires à {{COMPANY_ADDRESS}} (Identifiant Unique Locataire : `{{COMPANY_ID}}`), représentée par {{SIGNATORY_NAME}}, agissant en qualité de {{SIGNATORY_TITLE}} dûment mandaté(e) pour engager légalement son organisation (ci-après désignée le « **Client** »).

(Le Fournisseur et le Client étant individuellement désignés une « **Partie** » et conjointement les « **Parties** »).

---

### PRÉAMBULE
Le Fournisseur a conçu, développé et exploite la plateforme infonuagique intégrée dénommée **Avenqo** (la « **Plateforme** »), proposant des solutions modulaires d'aide à la décision, d'intégration de données retail, de gestion relation client (CRM) et d'automatisation d'affaires (Central AI).
Le Client désire souscrire un accès en mode logiciel-service (SaaS) à la Plateforme pour ses besoins d'affaires propres, selon les termes, conditions et limites stipulés aux présentes.

---

### ARTICLE 1 — DÉFINITIONS
- **Plateforme SaaS** : L'environnement logiciel multi-tenant Avenqo accessible à distance via des connexions réseau sécurisées.
- **Données Client** : L'ensemble des données, fichiers, transactions, catalogues, fiches clients et métadonnées téléversés ou synchronisés par le Client sur son espace dédié.
- **Modules d'Affaires** : Les composantes logicielles spécialisées souscrites et activées par le Client parmi le catalogue canonique, dans la limite stricte des droits de son forfait : **{{ACTIVE_MODULES}}**.
- **Crédits IA** : Unités numériques de calcul algorithmique allouées mensuellement selon le forfait souscrit ou achetées sous forme de packs rechargeables, consommées lors des inférences et traitements automatisés.

---

### ARTICLE 2 — OBJET, FORFAITS ET PORTÉE DU SERVICE
2.1 **Octroi d'accès** : Le Fournisseur concède au Client, qui l'accepte, un droit d'accès et d'utilisation non exclusif, non transférable, sans droit de sous-licence, mondial (sous réserve des lois sur le contrôle des exportations) à la Plateforme et aux modules sélectionnés.
2.2 **Spécifications des forfaits commerciaux** :
- **Forfait Base** : Comprend l'accès socle, **deux (2) modules d'affaires au choix**, et un quota mensuel de **6 500 crédits IA**.
- **Forfait Professional** : Comprend l'accès socle, **cinq (5) modules d'affaires au choix** parmi le catalogue disponible, et un quota mensuel de **20 000 crédits IA**. Le forfait Professional ne confère en aucun cas un accès illimité à l'intégralité des modules existants ou futurs.
- **Forfait Enterprise** : Configuration sur devis personnalisé incluant un nombre convenu de modules et des quotas adaptés, régie par un avenant d'entreprise distinct.
2.3 **Architecture multi-tenant et isolation** : Les services sont exploités sur une infrastructure mutualisée avec étanchéité stricte des données garantie au niveau base de données via PostgreSQL Row-Level Security (RLS).
2.4 **Non-cession de propriété intellectuelle** : Le présent contrat confère exclusivement un droit d'accès SaaS opérationnel et ne constitue en aucun cas une cession de code source, d'algorithmes ou de brevets.

---

### ARTICLE 3 — PRIX, FACTURATION ET CONDITIONS FISCALES
3.1 **Redevance d'abonnement** : Le Client souscrit à l'offre avec une redevance périodique convenue de : **{{SUBSCRIPTION_PRICE}}**.
3.2 **Conditions fiscales et taxes applicables** : Les prix s'entendent hors taxes. Les taxes de vente applicables (notamment la TPS et la TVQ au Canada, ou toute autre taxe locale exigible selon la juridiction du Client) seront facturées et perçues conformément aux exigences législatives en vigueur et à l'état officiel des inscriptions fiscales de PMC Solutions AI au moment de l'émission de la facture.
3.3 **Renouvellement automatique** : {{RENEWAL_TERMS}}.
3.4 **Règles des Crédits IA et interruption sécurisée** : Les crédits mensuels inclus sont renouvelés à chaque cycle mensuel sans report cumulatif des crédits non utilisés. Les packs de crédits additionnels demeurent valides tant que l'abonnement reste actif. En cas d'épuisement des crédits disponibles, les appels aux fonctions d'intelligence artificielle sont automatiquement suspendus (*fail-closed*) jusqu'à la recharge ou au prochain cycle, afin de prévenir tout surcoût imprévu.

---

### ARTICLE 4 — DISPONIBILITÉ DU SERVICE (SLA) ET SOUTIEN
4.1 **Objectif de disponibilité soutenable** : Le Fournisseur s'engage à déployer des efforts commercialement raisonnables pour assurer un taux de disponibilité mensuel cible de **99,0 %** de la Plateforme en production. Pour les clients souscrivant une offre Enterprise, les engagements de niveau de service (SLA) personnalisés et les modalités de support étendu sont régis par un avenant d'entreprise (Enterprise Addendum) distinct.
4.2 **Méthode de calcul et exclusions du SLA** : La disponibilité est calculée mensuellement selon la formule : `[(Minutes totales du mois - Minutes d'indisponibilité non exclues) / Minutes totales du mois] x 100`. Sont formellement exclues du calcul de l'indisponibilité :
- Les fenêtres de maintenance planifiée préalablement notifiées avec au moins 48 heures de préavis.
- Les pannes ou dégradations attribuables aux fournisseurs d'infrastructure d'hébergement ou de réseau tiers (ex. Cloudflare, Railway, AWS).
- Les défaillances des API externes partenaires intégrées (ex. Stripe, passerelles bancaires, Google Workspace, Telnyx, fournisseurs de LLM tiers).
- Les actes, omissions ou configurations erronées du Client, ou les cas de force majeure.
4.3 **Remède unique et exclusif (Crédits de service)** : Si le taux de disponibilité effectif mensuel est inférieur à 99,0 %, le Client pourra prétendre, sur demande écrite formulée dans les quinze (15) jours suivant la fin du mois concerné, à l'octroi d'un crédit de service appliqué sur sa prochaine facture :
- Disponibilité constatée entre 95,0 % et 98,9 % : Crédit de 10 % du montant mensuel de l'abonnement de base.
- Disponibilité constatée inférieure à 95,0 % : Crédit de 20 % du montant mensuel de l'abonnement de base.
Ce crédit de service constitue le recours unique, exclusif et exhaustif du Client pour tout défaut de disponibilité. Aucun remboursement en espèces ou indemnité distincte ne sera exigible.

---

### ARTICLE 5 — NATURE DES OUTILS D'IA ET ABSENCE DE GARANTIE DE RÉSULTAT
5.1 **Assistance à la décision** : Les synthèses, prédictions, recommandations et analyses produites par les modules d'IA d'Avenqo constituent des outils indicatifs d'aide à la décision d'affaires. PMC Solutions AI ne garantit pas que les inférences générées soient exhaustives, exemptes d'anomalies contextuelles ou parfaitement adaptées aux particularités opérationnelles imprévues du Client.
5.2 **Responsabilité décisionnelle du Client** : Le Client conserve l'entière responsabilité de vérifier, valider et superviser l'application concrète des résultats et recommandations fournis par la Plateforme au sein de ses activités commerciales.

---

### ARTICLE 6 — OBLIGATIONS DU CLIENT
6.1 **Usage légitime et conforme** : Le Client s'engage à exploiter la Plateforme en stricte conformité avec les lois applicables au Québec et au Canada, notamment en matière de protection des renseignements personnels (Loi 25 du Québec, LPRPDE/PIPEDA).
6.2 **Gestion des accès** : Le Client est seul garant de la confidentialité et de la sécurité des identifiants et des clés d'accès attribués à ses administrateurs et collaborateurs.
6.3 **Légalité des données téléversées** : Le Client garantit détenir tous les droits, consentements et autorisations légalement requis pour téléverser, intégrer et traiter ses données sur Avenqo.

---

### ARTICLE 7 — RÉSILIATION ET RÉVERSIBILITÉ
7.1 **Résiliation pour convenance** : Le Client peut résilier son abonnement à tout moment par l'intermédiaire de son portail de facturation libre-service. La résiliation prend effet au terme de la période de facturation mensuelle en cours, sans remboursement rétroactif pro rata temporis.
7.2 **Résiliation pour manquement** : Chacune des Parties peut résilier le contrat immédiatement en cas de manquement substantiel de l'autre Partie, non remédié dans un délai de trente (30) jours suivant notification écrite formelle.
7.3 **Réversibilité et restitution des données** : Pendant une période de trente (30) jours suivant la date d'effet de la résiliation, le Client a la faculté d'exporter l'intégralité de ses données dans un format standard lisible par machine (JSON/CSV). À l'issue de cette période de 30 jours, le Fournisseur procède à la suppression sécurisée et définitive des données de production du Client, sous réserve des archives de conservation fiscale obligatoires de sept (7) ans.

---

### ARTICLE 8 — LIMITATION DE RESPONSABILITÉ ET CODE CIVIL DU QUÉBEC
8.1 **Plafond financier de responsabilité** : Sous réserve expresse du paragraphe 8.3 ci-dessous, la responsabilité cumulative globale de PMC Solutions AI, toutes réclamations confondues découlant du présent contrat ou s'y rapportant, est strictement limitée au montant des redevances d'abonnement effectivement payées par le Client à PMC Solutions AI au cours des trois (3) mois précédant immédiatement le fait générateur du dommage (ou 500 $ CAD si ce montant est supérieur).
8.2 **Exclusion des dommages indirects** : Dans la pleine mesure autorisée par la loi applicable, aucune des Parties ne pourra être tenue responsable des dommages indirects, accessoires, exemplaires, spéciaux ou punitifs, ni des pertes de profits, manques à gagner, interruptions d'affaires ou pertes de données.
8.3 **Disposition impérative de l'article 1474 du Code civil du Québec** : Aucune disposition du présent contrat ne saurait limiter ou exclure la responsabilité d'une Partie en cas de faute lourde, de faute intentionnelle, ou de préjudice corporel ou moral, conformément aux règles d'ordre public de l'article 1474 du Code civil du Québec.

---

### ARTICLE 9 — CONFORMITÉ LINGUISTIQUE (QUÉBEC)
Conformément aux exigences de la *Charte de la langue française* (RLRQ c. C-11, modifiée par la Loi 96), les Parties confirment expressément que la version française du présent contrat a été fournie et mise à la disposition du Client préalablement à la consultation ou à la signature de toute version traduite.

---

### ARTICLE 10 — LOI APPLICABLE ET TRIBUNAUX COMPÉTENTS
Le présent contrat est régi et interprété conformément aux lois en vigueur dans la province de Québec et aux lois fédérales du Canada qui s'y appliquent. Tout litige relatif à sa validité, son interprétation ou son exécution relève de la compétence exclusive des tribunaux du district judiciaire de Montréal, province de Québec, Canada.

---

### MODALITÉS D'EXÉCUTION ET DE SIGNATURE

#### OPTION A — SIGNATURE ÉLECTRONIQUE SÉCURISÉE (LCCJTI c. C-1.1)
Scellée numériquement par empreinte SHA-256, horodatage UTC et journal d'audit infalsifiable.

#### OPTION B — SIGNATURE MANUSCRITE AU STYLO
Imprimable, signable physiquement et téléversable sous `/settings/contracts` pour contrôle d'intégrité et validation administrative (`PENDING_VERIFICATION`).

---

**POUR LE CLIENT :**  
Dénomination sociale : {{COMPANY_NAME}}  
Nom du signataire autorisé : {{SIGNATORY_NAME}}  
Titre / Fonction : {{SIGNATORY_TITLE}}  
Date d'effet : {{EFFECTIVE_DATE}}  
Signature du Client : {{SIGNATURE_BLOCK_CLIENT}}

**POUR PMC SOLUTIONS AI :**  
Dénomination : PMC SOLUTIONS AI (entreprise en cours d'incorporation au Québec, Canada)  
Nom du représentant : Mircea Paul Cioban  
Titre : Fondateur  
Date : {{EFFECTIVE_DATE}}  
Contresignature autorisée :  
`[En attente de contresignature autorisée par PMC Solutions AI]`
