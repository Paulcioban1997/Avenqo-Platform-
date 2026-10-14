import type { LocaleCode } from "./types";
import { completeLocaleMap } from "./complete-locale-map";

export interface VoicePermissionsCopy {
  title: string;
  description: string;
  locked: string;
  moduleOff: string;
}

/** Canonical Voice action_code values. Display copy never replaces these enums. */
export const VOICE_PERMISSION_ACTION_CODES = [
  "read_availability",
  "list_slots",
  "create_appointment",
  "update_appointment",
  "cancel_appointment",
  "read_client_self",
  "read_crm_metrics",
  "read_sales_summary",
  "read_products",
  "read_inventory",
  "read_unpaid_invoices",
  "read_cashflow",
  "read_documents",
  "read",
  "read_business_health",
] as const;

export const VOICE_PERMISSION_MODULE_CODES = [
  "crm",
  "retail",
  "accounting",
  "ocr",
  "marketing",
  "appointments",
  "hr",
  "media",
  "legal",
  "workflow",
  "ai_agents",
  "cross_agent",
] as const;

export const VOICE_PERMISSIONS_COPY: Record<LocaleCode, VoicePermissionsCopy> = completeLocaleMap({
  en: {
    title: "Voice module permissions",
    description: "Activated modules are not Voice permissions. Grant each action explicitly. Default grants are empty.",
    locked: "locked",
    moduleOff: "module off",
  },
  "en-GB": {
    title: "Voice module permissions",
    description: "Activated modules are not Voice permissions. Grant each action explicitly. Default grants are empty.",
    locked: "locked",
    moduleOff: "module off",
  },
  fr: {
    title: "Permissions des modules Voice",
    description: "Les modules activés ne sont pas des permissions Voice. Accordez chaque action explicitement. Les droits par défaut sont vides.",
    locked: "verrouillé",
    moduleOff: "module désactivé",
  },
  "fr-FR": {
    title: "Autorisations des modules Voice",
    description: "Les modules activés ne sont pas des autorisations Voice. Accordez chaque action explicitement. Les droits par défaut sont vides.",
    locked: "verrouillé",
    moduleOff: "module désactivé",
  },
  es: {
    title: "Permisos de módulos Voice",
    description: "Los módulos activados no son permisos de Voice. Conceda cada acción de forma explícita. Los permisos predeterminados están vacíos.",
    locked: "bloqueado",
    moduleOff: "módulo desactivado",
  },
  pt: {
    title: "Permissões de módulos Voice",
    description: "Módulos ativados não são permissões Voice. Conceda cada ação explicitamente. As concessões padrão estão vazias.",
    locked: "bloqueado",
    moduleOff: "módulo desativado",
  },
  ro: {
    title: "Permisiuni module Voice",
    description: "Modulele activate nu sunt permisiuni Voice. Acordați fiecare acțiune explicit. Drepturile implicite sunt goale.",
    locked: "blocat",
    moduleOff: "modul dezactivat",
  },
  de: {
    title: "Voice-Modulberechtigungen",
    description: "Aktivierte Module sind keine Voice-Berechtigungen. Gewähren Sie jede Aktion ausdrücklich. Standardrechte sind leer.",
    locked: "gesperrt",
    moduleOff: "Modul aus",
  },
  it: {
    title: "Autorizzazioni moduli Voice",
    description: "I moduli attivati non sono autorizzazioni Voice. Concedere ogni azione in modo esplicito. I diritti predefiniti sono vuoti.",
    locked: "bloccato",
    moduleOff: "modulo disattivato",
  },
  nl: {
    title: "Voice-modulemachtigingen",
    description: "Geactiveerde modules zijn geen Voice-machtigingen. Ken elke actie expliciet toe. Standaardrechten zijn leeg.",
    locked: "vergrendeld",
    moduleOff: "module uit",
  },
  pl: {
    title: "Uprawnienia modułów Voice",
    description: "Aktywowane moduły nie są uprawnieniami Voice. Przyznaj każdą akcję wprost. Domyślne uprawnienia są puste.",
    locked: "zablokowane",
    moduleOff: "moduł wyłączony",
  },
  ru: {
    title: "Права модулей Voice",
    description: "Включённые модули не являются правами Voice. Выдавайте каждое действие явно. Права по умолчанию пусты.",
    locked: "заблокировано",
    moduleOff: "модуль выключен",
  },
  uk: {
    title: "Дозволи модулів Voice",
    description: "Увімкнені модулі не є дозволами Voice. Надавайте кожну дію явно. Типові дозволи порожні.",
    locked: "заблоковано",
    moduleOff: "модуль вимкнено",
  },
  el: {
    title: "Δικαιώματα μονάδων Voice",
    description: "Οι ενεργές μονάδες δεν είναι δικαιώματα Voice. Εκχωρήστε κάθε ενέργεια ρητά. Τα προεπιλεγμένα δικαιώματα είναι κενά.",
    locked: "κλειδωμένο",
    moduleOff: "μονάδα ανενεργή",
  },
  sv: {
    title: "Voice-modulbehörigheter",
    description: "Aktiverade moduler är inte Voice-behörigheter. Bevilja varje åtgärd uttryckligen. Standardbehörigheter är tomma.",
    locked: "låst",
    moduleOff: "modul av",
  },
  tr: {
    title: "Voice modül izinleri",
    description: "Etkinleştirilmiş modüller Voice izinleri değildir. Her eylemi açıkça verin. Varsayılan izinler boştur.",
    locked: "kilitli",
    moduleOff: "modül kapalı",
  },
  cs: {
    title: "Oprávnění modulů Voice",
    description: "Aktivované moduly nejsou oprávnění Voice. Udělte každou akci výslovně. Výchozí oprávnění jsou prázdná.",
    locked: "uzamčeno",
    moduleOff: "modul vypnut",
  },
  ar: {
    title: "أذونات وحدات Voice",
    description: "الوحدات المفعّلة ليست أذونات Voice. امنح كل إجراء صراحة. الأذونات الافتراضية فارغة.",
    locked: "مقفل",
    moduleOff: "الوحدة متوقفة",
  },
  "ar-EG": {
    title: "أذونات وحدات Voice",
    description: "الوحدات المفعّلة مش أذونات Voice. امنح كل إجراء بشكل صريح. الأذونات الافتراضية فاضية.",
    locked: "مقفل",
    moduleOff: "الوحدة متوقفة",
  },
  he: {
    title: "הרשאות מודולי Voice",
    description: "מודולים פעילים אינם הרשאות Voice. יש להעניק כל פעולה במפורש. ההרשאות כברירת מחדל ריקות.",
    locked: "נעול",
    moduleOff: "מודול כבוי",
  },
  fa: {
    title: "مجوزهای ماژول Voice",
    description: "ماژول‌های فعال‌شده مجوز Voice نیستند. هر کنش را صریحاً اعطا کنید. مجوزهای پیش‌فرض خالی هستند.",
    locked: "قفل‌شده",
    moduleOff: "ماژول خاموش",
  },
  ja: {
    title: "Voice モジュール権限",
    description: "有効なモジュールは Voice 権限ではありません。各アクションを明示的に許可してください。既定の権限は空です。",
    locked: "ロック中",
    moduleOff: "モジュールオフ",
  },
  ko: {
    title: "Voice 모듈 권한",
    description: "활성화된 모듈은 Voice 권한이 아닙니다. 각 작업을 명시적으로 허용하세요. 기본 권한은 비어 있습니다.",
    locked: "잠김",
    moduleOff: "모듈 꺼짐",
  },
  zh: {
    title: "Voice 模块权限",
    description: "已启用的模块不是 Voice 权限。请明确授予每项操作。默认授权为空。",
    locked: "已锁定",
    moduleOff: "模块关闭",
  },
  hi: {
    title: "Voice मॉड्यूल अनुमतियाँ",
    description: "सक्रिय मॉड्यूल Voice अनुमतियाँ नहीं हैं। प्रत्येक क्रिया स्पष्ट रूप से दें। डिफ़ॉल्ट अनुमतियाँ खाली हैं।",
    locked: "लॉक",
    moduleOff: "मॉड्यूल बंद",
  },
  bn: {
    title: "Voice মডিউল অনুমতি",
    description: "সক্রিয় মডিউল Voice অনুমতি নয়। প্রতিটি কাজ স্পষ্টভাবে দিন। ডিফল্ট অনুমতি খালি।",
    locked: "লক করা",
    moduleOff: "মডিউল বন্ধ",
  },
  ur: {
    title: "Voice ماڈیول اجازتیں",
    description: "فعال ماڈیولز Voice اجازتیں نہیں ہیں۔ ہر عمل واضح طور پر دیں۔ ڈیفالٹ اجازتیں خالی ہیں۔",
    locked: "مقفل",
    moduleOff: "ماڈیول بند",
  },
  ta: {
    title: "Voice தொகுதி அனுமதிகள்",
    description: "இயக்கப்பட்ட தொகுதிகள் Voice அனுமதிகள் அல்ல. ஒவ்வொரு செயலையும் தெளிவாக வழங்கவும். இயல்புநிலை அனுமதிகள் காலியாக உள்ளன.",
    locked: "பூட்டப்பட்டது",
    moduleOff: "தொகுதி அணைக்கப்பட்டது",
  },
  pa: {
    title: "Voice ਮੋਡੀਊਲ ਇਜਾਜ਼ਤਾਂ",
    description: "ਸਰਗਰਮ ਮੋਡੀਊਲ Voice ਇਜਾਜ਼ਤਾਂ ਨਹੀਂ ਹਨ। ਹਰ ਕਾਰਵਾਈ ਸਪਸ਼ਟ ਤੌਰ ਤੇ ਦਿਓ। ਡਿਫਾਲਟ ਇਜਾਜ਼ਤਾਂ ਖਾਲੀ ਹਨ।",
    locked: "ਲਾਕ",
    moduleOff: "ਮੋਡੀਊਲ ਬੰਦ",
  },
  ne: {
    title: "Voice मोड्युल अनुमतिहरू",
    description: "सक्रिय मोड्युलहरू Voice अनुमति होइनन्। प्रत्येक कार्य स्पष्ट रूपमा दिनुहोस्। पूर्वनिर्धारित अनुमतिहरू खाली छन्।",
    locked: "लक",
    moduleOff: "मोड्युल बन्द",
  },
  vi: {
    title: "Quyền mô-đun Voice",
    description: "Mô-đun đã bật không phải là quyền Voice. Cấp từng hành động một cách rõ ràng. Quyền mặc định trống.",
    locked: "đã khóa",
    moduleOff: "mô-đun tắt",
  },
  th: {
    title: "สิทธิ์โมดูล Voice",
    description: "โมดูลที่เปิดใช้ไม่ใช่สิทธิ์ Voice โปรดให้แต่ละการกระทำอย่างชัดเจน สิทธิ์เริ่มต้นว่างเปล่า",
    locked: "ถูกล็อก",
    moduleOff: "โมดูลปิด",
  },
  id: {
    title: "Izin modul Voice",
    description: "Modul yang diaktifkan bukan izin Voice. Berikan setiap tindakan secara eksplisit. Izin default kosong.",
    locked: "terkunci",
    moduleOff: "modul mati",
  },
  ms: {
    title: "Kebenaran modul Voice",
    description: "Modul yang diaktifkan bukan kebenaran Voice. Berikan setiap tindakan secara jelas. Kebenaran lalai kosong.",
    locked: "dikunci",
    moduleOff: "modul dimatikan",
  },
  tl: {
    title: "Mga permiso ng Voice module",
    description: "Ang mga naka-activate na module ay hindi permiso ng Voice. Bigyan ang bawat aksyon nang tahasan. Walang laman ang default na permiso.",
    locked: "naka-lock",
    moduleOff: "naka-off ang module",
  },
  my: {
    title: "Voice မော်ဂျူး ခွင့်ပြုချက်များ",
    description: "ဖွင့်ထားသော မော်ဂျူးများသည် Voice ခွင့်ပြုချက်များ မဟုတ်ပါ။ လုပ်ဆောင်ချက်တစ်ခုချင်းကို သီးသန့်ခွင့်ပြုပါ။ ပုံသေခွင့်ပြုချက်များ ဗလာဖြစ်သည်။",
    locked: "သော့ခတ်ထား",
    moduleOff: "မော်ဂျူးပိတ်",
  },
  km: {
    title: "សិទ្ធិម៉ូឌុល Voice",
    description: "ម៉ូឌុលដែលបានបើកមិនមែនជាសិទ្ធិ Voice ទេ។ ផ្តល់សិទ្ធិសកម្មភាពនីមួយៗឱ្យច្បាស់។ សិទ្ធិលំនាំដើមទទេ។",
    locked: "ជាប់សោ",
    moduleOff: "ម៉ូឌុលបិទ",
  },
  mn: {
    title: "Voice модулийн эрх",
    description: "Идэвхжүүлсэн модуль нь Voice эрх биш. Үйлдэл бүрийг тодорхой олгоно уу. Үндсэн эрх хоосон.",
    locked: "түгжигдсэн",
    moduleOff: "модуль унтарсан",
  },
  ka: {
    title: "Voice მოდულის უფლებები",
    description: "აქტიური მოდულები არ არის Voice უფლებები. თითოეული ქმედება მკაფიოდ მიანიჭეთ. ნაგულისხმევი უფლებები ცარიელია.",
    locked: "დაბლოკილია",
    moduleOff: "მოდული გამორთულია",
  },
  hy: {
    title: "Voice մոդուլի թույլտվություններ",
    description: "Ակտիվացված մոդուլները Voice թույլտվություններ չեն։ Յուրաքանչյուր գործողություն տվեք հստակ։ Կանխադրված թույլտվությունները դատարկ են։",
    locked: "կողպված",
    moduleOff: "մոդուլն անջատված է",
  },
  sw: {
    title: "Ruhusa za moduli za Voice",
    description: "Moduli zilizowashwa si ruhusa za Voice. Toa kila kitendo waziwazi. Ruhusa chaguomsingi ni tupu.",
    locked: "imefungwa",
    moduleOff: "moduli imezimwa",
  },
  am: {
    title: "የVoice ሞጁል ፈቃዶች",
    description: "የነቁ ሞጁሎች የVoice ፈቃዶች አይደሉም። እያንዳንዱን እርምጃ በግልጽ ይስጡ። ነባሪ ፈቃዶች ባዶ ናቸው።",
    locked: "ተቆልፏል",
    moduleOff: "ሞጁል ጠፍቷል",
  },
  af: {
    title: "Voice-moduletoestemmings",
    description: "Geaktiveerde modules is nie Voice-toestemmings nie. Ken elke aksie uitdruklik toe. Verstektoestemmings is leeg.",
    locked: "gesluit",
    moduleOff: "module af",
  },
  ha: {
    title: "Izinonin module na Voice",
    description: "Amfani da aka kunna ba izinonin Voice ba ne. Ba da kowane aiki a fili. Izinonin tsoho fanko ne.",
    locked: "a kulle",
    moduleOff: "module a kashe",
  },
});
