import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/agents/agent_catalog.dart';
import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class AgentsPage extends StatefulWidget {
  const AgentsPage({super.key, this.api, this.onOpenAgent});

  final ApiClient? api;
  final ValueChanged<AvenqoAgentDefinition>? onOpenAgent;

  @override
  State<AgentsPage> createState() => _AgentsPageState();
}

class _AgentsPageState extends State<AgentsPage> {
  Future<dynamic>? _entitlements;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    _entitlements = widget.api?.get('/modules/entitlements');
  }

  Future<void> _toggle(
    AvenqoAgentDefinition agent,
    Map<String, String> states,
  ) async {
    final action = states[agent.id] == 'active' ? 'deactivate' : 'activate';
    try {
      await widget.api!.post('/modules/${agent.id}/$action');
      if (mounted) setState(_reload);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.message)),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    final activeLabel = AvenqoLocaleScope.translationsOf(context)
        .phase4e
        .billingValue('statusActive');
    final colors = AvenqoColors.of(context);
    return FutureBuilder<dynamic>(
      future: _entitlements,
      builder: (context, snapshot) {
        final summary = snapshot.data as Map<String, dynamic>?;
        final modules = (summary?['modules'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();
        final states = {
          for (final module in modules)
            module['key'].toString(): module['state'].toString(),
        };
        final activeCount = (summary?['active_modules'] as List<dynamic>?)?.length ?? 0;
        final limit = summary?['module_limit'];
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(strings.title, style: Theme.of(context).textTheme.headlineMedium),
                ),
                if (summary != null)
                  Text(
                    '$activeCount / ${limit ?? '∞'}',
                    style: TextStyle(color: colors.muted, fontWeight: FontWeight.w700),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(strings.subtitle, style: TextStyle(color: colors.muted, fontSize: 15)),
            const SizedBox(height: 24),
            if (_entitlements != null && snapshot.connectionState != ConnectionState.done)
              const Center(child: CircularProgressIndicator())
            else
              AgentCatalog(
                strings: strings,
                showAccessActions: true,
                moduleStates: states,
                activeLabel: activeLabel,
                limitLabel: '$activeCount / ${limit ?? '∞'}',
                onToggle: widget.api == null ? null : (agent) => _toggle(agent, states),
                onOpen: widget.onOpenAgent ?? (agent) => context.go(agent.route!),
              ),
          ],
        );
      },
    );
  }
}