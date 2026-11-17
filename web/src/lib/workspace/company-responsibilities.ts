/** Responsabilités d'entreprise proposées à l'invitation.

Une seule valeur est choisie. Elle devient le titre de poste et le
département, et elle pointe vers un accès déjà existant. Le propriétaire
n'est pas proposé : il ne s'attribue pas par invitation.
*/

export type CompanyAccess = "admin" | "manager" | "analyst" | "user" | "viewer";
export type CompanySize = "small" | "medium" | "large";

export type CompanyResponsibility = {
  id: string;
  size: CompanySize;
  access: CompanyAccess;
  title: { fr: string; en: string };
  department: { fr: string; en: string };
};

const ACCESS: CompanyAccess[] = ["admin", "manager", "analyst", "user", "viewer"];

export const COMPANY_SIZES: { id: CompanySize; fr: string; en: string }[] = [
  { id: "small", fr: "Petite entreprise", en: "Small company" },
  { id: "medium", fr: "Moyenne entreprise", en: "Mid-size company" },
  { id: "large", fr: "Grande entreprise", en: "Large company" },
];

export const ACCESS_SUMMARY: Record<CompanyAccess, { fr: string; en: string }> = {
  admin: {
    fr: "Administre l'équipe et les modules",
    en: "Manages the team and the modules",
  },
  manager: {
    fr: "Gère les opérations, les clients et les données",
    en: "Runs operations, customers and data",
  },
  analyst: {
    fr: "Consulte les chiffres et l'assistant",
    en: "Reads the figures and uses the assistant",
  },
  user: {
    fr: "Travaille dans son secteur, sans administrer l'entreprise",
    en: "Works in their area, without administering the company",
  },
  viewer: {
    fr: "Consultation seule",
    en: "Read only",
  },
};

function row(
  id: string,
  size: CompanySize,
  access: CompanyAccess,
  frTitle: string,
  enTitle: string,
  frDepartment: string,
  enDepartment: string,
): CompanyResponsibility {
  return {
    id,
    size,
    access,
    title: { fr: frTitle, en: enTitle },
    department: { fr: frDepartment, en: enDepartment },
  };
}

export const COMPANY_RESPONSIBILITIES: CompanyResponsibility[] = [
  row("adjoint-direction", "small", "admin", "Adjoint à la direction", "Deputy director", "Direction", "Leadership"),
  row("responsable-operations-pme", "small", "manager", "Responsable des opérations", "Operations lead", "Opérations", "Operations"),
  row("responsable-ventes-pme", "small", "manager", "Responsable des ventes", "Sales lead", "Ventes", "Sales"),
  row("comptable-pme", "small", "analyst", "Comptable", "Bookkeeper", "Finance", "Finance"),
  row("conseiller-ventes", "small", "user", "Conseiller aux ventes", "Sales advisor", "Ventes", "Sales"),
  row("responsable-clientele-pme", "small", "manager", "Responsable du service à la clientèle", "Customer service lead", "Service à la clientèle", "Customer service"),
  row("receptionniste", "small", "user", "Réceptionniste", "Receptionist", "Accueil", "Front desk"),
  row("technicien-service", "small", "user", "Technicien de service", "Service technician", "Service", "Service"),
  row("responsable-marketing-pme", "small", "manager", "Responsable marketing", "Marketing lead", "Marketing", "Marketing"),
  row("magasinier", "small", "user", "Magasinier", "Warehouse clerk", "Entrepôt", "Warehouse"),
  row("superviseur-equipe-pme", "small", "manager", "Superviseur d'équipe", "Team supervisor", "Opérations", "Operations"),
  row("adjoint-administratif", "small", "user", "Adjoint administratif", "Administrative assistant", "Administration", "Administration"),
  row("responsable-atelier", "small", "manager", "Responsable d'atelier", "Shop supervisor", "Production", "Production"),
  row("prepose-facturation", "small", "analyst", "Préposé à la facturation", "Billing clerk", "Finance", "Finance"),

  row("directeur-general-adjoint", "medium", "admin", "Directeur général adjoint", "Deputy general manager", "Direction", "Leadership"),
  row("directeur-ventes", "medium", "manager", "Directeur des ventes", "Sales director", "Ventes", "Sales"),
  row("directeur-operations-moyenne", "medium", "manager", "Directeur des opérations", "Operations director", "Opérations", "Operations"),
  row("chef-comptable", "medium", "manager", "Chef comptable", "Chief accountant", "Finance", "Finance"),
  row("responsable-rh", "medium", "admin", "Responsable des ressources humaines", "Human resources lead", "Ressources humaines", "Human resources"),
  row("responsable-ti", "medium", "admin", "Responsable des technologies", "Technology lead", "Technologie", "Technology"),
  row("chef-produit", "medium", "manager", "Chef de produit", "Product manager", "Produit", "Product"),
  row("acheteur", "medium", "analyst", "Acheteur", "Buyer", "Approvisionnement", "Procurement"),
  row("representant-commercial", "medium", "user", "Représentant commercial", "Sales representative", "Ventes", "Sales"),
  row("analyste-affaires", "medium", "analyst", "Analyste d'affaires", "Business analyst", "Analyse", "Analysis"),
  row("coordonnateur-projet", "medium", "manager", "Coordonnateur de projet", "Project coordinator", "Projets", "Projects"),
  row("responsable-paie", "medium", "analyst", "Responsable de la paie", "Payroll lead", "Paie", "Payroll"),
  row("adjoint-direction-moyenne", "medium", "user", "Adjoint de direction", "Executive assistant", "Direction", "Leadership"),
  row("superviseur-production", "medium", "manager", "Superviseur de production", "Production supervisor", "Production", "Production"),
  row("responsable-logistique", "medium", "manager", "Responsable logistique", "Logistics lead", "Logistique", "Logistics"),
  row("responsable-qualite", "medium", "analyst", "Responsable qualité", "Quality lead", "Qualité", "Quality"),

  row("vice-president", "large", "admin", "Vice-président", "Vice president", "Direction", "Leadership"),
  row("directeur-financier", "large", "admin", "Directeur financier", "Chief financial officer", "Finance", "Finance"),
  row("directeur-rh", "large", "admin", "Directeur des ressources humaines", "Human resources director", "Ressources humaines", "Human resources"),
  row("directeur-systemes", "large", "admin", "Directeur des systèmes d'information", "Chief information officer", "Technologie", "Technology"),
  row("directeur-commercial", "large", "manager", "Directeur commercial", "Commercial director", "Ventes", "Sales"),
  row("directeur-marketing", "large", "manager", "Directeur marketing", "Marketing director", "Marketing", "Marketing"),
  row("directeur-operations-grande", "large", "manager", "Directeur des opérations", "Operations director", "Opérations", "Operations"),
  row("directeur-juridique", "large", "analyst", "Directeur juridique", "General counsel", "Juridique", "Legal"),
  row("chef-departement", "large", "manager", "Chef de département", "Department head", "Direction", "Leadership"),
  row("gestionnaire-equipe", "large", "manager", "Gestionnaire d'équipe", "Team manager", "Opérations", "Operations"),
  row("controleur-gestion", "large", "analyst", "Contrôleur de gestion", "Management controller", "Finance", "Finance"),
  row("auditeur-interne", "large", "viewer", "Auditeur interne", "Internal auditor", "Conformité", "Compliance"),
  row("responsable-conformite", "large", "analyst", "Responsable conformité", "Compliance lead", "Conformité", "Compliance"),
  row("charge-grands-comptes", "large", "user", "Chargé de grands comptes", "Key account manager", "Ventes", "Sales"),
  row("specialiste-soutien", "large", "user", "Spécialiste au soutien", "Support specialist", "Service à la clientèle", "Customer service"),
  row("membre-conseil", "large", "viewer", "Membre du conseil, lecture seule", "Board member, read only", "Direction", "Leadership"),
  row("directeur-approvisionnement", "large", "manager", "Directeur de l'approvisionnement", "Procurement director", "Approvisionnement", "Procurement"),
  row("responsable-securite", "large", "analyst", "Responsable de la sécurité de l'information", "Information security lead", "Technologie", "Technology"),
];

export const DEFAULT_RESPONSIBILITY_ID = "adjoint-administratif";

export function responsibilityById(id: string): CompanyResponsibility {
  return COMPANY_RESPONSIBILITIES.find((item) => item.id === id) ?? COMPANY_RESPONSIBILITIES.find((item) => item.id === DEFAULT_RESPONSIBILITY_ID)!;
}

export function invitationFromResponsibility(id: string, locale: string): { role: CompanyAccess; job_title: string; department: string } {
  const item = responsibilityById(id);
  const lang = locale.startsWith("fr") ? "fr" : "en";
  if (!ACCESS.includes(item.access)) {
    return { role: "user", job_title: item.title[lang], department: item.department[lang] };
  }
  return { role: item.access, job_title: item.title[lang], department: item.department[lang] };
}
