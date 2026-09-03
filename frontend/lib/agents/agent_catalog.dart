import 'package:flutter/material.dart';
import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/i18n/translations.dart';

class AgentCatalog extends StatelessWidget {
  const AgentCatalog({
    super.key,
    required this.strings,
    this.onOpen,
    this.showAccessActions = false,
    this.moduleStates = const {},
    this.activeLabel,
    this.limitLabel,
    this.onToggle,
  });

  final AgentStrings strings;
  final ValueChanged<AvenqoAgentDefinition>? onOpen;
  final bool showAccessActions;
  final Map<String, String> moduleStates;
  final String? activeLabel;
  final String? limitLabel;
  final ValueChanged<AvenqoAgentDefinition>? onToggle;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 1080
            ? 3
            : constraints.maxWidth >= 680
                ? 2
                : 1;
        const spacing = 16.0;
        final cardWidth = (constraints.maxWidth - spacing * (columns - 1)) / columns;
        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: [
            for (final agent in avenqoAgentRegistry)
              SizedBox(
                width: cardWidth,
                child: _AgentCard(
                  agent: agent,
                  strings: strings,
                  state: moduleStates[agent.id],
                  activeLabel: activeLabel,
                  limitLabel: limitLabel,
                  onToggle: onToggle == null
                      ? null
                      : () => onToggle!.call(agent),
                  onOpen: showAccessActions &&
                          (moduleStates.isEmpty
                              ? agent.isAvailable
                              : moduleStates[agent.id] == 'active')
                      ? () => onOpen?.call(agent)
                      : null,
                  showAccessAction: showAccessActions &&
                      (moduleStates.isEmpty
                          ? agent.isAvailable
                          : moduleStates[agent.id] == 'active'),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _AgentCard extends StatelessWidget {
  const _AgentCard({
    required this.agent,
    required this.strings,
    required this.state,
    required this.activeLabel,
    required this.limitLabel,
    required this.onToggle,
    required this.onOpen,
    required this.showAccessAction,
  });

  final AvenqoAgentDefinition agent;
  final AgentStrings strings;
  final String? state;
  final String? activeLabel;
  final String? limitLabel;
  final VoidCallback? onToggle;
  final VoidCallback? onOpen;
  final bool showAccessAction;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final available = state == null
        ? agent.isAvailable
        : const {'active', 'available'}.contains(state);
    final accent = available ? const Color(0xFF087CF0) : colors.muted;
    final badgeLabel = switch (state) {
      'active' => activeLabel ?? strings.availableNow,
      'limit_reached' => limitLabel ?? strings.availableNow,
      'coming_soon' => strings.comingSoon,
      'unavailable' => strings.comingSoon,
      'upgrade_required' => strings.comingSoon,
      _ => available ? strings.availableNow : strings.comingSoon,
    };
    return Container(
      constraints: const BoxConstraints(minHeight: 230),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: available ? accent.withValues(alpha: 0.35) : colors.line),
        borderRadius: BorderRadius.circular(8),
        boxShadow: const [
          BoxShadow(color: Color(0x0A080B12), blurRadius: 18, offset: Offset(0, 8)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(_iconFor(agent.iconIdentifier), color: accent, size: 21),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  strings.value(agent.nameKey),
                  style: TextStyle(color: colors.ink, fontSize: 17, fontWeight: FontWeight.w800),
                ),
              ),
              if (state != null)
                Tooltip(
                  message: badgeLabel,
                  child: Switch(
                    value: state == 'active',
                    onChanged: const {'active', 'available'}.contains(state)
                        ? (_) => onToggle?.call()
                        : null,
                  ),
                ),
              ],
          ),
          const SizedBox(height: 16),
          Text(
            strings.value(agent.descriptionKey),
            style: TextStyle(color: colors.muted, height: 1.45),
          ),
          const SizedBox(height: 18),
          _AvailabilityBadge(
            label: badgeLabel,
            available: available,
          ),
          if (showAccessAction) ...[
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: onOpen,
              icon: const Icon(Icons.arrow_forward, size: 17),
              label: Text(strings.openAgent),
            ),
          ],
        ],
      ),
    );
  }
}

class _AvailabilityBadge extends StatelessWidget {
  const _AvailabilityBadge({required this.label, required this.available});

  final String label;
  final bool available;

  @override
  Widget build(BuildContext context) {
    final color = available ? const Color(0xFF087CF0) : AvenqoColors.of(context).muted;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700)),
    );
  }
}

IconData _iconFor(String identifier) => switch (identifier) {
      'storefront' => Icons.storefront_outlined,
      'campaign' => Icons.campaign_outlined,
      'contacts' => Icons.contacts_outlined,
      'groups' => Icons.groups_outlined,
      'account_balance' => Icons.account_balance_outlined,
      'document_scanner' => Icons.document_scanner_outlined,
      'mic' => Icons.mic_none_outlined,
      'perm_media' => Icons.perm_media_outlined,
      'gavel' => Icons.gavel_outlined,
      'calendar_month' => Icons.calendar_month_outlined,
      'account_tree' => Icons.account_tree_outlined,
      _ => Icons.extension_outlined,
    };