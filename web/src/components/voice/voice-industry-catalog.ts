/**
 * Avenqo Voice AI — Extensible International Industry Catalog
 * 30+ Sectors with representative photography, reliable SVG fallbacks,
 * domain categories, and tailored Voice AI capability suggestions.
 */

export interface IndustryItem {
  id: string;
  nameFr: string;
  nameEn: string;
  category: "health" | "commerce" | "hospitality" | "transport" | "property" | "finance_legal" | "professional" | "other";
  icon: string;
  descFr: string;
  descEn: string;
  image: string;
  fallbackSvg: string;
  suggestedCapabilitiesFr: string[];
  suggestedCapabilitiesEn: string[];
}

export interface IndustryCategory {
  id: string;
  labelFr: string;
  labelEn: string;
}

export const INDUSTRY_CATEGORIES: IndustryCategory[] = [
  { id: "all", labelFr: "Tous les secteurs", labelEn: "All sectors" },
  { id: "commerce", labelFr: "Commerce & Vente", labelEn: "Retail & Commerce" },
  { id: "health", labelFr: "Santé & Soins", labelEn: "Healthcare & Wellness" },
  { id: "hospitality", labelFr: "Hôtellerie & Restauration", labelEn: "Hospitality & Dining" },
  { id: "transport", labelFr: "Transport & Logistique", labelEn: "Transport & Logistics" },
  { id: "property", labelFr: "Immobilier & Travaux", labelEn: "Real Estate & Construction" },
  { id: "finance_legal", labelFr: "Finance & Juridique", labelEn: "Finance & Legal" },
  { id: "professional", labelFr: "Services & Entreprises", labelEn: "Professional Services" },
];

// Helper to create an instant gradient SVG fallback with dark Avenqo aesthetic
function createSvgFallback(title: string, icon: string, bgGradient: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 250" width="100%" height="100%">
    <defs>
      <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
        ${bgGradient}
      </linearGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#grad)" />
    <circle cx="200" cy="110" r="45" fill="rgba(255,255,255,0.08)" />
    <text x="50%" y="120" font-size="38" text-anchor="middle" dominant-baseline="middle">${icon}</text>
    <text x="50%" y="195" font-family="system-ui, sans-serif" font-size="16" font-weight="bold" fill="#ffffff" text-anchor="middle">${title}</text>
    <text x="50%" y="220" font-family="system-ui, sans-serif" font-size="11" fill="#94a3b8" text-anchor="middle">Avenqo Voice AI</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const INDUSTRY_CATALOG: IndustryItem[] = [
  // 1. Automobile / Pièces
  {
    id: "auto",
    nameFr: "Automobile / Pièces",
    nameEn: "Automotive / Parts",
    category: "transport",
    icon: "🚗",
    descFr: "Pièces compatibles, stocks réels, devis d'atelier et rendez-vous mécaniques.",
    descEn: "Compatible parts, inventory, garage quotes and service bookings.",
    image: "https://images.unsplash.com/photo-1619642751034-765dfdf7c58e?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Automobile / Pièces", "🚗", '<stop offset="0%" stop-color="#0f172a"/><stop offset="100%" stop-color="#1e293b"/>'),
    suggestedCapabilitiesFr: [
      "Vérification de compatibilité de pièces par VIN ou modèle",
      "Disponibilité des stocks et tarifs indicatifs",
      "Prise de rendez-vous d'entretien et réparations d'atelier",
      "Suivi de l'avancement d'un véhicule en atelier",
    ],
    suggestedCapabilitiesEn: [
      "Parts compatibility by VIN or vehicle model",
      "Inventory availability and indicative pricing",
      "Maintenance and repair workshop booking",
      "Work-in-progress status tracking",
    ],
  },
  // 2. Médical / Cliniques
  {
    id: "medical",
    nameFr: "Médical / Cliniques",
    nameEn: "Medical / Clinics",
    category: "health",
    icon: "🏥",
    descFr: "Accueil des patients, horaires, rendez-vous et transfert d'urgence au personnel soignant.",
    descEn: "Patient reception, hours, appointment booking and clinical routing.",
    image: "https://images.unsplash.com/photo-1629909613654-28e377c37b09?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Médical / Clinique", "🏥", '<stop offset="0%" stop-color="#064e3b"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Prise et modification de rendez-vous médicaux",
      "Informations administratives et documents requis",
      "Horaires des praticiens et téléconsultations",
      "Transfert prioritaire vers le personnel infirmier autorisé",
    ],
    suggestedCapabilitiesEn: [
      "Medical appointment booking and rescheduling",
      "Administrative guidance and required documents",
      "Practitioner schedules and telehealth options",
      "Priority transfer to authorized nursing staff",
    ],
  },
  // 3. Restauration
  {
    id: "restaurant",
    nameFr: "Restauration / Traiteur",
    nameEn: "Restaurant / Catering",
    category: "hospitality",
    icon: "🍽️",
    descFr: "Réservations de tables, menus, allergènes sur données vérifiées et horaires.",
    descEn: "Table reservations, menus, verified allergen inquiries and hours.",
    image: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Restauration", "🍽️", '<stop offset="0%" stop-color="#7c2d12"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Réservation de table et confirmation par SMS",
      "Présentation du menu et plats du jour",
      "Questions sur les allergènes fondées sur sources vérifiées",
      "Commandes à emporter et événements de groupe",
    ],
    suggestedCapabilitiesEn: [
      "Table booking with instant SMS confirmation",
      "Daily specials and menu presentation",
      "Allergen inquiries answered from verified ingredients data",
      "Takeout orders and private group bookings",
    ],
  },
  // 4. Commerce / Retail (URL Unsplash réparée + fallback local garanti)
  {
    id: "retail",
    nameFr: "Commerce / Retail",
    nameEn: "Retail / Boutique",
    category: "commerce",
    icon: "🛍️",
    descFr: "Disponibilité des articles en boutique, suivi de commande et retours.",
    descEn: "In-store product availability, order tracking and returns.",
    image: "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Commerce / Retail", "🛍️", '<stop offset="0%" stop-color="#1e1b4b"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Vérification des stocks en magasin en temps réel",
      "Suivi des colis et statut d'expédition",
      "Politique de retour et horaires des succursales",
      "Recommandations d'articles complémentaires autorisés",
    ],
    suggestedCapabilitiesEn: [
      "Real-time in-store stock checks",
      "Parcel tracking and shipment status",
      "Return policies and branch opening hours",
      "Authorized upsell & cross-sell suggestions",
    ],
  },
  // 5. Transport / Logistique
  {
    id: "transport",
    nameFr: "Transport / Logistique",
    nameEn: "Transport / Logistics",
    category: "transport",
    icon: "🚛",
    descFr: "Statut des livraisons, suivi des expéditions et assistance aux chauffeurs autorisés.",
    descEn: "Delivery status, shipment tracking and authorized driver assistance.",
    image: "https://images.unsplash.com/photo-1519003722824-194d4455a60c?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Transport / Logistique", "🚛", '<stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#0284c7"/>'),
    suggestedCapabilitiesFr: [
      "Suivi d'expédition par numéro de connaissement (BOL)",
      "Statut estimé d'arrivée (ETA) et créneaux de quai",
      "Assistance aux chauffeurs authentifiés par NIP",
      "Horaires et accès sécurisé aux entrepôts",
    ],
    suggestedCapabilitiesEn: [
      "Shipment tracking by Bill of Lading (BOL)",
      "Estimated time of arrival (ETA) and dock windows",
      "PIN-authenticated driver support & instructions",
      "Warehouse hours and gate access protocols",
    ],
  },
  // 6. Immobilier
  {
    id: "real_estate",
    nameFr: "Immobilier",
    nameEn: "Real Estate",
    category: "property",
    icon: "🏡",
    descFr: "Visites, qualification des acquéreurs, fiches propriétés et prise de rendez-vous.",
    descEn: "Property viewings, buyer qualification, listings and agent booking.",
    image: "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Immobilier", "🏡", '<stop offset="0%" stop-color="#14532d"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Renseignements sur les propriétés en vente ou location",
      "Qualification des critères de recherche et budget",
      "Planification de visites avec les courtiers",
      "Demande d'évaluation immobilière préliminaire",
    ],
    suggestedCapabilitiesEn: [
      "Information on properties for sale or lease",
      "Search criteria and buyer budget qualification",
      "Viewing bookings with licensed brokers",
      "Preliminary market evaluation requests",
    ],
  },
  // 7. Hôtellerie / Tourisme
  {
    id: "hospitality",
    nameFr: "Hôtellerie / Tourisme",
    nameEn: "Hospitality / Tourism",
    category: "hospitality",
    icon: "🏨",
    descFr: "Réservations, check-in, conciergerie, horaires et assistance séjour.",
    descEn: "Reservations, check-in info, concierge services and guest support.",
    image: "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Hôtellerie / Tourisme", "🏨", '<stop offset="0%" stop-color="#831843"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Réservation et modification de chambres",
      "Instructions de check-in / check-out et stationnement",
      "Services de conciergerie et recommandations locales",
      "Demandes spéciales pour les résidents",
    ],
    suggestedCapabilitiesEn: [
      "Room booking and stay modifications",
      "Check-in / check-out policies and parking guidance",
      "Concierge assistance and local recommendations",
      "Guest service requests and room amenities",
    ],
  },
  // 8. Beauté / Bien-être
  {
    id: "beauty",
    nameFr: "Beauté / Bien-être",
    nameEn: "Beauty / Wellness",
    category: "health",
    icon: "💆",
    descFr: "Rendez-vous, disponibilités des praticiens, soins et rappels automatiques.",
    descEn: "Appointments, specialist availability, treatments and reminders.",
    image: "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Beauté / Bien-être", "💆", '<stop offset="0%" stop-color="#701a75"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Réservation de soins esthétiques, coiffure et massothérapie",
      "Tarifs des prestations et forfaits",
      "Rappels de rendez-vous et gestion des reports",
      "Conseils préparatoires avant soins",
    ],
    suggestedCapabilitiesEn: [
      "Spa, hair salon, and massage booking",
      "Treatment pricing and package details",
      "Automated appointment reminders & rescheduling",
      "Pre-treatment preparation guidelines",
    ],
  },
  // 9. Construction / Entrepreneurs
  {
    id: "construction",
    nameFr: "Construction / Entrepreneurs",
    nameEn: "Construction / Contractors",
    category: "property",
    icon: "🏗️",
    descFr: "Demandes de soumissions, planification de chantiers et urgences travaux.",
    descEn: "Quote requests, project scheduling and emergency job calls.",
    image: "https://images.unsplash.com/photo-1541888946425-d0fbb18086f6?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Construction", "🏗️", '<stop offset="0%" stop-color="#b45309"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Collecte des besoins pour devis de rénovation ou construction",
      "Urgences plomberie, électricité ou toiture",
      "Planification des visites d'estimation sur site",
      "Coordination des sous-traitants autorisés",
    ],
    suggestedCapabilitiesEn: [
      "Project requirement intake for contractor quotes",
      "Emergency plumbing, electrical or roofing calls",
      "On-site estimate scheduling",
      "Authorized subcontractor coordination",
    ],
  },
  // 10. Finance / Services bancaires
  {
    id: "finance",
    nameFr: "Finance / Services bancaires",
    nameEn: "Finance / Banking",
    category: "finance_legal",
    icon: "💳",
    descFr: "Rendez-vous conseiller, horaires d'agences et pré-qualification sécurisée.",
    descEn: "Advisor appointments, branch hours and secure pre-qualification.",
    image: "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Finance", "💳", '<stop offset="0%" stop-color="#065f46"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Prise de rendez-vous avec un conseiller financier",
      "Renseignements sur les heures d'ouverture des succursales",
      "Pré-qualification sécurisée de demandes de prêt",
      "Orientation vers les services de gestion de patrimoine",
    ],
    suggestedCapabilitiesEn: [
      "Financial advisor meeting scheduling",
      "Branch locations and business hours",
      "Secure loan inquiry pre-qualification",
      "Routing to wealth management departments",
    ],
  },
  // 11. Assurance
  {
    id: "insurance",
    nameFr: "Assurance / Courtage",
    nameEn: "Insurance / Brokerage",
    category: "finance_legal",
    icon: "🛡️",
    descFr: "Déclaration préliminaire de sinistre, suivi de dossier et polices.",
    descEn: "Claim filing intake, claim tracking and policy inquiries.",
    image: "https://images.unsplash.com/photo-1450133064473-71024230f91b?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Assurance", "🛡️", '<stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Prise en charge initiale de déclaration de sinistre",
      "Suivi de l'avancement d'un dossier d'indemnisation",
      "Demande de soumission auto, habitation ou commerciale",
      "Attestations d'assurance et rendez-vous d'expert",
    ],
    suggestedCapabilitiesEn: [
      "Initial insurance claim reporting intake",
      "Status checks on ongoing claims",
      "Quote requests for auto, home or business policies",
      "Proof of insurance requests and adjuster appointments",
    ],
  },
  // 12. Cabinets juridiques
  {
    id: "legal",
    nameFr: "Cabinets juridiques / Notaires",
    nameEn: "Legal / Law Firms",
    category: "finance_legal",
    icon: "⚖️",
    descFr: "Prise de rendez-vous, filtrage de dossiers et confidentialité garantie.",
    descEn: "Client consultations, intake screening and strict confidentiality.",
    image: "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Cabinets juridiques", "⚖️", '<stop offset="0%" stop-color="#312e81"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Filtrage préalable des nouveaux dossiers juridiques",
      "Prise de rendez-vous pour consultation initiale",
      "Transmission sécurisée de documents requis",
      "Orientation selon le domaine de pratique juridique",
    ],
    suggestedCapabilitiesEn: [
      "New legal matter intake and screening",
      "Initial consultation booking",
      "Secure instructions on required documents",
      "Routing by practice area (corporate, family, litigation)",
    ],
  },
  // 13. Éducation / Universités
  {
    id: "education",
    nameFr: "Éducation / Universités",
    nameEn: "Education / Universities",
    category: "professional",
    icon: "🎓",
    descFr: "Renseignements admissions, calendrier académique et portes ouvertes.",
    descEn: "Admissions info, academic calendar and open house registrations.",
    image: "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Éducation", "🎓", '<stop offset="0%" stop-color="#1e1b4b"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Informations sur les programmes d'études et critères d'admission",
      "Dates limites d'inscription et calendrier universitaire",
      "Réservation de visites guidées du campus",
      "Transfert vers les services financiers étudiants",
    ],
    suggestedCapabilitiesEn: [
      "Program details and admission requirement inquiries",
      "Registration deadlines and academic calendar",
      "Campus tour and open house bookings",
      "Routing to student financial services",
    ],
  },
  // 14. Ressources humaines / Recrutement
  {
    id: "hr_recruitment",
    nameFr: "Ressources humaines / Recrutement",
    nameEn: "Human Resources / Staffing",
    category: "professional",
    icon: "👥",
    descFr: "Pré-qualification des candidats, prise de rendez-vous d'entrevue et offres.",
    descEn: "Candidate pre-screening, interview scheduling and job postings.",
    image: "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Ressources humaines", "👥", '<stop offset="0%" stop-color="#3730a3"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Réponses aux questions sur les postes ouverts",
      "Pré-qualification téléphonique des candidats",
      "Planification des entrevues d'embauche",
      "Suivi des étapes de recrutement",
    ],
    suggestedCapabilitiesEn: [
      "Open job positions inquiries & requirements",
      "Initial phone screening questions for candidates",
      "Automated interview time slot booking",
      "Candidate hiring process updates",
    ],
  },
  // 15. Informatique / Services TI
  {
    id: "it_services",
    nameFr: "Informatique / Services TI",
    nameEn: "IT Services / Tech Support",
    category: "professional",
    icon: "💻",
    descFr: "Tickets d'assistance niveau 1, état des pannes et interventions techniques.",
    descEn: "Tier 1 support tickets, outage status and technician dispatch.",
    image: "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Services TI", "💻", '<stop offset="0%" stop-color="#0369a1"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Création de tickets d'assistance informatique niveau 1",
      "Annonce de l'état des services et pannes signalées",
      "Planification d'interventions techniques sur site",
      "Escalade d'urgences vers l'équipe d'astreinte",
    ],
    suggestedCapabilitiesEn: [
      "Tier 1 IT helpdesk ticket generation",
      "System outage announcements & updates",
      "On-site technician dispatch scheduling",
      "Emergency escalation to on-call engineers",
    ],
  },
  // 16. Industrie / Fabrication
  {
    id: "manufacturing",
    nameFr: "Industrie / Fabrication",
    nameEn: "Manufacturing / Industry",
    category: "professional",
    icon: "⚙️",
    descFr: "Commandes B2B, délais de production et réception des matières premières.",
    descEn: "B2B orders, manufacturing lead times and raw material dock info.",
    image: "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Fabrication", "⚙️", '<stop offset="0%" stop-color="#334155"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Renseignements sur les capacités de production B2B",
      "Suivi des délais de fabrication et lots en cours",
      "Instructions pour les livraisons aux quais de déchargement",
      "Demandes de fiches techniques et certifications",
    ],
    suggestedCapabilitiesEn: [
      "B2B manufacturing capabilities inquiries",
      "Lead time and production batch tracking",
      "Delivery dock receiving instructions",
      "Technical specifications & compliance sheets",
    ],
  },
  // 17. Agriculture / Agroalimentaire
  {
    id: "agriculture",
    nameFr: "Agriculture / Agroalimentaire",
    nameEn: "Agriculture / Agrifood",
    category: "professional",
    icon: "🌾",
    descFr: "Disponibilité des récoltes, commandes en vrac et certifications.",
    descEn: "Crop availability, bulk orders, seasonal produce and certifications.",
    image: "https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Agriculture", "🌾", '<stop offset="0%" stop-color="#3f6212"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Disponibilité des récoltes et produits de saison",
      "Commandes en gros et logistique de livraison en vrac",
      "Normes de traçabilité et certifications biologiques",
      "Horaires des points de vente à la ferme",
    ],
    suggestedCapabilitiesEn: [
      "Harvest availability and seasonal produce information",
      "Wholesale ordering and bulk transport coordination",
      "Organic certifications and traceability standards",
      "Farm stand and collection point schedules",
    ],
  },
  // 18. Commerce de gros / Distribution
  {
    id: "wholesale",
    nameFr: "Commerce de gros / Distribution",
    nameEn: "Wholesale / Distribution",
    category: "commerce",
    icon: "📦",
    descFr: "Tarifs dégressifs B2B, encours de crédit et planification palettes.",
    descEn: "Tiered B2B pricing, credit terms and freight pallet scheduling.",
    image: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Commerce de gros", "📦", '<stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#334155"/>'),
    suggestedCapabilitiesFr: [
      "Vérification des volumes minimums de commande (MOQ)",
      "Vérification d'encours de compte client commercial",
      "Planification des départs palettes et transporteurs",
      "Catalogue de prix par volume",
    ],
    suggestedCapabilitiesEn: [
      "Minimum order quantity (MOQ) validation",
      "Commercial account balance and credit status checks",
      "Pallet freight departure planning",
      "Volume-based wholesale price tier inquiries",
    ],
  },
  // 19. Pharmacies
  {
    id: "pharmacy",
    nameFr: "Pharmacies",
    nameEn: "Pharmacies",
    category: "health",
    icon: "💊",
    descFr: "Renouvellement d'ordonnances, horaires de garde et transfert pharmacien.",
    descEn: "Prescription refills, on-duty hours and pharmacist routing.",
    image: "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Pharmacie", "💊", '<stop offset="0%" stop-color="#047857"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Prise en charge des demandes de renouvellement d'ordonnance",
      "Horaires d'ouverture et pharmacies de garde",
      "Disponibilité des médicaments et produits en vente libre",
      "Transfert sécurisé vers le pharmacien en service",
    ],
    suggestedCapabilitiesEn: [
      "Prescription refill request intake",
      "Operating hours and emergency on-duty pharmacy info",
      "Over-the-counter stock availability",
      "Direct transfer to on-duty licensed pharmacist",
    ],
  },
  // 20. Vétérinaires
  {
    id: "veterinary",
    nameFr: "Vétérinaires / Cliniques animales",
    nameEn: "Veterinary / Pet Clinics",
    category: "health",
    icon: "🐾",
    descFr: "Consultations pour animaux, urgences, soins et rappels de vaccins.",
    descEn: "Pet appointments, emergency triage and vaccination reminders.",
    image: "https://images.unsplash.com/photo-1576201836106-db1758fd1c97?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Vétérinaire", "🐾", '<stop offset="0%" stop-color="#0f766e"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Prise de rendez-vous pour animaux de compagnie",
      "Triage préliminaire des urgences animales",
      "Rappels de vaccination et vermifuges",
      "Consignes pré-opératoires pour chirurgies",
    ],
    suggestedCapabilitiesEn: [
      "Pet consultation and check-up bookings",
      "Preliminary emergency triage for animals",
      "Vaccine and preventive care reminders",
      "Pre-surgery fasting and arrival instructions",
    ],
  },
  // 21. Services professionnels / Consultants
  {
    id: "consulting",
    nameFr: "Services professionnels / Consultants",
    nameEn: "Consulting / Professional Services",
    category: "professional",
    icon: "💼",
    descFr: "Qualification des besoins, appels découverte et présentation d'offres.",
    descEn: "Client discovery calls, service scoping and consultation booking.",
    image: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Consultants", "💼", '<stop offset="0%" stop-color="#1e1b4b"/><stop offset="100%" stop-color="#312e81"/>'),
    suggestedCapabilitiesFr: [
      "Qualification initiale des projets et besoins clients",
      "Planification d'appels découverte avec les consultants",
      "Informations sur l'éventail de services et expertises",
      "Transmission de propositions et présentations",
    ],
    suggestedCapabilitiesEn: [
      "Project scoping and needs assessment",
      "Discovery call scheduling with senior consultants",
      "Overview of consulting practices and case studies",
      "Proposal and introductory deck requests",
    ],
  },
  // 22. Services municipaux / Publics
  {
    id: "public_services",
    nameFr: "Services municipaux / Publics",
    nameEn: "Municipal / Public Services",
    category: "professional",
    icon: "🏛️",
    descFr: "Démarches citoyennes, horaires des collectes et signalements d'incidents.",
    descEn: "Citizen inquiries, collection schedules and municipal issue reports.",
    image: "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Services publics", "🏛️", '<stop offset="0%" stop-color="#1f2937"/><stop offset="100%" stop-color="#111827"/>'),
    suggestedCapabilitiesFr: [
      "Renseignements sur les collectes de déchets et écocentres",
      "Enregistrement de signalements de voirie et nids-de-poule",
      "Horaires des bureaux municipaux et cours civiques",
      "Orientation vers les bons départements administratifs",
    ],
    suggestedCapabilitiesEn: [
      "Waste collection schedules and recycling center info",
      "Municipal roadwork and issue reporting",
      "City hall opening hours and permit guidelines",
      "Routing to relevant municipal departments",
    ],
  },
  // 23. Télécommunications
  {
    id: "telecom",
    nameFr: "Télécommunications / FAI",
    nameEn: "Telecommunications / ISP",
    category: "professional",
    icon: "📡",
    descFr: "Éligibilité aux forfaits, diagnostic de ligne et rendez-vous technicien.",
    descEn: "Plan eligibility, line diagnostics and technician visits.",
    image: "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Télécoms", "📡", '<stop offset="0%" stop-color="#075985"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Vérification d'éligibilité fibre et réseau par adresse",
      "Diagnostic automatisé des coupures de réseau",
      "Prise de rendez-vous pour installation ou technicien",
      "Renseignements sur les forfaits et options mobiles/Internet",
    ],
    suggestedCapabilitiesEn: [
      "Address-based broadband & fiber eligibility check",
      "Automated outage and service health check",
      "Installation and technician appointment booking",
      "Plan details and add-on package inquiries",
    ],
  },
  // 24. Immobilier commercial
  {
    id: "commercial_real_estate",
    nameFr: "Immobilier commercial",
    nameEn: "Commercial Real Estate",
    category: "property",
    icon: "🏙️",
    descFr: "Baux commerciaux, bureaux disponibles et visites d'entreprises.",
    descEn: "Commercial leases, office space availability and business tours.",
    image: "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Immobilier commercial", "🏙️", '<stop offset="0%" stop-color="#0f172a"/><stop offset="100%" stop-color="#334155"/>'),
    suggestedCapabilitiesFr: [
      "Disponibilité d'espaces de bureaux et locaux commerciaux",
      "Conditions de baux commerciaux et zonages municipaux",
      "Planification de visites pour dirigeants et courtiers",
      "Fiches techniques des immeubles (superficie, quais, stationnement)",
    ],
    suggestedCapabilitiesEn: [
      "Office and retail commercial space availability",
      "Commercial lease terms and municipal zoning details",
      "Site viewing scheduling for corporate executives",
      "Building specifications (sq footage, loading docks, parking)",
    ],
  },
  // 25. Gestion immobilière
  {
    id: "property_management",
    nameFr: "Gestion immobilière / Syndics",
    nameEn: "Property Management / Condos",
    category: "property",
    icon: "🏢",
    descFr: "Demandes des locataires, urgences plomberie/chauffage et avis de travaux.",
    descEn: "Tenant maintenance requests, heating/plumbing emergencies and building notices.",
    image: "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Gestion immobilière", "🏢", '<stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Prise en charge des requêtes de réparation des résidents",
      "Triage d'urgences techniques (fuite d'eau, panne de chauffage)",
      "Communication des avis de travaux et coupures d'eau",
      "Paiement des loyers et charges de copropriété",
    ],
    suggestedCapabilitiesEn: [
      "Tenant repair and maintenance request intake",
      "Urgent issue triage (water leaks, furnace failure)",
      "Maintenance notices and utility disruption updates",
      "Rent and condo fee payment guidance",
    ],
  },
  // 26. Centres sportifs / Gym
  {
    id: "fitness_gym",
    nameFr: "Centres sportifs / Gym",
    nameEn: "Fitness / Gyms",
    category: "hospitality",
    icon: "🏋️",
    descFr: "Horaires des cours collectifs, abonnements et séances avec entraîneur.",
    descEn: "Group class schedules, memberships and personal training sessions.",
    image: "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Centre sportif / Gym", "🏋️", '<stop offset="0%" stop-color="#991b1b"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Horaires et réservations pour les cours de groupe",
      "Tarifs d'abonnements, forfaits et passes journalières",
      "Réservation d'évaluations physiques avec un coach",
      "Règlement des installations et heures de pointe",
    ],
    suggestedCapabilitiesEn: [
      "Group fitness class schedule and reservations",
      "Membership rates, day passes and trial offers",
      "Personal trainer session booking",
      "Facility guidelines and peak-hour advisory",
    ],
  },
  // 27. Événementiel
  {
    id: "events",
    nameFr: "Événementiel / Spectacles",
    nameEn: "Events / Entertainment",
    category: "hospitality",
    icon: "🎟️",
    descFr: "Billetterie, programme des événements, accès exposants et logistique.",
    descEn: "Ticketing, event agenda, exhibitor passes and venue logistics.",
    image: "https://images.unsplash.com/photo-1511795409834-ef04bbd61622?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Événementiel", "🎟️", '<stop offset="0%" stop-color="#581c87"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Informations sur la programmation et la billetterie",
      "Accès, stationnement et consignes de sécurité",
      "Accueil et assistance pour les exposants et conférenciers",
      "Réservations d'espaces VIP et loges",
    ],
    suggestedCapabilitiesEn: [
      "Event schedule, line-up and ticketing information",
      "Venue directions, parking and accessibility guidelines",
      "Exhibitor and speaker support",
      "VIP room and corporate suite reservations",
    ],
  },
  // 28. Livraison / Courrier
  {
    id: "delivery_courier",
    nameFr: "Livraison / Courrier",
    nameEn: "Courier / Delivery",
    category: "transport",
    icon: "🛵",
    descFr: "Suivi de colis par numéro, reprogrammation d'adresse et avis de passage.",
    descEn: "Parcel tracking, delivery rescheduling and missed delivery notices.",
    image: "https://images.unsplash.com/photo-1526367790999-0150786686a2?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Livraison express", "🛵", '<stop offset="0%" stop-color="#c2410c"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Suivi instantané par numéro d'envoi",
      "Changement d'adresse de livraison ou point relais",
      "Instructions pour les dépôts en lieu sûr",
      "Gestion des avis de passage et secondes livraisons",
    ],
    suggestedCapabilitiesEn: [
      "Instant tracking by parcel tracking number",
      "Address changes or redirect to pickup point",
      "Safe-drop instructions for drivers",
      "Missed delivery resolution and re-delivery scheduling",
    ],
  },
  // 29. Services de nettoyage
  {
    id: "cleaning_services",
    nameFr: "Services de nettoyage / Entretien",
    nameEn: "Cleaning / Janitorial Services",
    category: "property",
    icon: "🧹",
    descFr: "Devis de nettoyage résidentiel ou commercial et planification des passages.",
    descEn: "Residential & commercial cleaning quotes and recurring schedule management.",
    image: "https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Services de nettoyage", "🧹", '<stop offset="0%" stop-color="#0284c7"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Devis rapide selon la superficie en pieds carrés ou pièces",
      "Planification des passages réguliers ou grand ménage",
      "Protocoles sanitaires et produits écologiques utilisés",
      "Signalements qualité et reprogrammation d'interventions",
    ],
    suggestedCapabilitiesEn: [
      "Instant quote by square footage or room count",
      "Recurring janitorial and deep-cleaning scheduling",
      "Sanitation protocols and eco-friendly supplies used",
      "Quality feedback and intervention rescheduling",
    ],
  },
  // 30. Secteur personnalisé
  {
    id: "custom",
    nameFr: "Autre secteur / Personnalisé",
    nameEn: "Other / Custom Industry",
    category: "other",
    icon: "✨",
    descFr: "Vocabulaire sur mesure, documents d'entreprise et intentions adaptées.",
    descEn: "Custom vocabulary, corporate documents and tailored conversation flow.",
    image: "https://images.unsplash.com/photo-1497215728101-856f4ea42174?auto=format&fit=crop&w=600&q=80",
    fallbackSvg: createSvgFallback("Secteur personnalisé", "✨", '<stop offset="0%" stop-color="#4338ca"/><stop offset="100%" stop-color="#0f172a"/>'),
    suggestedCapabilitiesFr: [
      "Apprentissage du vocabulaire spécifique à votre métier",
      "Réponses fondées exclusivement sur vos documents d'entreprise",
      "Aiguillage personnalisé des appels selon vos directives",
      "Intégration d'outils internes autorisés via API",
    ],
    suggestedCapabilitiesEn: [
      "Custom business vocabulary and terminology training",
      "Answers powered strictly by your verified company files",
      "Custom call routing based on your internal rules",
      "Authorized internal tool actions via secure APIs",
    ],
  },
];
