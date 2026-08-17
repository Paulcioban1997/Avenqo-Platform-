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
  const ModuleItem({required this.name, required this.description});

  factory ModuleItem.fromJson(Map<String, dynamic> json) => ModuleItem(
        name: json['name'] as String,
        description: json['description'] as String,
      );

  final String name;
  final String description;
}

class ModulesSectionStrings {
  const ModulesSectionStrings({
    required this.kicker,
    required this.title,
    required this.subtitle,
    required this.discover,
    required this.items,
  });

  factory ModulesSectionStrings.fromJson(Map<String, dynamic> json) => ModulesSectionStrings(
        kicker: json['kicker'] as String,
        title: json['title'] as String,
        subtitle: json['subtitle'] as String,
        discover: json['discover'] as String,
        items: (json['items'] as List<dynamic>)
            .map((e) => ModuleItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  final String kicker;
  final String title;
  final String subtitle;
  final String discover;
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
    required this.items,
    required this.action,
  });

  factory PricingPlan.fromJson(Map<String, dynamic> json) => PricingPlan(
        tier: json['tier'] as String,
        title: json['title'] as String,
        items: (json['items'] as List<dynamic>).cast<String>(),
        action: json['action'] as String,
      );

  final String tier;
  final String title;
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
