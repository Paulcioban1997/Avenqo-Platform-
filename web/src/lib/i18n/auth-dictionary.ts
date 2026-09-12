import type { LocaleCode } from "./types";

export type AuthStrings = {
  backToHome: string;
  workspace: string;
  asideLoginTitle: string;
  asideLoginDesc: string;
  asideRegisterTitle: string;
  asideRegisterDesc: string;
  legal: string;
  badgeLogin: string;
  badgeRegister: string;
  headingLogin: string;
  headingRegister: string;
  subheadingLogin: string;
  subheadingRegister: string;
  firstName: string;
  lastName: string;
  organization: string;
  billingEmail: string;
  industry: string;
  email: string;
  password: string;
  passwordHint: string;
  loginSubmit: string;
  registerSubmit: string;
  hasAccountPrompt: string;
  newToAvenqoPrompt: string;
  signInLink: string;
  createOrgLink: string;
};

const frStrings: AuthStrings = {
  backToHome: "Retour à l’accueil",
  workspace: "ESPACE AVENQO",
  asideLoginTitle: "Content de vous revoir.",
  asideLoginDesc: "Retrouvez vos équipes, vos indicateurs et vos prochaines actions.",
  asideRegisterTitle: "Votre entreprise, enfin réunie.",
  asideRegisterDesc: "Créez votre espace sécurisé et activez les modules adaptés à vos priorités.",
  legal: "Une plateforme de PMC Solutions AI",
  badgeLogin: "Espace sécurisé",
  badgeRegister: "Démarrer avec Avenqo",
  headingLogin: "Connexion",
  headingRegister: "Créer votre organisation",
  subheadingLogin: "Accédez à votre espace Avenqo.",
  subheadingRegister: "Configurez votre espace professionnel.",
  firstName: "Prénom",
  lastName: "Nom",
  organization: "Organisation",
  billingEmail: "Email de facturation",
  industry: "Secteur d’activité",
  email: "Email professionnel",
  password: "Mot de passe",
  passwordHint: "10 caractères minimum, avec majuscule, minuscule, chiffre et symbole.",
  loginSubmit: "Se connecter",
  registerSubmit: "Créer mon espace",
  hasAccountPrompt: "Vous avez déjà un compte ?",
  newToAvenqoPrompt: "Nouveau sur Avenqo ?",
  signInLink: "Se connecter",
  createOrgLink: "Créer une organisation",
};

const enStrings: AuthStrings = {
  backToHome: "Back to home",
  workspace: "AVENQO WORKSPACE",
  asideLoginTitle: "Welcome back.",
  asideLoginDesc: "Access your teams, performance metrics, and strategic actions.",
  asideRegisterTitle: "Your enterprise, unified at last.",
  asideRegisterDesc: "Create your secure workspace and activate modules tailored to your needs.",
  legal: "A platform by PMC Solutions AI",
  badgeLogin: "Secure Space",
  badgeRegister: "Get started with Avenqo",
  headingLogin: "Sign in",
  headingRegister: "Create your organization",
  subheadingLogin: "Access your Avenqo workspace.",
  subheadingRegister: "Set up your business workspace.",
  firstName: "First name",
  lastName: "Last name",
  organization: "Organization",
  billingEmail: "Billing email",
  industry: "Industry",
  email: "Work email",
  password: "Password",
  passwordHint: "At least 10 characters, with upper, lower, number, and symbol.",
  loginSubmit: "Sign in",
  registerSubmit: "Create my workspace",
  hasAccountPrompt: "Already have an account?",
  newToAvenqoPrompt: "New to Avenqo?",
  signInLink: "Sign in",
  createOrgLink: "Create an organization",
};

const esStrings: AuthStrings = {
  backToHome: "Volver al inicio",
  workspace: "ESPACIO AVENQO",
  asideLoginTitle: "Nos alegra verte de nuevo.",
  asideLoginDesc: "Accede a tus equipos, métricas clave y próximas acciones.",
  asideRegisterTitle: "Tu empresa, finalmente unida.",
  asideRegisterDesc: "Crea tu espacio seguro y activa los módulos adaptados a tus prioridades.",
  legal: "Una plataforma de PMC Solutions AI",
  badgeLogin: "Espacio seguro",
  badgeRegister: "Comenzar con Avenqo",
  headingLogin: "Iniciar sesión",
  headingRegister: "Crear tu organización",
  subheadingLogin: "Accede a tu espacio Avenqo.",
  subheadingRegister: "Configura tu espacio empresarial.",
  firstName: "Nombre",
  lastName: "Apellido",
  organization: "Organización",
  billingEmail: "Correo de facturación",
  industry: "Sector de actividad",
  email: "Correo profesional",
  password: "Contraseña",
  passwordHint: "Mínimo 10 caracteres, con mayúscula, minúscula, número y símbolo.",
  loginSubmit: "Iniciar sesión",
  registerSubmit: "Crear mi espacio",
  hasAccountPrompt: "¿Ya tienes una cuenta?",
  newToAvenqoPrompt: "¿Nuevo en Avenqo?",
  signInLink: "Iniciar sesión",
  createOrgLink: "Crear una organización",
};

const deStrings: AuthStrings = {
  backToHome: "Zurück zur Startseite",
  workspace: "AVENQO ARBEITSBEREICH",
  asideLoginTitle: "Willkommen zurück.",
  asideLoginDesc: "Greifen Sie auf Ihre Teams, Kennzahlen und nächsten Schritte zu.",
  asideRegisterTitle: "Ihr Unternehmen, endlich vereint.",
  asideRegisterDesc: "Erstellen Sie Ihren sicheren Bereich und aktivieren Sie passende Module.",
  legal: "Eine Plattform von PMC Solutions AI",
  badgeLogin: "Sicherer Bereich",
  badgeRegister: "Mit Avenqo starten",
  headingLogin: "Anmelden",
  headingRegister: "Organisation erstellen",
  subheadingLogin: "Greifen Sie auf Ihren Avenqo-Bereich zu.",
  subheadingRegister: "Richten Sie Ihren Unternehmensbereich ein.",
  firstName: "Vorname",
  lastName: "Nachname",
  organization: "Organisation",
  billingEmail: "Rechnungs-E-Mail",
  industry: "Branche",
  email: "Geschäftliche E-Mail",
  password: "Passwort",
  passwordHint: "Mindestens 10 Zeichen mit Groß-, Kleinbuchstaben, Zahl und Symbol.",
  loginSubmit: "Anmelden",
  registerSubmit: "Meinen Bereich erstellen",
  hasAccountPrompt: "Bereits ein Konto vorhanden?",
  newToAvenqoPrompt: "Neu bei Avenqo?",
  signInLink: "Anmelden",
  createOrgLink: "Organisation erstellen",
};

const itStrings: AuthStrings = {
  backToHome: "Torna alla home",
  workspace: "SPAZIO AVENQO",
  asideLoginTitle: "Bentornato.",
  asideLoginDesc: "Accedi ai tuoi team, ai tuoi indicatori e alle prossime azioni.",
  asideRegisterTitle: "La tua azienda, finalmente unita.",
  asideRegisterDesc: "Crea il tuo spazio sicuro e attiva i moduli adatti alle tue priorità.",
  legal: "Una piattaforma di PMC Solutions AI",
  badgeLogin: "Spazio sicuro",
  badgeRegister: "Inizia con Avenqo",
  headingLogin: "Accedi",
  headingRegister: "Crea la tua organizzazione",
  subheadingLogin: "Accedi al tuo spazio Avenqo.",
  subheadingRegister: "Configura il tuo spazio aziendale.",
  firstName: "Nome",
  lastName: "Cognome",
  organization: "Organizzazione",
  billingEmail: "Email di fatturazione",
  industry: "Settore",
  email: "Email aziendale",
  password: "Password",
  passwordHint: "Almeno 10 caratteri, con maiuscola, minuscola, numero e simbolo.",
  loginSubmit: "Accedi",
  registerSubmit: "Crea il mio spazio",
  hasAccountPrompt: "Hai già un account?",
  newToAvenqoPrompt: "Nuovo su Avenqo?",
  signInLink: "Accedi",
  createOrgLink: "Crea un'organizzazione",
};

const ptStrings: AuthStrings = {
  backToHome: "Voltar ao início",
  workspace: "ESPAÇO AVENQO",
  asideLoginTitle: "Bom ver você de volta.",
  asideLoginDesc: "Acesse suas equipes, métricas e próximas ações estratégicas.",
  asideRegisterTitle: "Sua empresa, finalmente reunida.",
  asideRegisterDesc: "Crie seu espaço seguro e ative os módulos adaptados às suas prioridades.",
  legal: "Uma plataforma da PMC Solutions AI",
  badgeLogin: "Espaço seguro",
  badgeRegister: "Comece com Avenqo",
  headingLogin: "Entrar",
  headingRegister: "Criar sua organização",
  subheadingLogin: "Acesse seu espaço Avenqo.",
  subheadingRegister: "Configure seu espaço empresarial.",
  firstName: "Nome",
  lastName: "Sobrenome",
  organization: "Organização",
  billingEmail: "Email de faturamento",
  industry: "Setor de atividade",
  email: "Email profissional",
  password: "Senha",
  passwordHint: "Mínimo de 10 caracteres, com maiúscula, minúscula, número e símbolo.",
  loginSubmit: "Entrar",
  registerSubmit: "Criar meu espaço",
  hasAccountPrompt: "Já tem uma conta?",
  newToAvenqoPrompt: "Novo no Avenqo?",
  signInLink: "Entrar",
  createOrgLink: "Criar uma organização",
};

const roStrings: AuthStrings = {
  backToHome: "Înapoi la pagina principală",
  workspace: "SPAȚIU AVENQO",
  asideLoginTitle: "Bine ai revenit.",
  asideLoginDesc: "Accesează-ți echipele, indicatorii de performanță și acțiunile următoare.",
  asideRegisterTitle: "Compania ta, în sfârșit unită.",
  asideRegisterDesc: "Creează-ți spațiul securizat și activează modulele adaptate priorităților tale.",
  legal: "O platformă creată de PMC Solutions AI",
  badgeLogin: "Spațiu securizat",
  badgeRegister: "Începe cu Avenqo",
  headingLogin: "Autentificare",
  headingRegister: "Creează-ți organizația",
  subheadingLogin: "Accesează-ți spațiul Avenqo.",
  subheadingRegister: "Configurează-ți spațiul profesional.",
  firstName: "Prenume",
  lastName: "Nume",
  organization: "Organizație",
  billingEmail: "Email facturare",
  industry: "Domeniu de activitate",
  email: "Email profesional",
  password: "Parolă",
  passwordHint: "Minim 10 caractere, majusculă, minusculă, cifră și simbol.",
  loginSubmit: "Autentificare",
  registerSubmit: "Creează spațiul meu",
  hasAccountPrompt: "Ai deja un cont?",
  newToAvenqoPrompt: "Nou pe Avenqo?",
  signInLink: "Autentificare",
  createOrgLink: "Creează o organizație",
};

const zhStrings: AuthStrings = {
  backToHome: "返回首页",
  workspace: "AVENQO 企业空间",
  asideLoginTitle: "欢迎回来。",
  asideLoginDesc: "访问您的团队、业务指标与下一步战略行动。",
  asideRegisterTitle: "企业智能生态，全景协同。",
  asideRegisterDesc: "创建安全工作区，即刻激活专属 AI 模块。",
  legal: "由 PMC Solutions AI 打造的智能平台",
  badgeLogin: "安全工作区",
  badgeRegister: "开启 Avenqo 之旅",
  headingLogin: "登录",
  headingRegister: "创建组织空间",
  subheadingLogin: "进入您的 Avenqo 工作台。",
  subheadingRegister: "配置专属企业工作区。",
  firstName: "名",
  lastName: "姓",
  organization: "企业或组织名称",
  billingEmail: "财务账单邮箱",
  industry: "行业类别",
  email: "工作邮箱",
  password: "密码",
  passwordHint: "至少 10 个字符，包含大写字母、小写字母、数字及特殊符号。",
  loginSubmit: "立即登录",
  registerSubmit: "创建工作区",
  hasAccountPrompt: "已有账号？",
  newToAvenqoPrompt: "初次使用 Avenqo？",
  signInLink: "登录",
  createOrgLink: "创建组织",
};

const jaStrings: AuthStrings = {
  backToHome: "ホームへ戻る",
  workspace: "AVENQO ワークスペース",
  asideLoginTitle: "お帰りなさい。",
  asideLoginDesc: "チーム、主要業績指標、次のアクションへアクセス。",
  asideRegisterTitle: "ビジネスのすべてを、ひとつに統合。",
  asideRegisterDesc: "セキュアなワークスペースを作成し、最適な AI モジュールを有効化。",
  legal: "PMC Solutions AI 提供プラットフォーム",
  badgeLogin: "セキュアスペース",
  badgeRegister: "Avenqo を始める",
  headingLogin: "ログイン",
  headingRegister: "組織を作成",
  subheadingLogin: "Avenqo ワークスペースへアクセス。",
  subheadingRegister: "ビジネスワークスペースを設定。",
  firstName: "名",
  lastName: "姓",
  organization: "組織名",
  billingEmail: "請求先メールアドレス",
  industry: "業種",
  email: "ビジネス用メールアドレス",
  password: "パスワード",
  passwordHint: "10文字以上、大文字・小文字・数字・記号を含めてください。",
  loginSubmit: "ログイン",
  registerSubmit: "スペースを作成",
  hasAccountPrompt: "すでにアカウントをお持ちですか？",
  newToAvenqoPrompt: "Avenqo は初めてですか？",
  signInLink: "ログイン",
  createOrgLink: "組織を作成",
};

const arStrings: AuthStrings = {
  backToHome: "العودة إلى الصفحة الرئيسية",
  workspace: "مساحة عمل أفينكو",
  asideLoginTitle: "أهلاً بك مجدداً.",
  asideLoginDesc: "وصول آمن إلى فرقك ومؤشرات أدائك والخطوات القادمة.",
  asideRegisterTitle: "مؤسستك، متكاملة أخيراً.",
  asideRegisterDesc: "أنشئ مساحة عملك الآمنة وفعّل حلول الذكاء الاصطناعي المناسبة.",
  legal: "منصة مدعومة من PMC Solutions AI",
  badgeLogin: "مساحة آمنة",
  badgeRegister: "ابدأ مع أفينكو",
  headingLogin: "تسجيل الدخول",
  headingRegister: "إنشاء مؤسستك",
  subheadingLogin: "ادخل إلى مساحة عمل أفينكو الخاصة بك.",
  subheadingRegister: "قم بإعداد مساحة عملك المهنية.",
  firstName: "الاسم الأول",
  lastName: "اسم العائلة",
  organization: "اسم المؤسسة",
  billingEmail: "بريد الفواتير",
  industry: "قطاع الأعمال",
  email: "البريد الإلكتروني للعمل",
  password: "كلمة المرور",
  passwordHint: "10 أحرف كحد أدنى، مع حروف كبيرة وصغيرة وأرقام ورموز.",
  loginSubmit: "تسجيل الدخول",
  registerSubmit: "إنشاء مساحة العمل",
  hasAccountPrompt: "هل لديك حساب بالفعل؟",
  newToAvenqoPrompt: "جديد في أفينكو؟",
  signInLink: "تسجيل الدخول",
  createOrgLink: "إنشاء مؤسسة",
};

const nlStrings: AuthStrings = {
  ...enStrings,
  backToHome: "Terug naar startpagina",
  workspace: "AVENQO WERKOMGEVING",
  asideLoginTitle: "Welkom terug.",
  asideLoginDesc: "Toegang tot uw teams, prestatiemetrics en strategische acties.",
  headingLogin: "Inloggen",
  subheadingLogin: "Ga naar uw Avenqo werkomgeving.",
  loginSubmit: "Inloggen",
  email: "Zakelijk e-mailadres",
  password: "Wachtwoord",
  newToAvenqoPrompt: "Nieuw bij Avenqo?",
  createOrgLink: "Organisatie aanmaken",
};

const plStrings: AuthStrings = {
  ...enStrings,
  backToHome: "Powrót do strony głównej",
  workspace: "OBSZAR ROBOCZY AVENQO",
  asideLoginTitle: "Witaj ponownie.",
  asideLoginDesc: "Dostęp do zespołów, kluczowych wskaźników i kolejnych działań.",
  headingLogin: "Zaloguj się",
  subheadingLogin: "Uzyskaj dostęp do obszaru roboczego Avenqo.",
  loginSubmit: "Zaloguj się",
  email: "Służbowy adres e-mail",
  password: "Hasło",
  newToAvenqoPrompt: "Nowy w Avenqo?",
  createOrgLink: "Utwórz organizację",
};

const ruStrings: AuthStrings = {
  ...enStrings,
  backToHome: "На главную",
  workspace: "ПРОСТРАНСТВО AVENQO",
  asideLoginTitle: "С возвращением.",
  asideLoginDesc: "Доступ к командам, метрикам и ключевым бизнес-задачам.",
  headingLogin: "Вход",
  subheadingLogin: "Войдите в рабочее пространство Avenqo.",
  loginSubmit: "Войти",
  email: "Корпоративный e-mail",
  password: "Пароль",
  newToAvenqoPrompt: "Впервые в Avenqo?",
  createOrgLink: "Создать организацию",
};

const AUTH_LOCALES: Record<string, AuthStrings> = {
  fr: frStrings,
  "fr-FR": frStrings,
  en: enStrings,
  "en-GB": enStrings,
  es: esStrings,
  de: deStrings,
  it: itStrings,
  pt: ptStrings,
  ro: roStrings,
  zh: zhStrings,
  ja: jaStrings,
  ar: arStrings,
  "ar-EG": arStrings,
  nl: nlStrings,
  pl: plStrings,
  ru: ruStrings,
};

export function getAuthStrings(locale: LocaleCode): AuthStrings {
  if (AUTH_LOCALES[locale]) {
    return AUTH_LOCALES[locale];
  }
  return enStrings;
}
