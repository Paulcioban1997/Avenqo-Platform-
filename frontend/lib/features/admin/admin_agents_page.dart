import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/agents/agent_catalog.dart';
import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class AdminAgentsPage extends StatelessWidget {
  const AdminAgentsPage({super.key, this.onOpenAgent});

  final ValueChanged<AvenqoAgentDefinition>? onOpenAgent;

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    final available = avenqoAgentRegistry.where((agent) => agent.isAvailable).length;
    final comingSoon = avenqoAgentRegistry.length - available;
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        AdminSectionHeader(title: strings.adminTitle, subtitle: strings.adminSubtitle),
        const SizedBox(height: 20),
        Wrap(
          spacing: 16,
          runSpacing: 16,
          children: [
            SizedBox(
              width: 230,
              child: AdminMetricCard(
                label: strings.availableCount,
                value: '$available',
                icon: Icons.check_circle_outline,
              ),
            ),
            SizedBox(
              width: 230,
              child: AdminMetricCard(
                label: strings.comingSoonCount,
                value: '$comingSoon',
                icon: Icons.schedule_outlined,
              ),
            ),
          ],
        ),
        const SizedBox(height: 24),
        AgentCatalog(
          strings: strings,
          showAccessActions: true,
          onOpen: onOpenAgent ?? (agent) => context.go('/admin/agents/${agent.id}'),
        ),
      ],
    );
  }
}