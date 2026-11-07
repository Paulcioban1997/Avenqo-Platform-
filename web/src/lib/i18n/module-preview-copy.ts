import type { LocaleCode } from "./types";
import { completeLocaleMap } from "./complete-locale-map";

export interface ModulePreviewCopy {
  comingSoon: string;
  restrictedAccess: string;
  connectData: string;
  plannedCapabilities: string;
  plannedDescription: string;
  isolatedArchitecture: string;
  returnDashboard: string;
}

export const MODULE_PREVIEW_COPY: Record<LocaleCode, ModulePreviewCopy> = completeLocaleMap({
  en: {
    comingSoon: "Coming soon ({targetRelease})",
    restrictedAccess: "Restricted Early Access",
    connectData: "Connect your data",
    plannedCapabilities: "Planned capabilities",
    plannedDescription: "This module will be directly powered by your synchronized datasets with complete tenant isolation.",
    isolatedArchitecture: "Avenqo isolated multi-tenant architecture",
    returnDashboard: "Return to dashboard",
  },
  "en-GB": {
    comingSoon: "Coming soon ({targetRelease})",
    restrictedAccess: "Restricted early access",
    connectData: "Connect your data",
    plannedCapabilities: "Planned capabilities",
    plannedDescription: "This module will be directly powered by your synchronised datasets with complete tenant isolation.",
    isolatedArchitecture: "Avenqo isolated multi-tenant architecture",
    returnDashboard: "Return to dashboard",
  },
  fr: {
    comingSoon: "Disponible prochainement ({targetRelease})",
    restrictedAccess: "Accès anticipé restreint",
    connectData: "Connecter vos données",
    plannedCapabilities: "Fonctionnalités au programme",
    plannedDescription: "Ce module sera alimenté par vos données synchronisées sans aucune fuite entre organisations.",
    isolatedArchitecture: "Architecture scellée multi-tenant Avenqo",
    returnDashboard: "Retour au tableau de bord",
  },
  "fr-FR": {
    comingSoon: "Disponible prochainement ({targetRelease})",
    restrictedAccess: "Accès anticipé restreint",
    connectData: "Connecter vos données",
    plannedCapabilities: "Fonctionnalités au programme",
    plannedDescription: "Ce module sera alimenté par vos données synchronisées sans aucune fuite entre organisations.",
    isolatedArchitecture: "Architecture cloisonnée multi-tenant Avenqo",
    returnDashboard: "Retour au tableau de bord",
  },
  es: {
    comingSoon: "Próximamente ({targetRelease})",
    restrictedAccess: "Acceso anticipado restringido",
    connectData: "Conectar sus datos",
    plannedCapabilities: "Capacidades previstas",
    plannedDescription: "Este módulo se alimentará de sus conjuntos de datos sincronizados con aislamiento total entre organizaciones.",
    isolatedArchitecture: "Arquitectura multiinquilino aislada de Avenqo",
    returnDashboard: "Volver al panel",
  },
  pt: {
    comingSoon: "Em breve ({targetRelease})",
    restrictedAccess: "Acesso antecipado restrito",
    connectData: "Ligar os seus dados",
    plannedCapabilities: "Capacidades previstas",
    plannedDescription: "Este módulo será alimentado pelos seus conjuntos de dados sincronizados, com isolamento total entre organizações.",
    isolatedArchitecture: "Arquitetura multi-inquilino isolada da Avenqo",
    returnDashboard: "Voltar ao painel",
  },
  ro: {
    comingSoon: "Disponibil în curând ({targetRelease})",
    restrictedAccess: "Acces anticipat restricționat",
    connectData: "Conectați datele",
    plannedCapabilities: "Funcționalități planificate",
    plannedDescription: "Acest modul va folosi seturile de date sincronizate, fără nicio scurgere între organizații.",
    isolatedArchitecture: "Arhitectură multi-tenant izolată Avenqo",
    returnDashboard: "Înapoi la tabloul de bord",
  },
  de: {
    comingSoon: "Demnächst verfügbar ({targetRelease})",
    restrictedAccess: "Eingeschränkter frühzeitiger Zugang",
    connectData: "Daten verbinden",
    plannedCapabilities: "Geplante Funktionen",
    plannedDescription: "Dieses Modul wird von Ihren synchronisierten Datensätzen gespeist – ohne Datenleck zwischen Organisationen.",
    isolatedArchitecture: "Isolierte Multi-Tenant-Architektur von Avenqo",
    returnDashboard: "Zurück zum Dashboard",
  },
  it: {
    comingSoon: "Disponibile a breve ({targetRelease})",
    restrictedAccess: "Accesso anticipato limitato",
    connectData: "Collega i tuoi dati",
    plannedCapabilities: "Funzionalità previste",
    plannedDescription: "Questo modulo sarà alimentato dai dataset sincronizzati, senza alcuna fuga tra organizzazioni.",
    isolatedArchitecture: "Architettura multi-tenant isolata Avenqo",
    returnDashboard: "Torna alla dashboard",
  },
  zh: {
    comingSoon: "即将推出（{targetRelease}）",
    restrictedAccess: "受限抢先体验",
    connectData: "连接您的数据",
    plannedCapabilities: "规划中的能力",
    plannedDescription: "该模块将直接使用您已同步的数据集，并在组织之间完全隔离。",
    isolatedArchitecture: "Avenqo 隔离式多租户架构",
    returnDashboard: "返回仪表板",
  },
  ja: {
    comingSoon: "近日公開（{targetRelease}）",
    restrictedAccess: "制限付きアーリーアクセス",
    connectData: "データを接続",
    plannedCapabilities: "予定されている機能",
    plannedDescription: "このモジュールは同期済みデータセットで動作し、組織間で完全に分離されます。",
    isolatedArchitecture: "Avenqo の分離型マルチテナント構成",
    returnDashboard: "ダッシュボードに戻る",
  },
  ko: {
    comingSoon: "곧 제공 ({targetRelease})",
    restrictedAccess: "제한된 사전 이용",
    connectData: "데이터 연결",
    plannedCapabilities: "예정된 기능",
    plannedDescription: "이 모듈은 동기화된 데이터세트로 동작하며 조직 간에 완전히 격리됩니다.",
    isolatedArchitecture: "Avenqo 격리형 멀티테넌트 아키텍처",
    returnDashboard: "대시보드로 돌아가기",
  },
  ar: {
    comingSoon: "قريبًا ({targetRelease})",
    restrictedAccess: "وصول مبكر مقيّد",
    connectData: "ربط بياناتك",
    plannedCapabilities: "القدرات المخططة",
    plannedDescription: "سيعتمد هذا الوحدة على مجموعات بياناتك المتزامنة مع عزل كامل بين المؤسسات.",
    isolatedArchitecture: "بنية Avenqo متعددة المستأجرين المعزولة",
    returnDashboard: "العودة إلى لوحة التحكم",
  },
});
