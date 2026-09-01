import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/agents/agent_catalog.dart';
import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class AgentsPage extends StatelessWidget {
  const AgentsPage({super.key, this.onOpenAgent});

  final ValueChanged<AvenqoAgentDefinition>? onOpenAgent;

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    final colors = AvenqoColors.of(context);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(strings.title, style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 6),
        Text(strings.subtitle, style: TextStyle(color: colors.muted, fontSize: 15)),
        const SizedBox(height: 24),
        AgentCatalog(
          strings: strings,
          showAccessActions: true,
          onOpen: onOpenAgent ?? (agent) => context.go(agent.route!),
        ),
      ],
    );
  }
}