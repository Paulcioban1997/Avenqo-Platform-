import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/central_ai_controller.dart';
import 'package:avenqo/features/ai_chat/ai_chat_models.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter/services.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const ink = Color(0xFF080B12);
}

/// Chaînes de l'Assistant IA : suit la langue de l'app quand le scope
/// [AvenqoLocaleScope] est disponible, retombe sur l'anglais sinon (tests
/// isolés qui montent `AssistantPage` sans monter toute l'app).
AssistantStrings _assistantStrings(BuildContext context) =>
    AvenqoLocaleScope.maybeTranslationsOf(context)?.assistant ?? AssistantStrings.fallback();

class AssistantPage extends StatefulWidget {
  const AssistantPage({
    super.key,
    required this.api,
    this.controller,
    this.pageContext,
  });

  final ApiClient api;
  final CentralAIController? controller;
  final String? pageContext;

  @override
  State<AssistantPage> createState() => _AssistantPageState();
}

class _AssistantPageState extends State<AssistantPage> {
  final _composer = TextEditingController();
  final _scrollController = ScrollController();
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  CentralAIController? _controller;
  bool _ownsController = false;
  bool _nearBottom = true;
  int _lastMessageCount = 0;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_trackScrollPosition);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_controller != null) return;
    final scoped = CentralAIControllerScope.maybeOf(context);
    _controller = widget.controller ?? scoped ?? CentralAIController(widget.api);
    _ownsController = widget.controller == null && scoped == null;
    _controller!.addListener(_onControllerChanged);
    _controller!.initialize();
  }

  @override
  void dispose() {
    _controller?.removeListener(_onControllerChanged);
    if (_ownsController) _controller?.dispose();
    _composer.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onControllerChanged() {
    if (!mounted) return;
    final shouldScroll = _controller!.messages.length != _lastMessageCount;
    _lastMessageCount = _controller!.messages.length;
    setState(() {});
    if (shouldScroll) _scrollToBottom(force: true);
  }

  Future<void> _send([String? suggestedText]) async {
    final content = (suggestedText ?? _composer.text).trim();
    if (content.isEmpty || _controller!.generating) return;
    _composer.clear();
    await _controller!.send(
      content,
      statusMessage: _messageForStatus,
      pageContext: widget.pageContext,
        locale: AvenqoLocaleScope.maybeTranslationsOf(context) == null
          ? null
          : AvenqoLocaleScope.of(context).code,
    );
  }

  String _messageForStatus(String status) {
    final t = _assistantStrings(context);
    return switch (status) {
      'agent_unavailable' => t.agentComingSoon,
      'unsupported_intent' => t.unsupportedIntent,
      'not_entitled' => t.retailNotEntitled,
      'credits_exhausted' => t.creditsExhausted,
      _ => t.requestUnavailable,
    };
  }

  void _retryLastMessage() {
    _controller!.retryLastMessage(
      statusMessage: _messageForStatus,
      pageContext: widget.pageContext,
        locale: AvenqoLocaleScope.maybeTranslationsOf(context) == null
          ? null
          : AvenqoLocaleScope.of(context).code,
    );
  }

  void _trackScrollPosition() {
    if (!_scrollController.hasClients) return;
    final nearBottom = _scrollController.position.maxScrollExtent - _scrollController.offset < 120;
    if (nearBottom != _nearBottom && mounted) setState(() => _nearBottom = nearBottom);
  }

  void _scrollToBottom({bool force = false}) {
    if (!force && !_nearBottom) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(_scrollController.position.maxScrollExtent, duration: const Duration(milliseconds: 180), curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller!;
    final compact = MediaQuery.sizeOf(context).width < 900;
    final sidebar = ConversationSidebar(
      conversations: controller.conversations,
      selectedId: controller.selected?.id,
      loading: controller.loadingConversations,
      onNewConversation: controller.newConversation,
      onSelect: (conversation) {
        if (compact) Navigator.of(context).pop();
        controller.selectConversation(conversation);
      },
      onDelete: controller.deleteConversation,
    );
    final t = _assistantStrings(context);
    return Scaffold(
      key: _scaffoldKey,
      endDrawer: compact ? Drawer(child: SafeArea(child: sidebar)) : null,
      body: Row(children: [
        if (!compact) SizedBox(width: 276, child: sidebar),
        if (!compact) const VerticalDivider(width: 1),
        Expanded(child: Column(children: [
          ChatHeader(title: controller.selected?.title ?? t.avenqoAi, compact: compact, onOpenConversations: () => _scaffoldKey.currentState?.openEndDrawer()),
          if (controller.errorCode != null) ChatErrorState(message: t.requestUnavailable, retryLabel: t.retry, onRetry: controller.loadConversations),
          Expanded(
            child: controller.loadingMessages
                ? const Center(child: CircularProgressIndicator())
                : ChatMessages(
                    controller: _scrollController,
                    messages: controller.messages,
                    generating: controller.generating,
                    onSuggestion: _send,
                    onRetry: _retryLastMessage,
                    empty: controller.selected == null && controller.messages.isEmpty,
                  ),
          ),
          if (!_nearBottom && controller.messages.isNotEmpty)
            Align(alignment: Alignment.centerRight, child: Padding(padding: const EdgeInsets.only(right: 24), child: FilledButton.tonalIcon(onPressed: () => _scrollToBottom(force: true), icon: const Icon(Icons.arrow_downward), label: Text(t.newest)))),
          if (controller.remainingAiCredits != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 4),
              child: Row(children: [
                Expanded(child: Text('${t.remainingCredits}: ${controller.remainingAiCredits}')),
                if (controller.creditsExhausted)
                  FilledButton.icon(
                    onPressed: () => context.go('/billing'),
                    icon: const Icon(Icons.account_balance_wallet_outlined),
                    label: Text(t.manageCredits),
                  ),
              ]),
            ),
          ChatComposer(controller: _composer, generating: controller.generating, onSend: _send),
        ])),
      ]),
    );
  }
}

class ConversationSidebar extends StatelessWidget {
  const ConversationSidebar({super.key, required this.conversations, required this.selectedId, required this.loading, required this.onNewConversation, required this.onSelect, required this.onDelete});
  final List<Conversation> conversations;
  final String? selectedId;
  final bool loading;
  final VoidCallback onNewConversation;
  final ValueChanged<Conversation> onSelect;
  final ValueChanged<Conversation> onDelete;

  @override
  Widget build(BuildContext context) {
    final t = _assistantStrings(context);
    final colors = AvenqoColors.of(context);
    return Material(color: colors.surface, child: Column(children: [
      Padding(padding: const EdgeInsets.all(16), child: SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: onNewConversation, style: FilledButton.styleFrom(backgroundColor: _Brand.blue), icon: const Icon(Icons.add), label: Text(t.newConversation)))),
      Expanded(child: loading ? const Center(child: CircularProgressIndicator()) : conversations.isEmpty ? Padding(padding: const EdgeInsets.all(24), child: Text(t.conversationsEmpty, style: TextStyle(color: colors.muted))) : ListView.builder(itemCount: conversations.length, itemBuilder: (context, index) {
        final conversation = conversations[index];
        return ListTile(selected: conversation.id == selectedId, title: Text(conversation.title, maxLines: 2, overflow: TextOverflow.ellipsis), onTap: () => onSelect(conversation), trailing: IconButton(tooltip: t.deleteConversation, icon: const Icon(Icons.delete_outline), onPressed: () => onDelete(conversation)));
      })),
    ]));
  }
}

class ChatHeader extends StatelessWidget {
  const ChatHeader({super.key, required this.title, required this.compact, required this.onOpenConversations});
  final String title;
  final bool compact;
  final VoidCallback onOpenConversations;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(height: 72, padding: const EdgeInsets.symmetric(horizontal: 20), decoration: BoxDecoration(color: colors.surface, border: Border(bottom: BorderSide(color: colors.line))), child: Row(children: [
      if (compact) IconButton(tooltip: _assistantStrings(context).newConversation, onPressed: onOpenConversations, icon: const Icon(Icons.forum_outlined)),
      Expanded(child: Text(title, style: Theme.of(context).textTheme.titleLarge, maxLines: 1, overflow: TextOverflow.ellipsis)),
      const Icon(Icons.auto_awesome_outlined, color: _Brand.blue),
    ]));
  }
}

class ChatMessages extends StatelessWidget {
  const ChatMessages({super.key, required this.controller, required this.messages, required this.generating, required this.onSuggestion, required this.onRetry, required this.empty});
  final ScrollController controller;
  final List<ChatMessage> messages;
  final bool generating;
  final ValueChanged<String?> onSuggestion;
  final VoidCallback onRetry;
  final bool empty;
  @override
  Widget build(BuildContext context) {
    if (empty) {
      return LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: EmptyChatState(onSuggestion: onSuggestion),
          ),
        ),
      );
    }
    return ListView.builder(controller: controller, padding: const EdgeInsets.fromLTRB(20, 24, 20, 20), itemCount: messages.length + (generating ? 1 : 0), itemBuilder: (context, index) {
      if (index == messages.length) return const StreamingMessage();
      final message = messages[index];
      return message.role == ChatRole.user ? UserMessage(message: message) : AssistantMessage(message: message, onRetry: onRetry);
    });
  }
}

class EmptyChatState extends StatelessWidget {
  const EmptyChatState({super.key, required this.onSuggestion});
  final ValueChanged<String?> onSuggestion;
  @override
  Widget build(BuildContext context) {
    final t = _assistantStrings(context);
    return Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 680), child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 52, height: 52, decoration: BoxDecoration(color: _Brand.blue.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)), child: const Icon(Icons.auto_awesome, color: _Brand.blue)),
      const SizedBox(height: 18), Text(t.title, style: Theme.of(context).textTheme.headlineMedium, textAlign: TextAlign.center),
      const SizedBox(height: 10), Text(t.subtitle, textAlign: TextAlign.center),
      const SizedBox(height: 22), Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [for (final item in t.suggestions) ActionChip(avatar: const Icon(Icons.arrow_outward, size: 16), label: Text(item), onPressed: () => onSuggestion(item))]),
      const SizedBox(height: 20), TextButton.icon(onPressed: () => context.go('/connections'), icon: const Icon(Icons.sync_alt), label: Text(t.connectData)),
    ]))));
  }
}

class UserMessage extends StatelessWidget {
  const UserMessage({super.key, required this.message});
  final ChatMessage message;
  @override
  Widget build(BuildContext context) => Align(alignment: Alignment.centerRight, child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 680), child: Container(margin: const EdgeInsets.only(bottom: 18), padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: _Brand.ink, borderRadius: BorderRadius.circular(8)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(_assistantStrings(context).you, style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w700)), const SizedBox(height: 6), SelectableText(message.content, style: const TextStyle(color: Colors.white))]))));
}

class AssistantMessage extends StatelessWidget {
  const AssistantMessage({super.key, required this.message, required this.onRetry});
  final ChatMessage message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Align(alignment: Alignment.centerLeft, child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 760), child: Container(margin: const EdgeInsets.only(bottom: 18), padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: colors.surface, border: Border.all(color: colors.line), borderRadius: BorderRadius.circular(8)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [const Icon(Icons.auto_awesome_outlined, size: 18, color: _Brand.blue), const SizedBox(width: 8), Text(_assistantStrings(context).avenqoAi, style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink))]), const SizedBox(height: 10),
      if (message.content.isNotEmpty) MarkdownBody(data: message.content, selectable: true),
      if (message.error != null) MessageError(message: message.error!, onRetry: onRetry),
      if (message.sources.isNotEmpty) MessageSources(sources: message.sources),
    ]))));
  }
}

class StreamingMessage extends StatelessWidget {
  const StreamingMessage({super.key});
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.only(bottom: 16), child: Row(children: [const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2)), const SizedBox(width: 10), Text(_assistantStrings(context).thinking)]));
}

class MessageSources extends StatelessWidget {
  const MessageSources({super.key, required this.sources});
  final List<ChatSource> sources;
  @override
  Widget build(BuildContext context) => ExpansionTile(tilePadding: EdgeInsets.zero, title: Text('${_assistantStrings(context).sourcesLabel} · ${sources.length}', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)), children: [for (final source in sources) ListTile(dense: true, leading: const Icon(Icons.description_outlined, size: 18), title: Text(source.name))]);
}

class MessageError extends StatelessWidget {
  const MessageError({super.key, required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(margin: const EdgeInsets.only(top: 8), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: scheme.errorContainer, borderRadius: BorderRadius.circular(6)), child: Row(children: [Icon(Icons.error_outline, color: scheme.onErrorContainer), const SizedBox(width: 8), Expanded(child: Text(message, style: TextStyle(color: scheme.onErrorContainer))), TextButton(onPressed: onRetry, child: Text(_assistantStrings(context).retry))]));
  }
}

class ChatErrorState extends StatelessWidget {
  const ChatErrorState({super.key, required this.message, required this.onRetry, this.retryLabel});
  final String message;
  final VoidCallback onRetry;
  final String? retryLabel;
  @override
  Widget build(BuildContext context) => MaterialBanner(content: Text(message), actions: [TextButton(onPressed: onRetry, child: Text(retryLabel ?? _assistantStrings(context).retry))]);
}

class ChatComposer extends StatelessWidget {
  const ChatComposer({super.key, required this.controller, required this.generating, required this.onSend, this.onStop});
  final TextEditingController controller;
  final bool generating;
  final ValueChanged<String?> onSend;
  final VoidCallback? onStop;
  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(color: colors.surface, padding: const EdgeInsets.fromLTRB(20, 12, 20, 20), child: SafeArea(top: false, child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Expanded(child: Focus(onKeyEvent: (node, event) {
        if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.enter && !HardwareKeyboard.instance.isShiftPressed) {
          onSend(null);
          return KeyEventResult.handled;
        }
        return KeyEventResult.ignored;
      }, child: TextField(controller: controller, minLines: 1, maxLines: 5, textInputAction: TextInputAction.newline, decoration: InputDecoration(hintText: _assistantStrings(context).subtitle)))), const SizedBox(width: 10),
        generating
          ? onStop == null
            ? const SizedBox.square(dimension: 40, child: Padding(padding: EdgeInsets.all(10), child: CircularProgressIndicator(strokeWidth: 2)))
            : Tooltip(message: _assistantStrings(context).thinking, child: IconButton.filled(onPressed: onStop, style: IconButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error), icon: const Icon(Icons.stop)))
          : Tooltip(message: _assistantStrings(context).avenqoAi, child: IconButton.filled(onPressed: () => onSend(null), style: IconButton.styleFrom(backgroundColor: _Brand.blue), icon: const Icon(Icons.arrow_upward))),
    ])));
  }
}