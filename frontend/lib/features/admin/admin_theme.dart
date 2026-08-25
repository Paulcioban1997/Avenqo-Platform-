import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';

/// Palette Avenqo Command Center. `navy`/`navyElevated`/`blue`/semantic tones
/// are the fixed Avenqo brand identity (same in light/dark). Text/surface/
/// border tokens are theme-aware — see [AvenqoColors.of].
class AdminBrand {
  const AdminBrand._();

  static const navy = Color(0xFF0B1220);
  static const navyElevated = Color(0xFF121B2E);
  static const blue = Color(0xFF087CF0);
  static const blueDark = Color(0xFF0757C9);
  static const success = Color(0xFF12A454);
  static const warning = Color(0xFFB6790A);
  static const danger = Color(0xFFD1362F);
}

enum AdminStatusTone { positive, warning, negative, neutral }

/// Bandeau/carte de section avec titre + description optionnelle.
class AdminSectionHeader extends StatelessWidget {
  const AdminSectionHeader({super.key, required this.title, this.subtitle, this.trailing});

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: colors.ink),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 4),
                Text(subtitle!, style: TextStyle(color: colors.muted, fontSize: 14)),
              ],
            ],
          ),
        ),
        ?trailing,
      ],
    );
  }
}

/// Carte premium générique (fond blanc, bordure fine, coins arrondis, ombre subtile).
class AdminCard extends StatelessWidget {
  const AdminCard({super.key, required this.child, this.padding = const EdgeInsets.all(20)});

  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: colors.line),
        boxShadow: const [
          BoxShadow(color: Color(0x0A080B12), blurRadius: 18, offset: Offset(0, 8)),
        ],
      ),
      padding: padding,
      child: child,
    );
  }
}

/// Carte de métrique KPI avec icône, label, valeur et variation optionnelle.
class AdminMetricCard extends StatelessWidget {
  const AdminMetricCard({
    super.key,
    required this.label,
    required this.value,
    this.icon = Icons.insights_outlined,
    this.accent = AdminBrand.blue,
    this.caption,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color accent;
  final String? caption;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return AdminCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: accent.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: accent, size: 18),
          ),
          const SizedBox(height: 14),
          Text(label, style: TextStyle(color: colors.muted, fontSize: 13, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(color: colors.ink, fontSize: 26, fontWeight: FontWeight.w800)),
          if (caption != null) ...[
            const SizedBox(height: 4),
            Text(caption!, style: TextStyle(color: colors.muted, fontSize: 12)),
          ],
        ],
      ),
    );
  }
}

/// Badge de statut (READY / DEGRADED / UNAVAILABLE / ...).
class AdminStatusBadge extends StatelessWidget {
  const AdminStatusBadge({super.key, required this.label, required this.tone});

  final String label;
  final AdminStatusTone tone;

  Color _color(BuildContext context) {
    switch (tone) {
      case AdminStatusTone.positive:
        return AdminBrand.success;
      case AdminStatusTone.warning:
        return AdminBrand.warning;
      case AdminStatusTone.negative:
        return AdminBrand.danger;
      case AdminStatusTone.neutral:
        return AvenqoColors.of(context).muted;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _color(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        border: Border.all(color: color.withValues(alpha: 0.35)),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 6, height: 6, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

AdminStatusTone toneForProviderStatus(String? rawStatus) {
  final status = (rawStatus ?? '').toUpperCase();
  if (status.contains('READY') || status.contains('HEALTHY') || status.contains('OK')) {
    return AdminStatusTone.positive;
  }
  if (status.contains('DEGRADED') || status.contains('QUOTA')) {
    return AdminStatusTone.warning;
  }
  if (status.contains('UNAVAILABLE') || status.contains('UNHEALTHY') || status.contains('ERROR')) {
    return AdminStatusTone.negative;
  }
  return AdminStatusTone.neutral;
}

class AdminLoadingState extends StatelessWidget {
  const AdminLoadingState({super.key});

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 64),
      child: Center(child: CircularProgressIndicator()),
    );
  }
}

class AdminErrorState extends StatelessWidget {
  const AdminErrorState({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return AdminCard(
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AdminBrand.danger),
          const SizedBox(width: 14),
          Expanded(child: Text(message, style: TextStyle(color: AvenqoColors.of(context).ink))),
        ],
      ),
    );
  }
}

class AdminEmptyState extends StatelessWidget {
  const AdminEmptyState({super.key, required this.message, this.icon = Icons.inbox_outlined});

  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return AdminCard(
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AdminBrand.blue.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: AdminBrand.blue, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(child: Text(message, style: TextStyle(color: AvenqoColors.of(context).muted))),
        ],
      ),
    );
  }
}
