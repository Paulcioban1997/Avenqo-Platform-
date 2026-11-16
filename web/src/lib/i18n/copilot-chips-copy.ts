import type { LocaleCode } from "./types";
import { completeLocaleMap } from "./complete-locale-map";

export interface CopilotChipsCopy {
  analyzeSales: string;
  forecastDemand: string;
  detectAnomalies: string;
  generateReport: string;
}

export const COPILOT_CHIPS_COPY: Record<LocaleCode, CopilotChipsCopy> = completeLocaleMap({
  en: {
    analyzeSales: "Analyze sales performance",
    forecastDemand: "Forecast demand",
    detectAnomalies: "Detect anomalies",
    generateReport: "Generate report",
  },
  "en-GB": {
    analyzeSales: "Analyse sales performance",
    forecastDemand: "Forecast demand",
    detectAnomalies: "Detect anomalies",
    generateReport: "Generate report",
  },
  fr: {
    analyzeSales: "Analyser mes ventes",
    forecastDemand: "Prévoir ma demande",
    detectAnomalies: "Détecter les anomalies",
    generateReport: "Générer un rapport",
  },
  "fr-FR": {
    analyzeSales: "Analyser mes ventes",
    forecastDemand: "Prévoir ma demande",
    detectAnomalies: "Détecter les anomalies",
    generateReport: "Générer un rapport",
  },
  es: {
    analyzeSales: "Analizar mis ventas",
    forecastDemand: "Prever la demanda",
    detectAnomalies: "Detectar anomalías",
    generateReport: "Generar un informe",
  },
  pt: {
    analyzeSales: "Analisar as minhas vendas",
    forecastDemand: "Prever a procura",
    detectAnomalies: "Detetar anomalias",
    generateReport: "Gerar um relatório",
  },
  ro: {
    analyzeSales: "Analizează vânzările",
    forecastDemand: "Estimează cererea",
    detectAnomalies: "Detectează anomalii",
    generateReport: "Generează un raport",
  },
  de: {
    analyzeSales: "Verkäufe analysieren",
    forecastDemand: "Nachfrage prognostizieren",
    detectAnomalies: "Anomalien erkennen",
    generateReport: "Bericht erstellen",
  },
  it: {
    analyzeSales: "Analizza le vendite",
    forecastDemand: "Prevedi la domanda",
    detectAnomalies: "Rileva anomalie",
    generateReport: "Genera un report",
  },
  nl: {
    analyzeSales: "Verkoop analyseren",
    forecastDemand: "Vraag voorspellen",
    detectAnomalies: "Afwijkingen detecteren",
    generateReport: "Rapport genereren",
  },
  pl: {
    analyzeSales: "Analizuj sprzedaż",
    forecastDemand: "Prognozuj popyt",
    detectAnomalies: "Wykryj anomalie",
    generateReport: "Wygeneruj raport",
  },
  ru: {
    analyzeSales: "Анализ продаж",
    forecastDemand: "Прогноз спроса",
    detectAnomalies: "Найти аномалии",
    generateReport: "Сформировать отчёт",
  },
  uk: {
    analyzeSales: "Аналіз продажів",
    forecastDemand: "Прогноз попиту",
    detectAnomalies: "Знайти аномалії",
    generateReport: "Сформувати звіт",
  },
  zh: {
    analyzeSales: "分析销售表现",
    forecastDemand: "预测需求",
    detectAnomalies: "检测异常",
    generateReport: "生成报告",
  },
  ja: {
    analyzeSales: "売上を分析",
    forecastDemand: "需要を予測",
    detectAnomalies: "異常を検出",
    generateReport: "レポートを作成",
  },
  ko: {
    analyzeSales: "매출 분석",
    forecastDemand: "수요 예측",
    detectAnomalies: "이상 탐지",
    generateReport: "보고서 생성",
  },
  ar: {
    analyzeSales: "تحليل المبيعات",
    forecastDemand: "توقّع الطلب",
    detectAnomalies: "اكتشاف الحالات الشاذة",
    generateReport: "إنشاء تقرير",
  },
  "ar-EG": {
    analyzeSales: "تحليل المبيعات",
    forecastDemand: "توقّع الطلب",
    detectAnomalies: "اكتشاف الحالات الشاذة",
    generateReport: "إنشاء تقرير",
  },
  he: {
    analyzeSales: "ניתוח ביצועי מכירות",
    forecastDemand: "חיזוי ביקוש",
    detectAnomalies: "זיהוי חריגות",
    generateReport: "הפקת דוח",
  },
  fa: {
    analyzeSales: "تحلیل عملکرد فروش",
    forecastDemand: "پیش‌بینی تقاضا",
    detectAnomalies: "شناسایی ناهنجاری‌ها",
    generateReport: "تولید گزارش",
  },
  ur: {
    analyzeSales: "فروخت کی کارکردگی کا تجزیہ",
    forecastDemand: "طلب کی پیش گوئی",
    detectAnomalies: "بے ضابطگیوں کی نشاندہی",
    generateReport: "رپورٹ تیار کریں",
  },
  el: {
    analyzeSales: "Ανάλυση πωλήσεων",
    forecastDemand: "Πρόβλεψη ζήτησης",
    detectAnomalies: "Εντοπισμός ανωμαλιών",
    generateReport: "Δημιουργία αναφοράς",
  },
  sv: {
    analyzeSales: "Analysera försäljning",
    forecastDemand: "Prognostisera efterfrågan",
    detectAnomalies: "Upptäck avvikelser",
    generateReport: "Generera rapport",
  },
  tr: {
    analyzeSales: "Satış performansını analiz et",
    forecastDemand: "Talebi tahmin et",
    detectAnomalies: "Anomalileri tespit et",
    generateReport: "Rapor oluştur",
  },
  cs: {
    analyzeSales: "Analyzovat prodeje",
    forecastDemand: "Předpovědět poptávku",
    detectAnomalies: "Odhalit anomálie",
    generateReport: "Vygenerovat zprávu",
  },
  ka: {
    analyzeSales: "გაყიდვების ანალიზი",
    forecastDemand: "მოთხოვნის პროგნოზი",
    detectAnomalies: "ანომალიების აღმოჩენა",
    generateReport: "ანგარიშის შექმნა",
  },
  hy: {
    analyzeSales: "Վաճառքների վերլուծություն",
    forecastDemand: "Պահանջարկի կանխատեսում",
    detectAnomalies: "Անոմալիաների հայտնաբերում",
    generateReport: "Հաշվետվության ստեղծում",
  },
  sw: {
    analyzeSales: "Changanua mauzo",
    forecastDemand: "Tabiri mahitaji",
    detectAnomalies: "Gundua hitilafu",
    generateReport: "Tengeneza ripoti",
  },
  am: {
    analyzeSales: "ሽያጭን ተንትን",
    forecastDemand: "ፍላጎትን ተንብይ",
    detectAnomalies: "ያልተለመዱ ሁኔታዎችን ለይ",
    generateReport: "ሪፖርት አዘጋጅ",
  },
  af: {
    analyzeSales: "Ontleed verkope",
    forecastDemand: "Voorspel vraag",
    detectAnomalies: "Spoor afwykings op",
    generateReport: "Genereer verslag",
  },
  ha: {
    analyzeSales: "Bincika tallace-tallace",
    forecastDemand: "Hasashen buƙata",
    detectAnomalies: "Gano matsala",
    generateReport: "Ƙirƙiri rahoto",
  },
  hi: {
    analyzeSales: "बिक्री का विश्लेषण करें",
    forecastDemand: "मांग का पूर्वानुमान",
    detectAnomalies: "असामान्यताएँ खोजें",
    generateReport: "रिपोर्ट बनाएँ",
  },
  bn: {
    analyzeSales: "বিক্রয় বিশ্লেষণ করুন",
    forecastDemand: "চাহিদার পূর্বাভাস",
    detectAnomalies: "অসঙ্গতি শনাক্ত করুন",
    generateReport: "রিপোর্ট তৈরি করুন",
  },
  ta: {
    analyzeSales: "விற்பனையை பகுப்பாய்வு செய்",
    forecastDemand: "தேவையை கணி",
    detectAnomalies: "முரண்பாடுகளைக் கண்டறி",
    generateReport: "அறிக்கை உருவாக்கு",
  },
  pa: {
    analyzeSales: "ਵਿਕਰੀ ਦਾ ਵਿਸ਼ਲੇਸ਼ਣ ਕਰੋ",
    forecastDemand: "ਮੰਗ ਦਾ ਅਨੁਮਾਨ ਲਗਾਓ",
    detectAnomalies: "ਅਸਮਾਨਤਾਵਾਂ ਲੱਭੋ",
    generateReport: "ਰਿਪੋਰਟ ਬਣਾਓ",
  },
  ne: {
    analyzeSales: "बिक्री विश्लेषण गर्नुहोस्",
    forecastDemand: "मागको पूर्वानुमान",
    detectAnomalies: "असामान्यता पत्ता लगाउनुहोस्",
    generateReport: "प्रतिवेदन तयार गर्नुहोस्",
  },
  vi: {
    analyzeSales: "Phân tích doanh số",
    forecastDemand: "Dự báo nhu cầu",
    detectAnomalies: "Phát hiện bất thường",
    generateReport: "Tạo báo cáo",
  },
  th: {
    analyzeSales: "วิเคราะห์ยอดขาย",
    forecastDemand: "คาดการณ์ความต้องการ",
    detectAnomalies: "ตรวจจับความผิดปกติ",
    generateReport: "สร้างรายงาน",
  },
  id: {
    analyzeSales: "Analisis penjualan",
    forecastDemand: "Perkirakan permintaan",
    detectAnomalies: "Deteksi anomali",
    generateReport: "Buat laporan",
  },
  ms: {
    analyzeSales: "Analisis jualan",
    forecastDemand: "Ramalkan permintaan",
    detectAnomalies: "Kesan anomali",
    generateReport: "Jana laporan",
  },
  tl: {
    analyzeSales: "Suriin ang benta",
    forecastDemand: "Tayahin ang demand",
    detectAnomalies: "Tukuyin ang anomalya",
    generateReport: "Bumuo ng ulat",
  },
  my: {
    analyzeSales: "ရောင်းအား ခွဲခြမ်းစိတ်ဖြာရန်",
    forecastDemand: "ဝယ်လိုအား ခန့်မှန်းရန်",
    detectAnomalies: "မူမမှန်မှုများ ရှာဖွေရန်",
    generateReport: "အစီရင်ခံစာ ထုတ်ရန်",
  },
  km: {
    analyzeSales: "វិភាគការលក់",
    forecastDemand: "ព្យាករណ៍តម្រូវការ",
    detectAnomalies: "រកឃើញភាពមិនប្រក្រតី",
    generateReport: "បង្កើតរបាយការណ៍",
  },
  mn: {
    analyzeSales: "Борлуулалтыг шинжлэх",
    forecastDemand: "Эрэлтийг таамаглах",
    detectAnomalies: "Гажиг илрүүлэх",
    generateReport: "Тайлан гаргах",
  },
});
