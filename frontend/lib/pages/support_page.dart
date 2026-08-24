import 'dart:async';

import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/ai_chat_models.dart';
import 'package:avenqo/features/ai_support/ai_support_api.dart';
import 'package:avenqo/pages/assistant_page.dart'
    show ChatComposer, ChatHeader, ChatErrorState, ConversationSidebar, MessageError, MessageSources, StreamingMessage, UserMessage;
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
}

/// Avenqo Support (Phase 32) — help/support assistant, entirely separate
/// from [AssistantPage] (Business Assistant): its own API (`/support/chat`),
/// its own conversation history, and it never has access to business data.
/// Reuses the same generic chat widgets (header/sidebar/composer/messages
/// shell) to avoid duplicating the whole chat UI stack.
class SupportPage extends StatefulWidget {
  const SupportPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<SupportPage> createState() => _SupportPageState();
}

class _SupportPageState extends State<SupportPage> {
  final _composer = TextEditingController();
  final _scrollController = ScrollController();
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  late final AiSupportApi _support = AiSupportApi(widget.api);
  StreamSubscription<ChatStreamEvent>? _stream;
  List<Conversation> _conversations = const [];
  List<ChatMessage> _messages = const [];
  Conversation? _selected;
  bool _loadingConversations = true;
  bool _loadingMessages = false;
  bool _generating = false;
  bool _nearBottom = true;
  String? _error;
  String? _statusMessage;

  static const suggestions = <String>[
    'How do I import a CSV file?',
    "What's included in my plan?",
    'How do I connect a data source?',
    'What does this error message mean?',
  ];

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_trackScrollPosition);
    _loadConversations();
  }

  @override
  void dispose() {
    _stream?.cancel();
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
      final conversations = await _support.listConversations();
      if (mounted) setState(() => _conversations = conversations);
    } on ApiException {
      if (mounted) {
        setState(() => _error = "Avenqo Support couldn't load your conversations. Please try again.");
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
      final detail = await _support.getConversation(conversation.id);
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
        _error = "Avenqo Support couldn't open this conversation. Please try again.";
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
        conversation = await _support.createConversation(_titleFor(content));
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
        _statusMessage = null;
        _messages = [
          ..._messages,
          ChatMessage(id: 'local-user-${now.microsecondsSinceEpoch}', role: ChatRole.user, content: content, createdAt: now),
          ChatMessage(id: 'local-assistant-${now.microsecondsSinceEpoch}', role: ChatRole.assistant, content: '', createdAt: now),
        ];
      });
      _scrollToBottom(force: true);
      _stream = _support.streamMessage(conversation.id, content).listen(
        _handleStreamEvent,
        onError: (_) => _completeStreamWithError(),
        onDone: _completeStream,
        cancelOnError: true,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.statusCode == 401
          ? 'Your session has expired. Please sign in again.'
          : "Avenqo Support couldn't start this conversation. Please try again.");
    }
  }

  void _handleStreamEvent(ChatStreamEvent event) {
    if (!mounted || _messages.isEmpty) return;
    if (event.status != null) {
      setState(() => _statusMessage = event.status);
      return;
    }
    setState(() {
      final last = _messages.last;
      _statusMessage = null;
      _messages = [
        ..._messages.take(_messages.length - 1),
        last.copyWith(
          content: '${last.content}${event.chunk ?? ''}',
          sources: event.sources.isEmpty ? null : event.sources,
        ),
      ];
    });
    _scrollToBottom();
  }

  void _completeStream() {
    if (mounted) setState(() { _generating = false; _statusMessage = null; });
    _stream = null;
  }

  void _completeStreamWithError() {
    if (!mounted || _messages.isEmpty) return;
    setState(() {
      final last = _messages.last.copyWith(error: "Avenqo Support couldn't complete this request. Please try again.");
      _messages = [..._messages.take(_messages.length - 1), last];
      _generating = false;
      _statusMessage = null;
    });
    _stream = null;
  }

  Future<void> _stopGenerating() async {
    await _stream?.cancel();
    _stream = null;
    if (mounted) setState(() { _generating = false; _statusMessage = null; });
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
      await _support.deleteConversation(conversation.id);
      if (!mounted) return;
      setState(() {
        _conversations = _conversations.where((item) => item.id != conversation.id).toList();
        if (_selected?.id == conversation.id) {
          _selected = null;
          _messages = const [];
        }
      });
    } on ApiException {
      if (mounted) setState(() => _error = "Avenqo Support couldn't delete this conversation. Please try again.");
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
    return Scaffold(
      key: _scaffoldKey,
      endDrawer: compact ? Drawer(child: SafeArea(child: sidebar)) : null,
      body: Row(children: [
        if (!compact) SizedBox(width: 276, child: sidebar),
        if (!compact) const VerticalDivider(width: 1),
        Expanded(child: Column(children: [
          ChatHeader(title: _selected?.title ?? 'Avenqo Support', compact: compact, onOpenConversations: () => _scaffoldKey.currentState?.openEndDrawer()),
          if (_error != null) ChatErrorState(message: _error!, onRetry: _loadConversations),
          Expanded(
            child: _loadingMessages
                ? const Center(child: CircularProgressIndicator())
                : _SupportChatMessages(
                    controller: _scrollController,
                    messages: _messages,
                    generating: _generating,
                    onSuggestion: _send,
                    onRetry: _retryLastMessage,
                    empty: _selected == null && _messages.isEmpty,
                  ),
          ),
          if (!_nearBottom && _messages.isNotEmpty)
            Align(alignment: Alignment.centerRight, child: Padding(padding: const EdgeInsets.only(right: 24), child: FilledButton.tonalIcon(onPressed: () => _scrollToBottom(force: true), icon: const Icon(Icons.arrow_downward), label: const Text('Newest')))),
          if (_statusMessage != null)
            Padding(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 4), child: Align(alignment: Alignment.centerLeft, child: Text(_statusMessage!, style: Theme.of(context).textTheme.bodySmall?.copyWith(fontStyle: FontStyle.italic)))),
          ChatComposer(controller: _composer, generating: _generating, onSend: _send, onStop: _stopGenerating),
        ])),
      ]),
    );
  }
}

class _SupportChatMessages extends StatelessWidget {
  const _SupportChatMessages({required this.controller, required this.messages, required this.generating, required this.onSuggestion, required this.onRetry, required this.empty});
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
          child: _SupportEmptyState(onSuggestion: onSuggestion),
        ),
      );
    }
    return ListView.builder(controller: controller, padding: const EdgeInsets.fromLTRB(20, 24, 20, 20), itemCount: messages.length + (generating ? 1 : 0), itemBuilder: (context, index) {
      if (index == messages.length) return const StreamingMessage();
      final message = messages[index];
      return message.role == ChatRole.user ? UserMessage(message: message) : _SupportAssistantMessage(message: message, onRetry: onRetry);
    });
  }
}

class _SupportEmptyState extends StatelessWidget {
  const _SupportEmptyState({required this.onSuggestion});
  final ValueChanged<String?> onSuggestion;

  @override
  Widget build(BuildContext context) => Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 680), child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [
    Container(width: 52, height: 52, decoration: BoxDecoration(color: _Brand.blue.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)), child: const Icon(Icons.help_outline, color: _Brand.blue)),
    const SizedBox(height: 18), Text('Ask Avenqo Support', style: Theme.of(context).textTheme.headlineMedium, textAlign: TextAlign.center),
    const SizedBox(height: 10), const Text("Ask how to use Avenqo — imports, connections, plans, or an error message you saw. This assistant never accesses your business data.", textAlign: TextAlign.center),
    const SizedBox(height: 22), Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [for (final item in _SupportPageState.suggestions) ActionChip(avatar: const Icon(Icons.arrow_outward, size: 16), label: Text(item), onPressed: () => onSuggestion(item))]),
  ]))));
}

class _SupportAssistantMessage extends StatelessWidget {
  const _SupportAssistantMessage({required this.message, required this.onRetry});
  final ChatMessage message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Align(alignment: Alignment.centerLeft, child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 760), child: Container(margin: const EdgeInsets.only(bottom: 18), padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: colors.surface, border: Border.all(color: colors.line), borderRadius: BorderRadius.circular(8)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [const Icon(Icons.help_outline, size: 18, color: _Brand.blue), const SizedBox(width: 8), Text('Avenqo Support', style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink))]), const SizedBox(height: 10),
      if (message.content.isNotEmpty) MarkdownBody(data: message.content, selectable: true),
      if (message.error != null) MessageError(message: message.error!, onRetry: onRetry),
      if (message.sources.isNotEmpty) MessageSources(sources: message.sources),
    ]))));
  }
}
