import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:avenqo/widgets/avenqo_brand.dart';
import 'package:avenqo/widgets/language_selector.dart';
import 'package:avenqo/widgets/theme_toggle_button.dart';

/// Couleurs de la marque Avenqo, alignées sur web/src/app/globals.css.
class _Brand {
  const _Brand._();

  static const blue = Color(0xFF087CF0);
  static const blueDark = Color(0xFF0757C9);
  static const ink = Color(0xFF080B12);
  static const muted = Color(0xFF5C6472);
  static const line = Color(0xFFE4E8ED);
}

Future<void> _contactByEmail() async {
  await launchUrl(Uri.parse('mailto:bonjour@avenqo.ca'));
}

/// Conteneur de section centré, aligné sur .page-shell / .section du site web.
class _Section extends StatelessWidget {
  const _Section({required this.child, this.color});

  final Widget child;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      width: double.infinity,
      color: color ?? colors.surface,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 72),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1180),
          child: child,
        ),
      ),
    );
  }
}

class _SectionHeading extends StatelessWidget {
  const _SectionHeading({
    required this.kicker,
    required this.title,
    this.subtitle,
    this.dark = false,
  });

  final String kicker;
  final String title;
  final String? subtitle;
  final bool dark;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final titleColor = dark ? colors.surface : colors.ink;
    final subtitleColor = dark ? colors.muted : colors.muted;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          kicker.toUpperCase(),
          style: const TextStyle(
            color: _Brand.blue,
            fontSize: 12,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.1,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          title,
          style: TextStyle(
            color: titleColor,
            fontSize: 32,
            fontWeight: FontWeight.w800,
            height: 1.2,
          ),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 12),
          SizedBox(
            width: 620,
            child: Text(
              subtitle!,
              style: TextStyle(color: subtitleColor, fontSize: 15, height: 1.6),
            ),
          ),
        ],
      ],
    );
  }
}

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AvenqoColors.of(context).canvas,
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: const [
            _Navbar(),
            _Hero(),
            _TrustStrip(),
            _FeaturesSection(),
            _ModulesSection(),
            _StepsSection(),
            _UsecasesSection(),
            _WhySection(),
            _PricingSection(),
            _FaqSection(),
            _FinalCtaSection(),
            _Footer(),
          ],
        ),
      ),
    );
  }
}

class _Navbar extends StatelessWidget {
  const _Navbar();

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context);
    final colors = AvenqoColors.of(context);
    return Container(
      color: colors.surface,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth > 860;
          return Row(
            children: [
              InkWell(
                onTap: () => context.go('/'),
                child: const AvenqoBrand(),
              ),
              const Spacer(),
              if (wide) ...[
                _NavLink(t.nav.features, () => context.go('/pricing')),
                _NavLink(t.nav.modules, () => context.go('/pricing')),
                _NavLink(t.nav.pricing, () => context.go('/pricing')),
                const SizedBox(width: 20),
              ],
              Flexible(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerRight,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      ThemeToggleButton(foregroundColor: colors.muted),
                      const SizedBox(width: 4),
                      const LanguageSelector(),
                      const SizedBox(width: 8),
                      TextButton(
                        onPressed: () => context.go('/login'),
                        style: TextButton.styleFrom(
                          foregroundColor: colors.muted,
                        ),
                        child: Text(t.common.login),
                      ),
                      const SizedBox(width: 8),
                      FilledButton.icon(
                        onPressed: () => context.go('/register'),
                        style: FilledButton.styleFrom(
                          backgroundColor: _Brand.blue,
                          foregroundColor: Colors.white,
                        ),
                        icon: const Icon(Icons.arrow_forward, size: 16),
                        label: Text(t.common.tryFree),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _NavLink extends StatelessWidget {
  const _NavLink(this.label, this.onTap);

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return TextButton(
      onPressed: onTap,
      style: TextButton.styleFrom(foregroundColor: colors.muted),
      child: Text(label),
    );
  }
}

class _Hero extends StatelessWidget {
  const _Hero();

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context);
    final colors = AvenqoColors.of(context);
    return Container(
      color: colors.surface,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 64),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1180),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 900;
              final copy = _heroCopy(context, wide, t);
              final preview = _DashboardPreview(dashboard: t.dashboard);
              if (!wide) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [copy, const SizedBox(height: 40), preview],
                );
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(flex: 5, child: copy),
                  const SizedBox(width: 54),
                  Expanded(flex: 6, child: preview),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _heroCopy(BuildContext context, bool wide, Translations t) {
    final colors = AvenqoColors.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _EyebrowDot(),
            const SizedBox(width: 9),
            Text(
              t.hero.eyebrow,
              style: const TextStyle(
                color: _Brand.blueDark,
                fontSize: 12,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.2,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Text.rich(
          TextSpan(
            style: TextStyle(
              fontSize: wide ? 48 : 34,
              fontWeight: FontWeight.w800,
              height: 1.12,
              color: colors.ink,
            ),
            children: [
              TextSpan(text: '${t.hero.titleLine1}\n'),
              TextSpan(
                text: t.hero.titleLine2,
                style: const TextStyle(color: _Brand.blue),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        SizedBox(
          width: 520,
          child: Text(
            t.hero.subtitle,
            style: TextStyle(color: colors.muted, fontSize: 16, height: 1.6),
          ),
        ),
        const SizedBox(height: 28),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            FilledButton.icon(
              onPressed: () => context.go('/register'),
              style: FilledButton.styleFrom(
                backgroundColor: colors.ink,
                foregroundColor: Colors.white,
              ),
              icon: const Icon(Icons.arrow_forward, size: 17),
              label: Text(t.common.tryFree),
            ),
            OutlinedButton.icon(
              onPressed: _contactByEmail,
              style: OutlinedButton.styleFrom(
                foregroundColor: colors.ink,
                side: BorderSide(color: colors.line),
              ),
              icon: const Icon(Icons.play_arrow, size: 16),
              label: Text(t.common.watchDemo),
            ),
          ],
        ),
        const SizedBox(height: 20),
        Wrap(
          spacing: 18,
          runSpacing: 8,
          children: [
            _ProofItem(t.common.noCreditCard),
            _ProofItem(t.common.guidedSetup),
            _ProofItem(t.common.isolatedData),
          ],
        ),
      ],
    );
  }
}

class _EyebrowDot extends StatelessWidget {
  const _EyebrowDot();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 8,
      height: 8,
      decoration: const BoxDecoration(
        color: _Brand.blue,
        shape: BoxShape.circle,
      ),
    );
  }
}

class _ProofItem extends StatelessWidget {
  const _ProofItem(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.check, size: 14, color: _Brand.blue),
        const SizedBox(width: 6),
        Text(label, style: TextStyle(color: colors.muted, fontSize: 13)),
      ],
    );
  }
}

class _DashboardPreview extends StatelessWidget {
  const _DashboardPreview({required this.dashboard});

  final DashboardStrings dashboard;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.line),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 40,
            offset: const Offset(0, 24),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _macDot(const Color(0xFFFF5F57)),
              const SizedBox(width: 6),
              _macDot(const Color(0xFFFEBC2E)),
              const SizedBox(width: 6),
              _macDot(const Color(0xFF28C840)),
              const Spacer(),
              Text(
                dashboard.subtitle,
                style: TextStyle(
                  color: colors.muted,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              const CircleAvatar(
                radius: 12,
                backgroundColor: _Brand.blue,
                child: Text(
                  'PC',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      dashboard.greeting,
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15,
                        color: colors.ink,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      dashboard.subtitle,
                      style: TextStyle(color: colors.muted, fontSize: 12),
                    ),
                  ],
                ),
              ),
              FilledButton.icon(
                onPressed: null,
                style: FilledButton.styleFrom(
                  backgroundColor: _Brand.blue,
                  disabledBackgroundColor: _Brand.blue,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 6,
                  ),
                  textStyle: const TextStyle(fontSize: 11),
                ),
                icon: const Icon(Icons.auto_awesome, size: 12),
                label: Text(dashboard.askAvenqo),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: dashboard.salesLabel,
                  value: '284 650 \$',
                  delta: '+12,4 %',
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: dashboard.activeClientsLabel,
                  value: '2 847',
                  delta: '+8,1 %',
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: dashboard.opportunitiesLabel,
                  value: '36',
                  delta: dashboard.opportunitiesHint,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  flex: 6,
                  child: _PerformanceCard(
                    label: dashboard.performanceLabel,
                    period: dashboard.performancePeriod,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  flex: 5,
                  child: _RecommendationCard(
                    label: dashboard.recommendationLabel,
                    title: dashboard.recommendationTitle,
                    action: dashboard.recommendationAction,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            dashboard.quickModulesLabel,
            style: TextStyle(
              color: colors.muted,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: dashboard.quickModules
                .map((module) => _ModuleChip(module.label))
                .toList(),
          ),
        ],
      ),
    );
  }

  Widget _macDot(Color color) => Container(
    width: 9,
    height: 9,
    decoration: BoxDecoration(color: color, shape: BoxShape.circle),
  );
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
    required this.delta,
  });

  final String label;
  final String value;
  final String delta;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: colors.muted, fontSize: 10)),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              color: colors.ink,
              fontSize: 16,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            delta,
            style: const TextStyle(
              color: _Brand.blue,
              fontSize: 10,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _PerformanceCard extends StatelessWidget {
  const _PerformanceCard({required this.label, required this.period});

  final String label;
  final String period;

  static const _heights = [26.0, 34.0, 30.0, 42.0, 46.0, 52.0, 60.0];

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                label,
                style: TextStyle(
                  color: colors.ink,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Text(period, style: TextStyle(color: colors.muted, fontSize: 9)),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            height: 60,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: _heights
                  .map(
                    (h) => Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 2),
                        child: Container(
                          height: h,
                          decoration: BoxDecoration(
                            color: _Brand.blue,
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      ),
    );
  }
}

class _RecommendationCard extends StatelessWidget {
  const _RecommendationCard({
    required this.label,
    required this.title,
    required this.action,
  });

  final String label;
  final String title;
  final String action;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: _Brand.ink,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: _Brand.blue,
              fontSize: 9,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
            maxLines: 3,
          ),
          const SizedBox(height: 8),
          Text(
            action,
            style: const TextStyle(
              color: _Brand.blue,
              fontSize: 10,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _ModuleChip extends StatelessWidget {
  const _ModuleChip(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _Brand.line),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: _Brand.ink,
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _TrustStrip extends StatelessWidget {
  const _TrustStrip();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 24),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: _Brand.line)),
      ),
      child: const Center(
        child: Wrap(
          alignment: WrapAlignment.center,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 18,
          runSpacing: 8,
          children: [
            Text(
              'Une seule plateforme pour',
              style: TextStyle(color: _Brand.muted, fontSize: 13),
            ),
            Text(
              'Vendre',
              style: TextStyle(
                color: Color(0xFF252A32),
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              'Comprendre',
              style: TextStyle(
                color: Color(0xFF252A32),
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              'Automatiser',
              style: TextStyle(
                color: Color(0xFF252A32),
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              'Décider',
              style: TextStyle(
                color: Color(0xFF252A32),
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FeaturesSection extends StatelessWidget {
  const _FeaturesSection();

  @override
  Widget build(BuildContext context) {
    return _Section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionHeading(
            kicker: 'Une intelligence utile',
            title: 'De la question à l\u2019action, sans complexité.',
            subtitle:
                'Avenqo transforme votre activité en décisions claires, au même endroit.',
          ),
          const SizedBox(height: 40),
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 900;
              final assistant = _FeatureCard(
                label: 'Assistant Avenqo',
                title: 'Parlez à votre entreprise.',
                text:
                    'Posez une question comme vous le feriez à un collègue. Avenqo rassemble le contexte et répond directement.',
                child: _ChatDemoCard(),
              );
              final smallCards = Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _FeatureCard(
                    label: 'Priorité élevée',
                    title: 'Des actions, pas des écrans.',
                    text:
                        'Chaque recommandation indique quoi faire, pourquoi et quel résultat attendre.',
                    child: const _ActionLineCard(),
                  ),
                  const SizedBox(height: 24),
                  const _SecurityCard(),
                ],
              );
              if (!wide) {
                return Column(
                  children: [assistant, const SizedBox(height: 24), smallCards],
                );
              }
              return IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(flex: 6, child: assistant),
                    const SizedBox(width: 24),
                    Expanded(flex: 5, child: smallCards),
                  ],
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

class _FeatureCard extends StatelessWidget {
  const _FeatureCard({
    required this.label,
    required this.title,
    required this.text,
    required this.child,
  });

  final String label;
  final String title;
  final String text;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label.toUpperCase(),
            style: const TextStyle(
              color: _Brand.blueDark,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            title,
            style: TextStyle(
              color: colors.ink,
              fontSize: 20,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            text,
            style: TextStyle(color: colors.muted, fontSize: 13, height: 1.55),
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}

class _ChatDemoCard extends StatelessWidget {
  const _ChatDemoCard();

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.canvas,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Pourquoi mes ventes baissent ce mois-ci ?',
            style: TextStyle(
              color: colors.ink,
              fontWeight: FontWeight.w700,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            'La baisse provient principalement du segment Maison, en recul de 14 %. Je recommande une relance ciblée sur 126 clients.',
            style: TextStyle(color: colors.muted, fontSize: 13, height: 1.55),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              FilledButton(
                onPressed: () => context.go('/register'),
                style: FilledButton.styleFrom(
                  backgroundColor: colors.ink,
                  foregroundColor: colors.surface,
                  textStyle: const TextStyle(fontSize: 12),
                ),
                child: const Text('Préparer la campagne'),
              ),
              OutlinedButton(
                onPressed: () => context.go('/pricing'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: colors.ink,
                  textStyle: const TextStyle(fontSize: 12),
                ),
                child: const Text('Voir l\u2019analyse'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ActionLineCard extends StatelessWidget {
  const _ActionLineCard();

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: colors.canvas,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(Icons.bolt, color: _Brand.blue, size: 18),
          SizedBox(width: 10),
          Text(
            'Relancer 42 comptes',
            style: TextStyle(
              color: colors.ink,
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _SecurityCard extends StatelessWidget {
  const _SecurityCard();

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _Brand.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Votre entreprise reste la vôtre.',
            style: TextStyle(
              color: colors.ink,
              fontSize: 18,
              fontWeight: FontWeight.w800,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Espaces isolés, accès maîtrisés et architecture conçue pour évoluer.',
            style: TextStyle(color: colors.muted, fontSize: 13, height: 1.55),
          ),
          SizedBox(height: 14),
          _SecurityItem('Accès par rôle'),
          _SecurityItem('Traçabilité'),
          _SecurityItem('Hébergement évolutif'),
        ],
      ),
    );
  }
}

class _SecurityItem extends StatelessWidget {
  const _SecurityItem(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        children: [
          const Icon(Icons.shield_outlined, size: 14, color: _Brand.blue),
          const SizedBox(width: 8),
          Text(label, style: TextStyle(color: colors.ink, fontSize: 13)),
        ],
      ),
    );
  }
}

class _ModulesSection extends StatelessWidget {
  const _ModulesSection();

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).modulesSection;
    return _Section(
      color: AvenqoColors.of(context).canvas,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeading(
            kicker: t.kicker,
            title: t.title,
            subtitle: t.subtitle,
          ),
          const SizedBox(height: 32),
          LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth > 980
                  ? 4
                  : (constraints.maxWidth > 640 ? 2 : 1);
              final cardWidth =
                  (constraints.maxWidth - (columns - 1) * 20) / columns;
              return Wrap(
                spacing: 20,
                runSpacing: 20,
                children: [
                  for (final module in t.items)
                    SizedBox(
                      width: cardWidth,
                      child: _ModuleCard(
                        name: module.name,
                        description: module.description,
                        available: module.available,
                        discoverLabel: t.discover,
                        availableNowLabel: t.availableNow,
                        comingSoonLabel: t.comingSoon,
                      ),
                    ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _ModuleCard extends StatelessWidget {
  const _ModuleCard({
    required this.name,
    required this.description,
    required this.available,
    required this.discoverLabel,
    required this.availableNowLabel,
    required this.comingSoonLabel,
  });

  final String name;
  final String description;
  final bool available;
  final String discoverLabel;
  final String availableNowLabel;
  final String comingSoonLabel;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            name,
            style: TextStyle(
              color: colors.ink,
              fontSize: 15,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            description,
            style: TextStyle(color: colors.muted, fontSize: 13, height: 1.5),
          ),
          const SizedBox(height: 14),
          if (available)
            InkWell(
              onTap: () => context.go('/pricing'),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Flexible(
                    child: Text(
                      discoverLabel,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _Brand.blue,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(width: 4),
                  const Icon(Icons.arrow_forward, size: 14, color: _Brand.blue),
                ],
              ),
            )
          else
            Text(
              comingSoonLabel,
              style: TextStyle(
                color: colors.muted,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          if (available)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                availableNowLabel,
                style: const TextStyle(
                  color: _Brand.blue,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _StepsSection extends StatelessWidget {
  const _StepsSection();

  static const _steps = [
    (
      '01',
      'Créez votre espace',
      'Configurez votre entreprise en quelques minutes.',
    ),
    (
      '02',
      'Choisissez vos modules',
      'Activez uniquement les solutions dont vous avez besoin.',
    ),
    (
      '03',
      'Connectez vos outils',
      'Reliez vos ventes, votre CRM ou vos documents.',
    ),
    (
      '04',
      'Laissez Avenqo agir',
      'Recevez des réponses et des actions prêtes à exécuter.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return _Section(
      color: _Brand.ink,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionHeading(
            kicker: 'Simple dès le départ',
            title: 'Opérationnel en quatre étapes.',
            dark: true,
          ),
          const SizedBox(height: 40),
          LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth > 900
                  ? 4
                  : (constraints.maxWidth > 560 ? 2 : 1);
              final cardWidth =
                  (constraints.maxWidth - (columns - 1) * 24) / columns;
              return Wrap(
                spacing: 24,
                runSpacing: 24,
                children: [
                  for (final step in _steps)
                    SizedBox(
                      width: cardWidth,
                      child: _StepCard(
                        number: step.$1,
                        title: step.$2,
                        text: step.$3,
                      ),
                    ),
                ],
              );
            },
          ),
          const SizedBox(height: 32),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              const Text(
                'Prêt à démarrer ?',
                style: TextStyle(color: Colors.white70, fontSize: 13),
              ),
              const SizedBox(width: 10),
              InkWell(
                onTap: () => context.go('/register'),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Créer mon espace',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(width: 4),
                    Icon(Icons.arrow_forward, size: 14, color: Colors.white),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard({
    required this.number,
    required this.title,
    required this.text,
  });

  final String number;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.only(top: 16),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Color(0xFF2A2E38))),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            number,
            style: const TextStyle(
              color: _Brand.blue,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            text,
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }
}

class _UsecasesSection extends StatelessWidget {
  const _UsecasesSection();

  static const _items = [
    (
      'Direction',
      'Suivez les priorités et les résultats en temps réel.',
      Icons.apartment_outlined,
    ),
    (
      'Finance',
      'Anticipez les écarts et accélérez le suivi.',
      Icons.attach_money,
    ),
    (
      'Commerce',
      'Identifiez les clients et produits à fort potentiel.',
      Icons.shopping_bag_outlined,
    ),
    (
      'Opérations',
      'Automatisez les tâches qui ralentissent vos équipes.',
      Icons.account_tree_outlined,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return _Section(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth > 900;
          final copy = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _SectionHeading(
                kicker: 'Pour toute l\u2019entreprise',
                title: 'Une vision commune. Des équipes plus rapides.',
                subtitle:
                    'Direction, ventes, finance et opérations partagent enfin la même lecture de l\u2019activité.',
              ),
              const SizedBox(height: 24),
              for (final item in _items)
                _UsecaseRow(title: item.$1, text: item.$2, icon: item.$3),
            ],
          );
          const card = _UsecaseBrandCard();
          if (!wide) {
            return Column(children: [copy, const SizedBox(height: 32), card]);
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(flex: 6, child: copy),
              const SizedBox(width: 40),
              const Expanded(flex: 5, child: card),
            ],
          );
        },
      ),
    );
  }
}

class _UsecaseRow extends StatelessWidget {
  const _UsecaseRow({
    required this.title,
    required this.text,
    required this.icon,
  });

  final String title;
  final String text;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: colors.line)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: _Brand.blue),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: colors.ink,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 3),
                Text(text, style: TextStyle(color: colors.muted, fontSize: 13)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _UsecaseBrandCard extends StatelessWidget {
  const _UsecaseBrandCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: _Brand.ink,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Row(
            children: [
              AvenqoBrandIcon(size: 28),
              SizedBox(width: 10),
              Text(
                'Avenqo',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'PLATEFORME IA TOUT-EN-UN',
            style: TextStyle(
              color: Colors.white54,
              fontSize: 10,
              letterSpacing: 1.2,
            ),
          ),
          const SizedBox(height: 24),
          Wrap(
            spacing: 16,
            runSpacing: 16,
            children: const [
              _BrandFeatureChip('Intelligence artificielle'),
              _BrandFeatureChip('Automatisation intelligente'),
              _BrandFeatureChip('Analytique avancée'),
              _BrandFeatureChip('Sécurisée et évolutive'),
            ],
          ),
          const SizedBox(height: 24),
          const Divider(color: Color(0xFF2A2E38)),
          const SizedBox(height: 12),
          const Text(
            'avenqo.ca',
            style: TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const Text(
            'Une plateforme. Toutes vos solutions IA.',
            style: TextStyle(color: Colors.white54, fontSize: 11),
          ),
        ],
      ),
    );
  }
}

class _BrandFeatureChip extends StatelessWidget {
  const _BrandFeatureChip(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 150,
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _WhySection extends StatelessWidget {
  const _WhySection();

  static const _items = [
    (
      '01',
      'Modulaire par nature',
      'Commencez par une priorité et étendez la plateforme sans recommencer.',
    ),
    (
      '02',
      'Une expérience unifiée',
      'Une connexion, une interface et un assistant commun à tous vos modules.',
    ),
    (
      '03',
      'Accompagnement humain',
      'PMC Solutions AI vous accompagne de la connexion à l\u2019adoption.',
    ),
    (
      '04',
      'Prêt pour l\u2019entreprise',
      'Gestion des accès, espaces isolés et infrastructure évolutive.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return _Section(
      color: colors.canvas,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionHeading(
            kicker: 'Pourquoi Avenqo',
            title: 'Conçu pour grandir avec vous.',
          ),
          const SizedBox(height: 32),
          LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth > 900
                  ? 4
                  : (constraints.maxWidth > 560 ? 2 : 1);
              final cardWidth =
                  (constraints.maxWidth - (columns - 1) * 20) / columns;
              return Wrap(
                spacing: 20,
                runSpacing: 20,
                children: [
                  for (final item in _items)
                    SizedBox(
                      width: cardWidth,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            item.$1,
                            style: const TextStyle(
                              color: _Brand.blue,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            item.$2,
                            style: TextStyle(
                              color: colors.ink,
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            item.$3,
                            style: TextStyle(
                              color: colors.muted,
                              fontSize: 13,
                              height: 1.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}

class _PricingSection extends StatelessWidget {
  const _PricingSection();

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).pricing;
    return _Section(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeading(
            kicker: t.kicker,
            title: t.title,
            subtitle: t.subtitle,
          ),
          const SizedBox(height: 32),
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 900;
              final cards = [
                for (var i = 0; i < t.plans.length; i++)
                  _PricingCard(
                    tier: t.plans[i].tier,
                    title: t.plans[i].title,
                    priceLabel: t.plans[i].priceLabel,
                    items: t.plans[i].items,
                    action: t.plans[i].action,
                    onAction:
                        t.plans[i].tier.toLowerCase() == 'professional' ||
                            t.plans[i].tier.toLowerCase() == 'professionnel'
                        ? () => context.go('/register')
                        : _contactByEmail,
                    featured: i == 1,
                    popularLabel: t.popular,
                  ),
              ];
              if (!wide) {
                return Column(
                  children: [
                    for (final card in cards)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 20),
                        child: card,
                      ),
                  ],
                );
              }
              return IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (var i = 0; i < cards.length; i++) ...[
                      if (i > 0) const SizedBox(width: 20),
                      Expanded(child: cards[i]),
                    ],
                  ],
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

class _PricingCard extends StatelessWidget {
  const _PricingCard({
    required this.tier,
    required this.title,
    required this.priceLabel,
    required this.items,
    required this.action,
    required this.onAction,
    required this.popularLabel,
    this.featured = false,
  });

  final String tier;
  final String title;
  final String priceLabel;
  final List<String> items;
  final String action;
  final VoidCallback onAction;
  final String popularLabel;
  final bool featured;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final bg = featured ? colors.ink : colors.surface;
    final fg = featured ? colors.surface : colors.ink;
    final mutedFg = featured
        ? colors.surface.withValues(alpha: 0.78)
        : colors.muted;
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: featured ? colors.ink : colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (featured)
            Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: _Brand.blue,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                popularLabel.toUpperCase(),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 9,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          Text(
            tier.toUpperCase(),
            style: TextStyle(
              color: _Brand.blue,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            title,
            style: TextStyle(
              color: fg,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            priceLabel,
            style: TextStyle(
              color: fg,
              fontSize: 18,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 16),
          Divider(color: colors.line),
          const SizedBox(height: 12),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  const Icon(Icons.check, size: 14, color: _Brand.blue),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      item,
                      style: TextStyle(color: mutedFg, fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: featured
                ? FilledButton(
                    onPressed: onAction,
                    style: FilledButton.styleFrom(
                      backgroundColor: _Brand.blue,
                      foregroundColor: Colors.white,
                    ),
                    child: Text(action),
                  )
                : OutlinedButton(
                    onPressed: onAction,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: colors.ink,
                      side: BorderSide(color: colors.line),
                    ),
                    child: Text(action),
                  ),
          ),
        ],
      ),
    );
  }
}

class _FaqSection extends StatelessWidget {
  const _FaqSection();

  static const _items = [
    (
      'Avenqo remplace-t-il mes outils actuels ?',
      'Avenqo se connecte à votre environnement et rassemble décisions, recommandations et automatisations dans une expérience unique.',
    ),
    (
      'Puis-je commencer avec un seul module ?',
      'Oui. Commencez par votre priorité, puis ajoutez des capacités au rythme de votre entreprise.',
    ),
    (
      'Mes informations sont-elles isolées ?',
      'Oui. Chaque entreprise dispose de son propre espace, de ses accès et de ses informations strictement séparées.',
    ),
    (
      'Avenqo convient-il aux PME ?',
      'Oui. Les offres accompagnent aussi bien une équipe en croissance qu\u2019une organisation multisite.',
    ),
    (
      'Combien de temps faut-il pour démarrer ?',
      'La création de l\u2019espace est immédiate. Le délai de connexion dépend ensuite des outils choisis.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return _Section(
      color: AvenqoColors.of(context).canvas,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth > 900;
          final left = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              const _SectionHeading(
                kicker: 'Questions fréquentes',
                title: 'Tout ce qu\u2019il faut savoir.',
                subtitle:
                    'Une autre question ? Notre équipe vous répond directement.',
              ),
              const SizedBox(height: 16),
              InkWell(
                onTap: _contactByEmail,
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'bonjour@avenqo.ca',
                      style: TextStyle(
                        color: _Brand.blue,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(width: 4),
                    Icon(Icons.arrow_forward, size: 14, color: _Brand.blue),
                  ],
                ),
              ),
            ],
          );
          final right = Theme(
            data: Theme.of(
              context,
            ).copyWith(dividerColor: AvenqoColors.of(context).line),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final item in _items)
                  _FaqTile(question: item.$1, answer: item.$2),
              ],
            ),
          );
          if (!wide) {
            return Column(children: [left, const SizedBox(height: 32), right]);
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(flex: 5, child: left),
              const SizedBox(width: 40),
              Expanded(flex: 6, child: right),
            ],
          );
        },
      ),
    );
  }
}

class _FaqTile extends StatelessWidget {
  const _FaqTile({required this.question, required this.answer});

  final String question;
  final String answer;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Material(
      color: Colors.transparent,
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 16),
        iconColor: _Brand.blue,
        collapsedIconColor: _Brand.blue,
        title: Text(
          question,
          style: TextStyle(
            color: colors.ink,
            fontSize: 14,
            fontWeight: FontWeight.w700,
          ),
        ),
        children: [
          Align(
            alignment: Alignment.topLeft,
            child: Text(
              answer,
              style: TextStyle(color: colors.muted, fontSize: 13, height: 1.55),
            ),
          ),
        ],
      ),
    );
  }
}

class _FinalCtaSection extends StatelessWidget {
  const _FinalCtaSection();

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).finalCta;
    return _Section(
      color: _Brand.blue,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth > 780;
          final copy = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                t.label.toUpperCase(),
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.1,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                t.title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          );
          final actions = Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              FilledButton.icon(
                onPressed: () => context.go('/register'),
                style: FilledButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: _Brand.blueDark,
                ),
                icon: const Icon(Icons.arrow_forward, size: 16),
                label: Text(t.tryFree),
              ),
              const SizedBox(height: 10),
              InkWell(
                onTap: _contactByEmail,
                child: Text(
                  t.scheduleDemo,
                  style: const TextStyle(
                    color: Colors.white,
                    decoration: TextDecoration.underline,
                    fontSize: 13,
                  ),
                ),
              ),
            ],
          );
          if (!wide) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [copy, const SizedBox(height: 24), actions],
            );
          }
          return Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(child: copy),
              const SizedBox(width: 24),
              actions,
            ],
          );
        },
      ),
    );
  }
}

class _Footer extends StatelessWidget {
  const _Footer();

  static const _platformLinks = [
    'Fonctionnalités',
    'Modules',
    'Tarifs',
    'Fonctionnement',
  ];
  static const _companyLinks = [
    'À propos',
    'Contact',
    'Sécurité',
    'Partenaires',
  ];
  static const _resourcesLinks = [
    'Documentation',
    'FAQ',
    'Confidentialité',
    'Conditions',
  ];

  @override
  Widget build(BuildContext context) {
    return _Section(
      color: _Brand.ink,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 760;
              final brand = const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      AvenqoBrandIcon(size: 20),
                      SizedBox(width: 8),
                      Text(
                        'Avenqo',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: 10),
                  Text(
                    'Une plateforme.\nToutes vos solutions IA.',
                    style: TextStyle(
                      color: Colors.white54,
                      fontSize: 13,
                      height: 1.5,
                    ),
                  ),
                ],
              );
              final columns = Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _FooterColumn(
                      title: 'Plateforme',
                      links: _platformLinks,
                    ),
                  ),
                  Expanded(
                    child: _FooterColumn(
                      title: 'Entreprise',
                      links: _companyLinks,
                    ),
                  ),
                  Expanded(
                    child: _FooterColumn(
                      title: 'Ressources',
                      links: _resourcesLinks,
                    ),
                  ),
                ],
              );
              if (!wide) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [brand, const SizedBox(height: 32), columns],
                );
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 4, child: brand),
                  Expanded(flex: 6, child: columns),
                ],
              );
            },
          ),
          const SizedBox(height: 40),
          const Divider(color: Color(0xFF2A2E38)),
          const SizedBox(height: 16),
          const Text(
            '© 2026 Avenqo. Une plateforme de PMC Solutions AI.',
            style: TextStyle(color: Colors.white38, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _FooterColumn extends StatelessWidget {
  const _FooterColumn({required this.title, required this.links});

  final String title;
  final List<String> links;

  static const _routes = {
    'Fonctionnalités': '/pricing',
    'Modules': '/pricing',
    'Tarifs': '/pricing',
    'Fonctionnement': '/pricing',
    'À propos': '/pricing',
    'Sécurité': '/pricing',
    'Documentation': '/pricing',
    'FAQ': '/pricing',
  };

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 14),
        for (final link in links)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: InkWell(
              onTap: () {
                if (link == 'Contact' ||
                    link == 'Partenaires' ||
                    link == 'Confidentialité' ||
                    link == 'Conditions') {
                  _contactByEmail();
                } else {
                  context.go(_routes[link] ?? '/pricing');
                }
              },
              child: Text(
                link,
                style: const TextStyle(color: Colors.white70, fontSize: 13),
              ),
            ),
          ),
      ],
    );
  }
}
