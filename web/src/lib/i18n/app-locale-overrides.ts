import type { LocaleCode } from "./types";

export type AppLocaleWords = {
  dashboard: string;
  retail: string;
  crm: string;
  accounting: string;
  integrations: string;
  settings: string;
  overview: string;
  clients: string;
  appointments: string;
  activeClients: string;
  appointmentsThisMonth: string;
  revenueGenerated: string;
  newAppointment?: string;
  attendanceRate?: string;
  calendar?: {
    today: string;
    day: string;
    week: string;
    month: string;
    agenda: string;
    kanban: string;
    list: string;
    allServices: string;
    allEmployees: string;
    allStatuses: string;
    searchPlaceholder: string;
    loadingAppointments: string;
    noAppointments: string;
    previous: string;
    next: string;
  };
};

const en: AppLocaleWords = {
  dashboard: "Dashboard", retail: "Retail AI", crm: "CRM AI", accounting: "Accounting AI",
  integrations: "Integrations", settings: "Settings", overview: "Overview", clients: "Clients",
  appointments: "Appointments", activeClients: "Active clients", appointmentsThisMonth: "Appointments this month",
  revenueGenerated: "Revenue generated",
};

export const APP_LOCALE_WORDS: Record<LocaleCode, AppLocaleWords> = {
  en, "en-GB": en,
  fr: { dashboard: "Tableau de bord", retail: "Retail IA", crm: "CRM IA", accounting: "Comptabilité IA", integrations: "Intégrations", settings: "Paramètres", overview: "Aperçu", clients: "Clients", appointments: "Rendez-vous", activeClients: "Clients actifs", appointmentsThisMonth: "Rendez-vous ce mois", revenueGenerated: "Revenus générés" },
  "fr-FR": { dashboard: "Tableau de bord", retail: "Retail IA", crm: "CRM IA", accounting: "Comptabilité IA", integrations: "Intégrations", settings: "Paramètres", overview: "Aperçu", clients: "Clients", appointments: "Rendez-vous", activeClients: "Clients actifs", appointmentsThisMonth: "Rendez-vous ce mois", revenueGenerated: "Revenus générés" },
  es: { dashboard: "Panel", retail: "Retail IA", crm: "CRM IA", accounting: "Contabilidad IA", integrations: "Integraciones", settings: "Configuración", overview: "Resumen", clients: "Clientes", appointments: "Citas", activeClients: "Clientes activos", appointmentsThisMonth: "Citas este mes", revenueGenerated: "Ingresos generados" },
  pt: { dashboard: "Painel", retail: "Retail IA", crm: "CRM IA", accounting: "Contabilidade IA", integrations: "Integrações", settings: "Configurações", overview: "Visão geral", clients: "Clientes", appointments: "Agendamentos", activeClients: "Clientes ativos", appointmentsThisMonth: "Agendamentos este mês", revenueGenerated: "Receita gerada" },
  ro: {
    dashboard: "Tablou de bord", retail: "Retail AI", crm: "CRM AI", accounting: "Contabilitate AI",
    integrations: "Integrări", settings: "Setări", overview: "Prezentare", clients: "Clienți",
    appointments: "Programări", activeClients: "Clienți activi", appointmentsThisMonth: "Programări luna aceasta",
    revenueGenerated: "Venituri generate", newAppointment: "Programare nouă", attendanceRate: "Rata de prezență",
    calendar: {
      today: "Astăzi", day: "Zi", week: "Săptămână", month: "Lună", agenda: "Agendă",
      kanban: "Kanban", list: "Listă", allServices: "Toate serviciile", allEmployees: "Toți angajații",
      allStatuses: "Toate stările", searchPlaceholder: "Filtrează clientul, serviciul sau titlul...",
      loadingAppointments: "Se încarcă programările...", noAppointments: "Nicio programare",
      previous: "Anterior", next: "Următor",
    },
  },
  de: { dashboard: "Dashboard", retail: "Retail KI", crm: "CRM KI", accounting: "Buchhaltung KI", integrations: "Integrationen", settings: "Einstellungen", overview: "Übersicht", clients: "Kunden", appointments: "Termine", activeClients: "Aktive Kunden", appointmentsThisMonth: "Termine diesen Monat", revenueGenerated: "Generierter Umsatz" },
  it: { dashboard: "Dashboard", retail: "Retail IA", crm: "CRM IA", accounting: "Contabilità IA", integrations: "Integrazioni", settings: "Impostazioni", overview: "Panoramica", clients: "Clienti", appointments: "Appuntamenti", activeClients: "Clienti attivi", appointmentsThisMonth: "Appuntamenti questo mese", revenueGenerated: "Ricavi generati" },
  nl: { dashboard: "Dashboard", retail: "Retail AI", crm: "CRM AI", accounting: "Boekhouding AI", integrations: "Integraties", settings: "Instellingen", overview: "Overzicht", clients: "Klanten", appointments: "Afspraken", activeClients: "Actieve klanten", appointmentsThisMonth: "Afspraken deze maand", revenueGenerated: "Gegenereerde omzet" },
  pl: { dashboard: "Panel", retail: "Retail AI", crm: "CRM AI", accounting: "Księgowość AI", integrations: "Integracje", settings: "Ustawienia", overview: "Przegląd", clients: "Klienci", appointments: "Spotkania", activeClients: "Aktywni klienci", appointmentsThisMonth: "Spotkania w tym miesiącu", revenueGenerated: "Wygenerowany przychód" },
  ru: { dashboard: "Панель", retail: "Retail ИИ", crm: "CRM ИИ", accounting: "Бухгалтерия ИИ", integrations: "Интеграции", settings: "Настройки", overview: "Обзор", clients: "Клиенты", appointments: "Встречи", activeClients: "Активные клиенты", appointmentsThisMonth: "Встречи в этом месяце", revenueGenerated: "Полученный доход" },
  uk: { dashboard: "Панель", retail: "Retail ШІ", crm: "CRM ШІ", accounting: "Бухгалтерія ШІ", integrations: "Інтеграції", settings: "Налаштування", overview: "Огляд", clients: "Клієнти", appointments: "Зустрічі", activeClients: "Активні клієнти", appointmentsThisMonth: "Зустрічі цього місяця", revenueGenerated: "Згенерований дохід" },
  el: { dashboard: "Πίνακας", retail: "Retail AI", crm: "CRM AI", accounting: "Λογιστική AI", integrations: "Ενσωματώσεις", settings: "Ρυθμίσεις", overview: "Επισκόπηση", clients: "Πελάτες", appointments: "Ραντεβού", activeClients: "Ενεργοί πελάτες", appointmentsThisMonth: "Ραντεβού αυτόν τον μήνα", revenueGenerated: "Έσοδα" },
  sv: { dashboard: "Panel", retail: "Retail AI", crm: "CRM AI", accounting: "Bokföring AI", integrations: "Integrationer", settings: "Inställningar", overview: "Översikt", clients: "Kunder", appointments: "Möten", activeClients: "Aktiva kunder", appointmentsThisMonth: "Möten denna månad", revenueGenerated: "Genererade intäkter" },
  tr: { dashboard: "Kontrol paneli", retail: "Retail AI", crm: "CRM AI", accounting: "Muhasebe AI", integrations: "Entegrasyonlar", settings: "Ayarlar", overview: "Genel bakış", clients: "Müşteriler", appointments: "Randevular", activeClients: "Aktif müşteriler", appointmentsThisMonth: "Bu ay randevular", revenueGenerated: "Oluşturulan gelir" },
  cs: { dashboard: "Nástěnka", retail: "Retail AI", crm: "CRM AI", accounting: "Účetnictví AI", integrations: "Integrace", settings: "Nastavení", overview: "Přehled", clients: "Klienti", appointments: "Schůzky", activeClients: "Aktivní klienti", appointmentsThisMonth: "Schůzky tento měsíc", revenueGenerated: "Vygenerované příjmy" },
  ka: { dashboard: "პანელი", retail: "Retail AI", crm: "CRM AI", accounting: "ბუღალტერია AI", integrations: "ინტეგრაციები", settings: "პარამეტრები", overview: "მიმოხილვა", clients: "კლიენტები", appointments: "შეხვედრები", activeClients: "აქტიური კლიენტები", appointmentsThisMonth: "შეხვედრები ამ თვეში", revenueGenerated: "გენერირებული შემოსავალი" },
  hy: { dashboard: "Վահանակ", retail: "Retail AI", crm: "CRM AI", accounting: "Հաշվապահություն AI", integrations: "Ինտեգրումներ", settings: "Կարգավորումներ", overview: "Ակնարկ", clients: "Հաճախորդներ", appointments: "Հանդիպումներ", activeClients: "Ակտիվ հաճախորդներ", appointmentsThisMonth: "Այս ամսվա հանդիպումներ", revenueGenerated: "Ստեղծված եկամուտ" },
  ar: { dashboard: "لوحة التحكم", retail: "Retail AI", crm: "CRM AI", accounting: "المحاسبة AI", integrations: "التكاملات", settings: "الإعدادات", overview: "نظرة عامة", clients: "العملاء", appointments: "المواعيد", activeClients: "العملاء النشطون", appointmentsThisMonth: "مواعيد هذا الشهر", revenueGenerated: "الإيرادات المحققة" },
  "ar-EG": { dashboard: "لوحة التحكم", retail: "Retail AI", crm: "CRM AI", accounting: "المحاسبة AI", integrations: "التكاملات", settings: "الإعدادات", overview: "نظرة عامة", clients: "العملاء", appointments: "المواعيد", activeClients: "العملاء النشطون", appointmentsThisMonth: "مواعيد هذا الشهر", revenueGenerated: "الإيرادات المحققة" },
  he: { dashboard: "לוח בקרה", retail: "Retail AI", crm: "CRM AI", accounting: "חשבונאות AI", integrations: "אינטגרציות", settings: "הגדרות", overview: "סקירה", clients: "לקוחות", appointments: "פגישות", activeClients: "לקוחות פעילים", appointmentsThisMonth: "פגישות החודש", revenueGenerated: "הכנסות שנוצרו" },
  fa: { dashboard: "داشبورد", retail: "Retail AI", crm: "CRM AI", accounting: "حسابداری AI", integrations: "یکپارچه‌سازی‌ها", settings: "تنظیمات", overview: "نمای کلی", clients: "مشتریان", appointments: "قرارها", activeClients: "مشتریان فعال", appointmentsThisMonth: "قرارهای این ماه", revenueGenerated: "درآمد ایجادشده" },
  zh: { dashboard: "仪表板", retail: "零售 AI", crm: "CRM AI", accounting: "会计 AI", integrations: "集成", settings: "设置", overview: "概览", clients: "客户", appointments: "预约", activeClients: "活跃客户", appointmentsThisMonth: "本月预约", revenueGenerated: "已生成收入" },
  ja: { dashboard: "ダッシュボード", retail: "小売 AI", crm: "CRM AI", accounting: "会計 AI", integrations: "連携", settings: "設定", overview: "概要", clients: "顧客", appointments: "予約", activeClients: "アクティブな顧客", appointmentsThisMonth: "今月の予約", revenueGenerated: "生成収益" },
  ko: { dashboard: "대시보드", retail: "리테일 AI", crm: "CRM AI", accounting: "회계 AI", integrations: "통합", settings: "설정", overview: "개요", clients: "고객", appointments: "예약", activeClients: "활성 고객", appointmentsThisMonth: "이번 달 예약", revenueGenerated: "생성된 수익" },
  hi: { dashboard: "डैशबोर्ड", retail: "रिटेल AI", crm: "CRM AI", accounting: "लेखांकन AI", integrations: "एकीकरण", settings: "सेटिंग्स", overview: "अवलोकन", clients: "ग्राहक", appointments: "अपॉइंटमेंट", activeClients: "सक्रिय ग्राहक", appointmentsThisMonth: "इस महीने के अपॉइंटमेंट", revenueGenerated: "उत्पन्न राजस्व" },
  bn: { dashboard: "ড্যাশবোর্ড", retail: "রিটেইল AI", crm: "CRM AI", accounting: "অ্যাকাউন্টিং AI", integrations: "ইন্টিগ্রেশন", settings: "সেটিংস", overview: "ওভারভিউ", clients: "গ্রাহক", appointments: "অ্যাপয়েন্টমেন্ট", activeClients: "সক্রিয় গ্রাহক", appointmentsThisMonth: "এই মাসের অ্যাপয়েন্টমেন্ট", revenueGenerated: "উৎপন্ন আয়" },
  ur: { dashboard: "ڈیش بورڈ", retail: "ریٹیل AI", crm: "CRM AI", accounting: "اکاؤنٹنگ AI", integrations: "انضمام", settings: "ترتیبات", overview: "جائزہ", clients: "صارفین", appointments: "ملاقاتیں", activeClients: "فعال صارفین", appointmentsThisMonth: "اس ماہ کی ملاقاتیں", revenueGenerated: "پیدا شدہ آمدنی" },
  ta: { dashboard: "டாஷ்போர்டு", retail: "சில்லறை AI", crm: "CRM AI", accounting: "கணக்கியல் AI", integrations: "ஒருங்கிணைப்புகள்", settings: "அமைப்புகள்", overview: "மேலோட்டம்", clients: "வாடிக்கையாளர்கள்", appointments: "சந்திப்புகள்", activeClients: "செயலில் உள்ள வாடிக்கையாளர்கள்", appointmentsThisMonth: "இந்த மாத சந்திப்புகள்", revenueGenerated: "உருவாக்கப்பட்ட வருவாய்" },
  pa: { dashboard: "ਡੈਸ਼ਬੋਰਡ", retail: "ਰਿਟੇਲ AI", crm: "CRM AI", accounting: "ਅਕਾਊਂਟਿੰਗ AI", integrations: "ਇੰਟੀਗ੍ਰੇਸ਼ਨ", settings: "ਸੈਟਿੰਗਾਂ", overview: "ਸੰਖੇਪ", clients: "ਗਾਹਕ", appointments: "ਮੁਲਾਕਾਤਾਂ", activeClients: "ਸਰਗਰਮ ਗਾਹਕ", appointmentsThisMonth: "ਇਸ ਮਹੀਨੇ ਦੀਆਂ ਮੁਲਾਕਾਤਾਂ", revenueGenerated: "ਪੈਦਾ ਕੀਤੀ ਆਮਦਨ" },
  ne: { dashboard: "ड्यासबोर्ड", retail: "रिटेल AI", crm: "CRM AI", accounting: "लेखा AI", integrations: "एकीकरण", settings: "सेटिङहरू", overview: "अवलोकन", clients: "ग्राहकहरू", appointments: "भेटघाटहरू", activeClients: "सक्रिय ग्राहकहरू", appointmentsThisMonth: "यस महिनाका भेटघाट", revenueGenerated: "उत्पन्न आम्दानी" },
  vi: { dashboard: "Bảng điều khiển", retail: "Retail AI", crm: "CRM AI", accounting: "Kế toán AI", integrations: "Tích hợp", settings: "Cài đặt", overview: "Tổng quan", clients: "Khách hàng", appointments: "Lịch hẹn", activeClients: "Khách hàng đang hoạt động", appointmentsThisMonth: "Lịch hẹn tháng này", revenueGenerated: "Doanh thu tạo ra" },
  th: { dashboard: "แดชบอร์ด", retail: "Retail AI", crm: "CRM AI", accounting: "บัญชี AI", integrations: "การผสานรวม", settings: "การตั้งค่า", overview: "ภาพรวม", clients: "ลูกค้า", appointments: "นัดหมาย", activeClients: "ลูกค้าที่ใช้งานอยู่", appointmentsThisMonth: "นัดหมายเดือนนี้", revenueGenerated: "รายได้ที่สร้างขึ้น" },
  id: { dashboard: "Dasbor", retail: "Retail AI", crm: "CRM AI", accounting: "Akuntansi AI", integrations: "Integrasi", settings: "Pengaturan", overview: "Ringkasan", clients: "Pelanggan", appointments: "Janji temu", activeClients: "Pelanggan aktif", appointmentsThisMonth: "Janji temu bulan ini", revenueGenerated: "Pendapatan yang dihasilkan" },
  ms: { dashboard: "Papan pemuka", retail: "Retail AI", crm: "CRM AI", accounting: "Perakaunan AI", integrations: "Integrasi", settings: "Tetapan", overview: "Gambaran keseluruhan", clients: "Pelanggan", appointments: "Temujanji", activeClients: "Pelanggan aktif", appointmentsThisMonth: "Temujanji bulan ini", revenueGenerated: "Hasil dijana" },
  tl: { dashboard: "Dashboard", retail: "Retail AI", crm: "CRM AI", accounting: "Accounting AI", integrations: "Mga integrasyon", settings: "Mga setting", overview: "Pangkalahatang-ideya", clients: "Mga customer", appointments: "Mga appointment", activeClients: "Aktibong customer", appointmentsThisMonth: "Mga appointment ngayong buwan", revenueGenerated: "Nabuong kita" },
  my: { dashboard: "ဒက်ရှ်ဘုတ်", retail: "Retail AI", crm: "CRM AI", accounting: "စာရင်းကိုင် AI", integrations: "ပေါင်းစည်းမှုများ", settings: "ဆက်တင်များ", overview: "ခြုံငုံသုံးသပ်ချက်", clients: "ဖောက်သည်များ", appointments: "ချိန်းဆိုမှုများ", activeClients: "တက်ကြွသောဖောက်သည်များ", appointmentsThisMonth: "ဤလချိန်းဆိုမှုများ", revenueGenerated: "ရရှိသောဝင်ငွေ" },
  km: { dashboard: "ផ្ទាំងគ្រប់គ្រង", retail: "Retail AI", crm: "CRM AI", accounting: "គណនេយ្យ AI", integrations: "ការរួមបញ្ចូល", settings: "ការកំណត់", overview: "ទិដ្ឋភាពទូទៅ", clients: "អតិថិជន", appointments: "ការណាត់ជួប", activeClients: "អតិថិជនសកម្ម", appointmentsThisMonth: "ការណាត់ជួបខែនេះ", revenueGenerated: "ចំណូលដែលបង្កើត" },
  mn: { dashboard: "Хянах самбар", retail: "Retail AI", crm: "CRM AI", accounting: "Нягтлан бодох AI", integrations: "Интеграц", settings: "Тохиргоо", overview: "Тойм", clients: "Харилцагчид", appointments: "Уулзалтууд", activeClients: "Идэвхтэй харилцагчид", appointmentsThisMonth: "Энэ сарын уулзалтууд", revenueGenerated: "Үүсгэсэн орлого" },
  sw: { dashboard: "Dashibodi", retail: "Retail AI", crm: "CRM AI", accounting: "Uhasibu AI", integrations: "Miunganisho", settings: "Mipangilio", overview: "Muhtasari", clients: "Wateja", appointments: "Miadi", activeClients: "Wateja hai", appointmentsThisMonth: "Miadi ya mwezi huu", revenueGenerated: "Mapato yaliyotengenezwa" },
  am: { dashboard: "ዳሽቦርድ", retail: "Retail AI", crm: "CRM AI", accounting: "የሂሳብ አያያዝ AI", integrations: "ውህደቶች", settings: "ቅንብሮች", overview: "አጠቃላይ እይታ", clients: "ደንበኞች", appointments: "ቀጠሮዎች", activeClients: "ንቁ ደንበኞች", appointmentsThisMonth: "የዚህ ወር ቀጠሮዎች", revenueGenerated: "የተፈጠረ ገቢ" },
  af: { dashboard: "Kontroleskerm", retail: "Retail KI", crm: "CRM KI", accounting: "Rekeningkunde KI", integrations: "Integrasies", settings: "Instellings", overview: "Oorsig", clients: "Kliënte", appointments: "Afsprake", activeClients: "Aktiewe kliënte", appointmentsThisMonth: "Afsprake hierdie maand", revenueGenerated: "Inkomste gegenereer" },
  ha: { dashboard: "Allon sarrafawa", retail: "Retail AI", crm: "CRM AI", accounting: "Accounting AI", integrations: "Haɗe-haɗe", settings: "Saituna", overview: "Bayani", clients: "Abokan ciniki", appointments: "Alƙawura", activeClients: "Abokan ciniki masu aiki", appointmentsThisMonth: "Alƙawuran wannan watan", revenueGenerated: "Kudin shiga da aka samar" },
};

type AppCommonWords = {
  close: string;
  cancel: string;
  deletePermanently: string;
  downloadCsv: string;
  noPreview: string;
  paginationPage: string;
  dataHubSubtitle: string;
  dropFilesPrompt: string;
};

const enCommon: AppCommonWords = {
  close: "Close",
  cancel: "Cancel",
  deletePermanently: "Delete permanently",
  downloadCsv: "Download CSV",
  noPreview: "No preview is available yet.",
  paginationPage: "Page {page} of {total}",
  dataHubSubtitle: "Manage your datasets, upload files, and explore your data.",
  dropFilesPrompt: "Drop your files here, or",
};

const frCommon: AppCommonWords = {
  close: "Fermer",
  cancel: "Annuler",
  deletePermanently: "Supprimer définitivement",
  downloadCsv: "Télécharger le CSV",
  noPreview: "Aucun aperçu disponible pour le moment.",
  paginationPage: "Page {page} sur {total}",
  dataHubSubtitle: "Gérez vos jeux de données, importez des fichiers et explorez vos données.",
  dropFilesPrompt: "Déposez vos fichiers ici, ou",
};

const esCommon: AppCommonWords = {
  close: "Cerrar",
  cancel: "Cancelar",
  deletePermanently: "Eliminar permanentemente",
  downloadCsv: "Descargar CSV",
  noPreview: "Aún no hay una vista previa disponible.",
  paginationPage: "Página {page} de {total}",
  dataHubSubtitle: "Gestiona tus conjuntos de datos, importa archivos y explora tus datos.",
  dropFilesPrompt: "Suelta tus archivos aquí, o",
};

const ptCommon: AppCommonWords = {
  close: "Fechar",
  cancel: "Cancelar",
  deletePermanently: "Excluir permanentemente",
  downloadCsv: "Baixar CSV",
  noPreview: "Ainda não há uma pré-visualização disponível.",
  paginationPage: "Página {page} de {total}",
  dataHubSubtitle: "Gira os seus conjuntos de dados, importe ficheiros e explore os seus dados.",
  dropFilesPrompt: "Solte os seus ficheiros aqui, ou",
};

export const APP_COMMON_WORDS: Record<LocaleCode, AppCommonWords> = {
  en: enCommon,
  "en-GB": enCommon,
  fr: frCommon,
  "fr-FR": frCommon,
  es: esCommon,
  pt: ptCommon,
  ro: { close: "Închide", cancel: "Anulează", deletePermanently: "Șterge definitiv", downloadCsv: "Descarcă CSV", noPreview: "Nu există încă o previzualizare disponibilă.", paginationPage: "Pagina {page} din {total}", dataHubSubtitle: "Gestionează seturile de date, importă fișiere și explorează datele.", dropFilesPrompt: "Plasează fișierele aici sau" },
  de: { close: "Schließen", cancel: "Abbrechen", deletePermanently: "Endgültig löschen", downloadCsv: "CSV herunterladen", noPreview: "Noch keine Vorschau verfügbar.", paginationPage: "Seite {page} von {total}", dataHubSubtitle: "Verwalten Sie Datensätze, importieren Sie Dateien und erkunden Sie Ihre Daten.", dropFilesPrompt: "Dateien hier ablegen oder" },
  it: { close: "Chiudi", cancel: "Annulla", deletePermanently: "Elimina definitivamente", downloadCsv: "Scarica CSV", noPreview: "Nessuna anteprima disponibile al momento.", paginationPage: "Pagina {page} di {total}", dataHubSubtitle: "Gestisci i dataset, importa file ed esplora i tuoi dati.", dropFilesPrompt: "Trascina qui i file oppure" },
  nl: { close: "Sluiten", cancel: "Annuleren", deletePermanently: "Definitief verwijderen", downloadCsv: "CSV downloaden", noPreview: "Er is nog geen voorbeeld beschikbaar.", paginationPage: "Pagina {page} van {total}", dataHubSubtitle: "Beheer datasets, importeer bestanden en verken je gegevens.", dropFilesPrompt: "Sleep bestanden hierheen of" },
  pl: { close: "Zamknij", cancel: "Anuluj", deletePermanently: "Usuń trwale", downloadCsv: "Pobierz CSV", noPreview: "Podgląd jest obecnie niedostępny.", paginationPage: "Strona {page} z {total}", dataHubSubtitle: "Zarządzaj zbiorami danych, importuj pliki i przeglądaj dane.", dropFilesPrompt: "Upuść tutaj pliki lub" },
  ru: { close: "Закрыть", cancel: "Отмена", deletePermanently: "Удалить безвозвратно", downloadCsv: "Скачать CSV", noPreview: "Предварительный просмотр пока недоступен.", paginationPage: "Страница {page} из {total}", dataHubSubtitle: "Управляйте наборами данных, загружайте файлы и изучайте данные.", dropFilesPrompt: "Перетащите файлы сюда или" },
  uk: { close: "Закрити", cancel: "Скасувати", deletePermanently: "Видалити назавжди", downloadCsv: "Завантажити CSV", noPreview: "Попередній перегляд поки недоступний.", paginationPage: "Сторінка {page} з {total}", dataHubSubtitle: "Керуйте наборами даних, імпортуйте файли та переглядайте дані.", dropFilesPrompt: "Перетягніть файли сюди або" },
  el: { close: "Κλείσιμο", cancel: "Ακύρωση", deletePermanently: "Οριστική διαγραφή", downloadCsv: "Λήψη CSV", noPreview: "Δεν υπάρχει ακόμη διαθέσιμη προεπισκόπηση.", paginationPage: "Σελίδα {page} από {total}", dataHubSubtitle: "Διαχειριστείτε σύνολα δεδομένων, εισαγάγετε αρχεία και εξερευνήστε τα δεδομένα σας.", dropFilesPrompt: "Αποθέστε τα αρχεία εδώ ή" },
  sv: { close: "Stäng", cancel: "Avbryt", deletePermanently: "Ta bort permanent", downloadCsv: "Ladda ned CSV", noPreview: "Ingen förhandsvisning tillgänglig ännu.", paginationPage: "Sida {page} av {total}", dataHubSubtitle: "Hantera datamängder, importera filer och utforska dina data.", dropFilesPrompt: "Släpp dina filer här eller" },
  tr: { close: "Kapat", cancel: "İptal", deletePermanently: "Kalıcı olarak sil", downloadCsv: "CSV indir", noPreview: "Henüz önizleme yok.", paginationPage: "{total} sayfadan {page}. sayfa", dataHubSubtitle: "Veri kümelerinizi yönetin, dosyaları içe aktarın ve verilerinizi inceleyin.", dropFilesPrompt: "Dosyalarınızı buraya bırakın veya" },
  cs: { close: "Zavřít", cancel: "Zrušit", deletePermanently: "Trvale odstranit", downloadCsv: "Stáhnout CSV", noPreview: "Náhled zatím není k dispozici.", paginationPage: "Stránka {page} z {total}", dataHubSubtitle: "Spravujte datové sady, importujte soubory a prozkoumávejte svá data.", dropFilesPrompt: "Přetáhněte sem soubory nebo" },
  ka: { close: "დახურვა", cancel: "გაუქმება", deletePermanently: "სამუდამოდ წაშლა", downloadCsv: "CSV-ის ჩამოტვირთვა", noPreview: "წინასწარი გადახედვა ჯერ მიუწვდომელია.", paginationPage: "გვერდი {page} / {total}", dataHubSubtitle: "მართეთ მონაცემთა ნაკრებები, შემოიტანეთ ფაილები და დაათვალიერეთ მონაცემები.", dropFilesPrompt: "ჩამოაგდეთ ფაილები აქ ან" },
  hy: { close: "Փակել", cancel: "Չեղարկել", deletePermanently: "Մշտապես ջնջել", downloadCsv: "Ներբեռնել CSV", noPreview: "Նախադիտումն առայժմ հասանելի չէ։", paginationPage: "Էջ {page}՝ {total}-ից", dataHubSubtitle: "Կառավարեք տվյալների հավաքածուները, ներմուծեք ֆայլեր և ուսումնասիրեք տվյալները։", dropFilesPrompt: "Ֆայլերը գցեք այստեղ կամ" },
  ar: { close: "إغلاق", cancel: "إلغاء", deletePermanently: "حذف نهائي", downloadCsv: "تنزيل CSV", noPreview: "لا تتوفر معاينة حتى الآن.", paginationPage: "الصفحة {page} من {total}", dataHubSubtitle: "أدر مجموعات البيانات واستورد الملفات واستكشف بياناتك.", dropFilesPrompt: "أفلت ملفاتك هنا أو" },
  "ar-EG": { close: "إغلاق", cancel: "إلغاء", deletePermanently: "حذف نهائي", downloadCsv: "تنزيل CSV", noPreview: "مفيش معاينة متاحة لسه.", paginationPage: "الصفحة {page} من {total}", dataHubSubtitle: "أدر مجموعات البيانات واستورد الملفات واستكشف بياناتك.", dropFilesPrompt: "حط ملفاتك هنا أو" },
  he: { close: "סגירה", cancel: "ביטול", deletePermanently: "מחיקה לצמיתות", downloadCsv: "הורדת CSV", noPreview: "אין עדיין תצוגה מקדימה זמינה.", paginationPage: "עמוד {page} מתוך {total}", dataHubSubtitle: "נהלו מערכי נתונים, ייבאו קבצים ועיינו בנתונים שלכם.", dropFilesPrompt: "גררו את הקבצים לכאן או" },
  fa: { close: "بستن", cancel: "لغو", deletePermanently: "حذف دائمی", downloadCsv: "دانلود CSV", noPreview: "پیش‌نمایشی در دسترس نیست.", paginationPage: "صفحه {page} از {total}", dataHubSubtitle: "مجموعه‌داده‌ها را مدیریت کنید، فایل‌ها را وارد کنید و داده‌ها را بررسی کنید.", dropFilesPrompt: "فایل‌ها را اینجا رها کنید یا" },
  sw: { close: "Funga", cancel: "Ghairi", deletePermanently: "Futa kabisa", downloadCsv: "Pakua CSV", noPreview: "Hakuna onyesho la kukagua bado.", paginationPage: "Ukurasa {page} kati ya {total}", dataHubSubtitle: "Dhibiti seti za data, leta faili na uchunguze data zako.", dropFilesPrompt: "Dondosha faili zako hapa au" },
  am: { close: "ዝጋ", cancel: "ይቅር", deletePermanently: "በቋሚነት ሰርዝ", downloadCsv: "CSV አውርድ", noPreview: "ቅድመ እይታ እስካሁን የለም።", paginationPage: "ገጽ {page} ከ {total}", dataHubSubtitle: "የውሂብ ስብስቦችን ያስተዳድሩ፣ ፋይሎችን ያስገቡ እና ውሂብዎን ይመርምሩ።", dropFilesPrompt: "ፋይሎችዎን እዚህ ይጣሉ ወይም" },
  af: { close: "Maak toe", cancel: "Kanselleer", deletePermanently: "Permanent uitvee", downloadCsv: "Laai CSV af", noPreview: "Geen voorskou beskikbaar nie.", paginationPage: "Bladsy {page} van {total}", dataHubSubtitle: "Bestuur datastelle, voer lêers in en verken jou data.", dropFilesPrompt: "Los jou lêers hier of" },
  ha: { close: "Rufe", cancel: "Soke", deletePermanently: "Share har abada", downloadCsv: "Sauke CSV", noPreview: "Babu samfoti da ake da shi tukuna.", paginationPage: "Shafi {page} cikin {total}", dataHubSubtitle: "Sarrafa rukunin bayanai, shigo da fayiloli, sannan ka bincika bayananka.", dropFilesPrompt: "Ajiye fayilolinka a nan ko" },
  zh: { close: "关闭", cancel: "取消", deletePermanently: "永久删除", downloadCsv: "下载 CSV", noPreview: "暂无预览。", paginationPage: "第 {page} 页，共 {total} 页", dataHubSubtitle: "管理数据集、导入文件并浏览数据。", dropFilesPrompt: "将文件拖放到此处，或" },
  ja: { close: "閉じる", cancel: "キャンセル", deletePermanently: "完全に削除", downloadCsv: "CSVをダウンロード", noPreview: "プレビューはまだありません。", paginationPage: "全 {total} ページ中 {page} ページ", dataHubSubtitle: "データセットを管理し、ファイルをインポートしてデータを確認できます。", dropFilesPrompt: "ここにファイルをドロップするか" },
  ko: { close: "닫기", cancel: "취소", deletePermanently: "영구 삭제", downloadCsv: "CSV 다운로드", noPreview: "아직 미리보기가 없습니다.", paginationPage: "전체 {total}페이지 중 {page}페이지", dataHubSubtitle: "데이터 세트를 관리하고 파일을 가져와 데이터를 살펴보세요.", dropFilesPrompt: "파일을 여기에 놓거나" },
  hi: { close: "बंद करें", cancel: "रद्द करें", deletePermanently: "स्थायी रूप से हटाएँ", downloadCsv: "CSV डाउनलोड करें", noPreview: "अभी कोई पूर्वावलोकन उपलब्ध नहीं है।", paginationPage: "कुल {total} में से पृष्ठ {page}", dataHubSubtitle: "डेटासेट प्रबंधित करें, फ़ाइलें आयात करें और अपना डेटा देखें।", dropFilesPrompt: "अपनी फ़ाइलें यहाँ छोड़ें या" },
  bn: { close: "বন্ধ করুন", cancel: "বাতিল করুন", deletePermanently: "স্থায়ীভাবে মুছুন", downloadCsv: "CSV ডাউনলোড করুন", noPreview: "এখনও কোনো প্রিভিউ উপলভ্য নেই।", paginationPage: "মোট {total}টির মধ্যে পৃষ্ঠা {page}", dataHubSubtitle: "ডেটাসেট পরিচালনা করুন, ফাইল আমদানি করুন এবং আপনার ডেটা দেখুন।", dropFilesPrompt: "আপনার ফাইল এখানে ছেড়ে দিন, অথবা" },
  ur: { close: "بند کریں", cancel: "منسوخ کریں", deletePermanently: "مستقل طور پر حذف کریں", downloadCsv: "CSV ڈاؤن لوڈ کریں", noPreview: "ابھی کوئی پیش منظر دستیاب نہیں ہے۔", paginationPage: "کل {total} میں سے صفحہ {page}", dataHubSubtitle: "ڈیٹاسیٹس منظم کریں، فائلیں درآمد کریں اور اپنا ڈیٹا دیکھیں۔", dropFilesPrompt: "اپنی فائلیں یہاں چھوڑیں یا" },
  ta: { close: "மூடு", cancel: "ரத்துசெய்", deletePermanently: "நிரந்தரமாக நீக்கு", downloadCsv: "CSV பதிவிறக்கு", noPreview: "முன்னோட்டம் இன்னும் இல்லை.", paginationPage: "மொத்தம் {total} இல் பக்கம் {page}", dataHubSubtitle: "தரவுத்தொகுப்புகளை நிர்வகித்து, கோப்புகளை இறக்குமதி செய்து, தரவை ஆராயுங்கள்.", dropFilesPrompt: "கோப்புகளை இங்கே விடுங்கள் அல்லது" },
  pa: { close: "ਬੰਦ ਕਰੋ", cancel: "ਰੱਦ ਕਰੋ", deletePermanently: "ਪੱਕੇ ਤੌਰ 'ਤੇ ਮਿਟਾਓ", downloadCsv: "CSV ਡਾਊਨਲੋਡ ਕਰੋ", noPreview: "ਹਾਲੇ ਕੋਈ ਝਲਕ ਉਪਲਬਧ ਨਹੀਂ ਹੈ।", paginationPage: "ਕੁੱਲ {total} ਵਿੱਚੋਂ ਪੰਨਾ {page}", dataHubSubtitle: "ਡਾਟਾਸੈੱਟ ਸੰਭਾਲੋ, ਫ਼ਾਈਲਾਂ ਇੰਪੋਰਟ ਕਰੋ ਅਤੇ ਆਪਣਾ ਡਾਟਾ ਵੇਖੋ।", dropFilesPrompt: "ਆਪਣੀਆਂ ਫ਼ਾਈਲਾਂ ਇੱਥੇ ਛੱਡੋ ਜਾਂ" },
  ne: { close: "बन्द गर्नुहोस्", cancel: "रद्द गर्नुहोस्", deletePermanently: "स्थायी रूपमा मेटाउनुहोस्", downloadCsv: "CSV डाउनलोड गर्नुहोस्", noPreview: "अहिले पूर्वावलोकन उपलब्ध छैन।", paginationPage: "कुल {total} मध्ये पृष्ठ {page}", dataHubSubtitle: "डेटासेट व्यवस्थापन गर्नुहोस्, फाइलहरू आयात गर्नुहोस् र आफ्नो डेटा हेर्नुहोस्।", dropFilesPrompt: "फाइलहरू यहाँ छोड्नुहोस् वा" },
  vi: { close: "Đóng", cancel: "Hủy", deletePermanently: "Xóa vĩnh viễn", downloadCsv: "Tải CSV xuống", noPreview: "Chưa có bản xem trước.", paginationPage: "Trang {page} / {total}", dataHubSubtitle: "Quản lý tập dữ liệu, nhập tệp và khám phá dữ liệu của bạn.", dropFilesPrompt: "Thả tệp vào đây hoặc" },
  th: { close: "ปิด", cancel: "ยกเลิก", deletePermanently: "ลบถาวร", downloadCsv: "ดาวน์โหลด CSV", noPreview: "ยังไม่มีตัวอย่างให้ดู", paginationPage: "หน้า {page} จาก {total}", dataHubSubtitle: "จัดการชุดข้อมูล นำเข้าไฟล์ และสำรวจข้อมูลของคุณ", dropFilesPrompt: "วางไฟล์ของคุณที่นี่ หรือ" },
  id: { close: "Tutup", cancel: "Batal", deletePermanently: "Hapus permanen", downloadCsv: "Unduh CSV", noPreview: "Pratinjau belum tersedia.", paginationPage: "Halaman {page} dari {total}", dataHubSubtitle: "Kelola kumpulan data, impor file, dan jelajahi data Anda.", dropFilesPrompt: "Letakkan file Anda di sini, atau" },
  ms: { close: "Tutup", cancel: "Batal", deletePermanently: "Padam secara kekal", downloadCsv: "Muat turun CSV", noPreview: "Pratonton belum tersedia.", paginationPage: "Halaman {page} daripada {total}", dataHubSubtitle: "Urus set data, import fail dan terokai data anda.", dropFilesPrompt: "Letakkan fail anda di sini atau" },
  tl: { close: "Isara", cancel: "Kanselahin", deletePermanently: "Permanenteng tanggalin", downloadCsv: "I-download ang CSV", noPreview: "Wala pang preview na magagamit.", paginationPage: "Pahina {page} sa {total}", dataHubSubtitle: "Pamahalaan ang mga dataset, mag-import ng mga file, at tingnan ang iyong data.", dropFilesPrompt: "I-drop ang mga file dito o" },
  my: { close: "ပိတ်ရန်", cancel: "မလုပ်တော့ပါ", deletePermanently: "အပြီးတိုင် ဖျက်ရန်", downloadCsv: "CSV ဒေါင်းလုဒ်လုပ်ရန်", noPreview: "အစမ်းကြည့်ရှုမှု မရှိသေးပါ။", paginationPage: "စာမျက်နှာ {page} / {total}", dataHubSubtitle: "ဒေတာအစုများကို စီမံခန့်ခွဲပါ၊ ဖိုင်များထည့်သွင်းပါ၊ ဒေတာကို စူးစမ်းပါ။", dropFilesPrompt: "ဖိုင်များကို ဤနေရာသို့ ချထားပါ သို့မဟုတ်" },
  km: { close: "បិទ", cancel: "បោះបង់", deletePermanently: "លុបជាអចិន្ត្រៃយ៍", downloadCsv: "ទាញយក CSV", noPreview: "មិនទាន់មានការមើលជាមុនទេ។", paginationPage: "ទំព័រ {page} នៃ {total}", dataHubSubtitle: "គ្រប់គ្រងសំណុំទិន្នន័យ នាំចូលឯកសារ និងស្វែងយល់ពីទិន្នន័យរបស់អ្នក។", dropFilesPrompt: "ទម្លាក់ឯកសាររបស់អ្នកនៅទីនេះ ឬ" },
  mn: { close: "Хаах", cancel: "Цуцлах", deletePermanently: "Бүрмөсөн устгах", downloadCsv: "CSV татах", noPreview: "Урьдчилан харах боломж хараахан алга.", paginationPage: "Нийт {total}-аас {page}-р хуудас", dataHubSubtitle: "Өгөгдлийн багцаа удирдаж, файл импортлон, өгөгдлөө судлаарай.", dropFilesPrompt: "Файлаа энд чирж оруулах эсвэл" },
};

export type AppMarketingWords = {
  channel: string;
  loyalVip: string;
  repeatPurchase: string;
  churnRisk: string;
  lastPurchase60Days: string;
  abandonedCarts: string;
  reactivate: string;
  recentPurchaseIntent: string;
};

const enMarketing: AppMarketingWords = {
  channel: "Channel",
  loyalVip: "Loyal customers & VIPs",
  repeatPurchase: "Higher average basket, frequent repeat purchases",
  churnRisk: "At risk of churn",
  lastPurchase60Days: "Last purchase more than 60 days ago",
  abandonedCarts: "Abandoned carts",
  reactivate: "Reactivate",
  recentPurchaseIntent: "Recent purchase intent not completed",
};

const frMarketing: AppMarketingWords = {
  channel: "Canal",
  loyalVip: "Clients fidèles et VIP",
  repeatPurchase: "Panier moyen élevé et achats répétés",
  churnRisk: "Risque d’attrition",
  lastPurchase60Days: "Dernier achat il y a plus de 60 jours",
  abandonedCarts: "Paniers abandonnés",
  reactivate: "À réactiver",
  recentPurchaseIntent: "Intention d’achat récente non concrétisée",
};

const esMarketing: AppMarketingWords = {
  channel: "Canal",
  loyalVip: "Clientes fieles y VIP",
  repeatPurchase: "Cesta media alta y compras frecuentes",
  churnRisk: "Riesgo de abandono",
  lastPurchase60Days: "Última compra hace más de 60 días",
  abandonedCarts: "Carritos abandonados",
  reactivate: "Reactivar",
  recentPurchaseIntent: "Intención de compra reciente no completada",
};

const ptMarketing: AppMarketingWords = {
  channel: "Canal",
  loyalVip: "Clientes fiéis e VIP",
  repeatPurchase: "Cesto médio elevado e compras repetidas",
  churnRisk: "Risco de abandono",
  lastPurchase60Days: "Última compra há mais de 60 dias",
  abandonedCarts: "Carrinhos abandonados",
  reactivate: "Reativar",
  recentPurchaseIntent: "Intenção de compra recente não concretizada",
};

export const APP_MARKETING_WORDS: Record<LocaleCode, AppMarketingWords> = {
  en: enMarketing,
  "en-GB": enMarketing,
  fr: frMarketing,
  "fr-FR": frMarketing,
  es: esMarketing,
  pt: ptMarketing,
  ro: { channel: "Canal", loyalVip: "Clienți fideli și VIP", repeatPurchase: "Valoare medie ridicată și cumpărături repetate", churnRisk: "Risc de pierdere a clienților", lastPurchase60Days: "Ultima achiziție în urmă cu peste 60 de zile", abandonedCarts: "Coșuri abandonate", reactivate: "Reactivare", recentPurchaseIntent: "Intenție recentă de cumpărare nefinalizată" },
  de: { channel: "Kanal", loyalVip: "Treue Kunden und VIPs", repeatPurchase: "Hoher durchschnittlicher Warenkorb und häufige Wiederkäufe", churnRisk: "Abwanderungsrisiko", lastPurchase60Days: "Letzter Kauf vor mehr als 60 Tagen", abandonedCarts: "Abgebrochene Warenkörbe", reactivate: "Reaktivieren", recentPurchaseIntent: "Jüngste Kaufabsicht nicht abgeschlossen" },
  it: { channel: "Canale", loyalVip: "Clienti fedeli e VIP", repeatPurchase: "Valore medio elevato e acquisti ripetuti", churnRisk: "Rischio di abbandono", lastPurchase60Days: "Ultimo acquisto oltre 60 giorni fa", abandonedCarts: "Carrelli abbandonati", reactivate: "Riattivare", recentPurchaseIntent: "Intenzione di acquisto recente non completata" },
  nl: { channel: "Kanaal", loyalVip: "Trouwe klanten en VIP’s", repeatPurchase: "Hogere gemiddelde bestelwaarde en herhaalaankopen", churnRisk: "Risico op klantverlies", lastPurchase60Days: "Laatste aankoop meer dan 60 dagen geleden", abandonedCarts: "Verlaten winkelwagens", reactivate: "Opnieuw activeren", recentPurchaseIntent: "Recente koopintentie niet afgerond" },
  pl: { channel: "Kanał", loyalVip: "Lojalni klienci i VIP-y", repeatPurchase: "Wyższa średnia wartość koszyka i częste ponowne zakupy", churnRisk: "Ryzyko odejścia klienta", lastPurchase60Days: "Ostatni zakup ponad 60 dni temu", abandonedCarts: "Porzucone koszyki", reactivate: "Reaktywuj", recentPurchaseIntent: "Niezrealizowany zamiar zakupu" },
  ru: { channel: "Канал", loyalVip: "Постоянные клиенты и VIP", repeatPurchase: "Высокий средний чек и частые повторные покупки", churnRisk: "Риск оттока", lastPurchase60Days: "Последняя покупка более 60 дней назад", abandonedCarts: "Брошенные корзины", reactivate: "Вернуть клиента", recentPurchaseIntent: "Недавнее намерение купить не завершилось покупкой" },
  uk: { channel: "Канал", loyalVip: "Постійні клієнти та VIP", repeatPurchase: "Високий середній чек і часті повторні покупки", churnRisk: "Ризик відтоку", lastPurchase60Days: "Остання покупка була понад 60 днів тому", abandonedCarts: "Покинуті кошики", reactivate: "Повернути клієнта", recentPurchaseIntent: "Нещодавній намір купити не завершився покупкою" },
  el: { channel: "Κανάλι", loyalVip: "Πιστοί πελάτες και VIP", repeatPurchase: "Υψηλότερη μέση αξία καλαθιού και επαναλαμβανόμενες αγορές", churnRisk: "Κίνδυνος αποχώρησης", lastPurchase60Days: "Τελευταία αγορά πριν από περισσότερες από 60 ημέρες", abandonedCarts: "Εγκαταλελειμμένα καλάθια", reactivate: "Επαναενεργοποίηση", recentPurchaseIntent: "Πρόσφατη πρόθεση αγοράς που δεν ολοκληρώθηκε" },
  sv: { channel: "Kanal", loyalVip: "Lojala kunder och VIP-kunder", repeatPurchase: "Högre genomsnittligt ordervärde och återkommande köp", churnRisk: "Risk för kundbortfall", lastPurchase60Days: "Senaste köp för mer än 60 dagar sedan", abandonedCarts: "Övergivna kundvagnar", reactivate: "Återaktivera", recentPurchaseIntent: "Nylig köpavsikt som inte slutfördes" },
  tr: { channel: "Kanal", loyalVip: "Sadık müşteriler ve VIP’ler", repeatPurchase: "Yüksek ortalama sepet ve sık tekrarlanan alışverişler", churnRisk: "Müşteri kaybı riski", lastPurchase60Days: "Son alışverişin üzerinden 60 günden fazla geçti", abandonedCarts: "Terk edilmiş sepetler", reactivate: "Yeniden etkinleştir", recentPurchaseIntent: "Yakın tarihli satın alma niyeti tamamlanmadı" },
  cs: { channel: "Kanál", loyalVip: "Věrní zákazníci a VIP", repeatPurchase: "Vyšší průměrná hodnota košíku a opakované nákupy", churnRisk: "Riziko odchodu zákazníka", lastPurchase60Days: "Poslední nákup před více než 60 dny", abandonedCarts: "Opuštěné košíky", reactivate: "Znovu aktivovat", recentPurchaseIntent: "Nedokončený nedávný nákupní záměr" },
  ka: { channel: "არხი", loyalVip: "ლოიალური მომხმარებლები და VIP-ები", repeatPurchase: "მაღალი საშუალო კალათა და ხშირი განმეორებითი შესყიდვები", churnRisk: "მომხმარებლის დაკარგვის რისკი", lastPurchase60Days: "ბოლო შესყიდვიდან 60 დღეზე მეტი გავიდა", abandonedCarts: "მიტოვებული კალათები", reactivate: "ხელახლა გააქტიურება", recentPurchaseIntent: "ბოლო შესყიდვის განზრახვა არ დასრულებულა" },
  hy: { channel: "Ալիք", loyalVip: "Հավատարիմ հաճախորդներ և VIP-ներ", repeatPurchase: "Բարձր միջին զամբյուղ և հաճախակի կրկնվող գնումներ", churnRisk: "Հաճախորդի կորստի ռիսկ", lastPurchase60Days: "Վերջին գնումից անցել է ավելի քան 60 օր", abandonedCarts: "Լքված զամբյուղներ", reactivate: "Վերաակտիվացնել", recentPurchaseIntent: "Վերջին գնման մտադրությունը չի ավարտվել" },
  ar: { channel: "القناة", loyalVip: "العملاء الأوفياء وكبار العملاء", repeatPurchase: "متوسط سلة أعلى وعمليات شراء متكررة", churnRisk: "مخاطر فقدان العملاء", lastPurchase60Days: "مر أكثر من 60 يومًا على آخر عملية شراء", abandonedCarts: "سلال متروكة", reactivate: "إعادة التفعيل", recentPurchaseIntent: "نية شراء حديثة لم تكتمل" },
  "ar-EG": { channel: "القناة", loyalVip: "العملاء المخلصون وVIP", repeatPurchase: "متوسط سلة أعلى وشراء متكرر", churnRisk: "خطر فقدان العميل", lastPurchase60Days: "آخر شراء كان من أكتر من 60 يوم", abandonedCarts: "سلال متروكة", reactivate: "إعادة تنشيط", recentPurchaseIntent: "نية شراء قريبة ما اكتملتش" },
  he: { channel: "ערוץ", loyalVip: "לקוחות נאמנים ולקוחות VIP", repeatPurchase: "סל ממוצע גבוה ורכישות חוזרות", churnRisk: "סיכון לנטישת לקוחות", lastPurchase60Days: "הרכישה האחרונה הייתה לפני יותר מ־60 יום", abandonedCarts: "עגלות נטושות", reactivate: "הפעלה מחדש", recentPurchaseIntent: "כוונת רכישה אחרונה שלא הושלמה" },
  fa: { channel: "کانال", loyalVip: "مشتریان وفادار و ویژه", repeatPurchase: "میانگین سبد بالاتر و خریدهای تکراری", churnRisk: "ریسک ریزش مشتری", lastPurchase60Days: "بیش از ۶۰ روز از آخرین خرید گذشته است", abandonedCarts: "سبدهای رهاشده", reactivate: "فعال‌سازی دوباره", recentPurchaseIntent: "قصد خرید اخیر تکمیل نشده است" },
  sw: { channel: "Kituo", loyalVip: "Wateja waaminifu na VIP", repeatPurchase: "Wastani wa kikapu mkubwa na ununuzi wa kurudia", churnRisk: "Hatari ya kupoteza wateja", lastPurchase60Days: "Ununuzi wa mwisho ulikuwa zaidi ya siku 60 zilizopita", abandonedCarts: "Mikokoteni iliyoachwa", reactivate: "Washa tena", recentPurchaseIntent: "Nia ya hivi karibuni ya kununua haikukamilika" },
  am: { channel: "ቻናል", loyalVip: "ታማኝ ደንበኞች እና VIP", repeatPurchase: "ከፍተኛ አማካይ ጋሪ እና ተደጋጋሚ ግዢዎች", churnRisk: "የደንበኛ መጥፋት አደጋ", lastPurchase60Days: "የመጨረሻው ግዢ ከ60 ቀናት በፊት ነበር", abandonedCarts: "የተተዉ ጋሪዎች", reactivate: "እንደገና አንቃ", recentPurchaseIntent: "የቅርብ ግዢ ፍላጎት አልተጠናቀቀም" },
  af: { channel: "Kanaal", loyalVip: "Lojale kliënte en BBP’s", repeatPurchase: "Hoër gemiddelde mandjie en herhaalde aankope", churnRisk: "Risiko vir kliënteverlies", lastPurchase60Days: "Laaste aankoop was meer as 60 dae gelede", abandonedCarts: "Verlate mandjies", reactivate: "Heraktiveer", recentPurchaseIntent: "Onlangse koopvoorneme nie voltooi nie" },
  ha: { channel: "Tashar sadarwa", loyalVip: "Amintattun kwastomomi da VIP", repeatPurchase: "Babban matsakaicin kwando da yawan saye-saye", churnRisk: "Haɗarin rasa kwastoma", lastPurchase60Days: "Sayen ƙarshe ya wuce kwanaki 60", abandonedCarts: "Kwandunan da aka bari", reactivate: "Sake kunna", recentPurchaseIntent: "Niyyar saye ta baya-bayan nan ba ta kammala ba" },
  zh: { channel: "渠道", loyalVip: "忠诚客户和 VIP 客户", repeatPurchase: "较高的平均客单价和频繁复购", churnRisk: "客户流失风险", lastPurchase60Days: "上次购买距今超过 60 天", abandonedCarts: "已弃置购物车", reactivate: "重新激活", recentPurchaseIntent: "近期购买意向未完成" },
  ja: { channel: "チャネル", loyalVip: "ロイヤル顧客と VIP 顧客", repeatPurchase: "平均購入額が高く、リピート購入が多い", churnRisk: "顧客離脱リスク", lastPurchase60Days: "最終購入から60日以上経過", abandonedCarts: "放棄されたカート", reactivate: "再アクティブ化", recentPurchaseIntent: "最近の購入意向が未完了" },
  ko: { channel: "채널", loyalVip: "충성 고객 및 VIP 고객", repeatPurchase: "높은 평균 주문 금액과 잦은 재구매", churnRisk: "고객 이탈 위험", lastPurchase60Days: "마지막 구매 후 60일 이상 경과", abandonedCarts: "버려진 장바구니", reactivate: "재활성화", recentPurchaseIntent: "최근 구매 의사가 완료되지 않음" },
  hi: { channel: "चैनल", loyalVip: "वफ़ादार ग्राहक और VIP", repeatPurchase: "अधिक औसत टोकरी और बार-बार खरीदारी", churnRisk: "ग्राहक छोड़ने का जोखिम", lastPurchase60Days: "पिछली खरीदारी को 60 दिनों से अधिक हो गए", abandonedCarts: "छोड़ी गई टोकरी", reactivate: "फिर सक्रिय करें", recentPurchaseIntent: "हाल की खरीदारी की मंशा पूरी नहीं हुई" },
  bn: { channel: "চ্যানেল", loyalVip: "অনুগত গ্রাহক ও VIP", repeatPurchase: "উচ্চ গড় ঝুড়ি এবং ঘন ঘন পুনঃক্রয়", churnRisk: "গ্রাহক হারানোর ঝুঁকি", lastPurchase60Days: "সর্বশেষ কেনাকাটা ৬০ দিনেরও বেশি আগে", abandonedCarts: "পরিত্যক্ত কার্ট", reactivate: "আবার সক্রিয় করুন", recentPurchaseIntent: "সাম্প্রতিক কেনার ইচ্ছা সম্পন্ন হয়নি" },
  ur: { channel: "چینل", loyalVip: "وفادار صارفین اور VIP", repeatPurchase: "زیادہ اوسط ٹوکری اور بار بار خریداری", churnRisk: "صارف کے جانے کا خطرہ", lastPurchase60Days: "آخری خریداری کو 60 دن سے زیادہ ہو گئے", abandonedCarts: "چھوڑی گئی ٹرالیاں", reactivate: "دوبارہ فعال کریں", recentPurchaseIntent: "حالیہ خریداری کا ارادہ مکمل نہیں ہوا" },
  ta: { channel: "சேனல்", loyalVip: "விசுவாசமான வாடிக்கையாளர்கள் மற்றும் VIP", repeatPurchase: "அதிக சராசரி கூடை மற்றும் மீண்டும் மீண்டும் கொள்முதல்", churnRisk: "வாடிக்கையாளர் விலகல் அபாயம்", lastPurchase60Days: "கடைசி கொள்முதல் 60 நாட்களுக்கு முன்பு", abandonedCarts: "கைவிடப்பட்ட கூடைகள்", reactivate: "மீண்டும் செயல்படுத்து", recentPurchaseIntent: "சமீபத்திய கொள்முதல் நோக்கம் நிறைவேறவில்லை" },
  pa: { channel: "ਚੈਨਲ", loyalVip: "ਵਫ਼ਾਦਾਰ ਗਾਹਕ ਅਤੇ VIP", repeatPurchase: "ਉੱਚੀ ਔਸਤ ਟੋਕਰੀ ਅਤੇ ਵਾਰ-ਵਾਰ ਖਰੀਦ", churnRisk: "ਗਾਹਕ ਗੁਆਉਣ ਦਾ ਜੋਖਮ", lastPurchase60Days: "ਆਖਰੀ ਖਰੀਦ ਨੂੰ 60 ਦਿਨ ਤੋਂ ਵੱਧ ਹੋ ਗਏ", abandonedCarts: "ਛੱਡੀਆਂ ਟੋਕਰੀਆਂ", reactivate: "ਮੁੜ ਸਰਗਰਮ ਕਰੋ", recentPurchaseIntent: "ਹਾਲੀਆ ਖਰੀਦ ਦਾ ਇਰਾਦਾ ਪੂਰਾ ਨਹੀਂ ਹੋਇਆ" },
  ne: { channel: "च्यानल", loyalVip: "निष्ठावान ग्राहक र VIP", repeatPurchase: "उच्च औसत टोकरी र बारम्बार पुनः खरिद", churnRisk: "ग्राहक गुमाउने जोखिम", lastPurchase60Days: "अन्तिम खरिद भएको ६० दिनभन्दा बढी भयो", abandonedCarts: "छोडिएका कार्टहरू", reactivate: "पुनः सक्रिय गर्नुहोस्", recentPurchaseIntent: "हालैको खरिद गर्ने इच्छा पूरा भएन" },
  vi: { channel: "Kênh", loyalVip: "Khách hàng trung thành và VIP", repeatPurchase: "Giá trị giỏ hàng trung bình cao và mua lại thường xuyên", churnRisk: "Nguy cơ khách hàng rời bỏ", lastPurchase60Days: "Lần mua gần nhất cách đây hơn 60 ngày", abandonedCarts: "Giỏ hàng bị bỏ quên", reactivate: "Kích hoạt lại", recentPurchaseIntent: "Ý định mua gần đây chưa hoàn tất" },
  th: { channel: "ช่องทาง", loyalVip: "ลูกค้าประจำและ VIP", repeatPurchase: "มูลค่าตะกร้าเฉลี่ยสูงและซื้อซ้ำบ่อย", churnRisk: "ความเสี่ยงที่ลูกค้าจะเลิกใช้บริการ", lastPurchase60Days: "ซื้อครั้งล่าสุดเมื่อกว่า 60 วันที่แล้ว", abandonedCarts: "ตะกร้าสินค้าที่ถูกทิ้ง", reactivate: "ดึงกลับมาใช้งาน", recentPurchaseIntent: "ความตั้งใจซื้อเมื่อเร็ว ๆ นี้ยังไม่สำเร็จ" },
  id: { channel: "Saluran", loyalVip: "Pelanggan setia dan VIP", repeatPurchase: "Nilai keranjang rata-rata tinggi dan sering membeli kembali", churnRisk: "Risiko pelanggan berhenti", lastPurchase60Days: "Pembelian terakhir lebih dari 60 hari lalu", abandonedCarts: "Keranjang yang ditinggalkan", reactivate: "Aktifkan kembali", recentPurchaseIntent: "Niat membeli baru-baru ini belum terwujud" },
  ms: { channel: "Saluran", loyalVip: "Pelanggan setia dan VIP", repeatPurchase: "Nilai bakul purata tinggi dan pembelian berulang", churnRisk: "Risiko pelanggan berhenti", lastPurchase60Days: "Pembelian terakhir lebih 60 hari lalu", abandonedCarts: "Bakul yang ditinggalkan", reactivate: "Aktifkan semula", recentPurchaseIntent: "Niat pembelian terkini belum diselesaikan" },
  tl: { channel: "Channel", loyalVip: "Matatapat na customer at VIP", repeatPurchase: "Mas mataas na average basket at madalas na muling pagbili", churnRisk: "Panganib na mawala ang customer", lastPurchase60Days: "Mahigit 60 araw na mula nang huling bumili", abandonedCarts: "Mga inabandonang cart", reactivate: "Muling i-activate", recentPurchaseIntent: "Hindi natuloy ang kamakailang intensiyong bumili" },
  my: { channel: "ချန်နယ်", loyalVip: "သစ္စာရှိဖောက်သည်များနှင့် VIP", repeatPurchase: "ပျမ်းမျှခြင်းတောင်းတန်ဖိုးမြင့်ပြီး ထပ်ခါတလဲလဲ ဝယ်ယူမှုများ", churnRisk: "ဖောက်သည်ဆုံးရှုံးနိုင်ခြေ", lastPurchase60Days: "နောက်ဆုံးဝယ်ယူမှုသည် ရက် ၆၀ ကျော်က ဖြစ်သည်", abandonedCarts: "စွန့်ပစ်ထားသော ဈေးခြင်းများ", reactivate: "ပြန်လည်အသက်သွင်းရန်", recentPurchaseIntent: "မကြာသေးမီက ဝယ်ယူလိုသည့်ဆန္ဒ မပြီးမြောက်ခဲ့ပါ" },
  km: { channel: "ប៉ុស្តិ៍", loyalVip: "អតិថិជនស្មោះត្រង់ និង VIP", repeatPurchase: "តម្លៃកន្ត្រកមធ្យមខ្ពស់ និងការទិញម្ដងទៀតញឹកញាប់", churnRisk: "ហានិភ័យបាត់បង់អតិថិជន", lastPurchase60Days: "ការទិញចុងក្រោយលើសពី ៦០ ថ្ងៃមុន", abandonedCarts: "កន្ត្រកដែលបានបោះបង់", reactivate: "ធ្វើឱ្យសកម្មឡើងវិញ", recentPurchaseIntent: "បំណងទិញថ្មីៗនេះមិនទាន់បានបញ្ចប់" },
  mn: { channel: "Суваг", loyalVip: "Үнэнч харилцагчид болон VIP", repeatPurchase: "Дундаж сагсны дүн өндөр, давтан худалдан авалт их", churnRisk: "Харилцагч алдах эрсдэл", lastPurchase60Days: "Сүүлийн худалдан авалтаас 60-аас дээш хоног өнгөрсөн", abandonedCarts: "Орхигдсон сагс", reactivate: "Дахин идэвхжүүлэх", recentPurchaseIntent: "Саяхны худалдан авах санаа хэрэгжээгүй" },
};

export type AppMarketingExtraWords = {
  estimatedRoi: string;
  topPercent: string;
};

export const APP_MARKETING_EXTRA_WORDS: Record<LocaleCode, AppMarketingExtraWords> = {
  en: { estimatedRoi: "Estimated ROI", topPercent: "Top {percent}" },
  "en-GB": { estimatedRoi: "Estimated ROI", topPercent: "Top {percent}" },
  fr: { estimatedRoi: "ROI estimé", topPercent: "Meilleurs {percent}" },
  "fr-FR": { estimatedRoi: "ROI estimé", topPercent: "Meilleurs {percent}" },
  es: { estimatedRoi: "ROI estimado", topPercent: "Mejores {percent}" },
  pt: { estimatedRoi: "ROI estimado", topPercent: "Principais {percent}" },
  ro: { estimatedRoi: "Rentabilitate estimată", topPercent: "Top {percent}" },
  de: { estimatedRoi: "Geschätzter ROI", topPercent: "Top {percent}" },
  it: { estimatedRoi: "ROI stimato", topPercent: "Migliori {percent}" },
  nl: { estimatedRoi: "Geschatte ROI", topPercent: "Top {percent}" },
  pl: { estimatedRoi: "Szacowany ROI", topPercent: "Najlepsze {percent}" },
  ru: { estimatedRoi: "Оценочный ROI", topPercent: "Лучшие {percent}" },
  uk: { estimatedRoi: "Орієнтовний ROI", topPercent: "Найкращі {percent}" },
  el: { estimatedRoi: "Εκτιμώμενο ROI", topPercent: "Κορυφαία {percent}" },
  sv: { estimatedRoi: "Uppskattad ROI", topPercent: "Bästa {percent}" },
  tr: { estimatedRoi: "Tahmini yatırım getirisi", topPercent: "En iyi {percent}" },
  cs: { estimatedRoi: "Odhadovaná návratnost investic", topPercent: "Nejlepších {percent}" },
  ka: { estimatedRoi: "სავარაუდო უკუგება", topPercent: "საუკეთესო {percent}" },
  hy: { estimatedRoi: "Գնահատված ROI", topPercent: "Լավագույն {percent}" },
  ar: { estimatedRoi: "العائد المتوقع", topPercent: "أفضل {percent}" },
  "ar-EG": { estimatedRoi: "العائد المتوقع", topPercent: "أفضل {percent}" },
  he: { estimatedRoi: "החזר השקעה משוער", topPercent: "המובילים {percent}" },
  fa: { estimatedRoi: "بازده تخمینی سرمایه‌گذاری", topPercent: "برترها {percent}" },
  sw: { estimatedRoi: "Faida inayokadiriwa", topPercent: "Bora {percent}" },
  am: { estimatedRoi: "የተገመተ ROI", topPercent: "ከፍተኛ {percent}" },
  af: { estimatedRoi: "Geskatte opbrengs", topPercent: "Top {percent}" },
  ha: { estimatedRoi: "Ribar da aka kiyasta", topPercent: "Manyan {percent}" },
  zh: { estimatedRoi: "预计投资回报率", topPercent: "排名前 {percent}" },
  ja: { estimatedRoi: "推定投資収益率", topPercent: "上位 {percent}" },
  ko: { estimatedRoi: "예상 투자 수익률", topPercent: "상위 {percent}" },
  hi: { estimatedRoi: "अनुमानित ROI", topPercent: "शीर्ष {percent}" },
  bn: { estimatedRoi: "আনুমানিক ROI", topPercent: "শীর্ষ {percent}" },
  ur: { estimatedRoi: "متوقع منافع", topPercent: "سرفہرست {percent}" },
  ta: { estimatedRoi: "மதிப்பிடப்பட்ட ROI", topPercent: "சிறந்த {percent}" },
  pa: { estimatedRoi: "ਅਨੁਮਾਨਿਤ ROI", topPercent: "ਸਿਖਰਲੇ {percent}" },
  ne: { estimatedRoi: "अनुमानित ROI", topPercent: "शीर्ष {percent}" },
  vi: { estimatedRoi: "ROI ước tính", topPercent: "Nhóm đầu {percent}" },
  th: { estimatedRoi: "ROI โดยประมาณ", topPercent: "อันดับต้น {percent}" },
  id: { estimatedRoi: "ROI perkiraan", topPercent: "Teratas {percent}" },
  ms: { estimatedRoi: "ROI anggaran", topPercent: "Teratas {percent}" },
  tl: { estimatedRoi: "Tinatayang ROI", topPercent: "Nangungunang {percent}" },
  my: { estimatedRoi: "ခန့်မှန်း ROI", topPercent: "ထိပ်တန်း {percent}" },
  km: { estimatedRoi: "ROI ប៉ាន់ស្មាន", topPercent: "កំពូល {percent}" },
  mn: { estimatedRoi: "Тооцоолсон ROI", topPercent: "Тэргүүлэх {percent}" },
};

export const APP_INVOICES_ISSUED: Record<LocaleCode, string> = {
  en: "Invoices issued: {count}",
  "en-GB": "Invoices issued: {count}",
  fr: "Factures émises : {count}",
  "fr-FR": "Factures émises : {count}",
  es: "Facturas emitidas: {count}",
  pt: "Faturas emitidas: {count}",
  ro: "Facturi emise: {count}",
  de: "Ausgestellte Rechnungen: {count}",
  it: "Fatture emesse: {count}",
  nl: "Uitgegeven facturen: {count}",
  pl: "Wystawione faktury: {count}",
  ru: "Выставленные счета: {count}",
  uk: "Виставлені рахунки: {count}",
  el: "Εκδοθέντα τιμολόγια: {count}",
  sv: "Utfärdade fakturor: {count}",
  tr: "Düzenlenen faturalar: {count}",
  cs: "Vystavené faktury: {count}",
  ka: "გამოწერილი ინვოისები: {count}",
  hy: "Դուրս գրված հաշիվներ․ {count}",
  ar: "الفواتير الصادرة: {count}",
  "ar-EG": "الفواتير الصادرة: {count}",
  he: "חשבוניות שהונפקו: {count}",
  fa: "فاکتورهای صادرشده: {count}",
  sw: "Ankara zilizotolewa: {count}",
  am: "የተላኩ ደረሰኞች፦ {count}",
  af: "Fakture uitgereik: {count}",
  ha: "Rasitan da aka bayar: {count}",
  zh: "已开具发票：{count}",
  ja: "発行済み請求書：{count}",
  ko: "발행된 청구서: {count}",
  hi: "जारी किए गए चालान: {count}",
  bn: "ইস্যু করা চালান: {count}",
  ur: "جاری کردہ رسیدیں: {count}",
  ta: "வழங்கப்பட்ட விலைப்பட்டியல்கள்: {count}",
  pa: "ਜਾਰੀ ਕੀਤੇ ਚਲਾਨ: {count}",
  ne: "जारी गरिएका बीजक: {count}",
  vi: "Hóa đơn đã phát hành: {count}",
  th: "ใบแจ้งหนี้ที่ออกแล้ว: {count}",
  id: "Faktur diterbitkan: {count}",
  ms: "Invois dikeluarkan: {count}",
  tl: "Mga inilabas na invoice: {count}",
  my: "ထုတ်ပေးထားသော ငွေတောင်းခံလွှာများ - {count}",
  km: "វិក្កយបត្រដែលបានចេញ៖ {count}",
  mn: "Гаргасан нэхэмжлэх: {count}",
};

export type AppRetailWords = {
  inventoryCount: string;
  unit: string;
  stock: string;
  safetyThreshold: string;
  reorderTitle: string;
  reorderDescription: string;
};

export const APP_RETAIL_WORDS: Record<LocaleCode, AppRetailWords> = {
  en: { inventoryCount: "{count} inventory items", unit: "units", stock: "Stock", safetyThreshold: "Safety threshold", reorderTitle: "Automated restocking recommended", reorderDescription: "To maintain a service level above 98%, place a supplier order when stock reaches 15 units." },
  "en-GB": { inventoryCount: "{count} inventory items", unit: "units", stock: "Stock", safetyThreshold: "Safety threshold", reorderTitle: "Automated restocking recommended", reorderDescription: "To maintain a service level above 98%, place a supplier order when stock reaches 15 units." },
  fr: { inventoryCount: "{count} articles en inventaire", unit: "unités", stock: "Stock", safetyThreshold: "Seuil de sécurité", reorderTitle: "Réapprovisionnement automatisé recommandé", reorderDescription: "Pour maintenir un taux de service supérieur à 98 %, passez une commande fournisseur lorsque le stock atteint 15 unités." },
  "fr-FR": { inventoryCount: "{count} articles en stock", unit: "unités", stock: "Stock", safetyThreshold: "Seuil de sécurité", reorderTitle: "Réapprovisionnement automatisé recommandé", reorderDescription: "Pour maintenir un taux de service supérieur à 98 %, passez une commande fournisseur lorsque le stock atteint 15 unités." },
  es: { inventoryCount: "{count} artículos en inventario", unit: "unidades", stock: "Existencias", safetyThreshold: "Umbral de seguridad", reorderTitle: "Se recomienda la reposición automática", reorderDescription: "Para mantener un nivel de servicio superior al 98 %, realiza un pedido al proveedor cuando las existencias lleguen a 15 unidades." },
  pt: { inventoryCount: "{count} artigos em inventário", unit: "unidades", stock: "Estoque", safetyThreshold: "Limite de segurança", reorderTitle: "Reposição automática recomendada", reorderDescription: "Para manter um nível de serviço acima de 98%, faça um pedido ao fornecedor quando o estoque chegar a 15 unidades." },
  ro: { inventoryCount: "{count} articole în inventar", unit: "unități", stock: "Stoc", safetyThreshold: "Prag de siguranță", reorderTitle: "Se recomandă reaprovizionarea automată", reorderDescription: "Pentru a menține un nivel de servicii de peste 98%, plasați o comandă la furnizor când stocul ajunge la 15 unități." },
  de: { inventoryCount: "{count} Lagerartikel", unit: "Einheiten", stock: "Bestand", safetyThreshold: "Sicherheitsbestand", reorderTitle: "Automatische Nachbestellung empfohlen", reorderDescription: "Um einen Servicegrad von über 98 % zu halten, bestellen Sie beim Lieferanten nach, sobald der Bestand 15 Einheiten erreicht." },
  it: { inventoryCount: "{count} articoli in inventario", unit: "unità", stock: "Scorte", safetyThreshold: "Soglia di sicurezza", reorderTitle: "Riordino automatico consigliato", reorderDescription: "Per mantenere un livello di servizio superiore al 98%, effettua un ordine al fornitore quando le scorte raggiungono 15 unità." },
  nl: { inventoryCount: "{count} voorraadartikelen", unit: "eenheden", stock: "Voorraad", safetyThreshold: "Veiligheidsdrempel", reorderTitle: "Automatisch aanvullen aanbevolen", reorderDescription: "Plaats een bestelling bij de leverancier zodra de voorraad 15 eenheden bereikt om een serviceniveau van meer dan 98% te behouden." },
  pl: { inventoryCount: "Liczba pozycji w magazynie: {count}", unit: "szt.", stock: "Stan magazynowy", safetyThreshold: "Próg bezpieczeństwa", reorderTitle: "Zalecane automatyczne uzupełnienie zapasów", reorderDescription: "Aby utrzymać poziom obsługi powyżej 98%, złóż zamówienie u dostawcy, gdy zapas osiągnie 15 sztuk." },
  ru: { inventoryCount: "Товаров в запасе: {count}", unit: "ед.", stock: "Запас", safetyThreshold: "Страховой порог", reorderTitle: "Рекомендуется автоматическое пополнение", reorderDescription: "Чтобы поддерживать уровень обслуживания выше 98%, оформите заказ поставщику, когда запас достигнет 15 единиц." },
  uk: { inventoryCount: "Товарів у запасі: {count}", unit: "од.", stock: "Запас", safetyThreshold: "Страховий поріг", reorderTitle: "Рекомендовано автоматичне поповнення", reorderDescription: "Щоб підтримувати рівень обслуговування понад 98%, замовте товар у постачальника, коли запас досягне 15 одиниць." },
  el: { inventoryCount: "{count} είδη αποθέματος", unit: "τεμάχια", stock: "Απόθεμα", safetyThreshold: "Όριο ασφαλείας", reorderTitle: "Συνιστάται αυτόματος ανεφοδιασμός", reorderDescription: "Για επίπεδο εξυπηρέτησης άνω του 98%, παραγγείλετε από τον προμηθευτή όταν το απόθεμα φτάσει τις 15 μονάδες." },
  sv: { inventoryCount: "{count} lagerartiklar", unit: "enheter", stock: "Lager", safetyThreshold: "Säkerhetsgräns", reorderTitle: "Automatisk påfyllning rekommenderas", reorderDescription: "Lägg en beställning hos leverantören när lagret når 15 enheter för att hålla servicenivån över 98 %." },
  tr: { inventoryCount: "Stok kalemi: {count}", unit: "adet", stock: "Stok", safetyThreshold: "Güvenlik eşiği", reorderTitle: "Otomatik stok yenileme önerilir", reorderDescription: "%98'in üzerinde hizmet düzeyini korumak için stok 15 birime ulaştığında tedarikçiye sipariş verin." },
  cs: { inventoryCount: "Počet skladových položek: {count}", unit: "ks", stock: "Zásoba", safetyThreshold: "Bezpečnostní limit", reorderTitle: "Doporučeno automatické doplnění zásob", reorderDescription: "Pro udržení úrovně služeb nad 98 % objednejte u dodavatele, jakmile zásoba dosáhne 15 kusů." },
  ka: { inventoryCount: "მარაგის ერთეულები: {count}", unit: "ერთეული", stock: "მარაგი", safetyThreshold: "უსაფრთხოების ზღვარი", reorderTitle: "რეკომენდებულია მარაგის ავტომატური შევსება", reorderDescription: "98%-ზე მაღალი მომსახურების დონის შესანარჩუნებლად მომწოდებელს შეუკვეთეთ, როცა მარაგი 15 ერთეულს მიაღწევს." },
  hy: { inventoryCount: "Պահեստի ապրանքներ՝ {count}", unit: "միավոր", stock: "Պաշար", safetyThreshold: "Անվտանգության շեմ", reorderTitle: "Խորհուրդ է տրվում ավտոմատ համալրում", reorderDescription: "98%-ից բարձր սպասարկման մակարդակը պահպանելու համար պատվիրեք մատակարարից, երբ պաշարը հասնի 15 միավորի։" },
  ar: { inventoryCount: "عناصر المخزون: {count}", unit: "وحدات", stock: "المخزون", safetyThreshold: "حد الأمان", reorderTitle: "يوصى بإعادة التخزين تلقائيًا", reorderDescription: "للحفاظ على مستوى خدمة أعلى من 98%، اطلب من المورد عندما يصل المخزون إلى 15 وحدة." },
  "ar-EG": { inventoryCount: "أصناف المخزون: {count}", unit: "وحدات", stock: "المخزون", safetyThreshold: "حد الأمان", reorderTitle: "يُنصح بإعادة التخزين تلقائيًا", reorderDescription: "للحفاظ على مستوى خدمة أعلى من 98%، اطلب من المورد عند وصول المخزون إلى 15 وحدة." },
  he: { inventoryCount: "פריטי מלאי: {count}", unit: "יחידות", stock: "מלאי", safetyThreshold: "סף בטיחות", reorderTitle: "מומלץ לבצע חידוש מלאי אוטומטי", reorderDescription: "כדי לשמור על רמת שירות מעל 98%, יש להזמין מהספק כשהמלאי מגיע ל-15 יחידות." },
  fa: { inventoryCount: "اقلام موجودی: {count}", unit: "واحد", stock: "موجودی", safetyThreshold: "آستانه ایمنی", reorderTitle: "شارژ خودکار موجودی توصیه می‌شود", reorderDescription: "برای حفظ سطح خدمات بالاتر از ۹۸٪، وقتی موجودی به ۱۵ واحد رسید از تأمین‌کننده سفارش دهید." },
  sw: { inventoryCount: "Bidhaa za hesabu: {count}", unit: "vipande", stock: "Hisa", safetyThreshold: "Kiwango cha usalama", reorderTitle: "Ujazaji upya wa kiotomatiki unapendekezwa", reorderDescription: "Ili kudumisha kiwango cha huduma zaidi ya 98%, agiza kutoka kwa msambazaji hisa zikifikia vipande 15." },
  am: { inventoryCount: "የክምችት እቃዎች፦ {count}", unit: "ክፍሎች", stock: "ክምችት", safetyThreshold: "የደህንነት ወሰን", reorderTitle: "ራስ-ሰር ክምችት መሙላት ይመከራል", reorderDescription: "ከ98% በላይ የአገልግሎት ደረጃ ለመጠበቅ፣ ክምችቱ 15 ክፍሎች ሲደርስ ከአቅራቢው ይዘዙ።" },
  af: { inventoryCount: "Voorraaditems: {count}", unit: "eenhede", stock: "Voorraad", safetyThreshold: "Veiligheidsdrempel", reorderTitle: "Outomatiese aanvulling word aanbeveel", reorderDescription: "Plaas 'n bestelling by die verskaffer wanneer voorraad 15 eenhede bereik om 'n diensvlak bo 98% te handhaaf." },
  ha: { inventoryCount: "Kayayyakin ajiya: {count}", unit: "raka'a", stock: "Haja", safetyThreshold: "Matsayin tsaro", reorderTitle: "Ana ba da shawarar sake cika haja ta atomatik", reorderDescription: "Don kiyaye matakin sabis sama da 98%, yi odar kaya daga mai samarwa idan haja ta kai raka'a 15." },
  zh: { inventoryCount: "库存商品：{count}", unit: "件", stock: "库存", safetyThreshold: "安全阈值", reorderTitle: "建议自动补货", reorderDescription: "为保持 98% 以上的服务水平，请在库存达到 15 件时向供应商下单。" },
  ja: { inventoryCount: "在庫商品：{count}", unit: "個", stock: "在庫", safetyThreshold: "安全在庫しきい値", reorderTitle: "自動補充を推奨", reorderDescription: "サービス水準を98%超に保つため、在庫が15個に達したら仕入先に発注してください。" },
  ko: { inventoryCount: "재고 품목: {count}", unit: "개", stock: "재고", safetyThreshold: "안전 재고 기준", reorderTitle: "자동 재고 보충 권장", reorderDescription: "서비스 수준을 98% 초과로 유지하려면 재고가 15개에 도달할 때 공급업체에 주문하세요." },
  hi: { inventoryCount: "इन्वेंट्री आइटम: {count}", unit: "इकाइयाँ", stock: "स्टॉक", safetyThreshold: "सुरक्षा सीमा", reorderTitle: "स्वचालित रीस्टॉकिंग की सलाह दी जाती है", reorderDescription: "98% से अधिक सेवा स्तर बनाए रखने के लिए, स्टॉक 15 इकाइयों तक पहुँचने पर आपूर्तिकर्ता को ऑर्डर दें।" },
  bn: { inventoryCount: "মজুত পণ্য: {count}", unit: "একক", stock: "মজুত", safetyThreshold: "নিরাপত্তা সীমা", reorderTitle: "স্বয়ংক্রিয়ভাবে মজুত পূরণের পরামর্শ", reorderDescription: "৯৮%-এর বেশি পরিষেবার স্তর বজায় রাখতে মজুত ১৫ এককে পৌঁছালে সরবরাহকারীর কাছে অর্ডার দিন।" },
  ur: { inventoryCount: "اسٹاک کی اشیا: {count}", unit: "یونٹ", stock: "اسٹاک", safetyThreshold: "حفاظتی حد", reorderTitle: "خودکار طور پر اسٹاک بھرنے کی تجویز", reorderDescription: "98% سے زیادہ سروس لیول برقرار رکھنے کے لیے، اسٹاک 15 یونٹ تک پہنچنے پر سپلائر کو آرڈر دیں۔" },
  ta: { inventoryCount: "சரக்கு பொருட்கள்: {count}", unit: "அலகுகள்", stock: "சரக்கு", safetyThreshold: "பாதுகாப்பு வரம்பு", reorderTitle: "தானியங்கி மறுநிரப்புதல் பரிந்துரைக்கப்படுகிறது", reorderDescription: "98%-க்கு மேல் சேவை நிலையைப் பராமரிக்க, சரக்கு 15 அலகுகளை அடையும்போது விநியோகஸ்தரிடம் ஆர்டர் செய்யுங்கள்." },
  pa: { inventoryCount: "ਸਟਾਕ ਦੀਆਂ ਚੀਜ਼ਾਂ: {count}", unit: "ਇਕਾਈਆਂ", stock: "ਸਟਾਕ", safetyThreshold: "ਸੁਰੱਖਿਆ ਹੱਦ", reorderTitle: "ਆਟੋਮੈਟਿਕ ਮੁੜ-ਸਟਾਕ ਦੀ ਸਿਫ਼ਾਰਸ਼", reorderDescription: "98% ਤੋਂ ਵੱਧ ਸੇਵਾ ਪੱਧਰ ਬਣਾਈ ਰੱਖਣ ਲਈ, ਸਟਾਕ 15 ਇਕਾਈਆਂ ਤੱਕ ਪਹੁੰਚਣ 'ਤੇ ਸਪਲਾਇਰ ਨੂੰ ਆਰਡਰ ਦਿਓ।" },
  ne: { inventoryCount: "मौज्दातका वस्तुहरू: {count}", unit: "एकाइ", stock: "मौज्दात", safetyThreshold: "सुरक्षा सीमा", reorderTitle: "स्वचालित रूपमा मौज्दात भर्न सिफारिस", reorderDescription: "९८% भन्दा बढी सेवा स्तर कायम राख्न मौज्दात १५ एकाइ पुगेपछि आपूर्तिकर्तालाई अर्डर गर्नुहोस्।" },
  vi: { inventoryCount: "Mặt hàng tồn kho: {count}", unit: "đơn vị", stock: "Tồn kho", safetyThreshold: "Ngưỡng an toàn", reorderTitle: "Nên tự động bổ sung hàng", reorderDescription: "Để duy trì mức dịch vụ trên 98%, hãy đặt hàng nhà cung cấp khi tồn kho đạt 15 đơn vị." },
  th: { inventoryCount: "รายการสินค้าในคลัง: {count}", unit: "หน่วย", stock: "สินค้าในคลัง", safetyThreshold: "ระดับสต็อกสำรอง", reorderTitle: "แนะนำให้เติมสินค้าอัตโนมัติ", reorderDescription: "เพื่อรักษาระดับบริการให้สูงกว่า 98% ให้สั่งซื้อจากซัพพลายเออร์เมื่อสินค้าในคลังถึง 15 หน่วย" },
  id: { inventoryCount: "Item inventaris: {count}", unit: "unit", stock: "Stok", safetyThreshold: "Ambang batas aman", reorderTitle: "Pengisian ulang otomatis disarankan", reorderDescription: "Untuk mempertahankan tingkat layanan di atas 98%, pesan dari pemasok saat stok mencapai 15 unit." },
  ms: { inventoryCount: "Item inventori: {count}", unit: "unit", stock: "Stok", safetyThreshold: "Ambang keselamatan", reorderTitle: "Pengisian semula automatik disyorkan", reorderDescription: "Untuk mengekalkan tahap perkhidmatan melebihi 98%, buat pesanan kepada pembekal apabila stok mencapai 15 unit." },
  tl: { inventoryCount: "Mga item sa imbentaryo: {count}", unit: "yunit", stock: "Imbentaryo", safetyThreshold: "Hangganan ng kaligtasan", reorderTitle: "Inirerekomenda ang awtomatikong muling pag-stock", reorderDescription: "Para mapanatili ang antas ng serbisyo na higit sa 98%, umorder sa supplier kapag umabot sa 15 yunit ang stock." },
  my: { inventoryCount: "လက်ကျန်ပစ္စည်းများ - {count}", unit: "ယူနစ်", stock: "လက်ကျန်", safetyThreshold: "ဘေးကင်းရေး သတ်မှတ်ချက်", reorderTitle: "အလိုအလျောက် ပြန်လည်ဖြည့်တင်းရန် အကြံပြုသည်", reorderDescription: "ဝန်ဆောင်မှုအဆင့် ၉၈% ကျော်ရှိစေရန် လက်ကျန် ၁၅ ယူနစ်ရောက်သောအခါ ပေးသွင်းသူထံ မှာယူပါ။" },
  km: { inventoryCount: "ទំនិញក្នុងស្តុក៖ {count}", unit: "ឯកតា", stock: "ស្តុក", safetyThreshold: "កម្រិតសុវត្ថិភាព", reorderTitle: "សូមណែនាំឱ្យបំពេញស្តុកដោយស្វ័យប្រវត្តិ", reorderDescription: "ដើម្បីរក្សាកម្រិតសេវាកម្មលើសពី 98% សូមបញ្ជាទិញពីអ្នកផ្គត់ផ្គង់នៅពេលស្តុកដល់ 15 ឯកតា។" },
  mn: { inventoryCount: "Нөөцийн бараа: {count}", unit: "ширхэг", stock: "Нөөц", safetyThreshold: "Аюулгүйн босго", reorderTitle: "Автоматаар нөөцлөхийг зөвлөж байна", reorderDescription: "Үйлчилгээний түвшнийг 98%-иас дээш байлгахын тулд нөөц 15 ширхэгт хүрэхэд нийлүүлэгчид захиалга өгнө үү." },
};