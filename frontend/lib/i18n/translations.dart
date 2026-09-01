/// Dart mirror of web/src/lib/i18n/types.ts::Translations — one shape, 42 locale
/// JSON assets under assets/i18n/, no field ever hardcoded per-widget again.
class Translations {
  const Translations({
    required this.common,
    required this.nav,
    required this.hero,
    required this.dashboard,
    required this.features,
    required this.modulesSection,
    required this.steps,
    required this.usecases,
    required this.why,
    required this.pricing,
    required this.faq,
    required this.finalCta,
    required this.footer,
    required this.assistant,
    required this.auth,
    required this.dashboardHome,
    required this.admin,
    required this.onboarding,
    required this.company,
    required this.phase4d,
    required this.phase4e,
    required this.agents,
  });

  factory Translations.fromJson(Map<String, dynamic> json) {
    return Translations(
      common: CommonStrings.fromJson(json['common'] as Map<String, dynamic>),
      nav: NavStrings.fromJson(json['nav'] as Map<String, dynamic>),
      hero: HeroStrings.fromJson(json['hero'] as Map<String, dynamic>),
      dashboard: DashboardStrings.fromJson(json['dashboard'] as Map<String, dynamic>),
      features: FeaturesStrings.fromJson(json['features'] as Map<String, dynamic>),
      modulesSection: ModulesSectionStrings.fromJson(json['modulesSection'] as Map<String, dynamic>),
      steps: StepsStrings.fromJson(json['steps'] as Map<String, dynamic>),
      usecases: UsecasesStrings.fromJson(json['usecases'] as Map<String, dynamic>),
      why: WhyStrings.fromJson(json['why'] as Map<String, dynamic>),
      pricing: PricingStrings.fromJson(json['pricing'] as Map<String, dynamic>),
      faq: FaqStrings.fromJson(json['faq'] as Map<String, dynamic>),
      finalCta: FinalCtaStrings.fromJson(json['finalCta'] as Map<String, dynamic>),
      footer: FooterStrings.fromJson(json['footer'] as Map<String, dynamic>),
      // Traduit uniquement pour fr/en pour le moment : les 40 autres locales
      // retombent sur l'anglais existant tant qu'elles n'ont pas la clé.
      assistant: json['assistant'] != null
          ? AssistantStrings.fromJson(json['assistant'] as Map<String, dynamic>)
          : AssistantStrings.fallback(),
      // Même logique de repli que assistant : fr/en traduits, le reste en anglais.
      auth: json['auth'] != null
          ? AuthStrings.fromJson(json['auth'] as Map<String, dynamic>)
          : AuthStrings.fallback(),
      // Même logique de repli que assistant/auth : fr/en traduits, le reste en anglais.
      dashboardHome: json['dashboardHome'] != null
          ? DashboardHomeStrings.fromJson(json['dashboardHome'] as Map<String, dynamic>)
          : DashboardHomeStrings.fallback(),
      // Même logique de repli que assistant/auth/dashboardHome : fr/en traduits,
      // le reste en anglais.
      admin: json['admin'] != null
          ? AdminStrings.fromJson(json['admin'] as Map<String, dynamic>)
          : AdminStrings.fallback(),
      // Même logique de repli : fr/en traduits, le reste en anglais.
      onboarding: json['onboarding'] != null
          ? OnboardingStrings.fromJson(json['onboarding'] as Map<String, dynamic>)
          : OnboardingStrings.fallback(),
      // Même logique de repli : fr/en traduits, le reste en anglais.
      company: json['company'] != null
          ? CompanyStrings.fromJson(json['company'] as Map<String, dynamic>)
          : CompanyStrings.fallback(),
        phase4d: json['phase4d'] != null
          ? Phase4dStrings.fromJson(json['phase4d'] as Map<String, dynamic>)
          : Phase4dStrings.fallback(),
        phase4e: json['phase4e'] != null
          ? Phase4eStrings.fromJson(json['phase4e'] as Map<String, dynamic>)
          : Phase4eStrings.fallback(),
        agents: json['agents'] != null
          ? AgentStrings.fromJson(json['agents'] as Map<String, dynamic>)
          : AgentStrings.fallback(),
    );
  }

  final CommonStrings common;
  final NavStrings nav;
  final HeroStrings hero;
  final DashboardStrings dashboard;
  final FeaturesStrings features;
  final ModulesSectionStrings modulesSection;
  final StepsStrings steps;
  final UsecasesStrings usecases;
  final WhyStrings why;
  final PricingStrings pricing;
  final FaqStrings faq;
  final FinalCtaStrings finalCta;
  final FooterStrings footer;
  final AssistantStrings assistant;
  final AuthStrings auth;
  final DashboardHomeStrings dashboardHome;
  final AdminStrings admin;
  final OnboardingStrings onboarding;
  final CompanyStrings company;
  final Phase4dStrings phase4d;
  final Phase4eStrings phase4e;
  final AgentStrings agents;
}

class AgentStrings {
  const AgentStrings(this.values);

  factory AgentStrings.fromJson(Map<String, dynamic> json) => AgentStrings(
        json.map((key, value) => MapEntry(key, value as String)),
      );

  factory AgentStrings.fallback() => const AgentStrings({
        'navLabel': 'Agents',
        'title': 'Avenqo Agents',
        'subtitle': 'Specialized business capabilities, connected in one workspace.',
        'availableNow': 'Available now',
        'comingSoon': 'Coming Soon',
        'openAgent': 'Open agent',
        'adminTitle': 'Agent Catalog',
        'adminSubtitle': 'Platform capabilities and their current availability.',
        'availableCount': 'Available agents',
        'comingSoonCount': 'Coming Soon agents',
        'retailName': 'Retail Intelligence',
        'retailDescription': 'Operate sales, customers, products, recommendations, and retail analytics.',
        'marketingName': 'Marketing AI',
        'marketingDescription': 'Prepare campaigns, audiences, and measurable growth actions.',
        'crmName': 'CRM AI',
        'crmDescription': 'Prioritize relationships, opportunities, and next best actions.',
        'hrName': 'HR AI',
        'hrDescription': 'Support people operations, workforce insights, and employee workflows.',
        'accountingName': 'Accounting AI',
        'accountingDescription': 'Accelerate financial operations, controls, and reporting workflows.',
        'ocrName': 'OCR AI',
        'ocrDescription': 'Turn business documents into structured, usable information.',
        'voiceName': 'Voice AI',
        'voiceDescription': 'Prepare intelligent voice interactions connected to business context.',
        'mediaName': 'Media AI',
        'mediaDescription': 'Create, organize, and manage business media workflows.',
        'legalName': 'Legal AI',
        'legalDescription': 'Support contract analysis and controlled legal-document workflows.',
        'appointmentsName': 'Appointments AI',
        'appointmentsDescription': 'Coordinate bookings and availability across service-based businesses.',
        'workflowName': 'Workflow Automation',
        'workflowDescription': 'Connect repeatable tasks, approvals, and business processes.',
      });

  final Map<String, String> values;

  String value(String key) => values[key] ?? AgentStrings.fallback().values[key] ?? key;
  String get navLabel => value('navLabel');
  String get title => value('title');
  String get subtitle => value('subtitle');
  String get availableNow => value('availableNow');
  String get comingSoon => value('comingSoon');
  String get openAgent => value('openAgent');
  String get adminTitle => value('adminTitle');
  String get adminSubtitle => value('adminSubtitle');
  String get availableCount => value('availableCount');
  String get comingSoonCount => value('comingSoonCount');
}

class Phase4eStrings {
  const Phase4eStrings({
    required this.creditsTitle,
    required this.creditsSubtitle,
    required this.monthlyAllowance,
    required this.monthlyRemaining,
    required this.purchasedRemaining,
    required this.totalRemaining,
    required this.billingPeriod,
    required this.monthlyProgress,
    required this.customAllowance,
    required this.resetExplanation,
    required this.packsTitle,
    required this.packsSubtitle,
    required this.creditsUnit,
    required this.purchase,
    required this.purchaseRequiresActive,
    required this.priceUsd,
    required this.adminSubtitle,
    required this.company,
    required this.plan,
    required this.subscription,
    required this.aiUsage,
    required this.noCompanies,
  });

  factory Phase4eStrings.fromJson(Map<String, dynamic> json) => Phase4eStrings(
        creditsTitle: json['creditsTitle'] as String,
        creditsSubtitle: json['creditsSubtitle'] as String,
        monthlyAllowance: json['monthlyAllowance'] as String,
        monthlyRemaining: json['monthlyRemaining'] as String,
        purchasedRemaining: json['purchasedRemaining'] as String,
        totalRemaining: json['totalRemaining'] as String,
        billingPeriod: json['billingPeriod'] as String,
        monthlyProgress: json['monthlyProgress'] as String,
        customAllowance: json['customAllowance'] as String,
        resetExplanation: json['resetExplanation'] as String,
        packsTitle: json['packsTitle'] as String,
        packsSubtitle: json['packsSubtitle'] as String,
        creditsUnit: json['creditsUnit'] as String,
        purchase: json['purchase'] as String,
        purchaseRequiresActive: json['purchaseRequiresActive'] as String,
        priceUsd: json['priceUsd'] as String,
        adminSubtitle: json['adminSubtitle'] as String,
        company: json['company'] as String,
        plan: json['plan'] as String,
        subscription: json['subscription'] as String,
        aiUsage: json['aiUsage'] as String,
        noCompanies: json['noCompanies'] as String,
      );

  factory Phase4eStrings.fallback() => const Phase4eStrings(
        creditsTitle: 'AI credits',
        creditsSubtitle: 'Your monthly allowance and purchased credit balance.',
        monthlyAllowance: 'Monthly allowance',
        monthlyRemaining: 'Monthly remaining',
        purchasedRemaining: 'Purchased remaining',
        totalRemaining: 'Total remaining',
        billingPeriod: 'Billing period',
        monthlyProgress: '{used} of {included} credits used this period',
        customAllowance: 'Contractual / custom',
        resetExplanation: 'Monthly credits reset each billing period. Purchased credits carry over.',
        packsTitle: 'Add AI credits',
        packsSubtitle: 'One-time credit packs, fulfilled securely through Stripe.',
        creditsUnit: 'credits',
        purchase: 'Purchase',
        purchaseRequiresActive: 'An active or trialing subscription is required to purchase credit packs.',
        priceUsd: '\${price} USD',
        adminSubtitle: 'Tenant-scoped balances and logical AI usage across Avenqo.',
        company: 'Company',
        plan: 'Plan',
        subscription: 'Subscription',
        aiUsage: 'AI usage',
        noCompanies: 'No company credit data is available.',
      );

  final String creditsTitle;
  final String creditsSubtitle;
  final String monthlyAllowance;
  final String monthlyRemaining;
  final String purchasedRemaining;
  final String totalRemaining;
  final String billingPeriod;
  final String monthlyProgress;
  final String customAllowance;
  final String resetExplanation;
  final String packsTitle;
  final String packsSubtitle;
  final String creditsUnit;
  final String purchase;
  final String purchaseRequiresActive;
  final String priceUsd;
  final String adminSubtitle;
  final String company;
  final String plan;
  final String subscription;
  final String aiUsage;
  final String noCompanies;
}

class Phase4dStrings {
  const Phase4dStrings({
    required this.productsTotal,
    required this.productsActive,
    required this.productsRevenue,
    required this.productsUnits,
    required this.productsAveragePrice,
    required this.productsConcentration,
    required this.productsSearch,
    required this.productLabel,
    required this.categoryLabel,
    required this.revenueLabel,
    required this.unitsLabel,
    required this.averagePriceLabel,
    required this.lastActivityLabel,
    required this.performanceLabel,
    required this.strongLabel,
    required this.weakLabel,
    required this.allLabel,
    required this.sortLabel,
    required this.partialReady,
    required this.recommendationsEmpty,
    required this.priorityLabel,
    required this.evidenceLabel,
    required this.suggestedActionLabel,
    required this.productDeclineTitle,
    required this.productGrowthTitle,
    required this.productConcentrationTitle,
    required this.crossSellOpportunityTitle,
    required this.productRevenueChangedExplanation,
    required this.productConcentrationExplanation,
    required this.crossSellOpportunityExplanation,
    required this.reviewProductPerformance,
    required this.reviewProductConcentration,
    required this.reviewCrossSellOpportunities,
    required this.changeEvidence,
    required this.concentrationEvidence,
    required this.customerEvidence,
  });

  factory Phase4dStrings.fromJson(Map<String, dynamic> json) {
    final fallback = Phase4dStrings.fallback();
    String value(String key, String fallbackValue) => json[key] as String? ?? fallbackValue;
    return Phase4dStrings(
      productsTotal: value('productsTotal', fallback.productsTotal),
      productsActive: value('productsActive', fallback.productsActive),
      productsRevenue: value('productsRevenue', fallback.productsRevenue),
      productsUnits: value('productsUnits', fallback.productsUnits),
      productsAveragePrice: value('productsAveragePrice', fallback.productsAveragePrice),
      productsConcentration: value('productsConcentration', fallback.productsConcentration),
      productsSearch: value('productsSearch', fallback.productsSearch),
      productLabel: value('productLabel', fallback.productLabel),
      categoryLabel: value('categoryLabel', fallback.categoryLabel),
      revenueLabel: value('revenueLabel', fallback.revenueLabel),
      unitsLabel: value('unitsLabel', fallback.unitsLabel),
      averagePriceLabel: value('averagePriceLabel', fallback.averagePriceLabel),
      lastActivityLabel: value('lastActivityLabel', fallback.lastActivityLabel),
      performanceLabel: value('performanceLabel', fallback.performanceLabel),
      strongLabel: value('strongLabel', fallback.strongLabel),
      weakLabel: value('weakLabel', fallback.weakLabel),
      allLabel: value('allLabel', fallback.allLabel),
      sortLabel: value('sortLabel', fallback.sortLabel),
      partialReady: value('partialReady', fallback.partialReady),
      recommendationsEmpty: value('recommendationsEmpty', fallback.recommendationsEmpty),
      priorityLabel: value('priorityLabel', fallback.priorityLabel),
      evidenceLabel: value('evidenceLabel', fallback.evidenceLabel),
      suggestedActionLabel: value('suggestedActionLabel', fallback.suggestedActionLabel),
      productDeclineTitle: value('productDeclineTitle', fallback.productDeclineTitle),
      productGrowthTitle: value('productGrowthTitle', fallback.productGrowthTitle),
      productConcentrationTitle: value('productConcentrationTitle', fallback.productConcentrationTitle),
      crossSellOpportunityTitle: value('crossSellOpportunityTitle', fallback.crossSellOpportunityTitle),
      productRevenueChangedExplanation: value('productRevenueChangedExplanation', fallback.productRevenueChangedExplanation),
      productConcentrationExplanation: value('productConcentrationExplanation', fallback.productConcentrationExplanation),
      crossSellOpportunityExplanation: value('crossSellOpportunityExplanation', fallback.crossSellOpportunityExplanation),
      reviewProductPerformance: value('reviewProductPerformance', fallback.reviewProductPerformance),
      reviewProductConcentration: value('reviewProductConcentration', fallback.reviewProductConcentration),
      reviewCrossSellOpportunities: value('reviewCrossSellOpportunities', fallback.reviewCrossSellOpportunities),
      changeEvidence: value('changeEvidence', fallback.changeEvidence),
      concentrationEvidence: value('concentrationEvidence', fallback.concentrationEvidence),
      customerEvidence: value('customerEvidence', fallback.customerEvidence),
    );
  }

  factory Phase4dStrings.fallback() => const Phase4dStrings(
        productsTotal: 'Total products',
        productsActive: 'Active products',
        productsRevenue: 'Product revenue',
        productsUnits: 'Units sold',
        productsAveragePrice: 'Average selling price',
        productsConcentration: 'Top product revenue share',
        productsSearch: 'Search products',
        productLabel: 'Product',
        categoryLabel: 'Category',
        revenueLabel: 'Revenue',
        unitsLabel: 'Units',
        averagePriceLabel: 'Average price',
        lastActivityLabel: 'Last activity',
        performanceLabel: 'Performance',
        strongLabel: 'Strong',
        weakLabel: 'Weak',
        allLabel: 'All',
        sortLabel: 'Sort by',
        partialReady: 'Some data is still processing. Ready results are shown below.',
        recommendationsEmpty: 'No evidence-backed recommendation is available right now.',
        priorityLabel: 'Priority',
        evidenceLabel: 'Evidence',
        suggestedActionLabel: 'Suggested action',
        productDeclineTitle: 'Product revenue is declining',
        productGrowthTitle: 'Product revenue is growing',
        productConcentrationTitle: 'Revenue is concentrated in one product',
        crossSellOpportunityTitle: 'Cross-sell opportunities are available',
        productRevenueChangedExplanation: 'Revenue changed compared with the previous equivalent period.',
        productConcentrationExplanation: 'One product represents a significant share of observed product revenue.',
        crossSellOpportunityExplanation: 'The active validated recommendation model identified customers with relevant product suggestions.',
        reviewProductPerformance: 'Review product performance',
        reviewProductConcentration: 'Review product concentration',
        reviewCrossSellOpportunities: 'Review cross-sell opportunities',
        changeEvidence: '{entity}: {current} vs {comparison} ({change}%)',
        concentrationEvidence: '{entity}: {current}% of product revenue',
        customerEvidence: '{current} customers with recommendations',
      );

  final String productsTotal;
  final String productsActive;
  final String productsRevenue;
  final String productsUnits;
  final String productsAveragePrice;
  final String productsConcentration;
  final String productsSearch;
  final String productLabel;
  final String categoryLabel;
  final String revenueLabel;
  final String unitsLabel;
  final String averagePriceLabel;
  final String lastActivityLabel;
  final String performanceLabel;
  final String strongLabel;
  final String weakLabel;
  final String allLabel;
  final String sortLabel;
  final String partialReady;
  final String recommendationsEmpty;
  final String priorityLabel;
  final String evidenceLabel;
  final String suggestedActionLabel;
  final String productDeclineTitle;
  final String productGrowthTitle;
  final String productConcentrationTitle;
  final String crossSellOpportunityTitle;
  final String productRevenueChangedExplanation;
  final String productConcentrationExplanation;
  final String crossSellOpportunityExplanation;
  final String reviewProductPerformance;
  final String reviewProductConcentration;
  final String reviewCrossSellOpportunities;
  final String changeEvidence;
  final String concentrationEvidence;
  final String customerEvidence;
}

class OnboardingStrings {
  const OnboardingStrings({
    required this.title,
    required this.subtitle,
    required this.goalsLabel,
    required this.goalIncreaseSales,
    required this.goalReduceChurn,
    required this.goalOptimizePricing,
    required this.goalImproveInventory,
    required this.goalUnderstandCustomers,
    required this.goalAutomateReports,
    required this.toolsLabel,
    required this.toolPos,
    required this.toolEcommerce,
    required this.toolSpreadsheets,
    required this.toolAccounting,
    required this.toolCrm,
    required this.toolNone,
    required this.teamSizeLabel,
    required this.teamSizeSolo,
    required this.teamSizeSmall,
    required this.teamSizeMedium,
    required this.teamSizeLarge,
    required this.refineIndustryLabel,
    required this.refineIndustryHint,
    required this.continueCta,
    required this.skipCta,
    required this.genericError,
    required this.goalsRequired,
    required this.teamSizeRequired,
  });

  factory OnboardingStrings.fromJson(Map<String, dynamic> json) => OnboardingStrings(
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        goalsLabel: json['goalsLabel'] as String,
        goalIncreaseSales: json['goalIncreaseSales'] as String,
        goalReduceChurn: json['goalReduceChurn'] as String,
        goalOptimizePricing: json['goalOptimizePricing'] as String,
        goalImproveInventory: json['goalImproveInventory'] as String,
        goalUnderstandCustomers: json['goalUnderstandCustomers'] as String,
        goalAutomateReports: json['goalAutomateReports'] as String,
        toolsLabel: json['toolsLabel'] as String,
        toolPos: json['toolPos'] as String,
        toolEcommerce: json['toolEcommerce'] as String,
        toolSpreadsheets: json['toolSpreadsheets'] as String,
        toolAccounting: json['toolAccounting'] as String,
        toolCrm: json['toolCrm'] as String,
        toolNone: json['toolNone'] as String,
        teamSizeLabel: json['teamSizeLabel'] as String,
        teamSizeSolo: json['teamSizeSolo'] as String,
        teamSizeSmall: json['teamSizeSmall'] as String,
        teamSizeMedium: json['teamSizeMedium'] as String,
        teamSizeLarge: json['teamSizeLarge'] as String,
        refineIndustryLabel: json['refineIndustryLabel'] as String,
        refineIndustryHint: json['refineIndustryHint'] as String,
        continueCta: json['continueCta'] as String,
        skipCta: json['skipCta'] as String,
        genericError: json['genericError'] as String,
        goalsRequired: json['goalsRequired'] as String,
        teamSizeRequired: json['teamSizeRequired'] as String,
      );

  factory OnboardingStrings.fallback() => const OnboardingStrings(
        title: "Let's set up your Avenqo workspace",
        subtitle: 'A few quick questions to personalize your priorities and recommendations.',
        goalsLabel: 'What are your main goals?',
        goalIncreaseSales: 'Increase sales',
        goalReduceChurn: 'Reduce customer churn',
        goalOptimizePricing: 'Optimize pricing',
        goalImproveInventory: 'Improve inventory management',
        goalUnderstandCustomers: 'Better understand my customers',
        goalAutomateReports: 'Automate my reports',
        toolsLabel: 'Which tools do you currently use?',
        toolPos: 'Point of sale (POS) system',
        toolEcommerce: 'E-commerce platform',
        toolSpreadsheets: 'Spreadsheets (Excel/Sheets)',
        toolAccounting: 'Accounting software',
        toolCrm: 'CRM',
        toolNone: 'No tools yet',
        teamSizeLabel: 'What is the size of your team?',
        teamSizeSolo: 'Just me',
        teamSizeSmall: '2 to 10 people',
        teamSizeMedium: '11 to 50 people',
        teamSizeLarge: 'More than 50 people',
        refineIndustryLabel: 'Refine your industry (optional)',
        refineIndustryHint: 'E.g. specialty retail, fast food, accounting firm...',
        continueCta: 'Continue',
        skipCta: 'Skip for now',
        genericError: "We couldn't save your answers right now.",
        goalsRequired: 'Select at least one goal.',
        teamSizeRequired: 'Select your team size.',
      );

  final String title;
  final String subtitle;
  final String goalsLabel;
  final String goalIncreaseSales;
  final String goalReduceChurn;
  final String goalOptimizePricing;
  final String goalImproveInventory;
  final String goalUnderstandCustomers;
  final String goalAutomateReports;
  final String toolsLabel;
  final String toolPos;
  final String toolEcommerce;
  final String toolSpreadsheets;
  final String toolAccounting;
  final String toolCrm;
  final String toolNone;
  final String teamSizeLabel;
  final String teamSizeSolo;
  final String teamSizeSmall;
  final String teamSizeMedium;
  final String teamSizeLarge;
  final String refineIndustryLabel;
  final String refineIndustryHint;
  final String continueCta;
  final String skipCta;
  final String genericError;
  final String goalsRequired;
  final String teamSizeRequired;
}

class DashboardHomeStrings {
  const DashboardHomeStrings({
    required this.hello,
    required this.subtitleForCompany,
    required this.askAvenqo,
    required this.connectDataTitle,
    required this.connectDataCta,
    required this.thisMonth,
    required this.salesLabel,
    required this.ordersLabel,
    required this.customersLabel,
    required this.avgOrderLabel,
    required this.prioritiesTitle,
    required this.prioritiesEmpty,
    required this.planLabel,
    required this.askAvenqoSubtitle,
    required this.askAvenqoCta,
    required this.importDataTitle,
    required this.importDataSubtitle,
    required this.importDataCta,
    required this.connectionsTitle,
    required this.connectionsEmpty,
    required this.connectionsEmptyCta,
    required this.connectionsReadyLabel,
    required this.connectionsLastUpdate,
    required this.activityTitle,
    required this.activityEmpty,
    required this.stepsTitle,
    required this.stepOrgLabel,
    required this.stepDataLabel,
    required this.stepInsightsLabel,
    required this.stepAskLabel,
    required this.revenueDeclineTitle,
    required this.revenueGrowthTitle,
    required this.revenueChangedExplanation,
    required this.datasetImportedActivity,
    required this.modelActivatedActivity,
  });

  factory DashboardHomeStrings.fromJson(Map<String, dynamic> json) => DashboardHomeStrings(
        hello: json['hello'] as String,
        subtitleForCompany: json['subtitleForCompany'] as String,
        askAvenqo: json['askAvenqo'] as String,
        connectDataTitle: json['connectDataTitle'] as String,
        connectDataCta: json['connectDataCta'] as String,
        thisMonth: json['thisMonth'] as String,
        salesLabel: json['salesLabel'] as String,
        ordersLabel: json['ordersLabel'] as String,
        customersLabel: json['customersLabel'] as String,
        avgOrderLabel: json['avgOrderLabel'] as String,
        prioritiesTitle: json['prioritiesTitle'] as String,
        prioritiesEmpty: json['prioritiesEmpty'] as String,
        planLabel: json['planLabel'] as String,
        askAvenqoSubtitle: json['askAvenqoSubtitle'] as String? ?? DashboardHomeStrings.fallback().askAvenqoSubtitle,
        askAvenqoCta: json['askAvenqoCta'] as String? ?? DashboardHomeStrings.fallback().askAvenqoCta,
        importDataTitle: json['importDataTitle'] as String? ?? DashboardHomeStrings.fallback().importDataTitle,
        importDataSubtitle: json['importDataSubtitle'] as String? ?? DashboardHomeStrings.fallback().importDataSubtitle,
        importDataCta: json['importDataCta'] as String? ?? DashboardHomeStrings.fallback().importDataCta,
        connectionsTitle: json['connectionsTitle'] as String? ?? DashboardHomeStrings.fallback().connectionsTitle,
        connectionsEmpty: json['connectionsEmpty'] as String? ?? DashboardHomeStrings.fallback().connectionsEmpty,
        connectionsEmptyCta: json['connectionsEmptyCta'] as String? ?? DashboardHomeStrings.fallback().connectionsEmptyCta,
        connectionsReadyLabel: json['connectionsReadyLabel'] as String? ?? DashboardHomeStrings.fallback().connectionsReadyLabel,
        connectionsLastUpdate: json['connectionsLastUpdate'] as String? ?? DashboardHomeStrings.fallback().connectionsLastUpdate,
        activityTitle: json['activityTitle'] as String? ?? DashboardHomeStrings.fallback().activityTitle,
        activityEmpty: json['activityEmpty'] as String? ?? DashboardHomeStrings.fallback().activityEmpty,
        stepsTitle: json['stepsTitle'] as String? ?? DashboardHomeStrings.fallback().stepsTitle,
        stepOrgLabel: json['stepOrgLabel'] as String? ?? DashboardHomeStrings.fallback().stepOrgLabel,
        stepDataLabel: json['stepDataLabel'] as String? ?? DashboardHomeStrings.fallback().stepDataLabel,
        stepInsightsLabel: json['stepInsightsLabel'] as String? ?? DashboardHomeStrings.fallback().stepInsightsLabel,
        stepAskLabel: json['stepAskLabel'] as String? ?? DashboardHomeStrings.fallback().stepAskLabel,
        revenueDeclineTitle: json['revenueDeclineTitle'] as String? ?? DashboardHomeStrings.fallback().revenueDeclineTitle,
        revenueGrowthTitle: json['revenueGrowthTitle'] as String? ?? DashboardHomeStrings.fallback().revenueGrowthTitle,
        revenueChangedExplanation: json['revenueChangedExplanation'] as String? ?? DashboardHomeStrings.fallback().revenueChangedExplanation,
        datasetImportedActivity: json['datasetImportedActivity'] as String? ?? DashboardHomeStrings.fallback().datasetImportedActivity,
        modelActivatedActivity: json['modelActivatedActivity'] as String? ?? DashboardHomeStrings.fallback().modelActivatedActivity,
      );

  factory DashboardHomeStrings.fallback() => const DashboardHomeStrings(
        hello: 'Hello',
        subtitleForCompany: "Here's what deserves your attention at {company}.",
        askAvenqo: 'What would you like to understand today?',
        connectDataTitle: 'Connect your business data to unlock analytics, forecasts and Avenqo AI insights.',
        connectDataCta: 'Connect data',
        thisMonth: 'This month',
        salesLabel: 'Revenue',
        ordersLabel: 'Orders',
        customersLabel: 'Active customers',
        avgOrderLabel: 'Average order',
        prioritiesTitle: 'Recommended priorities',
        prioritiesEmpty: 'Your priorities will appear here once your business data is connected.',
        planLabel: 'Plan',
        askAvenqoSubtitle: 'Ask questions about your business data and receive contextual insights.',
        askAvenqoCta: 'Ask Avenqo AI',
        importDataTitle: 'Import your data',
        importDataSubtitle: 'Connect or import your business sources to unlock Avenqo intelligence.',
        importDataCta: 'Import my data',
        connectionsTitle: 'Connections',
        connectionsEmpty: 'No data connected yet',
        connectionsEmptyCta: 'Import my data',
        connectionsReadyLabel: 'Ready',
        connectionsLastUpdate: 'Last update',
        activityTitle: 'Recent activity',
        activityEmpty: 'No recent activity yet.',
        stepsTitle: 'Next recommended steps',
        stepOrgLabel: 'Complete your company setup',
        stepDataLabel: 'Connect or import your data',
        stepInsightsLabel: 'Explore your insights',
        stepAskLabel: 'Ask Avenqo AI',
        revenueDeclineTitle: 'Review the recent revenue decline',
        revenueGrowthTitle: 'Build on recent revenue growth',
        revenueChangedExplanation: 'Revenue changed materially from the previous equivalent period.',
        datasetImportedActivity: 'Dataset imported',
        modelActivatedActivity: 'Intelligence capability activated',
      );

  final String hello;
  final String subtitleForCompany;
  final String askAvenqo;
  final String connectDataTitle;
  final String connectDataCta;
  final String thisMonth;
  final String salesLabel;
  final String ordersLabel;
  final String customersLabel;
  final String avgOrderLabel;
  final String prioritiesTitle;
  final String prioritiesEmpty;
  final String planLabel;
  final String askAvenqoSubtitle;
  final String askAvenqoCta;
  final String importDataTitle;
  final String importDataSubtitle;
  final String importDataCta;
  final String connectionsTitle;
  final String connectionsEmpty;
  final String connectionsEmptyCta;
  final String connectionsReadyLabel;
  final String connectionsLastUpdate;
  final String activityTitle;
  final String activityEmpty;
  final String stepsTitle;
  final String stepOrgLabel;
  final String stepDataLabel;
  final String stepInsightsLabel;
  final String stepAskLabel;
  final String revenueDeclineTitle;
  final String revenueGrowthTitle;
  final String revenueChangedExplanation;
  final String datasetImportedActivity;
  final String modelActivatedActivity;
}

class AssistantStrings {
  const AssistantStrings({
    required this.title,
    required this.subtitle,
    required this.connectData,
    required this.newConversation,
    required this.conversationsEmpty,
    required this.deleteConversation,
    required this.thinking,
    required this.retry,
    required this.sourcesLabel,
    required this.newest,
    required this.you,
    required this.avenqoAi,
    required this.suggestions,
  });

  factory AssistantStrings.fromJson(Map<String, dynamic> json) => AssistantStrings(
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        connectData: json['connectData'] as String,
        newConversation: json['newConversation'] as String,
        conversationsEmpty: json['conversationsEmpty'] as String,
        deleteConversation: json['deleteConversation'] as String,
        thinking: json['thinking'] as String,
        retry: json['retry'] as String,
        sourcesLabel: json['sourcesLabel'] as String,
        newest: json['newest'] as String,
        you: json['you'] as String,
        avenqoAi: json['avenqoAi'] as String,
        suggestions: json['suggestions'] != null
            ? (json['suggestions'] as List<dynamic>).cast<String>()
            : AssistantStrings.fallback().suggestions,
      );

  /// Anglais par d\u00e9faut : m\u00eame texte que l'ancien code en dur, utilis\u00e9 par
  /// toutes les locales qui n'ont pas encore la cl\u00e9 "assistant".
  factory AssistantStrings.fallback() => const AssistantStrings(
        title: 'Ask Avenqo about your business',
        subtitle: 'Ask a business question and Avenqo will use the information available to your company.',
        connectData: 'Connect your business data',
        newConversation: 'New conversation',
        conversationsEmpty: 'Your conversations will appear here.',
        deleteConversation: 'Delete conversation',
        thinking: 'Avenqo is thinking...',
        retry: 'Retry',
        sourcesLabel: 'Sources',
        newest: 'Newest',
        you: 'You',
        avenqoAi: 'Avenqo AI',
        suggestions: [
          'How are my sales performing?',
          'Which customers need attention?',
          'What changed this month?',
          'Summarize my business performance.',
        ],
      );

  final String title;
  final String subtitle;
  final String connectData;
  final String newConversation;
  final String conversationsEmpty;
  final String deleteConversation;
  final String thinking;
  final String retry;
  final String sourcesLabel;
  final String newest;
  final String you;
  final String avenqoAi;
  final List<String> suggestions;
}

class AuthStrings {
  const AuthStrings({
    required this.tagline,
    required this.loginTitle,
    required this.loginSubtitle,
    required this.registerTitle,
    required this.registerSubtitle,
    required this.forgotTitle,
    required this.forgotSubtitle,
    required this.verifyTitle,
    required this.verifySubtitle,
    required this.resetTitle,
    required this.resetSubtitle,
    required this.organisation,
    required this.billingEmail,
    required this.firstName,
    required this.lastName,
    required this.email,
    required this.password,
    required this.emailToken,
    required this.requiredField,
    required this.forgotPassword,
    required this.createOrganisation,
    required this.backToLogin,
    required this.home,
    required this.registerSuccess,
    required this.registerPendingVerification,
    required this.workspaceReadyMessage,
    required this.continueLabel,
    required this.forgotSuccess,
    required this.verifySuccess,
    required this.resetSuccess,
    required this.genericError,
  });

  factory AuthStrings.fromJson(Map<String, dynamic> json) => AuthStrings(
        tagline: json['tagline'] as String,
        loginTitle: json['loginTitle'] as String,
        loginSubtitle: json['loginSubtitle'] as String,
        registerTitle: json['registerTitle'] as String,
        registerSubtitle: json['registerSubtitle'] as String,
        forgotTitle: json['forgotTitle'] as String,
        forgotSubtitle: json['forgotSubtitle'] as String,
        verifyTitle: json['verifyTitle'] as String,
        verifySubtitle: json['verifySubtitle'] as String,
        resetTitle: json['resetTitle'] as String,
        resetSubtitle: json['resetSubtitle'] as String,
        organisation: json['organisation'] as String,
        billingEmail: json['billingEmail'] as String,
        firstName: json['firstName'] as String,
        lastName: json['lastName'] as String,
        email: json['email'] as String,
        password: json['password'] as String,
        emailToken: json['emailToken'] as String,
        requiredField: json['requiredField'] as String,
        forgotPassword: json['forgotPassword'] as String,
        createOrganisation: json['createOrganisation'] as String,
        backToLogin: json['backToLogin'] as String,
        home: json['home'] as String,
        registerSuccess: json['registerSuccess'] as String,
        registerPendingVerification: json['registerPendingVerification'] as String,
        workspaceReadyMessage: json['workspaceReadyMessage'] as String,
        continueLabel: json['continueLabel'] as String,
        forgotSuccess: json['forgotSuccess'] as String,
        verifySuccess: json['verifySuccess'] as String,
        resetSuccess: json['resetSuccess'] as String,
        genericError: json['genericError'] as String,
      );

  factory AuthStrings.fallback() => const AuthStrings(
        tagline: 'The AI platform for your business decisions',
        loginTitle: 'Log in',
        loginSubtitle: 'Access your Avenqo workspace.',
        registerTitle: 'Create an organization',
        registerSubtitle: 'Set up your Avenqo workspace in a few minutes.',
        forgotTitle: 'Forgot password',
        forgotSubtitle: 'Get a link to reset your password.',
        verifyTitle: 'Verify your email',
        verifySubtitle: 'Enter the token you received by email.',
        resetTitle: 'New password',
        resetSubtitle: 'Choose a new, secure password.',
        organisation: 'Organization',
        billingEmail: 'Billing email',
        firstName: 'First name',
        lastName: 'Last name',
        email: 'Email',
        password: 'Password',
        emailToken: 'Token received by email',
        requiredField: 'Required field',
        forgotPassword: 'Forgot password',
        createOrganisation: 'Create an organization',
        backToLogin: 'Back to login',
        home: 'Home',
        registerSuccess: 'Account created. Check your email address.',
        registerPendingVerification: 'Account created. An administrator will confirm your access shortly.',
        workspaceReadyMessage: 'Your Avenqo workspace is ready to be created.',
        continueLabel: 'Continue',
        forgotSuccess: 'If the account exists, an email has been sent.',
        verifySuccess: 'Email verified. You can now log in.',
        resetSuccess: 'Password changed. You can now log in.',
        genericError: 'The service is temporarily unavailable.',
      );

  final String tagline;
  final String loginTitle;
  final String loginSubtitle;
  final String registerTitle;
  final String registerSubtitle;
  final String forgotTitle;
  final String forgotSubtitle;
  final String verifyTitle;
  final String verifySubtitle;
  final String resetTitle;
  final String resetSubtitle;
  final String organisation;
  final String billingEmail;
  final String firstName;
  final String lastName;
  final String email;
  final String password;
  final String emailToken;
  final String requiredField;
  final String forgotPassword;
  final String createOrganisation;
  final String backToLogin;
  final String home;
  final String registerSuccess;
  final String registerPendingVerification;
  final String workspaceReadyMessage;
  final String continueLabel;
  final String forgotSuccess;
  final String verifySuccess;
  final String resetSuccess;
  final String genericError;
}

/// Platform Admin (Command Center) strings — fr/en translated, other locales
/// fall back to English via [AdminStrings.fallback] (see Translations.fromJson).
class AdminStrings {
  const AdminStrings({
    required this.commandCenterTitle,
    required this.platformBadge,
    required this.backToWorkspace,
    required this.logOut,
    required this.navOverview,
    required this.navCompanies,
    required this.navSubscriptions,
    required this.navBilling,
    required this.navAiUsage,
    required this.navProviders,
    required this.navSystemHealth,
    required this.navAuditLogs,
    required this.navSupport,
    required this.navSettings,
    required this.overviewTitle,
    required this.overviewSubtitle,
    required this.overviewError,
    required this.totalCompanies,
    required this.newCompanies30d,
    required this.activeSubscriptions,
    required this.pastDue,
    required this.aiRequestsPeriod,
    required this.planDistribution,
    required this.providerHealth,
    required this.noCompaniesYet,
    required this.noProviderStatus,
    required this.companiesTitle,
    required this.companiesSubtitle,
    required this.searchCompaniesHint,
    required this.companiesError,
    required this.noCompaniesMatch,
    required this.companyFallbackName,
    required this.joinedLabel,
    required this.companyDetailError,
    required this.usage,
    required this.users,
    required this.datasets,
    required this.trainedModels,
    required this.subscription,
    required this.currentPeriodEnd,
    required this.cancelsAtPeriodEnd,
    required this.yes,
    required this.no,
    required this.enterpriseOverride,
    required this.active,
    required this.auditLogTitle,
    required this.auditLogSubtitle,
    required this.auditLogError,
    required this.noAuditEntries,
    required this.subscriptionsTitle,
    required this.subscriptionsSubtitle,
    required this.subscriptionsError,
    required this.noSubscriptionsYet,
    required this.billingTitle,
    required this.billingSubtitle,
    required this.billingError,
    required this.noInvoicesMessage,
    required this.aiUsageTitle,
    required this.aiUsageSubtitle,
    required this.aiUsageError,
    required this.aiRequestsCurrentPeriod,
    required this.providersLabel,
    required this.noCostBreakdownMessage,
    required this.providersTitle,
    required this.providersSubtitle,
    required this.providersError,
    required this.systemHealthTitle,
    required this.systemHealthSubtitle,
    required this.systemHealthError,
    required this.backendLabel,
    required this.databaseLabel,
    required this.billingStripeLabel,
    required this.configured,
    required this.notConfigured,
    required this.unknownStatus,
    required this.supportTitle,
    required this.supportSubtitle,
    required this.noSupportMessage,
    required this.settingsTitle,
    required this.signedInAs,
    required this.noSettingsMessage,
  });

  factory AdminStrings.fromJson(Map<String, dynamic> json) => AdminStrings(
        commandCenterTitle: json['commandCenterTitle'] as String,
        platformBadge: json['platformBadge'] as String,
        backToWorkspace: json['backToWorkspace'] as String,
        logOut: json['logOut'] as String,
        navOverview: json['navOverview'] as String,
        navCompanies: json['navCompanies'] as String,
        navSubscriptions: json['navSubscriptions'] as String,
        navBilling: json['navBilling'] as String,
        navAiUsage: json['navAiUsage'] as String,
        navProviders: json['navProviders'] as String,
        navSystemHealth: json['navSystemHealth'] as String,
        navAuditLogs: json['navAuditLogs'] as String,
        navSupport: json['navSupport'] as String,
        navSettings: json['navSettings'] as String,
        overviewTitle: json['overviewTitle'] as String,
        overviewSubtitle: json['overviewSubtitle'] as String,
        overviewError: json['overviewError'] as String,
        totalCompanies: json['totalCompanies'] as String,
        newCompanies30d: json['newCompanies30d'] as String,
        activeSubscriptions: json['activeSubscriptions'] as String,
        pastDue: json['pastDue'] as String,
        aiRequestsPeriod: json['aiRequestsPeriod'] as String,
        planDistribution: json['planDistribution'] as String,
        providerHealth: json['providerHealth'] as String,
        noCompaniesYet: json['noCompaniesYet'] as String,
        noProviderStatus: json['noProviderStatus'] as String,
        companiesTitle: json['companiesTitle'] as String,
        companiesSubtitle: json['companiesSubtitle'] as String,
        searchCompaniesHint: json['searchCompaniesHint'] as String,
        companiesError: json['companiesError'] as String,
        noCompaniesMatch: json['noCompaniesMatch'] as String,
        companyFallbackName: json['companyFallbackName'] as String,
        joinedLabel: json['joinedLabel'] as String,
        companyDetailError: json['companyDetailError'] as String,
        usage: json['usage'] as String,
        users: json['users'] as String,
        datasets: json['datasets'] as String,
        trainedModels: json['trainedModels'] as String,
        subscription: json['subscription'] as String,
        currentPeriodEnd: json['currentPeriodEnd'] as String,
        cancelsAtPeriodEnd: json['cancelsAtPeriodEnd'] as String,
        yes: json['yes'] as String,
        no: json['no'] as String,
        enterpriseOverride: json['enterpriseOverride'] as String,
        active: json['active'] as String,
        auditLogTitle: json['auditLogTitle'] as String,
        auditLogSubtitle: json['auditLogSubtitle'] as String,
        auditLogError: json['auditLogError'] as String,
        noAuditEntries: json['noAuditEntries'] as String,
        subscriptionsTitle: json['subscriptionsTitle'] as String,
        subscriptionsSubtitle: json['subscriptionsSubtitle'] as String,
        subscriptionsError: json['subscriptionsError'] as String,
        noSubscriptionsYet: json['noSubscriptionsYet'] as String,
        billingTitle: json['billingTitle'] as String,
        billingSubtitle: json['billingSubtitle'] as String,
        billingError: json['billingError'] as String,
        noInvoicesMessage: json['noInvoicesMessage'] as String,
        aiUsageTitle: json['aiUsageTitle'] as String,
        aiUsageSubtitle: json['aiUsageSubtitle'] as String,
        aiUsageError: json['aiUsageError'] as String,
        aiRequestsCurrentPeriod: json['aiRequestsCurrentPeriod'] as String,
        providersLabel: json['providersLabel'] as String,
        noCostBreakdownMessage: json['noCostBreakdownMessage'] as String,
        providersTitle: json['providersTitle'] as String,
        providersSubtitle: json['providersSubtitle'] as String,
        providersError: json['providersError'] as String,
        systemHealthTitle: json['systemHealthTitle'] as String,
        systemHealthSubtitle: json['systemHealthSubtitle'] as String,
        systemHealthError: json['systemHealthError'] as String,
        backendLabel: json['backendLabel'] as String,
        databaseLabel: json['databaseLabel'] as String,
        billingStripeLabel: json['billingStripeLabel'] as String,
        configured: json['configured'] as String,
        notConfigured: json['notConfigured'] as String,
        unknownStatus: json['unknownStatus'] as String,
        supportTitle: json['supportTitle'] as String,
        supportSubtitle: json['supportSubtitle'] as String,
        noSupportMessage: json['noSupportMessage'] as String,
        settingsTitle: json['settingsTitle'] as String,
        signedInAs: json['signedInAs'] as String,
        noSettingsMessage: json['noSettingsMessage'] as String,
      );

  factory AdminStrings.fallback() => const AdminStrings(
        commandCenterTitle: 'Avenqo Command Center',
        platformBadge: 'PLATFORM',
        backToWorkspace: 'Back to workspace',
        logOut: 'Log out',
        navOverview: 'Overview',
        navCompanies: 'Companies',
        navSubscriptions: 'Subscriptions',
        navBilling: 'Billing',
        navAiUsage: 'AI Usage',
        navProviders: 'Providers',
        navSystemHealth: 'System Health',
        navAuditLogs: 'Audit Logs',
        navSupport: 'Support',
        navSettings: 'Settings',
        overviewTitle: 'Platform Overview',
        overviewSubtitle: 'Cross-tenant KPIs, health, and recent activity across Avenqo.',
        overviewError: 'Admin dashboard is temporarily unavailable.',
        totalCompanies: 'Total companies',
        newCompanies30d: 'New companies (30d)',
        activeSubscriptions: 'Active subscriptions',
        pastDue: 'Past due',
        aiRequestsPeriod: 'AI requests (period)',
        planDistribution: 'Plan distribution',
        providerHealth: 'AI provider health',
        noCompaniesYet: 'No companies yet.',
        noProviderStatus: 'No provider status reported.',
        companiesTitle: 'Companies',
        companiesSubtitle: 'companies on the platform',
        searchCompaniesHint: 'Search companies…',
        companiesError: 'Company directory is temporarily unavailable.',
        noCompaniesMatch: 'No companies match',
        companyFallbackName: 'Company',
        joinedLabel: 'joined',
        companyDetailError: "This company's detail is unavailable.",
        usage: 'Usage',
        users: 'Users',
        datasets: 'Datasets',
        trainedModels: 'Trained models',
        subscription: 'Subscription',
        currentPeriodEnd: 'Current period end',
        cancelsAtPeriodEnd: 'Cancels at period end',
        yes: 'Yes',
        no: 'No',
        enterpriseOverride: 'Enterprise override',
        active: 'Active',
        auditLogTitle: 'Audit Logs',
        auditLogSubtitle: 'recent entries · read-only',
        auditLogError: 'Audit log is temporarily unavailable.',
        noAuditEntries: 'No audit entries yet.',
        subscriptionsTitle: 'Subscriptions',
        subscriptionsSubtitle: 'companies · Demo / Professional / Enterprise',
        subscriptionsError: 'Subscription data is temporarily unavailable.',
        noSubscriptionsYet: 'No subscriptions yet.',
        billingTitle: 'Billing',
        billingSubtitle: 'Platform-wide subscription and revenue signals.',
        billingError: 'Billing overview is temporarily unavailable.',
        noInvoicesMessage:
            'Cross-tenant invoices, MRR and ARR require a dedicated admin billing aggregation endpoint '
            'that does not exist yet on the backend. Not fabricated here.',
        aiUsageTitle: 'AI Usage',
        aiUsageSubtitle: 'Logical AI requests and provider availability across all companies.',
        aiUsageError: 'AI usage is temporarily unavailable.',
        aiRequestsCurrentPeriod: 'Avenqo AI requests (current period)',
        providersLabel: 'Providers',
        noCostBreakdownMessage:
            'Per-provider token counts and estimated cost breakdown require a dedicated usage-aggregation '
            'endpoint that does not exist yet on the backend. Not fabricated here.',
        providersTitle: 'Providers',
        providersSubtitle: 'Live AI Gateway provider health — no keys or raw errors shown.',
        providersError: 'Provider status is temporarily unavailable.',
        systemHealthTitle: 'System Health',
        systemHealthSubtitle: 'Live readiness of core Avenqo services.',
        systemHealthError: 'System health is temporarily unavailable.',
        backendLabel: 'Backend',
        databaseLabel: 'Database',
        billingStripeLabel: 'Billing (Stripe)',
        configured: 'configured',
        notConfigured: 'not configured',
        unknownStatus: 'unknown',
        supportTitle: 'Support',
        supportSubtitle: 'Escalations, important issues, and enterprise incidents.',
        noSupportMessage:
            'No admin support/ticketing backend exists yet — this view intentionally shows no fabricated tickets.',
        settingsTitle: 'Settings',
        signedInAs: 'Signed in as',
        noSettingsMessage:
            'No platform-wide configuration is exposed here yet — nothing to show honestly beyond account identity.',
      );

  final String commandCenterTitle;
  final String platformBadge;
  final String backToWorkspace;
  final String logOut;
  final String navOverview;
  final String navCompanies;
  final String navSubscriptions;
  final String navBilling;
  final String navAiUsage;
  final String navProviders;
  final String navSystemHealth;
  final String navAuditLogs;
  final String navSupport;
  final String navSettings;
  final String overviewTitle;
  final String overviewSubtitle;
  final String overviewError;
  final String totalCompanies;
  final String newCompanies30d;
  final String activeSubscriptions;
  final String pastDue;
  final String aiRequestsPeriod;
  final String planDistribution;
  final String providerHealth;
  final String noCompaniesYet;
  final String noProviderStatus;
  final String companiesTitle;
  final String companiesSubtitle;
  final String searchCompaniesHint;
  final String companiesError;
  final String noCompaniesMatch;
  final String companyFallbackName;
  final String joinedLabel;
  final String companyDetailError;
  final String usage;
  final String users;
  final String datasets;
  final String trainedModels;
  final String subscription;
  final String currentPeriodEnd;
  final String cancelsAtPeriodEnd;
  final String yes;
  final String no;
  final String enterpriseOverride;
  final String active;
  final String auditLogTitle;
  final String auditLogSubtitle;
  final String auditLogError;
  final String noAuditEntries;
  final String subscriptionsTitle;
  final String subscriptionsSubtitle;
  final String subscriptionsError;
  final String noSubscriptionsYet;
  final String billingTitle;
  final String billingSubtitle;
  final String billingError;
  final String noInvoicesMessage;
  final String aiUsageTitle;
  final String aiUsageSubtitle;
  final String aiUsageError;
  final String aiRequestsCurrentPeriod;
  final String providersLabel;
  final String noCostBreakdownMessage;
  final String providersTitle;
  final String providersSubtitle;
  final String providersError;
  final String systemHealthTitle;
  final String systemHealthSubtitle;
  final String systemHealthError;
  final String backendLabel;
  final String databaseLabel;
  final String billingStripeLabel;
  final String configured;
  final String notConfigured;
  final String unknownStatus;
  final String supportTitle;
  final String supportSubtitle;
  final String noSupportMessage;
  final String settingsTitle;
  final String signedInAs;
  final String noSettingsMessage;
}

class CommonStrings {
  const CommonStrings({
    required this.login,
    required this.tryFree,
    required this.watchDemo,
    required this.noCreditCard,
    required this.guidedSetup,
    required this.isolatedData,
  });

  factory CommonStrings.fromJson(Map<String, dynamic> json) => CommonStrings(
        login: json['login'] as String,
        tryFree: json['tryFree'] as String,
        watchDemo: json['watchDemo'] as String,
        noCreditCard: json['noCreditCard'] as String,
        guidedSetup: json['guidedSetup'] as String,
        isolatedData: json['isolatedData'] as String,
      );

  final String login;
  final String tryFree;
  final String watchDemo;
  final String noCreditCard;
  final String guidedSetup;
  final String isolatedData;
}

class NavStrings {
  const NavStrings({
    required this.features,
    required this.modules,
    required this.pricing,
    required this.enterprise,
    required this.docs,
  });

  factory NavStrings.fromJson(Map<String, dynamic> json) => NavStrings(
        features: json['features'] as String,
        modules: json['modules'] as String,
        pricing: json['pricing'] as String,
        enterprise: json['enterprise'] as String,
        docs: json['docs'] as String,
      );

  final String features;
  final String modules;
  final String pricing;
  final String enterprise;
  final String docs;
}

class HeroStrings {
  const HeroStrings({
    required this.eyebrow,
    required this.titleLine1,
    required this.titleLine2,
    required this.subtitle,
    required this.trustLabel,
    required this.trustSell,
    required this.trustUnderstand,
    required this.trustAutomate,
    required this.trustDecide,
  });

  factory HeroStrings.fromJson(Map<String, dynamic> json) => HeroStrings(
        eyebrow: json['eyebrow'] as String,
        titleLine1: json['titleLine1'] as String,
        titleLine2: json['titleLine2'] as String,
        subtitle: json['subtitle'] as String,
        trustLabel: json['trustLabel'] as String,
        trustSell: json['trustSell'] as String,
        trustUnderstand: json['trustUnderstand'] as String,
        trustAutomate: json['trustAutomate'] as String,
        trustDecide: json['trustDecide'] as String,
      );

  final String eyebrow;
  final String titleLine1;
  final String titleLine2;
  final String subtitle;
  final String trustLabel;
  final String trustSell;
  final String trustUnderstand;
  final String trustAutomate;
  final String trustDecide;
}

class QuickModule {
  const QuickModule({required this.key, required this.label});

  factory QuickModule.fromJson(Map<String, dynamic> json) => QuickModule(
        key: json['key'] as String,
        label: json['label'] as String,
      );

  final String key;
  final String label;
}

class DashboardStrings {
  const DashboardStrings({
    required this.greeting,
    required this.subtitle,
    required this.askAvenqo,
    required this.salesLabel,
    required this.activeClientsLabel,
    required this.opportunitiesLabel,
    required this.opportunitiesHint,
    required this.performanceLabel,
    required this.performancePeriod,
    required this.recommendationLabel,
    required this.recommendationTitle,
    required this.recommendationText,
    required this.recommendationAction,
    required this.quickModulesLabel,
    required this.quickModules,
  });

  factory DashboardStrings.fromJson(Map<String, dynamic> json) => DashboardStrings(
        greeting: json['greeting'] as String,
        subtitle: json['subtitle'] as String,
        askAvenqo: json['askAvenqo'] as String,
        salesLabel: json['salesLabel'] as String,
        activeClientsLabel: json['activeClientsLabel'] as String,
        opportunitiesLabel: json['opportunitiesLabel'] as String,
        opportunitiesHint: json['opportunitiesHint'] as String,
        performanceLabel: json['performanceLabel'] as String,
        performancePeriod: json['performancePeriod'] as String,
        recommendationLabel: json['recommendationLabel'] as String,
        recommendationTitle: json['recommendationTitle'] as String,
        recommendationText: json['recommendationText'] as String,
        recommendationAction: json['recommendationAction'] as String,
        quickModulesLabel: json['quickModulesLabel'] as String,
        quickModules: (json['quickModules'] as List<dynamic>)
            .map((e) => QuickModule.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String greeting;
  final String subtitle;
  final String askAvenqo;
  final String salesLabel;
  final String activeClientsLabel;
  final String opportunitiesLabel;
  final String opportunitiesHint;
  final String performanceLabel;
  final String performancePeriod;
  final String recommendationLabel;
  final String recommendationTitle;
  final String recommendationText;
  final String recommendationAction;
  final String quickModulesLabel;
  final List<QuickModule> quickModules;
}

class FeaturesStrings {
  const FeaturesStrings({
    required this.kicker,
    required this.title,
    required this.subtitle,
    required this.assistantLabel,
    required this.assistantTitle,
    required this.assistantText,
    required this.demoQuestion,
    required this.demoAnswer,
    required this.demoAction1,
    required this.demoAction2,
    required this.actionsTitle,
    required this.actionsText,
    required this.actionsPriority,
    required this.actionsLine,
    required this.securityTitle,
    required this.securityText,
    required this.securityItem1,
    required this.securityItem2,
    required this.securityItem3,
  });

  factory FeaturesStrings.fromJson(Map<String, dynamic> json) => FeaturesStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        assistantLabel: json['assistantLabel'] as String,
        assistantTitle: json['assistantTitle'] as String,
        assistantText: json['assistantText'] as String,
        demoQuestion: json['demoQuestion'] as String,
        demoAnswer: json['demoAnswer'] as String,
        demoAction1: json['demoAction1'] as String,
        demoAction2: json['demoAction2'] as String,
        actionsTitle: json['actionsTitle'] as String,
        actionsText: json['actionsText'] as String,
        actionsPriority: json['actionsPriority'] as String,
        actionsLine: json['actionsLine'] as String,
        securityTitle: json['securityTitle'] as String,
        securityText: json['securityText'] as String,
        securityItem1: json['securityItem1'] as String,
        securityItem2: json['securityItem2'] as String,
        securityItem3: json['securityItem3'] as String,
      );

  final String kicker;
  final String title;
  final String subtitle;
  final String assistantLabel;
  final String assistantTitle;
  final String assistantText;
  final String demoQuestion;
  final String demoAnswer;
  final String demoAction1;
  final String demoAction2;
  final String actionsTitle;
  final String actionsText;
  final String actionsPriority;
  final String actionsLine;
  final String securityTitle;
  final String securityText;
  final String securityItem1;
  final String securityItem2;
  final String securityItem3;
}

class ModuleItem {
  const ModuleItem({required this.name, required this.description, required this.available});

  factory ModuleItem.fromJson(Map<String, dynamic> json) => ModuleItem(
        name: json['name'] as String,
        description: json['description'] as String,
        available: json['available'] as bool? ?? false,
      );

  final String name;
  final String description;
  final bool available;
}

class ModulesSectionStrings {
  const ModulesSectionStrings({
    required this.kicker,
    required this.title,
    required this.subtitle,
    required this.discover,
    required this.availableNow,
    required this.comingSoon,
    required this.items,
  });

  factory ModulesSectionStrings.fromJson(Map<String, dynamic> json) => ModulesSectionStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        discover: json['discover'] as String,
        availableNow: json['availableNow'] as String,
        comingSoon: json['comingSoon'] as String,
        items: (json['items'] as List<dynamic>)
            .map((e) => ModuleItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String kicker;
  final String title;
  final String subtitle;
  final String discover;
  final String availableNow;
  final String comingSoon;
  final List<ModuleItem> items;
}

class StepItem {
  const StepItem({required this.number, required this.title, required this.text});

  factory StepItem.fromJson(Map<String, dynamic> json) => StepItem(
        number: json['number'] as String,
        title: json['title'] as String,
        text: json['text'] as String,
      );

  final String number;
  final String title;
  final String text;
}

class StepsStrings {
  const StepsStrings({
    required this.kicker,
    required this.title,
    required this.ctaLabel,
    required this.ctaButton,
    required this.items,
  });

  factory StepsStrings.fromJson(Map<String, dynamic> json) => StepsStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        ctaLabel: json['ctaLabel'] as String,
        ctaButton: json['ctaButton'] as String,
        items: (json['items'] as List<dynamic>)
            .map((e) => StepItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String kicker;
  final String title;
  final String ctaLabel;
  final String ctaButton;
  final List<StepItem> items;
}

class UsecaseEntry {
  const UsecaseEntry({required this.title, required this.text});

  factory UsecaseEntry.fromJson(Map<String, dynamic> json) => UsecaseEntry(
        title: json['title'] as String,
        text: json['text'] as String,
      );

  final String title;
  final String text;
}

class UsecasesStrings {
  const UsecasesStrings({
    required this.kicker,
    required this.title,
    required this.subtitle,
    required this.direction,
    required this.finance,
    required this.commerce,
    required this.operations,
  });

  factory UsecasesStrings.fromJson(Map<String, dynamic> json) => UsecasesStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        direction: UsecaseEntry.fromJson(json['direction'] as Map<String, dynamic>),
        finance: UsecaseEntry.fromJson(json['finance'] as Map<String, dynamic>),
        commerce: UsecaseEntry.fromJson(json['commerce'] as Map<String, dynamic>),
        operations: UsecaseEntry.fromJson(json['operations'] as Map<String, dynamic>),
      );

  final String kicker;
  final String title;
  final String subtitle;
  final UsecaseEntry direction;
  final UsecaseEntry finance;
  final UsecaseEntry commerce;
  final UsecaseEntry operations;
}

class WhyItem {
  const WhyItem({required this.number, required this.title, required this.text});

  factory WhyItem.fromJson(Map<String, dynamic> json) => WhyItem(
        number: json['number'] as String,
        title: json['title'] as String,
        text: json['text'] as String,
      );

  final String number;
  final String title;
  final String text;
}

class WhyStrings {
  const WhyStrings({required this.kicker, required this.title, required this.items});

  factory WhyStrings.fromJson(Map<String, dynamic> json) => WhyStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        items: (json['items'] as List<dynamic>)
            .map((e) => WhyItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String kicker;
  final String title;
  final List<WhyItem> items;
}

class PricingPlan {
  const PricingPlan({
    required this.tier,
    required this.title,
    required this.priceLabel,
    required this.items,
    required this.action,
  });

  factory PricingPlan.fromJson(Map<String, dynamic> json) => PricingPlan(
        tier: json['tier'] as String,
        title: json['title'] as String,
        priceLabel: json['priceLabel'] as String,
        items: (json['items'] as List<dynamic>).cast<String>(),
        action: json['action'] as String,
      );

  final String tier;
  final String title;
  final String priceLabel;
  final List<String> items;
  final String action;
}

class PricingStrings {
  const PricingStrings({
    required this.kicker,
    required this.title,
    required this.subtitle,
    required this.popular,
    required this.priceLabel,
    required this.plans,
  });

  factory PricingStrings.fromJson(Map<String, dynamic> json) => PricingStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        popular: json['popular'] as String,
        priceLabel: json['priceLabel'] as String,
        plans: (json['plans'] as List<dynamic>)
            .map((e) => PricingPlan.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String kicker;
  final String title;
  final String subtitle;
  final String popular;
  final String priceLabel;
  final List<PricingPlan> plans;
}

class FaqItem {
  const FaqItem({required this.question, required this.answer});

  factory FaqItem.fromJson(Map<String, dynamic> json) => FaqItem(
        question: json['question'] as String,
        answer: json['answer'] as String,
      );

  final String question;
  final String answer;
}

class FaqStrings {
  const FaqStrings({
    required this.kicker,
    required this.title,
    required this.subtitle,
    required this.contactCta,
    required this.items,
  });

  factory FaqStrings.fromJson(Map<String, dynamic> json) => FaqStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        contactCta: json['contactCta'] as String,
        items: (json['items'] as List<dynamic>)
            .map((e) => FaqItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String kicker;
  final String title;
  final String subtitle;
  final String contactCta;
  final List<FaqItem> items;
}

class FinalCtaStrings {
  const FinalCtaStrings({
    required this.label,
    required this.title,
    required this.tryFree,
    required this.scheduleDemo,
  });

  factory FinalCtaStrings.fromJson(Map<String, dynamic> json) => FinalCtaStrings(
        label: json['label'] as String,
        title: json['title'] as String,
        tryFree: json['tryFree'] as String,
        scheduleDemo: json['scheduleDemo'] as String,
      );

  final String label;
  final String title;
  final String tryFree;
  final String scheduleDemo;
}

class FooterStrings {
  const FooterStrings({
    required this.tagline,
    required this.platformTitle,
    required this.platformLinks,
    required this.companyTitle,
    required this.companyLinks,
    required this.resourcesTitle,
    required this.resourcesLinks,
    required this.copyright,
  });

  factory FooterStrings.fromJson(Map<String, dynamic> json) => FooterStrings(
        tagline: json['tagline'] as String,
        platformTitle: json['platformTitle'] as String,
        platformLinks: (json['platformLinks'] as List<dynamic>).cast<String>(),
        companyTitle: json['companyTitle'] as String,
        companyLinks: (json['companyLinks'] as List<dynamic>).cast<String>(),
        resourcesTitle: json['resourcesTitle'] as String,
        resourcesLinks: (json['resourcesLinks'] as List<dynamic>).cast<String>(),
        copyright: json['copyright'] as String,
      );

  final String tagline;
  final String platformTitle;
  final List<String> platformLinks;
  final String companyTitle;
  final List<String> companyLinks;
  final String resourcesTitle;
  final List<String> resourcesLinks;
  final String copyright;
}

/// Espace de travail client authentifié (sidebar, Connexions, Facturation,
/// Équipe, Paramètres, pages métier). Comme [AssistantStrings]/[AuthStrings] :
/// fr/en traduits, le reste retombe sur l'anglais via [CompanyStrings.fallback].
class CompanyStrings {
  const CompanyStrings({
    required this.navOverviewLabel,
    required this.navOverviewDescription,
    required this.navAssistantLabel,
    required this.navAssistantDescription,
    required this.navSalesLabel,
    required this.navSalesDescription,
    required this.navCustomersLabel,
    required this.navCustomersDescription,
    required this.navProductsLabel,
    required this.navProductsDescription,
    required this.navRecommendationsLabel,
    required this.navRecommendationsDescription,
    required this.navAlertsLabel,
    required this.navAlertsDescription,
    required this.navReportsLabel,
    required this.navReportsDescription,
    required this.navConnectionsLabel,
    required this.navConnectionsDescription,
    required this.navTeamLabel,
    required this.navTeamDescription,
    required this.navBillingLabel,
    required this.navBillingDescription,
    required this.navSettingsLabel,
    required this.navSettingsDescription,
    required this.navSupportLabel,
    required this.navSupportDescription,
    required this.connectionsLoading,
    required this.connectionsNoDataTitle,
    required this.connectionsNoDataFormats,
    required this.connectionsImportButton,
    required this.connectionsUploadingLabel,
    required this.connectionsAnalyzing,
    required this.connectionsPreparingData,
    required this.connectionsTrainingAi,
    required this.connectionsAttentionRequired,
    required this.connectionsMappingTitle,
    required this.connectionsMappingSubtitle,
    required this.connectionsMappingIgnore,
    required this.connectionsConfirmMapping,
    required this.connectionsReadyTitle,
    required this.connectionsStatNameLabel,
    required this.connectionsStatRowsLabel,
    required this.connectionsStatColumnsLabel,
    required this.connectionsStatUpdatedLabel,
    required this.connectionsGoDashboard,
    required this.connectionsAskAvenqo,
    required this.connectionsImportAnother,
    required this.connectionsRetry,
    required this.connectionsGenericError,
    required this.connectionsFileEmptyError,
    required this.connectionsProcessingError,
    required this.connectionsAddFiles,
    required this.connectionsAddMoreFiles,
    required this.connectionsReadyToUpload,
    required this.connectionsUploadCountOne,
    required this.connectionsUploadCountOther,
    required this.connectionsRemoveFile,
    required this.connectionsDuplicateFileNotice,
    required this.connectionsImportCompleteTitle,
    required this.connectionsImportSummarySuccessOne,
    required this.connectionsImportSummarySuccessOther,
    required this.connectionsImportSummaryErrorsOne,
    required this.connectionsImportSummaryErrorsOther,
    required this.connectionsMappingRequiredBadge,
    required this.connectionsCompleteMapping,
    required this.connectionsConnectedDataTitle,
    required this.connectionsContinueLabel,
    required this.connectionsImportedAtLabel,
    required this.connectionsUploadedFileSuccessLabel,
    required this.businessDefaultTitle,
    required this.businessDefaultDescription,
    required this.businessConnectButton,
    required this.businessSalesTitle,
    required this.businessSalesDescription,
    required this.businessCustomersTitle,
    required this.businessCustomersDescription,
    required this.analyticsUnavailable,
    required this.periodCurrentMonth,
    required this.periodLast30Days,
    required this.periodLast90Days,
    required this.periodYearToDate,
    required this.salesTrendTitle,
    required this.salesForecastTitle,
    required this.salesStrongestPeriod,
    required this.salesWeakestPeriod,
    required this.customersTotal,
    required this.customersActive,
    required this.customersNew,
    required this.customersRepeat,
    required this.customersAverageValue,
    required this.customersFrequency,
    required this.customersSearch,
    required this.customersOrders,
    required this.customersValue,
    required this.customersLastPurchase,
    required this.customersSegment,
    required this.customersRisk,
    required this.previousPage,
    required this.nextPage,
    required this.businessProductsTitle,
    required this.businessProductsDescription,
    required this.businessRecommendationsTitle,
    required this.businessRecommendationsDescription,
    required this.businessAlertsTitle,
    required this.businessAlertsDescription,
    required this.businessReportsTitle,
    required this.businessReportsDescription,
    required this.billingTitle,
    required this.billingPortalButton,
    required this.billingUnavailable,
    required this.billingPlanPrefix,
    required this.billingStatusPrefix,
    required this.billingCancelScheduled,
    required this.billingInvoicesTitle,
    required this.billingInvoiceFallback,
    required this.employeesTitle,
    required this.employeesRefreshTooltip,
    required this.employeesUnavailable,
    required this.employeesColumnName,
    required this.employeesColumnEmail,
    required this.employeesColumnRole,
    required this.employeesColumnStatus,
    required this.settingsTitle,
    required this.settingsSubtitle,
    required this.settingsAccountSection,
    required this.settingsCompanySection,
    required this.settingsAppearanceSection,
    required this.settingsSessionSection,
    required this.settingsNameLabel,
    required this.settingsEmailLabel,
    required this.settingsRoleLabel,
    required this.settingsPlanLabel,
    required this.settingsManageSubscription,
    required this.settingsThemeLabel,
    required this.settingsLanguageLabel,
    required this.settingsThemeLight,
    required this.settingsThemeDark,
    required this.settingsThemeSystem,
    required this.settingsLogout,
    required this.themeToggleSwitchToDark,
    required this.themeToggleSwitchToLight,
  });

  factory CompanyStrings.fromJson(Map<String, dynamic> json) {
    final fallback = CompanyStrings.fallback();
    String s(String key) => json[key] as String? ?? fallback._byKey(key);
    return CompanyStrings(
      navOverviewLabel: s('navOverviewLabel'),
      navOverviewDescription: s('navOverviewDescription'),
      navAssistantLabel: s('navAssistantLabel'),
      navAssistantDescription: s('navAssistantDescription'),
      navSalesLabel: s('navSalesLabel'),
      navSalesDescription: s('navSalesDescription'),
      navCustomersLabel: s('navCustomersLabel'),
      navCustomersDescription: s('navCustomersDescription'),
      navProductsLabel: s('navProductsLabel'),
      navProductsDescription: s('navProductsDescription'),
      navRecommendationsLabel: s('navRecommendationsLabel'),
      navRecommendationsDescription: s('navRecommendationsDescription'),
      navAlertsLabel: s('navAlertsLabel'),
      navAlertsDescription: s('navAlertsDescription'),
      navReportsLabel: s('navReportsLabel'),
      navReportsDescription: s('navReportsDescription'),
      navConnectionsLabel: s('navConnectionsLabel'),
      navConnectionsDescription: s('navConnectionsDescription'),
      navTeamLabel: s('navTeamLabel'),
      navTeamDescription: s('navTeamDescription'),
      navBillingLabel: s('navBillingLabel'),
      navBillingDescription: s('navBillingDescription'),
      navSettingsLabel: s('navSettingsLabel'),
      navSettingsDescription: s('navSettingsDescription'),
      navSupportLabel: s('navSupportLabel'),
      navSupportDescription: s('navSupportDescription'),
      connectionsLoading: s('connectionsLoading'),
      connectionsNoDataTitle: s('connectionsNoDataTitle'),
      connectionsNoDataFormats: s('connectionsNoDataFormats'),
      connectionsImportButton: s('connectionsImportButton'),
      connectionsUploadingLabel: s('connectionsUploadingLabel'),
      connectionsAnalyzing: s('connectionsAnalyzing'),
      connectionsPreparingData: s('connectionsPreparingData'),
      connectionsTrainingAi: s('connectionsTrainingAi'),
      connectionsAttentionRequired: s('connectionsAttentionRequired'),
      connectionsMappingTitle: s('connectionsMappingTitle'),
      connectionsMappingSubtitle: s('connectionsMappingSubtitle'),
      connectionsMappingIgnore: s('connectionsMappingIgnore'),
      connectionsConfirmMapping: s('connectionsConfirmMapping'),
      connectionsReadyTitle: s('connectionsReadyTitle'),
      connectionsStatNameLabel: s('connectionsStatNameLabel'),
      connectionsStatRowsLabel: s('connectionsStatRowsLabel'),
      connectionsStatColumnsLabel: s('connectionsStatColumnsLabel'),
      connectionsStatUpdatedLabel: s('connectionsStatUpdatedLabel'),
      connectionsGoDashboard: s('connectionsGoDashboard'),
      connectionsAskAvenqo: s('connectionsAskAvenqo'),
      connectionsImportAnother: s('connectionsImportAnother'),
      connectionsRetry: s('connectionsRetry'),
      connectionsGenericError: s('connectionsGenericError'),
      connectionsFileEmptyError: s('connectionsFileEmptyError'),
      connectionsProcessingError: s('connectionsProcessingError'),
      connectionsAddFiles: s('connectionsAddFiles'),
      connectionsAddMoreFiles: s('connectionsAddMoreFiles'),
      connectionsReadyToUpload: s('connectionsReadyToUpload'),
      connectionsUploadCountOne: s('connectionsUploadCountOne'),
      connectionsUploadCountOther: s('connectionsUploadCountOther'),
      connectionsRemoveFile: s('connectionsRemoveFile'),
      connectionsDuplicateFileNotice: s('connectionsDuplicateFileNotice'),
      connectionsImportCompleteTitle: s('connectionsImportCompleteTitle'),
      connectionsImportSummarySuccessOne: s('connectionsImportSummarySuccessOne'),
      connectionsImportSummarySuccessOther: s('connectionsImportSummarySuccessOther'),
      connectionsImportSummaryErrorsOne: s('connectionsImportSummaryErrorsOne'),
      connectionsImportSummaryErrorsOther: s('connectionsImportSummaryErrorsOther'),
      connectionsMappingRequiredBadge: s('connectionsMappingRequiredBadge'),
      connectionsCompleteMapping: s('connectionsCompleteMapping'),
      connectionsConnectedDataTitle: s('connectionsConnectedDataTitle'),
      connectionsContinueLabel: s('connectionsContinueLabel'),
      connectionsImportedAtLabel: s('connectionsImportedAtLabel'),
      connectionsUploadedFileSuccessLabel: s('connectionsUploadedFileSuccessLabel'),
      businessDefaultTitle: s('businessDefaultTitle'),
      businessDefaultDescription: s('businessDefaultDescription'),
      businessConnectButton: s('businessConnectButton'),
      businessSalesTitle: s('businessSalesTitle'),
      businessSalesDescription: s('businessSalesDescription'),
      businessCustomersTitle: s('businessCustomersTitle'),
      businessCustomersDescription: s('businessCustomersDescription'),
      analyticsUnavailable: s('analyticsUnavailable'),
      periodCurrentMonth: s('periodCurrentMonth'),
      periodLast30Days: s('periodLast30Days'),
      periodLast90Days: s('periodLast90Days'),
      periodYearToDate: s('periodYearToDate'),
      salesTrendTitle: s('salesTrendTitle'),
      salesForecastTitle: s('salesForecastTitle'),
      salesStrongestPeriod: s('salesStrongestPeriod'),
      salesWeakestPeriod: s('salesWeakestPeriod'),
      customersTotal: s('customersTotal'),
      customersActive: s('customersActive'),
      customersNew: s('customersNew'),
      customersRepeat: s('customersRepeat'),
      customersAverageValue: s('customersAverageValue'),
      customersFrequency: s('customersFrequency'),
      customersSearch: s('customersSearch'),
      customersOrders: s('customersOrders'),
      customersValue: s('customersValue'),
      customersLastPurchase: s('customersLastPurchase'),
      customersSegment: s('customersSegment'),
      customersRisk: s('customersRisk'),
      previousPage: s('previousPage'),
      nextPage: s('nextPage'),
      businessProductsTitle: s('businessProductsTitle'),
      businessProductsDescription: s('businessProductsDescription'),
      businessRecommendationsTitle: s('businessRecommendationsTitle'),
      businessRecommendationsDescription: s('businessRecommendationsDescription'),
      businessAlertsTitle: s('businessAlertsTitle'),
      businessAlertsDescription: s('businessAlertsDescription'),
      businessReportsTitle: s('businessReportsTitle'),
      businessReportsDescription: s('businessReportsDescription'),
      billingTitle: s('billingTitle'),
      billingPortalButton: s('billingPortalButton'),
      billingUnavailable: s('billingUnavailable'),
      billingPlanPrefix: s('billingPlanPrefix'),
      billingStatusPrefix: s('billingStatusPrefix'),
      billingCancelScheduled: s('billingCancelScheduled'),
      billingInvoicesTitle: s('billingInvoicesTitle'),
      billingInvoiceFallback: s('billingInvoiceFallback'),
      employeesTitle: s('employeesTitle'),
      employeesRefreshTooltip: s('employeesRefreshTooltip'),
      employeesUnavailable: s('employeesUnavailable'),
      employeesColumnName: s('employeesColumnName'),
      employeesColumnEmail: s('employeesColumnEmail'),
      employeesColumnRole: s('employeesColumnRole'),
      employeesColumnStatus: s('employeesColumnStatus'),
      settingsTitle: s('settingsTitle'),
      settingsSubtitle: s('settingsSubtitle'),
      settingsAccountSection: s('settingsAccountSection'),
      settingsCompanySection: s('settingsCompanySection'),
      settingsAppearanceSection: s('settingsAppearanceSection'),
      settingsSessionSection: s('settingsSessionSection'),
      settingsNameLabel: s('settingsNameLabel'),
      settingsEmailLabel: s('settingsEmailLabel'),
      settingsRoleLabel: s('settingsRoleLabel'),
      settingsPlanLabel: s('settingsPlanLabel'),
      settingsManageSubscription: s('settingsManageSubscription'),
      settingsThemeLabel: s('settingsThemeLabel'),
      settingsLanguageLabel: s('settingsLanguageLabel'),
      settingsThemeLight: s('settingsThemeLight'),
      settingsThemeDark: s('settingsThemeDark'),
      settingsThemeSystem: s('settingsThemeSystem'),
      settingsLogout: s('settingsLogout'),
      themeToggleSwitchToDark: s('themeToggleSwitchToDark'),
      themeToggleSwitchToLight: s('themeToggleSwitchToLight'),
    );
  }

  factory CompanyStrings.fallback() => const CompanyStrings(
        navOverviewLabel: 'Overview',
        navOverviewDescription: 'The key indicators of your business.',
        navAssistantLabel: 'AI Assistant',
        navAssistantDescription: 'Ask questions and take action.',
        navSalesLabel: 'Sales',
        navSalesDescription: 'Track revenue and trends.',
        navCustomersLabel: 'Customers',
        navCustomersDescription: 'Understand loyalty and churn risk.',
        navProductsLabel: 'Products',
        navProductsDescription: 'Monitor demand and catalog performance.',
        navRecommendationsLabel: 'Recommendations',
        navRecommendationsDescription: 'Find the highest priority opportunities.',
        navAlertsLabel: 'Alerts',
        navAlertsDescription: 'Watch for changes that need your attention.',
        navReportsLabel: 'Reports',
        navReportsDescription: 'View and share your executive summaries.',
        navConnectionsLabel: 'Connections',
        navConnectionsDescription: 'Connect your sales and management tools.',
        navTeamLabel: 'Team',
        navTeamDescription: "Manage your teammates' access.",
        navBillingLabel: 'Billing',
        navBillingDescription: 'Manage your subscription and invoices.',
        navSettingsLabel: 'Settings',
        navSettingsDescription: 'Your account and company preferences.',
        navSupportLabel: 'Avenqo Support',
        navSupportDescription: 'Need help using Avenqo? Ask your question here.',
        connectionsLoading: 'Loading…',
        connectionsNoDataTitle: 'Connect your data to unlock analytics and Avenqo AI.',
        connectionsNoDataFormats: 'Accepted formats: CSV, XLSX, JSON, Parquet.',
        connectionsImportButton: 'Import a file',
        connectionsUploadingLabel: 'Uploading…',
        connectionsAnalyzing: 'Analyzing the structure of your data…',
        connectionsPreparingData: 'Preparing data…',
        connectionsTrainingAi: 'Training AI…',
        connectionsAttentionRequired: 'Attention required',
        connectionsMappingTitle: 'Confirm your column mapping',
        connectionsMappingSubtitle: 'Some columns need manual confirmation before analytics can be activated.',
        connectionsMappingIgnore: 'Ignore this column',
        connectionsConfirmMapping: 'Confirm mapping',
        connectionsReadyTitle: 'Data ready',
        connectionsStatNameLabel: 'Name',
        connectionsStatRowsLabel: 'Rows',
        connectionsStatColumnsLabel: 'Columns',
        connectionsStatUpdatedLabel: 'Last updated',
        connectionsGoDashboard: 'Go to dashboard',
        connectionsAskAvenqo: 'Ask Avenqo AI',
        connectionsImportAnother: 'Import another dataset',
        connectionsRetry: 'Retry',
        connectionsGenericError: 'An unexpected error occurred.',
        connectionsFileEmptyError: 'The selected file is empty or unreadable.',
        connectionsProcessingError: 'This file could not be processed.',
        connectionsAddFiles: 'Add files',
        connectionsAddMoreFiles: 'Add more files',
        connectionsReadyToUpload: 'Ready to upload',
        connectionsUploadCountOne: 'Upload {n} file',
        connectionsUploadCountOther: 'Upload {n} files',
        connectionsRemoveFile: 'Remove',
        connectionsDuplicateFileNotice: 'This file is already selected.',
        connectionsImportCompleteTitle: 'Import complete',
        connectionsImportSummarySuccessOne: '{n} file imported successfully.',
        connectionsImportSummarySuccessOther: '{n} files imported successfully.',
        connectionsImportSummaryErrorsOne: '{n} file failed.',
        connectionsImportSummaryErrorsOther: '{n} files failed.',
        connectionsMappingRequiredBadge: 'Mapping required',
        connectionsCompleteMapping: 'Complete mapping',
        connectionsConnectedDataTitle: 'Connected data',
        connectionsContinueLabel: 'Continue',
        connectionsImportedAtLabel: 'Imported',
        connectionsUploadedFileSuccessLabel: 'Data imported successfully',
        businessDefaultTitle: 'Your space is ready',
        businessDefaultDescription: 'Connect your tools to see up-to-date information here.',
        businessConnectButton: 'Connect my tools',
        businessSalesTitle: 'Track every change',
        businessSalesDescription: 'Your sales trends, comparisons and forecasts will appear here.',
        businessCustomersTitle: 'Retain the right customers',
        businessCustomersDescription: "You'll find customers to prioritize, re-engage or support here.",
        analyticsUnavailable: 'This capability is unavailable with your current business data.',
        periodCurrentMonth: 'Current month',
        periodLast30Days: 'Last 30 days',
        periodLast90Days: 'Last 90 days',
        periodYearToDate: 'Year to date',
        salesTrendTitle: 'Revenue trend',
        salesForecastTitle: 'Validated sales forecast',
        salesStrongestPeriod: 'Strongest period',
        salesWeakestPeriod: 'Weakest period',
        customersTotal: 'Total customers',
        customersActive: 'Active customers',
        customersNew: 'New customers',
        customersRepeat: 'Repeat customers',
        customersAverageValue: 'Average customer value',
        customersFrequency: 'Purchase frequency',
        customersSearch: 'Search customers',
        customersOrders: 'Orders',
        customersValue: 'Value',
        customersLastPurchase: 'Last purchase',
        customersSegment: 'Segment',
        customersRisk: 'Risk',
        previousPage: 'Previous',
        nextPage: 'Next',
        businessProductsTitle: 'Manage your catalog',
        businessProductsDescription: 'Top-performing products, expected demand and stock to watch will be gathered here.',
        businessRecommendationsTitle: 'Act directly on opportunities',
        businessRecommendationsDescription: "Avenqo will rank opportunities by their potential impact on your business.",
        businessAlertsTitle: 'Stay informed without the noise',
        businessAlertsDescription: 'Important changes and risks will be flagged with a recommended action.',
        businessReportsTitle: 'Your executive summaries',
        businessReportsDescription: "Create and share clear reports on your company's results.",
        billingTitle: 'Billing',
        billingPortalButton: 'Stripe portal',
        billingUnavailable: 'Billing is temporarily unavailable.',
        billingPlanPrefix: 'Plan ',
        billingStatusPrefix: 'Status: ',
        billingCancelScheduled: 'Cancellation scheduled',
        billingInvoicesTitle: 'Invoices',
        billingInvoiceFallback: 'Invoice',
        employeesTitle: 'Users',
        employeesRefreshTooltip: 'Refresh',
        employeesUnavailable: 'User access is temporarily unavailable.',
        employeesColumnName: 'Name',
        employeesColumnEmail: 'Email',
        employeesColumnRole: 'Role',
        employeesColumnStatus: 'Status',
        settingsTitle: 'Settings',
        settingsSubtitle: 'Your account, company and preference information.',
        settingsAccountSection: 'Account',
        settingsCompanySection: 'Company',
        settingsAppearanceSection: 'Appearance',
        settingsSessionSection: 'Session',
        settingsNameLabel: 'Name',
        settingsEmailLabel: 'Email',
        settingsRoleLabel: 'Role',
        settingsPlanLabel: 'Plan',
        settingsManageSubscription: 'Manage subscription',
        settingsThemeLabel: 'Theme',
        settingsLanguageLabel: 'Language',
        settingsThemeLight: 'Light',
        settingsThemeDark: 'Dark',
        settingsThemeSystem: 'System',
        settingsLogout: 'Log out',
        themeToggleSwitchToDark: 'Switch to dark mode',
        themeToggleSwitchToLight: 'Switch to light mode',
      );

  String _byKey(String key) => switch (key) {
        'navOverviewLabel' => navOverviewLabel,
        'navOverviewDescription' => navOverviewDescription,
        'navAssistantLabel' => navAssistantLabel,
        'navAssistantDescription' => navAssistantDescription,
        'navSalesLabel' => navSalesLabel,
        'navSalesDescription' => navSalesDescription,
        'navCustomersLabel' => navCustomersLabel,
        'navCustomersDescription' => navCustomersDescription,
        'navProductsLabel' => navProductsLabel,
        'navProductsDescription' => navProductsDescription,
        'navRecommendationsLabel' => navRecommendationsLabel,
        'navRecommendationsDescription' => navRecommendationsDescription,
        'navAlertsLabel' => navAlertsLabel,
        'navAlertsDescription' => navAlertsDescription,
        'navReportsLabel' => navReportsLabel,
        'navReportsDescription' => navReportsDescription,
        'navConnectionsLabel' => navConnectionsLabel,
        'navConnectionsDescription' => navConnectionsDescription,
        'navTeamLabel' => navTeamLabel,
        'navTeamDescription' => navTeamDescription,
        'navBillingLabel' => navBillingLabel,
        'navBillingDescription' => navBillingDescription,
        'navSettingsLabel' => navSettingsLabel,
        'navSettingsDescription' => navSettingsDescription,
        'navSupportLabel' => navSupportLabel,
        'navSupportDescription' => navSupportDescription,
        'connectionsLoading' => connectionsLoading,
        'connectionsNoDataTitle' => connectionsNoDataTitle,
        'connectionsNoDataFormats' => connectionsNoDataFormats,
        'connectionsImportButton' => connectionsImportButton,
        'connectionsUploadingLabel' => connectionsUploadingLabel,
        'connectionsAnalyzing' => connectionsAnalyzing,
        'connectionsPreparingData' => connectionsPreparingData,
        'connectionsTrainingAi' => connectionsTrainingAi,
        'connectionsAttentionRequired' => connectionsAttentionRequired,
        'connectionsMappingTitle' => connectionsMappingTitle,
        'connectionsMappingSubtitle' => connectionsMappingSubtitle,
        'connectionsMappingIgnore' => connectionsMappingIgnore,
        'connectionsConfirmMapping' => connectionsConfirmMapping,
        'connectionsReadyTitle' => connectionsReadyTitle,
        'connectionsStatNameLabel' => connectionsStatNameLabel,
        'connectionsStatRowsLabel' => connectionsStatRowsLabel,
        'connectionsStatColumnsLabel' => connectionsStatColumnsLabel,
        'connectionsStatUpdatedLabel' => connectionsStatUpdatedLabel,
        'connectionsGoDashboard' => connectionsGoDashboard,
        'connectionsAskAvenqo' => connectionsAskAvenqo,
        'connectionsImportAnother' => connectionsImportAnother,
        'connectionsRetry' => connectionsRetry,
        'connectionsGenericError' => connectionsGenericError,
        'connectionsFileEmptyError' => connectionsFileEmptyError,
        'connectionsProcessingError' => connectionsProcessingError,
        'connectionsAddFiles' => connectionsAddFiles,
        'connectionsAddMoreFiles' => connectionsAddMoreFiles,
        'connectionsReadyToUpload' => connectionsReadyToUpload,
        'connectionsUploadCountOne' => connectionsUploadCountOne,
        'connectionsUploadCountOther' => connectionsUploadCountOther,
        'connectionsRemoveFile' => connectionsRemoveFile,
        'connectionsDuplicateFileNotice' => connectionsDuplicateFileNotice,
        'connectionsImportCompleteTitle' => connectionsImportCompleteTitle,
        'connectionsImportSummarySuccessOne' => connectionsImportSummarySuccessOne,
        'connectionsImportSummarySuccessOther' => connectionsImportSummarySuccessOther,
        'connectionsImportSummaryErrorsOne' => connectionsImportSummaryErrorsOne,
        'connectionsImportSummaryErrorsOther' => connectionsImportSummaryErrorsOther,
        'connectionsMappingRequiredBadge' => connectionsMappingRequiredBadge,
        'connectionsCompleteMapping' => connectionsCompleteMapping,
        'connectionsConnectedDataTitle' => connectionsConnectedDataTitle,
        'connectionsContinueLabel' => connectionsContinueLabel,
        'connectionsImportedAtLabel' => connectionsImportedAtLabel,
        'connectionsUploadedFileSuccessLabel' => connectionsUploadedFileSuccessLabel,
        'businessDefaultTitle' => businessDefaultTitle,
        'businessDefaultDescription' => businessDefaultDescription,
        'businessConnectButton' => businessConnectButton,
        'businessSalesTitle' => businessSalesTitle,
        'businessSalesDescription' => businessSalesDescription,
        'businessCustomersTitle' => businessCustomersTitle,
        'businessCustomersDescription' => businessCustomersDescription,
        'analyticsUnavailable' => analyticsUnavailable,
        'periodCurrentMonth' => periodCurrentMonth,
        'periodLast30Days' => periodLast30Days,
        'periodLast90Days' => periodLast90Days,
        'periodYearToDate' => periodYearToDate,
        'salesTrendTitle' => salesTrendTitle,
        'salesForecastTitle' => salesForecastTitle,
        'salesStrongestPeriod' => salesStrongestPeriod,
        'salesWeakestPeriod' => salesWeakestPeriod,
        'customersTotal' => customersTotal,
        'customersActive' => customersActive,
        'customersNew' => customersNew,
        'customersRepeat' => customersRepeat,
        'customersAverageValue' => customersAverageValue,
        'customersFrequency' => customersFrequency,
        'customersSearch' => customersSearch,
        'customersOrders' => customersOrders,
        'customersValue' => customersValue,
        'customersLastPurchase' => customersLastPurchase,
        'customersSegment' => customersSegment,
        'customersRisk' => customersRisk,
        'previousPage' => previousPage,
        'nextPage' => nextPage,
        'businessProductsTitle' => businessProductsTitle,
        'businessProductsDescription' => businessProductsDescription,
        'businessRecommendationsTitle' => businessRecommendationsTitle,
        'businessRecommendationsDescription' => businessRecommendationsDescription,
        'businessAlertsTitle' => businessAlertsTitle,
        'businessAlertsDescription' => businessAlertsDescription,
        'businessReportsTitle' => businessReportsTitle,
        'businessReportsDescription' => businessReportsDescription,
        'billingTitle' => billingTitle,
        'billingPortalButton' => billingPortalButton,
        'billingUnavailable' => billingUnavailable,
        'billingPlanPrefix' => billingPlanPrefix,
        'billingStatusPrefix' => billingStatusPrefix,
        'billingCancelScheduled' => billingCancelScheduled,
        'billingInvoicesTitle' => billingInvoicesTitle,
        'billingInvoiceFallback' => billingInvoiceFallback,
        'employeesTitle' => employeesTitle,
        'employeesRefreshTooltip' => employeesRefreshTooltip,
        'employeesUnavailable' => employeesUnavailable,
        'employeesColumnName' => employeesColumnName,
        'employeesColumnEmail' => employeesColumnEmail,
        'employeesColumnRole' => employeesColumnRole,
        'employeesColumnStatus' => employeesColumnStatus,
        'settingsTitle' => settingsTitle,
        'settingsSubtitle' => settingsSubtitle,
        'settingsAccountSection' => settingsAccountSection,
        'settingsCompanySection' => settingsCompanySection,
        'settingsAppearanceSection' => settingsAppearanceSection,
        'settingsSessionSection' => settingsSessionSection,
        'settingsNameLabel' => settingsNameLabel,
        'settingsEmailLabel' => settingsEmailLabel,
        'settingsRoleLabel' => settingsRoleLabel,
        'settingsPlanLabel' => settingsPlanLabel,
        'settingsManageSubscription' => settingsManageSubscription,
        'settingsThemeLabel' => settingsThemeLabel,
        'settingsLanguageLabel' => settingsLanguageLabel,
        'settingsThemeLight' => settingsThemeLight,
        'settingsThemeDark' => settingsThemeDark,
        'settingsThemeSystem' => settingsThemeSystem,
        'settingsLogout' => settingsLogout,
        'themeToggleSwitchToDark' => themeToggleSwitchToDark,
        'themeToggleSwitchToLight' => themeToggleSwitchToLight,
        _ => '',
      };

  final String navOverviewLabel;
  final String navOverviewDescription;
  final String navAssistantLabel;
  final String navAssistantDescription;
  final String navSalesLabel;
  final String navSalesDescription;
  final String navCustomersLabel;
  final String navCustomersDescription;
  final String navProductsLabel;
  final String navProductsDescription;
  final String navRecommendationsLabel;
  final String navRecommendationsDescription;
  final String navAlertsLabel;
  final String navAlertsDescription;
  final String navReportsLabel;
  final String navReportsDescription;
  final String navConnectionsLabel;
  final String navConnectionsDescription;
  final String navTeamLabel;
  final String navTeamDescription;
  final String navBillingLabel;
  final String navBillingDescription;
  final String navSettingsLabel;
  final String navSettingsDescription;
  final String navSupportLabel;
  final String navSupportDescription;
  final String connectionsLoading;
  final String connectionsNoDataTitle;
  final String connectionsNoDataFormats;
  final String connectionsImportButton;
  final String connectionsUploadingLabel;
  final String connectionsAnalyzing;
  final String connectionsPreparingData;
  final String connectionsTrainingAi;
  final String connectionsAttentionRequired;
  final String connectionsMappingTitle;
  final String connectionsMappingSubtitle;
  final String connectionsMappingIgnore;
  final String connectionsConfirmMapping;
  final String connectionsReadyTitle;
  final String connectionsStatNameLabel;
  final String connectionsStatRowsLabel;
  final String connectionsStatColumnsLabel;
  final String connectionsStatUpdatedLabel;
  final String connectionsGoDashboard;
  final String connectionsAskAvenqo;
  final String connectionsImportAnother;
  final String connectionsRetry;
  final String connectionsGenericError;
  final String connectionsFileEmptyError;
  final String connectionsProcessingError;
  final String connectionsAddFiles;
  final String connectionsAddMoreFiles;
  final String connectionsReadyToUpload;
  final String connectionsUploadCountOne;
  final String connectionsUploadCountOther;
  final String connectionsRemoveFile;
  final String connectionsDuplicateFileNotice;
  final String connectionsImportCompleteTitle;
  final String connectionsImportSummarySuccessOne;
  final String connectionsImportSummarySuccessOther;
  final String connectionsImportSummaryErrorsOne;
  final String connectionsImportSummaryErrorsOther;
  final String connectionsMappingRequiredBadge;
  final String connectionsCompleteMapping;
  final String connectionsConnectedDataTitle;
  final String connectionsContinueLabel;
  final String connectionsImportedAtLabel;
  final String connectionsUploadedFileSuccessLabel;
  final String businessDefaultTitle;
  final String businessDefaultDescription;
  final String businessConnectButton;
  final String businessSalesTitle;
  final String businessSalesDescription;
  final String businessCustomersTitle;
  final String businessCustomersDescription;
  final String analyticsUnavailable;
  final String periodCurrentMonth;
  final String periodLast30Days;
  final String periodLast90Days;
  final String periodYearToDate;
  final String salesTrendTitle;
  final String salesForecastTitle;
  final String salesStrongestPeriod;
  final String salesWeakestPeriod;
  final String customersTotal;
  final String customersActive;
  final String customersNew;
  final String customersRepeat;
  final String customersAverageValue;
  final String customersFrequency;
  final String customersSearch;
  final String customersOrders;
  final String customersValue;
  final String customersLastPurchase;
  final String customersSegment;
  final String customersRisk;
  final String previousPage;
  final String nextPage;
  final String businessProductsTitle;
  final String businessProductsDescription;
  final String businessRecommendationsTitle;
  final String businessRecommendationsDescription;
  final String businessAlertsTitle;
  final String businessAlertsDescription;
  final String businessReportsTitle;
  final String businessReportsDescription;
  final String billingTitle;
  final String billingPortalButton;
  final String billingUnavailable;
  final String billingPlanPrefix;
  final String billingStatusPrefix;
  final String billingCancelScheduled;
  final String billingInvoicesTitle;
  final String billingInvoiceFallback;
  final String employeesTitle;
  final String employeesRefreshTooltip;
  final String employeesUnavailable;
  final String employeesColumnName;
  final String employeesColumnEmail;
  final String employeesColumnRole;
  final String employeesColumnStatus;
  final String settingsTitle;
  final String settingsSubtitle;
  final String settingsAccountSection;
  final String settingsCompanySection;
  final String settingsAppearanceSection;
  final String settingsSessionSection;
  final String settingsNameLabel;
  final String settingsEmailLabel;
  final String settingsRoleLabel;
  final String settingsPlanLabel;
  final String settingsManageSubscription;
  final String settingsThemeLabel;
  final String settingsLanguageLabel;
  final String settingsThemeLight;
  final String settingsThemeDark;
  final String settingsThemeSystem;
  final String settingsLogout;
  final String themeToggleSwitchToDark;
  final String themeToggleSwitchToLight;
}

