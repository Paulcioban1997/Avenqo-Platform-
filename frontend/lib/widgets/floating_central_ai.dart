import 'dart:math' as math;

import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/central_ai_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/assistant_page.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class FloatingCentralAI extends StatefulWidget {
  const FloatingCentralAI({
    super.key,
    required this.api,
    required this.controller,
    required this.currentPath,
    this.onOpenFull,
  });

  final ApiClient api;
  final CentralAIController controller;
  final String currentPath;
  final VoidCallback? onOpenFull;

  @override
  State<FloatingCentralAI> createState() => _FloatingCentralAIState();
}

class _FloatingCentralAIState extends State<FloatingCentralAI> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final translations = AvenqoLocaleScope.translationsOf(context);
    final assistant = translations.assistant;
    if (!_open) {
      return Align(
        alignment: Alignment.bottomRight,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: FloatingActionButton(
            heroTag: 'central-ai-launcher',
            tooltip: assistant.avenqoAi,
            onPressed: () => setState(() => _open = true),
            child: const Icon(Icons.auto_awesome),
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final width = math.min(430.0, constraints.maxWidth - 24);
        final height = math.min(640.0, constraints.maxHeight - 24);
        return Align(
          alignment: Alignment.bottomRight,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Material(
              elevation: 18,
              clipBehavior: Clip.antiAlias,
              borderRadius: BorderRadius.circular(8),
              child: SizedBox(
                width: width,
                height: height,
                child: Column(
                  children: [
                    Container(
                      height: 52,
                      padding: const EdgeInsets.only(left: 16, right: 6),
                      color: Theme.of(context).colorScheme.surfaceContainerHighest,
                      child: Row(
                        children: [
                          const Icon(Icons.auto_awesome, size: 19),
                          const SizedBox(width: 8),
                          Expanded(child: Text(assistant.avenqoAi, style: const TextStyle(fontWeight: FontWeight.w700))),
                          IconButton(
                            tooltip: translations.company.navAssistantLabel,
                            onPressed: widget.onOpenFull ?? () => context.go('/assistant'),
                            icon: const Icon(Icons.open_in_full),
                          ),
                          IconButton(
                            tooltip: MaterialLocalizations.of(context).closeButtonTooltip,
                            onPressed: () => setState(() => _open = false),
                            icon: const Icon(Icons.close),
                          ),
                        ],
                      ),
                    ),
                    Expanded(
                      child: MediaQuery(
                        data: MediaQuery.of(context).copyWith(size: Size(width, height - 52)),
                        child: AssistantPage(
                          api: widget.api,
                          controller: widget.controller,
                          pageContext: widget.currentPath,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}