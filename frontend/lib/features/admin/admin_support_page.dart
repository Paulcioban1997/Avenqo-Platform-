import 'package:flutter/material.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Escalades/support plateforme. Aucun backend de tickets n'existe encore —
/// état vide honnête plutôt que des tickets fictifs.
class AdminSupportPage extends StatelessWidget {
  const AdminSupportPage({super.key, required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        AdminSectionHeader(
          title: s.supportTitle,
          subtitle: s.supportSubtitle,
        ),
        const SizedBox(height: 20),
        AdminEmptyState(
          message: s.noSupportMessage,
          icon: Icons.support_agent_outlined,
        ),
      ],
    );
  }
}
