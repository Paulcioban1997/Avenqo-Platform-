import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/ai_chat_api.dart';
import 'package:avenqo/features/ai_chat/ai_chat_models.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:flutter/foundation.dart';
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
  const AssistantPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<AssistantPage> createState() => _AssistantPageState();
}

class _AssistantPageState extends State<AssistantPage> {
  final _composer = TextEditingController();
  final _scrollController = ScrollController();
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  late final AiChatApi _chat = AiChatApi(widget.api);
  List<Conversation> _conversations = const [];
  List<ChatMessage> _messages = const [];
  Conversation? _selected;
  bool _loadingConversations = true;
  bool _loadingMessages = false;
  bool _generating = false;
  bool _nearBottom = true;
  String? _error;
  int? _remainingAiCredits;
  bool _creditsExhausted = false;

  String _devFriendlyMessage(ApiException error) {
    if (kReleaseMode) return error.message;
    final detail = error.message.toLowerCase();
    if (error.statusCode == 401) return 'DEV: erreur_auth';
    if (error.statusCode == 429 || detail.contains('quota')) return 'DEV: quota_atteint';
    if (detail.contains('provider_non_configure')) return 'DEV: provider_non_configure';
    if (detail.contains('provider_inaccessible')) return 'DEV: backend_ou_provider_inaccessible';
    if (detail.contains('no business data') || detail.contains('dataset')) return 'DEV: dataset_indisponible';
    return 'DEV: ${error.message}';
  }


  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_trackScrollPosition);
    _loadConversations();
  }

  @override
  void dispose() {
    _composer.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadConversations() async {
    setState(() {
      _loadingConversations = true;
      _error = null;
    });
    try {
      final conversations = await _chat.listConversations();
      if (mounted) setState(() => _conversations = conversations);
    } on ApiException {
      if (mounted) {
        setState(() => _error = "Avenqo couldn't load your conversations. Please try again.");
      }
    } finally {
      if (mounted) setState(() => _loadingConversations = false);
    }
  }

  Future<void> _selectConversation(Conversation conversation) async {
    if (_generating) return;
    setState(() {
      _selected = conversation;
      _messages = const [];
      _loadingMessages = true;
      _error = null;
    });
    try {
      final detail = await _chat.getConversation(conversation.id);
      if (mounted && _selected?.id == conversation.id) {
        setState(() => _messages = detail.messages);
        _scrollToBottom(force: true);
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        if (error.statusCode == 404) {
          _conversations = _conversations.where((item) => item.id != conversation.id).toList();
          _selected = null;
        }
        _error = "Avenqo couldn't open this conversation. Please try again.";
      });
    } finally {
      if (mounted) setState(() => _loadingMessages = false);
    }
  }

  void _newConversation() {
    if (_generating) return;
    setState(() {
      _selected = null;
      _messages = const [];
      _error = null;
    });
  }

  Future<void> _send([String? suggestedText]) async {
    final content = (suggestedText ?? _composer.text).trim();
    if (content.isEmpty || _generating) return;
    _composer.clear();
    try {
      var conversation = _selected;
      if (conversation == null) {
        conversation = await _chat.createConversation(_titleFor(content));
        if (!mounted) return;
        setState(() {
          _selected = conversation;
          _conversations = [conversation!, ..._conversations];
        });
      }
      final now = DateTime.now();
      setState(() {
        _generating = true;
        _error = null;
        _creditsExhausted = false;
        _messages = [
          ..._messages,
          ChatMessage(id: 'local-user-${now.microsecondsSinceEpoch}', role: ChatRole.user, content: content, createdAt: now),
          ChatMessage(id: 'local-assistant-${now.microsecondsSinceEpoch}', role: ChatRole.assistant, content: '', createdAt: now),
        ];
      });
      _scrollToBottom(force: true);
      final result = await _chat.sendCentralMessage(conversation.id, content);
      if (!mounted) return;
      final response = result.answer ?? _messageForStatus(result.status);
      setState(() {
        final last = _messages.last;
        _messages = [
          ..._messages.take(_messages.length - 1),
          last.copyWith(content: response),
        ];
        _remainingAiCredits = result.remainingAiCredits;
        _creditsExhausted = result.status == 'credits_exhausted';
        _generating = false;
      });
      _scrollToBottom();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _generating = false;
        _error = error.statusCode == 401
            ? 'Your session has expired. Please sign in again.'
            : (kReleaseMode
                ? "Avenqo couldn't start this conversation. Please try again."
                : _devFriendlyMessage(error));
      });
    }
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
    for (final message in _messages.reversed) {
      if (message.role == ChatRole.user) {
        _send(message.content);
        return;
      }
    }
  }

  Future<void> _deleteConversation(Conversation conversation) async {
    if (_generating) return;
    try {
      await _chat.deleteConversation(conversation.id);
      if (!mounted) return;
      setState(() {
        _conversations = _conversations.where((item) => item.id != conversation.id).toList();
        if (_selected?.id == conversation.id) {
          _selected = null;
          _messages = const [];
        }
      });
    } on ApiException {
      if (mounted) setState(() => _error = "Avenqo couldn't delete this conversation. Please try again.");
    }
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

  String _titleFor(String content) => content.length > 54 ? '${content.substring(0, 54)}...' : content;

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 900;
    final sidebar = ConversationSidebar(
      conversations: _conversations,
      selectedId: _selected?.id,
      loading: _loadingConversations,
      onNewConversation: _newConversation,
      onSelect: (conversation) {
        if (compact) Navigator.of(context).pop();
        _selectConversation(conversation);
      },
      onDelete: _deleteConversation,
    );
    final t = _assistantStrings(context);
    return Scaffold(
      key: _scaffoldKey,
      endDrawer: compact ? Drawer(child: SafeArea(child: sidebar)) : null,
      body: Row(children: [
        if (!compact) SizedBox(width: 276, child: sidebar),
        if (!compact) const VerticalDivider(width: 1),
        Expanded(child: Column(children: [
          ChatHeader(title: _selected?.title ?? t.avenqoAi, compact: compact, onOpenConversations: () => _scaffoldKey.currentState?.openEndDrawer()),
          if (_error != null) ChatErrorState(message: _error!, retryLabel: t.retry, onRetry: _loadConversations),
          Expanded(
            child: _loadingMessages
                ? const Center(child: CircularProgressIndicator())
                : ChatMessages(
                    controller: _scrollController,
                    messages: _messages,
                    generating: _generating,
                    onSuggestion: _send,
                    onRetry: _retryLastMessage,
                    empty: _selected == null && _messages.isEmpty,
                  ),
          ),
          if (!_nearBottom && _messages.isNotEmpty)
            Align(alignment: Alignment.centerRight, child: Padding(padding: const EdgeInsets.only(right: 24), child: FilledButton.tonalIcon(onPressed: () => _scrollToBottom(force: true), icon: const Icon(Icons.arrow_downward), label: Text(t.newest)))),
          if (_remainingAiCredits != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 4),
              child: Row(children: [
                Expanded(child: Text('${t.remainingCredits}: $_remainingAiCredits')),
                if (_creditsExhausted)
                  FilledButton.icon(
                    onPressed: () => context.go('/billing'),
                    icon: const Icon(Icons.account_balance_wallet_outlined),
                    label: Text(t.manageCredits),
                  ),
              ]),
            ),
          ChatComposer(controller: _composer, generating: _generating, onSend: _send),
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
      if (compact) IconButton(tooltip: 'Conversations', onPressed: onOpenConversations, icon: const Icon(Icons.forum_outlined)),
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
      return SingleChildScrollView(
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height,
          child: EmptyChatState(onSuggestion: onSuggestion),
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
  const ChatComposer({super.key, required this.controller, required this.generating, required this.onSend});
  final TextEditingController controller;
  final bool generating;
  final ValueChanged<String?> onSend;
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
      }, child: TextField(controller: controller, minLines: 1, maxLines: 5, textInputAction: TextInputAction.newline, decoration: const InputDecoration(hintText: 'Ask Avenqo anything about your business...')))), const SizedBox(width: 10),
        generating
          ? const SizedBox.square(dimension: 40, child: Padding(padding: EdgeInsets.all(10), child: CircularProgressIndicator(strokeWidth: 2)))
          : Tooltip(message: 'Send message', child: IconButton.filled(onPressed: () => onSend(null), style: IconButton.styleFrom(backgroundColor: _Brand.blue), icon: const Icon(Icons.arrow_upward))),
    ])));
  }
}