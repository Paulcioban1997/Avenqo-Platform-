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
  });

  final AgentStrings strings;
  final ValueChanged<AvenqoAgentDefinition>? onOpen;
  final bool showAccessActions;

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
                  onOpen: showAccessActions && agent.isAvailable
                      ? () => onOpen?.call(agent)
                      : null,
                  showAccessAction: showAccessActions && agent.isAvailable,
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
    required this.onOpen,
    required this.showAccessAction,
  });

  final AvenqoAgentDefinition agent;
  final AgentStrings strings;
  final VoidCallback? onOpen;
  final bool showAccessAction;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final available = agent.isAvailable;
    final accent = available ? const Color(0xFF087CF0) : colors.muted;
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
            ],
          ),
          const SizedBox(height: 16),
          Text(
            strings.value(agent.descriptionKey),
            style: TextStyle(color: colors.muted, height: 1.45),
          ),
          const SizedBox(height: 18),
          _AvailabilityBadge(
            label: available ? strings.availableNow : strings.comingSoon,
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