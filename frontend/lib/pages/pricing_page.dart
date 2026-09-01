import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:avenqo/widgets/avenqo_brand.dart';
import 'package:avenqo/widgets/language_selector.dart';
import 'package:avenqo/widgets/theme_toggle_button.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

const _blue = Color(0xFF087CF0);

class PricingPage extends StatefulWidget {
  const PricingPage({super.key, required this.api, this.embedded = false});

  final ApiClient api;
  final bool embedded;

  @override
  State<PricingPage> createState() => _PricingPageState();
}

class _PricingPageState extends State<PricingPage> {
  late final Future<dynamic> _plansFuture = widget.api.get(
    '/billing/plans',
    authenticated: false,
  );

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final content = FutureBuilder<dynamic>(
      future: _plansFuture,
      builder: (context, snapshot) {
        final livePlans = snapshot.data is List
            ? snapshot.data as List<dynamic>
            : const <dynamic>[];
        return _PricingContent(
          livePlans: livePlans,
          loading: snapshot.connectionState != ConnectionState.done,
        );
      },
    );

    if (widget.embedded) return content;
    return Scaffold(
      backgroundColor: colors.canvas,
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [_PublicHeader(), content, const _PricingFooter()],
        ),
      ),
    );
  }
}

class _PublicHeader extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context);
    final colors = AvenqoColors.of(context);
    return Container(
      color: colors.surface,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1180),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 860;
              final brand = InkWell(
                onTap: () => context.go('/'),
                child: const AvenqoBrand(iconSize: 38, textSize: 20),
              );
              final preferences = Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ThemeToggleButton(foregroundColor: colors.muted),
                  const SizedBox(width: 4),
                  const LanguageSelector(),
                ],
              );
              final login = TextButton(
                onPressed: () => context.go('/login'),
                child: Text(t.common.login),
              );
              final register = FilledButton.icon(
                onPressed: () => context.go('/register'),
                style: FilledButton.styleFrom(
                  backgroundColor: _blue,
                  foregroundColor: Colors.white,
                ),
                icon: const Icon(Icons.arrow_forward, size: 16),
                label: Text(t.common.tryFree),
              );
              if (!wide) {
                return Column(
                  children: [
                    Row(
                      children: [
                        brand,
                        const Spacer(),
                        ThemeToggleButton(foregroundColor: colors.muted),
                      ],
                    ),
                    const SizedBox(height: 8),
                    const Align(
                      alignment: Alignment.centerRight,
                      child: LanguageSelector(),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(child: login),
                        const SizedBox(width: 8),
                        Expanded(child: register),
                      ],
                    ),
                  ],
                );
              }
              return Row(
                children: [
                  brand,
                  const Spacer(),
                  _HeaderLink(
                    t.nav.features,
                    () => context.go('/?section=features'),
                  ),
                  _HeaderLink(
                    t.nav.modules,
                    () => context.go('/?section=modules'),
                  ),
                  _HeaderLink(t.nav.pricing, () {}),
                  const SizedBox(width: 16),
                  preferences,
                  const SizedBox(width: 8),
                  login,
                  const SizedBox(width: 8),
                  register,
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _HeaderLink extends StatelessWidget {
  const _HeaderLink(this.label, this.onPressed);

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(onPressed: onPressed, child: Text(label));
  }
}

class _PricingContent extends StatelessWidget {
  const _PricingContent({required this.livePlans, required this.loading});

  final List<dynamic> livePlans;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context);
    final pricing = t.pricing;
    final colors = AvenqoColors.of(context);
    return Container(
      color: colors.surface,
      padding: const EdgeInsets.fromLTRB(24, 72, 24, 88),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1180),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      pricing.kicker.toUpperCase(),
                      style: const TextStyle(
                        color: _blue,
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.1,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      pricing.title,
                      style: TextStyle(
                        color: colors.ink,
                        fontSize: 46,
                        height: 1.08,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 18),
                    Text(
                      pricing.subtitle,
                      style: TextStyle(
                        color: colors.muted,
                        fontSize: 17,
                        height: 1.6,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 48),
              if (loading)
                const Padding(
                  padding: EdgeInsets.only(bottom: 16),
                  child: LinearProgressIndicator(minHeight: 2),
                ),
              LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth > 900;
                  final cards = [
                    for (var index = 0; index < pricing.plans.length; index++)
                      _PlanCard(
                        plan: pricing.plans[index],
                        price: _livePrice(index, pricing.plans[index]),
                        featured: index == 1,
                        popularLabel: pricing.popular,
                        onPressed: index == pricing.plans.length - 1
                            ? () => launchUrl(
                                Uri.parse('mailto:bonjour@avenqo.ca'),
                              )
                            : () => context.go('/register'),
                      ),
                  ];
                  if (!wide) {
                    return Column(
                      children: [
                        for (final card in cards) ...[
                          card,
                          const SizedBox(height: 20),
                        ],
                      ],
                    );
                  }
                  return IntrinsicHeight(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (var index = 0; index < cards.length; index++) ...[
                          if (index > 0) const SizedBox(width: 20),
                          Expanded(child: cards[index]),
                        ],
                      ],
                    ),
                  );
                },
              ),
              const SizedBox(height: 36),
              Wrap(
                spacing: 24,
                runSpacing: 12,
                children: [
                  _ValuePoint(
                    icon: Icons.credit_card_off_outlined,
                    label: t.common.noCreditCard,
                  ),
                  _ValuePoint(
                    icon: Icons.route_outlined,
                    label: t.common.guidedSetup,
                  ),
                  _ValuePoint(
                    icon: Icons.shield_outlined,
                    label: t.common.isolatedData,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _livePrice(int index, PricingPlan fallback) {
    if (index >= livePlans.length || livePlans[index] is! Map) {
      return fallback.priceLabel;
    }
    final plan = livePlans[index] as Map;
    final price = plan['monthly_price_usd'];
    return price == null ? fallback.priceLabel : '\$$price USD';
  }
}

class _PlanCard extends StatelessWidget {
  const _PlanCard({
    required this.plan,
    required this.price,
    required this.featured,
    required this.popularLabel,
    required this.onPressed,
  });

  final PricingPlan plan;
  final String price;
  final bool featured;
  final String popularLabel;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final background = featured ? colors.ink : colors.surface;
    final foreground = featured ? colors.surface : colors.ink;
    final secondary = featured
        ? colors.surface.withValues(alpha: 0.72)
        : colors.muted;
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: featured ? colors.ink : colors.line),
        boxShadow: featured
            ? [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.14),
                  blurRadius: 30,
                  offset: const Offset(0, 16),
                ),
              ]
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  plan.tier.toUpperCase(),
                  style: const TextStyle(
                    color: _blue,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1,
                  ),
                ),
              ),
              if (featured)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 9,
                    vertical: 5,
                  ),
                  decoration: BoxDecoration(
                    color: _blue,
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
            ],
          ),
          const SizedBox(height: 18),
          Text(
            plan.title,
            style: TextStyle(
              color: foreground,
              fontSize: 20,
              height: 1.25,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 18),
          Text(
            price,
            style: TextStyle(
              color: foreground,
              fontSize: 24,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 22),
          Divider(color: featured ? Colors.white24 : colors.line),
          const SizedBox(height: 18),
          for (final item in plan.items)
            Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.check_circle, size: 17, color: _blue),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      item,
                      style: TextStyle(
                        color: secondary,
                        fontSize: 14,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: featured
                ? FilledButton.icon(
                    onPressed: onPressed,
                    style: FilledButton.styleFrom(
                      backgroundColor: _blue,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 17),
                    ),
                    icon: const Icon(Icons.arrow_forward, size: 17),
                    label: Text(plan.action),
                  )
                : OutlinedButton.icon(
                    onPressed: onPressed,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: foreground,
                      side: BorderSide(color: colors.line),
                      padding: const EdgeInsets.symmetric(vertical: 17),
                    ),
                    icon: const Icon(Icons.arrow_forward, size: 17),
                    label: Text(plan.action),
                  ),
          ),
        ],
      ),
    );
  }
}

class _ValuePoint extends StatelessWidget {
  const _ValuePoint({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 17, color: _blue),
        const SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(
            color: colors.muted,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _PricingFooter extends StatelessWidget {
  const _PricingFooter();

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF080B12),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1180),
          child: LayoutBuilder(
            builder: (context, constraints) {
              const brand = AvenqoBrand(
                iconSize: 32,
                textSize: 18,
                lightOnDark: true,
              );
              final contact = TextButton.icon(
                onPressed: () =>
                    launchUrl(Uri.parse('mailto:bonjour@avenqo.ca')),
                style: TextButton.styleFrom(foregroundColor: Colors.white70),
                icon: const Icon(Icons.mail_outline, size: 17),
                label: const Text('bonjour@avenqo.ca'),
              );
              if (constraints.maxWidth < 520) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [brand, const SizedBox(height: 16), contact],
                );
              }
              return Row(children: [brand, const Spacer(), contact]);
            },
          ),
        ),
      ),
    );
  }
}
