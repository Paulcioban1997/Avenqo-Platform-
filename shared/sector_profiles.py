"""Universal Sector Profiles and Multi-Industry Architecture for Avenqo (Phase 1).

Configurable industry profiles with localized descriptions, recommended business modules,
concrete use cases, synthetic demo scenarios, and regulatory constraints.
Strict adherence: Sector profiles never bypass RBAC or subscription plan limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DemoStep:
    step_number: int
    title_fr: str
    title_en: str
    description_fr: str
    description_en: str
    active_module: str  # One of: "retail", "crm", "voice", "accounting", "marketing", "ocr", "central_ai"
    input_data: str
    simulated_output: str
    visual_metric: str


@dataclass(frozen=True, slots=True)
class SectorProfile:
    id: str
    name_fr: str
    name_en: str
    description_fr: str
    description_en: str
    icon_name: str
    recommended_modules: tuple[str, ...]  # Strictly among the 6 official business modules
    use_cases_fr: tuple[str, ...]
    use_cases_en: tuple[str, ...]
    workflow_templates: tuple[str, ...]
    integration_prerequisites: tuple[str, ...]
    regulatory_constraints_fr: str
    regulatory_constraints_en: str
    feature_availability: str  # "available" | "beta"
    demo_steps: tuple[DemoStep, ...] = field(default_factory=tuple)


SECTOR_PROFILES: tuple[SectorProfile, ...] = (
    SectorProfile(
        id="retail_ecommerce",
        name_fr="Commerce & E-commerce",
        name_en="Retail & E-commerce",
        description_fr="Boutiques physiques, vente en ligne multi-canaux (Shopify, WooCommerce, Etsy) et distribution de détail.",
        description_en="Brick-and-mortar stores, omnichannel e-commerce (Shopify, WooCommerce, Etsy), and retail distribution.",
        icon_name="ShoppingBag",
        recommended_modules=("retail", "marketing", "crm", "accounting"),
        use_cases_fr=(
            "Analyse des ventes en temps réel et anticipation des ruptures de stock",
            "Segmentation client dynamique pour campagnes de réactivation à fort panier",
            "Réconciliation automatisée des flux de paiements (Stripe, TPV)",
        ),
        use_cases_en=(
            "Real-time sales velocity and automated stockout forecasting",
            "Dynamic customer segmentation for high-AOV repeat campaigns",
            "Automated payment gateway reconciliation (Stripe, POS)",
        ),
        workflow_templates=("retail_stockout_alert", "ecommerce_cart_recovery", "omnichannel_daily_report"),
        integration_prerequisites=("Shopify / WooCommerce API", "Passerelle de paiement"),
        regulatory_constraints_fr="Conformité taxes provinciales (TPS/TVQ), consentement RGPD/Loi 25 pour le marketing par courriel/SMS.",
        regulatory_constraints_en="Provincial tax compliance (GST/QST), GDPR/Law 25 consent for marketing emails/SMS.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Importation des ventes", "Sales Data Ingestion", "Données transactionnelles fictives synchronisées", "Simulated POS & online store transaction ingest", "retail", "2 840 commandes (derniers 30 jours)", "Ventes nettes : 184 250 $ · Marge moyenne : 41.2%", "+14.8% vs N-1"),
            DemoStep(2, "Détection d'anomalies & tendances", "Trend & Anomaly Detection", "IA Central identifie 42 clients dormants à forte valeur", "IA Central detects 42 high-LTV dormant accounts", "central_ai", "Recherche segment : LTV > 1 200 $, inactifs depuis 60j", "Segment identifié : 42 clients (panier moyen 185 $)", "Potentiel : 7 770 $"),
            DemoStep(3, "Génération de campagne ciblée", "Targeted Campaign Generation", "Marketing IA prépare une offre personnalisée de réactivation", "Marketing AI drafts personalized win-back offer", "marketing", "Paramètres : courriel courtois, offre privilège -15%", "Brouillon prêt pour revue humaine autorisée", "Approbation requise"),
            DemoStep(4, "Validation & Résultat projeté", "Human Approval & Projection", "L'administrateur approuve l'action en un clic", "Manager approves execution with one click", "central_ai", "Validation humaine effectuée", "Campagne prête à diffuser via canal autorisé", "+22% réactivation estimée"),
        ),
    ),
    SectorProfile(
        id="garage_auto",
        name_fr="Garages & Concessions Automobiles",
        name_en="Automotive Repair & Dealerships",
        description_fr="Ateliers mécaniques, carrosseries, centres de pneus et concessionnaires automobiles.",
        description_en="Auto repair shops, body shops, tire centers, and vehicle dealerships.",
        icon_name="Wrench",
        recommended_modules=("voice", "crm", "ocr", "accounting"),
        use_cases_fr=(
            "Accueil téléphonique 24/7 et qualification de pannes ou changements de pneus",
            "Prise de rendez-vous automatique synchronisée avec les ponts élévateurs",
            "Extraction OCR immédiate des factures de pièces de rechange et bons de livraison",
        ),
        use_cases_en=(
            "24/7 voice reception qualifying breakdowns and tire season bookings",
            "Automated appointment scheduling synchronized with service bay calendars",
            "Instant OCR parsing of parts supplier invoices and delivery slips",
        ),
        workflow_templates=("auto_seasonal_tire_booking", "parts_invoice_ocr_entry", "mechanic_service_reminder"),
        integration_prerequisites=("Telnyx SIP / Numéro de téléphone", "Google Calendar (bays)"),
        regulatory_constraints_fr="Transparence des devis automobiles et enregistrement vocal avec avis préalable.",
        regulatory_constraints_en="Automotive repair estimate transparency and call recording disclosure.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel entrant du client", "Incoming Customer Call", "Un client appelle pour un changement de pneus et freins", "Customer calls requesting seasonal tire change and brakes", "voice", "Appel vocal audio capté par Telnyx", "Qualification : Toyota RAV4 2022, freins avant + 4 pneus", "Appel qualifié"),
            DemoStep(2, "Vérification des disponibilités", "Bay Availability Check", "Voice IA interroge CRM IA pour les créneaux atelier", "Voice AI queries CRM AI for open mechanical bay slots", "crm", "Recherche disponibilité : Jeudi prochain à 14h00", "Créneau disponible : Pont 2 libre à 14h00 (durée 90 min)", "Zéro surbooking"),
            DemoStep(3, "Confirmation orale sécurisée", "Verbal Confirmation & Guardrail", "L'agent vocal confirme la date et le tarif estimatif avec l'appelant", "Voice agent verbally verifies date and estimate with caller", "voice", "Consentement explicite du client reçu", "SMS de confirmation envoyé avec lien d'accès", "Réservation confirmée"),
            DemoStep(4, "Synchronisation agenda & fiche client", "Calendar & Customer Sync", "Inscription dans l'agenda de l'atelier et création du bon de travail", "Work order logged into garage CRM and Google Calendar", "central_ai", "Enregistrement en base de données", "Fiche client mise à jour · Google Calendar synchronisé", "Rendez-vous actif"),
        ),
    ),
    SectorProfile(
        id="health_clinic",
        name_fr="Cliniques & Professionnels de la Santé",
        name_en="Healthcare & Medical Clinics",
        description_fr="Cliniques médicales privées, dentistes, physiothérapie, psychologie et soins spécialisés.",
        description_en="Private medical practices, dental clinics, physical therapy, and specialized care.",
        icon_name="HeartPulse",
        recommended_modules=("crm", "voice", "ocr"),
        use_cases_fr=(
            "Prise de rendez-vous téléphonique intelligente avec filtrage des urgences",
            "Rappels automatiques de consultations et réduction des rendez-vous manqués",
            "Numérisation OCR de prescriptions et formulaires de consentement",
        ),
        use_cases_en=(
            "Intelligent phone appointment booking with triage and emergency redirection",
            "Automated patient appointment reminders reducing no-shows",
            "OCR digitization of consent forms, receipts, and clinical notes",
        ),
        workflow_templates=("clinic_patient_booking", "no_show_prevention", "prescription_ocr"),
        integration_prerequisites=("Google Calendar praticien", "Ligne téléphonique Telnyx"),
        regulatory_constraints_fr="Loi 25 (Québec) / HIPAA : données médicales protégées, chiffrement strict et consentement explicite requis.",
        regulatory_constraints_en="Law 25 (Quebec) / HIPAA compliance: protected health info, strict encryption, explicit consent.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Demande de consultation", "Consultation Request", "Patient sollicite une consultation de physiothérapie", "Patient requests physical therapy evaluation", "voice", "Demande vocale : première évaluation cervicale", "Qualification administrative sans collecte de diagnostic confidentiel", "Filtrage sécurisé"),
            DemoStep(2, "Vérification des disponibilités praticien", "Practitioner Availability", "CRM IA vérifie l'agenda du spécialiste disponible", "CRM AI checks therapist calendar availability", "crm", "Recherche créneau : Vendredi 10h30", "Créneau confirmé disponible chez Dr. Tremblay", "Créneau libre"),
            DemoStep(3, "Avis de gestion des données & consentement", "Privacy & Data Consent Notice", "Notification préalable sur la gestion confidentielle des données", "Automated consent notice provided before appointment storage", "central_ai", "Validation des conditions de confidentialité", "Données cloisonnées au locataire · Chiffrement AES-256", "Pratiques Loi 25 actives"),
            DemoStep(4, "Confirmation & Instructions d'arrivée", "Confirmation & Pre-visit Guide", "Envoi d'instructions d'accueil et ajout à l'agenda sécurisé", "Intake instructions issued and slot reserved on secure calendar", "crm", "Génération du rappel patient", "Réservation confirmée avec rappel 24h avant", "Rendez-vous planifié"),
        ),
    ),
    SectorProfile(
        id="restaurant_cafe",
        name_fr="Restaurants, Bars & Cafés",
        name_en="Restaurants, Bars & Cafes",
        description_fr="Établissements de restauration, traiteurs, microbrasseries et services de livraison.",
        description_en="Dining establishments, caterers, microbreweries, and food delivery businesses.",
        icon_name="Utensils",
        recommended_modules=("voice", "crm", "retail", "accounting"),
        use_cases_fr=(
            "Prise de réservations téléphoniques pendant les heures de coupure ou rush de service",
            "Analyse des coûts matières et prévision d'affluence selon la météo et le calendrier",
            "Extraction OCR immédiate des factures fournisseurs de denrées et boissons",
        ),
        use_cases_en=(
            "Voice reservation booking during peak prep hours and rush services",
            "Ingredient cost analytics and footfall prediction based on weather/season",
            "Instant OCR extraction of food and beverage supplier delivery bills",
        ),
        workflow_templates=("table_reservation_voice", "food_cost_ocr_import", "shift_affluence_forecast"),
        integration_prerequisites=("Système POS / TPV", "Google Calendar (plans de table)"),
        regulatory_constraints_fr="Mentions obligatoires sur les allergènes et conformité Module d'enregistrement des ventes (MEV).",
        regulatory_constraints_en="Allergen advisory requirements and restaurant sales recording module (SRM) rules.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Réservation téléphonique automatique", "Automated Table Booking", "Client appelle pour réserver une table de 4 personnes ce samedi", "Customer calls to reserve a table of 4 for Saturday night", "voice", "Appel vocal : samedi 19h30, 4 personnes, terrasse souhaitée", "Disponibilité vérifiée dans le CRM de réservations", "Table libre"),
            DemoStep(2, "Confirmation & Notes spécifiques", "Dietary Notes & Confirmation", "Prise en compte des remarques (ex: chaise haute requise)", "Notes recorded for high chair and window seating", "crm", "Enregistrement : Table 14 réservée", "SMS de rappel envoyé au client avec lien de modification", "Réservation validée"),
            DemoStep(3, "Extraction OCR facture fournisseur", "Supplier Invoice OCR", "Le chef photographie un bordereau de livraison de produits frais", "Chef captures delivery receipt from local seafood supplier", "ocr", "Scan PDF/Photo : 480.50 $ (poissons & légumes)", "Extraction ventilée : sous-total, taxes TPS/TVQ, fournisseur", "Extraction 99.4%"),
            DemoStep(4, "Intégration comptable préparatoire", "Accounting Ledger Prep", "Rapprochement avec le compte bancaire du restaurant", "Expense ready for month-end close with restaurant ledger", "accounting", "Écriture préparatoire générée", "Trésorerie mise à jour · Aucune double saisie manuelle", "Écriture prête"),
        ),
    ),
    SectorProfile(
        id="hair_beauty",
        name_fr="Salons de Coiffure & Esthétique",
        name_en="Hair Salons & Aesthetics",
        description_fr="Salons de coiffure, instituts de beauté, barbiers, spas et centres de bien-être.",
        description_en="Hair salons, beauty institutes, barbershops, day spas, and wellness centers.",
        icon_name="Sparkles",
        recommended_modules=("voice", "crm", "marketing"),
        use_cases_fr=(
            "Réception d'appels et réservation de soins pendant que les coiffeurs sont occupés",
            "Fiches clientes détaillées avec historique des prestations et formules de coloration",
            "Campagnes automatiques de rappel après 6 à 8 semaines d'intervalle",
        ),
        use_cases_en=(
            "Phone booking answering client calls while stylists are with clients",
            "Detailed client history cards storing color formulas and service notes",
            "Automated repeat reminders sent 6 to 8 weeks after last appointment",
        ),
        workflow_templates=("salon_appointment_voice", "client_formula_history", "recall_campaign_8weeks"),
        integration_prerequisites=("Telnyx Voice", "Google Calendar (agenda par fauteuil)"),
        regulatory_constraints_fr="Consentement pour les relances promotionnelles par SMS.",
        regulatory_constraints_en="Explicit consent required for promotional SMS recalls.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel entrant pour coupe & coloration", "Voice Booking Request", "Une cliente appelle pour un forfait balayage avec sa styliste favorite", "Client calls for color and cut with her favorite stylist", "voice", "Appel entrant : balayage avec Sophie, samedi matin", "Vérification des disponibilités de Sophie (créneau 120 min)", "Créneau trouvé"),
            DemoStep(2, "Réservation & Enregistrement CRM", "CRM Booking Entry", "Le rendez-vous est bloqué dans le calendrier du fauteuil", "Slot locked on stylist chair schedule and client history loaded", "crm", "Validation créneau : Samedi à 09h30", "Fiche client associée avec historique de ses teintes", "Agenda à jour"),
            DemoStep(3, "Campagne de fidélité automatique", "Automated Loyalty Follow-up", "Marketing IA programme le rappel personnalisé pour dans 7 semaines", "Marketing AI schedules gentle maintenance reminder for 7 weeks out", "marketing", "Règle de rétention : délai moyen entre visites = 50 jours", "Message pré-rédigé pour approbation", "Rétention +28%"),
            DemoStep(4, "Confirmation client par SMS", "SMS Appointment Confirmation", "Notification de confirmation envoyée immédiatement à la cliente", "Confirmation details delivered instantly to client", "voice", "Notification envoyée avec rappel d'annulation 24h", "Confirmation instantanée · Zéro interruption en salon", "Réservé"),
        ),
    ),
    SectorProfile(
        id="real_estate",
        name_fr="Immobilier & Gestion Locative",
        name_en="Real Estate & Property Management",
        description_fr="Agences immobilières, courtiers, gestionnaires d'immeubles et promoteurs.",
        description_en="Real estate agencies, brokers, property managers, and developers.",
        icon_name="Building",
        recommended_modules=("crm", "voice", "ocr", "marketing"),
        use_cases_fr=(
            "Qualification immédiate des appels d'acheteurs et locataires sur les annonces",
            "Planification automatique des visites d'immeubles sans allers-retours téléphoniques",
            "Extraction OCR des baux, contrats de vente et états des lieux",
        ),
        use_cases_en=(
            "Instant qualification of buyer and renter inbound calls on listings",
            "Automated property tour booking without phone tag",
            "OCR parsing of lease agreements, sales contracts, and inspection sheets",
        ),
        workflow_templates=("listing_lead_qualification", "tour_booking_calendar", "lease_contract_ocr"),
        integration_prerequisites=("Google Calendar courtier", "Ligne d'annonce Telnyx"),
        regulatory_constraints_fr="Conformité OACIQ (Québec) / Real Estate Council, protection des données des locataires.",
        regulatory_constraints_en="Real estate board regulatory compliance and tenant privacy guidelines.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel sur annonce immobilière", "Inbound Property Inquiry", "Un acheteur appelle pour obtenir des informations sur un condo en vente", "Buyer calls inquiring about a listed downtown condo", "voice", "Appel : Condo rue Sherbrooke, budget 450 000 $, visite souhaitée", "Qualification : acheteur pré-qualifié hypothécaire", "Prospect qualifié"),
            DemoStep(2, "Organisation de la visite privée", "Private Showing Scheduling", "L'agent vocal propose les plages de visite libres du courtier", "Voice agent offers open showing windows on broker calendar", "crm", "Vérification créneau : Dimanche à 14h00", "Plage de visite 45 min réservée pour le condo #402", "Visite planifiée"),
            DemoStep(3, "Extraction OCR de promesse d'achat", "Purchase Offer OCR Parsing", "Le courtier numérise une promesse d'achat reçue", "Broker uploads incoming purchase agreement PDF", "ocr", "Document PDF : Contrat de 12 pages", "Extraction : prix offert, conditions d'inspection, date d'acte", "Données extraites"),
            DemoStep(4, "Mise à jour du pipeline CRM", "Deal Pipeline Update", "Le dossier de transaction passe à l'étape 'Offre en cours'", "Deal card moves to 'Pending Conditions' stage in CRM", "crm", "Synchronisation du tableau de bord", "Courtier notifié avec échéancier d'inspection", "Dossier à jour"),
        ),
    ),
    SectorProfile(
        id="construction",
        name_fr="Construction & Rénovation",
        name_en="Construction & Contracting",
        description_fr="Entrepreneurs généraux, électriciens, plombiers, menuisiers et professionnels du bâtiment.",
        description_en="General contractors, electricians, plumbers, carpenters, and trades businesses.",
        icon_name="Hammer",
        recommended_modules=("voice", "crm", "ocr", "accounting"),
        use_cases_fr=(
            "Ne manquez aucun appel client pendant que vous êtes sur un chantier avec du bruit",
            "Qualification des demandes de devis et planification des visites d'estimation",
            "Extraction OCR immédiate des factures de quincaillerie et matériaux",
        ),
        use_cases_en=(
            "Never miss a client call while working on noisy job sites",
            "Estimates request qualification and site assessment booking",
            "Instant OCR parsing of hardware and building materials receipts",
        ),
        workflow_templates=("jobsite_call_capture", "estimate_visit_booking", "materials_invoice_ocr"),
        integration_prerequisites=("Numéro de téléphone d'entreprise Telnyx", "Google Calendar"),
        regulatory_constraints_fr="Licences RBQ / CCQ (Québec) et obligations légales sur les soumissions écrites.",
        regulatory_constraints_en="Trade licensing requirements and written estimate compliance.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel client pendant un chantier", "Jobsite Call Capture", "Un client appelle pour une rénovation complète de salle de bain", "Client calls requesting full bathroom renovation quote", "voice", "Appel téléphonique : rénovation résidentielle, début souhaité le mois prochain", "Voice IA qualifie l'adresse, l'ampleur et l'échéance", "Demande qualifiée"),
            DemoStep(2, "Prise de RDV pour estimation", "Site Assessment Scheduling", "L'agent vocal planifie la visite d'estimation sur le calendrier", "Voice agent books on-site estimate visit on contractor calendar", "crm", "Créneau proposé : Mercredi prochain à 17h00", "Visite enregistrée avec adresse du chantier", "Visite fixée"),
            DemoStep(3, "Traitement OCR des factures matériaux", "Materials Receipt OCR", "L'entrepreneur photographie un reçu de matériaux au comptoir", "Contractor snaps lumber and plumbing supply receipt", "ocr", "Photo de facture : 1 450.80 $ chez le fournisseur", "Extraction instantanée : ventilation par poste de coût", "OCR complété"),
            DemoStep(4, "Suivi de rentabilité du chantier", "Job Costing Sync", "Affectation des dépenses au dossier client dans Avenqo", "Costs attributed to client project file in Avenqo workspace", "accounting", "Calcul de la marge réelle du projet", "Dépenses imputées · Synthèse prête pour la facturation", "Marge suivie"),
        ),
    ),
    SectorProfile(
        id="transport_logistics",
        name_fr="Transport & Logistique",
        name_en="Transportation & Logistics",
        description_fr="Flottes de livraison, transporteurs de fret, transitaires et entrepôts de distribution.",
        description_en="Delivery fleets, freight carriers, freight forwarders, and distribution warehouses.",
        icon_name="Truck",
        recommended_modules=("crm", "voice", "ocr", "retail"),
        use_cases_fr=(
            "Gestion des statuts de livraison et demandes de repérage par téléphone",
            "Extraction OCR automatique des bordereaux de livraison et connaissements (BOL)",
            "Suivi de la relation client avec les expéditeurs et chargeurs réguliers",
        ),
        use_cases_en=(
            "Automated phone tracking inquiries and delivery status updates",
            "Automated OCR extraction of bills of lading (BOL) and delivery manifests",
            "Carrier CRM managing regular shippers and contract accounts",
        ),
        workflow_templates=("delivery_status_voice_ivr", "bill_of_lading_ocr", "shipper_account_crm"),
        integration_prerequisites=("Système TMS ou tableurs d'expéditions", "Ligne Telnyx"),
        regulatory_constraints_fr="Conformité réglementaire des transports et traçabilité des manifestes de marchandises.",
        regulatory_constraints_en="Freight tracking regulatory compliance and transport manifest records.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel de suivi d'expédition", "Shipment Tracking Voice Inquiry", "Un client appelle pour connaître l'heure de livraison de son fret", "Shipper calls asking for estimated delivery window on cargo", "voice", "Appel vocal : numéro d'expédition #TR-8842", "Vérification du statut d'expédition en temps réel", "Statut repéré"),
            DemoStep(2, "Réponse vocale instantanée", "Instant Automated Response", "L'agent vocal communique l'heure estimée et le nom du chauffeur", "Voice agent announces delivery window and assigned truck", "voice", "Réponse : Arrivée estimée aujourd'hui entre 14h30 et 15h15", "Appel résolu sans mobiliser l'équipe d'exploitation", "Appel traité"),
            DemoStep(3, "Numérisation OCR du connaissement", "Bill of Lading OCR Ingestion", "Le chauffeur dépose la photo du bon de livraison signé", "Driver uploads mobile scan of signed delivery slip", "ocr", "Document numérisé : preuve de livraison signée", "Extraction : poids, palettes, signature, date et heure", "BOL validé"),
            DemoStep(4, "Clôture de la commande", "Order Delivery Clearance", "Le dossier est marqué livré et la facture est prête pour émission", "Delivery confirmed and invoice prepped for shipper account", "crm", "Statut passé à 'Livré et vérifié'", "Avis envoyé au chargeur · Données archivées", "Dossier clos"),
        ),
    ),
    SectorProfile(
        id="education",
        name_fr="Éducation & Formation",
        name_en="Education & Training Centers",
        description_fr="Écoles de langues, centres de formation professionnelle, académies privées et cours spécialisés.",
        description_en="Language schools, vocational training centers, private academies, and tutoring institutes.",
        icon_name="GraduationCap",
        recommended_modules=("crm", "voice", "marketing", "ocr"),
        use_cases_fr=(
            "Qualification et orientation des inscriptions étudiantes par téléphone",
            "Gestion du pipeline d'admissions et suivi des prospects jusqu'à l'inscription",
            "Campagnes marketing ciblées pour les sessions et rentrées de cours",
        ),
        use_cases_en=(
            "Inbound phone qualification and guidance for student enrollment",
            "Admissions pipeline management and applicant follow-ups",
            "Targeted marketing campaigns for upcoming course intakes",
        ),
        workflow_templates=("admissions_inbound_voice", "course_enrollment_pipeline", "session_start_campaign"),
        integration_prerequisites=("Google Calendar (séances d'information)", "Ligne d'accueil Telnyx"),
        regulatory_constraints_fr="Protection des données personnelles des étudiants et politiques de désinscription respectées.",
        regulatory_constraints_en="Student privacy protections and opt-out policies for academic communications.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Demande d'information de formation", "Training Inquiry Call", "Un candidat appelle pour se renseigner sur le programme certifiant", "Prospective student calls asking about certification program", "voice", "Appel : Début de session, prérequis, options de financement", "Qualification de l'admissibilité par l'agent d'accueil", "Candidat qualifié"),
            DemoStep(2, "Planification de l'entretien d'admission", "Admissions Interview Booking", "L'agent planifie une séance d'évaluation avec un conseiller", "Agent reserves an interview slot with academic advisor", "crm", "Sélection créneau : Lundi à 11h00 en visioconférence", "Ajout à l'agenda de l'équipe des admissions", "Entretien fixé"),
            DemoStep(3, "Envoi automatique de la brochure", "Brochure & Syllabus Dispatch", "IA Central déclenche l'envoi du plan de cours complet par courriel", "IA Central triggers automated course syllabus and tuition guide", "central_ai", "Envoi courriel avec syllabus et fiche d'inscription", "Document acheminé avec suivi d'ouverture", "Courriel envoyé"),
            DemoStep(4, "Suivi dans le CRM des admissions", "Admissions CRM Tracking", "La fiche prospect est mise à jour avec l'ensemble des notes", "Prospect file logged with complete call notes and milestones", "crm", "Statut du prospect : 'Entretien planifié'", "Conseiller académique assigné avec contexte d'appel", "Dossier actif"),
        ),
    ),
    SectorProfile(
        id="hospitality_tourism",
        name_fr="Hôtellerie & Tourisme",
        name_en="Hospitality & Tourism",
        description_fr="Hôtels indépendants, auberges, chalets de villégiature et agences d'excursions.",
        description_en="Boutique hotels, lodges, vacation rentals, and tour operators.",
        icon_name="Compass",
        recommended_modules=("voice", "crm", "marketing", "accounting"),
        use_cases_fr=(
            "Accueil téléphonique multilingue 24/7 pour renseignements et réservations de séjours",
            "Fiches clients avec préférences de séjour pour un accueil personnalisé",
            "Communication automatisée avant l'arrivée avec instructions d'accès",
        ),
        use_cases_en=(
            "24/7 multilingual phone reception for stay inquiries and bookings",
            "Guest profile management capturing room preferences and VIP status",
            "Automated pre-arrival communications with check-in access instructions",
        ),
        workflow_templates=("hotel_guest_inbound_voice", "guest_pre_arrival_flow", "seasonal_direct_booking_promo"),
        integration_prerequisites=("Système PMS hôtelier ou calendrier", "Ligne téléphonique Telnyx"),
        regulatory_constraints_fr="Conformité sur la taxe sur l'hébergement et déclaration d'enregistrement touristique.",
        regulatory_constraints_en="Lodging tax compliance and tourist establishment licensing.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel de réservation en soirée", "Evening Reservation Call", "Un voyageur appelle à 22h pour réserver un chalet ce week-end", "Traveler calls at 10 PM to check lodge availability for weekend", "voice", "Appel : 2 nuitées, 2 adultes, options spa et animaux acceptés", "Voice IA répond immédiatement en français et anglais", "Disponibilité vérifiée"),
            DemoStep(2, "Confirmation de la réservation", "Stay Reservation Confirmation", "Création de la réservation avec consignes d'arrivée", "Reservation created with lockbox code and arrival guidelines", "crm", "Chalet Le Sommet réservé pour vendredi et samedi", "Envoi instantané de la confirmation sécurisée", "Séjour réservé"),
            DemoStep(3, "Préparation de l'accueil client", "Guest Welcoming Notes", "Les préférences du voyageur sont mémorisées dans son profil", "Guest preferences logged for future direct bookings", "crm", "Fiche client : préférence bois de chauffage et animaux", "Profil voyageur enrichi", "Profil à jour"),
            DemoStep(4, "Synchronisation comptable du séjour", "Revenue & Tax Ledgering", "La facture d'hébergement est prête pour la clôture", "Lodging transaction mapped to tax-compliant accounting entry", "accounting", "Écriture préparatoire : hébergement + taxe séjour", "Livre comptable prêt pour exportation", "Comptabilité prête"),
        ),
    ),
    SectorProfile(
        id="professional_services",
        name_fr="Services Professionnels & Conseil",
        name_en="Professional Services & Consulting",
        description_fr="Consultants en gestion, cabinets d'ingénieurs, architectes et agences de design.",
        description_en="Management consultants, engineering firms, architects, and design agencies.",
        icon_name="Briefcase",
        recommended_modules=("crm", "voice", "ocr", "accounting"),
        use_cases_fr=(
            "Filtrage des appels d'affaires entrants et prise de messages qualifiés",
            "Suivi rigoureux des mandats, jalons contractuels et propositions d'honoraires",
            "Extraction OCR des notes de frais de déplacement et reçus de mission",
        ),
        use_cases_en=(
            "Executive inbound call screening and structured message intake",
            "Rigorous tracking of client mandates, proposals, and project milestones",
            "OCR capture of travel expense receipts and project disbursements",
        ),
        workflow_templates=("consulting_lead_qualification", "mandate_milestone_crm", "expense_disbursement_ocr"),
        integration_prerequisites=("Google Calendar consultant", "Ligne téléphonique d'affaires"),
        regulatory_constraints_fr="Confidentialité des mandats (secret professionnel / accords de non-divulgation).",
        regulatory_constraints_en="Client confidentiality requirements and non-disclosure obligations.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel entrant d'un client potentiel", "Executive Inbound Call", "Un directeur d'entreprise appelle pour une mission d'audit stratégique", "Corporate executive calls requesting advisory engagement", "voice", "Appel vocal : audit organisationnel, entreprise de 85 employés", "Voice IA qualifie le besoin, le délai et le décideur", "Mandat qualifié"),
            DemoStep(2, "Planification de la consultation initiale", "Discovery Call Booking", "L'agent réserve un échange de cadrage avec l'associé principal", "Agent schedules discovery session on senior partner calendar", "crm", "Créneau fixé : Mardi prochain à 10h00", "Lien de visioconférence et confirmation transmis", "Cadrage planifié"),
            DemoStep(3, "Numérisation des reçus de mission", "Project Expense OCR", "Un consultant dépose ses reçus de déplacement ferroviaire et hôtel", "Consultant uploads business trip travel receipts", "ocr", "3 reçus scannés : 640.20 $ de débours remboursables", "Extraction détaillée : TVA, devise, poste de dépense", "OCR 100% vérifié"),
            DemoStep(4, "Rapprochement et imputation projet", "Mandate Expense Ledger", "Les débours sont rattachés au mandat client pour refacturation", "Disbursements attached to client file for project billing", "accounting", "Écriture de facturation prête", "Frais imputés au dossier · Prêt pour émission de facture", "Dossier prêt"),
        ),
    ),
    SectorProfile(
        id="accounting_firms",
        name_fr="Cabinets Comptables & Fiscalistes",
        name_en="Accounting & Tax Practices",
        description_fr="Comptables professionnels agréés (CPA), préparateurs d'impôts et conseillers fiscaux.",
        description_en="Certified public accountants (CPA), tax preparers, and bookkeeping practices.",
        icon_name="Calculator",
        recommended_modules=("accounting", "ocr", "crm", "voice"),
        use_cases_fr=(
            "Gestion des flux d'appels intenses en période fiscale (mars-avril)",
            "Collecte et extraction OCR des pièces justificatives, factures et T4/Relevé 1",
            "Suivi de l'état d'avancement des dossiers de clôture par client",
        ),
        use_cases_en=(
            "Handling heavy phone call surges during peak tax filing season",
            "Document intake and OCR parsing of client receipts and tax slips",
            "Client close tracking and missing document collection reminders",
        ),
        workflow_templates=("tax_season_call_handler", "tax_document_ocr_intake", "client_missing_doc_nudge"),
        integration_prerequisites=("Ligne Telnyx cabinet", "Google Calendar rendez-vous fiscaux"),
        regulatory_constraints_fr="Avis de non-certification : Avenqo fournit une assistance de préparation comptable sans se substituer à l'exercice d'un CPA certifié.",
        regulatory_constraints_en="Non-certification notice: Avenqo provides workflow prep and does not replace certified CPA judgment.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel client en période fiscale", "Tax Season Phone Surge", "Un client appelle pour connaître la date de remise de sa déclaration", "Client calls asking about status of corporate tax filing", "voice", "Appel : 'Mon dossier de déclaration fiscale 2025 est-il prêt ?'", "Voice IA identifie le client via son numéro vérifié", "Client authentifié"),
            DemoStep(2, "Consultation du statut dans le CRM", "File Status Retrieval", "IA Central vérifie l'étape du dossier dans le cabinet", "IA Central looks up progress stage in firm workspace", "crm", "Vérification statut : 'En révision finale par le fiscaliste'", "L'agent informe le client et propose un point téléphonique", "Statut clair"),
            DemoStep(3, "Traitement par lot de reçus clients", "Batch Receipt OCR Ingestion", "Téléversement d'un lot de 25 factures pour un client de tenue de livres", "Bookkeeper drops 25 client expense slips for month-end", "ocr", "25 documents traités en moins de 15 secondes", "Extraction automatique : dates, numéros de facture, taxes", "25/25 extraits"),
            DemoStep(4, "Génération des écritures préparatoires", "Accountant Ledger Prep", "Export structuré pour injection dans le logiciel comptable", "Structured entries ready for CPA verification and ledger import", "accounting", "Écritures équilibrées générées avec mention d'assistance", "Gain de temps de saisie de 85% pour le cabinet", "Livre préparé"),
        ),
    ),
    SectorProfile(
        id="manufacturing_distribution",
        name_fr="Industrie, Fabrication & Distribution",
        name_en="Manufacturing & Wholesale Distribution",
        description_fr="Usines de fabrication, grossistes, distributeurs industriels et importateurs B2B.",
        description_en="Manufacturing plants, wholesalers, industrial distributors, and B2B importers.",
        icon_name="Factory",
        recommended_modules=("retail", "ocr", "crm", "accounting"),
        use_cases_fr=(
            "Analyse des volumes de commandes B2B et anticipation des réapprovisionnements matières",
            "Numérisation OCR des bons de commande clients complexes et manifestes d'expédition",
            "Gestion des comptes clients distributeurs et suivi des conditions tarifaires",
        ),
        use_cases_en=(
            "B2B order volume velocity and raw material replenishment forecasts",
            "OCR processing of complex purchase orders (PO) and shipping manifests",
            "Wholesale distributor CRM tracking negotiated payment terms and pricing",
        ),
        workflow_templates=("b2b_purchase_order_ocr", "wholesale_replenishment_forecast", "distributor_account_review"),
        integration_prerequisites=("Système ERP / tableurs d'inventaire", "Passerelle de facturation"),
        regulatory_constraints_fr="Traçabilité des lots et respect des normes industrielles applicables.",
        regulatory_constraints_en="Batch lot traceability and industrial trade standards compliance.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Réception d'un bon de commande B2B", "B2B Purchase Order Ingestion", "Un distributeur transmet un bon de commande PDF de 14 lignes d'articles", "Distributor submits 14-line item purchase order PDF", "ocr", "Bon de commande PDF de 45 200 $ reçu par courriel", "Extraction OCR : codes SKU, quantités, prix unitaires convenus", "14 lignes extraites"),
            DemoStep(2, "Vérification des stocks disponibles", "Inventory Sufficiency Check", "Retail IA vérifie la disponibilité des pièces en entrepôt", "Retail AI verifies warehouse stock balance for all 14 lines", "retail", "Analyse stocks : 12 articles prêts, 2 en réassort dans 48h", "Calcul de la date de livraison garantie complète", "Stock vérifié"),
            DemoStep(3, "Mise à jour de la fiche grand compte", "Account Deal Update", "Le CRM enregistre la commande confirmée au compte du distributeur", "CRM records confirmed order on distributor ledger", "crm", "Enregistrement commande #PO-9418", "Termes de paiement : Net 30 jours appliqués", "Commande enregistrée"),
            DemoStep(4, "Génération de l'accusé de réception", "Order Confirmation Dispatch", "Confirmation automatique avec date d'expédition expédiée au client", "Order confirmation and planned ship date dispatched to client", "central_ai", "Accusé de réception formel envoyé", "Équipe d'entrepôt notifiée pour préparation de la commande", "Ordre lancé"),
        ),
    ),
    SectorProfile(
        id="service_companies",
        name_fr="Entreprises de Services & Dépannage",
        name_en="Field Services & Maintenance",
        description_fr="Services de nettoyage, sécurité, dépannage informatique, climatisation et paysagement.",
        description_en="Commercial cleaning, security patrol, IT repair, HVAC maintenance, and landscaping.",
        icon_name="ShieldCheck",
        recommended_modules=("voice", "crm", "ocr", "marketing"),
        use_cases_fr=(
            "Permanence téléphonique pour urgences de dépannage 24/7 avec routage immédiat",
            "Attribution des demandes d'intervention aux techniciens sur le terrain",
            "Facturation des interventions récurrentes et suivi des contrats annuels",
        ),
        use_cases_en=(
            "24/7 on-call dispatch handling urgent maintenance calls and triage",
            "Field technician job assignment and mobile dispatch tracking",
            "Recurring contract billing management and annual maintenance renewals",
        ),
        workflow_templates=("field_service_emergency_call", "technician_job_dispatch", "annual_maintenance_renewal"),
        integration_prerequisites=("Ligne de garde Telnyx", "Google Calendar techniciens"),
        regulatory_constraints_fr="Obligation de confirmation écrite des tarifs avant intervention d'urgence.",
        regulatory_constraints_en="Mandatory disclosure of emergency rates before dispatch.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Appel pour urgence climatisation / CVC", "Urgent Service Call", "Un gestionnaire d'immeuble appelle pour une panne de climatiseur en surchauffe", "Building manager calls for urgent server room HVAC failure", "voice", "Appel d'urgence : panne de climatisation, salle des serveurs", "L'agent vocal qualifie l'urgence critique et la localisation", "Urgence identifiée"),
            DemoStep(2, "Sélection du technicien de garde", "Technician Calendar Check", "CRM IA vérifie qui est le technicien d'astreinte disponible dans la zone", "CRM AI checks on-call technician schedule in geographic sector", "crm", "Technicien Marc disponible à 25 minutes du site", "Créneau d'intervention bloqué à 11h15", "Technicien assigné"),
            DemoStep(3, "Confirmation immédiate au client", "Caller Status Update", "L'agent rassure l'appelant et confirme l'arrivée du technicien", "Voice agent confirms estimated technician arrival with caller", "voice", "Avis verbal : technicien Marc en route, arrivée 11h15", "SMS de suivi transmis au gestionnaire", "Client rassuré"),
            DemoStep(4, "Création du bon d'intervention", "Service Ticket Generation", "Le bon de travail complet est généré dans le CRM d'entreprise", "Comprehensive ticket logged with notes and fault description", "crm", "Fiche intervention #TK-551 créée", "Rapport prêt pour validation post-intervention", "Ticket actif"),
        ),
    ),
    SectorProfile(
        id="associations_nonprofit",
        name_fr="Associations & Organismes sans but lucratif",
        name_en="Associations & Non-Profits",
        description_fr="Organismes de bienfaisance, chambres de commerce, ordres professionnels et fondations.",
        description_en="Charitable organizations, chambers of commerce, non-profits, and foundations.",
        icon_name="Users",
        recommended_modules=("crm", "marketing", "ocr", "accounting"),
        use_cases_fr=(
            "Gestion des adhésions, cotisations et renouvellements annuels des membres",
            "Campagnes de sensibilisation et courriels d'invitation aux assemblées",
            "Extraction OCR des reçus de dons et justificatifs de subventions",
        ),
        use_cases_en=(
            "Member database management, annual renewals, and dues tracking",
            "Community outreach campaigns and AGM invitation broadcasts",
            "OCR processing of donation slips, receipts, and grant expense reports",
        ),
        workflow_templates=("membership_renewal_nudge", "donor_receipt_ocr", "community_event_invitation"),
        integration_prerequisites=("Passerelle de don ou paiements", "Base de contacts membres"),
        regulatory_constraints_fr="Conformité sur la gouvernance des OSBL et émission de reçus officiels de don.",
        regulatory_constraints_en="Non-profit governance rules and official tax receipt standards.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Gestion des renouvellements d'adhésion", "Member Dues Renewal", "Identification des membres arrivant à échéance de cotisation", "System checks members whose annual membership expires this month", "crm", "Filtre CRM : 86 adhésions à renouveler ce mois-ci", "Liste segmentée prête pour communication personnalisée", "86 membres ciblés"),
            DemoStep(2, "Préparation du message de courtoisie", "Friendly Renewal Campaign", "Marketing IA rédige un message chaleureux rappelant l'impact des actions", "Marketing AI crafts warm reminder letter highlighting yearly impact", "marketing", "Texte personnalisé selon le niveau d'adhésion", "Soumis à l'approbation du conseil d'administration", "Brouillon prêt"),
            DemoStep(3, "Validation humaine du message", "Board Approval Validation", "Le directeur général approuve la diffusion", "Executive director signs off on the outreach communication", "central_ai", "Validation administrative effectuée", "Envoi planifié sans sollicitation agressive", "Action approuvée"),
            DemoStep(4, "Numérisation des reçus de don", "Donation Receipt OCR", "Numérisation des bordereaux de dons reçus par la poste", "Intake of paper donation slips received at community office", "ocr", "Lots de dons numérisés avec attribution aux donateurs", "Extraction des montants pour production du reçu fiscal", "Dons enregistrés"),
        ),
    ),
    SectorProfile(
        id="other_custom",
        name_fr="Autre secteur d'activité",
        name_en="Other Custom Sector",
        description_fr="Entreprise ou activité spécifique : configurez votre secteur sur mesure avec vos propres processus.",
        description_en="Specialized business model: configure your custom industry profile tailored to your unique operations.",
        icon_name="Sparkles",
        recommended_modules=("crm", "voice", "retail", "accounting", "marketing", "ocr"),
        use_cases_fr=(
            "Personnalisation intégrale des modules selon vos processus opérationnels uniques",
            "Orchestration IA Central sur mesure reliant vos outils et vos équipes",
            "Démonstration synthétique guidée avec vos cas d'usages spécifiques",
        ),
        use_cases_en=(
            "Full module customization configured around your unique business operations",
            "Custom IA Central orchestration connecting your team and external tools",
            "Guided synthetic demonstration adapted to your explicit operating model",
        ),
        workflow_templates=("custom_business_automation", "central_ai_orchestration"),
        integration_prerequisites=("Selon les modules choisis",),
        regulatory_constraints_fr="Application stricte des règles de sécurité, de confidentialité et des permissions en vigueur.",
        regulatory_constraints_en="Strict application of active security, privacy, and permission controls.",
        feature_availability="available",
        demo_steps=(
            DemoStep(1, "Expression du besoin métier", "Custom Business Requirement", "Le client décrit son modèle d'exploitation personnalisé", "User describes their unique operating model and customer journey", "central_ai", "Description : modèle hybride avec rendez-vous et vente directe", "Analyse par IA Central des flux opérationnels", "Profil analysé"),
            DemoStep(2, "Recommandation modulaire adaptée", "Tailored Modular Fit", "Sélection des modules essentiels pour respecter le budget et le forfait", "Recommended module combination fitting the chosen subscription tier", "central_ai", "Modules suggérés : CRM IA + Voice IA (Forfait Base)", "Allocation exacte de 2 modules sans dépassement de forfait", "Configuration exacte"),
            DemoStep(3, "Simulation du parcours de travail", "Simulated Workflow Journey", "Démonstration interactive démontrant la synergie des modules sélectionnés", "Interactive demonstration showcasing coordination between modules", "crm", "Coordination fluide entre réception et gestion des dossiers", "Zéro friction · Processus documenté de bout en bout", "Parcours validé"),
            DemoStep(4, "Espace entreprise prêt pour activation", "Workspace Ready for Activation", "Création de l'espace avec paramètres personnalisés", "Company workspace created with dedicated custom industry profile", "central_ai", "Environnement multi-tenant isolé généré", "Accompagnement guidé pour la première valeur vérifiée", "Espace prêt"),
        ),
    ),
)

SECTOR_PROFILES_BY_ID = {profile.id: profile for profile in SECTOR_PROFILES}


def get_sector_profile(sector_id: str) -> SectorProfile:
    """Retrieve sector profile or fallback to other_custom."""
    return SECTOR_PROFILES_BY_ID.get(sector_id, SECTOR_PROFILES_BY_ID["other_custom"])
