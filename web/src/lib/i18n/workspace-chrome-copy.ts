import { getApplicationCatalog } from "./generated-app-catalogs";
import type { LocaleCode } from "./types";

export type WorkspaceChromeCopy = {
  modules: string;
  contracts: string;
  security: string;
  legal: string;
  modulesOutOfSync: string;
  retry: string;
  whiteLabel: string;
  userFallback: string;
  memberFallback: string;
};

const fr: WorkspaceChromeCopy = {
  modules: "Modules",
  contracts: "Contrats",
  security: "Sécurité et confiance",
  legal: "Juridique",
  modulesOutOfSync: "Modules non synchronisés",
  retry: "Réessayer",
  whiteLabel: "Espace marque blanche",
  userFallback: "Utilisateur",
  memberFallback: "Membre",
};

const en: WorkspaceChromeCopy = {
  modules: "Modules",
  contracts: "Contracts",
  security: "Security and trust",
  legal: "Legal",
  modulesOutOfSync: "Modules out of sync",
  retry: "Retry",
  whiteLabel: "White-label workspace",
  userFallback: "User",
  memberFallback: "Member",
};

export const WORKSPACE_CHROME_EXPLICIT: Record<LocaleCode, WorkspaceChromeCopy> = {
  fr,
  "fr-FR": fr,
  en,
  "en-GB": en,
  es: { modules: "Módulos", contracts: "Contratos", security: "Seguridad y confianza", legal: "Legal", modulesOutOfSync: "Módulos sin sincronizar", retry: "Reintentar", whiteLabel: "Espacio de marca blanca", userFallback: "Usuario", memberFallback: "Miembro" },
  pt: { modules: "Módulos", contracts: "Contratos", security: "Segurança e confiança", legal: "Jurídico", modulesOutOfSync: "Módulos dessincronizados", retry: "Tentar novamente", whiteLabel: "Espaço marca branca", userFallback: "Usuário", memberFallback: "Membro" },
  ro: { modules: "Module", contracts: "Contracte", security: "Securitate și încredere", legal: "Juridic", modulesOutOfSync: "Module nesincronizate", retry: "Reîncearcă", whiteLabel: "Spațiu white-label", userFallback: "Utilizator", memberFallback: "Membru" },
  de: { modules: "Module", contracts: "Verträge", security: "Sicherheit & Vertrauen", legal: "Rechtliches", modulesOutOfSync: "Module nicht synchronisiert", retry: "Erneut versuchen", whiteLabel: "White-Label-Arbeitsbereich", userFallback: "Benutzer", memberFallback: "Mitglied" },
  it: { modules: "Moduli", contracts: "Contratti", security: "Sicurezza e fiducia", legal: "Legale", modulesOutOfSync: "Moduli non sincronizzati", retry: "Riprova", whiteLabel: "Spazio white-label", userFallback: "Utente", memberFallback: "Membro" },
  nl: { modules: "Modules", contracts: "Contracten", security: "Beveiliging en vertrouwen", legal: "Juridisch", modulesOutOfSync: "Modules niet gesynchroniseerd", retry: "Opnieuw proberen", whiteLabel: "White-label werkruimte", userFallback: "Gebruiker", memberFallback: "Lid" },
  pl: { modules: "Moduły", contracts: "Umowy", security: "Bezpieczeństwo i zaufanie", legal: "Prawne", modulesOutOfSync: "Moduły niezsynchronizowane", retry: "Ponów", whiteLabel: "Przestrzeń white-label", userFallback: "Użytkownik", memberFallback: "Członek" },
  ru: { modules: "Модули", contracts: "Договоры", security: "Безопасность и доверие", legal: "Юридический раздел", modulesOutOfSync: "Модули не синхронизированы", retry: "Повторить", whiteLabel: "Пространство White-label", userFallback: "Пользователь", memberFallback: "Участник" },
  uk: { modules: "Модулі", contracts: "Договори", security: "Безпека та довіра", legal: "Юридичний розділ", modulesOutOfSync: "Модулі не синхронізовані", retry: "Повторити", whiteLabel: "Простір white-label", userFallback: "Користувач", memberFallback: "Учасник" },
  el: { modules: "Ενότητες", contracts: "Συμβάσεις", security: "Ασφάλεια και εμπιστοσύνη", legal: "Νομικά", modulesOutOfSync: "Μη συγχρονισμένες ενότητες", retry: "Επανάληψη", whiteLabel: "Χώρος white-label", userFallback: "Χρήστης", memberFallback: "Μέλος" },
  sv: { modules: "Moduler", contracts: "Avtal", security: "Säkerhet och förtroende", legal: "Juridik", modulesOutOfSync: "Moduler ej synkroniserade", retry: "Försök igen", whiteLabel: "White-label-arbetsyta", userFallback: "Användare", memberFallback: "Medlem" },
  tr: { modules: "Modüller", contracts: "Sözleşmeler", security: "Güvenlik ve güven", legal: "Hukuk", modulesOutOfSync: "Modüller senkronize değil", retry: "Yeniden dene", whiteLabel: "White-label çalışma alanı", userFallback: "Kullanıcı", memberFallback: "Üye" },
  cs: { modules: "Moduly", contracts: "Smlouvy", security: "Bezpečnost a důvěra", legal: "Právní", modulesOutOfSync: "Moduly nejsou synchronizovány", retry: "Zkusit znovu", whiteLabel: "White-label prostor", userFallback: "Uživatel", memberFallback: "Člen" },
  ar: { modules: "الوحدات", contracts: "العقود", security: "الأمان والثقة", legal: "الشؤون القانونية", modulesOutOfSync: "الوحدات غير متزامنة", retry: "إعادة المحاولة", whiteLabel: "مساحة عمل بعلامة بيضاء", userFallback: "مستخدم", memberFallback: "عضو" },
  "ar-EG": { modules: "الوحدات", contracts: "العقود", security: "الأمان والثقة", legal: "الشؤون القانونية", modulesOutOfSync: "الوحدات غير متزامنة", retry: "إعادة المحاولة", whiteLabel: "مساحة عمل بعلامة بيضاء", userFallback: "مستخدم", memberFallback: "عضو" },
  he: { modules: "מודולים", contracts: "חוזים", security: "אבטחה ואמון", legal: "משפטי", modulesOutOfSync: "מודולים לא מסונכרנים", retry: "נסה שוב", whiteLabel: "סביבת White-label", userFallback: "משתמש", memberFallback: "חבר" },
  fa: { modules: "ماژول‌ها", contracts: "قراردادها", security: "امنیت و اعتماد", legal: "حقوقی", modulesOutOfSync: "ماژول‌ها همگام نیستند", retry: "تلاش مجدد", whiteLabel: "فضای کاری برند اختصاصی", userFallback: "کاربر", memberFallback: "عضو" },
  ja: { modules: "モジュール", contracts: "契約", security: "セキュリティと信頼", legal: "法務", modulesOutOfSync: "モジュール未同期", retry: "再試行", whiteLabel: "ホワイトラベル空間", userFallback: "ユーザー", memberFallback: "メンバー" },
  ko: { modules: "모듈", contracts: "계약", security: "보안 및 신뢰", legal: "법무", modulesOutOfSync: "모듈 동기화 안 됨", retry: "다시 시도", whiteLabel: "화이트 라벨 워크스페이스", userFallback: "사용자", memberFallback: "구성원" },
  zh: { modules: "模块", contracts: "合同", security: "安全与信任", legal: "法务", modulesOutOfSync: "模块未同步", retry: "重试", whiteLabel: "白标工作区", userFallback: "用户", memberFallback: "成员" },
  ka: { modules: "მოდულები", contracts: "კონტრაქტები", security: "უსაფრთხოება და ნდობა", legal: "სამართლებრივი", modulesOutOfSync: "მოდულები არასინქრონიზებულია", retry: "ხელახლა ცდა", whiteLabel: "White-label სივრცე", userFallback: "მომხმარებელი", memberFallback: "წევრი" },
  hy: { modules: "Մոդուլներ", contracts: "Պայմանագրեր", security: "Անվտանգություն և վստահություն", legal: "Իրավական", modulesOutOfSync: "Մոդուլները համաժամեցված չեն", retry: "Կրկին փորձել", whiteLabel: "White-label աշխատատարածք", userFallback: "Օգտատեր", memberFallback: "Անդամ" },
  sw: { modules: "Moduli", contracts: "Mikataba", security: "Usalama na uaminifu", legal: "Kisheria", modulesOutOfSync: "Moduli hazijasawazishwa", retry: "Jaribu tena", whiteLabel: "Nafasi ya white-label", userFallback: "Mtumiaji", memberFallback: "Mwanachama" },
  am: { modules: "ሞጁሎች", contracts: "ውሎች", security: "ደህንነት እና እምነት", legal: "ህጋዊ", modulesOutOfSync: "ሞጁሎች አልተመሳሰሉም", retry: "እንደገና ሞክር", whiteLabel: "ነጭ-መለያ የስራ ቦታ", userFallback: "ተጠቃሚ", memberFallback: "አባል" },
  af: { modules: "Modules", contracts: "Kontrakte", security: "Sekuriteit en vertroue", legal: "Regskennisgewing", modulesOutOfSync: "Modules nie gesinkroniseer nie", retry: "Probeer weer", whiteLabel: "White-label-werkspasie", userFallback: "Gebruiker", memberFallback: "Lid" },
  ha: { modules: "Rukuni", contracts: "Kwangiloli", security: "Tsaro da amana", legal: "Shari'a", modulesOutOfSync: "Rukunai ba su daidaita ba", retry: "Sake gwadawa", whiteLabel: "Wurin aiki na white-label", userFallback: "Mai amfani", memberFallback: "Memba" },
  hi: { modules: "मॉड्यूल", contracts: "अनुबंध", security: "सुरक्षा और विश्वास", legal: "कानूनी", modulesOutOfSync: "मॉड्यूल सिंक नहीं हैं", retry: "पुनः प्रयास करें", whiteLabel: "व्हाइट-लेबल कार्यक्षेत्र", userFallback: "उपयोगकर्ता", memberFallback: "सदस्य" },
  bn: { modules: "মডিউল", contracts: "চুক্তি", security: "নিরাপত্তা ও আস্থা", legal: "আইনি", modulesOutOfSync: "মডিউল সিঙ্ক হয়নি", retry: "আবার চেষ্টা করুন", whiteLabel: "হোয়াইট-লেবেল কর্মক্ষেত্র", userFallback: "ব্যবহারকারী", memberFallback: "সদস্য" },
  ur: { modules: "ماڈیولز", contracts: "معاہدے", security: "سیکیورٹی اور اعتماد", legal: "قانونی", modulesOutOfSync: "ماڈیولز مطابقت نہیں رکھتے", retry: "دوبارہ کوشش کریں", whiteLabel: "وائٹ لیبل ورک اسپیس", userFallback: "صارف", memberFallback: "رکن" },
  ta: { modules: "தொகுதிகள்", contracts: "ஒப்பந்தங்கள்", security: "பாதுகாப்பு மற்றும் நம்பிக்கை", legal: "சட்டம்", modulesOutOfSync: "தொகுதிகள் ஒத்திசைக்கப்படவில்லை", retry: "மீண்டும் முயற்சிக்கவும்", whiteLabel: "வைட்-லேபிள் பணியிடம்", userFallback: "பயனர்", memberFallback: "உறுப்பினர்" },
  pa: { modules: "ਮਾਡਿਊਲ", contracts: "ਇਕਰਾਰਨਾਮੇ", security: "ਸੁਰੱਖਿਆ ਅਤੇ ਭਰੋਸਾ", legal: "ਕਾਨੂੰਨੀ", modulesOutOfSync: "ਮਾਡਿਊਲ ਸਿੰਕ ਨਹੀਂ ਹਨ", retry: "ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ", whiteLabel: "ਵਾਈਟ-ਲੇਬਲ ਵਰਕਸਪੇਸ", userFallback: "ਵਰਤੋਂਕਾਰ", memberFallback: "ਮੈਂਬਰ" },
  ne: { modules: "मोड्युलहरू", contracts: "सम्झौताहरू", security: "सुरक्षा र विश्वास", legal: "कानुनी", modulesOutOfSync: "मोड्युलहरू सिङ्क भएका छैनन्", retry: "पुनः प्रयास गर्नुहोस्", whiteLabel: "ह्वाइट-लेबल कार्यक्षेत्र", userFallback: "प्रयोगकर्ता", memberFallback: "सदस्य" },
  vi: { modules: "Mô-đun", contracts: "Hợp đồng", security: "Bảo mật và tin cậy", legal: "Pháp lý", modulesOutOfSync: "Mô-đun chưa đồng bộ", retry: "Thử lại", whiteLabel: "Không gian nhãn trắng", userFallback: "Người dùng", memberFallback: "Thành viên" },
  th: { modules: "โมดูล", contracts: "สัญญา", security: "ความปลอดภัยและความน่าเชื่อถือ", legal: "กฎหมาย", modulesOutOfSync: "โมดูลไม่ตรงกัน", retry: "ลองอีกครั้ง", whiteLabel: "พื้นที่ทำงานไวท์เลเบล", userFallback: "ผู้ใช้", memberFallback: "สมาชิก" },
  id: { modules: "Modul", contracts: "Kontrak", security: "Keamanan dan kepercayaan", legal: "Hukum", modulesOutOfSync: "Modul tidak sinkron", retry: "Coba lagi", whiteLabel: "Ruang kerja white-label", userFallback: "Pengguna", memberFallback: "Anggota" },
  ms: { modules: "Modul", contracts: "Kontrak", security: "Keselamatan dan kepercayaan", legal: "Undang-undang", modulesOutOfSync: "Modul tidak disegerakkan", retry: "Cuba lagi", whiteLabel: "Ruang kerja white-label", userFallback: "Pengguna", memberFallback: "Ahli" },
  tl: { modules: "Mga Module", contracts: "Mga Kontrata", security: "Seguridad at tiwala", legal: "Legal", modulesOutOfSync: "Hindi naka-sync ang mga module", retry: "Subukan muli", whiteLabel: "White-label workspace", userFallback: "Gumagamit", memberFallback: "Miyembro" },
  my: { modules: "မော်ဂျူးများ", contracts: "စာချုပ်များ", security: "လုံခြုံရေးနှင့် ယုံကြည်မှု", legal: "ဥပဒေရေးရာ", modulesOutOfSync: "မော်ဂျူးများ ထပ်တူမကျပါ", retry: "ထပ်စမ်းကြည့်ပါ", whiteLabel: "White-label လုပ်ငန်းခွင်", userFallback: "အသုံးပြုသူ", memberFallback: "အဖွဲ့ဝင်" },
  km: { modules: "ម៉ូឌុល", contracts: "កិច្ចសន្យា", security: "សុវត្ថិភាព និងទំនុកចិត្ត", legal: "ច្បាប់", modulesOutOfSync: "ម៉ូឌុលមិនទាន់ធ្វើសមកាលកម្ម", retry: "ព្យាយាមម្តងទៀត", whiteLabel: "កន្លែងការងារ white-label", userFallback: "អ្នកប្រើប្រាស់", memberFallback: "សមាជិក" },
  mn: { modules: "Модулиуд", contracts: "Гэрээнүүд", security: "Аюулгүй байдал ба итгэл", legal: "Хууль эрх зүй", modulesOutOfSync: "Модулиуд синк хийгдээгүй", retry: "Дахин оролдох", whiteLabel: "White-label ажлын талбар", userFallback: "Хэрэглэгч", memberFallback: "Гишүүн" },
};

/** Existing assistant catalog. Not a new translation. */
export const WORKSPACE_CATALOG_BACKED_KEYS = ["retry"] as const;

export function getWorkspaceChrome(locale: string): {
  copy: WorkspaceChromeCopy;
  explicit: boolean;
  catalogBackedKeys: readonly string[];
} {
  const direct = WORKSPACE_CHROME_EXPLICIT[locale as LocaleCode];
  const fallback = locale.toLowerCase().startsWith("fr") ? "fr" : "en";
  const base = direct ?? WORKSPACE_CHROME_EXPLICIT[fallback];
  return {
    copy: { ...base, retry: getApplicationCatalog(locale).assistant.retry },
    explicit: Boolean(direct),
    catalogBackedKeys: WORKSPACE_CATALOG_BACKED_KEYS,
  };
}
