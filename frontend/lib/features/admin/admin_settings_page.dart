import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Réglages plateforme — n'affiche que ce qui existe réellement (identité de
/// l'admin connecté) ; aucun secret n'est exposé.
class AdminSettingsPage extends StatelessWidget {
  const AdminSettingsPage({super.key, required this.auth});
  final AuthController auth;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    final colors = AvenqoColors.of(context);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        AdminSectionHeader(title: s.settingsTitle),
        const SizedBox(height: 20),
        AdminCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(s.signedInAs, style: TextStyle(color: colors.muted, fontSize: 13)),
              const SizedBox(height: 6),
              Text(
                auth.user?['email']?.toString() ?? '—',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: colors.ink),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        AdminEmptyState(
          message: s.noSettingsMessage,
          icon: Icons.settings_outlined,
        ),
      ],
    );
  }
}
