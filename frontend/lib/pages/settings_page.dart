import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:avenqo/widgets/language_selector.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
}

/// Real settings screen: account/company info from the authenticated
/// session, plus the actual functional theme and language controls (no
/// fabricated preferences — everything here reads/writes real state).
class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key, required this.auth});

  final AuthController auth;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final user = auth.user ?? const <String, dynamic>{};
    final company = auth.company ?? const <String, dynamic>{};
    final fullName = [user['first_name'], user['last_name']]
        .whereType<String>()
        .where((part) => part.trim().isNotEmpty)
        .join(' ');
    final planCode = company['subscription_plan']?.toString();

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(t.settingsTitle, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 6),
              Text(
                t.settingsSubtitle,
                style: TextStyle(color: colors.muted),
              ),
              const SizedBox(height: 28),
              _SettingsSection(
                title: t.settingsAccountSection,
                colors: colors,
                children: [
                  _InfoRow(label: t.settingsNameLabel, value: fullName.isEmpty ? '—' : fullName, colors: colors),
                  _InfoRow(label: t.settingsEmailLabel, value: user['email']?.toString() ?? '—', colors: colors),
                  _InfoRow(label: t.settingsRoleLabel, value: user['role']?.toString() ?? '—', colors: colors),
                ],
              ),
              const SizedBox(height: 20),
              _SettingsSection(
                title: t.settingsCompanySection,
                colors: colors,
                children: [
                  _InfoRow(label: t.settingsNameLabel, value: company['name']?.toString() ?? '—', colors: colors),
                  _InfoRow(
                    label: t.settingsPlanLabel,
                    value: planCode == null ? '—' : '${planCode[0].toUpperCase()}${planCode.substring(1)}',
                    colors: colors,
                  ),
                  const SizedBox(height: 12),
                  TextButton.icon(
                    onPressed: () => context.go('/billing'),
                    icon: const Icon(Icons.credit_card, size: 18, color: _Brand.blue),
                    label: Text(t.settingsManageSubscription, style: const TextStyle(color: _Brand.blue)),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              _SettingsSection(
                title: t.settingsAppearanceSection,
                colors: colors,
                children: [
                  Row(
                    children: [
                      Expanded(child: Text(t.settingsThemeLabel, style: TextStyle(color: colors.ink))),
                      _ThemeModeSelector(t: t),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(child: Text(t.settingsLanguageLabel, style: TextStyle(color: colors.ink))),
                      const LanguageSelector(foregroundColor: _Brand.blue),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 20),
              _SettingsSection(
                title: t.settingsSessionSection,
                colors: colors,
                children: [
                  OutlinedButton.icon(
                    onPressed: auth.busy ? null : auth.logout,
                    icon: const Icon(Icons.logout),
                    label: Text(t.settingsLogout),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ThemeModeSelector extends StatelessWidget {
  const _ThemeModeSelector({required this.t});

  final CompanyStrings t;

  String _labelFor(ThemeMode mode) => switch (mode) {
        ThemeMode.light => t.settingsThemeLight,
        ThemeMode.dark => t.settingsThemeDark,
        ThemeMode.system => t.settingsThemeSystem,
      };

  @override
  Widget build(BuildContext context) {
    final controller = AvenqoThemeScope.of(context);
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        return SegmentedButton<ThemeMode>(
          segments: [
            for (final mode in ThemeMode.values)
              ButtonSegment(value: mode, label: Text(_labelFor(mode))),
          ],
          selected: {controller.mode},
          onSelectionChanged: (selection) => controller.setMode(selection.first),
        );
      },
    );
  }
}

class _SettingsSection extends StatelessWidget {
  const _SettingsSection({required this.title, required this.colors, required this.children});

  final String title;
  final AvenqoColors colors;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: colors.ink)),
          const SizedBox(height: 14),
          ...children,
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value, required this.colors});

  final String label;
  final String value;
  final AvenqoColors colors;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          SizedBox(width: 110, child: Text(label, style: TextStyle(color: colors.muted, fontSize: 13))),
          Expanded(child: Text(value, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }
}
