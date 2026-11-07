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
  hi: {
    analyzeSales: "बिक्री का विश्लेषण करें",
    forecastDemand: "मांग का पूर्वानुमान",
    detectAnomalies: "असामान्यताएँ खोजें",
    generateReport: "रिपोर्ट बनाएँ",
  },
});
