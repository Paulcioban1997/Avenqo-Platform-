Warning: truncated output (original token count: 32502)
Total output lines: 3292

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
      dashboard: DashboardStrings.fromJson(
        json['dashboard'] as Map<String, dynamic>,
      ),
      features: FeaturesStrings.fromJson(
        json['features'] as Map<String, dynamic>,
      ),
      modulesSection: ModulesSectionStrings.fromJson(
        json['modulesSection'] as Map<String, dynamic>,
      ),
      steps: StepsStrings.fromJson(json['steps'] as Map<String, dynamic>),
      usecases: UsecasesStrings.fromJson(
        json['usecases'] as Map<String, dynamic>,
      ),
      why: WhyStrings.fromJson(json['why'] as Map<String, dynamic>),
      pricing: PricingStrings.fromJson(json['pricing'] as Map<String, dynamic>),
      faq: FaqStrings.fromJson(json['faq'] as Map<String, dynamic>),
      finalCta: FinalCtaStrings.fromJson(
        json['finalCta'] as Map<String, dynamic>,
      ),
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
          ? DashboardHomeStrings.fromJson(
              json['dashboardHome'] as Map<String, dynamic>,
            )
          : DashboardHomeStrings.fallback(),
      // Même logique de repli que assistant/auth/dashboardHome : fr/en traduits,
      // le reste en anglais.
      admin: json['admin'] != null
          ? AdminStrings.fromJson(json['admin'] as Map<String, dynamic>)
          : AdminStrings.fallback(),
      // Même logique de repli : fr/en traduits, le reste en anglais.
      onboarding: json['onboarding'] != null
          ? OnboardingStrings.fromJson(
              json['onboarding'] as Map<String, dynamic>,
            )
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

  factory AgentStrings.fromJson(Map<String, dynamic> json) =>
      AgentStrings(json.map((key, value) => MapEntry(key, value as String)));

  factory AgentStrings.fallback() => const AgentStrings({
    'navLabel': 'Agents',
    'title': 'Avenqo Agents',
    'subtitle':
        'Specialized business capabilities, connected in one workspace.',
    'availableNow': 'Available now',
    'comingSoon': 'Coming Soon',
    'openAgent': 'Open agent',
    'adminTitle': 'Agent Catalog',
    'adminSubtitle': 'Platform capabilities and their current availability.',
    'availableCount': 'Available agents',
    'comingSoonCount': 'Coming Soon agents',
    'retailName': 'Retail Intelligence',
    'retailDescription':
        'Operate sales, customers, products, recommendations, and retail analytics.',
    'marketingName': 'Marketing AI',
    'marketingDescription':
        'Prepare campaigns, audiences, and measurable growth actions.',
    'crmName': 'CRM AI',
    'crmDescription':
        'Prioritize relationships, opportunities, and next best actions.',
    'hrName': 'HR AI',
    'hrDescription':
        'Support people operations, workforce insights, and employee workflows.',
    'accountingName': 'Accounting AI',
    'accountingDescription':
        'Accelerate financial operations, controls, and reporting workflows.',
    'ocrName': 'OCR AI',
    'ocrDescription':
        'Turn business documents into structured, usable information.',
    'voiceName': 'Voice AI',
    'voiceDescription':
        'Prepare intelligent voice interactions connected to business context.',
    'mediaName': 'Media AI',
    'mediaDescription':
        'Create, organize, and manage business media workflows.',
    'legalName': 'Legal AI',
    'legalDescription':
        'Support contract analysis and controlled legal-document workflows.',
    'appointmentsName': 'Appointments AI',
    'appointmentsDescription':
        'Coordinate bookings and availability across service-based businesses.',
    'workflowName': 'Workflow Automation',
    'workflowDescription':
        'Connect repeatable tasks, approvals, and business processes.',
    'retailOverviewLabel': 'Overview',
    'retailSalesLabel': 'Sales',
    'retailCustomersLabel': 'Customers',
    'retailProductsLabel': 'Products',
    'retailRecommendationsLabel': 'Recommendations',
    'adminRetailSubtitle':
        'Manage sales, products, loyalty, and retail analytics from one view.',
    'adminSelectTenantTitle': 'Select company',
    'adminSelectTenantSubtitle':
        'Choose a company before accessing Retail Intelligence.',
    'loadTenantsError': 'Companies could not be loaded.',
    'operationalAccessUnavailable':
        'Operational Retail data remains protected until an authorized tenant context is available.',
    'noTenants': 'No companies available.',
    'selectTenantAction': 'Select company',
    'selectedTenant': 'Selected company',
    'viewCompanyDetails': 'View company details',
    'adminViewLabel': 'Admin view — Company',
    'switchCompany': 'Switch company',
    'exitTenantView': 'Exit tenant view',
    'tenantContextError': 'The tenant context could not be validated.',
  });

  final Map<String, String> values;

  String value(String key) =>
      values[key] ?? AgentStrings.fallback().values[key] ?? key;
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
    required this.billing,
  });

  factory Phase4eStrings.fromJson(Map<String, dynamic> json) {
    final fallback = Phase4eStrings.fallback();
    String value(String key, String fallbackValue) =>
        json[key] is String ? json[key] as String : fallbackValue;
    final localizedBilling = json['billing'] is Map<String, dynamic>
        ? json['billing'] as Map<String, dynamic>
        : const <String, dynamic>{};
    final billing = <String, String>{...fallback.billing};
    for (final entry in localizedBilling.entries) {
      if (entry.value is String) billing[entry.key] = entry.value as String;
    }
    return Phase4eStrings(
      creditsTitle: value('creditsTitle', fallback.creditsTitle),
      creditsSubtitle: value('creditsSubtitle', fallback.creditsSubtitle),
      monthlyAllowance: value('monthlyAllowance', fallback.monthlyAllowance),
      monthlyRemaining: value('monthlyRemaining', fallback.monthlyRemaining),
      purchasedRemaining: value(
        'purchasedRemaining',
        fallback.purchasedRemaining,
      ),
      totalRemaining: value('totalRemaining', fallback.totalRemaining),
      billingPeriod: value('billingPeriod', fallback.billingPeriod),
      monthlyProgress: value('monthlyProgress', fallback.monthlyProgress),
      customAllowance: value('customAllowance', fallback.customAllowance),
      resetExplanation: value('resetExplanation', fallback.resetExplanation),
      packsTitle: value('packsTitle', fallback.packsTitle),
      packsSubtitle: value('packsSubtitle', fallback.packsSubtitle),
      creditsUnit: value('creditsUnit', fallback.creditsUnit),
      purchase: value('purchase', fallback.purchase),
      purchaseRequiresActive: value(
        'purchaseRequiresActive',
        fallback.purchaseRequiresActive,
      ),
      priceUsd: value('priceUsd', fallback.priceUsd),
      adminSubtitle: value('adminSubtitle', fallback.adminSubtitle),
      company: value('company', fallback.company),
      plan: value('plan', fallback.plan),
      subscription: value('subscription', fallback.subscription),
      aiUsage: value('aiUsage', fallback.aiUsage),
      noCompanies: value('noCompanies', fallback.noCompanies),
      billing: billing,
    );
  }

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
    resetExplanation:
        'Monthly usage and purchased credits reset at each successful subscription renewal.',
    packsTitle: 'Add AI credits',
    packsSubtitle: 'One-time credit packs, fulfilled securely through Stripe.',
    creditsUnit: 'credits',
    purchase: 'Purchase',
    purchaseRequiresActive:
        'An active or trialing subscription is required to purchase credit packs.',
    priceUsd: '\${price} USD',
    adminSubtitle: 'Tenant-scoped balances and logical AI usage across Avenqo.',
    company: 'Company',
    plan: 'Plan',
    subscription: 'Subscription',
    aiUsage: 'AI usage',
    noCompanies: 'No company credit data is available.',
    billing: {
      'cancelSubscription': 'Cancel subscription',
      'cancelTitle': 'Cancel subscription?',
      'cancelMessage':
          'Your access will continue until the end of the paid period.',
      'cancelConfirm': 'Schedule cancellation',
      'keepSubscription': 'Keep subscription',
      'effectiveEnd': 'Access ends on {date}',
      'invoicePeriod': '{start} to {end}',
      'viewInvoice': 'View invoices',
      'downloadPdf': 'Download PDF',
      'noInvoices': 'No invoices yet.',
      'statusInactive': 'Inactive',
      'statusTrialing': 'Trialing',
      'statusActive': 'Active',
      'statusPastDue': 'Past due',
      'statusCancelingAtPeriodEnd': 'Canceling at period end',
      'statusCanceled': 'Canceled',
      'statusUnknown': 'Unknown',
      'invoicePaid': 'Paid',
      'invoiceOpen': 'Open',
      'invoiceDraft': 'Draft',
      'invoiceVoid': 'Void',
      'invoiceUncollectible': 'Uncollectible',
      'planDemo': 'Demo',
      'planProfessional': 'Professional',
      'planEnterprise': 'Enterprise',
    },
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
  final Map<String, String> billing;

  String billingValue(String key) => billing[key] ?? key;

  String subscriptionStatus(String status) => billingValue(switch (status) {
    'inactive' => 'statusInactive',
    'trialing' => 'statusTrialing',
    'active' => 'statusActive',
    'past_due' => 'statusPastDue',
    'canceling_at_period_end' => 'statusCancelingAtPeriodEnd',
    'canceled' => 'statusCanceled',
    _ => 'statusUnknown',
  });

  String invoiceStatus(String status) => billingValue(switch (status) {
    'paid' => 'invoicePaid',
    'open' => 'invoiceOpen',
    'draft' => 'invoiceDraft',
    'void' => 'invoiceVoid',
    'uncollectible' => 'invoiceUncollectible',
    _ => 'statusUnknown',
  });

  String planName(String plan) => switch (plan) {
    'demo' => 'Demo',
    'professional' => 'Professional',
    'enterprise' || 'custom_enterprise' => 'Enterprise',
    _ => billingValue('statusUnknown'),
  };
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
    required this.skuLabel,
    required this.currentPeriodLabel,
    required this.previousPeriodLabel,
    required this.changeLabel,
    required this.businessImpactLabel,
    required this.periodLabel,
    required this.severityReasonLabel,
    required this.severityInformational,
    required this.severityLow,
    required this.severityMedium,
    required this.severityHigh,
    required this.severityCritical,
    required this.reasonMaterialAbsoluteAndShare,
    required this.reasonMaterialRevenueChange,
    required this.reasonMeaningfulChange,
    required this.reasonLimitedImpact,
    required this.reasonMinorImpact,
    required this.reasonDecisionPolicy,
  });

  factory Phase4dStrings.fromJson(Map<String, dynamic> json) {
    final fallback = Phase4dStrings.fallback();
    String value(String key, String fallbackValue) =>
        json[key] as String? ?? fallbackValue;
    return Phase4dStrings(
      productsTotal: value('productsTotal', fallback.productsTotal),
      productsActive: value('productsActive', fallback.productsActive),
      productsRevenue: value('productsRevenue', fallback.productsRevenue),
      productsUnits: value('productsUnits', fallback.productsUnits),
      productsAveragePrice: value(
        'productsAveragePrice',
        fallback.productsAveragePrice,
      ),
      productsConcentration: value(
        'productsConcentration',
        fallback.productsConcentration,
      ),
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
      recommendationsEmpty: value(
        'recommendationsEmpty',
        fallback.recommendationsEmpty,
      ),
      priorityLabel: value('priorityLabel', fallback.priorityLabel),
      evidenceLabel: value('evidenceLabel', fallback.evidenceLabel),
      suggestedActionLabel: value(
        'suggestedActionLabel',
        fallback.suggestedActionLabel,
      ),
      productDeclineTitle: value(
        'productDeclineTitle',
        fallback.productDeclineTitle,
      ),
      productGrowthTitle: value(
        'productGrowthTitle',
        fallback.productGrowthTitle,
      ),
      productConcentrationTitle: value(
        'productConcentrationTitle',
        fallback.productConcentrationTitle,
      ),
      crossSellOpportunityTitle: value(
        'crossSellOpportunityTitle',
        fallback.crossSellOpportunityTitle,
      ),
      productRevenueChangedExplanation: value(
        'productRevenueChangedExplanation',
        fallback.productRevenueChangedExplanation,
      ),
      productConcentrationExplanation: value(
        'productConcentrationExplanation',
        fallback.productConcentrationExplanation,
      ),
      crossSellOpportunityExplanation: value(
        'crossSellOpportunityExplanation',
        fallback.crossSellOpportunityExplanation,
      ),
      reviewProductPerformance: value(
        'reviewProductPerformance',
        fallback.reviewProductPerformance,
      ),
      reviewProductConcentration: value(
        'reviewProductConcentration',
        fallback.reviewProductConcentration,
      ),
      reviewCrossSellOpportunities: value(
        'reviewCrossSellOpportunities',
        fallback.reviewCrossSellOpportunities,
      ),
      changeEvidence: value('changeEvidence', fallback.changeEvidence),
      concentrationEvidence: value(
        'concentrationEvidence',
        fallback.concentrationEvidence,
      ),
      customerEvidence: value('customerEvidence', fallback.customerEvidence),
      skuLabel: value('skuLabel', fallback.skuLabel),
      currentPeriodLabel: value(
        'currentPeriodLabel',
        fallback.currentPeriodLabel,
      ),
      previousPeriodLabel: value(
        'previousPeriodLabel',
        fallback.previousPeriodLabel,
      ),
      changeLabel: value('changeLabel', fallback.changeLabel),
      businessImpactLabel: value(
        'businessImpactLabel',
        fallback.businessImpactLabel,
      ),
      periodLabel: value('periodLabel', fallback.periodLabel),
      severityReasonLabel: value(
        'severityReasonLabel',
        fallback.severityReasonLabel,
      ),
      severityInformational: value(
        'severityInformational',
        fallback.severityInformational,
      ),
      severityLow: value('severityLow', fallback.severityLow),
      severityMedium: value('severityMedium', fallback.severityMedium),
      severityHigh: value('severityHigh', fallback.severityHigh),
      severityCritical: value('severityCritical', fallback.severityCritical),
      reasonMaterialAbsoluteAndShare: value(
        'reasonMaterialAbsoluteAndShare',
        fallback.reasonMaterialAbsoluteAndShare,
      ),
      reasonMaterialRevenueChange: value(
        'reasonMaterialRevenueChange',
        fallback.reasonMaterialRevenueChange,
      ),
      reasonMeaningfulChange: value(
        'reasonMeaningfulChange',
        fallback.reasonMeaningfulChange,
      ),
      reasonLimitedImpact: value(
        'reasonLimitedImpact',
        fallback.reasonLimitedImpact,
      ),
      reasonMinorImpact: value('reasonMinorImpact', fallback.reasonMinorImpact),
      reasonDecisionPolicy: value(
        'reasonDecisionPolicy',
        fallback.reasonDecisionPolicy,
      ),
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
    partialReady:
        'Some data is still processing. Ready results are shown below.',
    recommendationsEmpty:
        'No evidence-backed recommendation is available right now.',
    priorityLabel: 'Priority',
    evidenceLabel: 'Evidence',
    suggestedActionLabel: 'Suggested action',
    productDeclineTitle: 'Product revenue is declining',
    productGrowthTitle: 'Product revenue is growing',
    productConcentrationTitle: 'Revenue is concentrated in one product',
    crossSellOpportunityTitle: 'Cross-sell opportunities are available',
    productRevenueChangedExplanation:
        'Revenue changed compared with the previous equivalent period.',
    productConcentrationExplanation:
        'One product represents a significant share of observed product revenue.',
    crossSellOpportunityExplanation:
        'The active validated recommendation model identified customers with relevant product suggestions.',
    reviewProductPerformance: 'Review product performance',
    reviewProductConcentration: 'Review product concentration',
    reviewCrossSellOpportunities: 'Review cross-sell opportunities',
    changeEvidence: '{entity}: {current} vs {comparison} ({change}%)',
    concentrationEvidence: '{entity}: {current}% of product revenue',
    customerEvidence: '{current} customers with recommendations',
    skuLabel: 'SKU / product ID',
    currentPeriodLabel: 'Current period revenue',
    previousPeriodLabel: 'Previous comparable period',
    changeLabel: 'Change',
    businessImpactLabel: 'Business impact',
    periodLabel: 'Period compared',
    severityReasonLabel: 'Why this severity',
    severityInformational: 'Information',
    severityLow: 'Low',
    severityMedium: 'Medium',
    severityHigh: 'High',
    severityCritical: 'Critical',
    reasonMaterialAbsoluteAndShare:
        'The absolute impact and share of tenant revenue are both material.',
    reasonMaterialRevenueChange:
        'The revenue change has a material financial impact.',
    reasonMeaningfulChange:
        'The relative change or share of tenant revenue is meaningful.',
    reasonLimitedImpact: 'The observed change has limited business impact.',
    reasonMinorImpact: 'The observed change has minor business impact.',
    reasonDecisionPolicy:
        'Severity follows the deterministic business decision policy.',
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
  final String skuLabel;
  final String currentPeriodLabel;
  final String previousPeriodLabel;
  final String changeLabel;
  final String businessImpactLabel;
  final String periodLabel;
  final String severityReasonLabel;
  final String severityInformational;
  final String severityLow;
  final String severityMedium;
  final String severityHigh;
  final String severityCritical;
  final String reasonMaterialAbsoluteAndShare;
  final String reasonMaterialRevenueChange;
  final String reasonMeaningfulChange;
  final String reasonLimitedImpact;
  final String reasonMinorImpact;
  final String reasonDecisionPolicy;

  String severityName(String value) => switch (value) {
    'critical' => severityCritical,
    'high' => severityHigh,
    'medium' => severityMedium,
    'low' => severityLow,
    _ => severityInformational,
  };

  String severityReason(String value) => switch (value) {
    'material_absolute_and_tenant_share' => reasonMaterialAbsoluteAndShare,
    'material_revenue_change' => reasonMaterialRevenueChange,
    'meaningful_relative_or_tenant_share' => reasonMeaningfulChange,
    'limited_business_impact' => reasonLimitedImpact,
    'minor_business_impact' => reasonMinorImpact,
    _ => reasonDecisionPolicy,
  };
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

  factory OnboardingStrings.fromJson(Map<String, dynamic> json) =>
      OnboardingStrings(
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
    subtitle:
        'A few quick questions to personalize your priorities and recommendations.',
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

  factory DashboardHomeStrings.fromJson(Map<String, dynamic> json) =>
      DashboardHomeStrings(
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
        askAvenqoSubtitle:
            json['askAvenqoSubtitle'] as String? ??
            DashboardHomeStrings.fallback().askAvenqoSubtitle,
        askAvenqoCta:
            json['askAvenqoCta'] as String? ??
            DashboardHomeStrings.fallback().askAvenqoCta,
        importDataTitle:
            json['importDataTitle'] as String? ??
            DashboardHomeStrings.fallback().importDataTitle,
        importDataSubtitle:
            json['importDataSubtitle'] as String? ??
            DashboardHomeStrings.fallback().importDataSubtitle,
        importDataCta:
            json['importDataCta'] as String? ??
            DashboardHomeStrings.fallback().importDataCta,
        connectionsTitle:
            json['connectionsTitle'] as String? ??
            DashboardHomeStrings.fallback().connectionsTitle,
        connectionsEmpty:
            json['connectionsEmpty'] as String? ??
            DashboardHomeStrings.fallback().connectionsEmpty,
        connectionsEmptyCta:
            json['connectionsEmptyCta'] as String? ??
            DashboardHomeStrings.fallback().connectionsEmptyCta,
        connectionsReadyLabel:
            json['connectionsReadyLabel'] as String? ??
            DashboardHomeStrings.fallback().connectionsReadyLabel,
        connectionsLastUpdate:
            json['connectionsLastUpdate'] as String? ??
            DashboardHomeStrings.fallback().connectionsLastUpdate,
        activityTitle:
            json['activityTitle'] as String? ??
            DashboardHomeStrings.fallback().activityTitle,
        activityEmpty:
            json['activityEmpty'] as String? ??
            DashboardHomeStrings.fallback().activityEmpty,
        stepsTitle:
            json['stepsTitle'] as String? ??
            DashboardHomeStrings.fallback().stepsTitle,
        stepOrgLabel:
            json['stepOrgLabel'] as String? ??
            DashboardHomeStrings.fallback().stepOrgLabel,
        stepDataLabel:
            json['stepDataLabel'] as String? ??
            DashboardHomeStrings.fallback().stepDataLabel,
        stepInsightsLabel:
            json['stepInsightsLabel'] as String? ??
            DashboardHomeStrings.fallback().stepInsightsLabel,
        stepAskLabel:
            json['stepAskLabel'] as String? ??
            DashboardHomeStrings.fallback().stepAskLabel,
        revenueDeclineTitle:
            json['revenueDeclineTitle'] as String? ??
            DashboardHomeStrings.fallback().revenueDeclineTitle,
        revenueGrowthTitle:
            json['revenueGrowthTitle'] as String? ??
            DashboardHomeStrings.fallback().revenueGrowthTitle,
        revenueChangedExplanation:
            json['revenueChangedExplanation'] as String? ??
            DashboardHomeStrings.fallback().revenueChangedExplanation,
        datasetImportedActivity:
            json['datasetImportedActivity'] as String? ??
            DashboardHomeStrings.fallback().datasetImportedActivity,
        modelActivatedActivity:
            json['modelActivatedActivity'] as String? ??
            DashboardHomeStrings.fallback().modelActivatedActivity,
      );

  factory DashboardHomeStrings.fallback() => const DashboardHomeStrings(
    hello: 'Hello',
    subtitleForCompany: "Here's what deserves your attention at {company}.",
    askAvenqo: 'What would you like to understand today?',
    connectDataTitle:
        'Connect your business data to unlock analytics, forecasts and Avenqo AI insights.',
    connectDataCta: 'Connect data',
    thisMonth: 'This month',
    salesLabel: 'Revenue',
    ordersLabel: 'Orders',
    customersLabel: 'Active customers',
    avgOrderLabel: 'Average order',
    prioritiesTitle: 'Recommended priorities',
    prioritiesEmpty:
        'Your priorities will appear here once your business data is connected.',
    planLabel: 'Plan',
    askAvenqoSubtitle:
        'Ask questions about your business data and receive contextual insights.',
    askAvenqoCta: 'Ask Avenqo AI',
    importDataTitle: 'Import your data',
    importDataSubtitle:
        'Connect or import your business sources to unlock Avenqo intelligence.',
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
…12502 tokens truncated…vSupportDescription: s('navSupportDescription'),
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
      connectionsImportSummarySuccessOne: s(
        'connectionsImportSummarySuccessOne',
      ),
      connectionsImportSummarySuccessOther: s(
        'connectionsImportSummarySuccessOther',
      ),
      connectionsImportSummaryErrorsOne: s('connectionsImportSummaryErrorsOne'),
      connectionsImportSummaryErrorsOther: s(
        'connectionsImportSummaryErrorsOther',
      ),
      connectionsMappingRequiredBadge: s('connectionsMappingRequiredBadge'),
      connectionsCompleteMapping: s('connectionsCompleteMapping'),
      connectionsConnectedDataTitle: s('connectionsConnectedDataTitle'),
      connectionsDeleteData: s('connectionsDeleteData'),
      connectionsDeleteSelected: s('connectionsDeleteSelected'),
      connectionsDeletePermanently: s('connectionsDeletePermanently'),
      connectionsDeleteCancel: s('connectionsDeleteCancel'),
      connectionsDeleteTitle: s('connectionsDeleteTitle'),
      connectionsDeleteWarning: s('connectionsDeleteWarning'),
      connectionsDeleteSuccess: s('connectionsDeleteSuccess'),
      connectionsDeleteFailure: s('connectionsDeleteFailure'),
      connectionsUploadedSource: s('connectionsUploadedSource'),
      connectionsSynchronizedSource: s('connectionsSynchronizedSource'),
      connectionsSelectedCount: s('connectionsSelectedCount'),
      connectionsContinueLabel: s('connectionsContinueLabel'),
      connectionsImportedAtLabel: s('connectionsImportedAtLabel'),
      connectionsUploadedFileSuccessLabel: s(
        'connectionsUploadedFileSuccessLabel',
      ),
      connectionsCleaning: {
        for (final key in const [
          'view',
          'summary',
          'before',
          'after',
          'quality',
          'qualityBefore',
          'qualityAfter',
          'entityViews',
          'mappingAudit',
          'structuralNulls',
          'notApplicableFields',
          'requiredMissing',
          'optionalMissing',
          'customers',
          'catalog',
          'commerce',
          'otherFields',
          'rowsBeforeAfter',
          'columns',
          'duplicatesRemoved',
          'missingValues',
          'invalidValues',
          'mappedColumns',
          'columnStrategies',
          'mappedField',
          'inferredType',
          'suggestedStrategy',
          'appliedStrategies',
          'conversions',
          'invalidCorrected',
          'preview',
          'previewEmpty',
          'exports',
          'readyBanner',
          'attentionBanner',
          'notMapped',
          'notAvailable',
          'trainingFailed',
          'mean',
          'median',
          'mode',
          'suppression',
          'leave_empty',
          'normalize_numeric',
          'normalize_date',
          'normalize_boolean',
          'coerce_invalid_to_empty',
          'preserve_non_duplicate_rows',
          'preserve_missing_values',
        ])
          key: cleaning?[key] as String? ?? fallback.connectionsCleaning[key]!,
      },
      connectorHub: {
        ...fallback.connectorHub,
        if (connectorHub != null)
          for (final entry in connectorHub.entries)
            if (entry.value is String) entry.key: entry.value as String,
      },
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
      customersNotCalculated: s('customersNotCalculated'),
      customerSegmentVip: s('customerSegmentVip'),
      customerSegmentHighValue: s('customerSegmentHighValue'),
      customerSegmentLoyal: s('customerSegmentLoyal'),
      customerSegmentRegular: s('customerSegmentRegular'),
      customerSegmentNew: s('customerSegmentNew'),
      customerSegmentDormant: s('customerSegmentDormant'),
      customerRiskLow: s('customerRiskLow'),
      customerRiskMedium: s('customerRiskMedium'),
      customerRiskHigh: s('customerRiskHigh'),
      customerRiskCritical: s('customerRiskCritical'),
      previousPage: s('previousPage'),
      nextPage: s('nextPage'),
      businessProductsTitle: s('businessProductsTitle'),
      businessProductsDescription: s('businessProductsDescription'),
      businessRecommendationsTitle: s('businessRecommendationsTitle'),
      businessRecommendationsDescription: s(
        'businessRecommendationsDescription',
      ),
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
    connectionsNoDataTitle:
        'Connect your data to unlock analytics and Avenqo AI.',
    connectionsNoDataFormats: 'Accepted formats: CSV, XLSX, JSON, Parquet.',
    connectionsImportButton: 'Import a file',
    connectionsUploadingLabel: 'Uploading…',
    connectionsAnalyzing: 'Analyzing the structure of your data…',
    connectionsPreparingData: 'Preparing data…',
    connectionsTrainingAi: 'Training AI…',
    connectionsAttentionRequired: 'Attention required',
    connectionsMappingTitle: 'Confirm your column mapping',
    connectionsMappingSubtitle:
        'Some columns need manual confirmation before analytics can be activated.',
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
    connectionsDeleteData: 'Delete data',
    connectionsDeleteSelected: 'Delete selected',
    connectionsDeletePermanently: 'Delete permanently',
    connectionsDeleteCancel: 'Cancel',
    connectionsDeleteTitle: 'Delete data?',
    connectionsDeleteWarning:
        'This permanently deletes the selected source data, cleaned data, models, forecasts, and AI context. Connected stores remain connected.',
    connectionsDeleteSuccess: 'Data deleted successfully.',
    connectionsDeleteFailure: 'Data deletion failed.',
    connectionsUploadedSource: 'Uploaded file',
    connectionsSynchronizedSource: 'Synchronized data',
    connectionsSelectedCount: '{n} selected',
    connectionsContinueLabel: 'Continue',
    connectionsImportedAtLabel: 'Imported',
    connectionsUploadedFileSuccessLabel: 'Data imported successfully',
    connectionsCleaning: {
      'view': 'View cleaned data',
      'summary': 'Cleaning summary',
      'before': 'Before',
      'after': 'After',
      'quality': 'Cleaning quality',
      'qualityBefore': 'Quality before',
      'qualityAfter': 'Quality after',
      'entityViews': 'Business entities',
      'mappingAudit': 'Mapping audit',
      'structuralNulls': 'Structural nulls',
      'notApplicableFields': 'Not applicable',
      'requiredMissing': 'Required values missing',
      'optionalMissing': 'Optional values missing',
      'customers': 'Customers',
      'catalog': 'Products and inventory',
      'commerce': 'Orders and payments',
      'otherFields': 'Other fields',
      'rowsBeforeAfter': 'Rows',
      'columns': 'Columns',
      'duplicatesRemoved': 'Duplicates removed',
      'missingValues': 'Missing values',
      'invalidValues': 'Invalid values corrected',
      'mappedColumns': 'Mapped columns',
      'columnStrategies': 'Column strategies',
      'mappedField': 'Mapped field',
      'inferredType': 'Detected type',
      'suggestedStrategy': 'Suggested missing-data strategy',
      'appliedStrategies': 'Applied actions',
      'conversions': 'Conversions',
      'invalidCorrected': 'Invalid values corrected',
      'preview': 'Before and after preview',
      'previewEmpty': 'No preview is available yet.',
      'exports': 'Export cleaned data',
      'readyBanner': 'The cleaned dataset is ready to use now.',
      'attentionBanner':
          'The cleaned dataset is ready, but some column mapping still needs confirmation.',
      'notMapped': 'Not mapped',
      'notAvailable': 'Not available',
      'trainingFailed': 'Advanced AI training needs retry',
      'mean': 'Mean',
      'median': 'Median',
      'mode': 'Mode',
      'suppression': 'Remove or ignore',
      'leave_empty': 'Keep empty',
      'normalize_numeric': 'Normalize numeric values',
      'normalize_date': 'Normalize dates',
      'normalize_boolean': 'Normalize yes/no values',
      'coerce_invalid_to_empty': 'Replace invalid values with empty',
      'preserve_non_duplicate_rows': 'Keep non-duplicate rows',
      'preserve_missing_values': 'Keep missing values visible',
    },
    connectorHub: {
      'title': 'Retail Connector Hub',
      'subtitle': 'Live sales sources and upcoming integrations.',
      'searchHint': 'Search providers',
      'all': 'All',
      'categoryFilter': 'Category',
      'statusFilter': 'Status',
      'available': 'Available',
      'configurationRequired': 'Configuration required',
      'comingSoon': 'Coming soon',
      'unavailableStatus': 'Unavailable',
      'connect': 'Connect',
      'connectAnother': 'Connect another store',
      'connectedStores': 'Connected stores',
      'commerceSources': 'Commerce sources',
      'addOnlineStore': 'Connect an online store',
      'providerSearchHint': 'Search for a platform...',
      'providerDescription':
          'Connect this store to Avenqo to synchronize products, customers, orders, inventory, and commerce data.',
      'connectToAvenqo': 'Connect to Avenqo',
      'testConnector': 'Test connector',
      'shopDomainTitle': 'Connect Shopify',
      'shopDomainHint': 'your-store.myshopify.com',
      'authorize': 'Continue to Shopify',
      'wooTitle': 'Connect WooCommerce',
      'wooStoreUrl': 'Store URL',
      'wooStoreUrlHint': 'https://store.example.com',
      'wooManualMode': 'Use API keys manually',
      'wooManualDescription':
          'Use only when browser authorization is unavailable.',
      'wooConsumerKey': 'Consumer key',
      'wooConsumerSecret': 'Consumer secret',
      'wooAuthorize': 'Continue to WooCommerce',
      'wooConnectManual': 'Connect securely',
      'wooCredentialsRequired':
          'Enter both the consumer key and consumer secret.',
      'wooLaunchFailed': 'WooCommerce authorization could not be opened.',
      'cancel': 'Cancel',
      'close': 'Close',
      'search': 'Search',
      'connection': 'Connection',
      'sync': 'Sync now',
      'disconnect': 'Disconnect',
      'reconnect': 'Reconnect',
      'refresh': 'Refresh',
      'syncing': 'Syncing',
      'ready': 'Ready',
      'connected': 'Connected',
      'error': 'Needs attention',
      'disconnected': 'Disconnected',
      'processing': 'Processing',
      'connecting': 'Connecting',
      'authorizing': 'Awaiting authorization',
      'reauthorizationRequired': 'Authorization required',
      'reauthorizeWooCommerce': 'Reauthorize WooCommerce',
      'lastSync': 'Last sync',
      'neverSynced': 'Not synced yet',
      'syncFailed': 'Synchronization failed',
      'storageUnavailable': 'Storage unavailable',
      'unavailable': 'Configuration unavailable',
      'launchFailed': 'Shopify authorization could not be opened.',
      'disconnectConfirm': 'Disconnect this store?',
      'catalogUnavailable': 'The connector catalog is temporarily unavailable.',
      'fileImportTitle': 'File imports',
      'fileImportSubtitle': 'CSV, XLSX, JSON and Parquet remain available.',
      'records': 'records',
      'ecommerce': 'Online stores',
      'marketplace': 'Marketplaces',
      'pos': 'POS',
      'payments': 'Payments',
      'catalog': 'Catalogs',
      'marketing': 'Marketing',
      'fulfillment': 'Fulfillment',
      'analytics': 'Analytics',
      'capabilities': 'Capabilities',
      'capabilityOrders': 'Orders',
      'capabilityCustomers': 'Customers',
      'capabilityProducts': 'Products',
      'capabilityInventory': 'Inventory',
      'capabilityRefunds': 'Refunds',
      'capabilityPayments': 'Payments',
      'capabilityDiscounts': 'Discounts',
      'capabilityVariants': 'Variants',
      'capabilityLocations': 'Locations',
      'capabilityFulfillments': 'Fulfillments',
      'capabilityAbandonedCarts': 'Abandoned carts',
      'capabilityCatalog': 'Catalog',
      'capabilityWebhooks': 'Webhooks',
      'capabilityIncrementalSync': 'Incremental sync',
      'authorization': 'Authorization',
    },
    businessDefaultTitle: 'Your space is ready',
    businessDefaultDescription:
        'Connect your tools to see up-to-date information here.',
    businessConnectButton: 'Connect my tools',
    businessSalesTitle: 'Track every change',
    businessSalesDescription:
        'Your sales trends, comparisons and forecasts will appear here.',
    businessCustomersTitle: 'Retain the right customers',
    businessCustomersDescription:
        "You'll find customers to prioritize, re-engage or support here.",
    analyticsUnavailable:
        'This capability is unavailable with your current business data.',
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
    customersNotCalculated: 'Not calculated',
    customerSegmentVip: 'VIP',
    customerSegmentHighValue: 'High value',
    customerSegmentLoyal: 'Loyal',
    customerSegmentRegular: 'Regular',
    customerSegmentNew: 'New',
    customerSegmentDormant: 'Dormant',
    customerRiskLow: 'Low',
    customerRiskMedium: 'Medium',
    customerRiskHigh: 'High',
    customerRiskCritical: 'Critical',
    previousPage: 'Previous',
    nextPage: 'Next',
    businessProductsTitle: 'Manage your catalog',
    businessProductsDescription:
        'Top-performing products, expected demand and stock to watch will be gathered here.',
    businessRecommendationsTitle: 'Act directly on opportunities',
    businessRecommendationsDescription:
        "Avenqo will rank opportunities by their potential impact on your business.",
    businessAlertsTitle: 'Stay informed without the noise',
    businessAlertsDescription:
        'Important changes and risks will be flagged with a recommended action.',
    businessReportsTitle: 'Your executive summaries',
    businessReportsDescription:
        "Create and share clear reports on your company's results.",
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
    'connectionsImportSummarySuccessOther' =>
      connectionsImportSummarySuccessOther,
    'connectionsImportSummaryErrorsOne' => connectionsImportSummaryErrorsOne,
    'connectionsImportSummaryErrorsOther' =>
      connectionsImportSummaryErrorsOther,
    'connectionsMappingRequiredBadge' => connectionsMappingRequiredBadge,
    'connectionsCompleteMapping' => connectionsCompleteMapping,
    'connectionsConnectedDataTitle' => connectionsConnectedDataTitle,
    'connectionsDeleteData' => connectionsDeleteData,
    'connectionsDeleteSelected' => connectionsDeleteSelected,
    'connectionsDeletePermanently' => connectionsDeletePermanently,
    'connectionsDeleteCancel' => connectionsDeleteCancel,
    'connectionsDeleteTitle' => connectionsDeleteTitle,
    'connectionsDeleteWarning' => connectionsDeleteWarning,
    'connectionsDeleteSuccess' => connectionsDeleteSuccess,
    'connectionsDeleteFailure' => connectionsDeleteFailure,
    'connectionsUploadedSource' => connectionsUploadedSource,
    'connectionsSynchronizedSource' => connectionsSynchronizedSource,
    'connectionsSelectedCount' => connectionsSelectedCount,
    'connectionsContinueLabel' => connectionsContinueLabel,
    'connectionsImportedAtLabel' => connectionsImportedAtLabel,
    'connectionsUploadedFileSuccessLabel' =>
      connectionsUploadedFileSuccessLabel,
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
    'customersNotCalculated' => customersNotCalculated,
    'customerSegmentVip' => customerSegmentVip,
    'customerSegmentHighValue' => customerSegmentHighValue,
    'customerSegmentLoyal' => customerSegmentLoyal,
    'customerSegmentRegular' => customerSegmentRegular,
    'customerSegmentNew' => customerSegmentNew,
    'customerSegmentDormant' => customerSegmentDormant,
    'customerRiskLow' => customerRiskLow,
    'customerRiskMedium' => customerRiskMedium,
    'customerRiskHigh' => customerRiskHigh,
    'customerRiskCritical' => customerRiskCritical,
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
  final String connectionsDeleteData;
  final String connectionsDeleteSelected;
  final String connectionsDeletePermanently;
  final String connectionsDeleteCancel;
  final String connectionsDeleteTitle;
  final String connectionsDeleteWarning;
  final String connectionsDeleteSuccess;
  final String connectionsDeleteFailure;
  final String connectionsUploadedSource;
  final String connectionsSynchronizedSource;
  final String connectionsSelectedCount;
  final String connectionsContinueLabel;
  final String connectionsImportedAtLabel;
  final String connectionsUploadedFileSuccessLabel;
  final Map<String, String> connectionsCleaning;
  final Map<String, String> connectorHub;
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
  final String customersNotCalculated;
  final String customerSegmentVip;
  final String customerSegmentHighValue;
  final String customerSegmentLoyal;
  final String customerSegmentRegular;
  final String customerSegmentNew;
  final String customerSegmentDormant;
  final String customerRiskLow;
  final String customerRiskMedium;
  final String customerRiskHigh;
  final String customerRiskCritical;

  String customerSegmentName(String value) => switch (value) {
    'vip' => customerSegmentVip,
    'high_value' => customerSegmentHighValue,
    'loyal' => customerSegmentLoyal,
    'regular' => customerSegmentRegular,
    'new' => customerSegmentNew,
    'dormant' => customerSegmentDormant,
    _ => customersNotCalculated,
  };

  String customerRiskName(String value) => switch (value) {
    'critical' => customerRiskCritical,
    'high' => customerRiskHigh,
    'medium' => customerRiskMedium,
    'low' => customerRiskLow,
    _ => customersNotCalculated,
  };
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
