import type { LocaleCode } from "./types";

export interface VoiceHealthCopy {
  phone: string;
  calls: string;
  minutes: string;
  credits: string;
  lastActivity: string;
  freshness: string;
}

export const VOICE_HEALTH_COPY: Record<LocaleCode, VoiceHealthCopy> = {
  en: { phone: "Business number", calls: "Calls", minutes: "Minutes", credits: "AI credits", lastActivity: "Last interaction", freshness: "Data freshness" },
  "en-GB": { phone: "Business number", calls: "Calls", minutes: "Minutes", credits: "AI credits", lastActivity: "Last interaction", freshness: "Data freshness" },
  fr: { phone: "Numéro professionnel", calls: "Appels", minutes: "Minutes", credits: "Crédits IA", lastActivity: "Dernière interaction", freshness: "Fraîcheur des données" },
  "fr-FR": { phone: "Numéro professionnel", calls: "Appels", minutes: "Minutes", credits: "Crédits IA", lastActivity: "Dernière interaction", freshness: "Fraîcheur des données" },
  es: { phone: "Número profesional", calls: "Llamadas", minutes: "Minutos", credits: "Créditos de IA", lastActivity: "Última interacción", freshness: "Actualización de datos" },
  pt: { phone: "Número profissional", calls: "Chamadas", minutes: "Minutos", credits: "Créditos de IA", lastActivity: "Última interação", freshness: "Atualização dos dados" },
  ro: { phone: "Număr profesional", calls: "Apeluri", minutes: "Minute", credits: "Credite IA", lastActivity: "Ultima interacțiune", freshness: "Prospețimea datelor" },
  de: { phone: "Geschäftsnummer", calls: "Anrufe", minutes: "Minuten", credits: "KI-Guthaben", lastActivity: "Letzte Interaktion", freshness: "Datenaktualität" },
  it: { phone: "Numero aziendale", calls: "Chiamate", minutes: "Minuti", credits: "Crediti IA", lastActivity: "Ultima interazione", freshness: "Freschezza dei dati" },
  nl: { phone: "Zakelijk nummer", calls: "Oproepen", minutes: "Minuten", credits: "AI-tegoed", lastActivity: "Laatste interactie", freshness: "Actualiteit van gegevens" },
  pl: { phone: "Numer firmowy", calls: "Połączenia", minutes: "Minuty", credits: "Kredyty AI", lastActivity: "Ostatnia interakcja", freshness: "Aktualność danych" },
  ru: { phone: "Рабочий номер", calls: "Звонки", minutes: "Минуты", credits: "Кредиты ИИ", lastActivity: "Последнее взаимодействие", freshness: "Свежесть данных" },
  uk: { phone: "Робочий номер", calls: "Дзвінки", minutes: "Хвилини", credits: "Кредити ШІ", lastActivity: "Остання взаємодія", freshness: "Актуальність даних" },
  el: { phone: "Επαγγελματικός αριθμός", calls: "Κλήσεις", minutes: "Λεπτά", credits: "Μονάδες AI", lastActivity: "Τελευταία αλληλεπίδραση", freshness: "Ενημέρωση δεδομένων" },
  sv: { phone: "Företagsnummer", calls: "Samtal", minutes: "Minuter", credits: "AI-krediter", lastActivity: "Senaste interaktion", freshness: "Dataaktualitet" },
  tr: { phone: "İş numarası", calls: "Aramalar", minutes: "Dakika", credits: "Yapay zekâ kredisi", lastActivity: "Son etkileşim", freshness: "Veri güncelliği" },
  cs: { phone: "Firemní číslo", calls: "Hovory", minutes: "Minuty", credits: "Kredity AI", lastActivity: "Poslední interakce", freshness: "Aktuálnost dat" },
  ar: { phone: "رقم العمل", calls: "المكالمات", minutes: "الدقائق", credits: "أرصدة الذكاء الاصطناعي", lastActivity: "آخر تفاعل", freshness: "حداثة البيانات" },
  "ar-EG": { phone: "رقم العمل", calls: "المكالمات", minutes: "الدقائق", credits: "أرصدة الذكاء الاصطناعي", lastActivity: "آخر تفاعل", freshness: "حداثة البيانات" },
  he: { phone: "מספר עסקי", calls: "שיחות", minutes: "דקות", credits: "קרדיט AI", lastActivity: "אינטראקציה אחרונה", freshness: "עדכניות הנתונים" },
  fa: { phone: "شماره کاری", calls: "تماس‌ها", minutes: "دقیقه", credits: "اعتبار هوش مصنوعی", lastActivity: "آخرین تعامل", freshness: "تازگی داده‌ها" },
  ja: { phone: "業務用番号", calls: "通話", minutes: "分", credits: "AI クレジット", lastActivity: "最終利用", freshness: "データの鮮度" },
  ko: { phone: "업무용 번호", calls: "통화", minutes: "분", credits: "AI 크레딧", lastActivity: "마지막 상호작용", freshness: "데이터 최신성" },
  zh: { phone: "商务号码", calls: "通话", minutes: "分钟", credits: "AI 点数", lastActivity: "最近交互", freshness: "数据新鲜度" },
  ka: { phone: "ბიზნეს ნომერი", calls: "ზარები", minutes: "წუთები", credits: "AI კრედიტები", lastActivity: "ბოლო ურთიერთქმედება", freshness: "მონაცემების სიახლე" },
  hy: { phone: "Գործարար համար", calls: "Զանգեր", minutes: "Րոպեներ", credits: "AI կրեդիտներ", lastActivity: "Վերջին փոխազդեցություն", freshness: "Տվյալների թարմություն" },
  sw: { phone: "Nambari ya biashara", calls: "Simu", minutes: "Dakika", credits: "Salio la AI", lastActivity: "Mwingiliano wa mwisho", freshness: "Ufreshi wa data" },
  am: { phone: "የንግድ ስልክ ቁጥር", calls: "ጥሪዎች", minutes: "ደቂቃዎች", credits: "የAI ክሬዲቶች", lastActivity: "የመጨረሻ ግንኙነት", freshness: "የውሂብ ትኩስነት" },
  af: { phone: "Besigheidsnommer", calls: "Oproepe", minutes: "Minute", credits: "KI-krediete", lastActivity: "Laaste interaksie", freshness: "Datavarsheid" },
  ha: { phone: "Lambar kasuwanci", calls: "Kira", minutes: "Mintuna", credits: "Kiredit na AI", lastActivity: "Mu'amala ta ƙarshe", freshness: "Sabunta bayanai" },
  hi: { phone: "व्यावसायिक नंबर", calls: "कॉल", minutes: "मिनट", credits: "AI क्रेडिट", lastActivity: "अंतिम बातचीत", freshness: "डेटा की ताज़गी" },
  bn: { phone: "ব্যবসায়িক নম্বর", calls: "কল", minutes: "মিনিট", credits: "এআই ক্রেডিট", lastActivity: "সর্বশেষ যোগাযোগ", freshness: "ডেটার হালনাগাদ অবস্থা" },
  ur: { phone: "کاروباری نمبر", calls: "کالز", minutes: "منٹ", credits: "اے آئی کریڈٹس", lastActivity: "آخری تعامل", freshness: "ڈیٹا کی تازگی" },
  ta: { phone: "வணிக எண்", calls: "அழைப்புகள்", minutes: "நிமிடங்கள்", credits: "AI கிரெடிட்கள்", lastActivity: "கடைசி தொடர்பு", freshness: "தரவு புதுமை" },
  pa: { phone: "ਕਾਰੋਬਾਰੀ ਨੰਬਰ", calls: "ਕਾਲਾਂ", minutes: "ਮਿੰਟ", credits: "AI ਕ੍ਰੈਡਿਟ", lastActivity: "ਆਖਰੀ ਸੰਪਰਕ", freshness: "ਡਾਟਾ ਤਾਜ਼ਗੀ" },
  ne: { phone: "व्यावसायिक नम्बर", calls: "कलहरू", minutes: "मिनेट", credits: "AI क्रेडिट", lastActivity: "अन्तिम सम्पर्क", freshness: "डेटा ताजापन" },
  vi: { phone: "Số doanh nghiệp", calls: "Cuộc gọi", minutes: "Phút", credits: "Tín dụng AI", lastActivity: "Tương tác gần nhất", freshness: "Độ mới của dữ liệu" },
  th: { phone: "หมายเลขธุรกิจ", calls: "การโทร", minutes: "นาที", credits: "เครดิต AI", lastActivity: "การโต้ตอบล่าสุด", freshness: "ความใหม่ของข้อมูล" },
  id: { phone: "Nomor bisnis", calls: "Panggilan", minutes: "Menit", credits: "Kredit AI", lastActivity: "Interaksi terakhir", freshness: "Kesegaran data" },
  ms: { phone: "Nombor perniagaan", calls: "Panggilan", minutes: "Minit", credits: "Kredit AI", lastActivity: "Interaksi terakhir", freshness: "Kesegaran data" },
  tl: { phone: "Numero ng negosyo", calls: "Mga tawag", minutes: "Minuto", credits: "AI credits", lastActivity: "Huling interaksyon", freshness: "Pagkasariwa ng data" },
  my: { phone: "လုပ်ငန်းဖုန်းနံပါတ်", calls: "ဖုန်းခေါ်ဆိုမှုများ", minutes: "မိနစ်", credits: "AI ခရက်ဒစ်", lastActivity: "နောက်ဆုံးအပြန်အလှန်", freshness: "ဒေတာလတ်ဆတ်မှု" },
  km: { phone: "លេខអាជីវកម្ម", calls: "ការហៅ", minutes: "នាទី", credits: "ក្រេឌីត AI", lastActivity: "អន្តរកម្មចុងក្រោយ", freshness: "ភាពថ្មីនៃទិន្នន័យ" },
  mn: { phone: "Бизнес дугаар", calls: "Дуудлага", minutes: "Минут", credits: "AI кредит", lastActivity: "Сүүлийн харилцан үйлдэл", freshness: "Өгөгдлийн шинэ байдал" },
};