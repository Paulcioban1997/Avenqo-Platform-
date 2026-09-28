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
};

const enCommon: AppCommonWords = {
  close: "Close",
  cancel: "Cancel",
  deletePermanently: "Delete permanently",
  downloadCsv: "Download CSV",
  noPreview: "No preview is available yet.",
  paginationPage: "Page {page} of {total}",
};

const frCommon: AppCommonWords = {
  close: "Fermer",
  cancel: "Annuler",
  deletePermanently: "Supprimer définitivement",
  downloadCsv: "Télécharger le CSV",
  noPreview: "Aucun aperçu disponible pour le moment.",
  paginationPage: "Page {page} sur {total}",
};

const esCommon: AppCommonWords = {
  close: "Cerrar",
  cancel: "Cancelar",
  deletePermanently: "Eliminar permanentemente",
  downloadCsv: "Descargar CSV",
  noPreview: "Aún no hay una vista previa disponible.",
  paginationPage: "Página {page} de {total}",
};

const ptCommon: AppCommonWords = {
  close: "Fechar",
  cancel: "Cancelar",
  deletePermanently: "Excluir permanentemente",
  downloadCsv: "Baixar CSV",
  noPreview: "Ainda não há uma pré-visualização disponível.",
  paginationPage: "Página {page} de {total}",
};

export const APP_COMMON_WORDS: Record<LocaleCode, AppCommonWords> = {
  en: enCommon,
  "en-GB": enCommon,
  fr: frCommon,
  "fr-FR": frCommon,
  es: esCommon,
  pt: ptCommon,
  ro: { close: "Închide", cancel: "Anulează", deletePermanently: "Șterge definitiv", downloadCsv: "Descarcă CSV", noPreview: "Nu există încă o previzualizare disponibilă.", paginationPage: "Pagina {page} din {total}" },
  de: { close: "Schließen", cancel: "Abbrechen", deletePermanently: "Endgültig löschen", downloadCsv: "CSV herunterladen", noPreview: "Noch keine Vorschau verfügbar.", paginationPage: "Seite {page} von {total}" },
  it: { close: "Chiudi", cancel: "Annulla", deletePermanently: "Elimina definitivamente", downloadCsv: "Scarica CSV", noPreview: "Nessuna anteprima disponibile al momento.", paginationPage: "Pagina {page} di {total}" },
  nl: { close: "Sluiten", cancel: "Annuleren", deletePermanently: "Definitief verwijderen", downloadCsv: "CSV downloaden", noPreview: "Er is nog geen voorbeeld beschikbaar.", paginationPage: "Pagina {page} van {total}" },
  pl: { close: "Zamknij", cancel: "Anuluj", deletePermanently: "Usuń trwale", downloadCsv: "Pobierz CSV", noPreview: "Podgląd jest obecnie niedostępny.", paginationPage: "Strona {page} z {total}" },
  ru: { close: "Закрыть", cancel: "Отмена", deletePermanently: "Удалить безвозвратно", downloadCsv: "Скачать CSV", noPreview: "Предварительный просмотр пока недоступен.", paginationPage: "Страница {page} из {total}" },
  uk: { close: "Закрити", cancel: "Скасувати", deletePermanently: "Видалити назавжди", downloadCsv: "Завантажити CSV", noPreview: "Попередній перегляд поки недоступний.", paginationPage: "Сторінка {page} з {total}" },
  el: { close: "Κλείσιμο", cancel: "Ακύρωση", deletePermanently: "Οριστική διαγραφή", downloadCsv: "Λήψη CSV", noPreview: "Δεν υπάρχει ακόμη διαθέσιμη προεπισκόπηση.", paginationPage: "Σελίδα {page} από {total}" },
  sv: { close: "Stäng", cancel: "Avbryt", deletePermanently: "Ta bort permanent", downloadCsv: "Ladda ned CSV", noPreview: "Ingen förhandsvisning tillgänglig ännu.", paginationPage: "Sida {page} av {total}" },
  tr: { close: "Kapat", cancel: "İptal", deletePermanently: "Kalıcı olarak sil", downloadCsv: "CSV indir", noPreview: "Henüz önizleme yok.", paginationPage: "{total} sayfadan {page}. sayfa" },
  cs: { close: "Zavřít", cancel: "Zrušit", deletePermanently: "Trvale odstranit", downloadCsv: "Stáhnout CSV", noPreview: "Náhled zatím není k dispozici.", paginationPage: "Stránka {page} z {total}" },
  ka: { close: "დახურვა", cancel: "გაუქმება", deletePermanently: "სამუდამოდ წაშლა", downloadCsv: "CSV-ის ჩამოტვირთვა", noPreview: "წინასწარი გადახედვა ჯერ მიუწვდომელია.", paginationPage: "გვერდი {page} / {total}" },
  hy: { close: "Փակել", cancel: "Չեղարկել", deletePermanently: "Մշտապես ջնջել", downloadCsv: "Ներբեռնել CSV", noPreview: "Նախադիտումն առայժմ հասանելի չէ։", paginationPage: "Էջ {page}՝ {total}-ից" },
  ar: { close: "إغلاق", cancel: "إلغاء", deletePermanently: "حذف نهائي", downloadCsv: "تنزيل CSV", noPreview: "لا تتوفر معاينة حتى الآن.", paginationPage: "الصفحة {page} من {total}" },
  "ar-EG": { close: "إغلاق", cancel: "إلغاء", deletePermanently: "حذف نهائي", downloadCsv: "تنزيل CSV", noPreview: "مفيش معاينة متاحة لسه.", paginationPage: "الصفحة {page} من {total}" },
  he: { close: "סגירה", cancel: "ביטול", deletePermanently: "מחיקה לצמיתות", downloadCsv: "הורדת CSV", noPreview: "אין עדיין תצוגה מקדימה זמינה.", paginationPage: "עמוד {page} מתוך {total}" },
  fa: { close: "بستن", cancel: "لغو", deletePermanently: "حذف دائمی", downloadCsv: "دانلود CSV", noPreview: "پیش‌نمایشی در دسترس نیست.", paginationPage: "صفحه {page} از {total}" },
  sw: { close: "Funga", cancel: "Ghairi", deletePermanently: "Futa kabisa", downloadCsv: "Pakua CSV", noPreview: "Hakuna onyesho la kukagua bado.", paginationPage: "Ukurasa {page} kati ya {total}" },
  am: { close: "ዝጋ", cancel: "ይቅር", deletePermanently: "በቋሚነት ሰርዝ", downloadCsv: "CSV አውርድ", noPreview: "ቅድመ እይታ እስካሁን የለም።", paginationPage: "ገጽ {page} ከ {total}" },
  af: { close: "Maak toe", cancel: "Kanselleer", deletePermanently: "Permanent uitvee", downloadCsv: "Laai CSV af", noPreview: "Geen voorskou beskikbaar nie.", paginationPage: "Bladsy {page} van {total}" },
  ha: { close: "Rufe", cancel: "Soke", deletePermanently: "Share har abada", downloadCsv: "Sauke CSV", noPreview: "Babu samfoti da ake da shi tukuna.", paginationPage: "Shafi {page} cikin {total}" },
  zh: { close: "关闭", cancel: "取消", deletePermanently: "永久删除", downloadCsv: "下载 CSV", noPreview: "暂无预览。", paginationPage: "第 {page} 页，共 {total} 页" },
  ja: { close: "閉じる", cancel: "キャンセル", deletePermanently: "完全に削除", downloadCsv: "CSVをダウンロード", noPreview: "プレビューはまだありません。", paginationPage: "全 {total} ページ中 {page} ページ" },
  ko: { close: "닫기", cancel: "취소", deletePermanently: "영구 삭제", downloadCsv: "CSV 다운로드", noPreview: "아직 미리보기가 없습니다.", paginationPage: "전체 {total}페이지 중 {page}페이지" },
  hi: { close: "बंद करें", cancel: "रद्द करें", deletePermanently: "स्थायी रूप से हटाएँ", downloadCsv: "CSV डाउनलोड करें", noPreview: "अभी कोई पूर्वावलोकन उपलब्ध नहीं है।", paginationPage: "कुल {total} में से पृष्ठ {page}" },
  bn: { close: "বন্ধ করুন", cancel: "বাতিল করুন", deletePermanently: "স্থায়ীভাবে মুছুন", downloadCsv: "CSV ডাউনলোড করুন", noPreview: "এখনও কোনো প্রিভিউ উপলভ্য নেই।", paginationPage: "মোট {total}টির মধ্যে পৃষ্ঠা {page}" },
  ur: { close: "بند کریں", cancel: "منسوخ کریں", deletePermanently: "مستقل طور پر حذف کریں", downloadCsv: "CSV ڈاؤن لوڈ کریں", noPreview: "ابھی کوئی پیش منظر دستیاب نہیں ہے۔", paginationPage: "کل {total} میں سے صفحہ {page}" },
  ta: { close: "மூடு", cancel: "ரத்துசெய்", deletePermanently: "நிரந்தரமாக நீக்கு", downloadCsv: "CSV பதிவிறக்கு", noPreview: "முன்னோட்டம் இன்னும் இல்லை.", paginationPage: "மொத்தம் {total} இல் பக்கம் {page}" },
  pa: { close: "ਬੰਦ ਕਰੋ", cancel: "ਰੱਦ ਕਰੋ", deletePermanently: "ਪੱਕੇ ਤੌਰ 'ਤੇ ਮਿਟਾਓ", downloadCsv: "CSV ਡਾਊਨਲੋਡ ਕਰੋ", noPreview: "ਹਾਲੇ ਕੋਈ ਝਲਕ ਉਪਲਬਧ ਨਹੀਂ ਹੈ।", paginationPage: "ਕੁੱਲ {total} ਵਿੱਚੋਂ ਪੰਨਾ {page}" },
  ne: { close: "बन्द गर्नुहोस्", cancel: "रद्द गर्नुहोस्", deletePermanently: "स्थायी रूपमा मेटाउनुहोस्", downloadCsv: "CSV डाउनलोड गर्नुहोस्", noPreview: "अहिले पूर्वावलोकन उपलब्ध छैन।", paginationPage: "कुल {total} मध्ये पृष्ठ {page}" },
  vi: { close: "Đóng", cancel: "Hủy", deletePermanently: "Xóa vĩnh viễn", downloadCsv: "Tải CSV xuống", noPreview: "Chưa có bản xem trước.", paginationPage: "Trang {page} / {total}" },
  th: { close: "ปิด", cancel: "ยกเลิก", deletePermanently: "ลบถาวร", downloadCsv: "ดาวน์โหลด CSV", noPreview: "ยังไม่มีตัวอย่างให้ดู", paginationPage: "หน้า {page} จาก {total}" },
  id: { close: "Tutup", cancel: "Batal", deletePermanently: "Hapus permanen", downloadCsv: "Unduh CSV", noPreview: "Pratinjau belum tersedia.", paginationPage: "Halaman {page} dari {total}" },
  ms: { close: "Tutup", cancel: "Batal", deletePermanently: "Padam secara kekal", downloadCsv: "Muat turun CSV", noPreview: "Pratonton belum tersedia.", paginationPage: "Halaman {page} daripada {total}" },
  tl: { close: "Isara", cancel: "Kanselahin", deletePermanently: "Permanenteng tanggalin", downloadCsv: "I-download ang CSV", noPreview: "Wala pang preview na magagamit.", paginationPage: "Pahina {page} sa {total}" },
  my: { close: "ပိတ်ရန်", cancel: "မလုပ်တော့ပါ", deletePermanently: "အပြီးတိုင် ဖျက်ရန်", downloadCsv: "CSV ဒေါင်းလုဒ်လုပ်ရန်", noPreview: "အစမ်းကြည့်ရှုမှု မရှိသေးပါ။", paginationPage: "စာမျက်နှာ {page} / {total}" },
  km: { close: "បិទ", cancel: "បោះបង់", deletePermanently: "លុបជាអចិន្ត្រៃយ៍", downloadCsv: "ទាញយក CSV", noPreview: "មិនទាន់មានការមើលជាមុនទេ។", paginationPage: "ទំព័រ {page} នៃ {total}" },
  mn: { close: "Хаах", cancel: "Цуцлах", deletePermanently: "Бүрмөсөн устгах", downloadCsv: "CSV татах", noPreview: "Урьдчилан харах боломж хараахан алга.", paginationPage: "Нийт {total}-аас {page}-р хуудас" },
};