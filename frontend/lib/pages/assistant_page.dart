import 'dart:async';

import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/ai_chat_api.dart';
import 'package:avenqo/features/ai_chat/ai_chat_models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter/services.dart';

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
    'How are my sales performing?',
    'Which customers need attention?',
    'What changed this month?',
    'Summarize my business performance.',
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
        _statusMessage = null;
        _messages = [
          ..._messages,
          ChatMessage(id: 'local-user-${now.microsecondsSinceEpoch}', role: ChatRole.user, content: content, createdAt: now),
          ChatMessage(id: 'local-assistant-${now.microsecondsSinceEpoch}', role: ChatRole.assistant, content: '', createdAt: now),
        ];
      });
      _scrollToBottom(force: true);
      _stream = _chat.streamMessage(conversation.id, content).listen(
        _handleStreamEvent,
        onError: (_) => _completeStreamWithError(),
        onDone: _completeStream,
        cancelOnError: true,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.statusCode == 401
          ? 'Your session has expired. Please sign in again.'
          : "Avenqo couldn't start this conversation. Please try again.");
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
      final last = _messages.last.copyWith(error: "Avenqo couldn't complete this request. Please try again.");
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
    return Scaffold(
      key: _scaffoldKey,
      endDrawer: compact ? Drawer(child: SafeArea(child: sidebar)) : null,
      body: Row(children: [
        if (!compact) SizedBox(width: 276, child: sidebar),
        if (!compact) const VerticalDivider(width: 1),
        Expanded(child: Column(children: [
          ChatHeader(title: _selected?.title ?? 'Avenqo AI', compact: compact, onOpenConversations: () => _scaffoldKey.currentState?.openEndDrawer()),
          if (_error != null) ChatErrorState(message: _error!, onRetry: _loadConversations),
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
            Align(alignment: Alignment.centerRight, child: Padding(padding: const EdgeInsets.only(right: 24), child: FilledButton.tonalIcon(onPressed: () => _scrollToBottom(force: true), icon: const Icon(Icons.arrow_downward), label: const Text('Newest')))),
          if (_statusMessage != null)
            Padding(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 4), child: Align(alignment: Alignment.centerLeft, child: Text(_statusMessage!, style: Theme.of(context).textTheme.bodySmall?.copyWith(fontStyle: FontStyle.italic)))),
          ChatComposer(controller: _composer, generating: _generating, onSend: _send, onStop: _stopGenerating),
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
  Widget build(BuildContext context) => ColoredBox(color: Colors.white, child: Column(children: [
    Padding(padding: const EdgeInsets.all(16), child: SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: onNewConversation, icon: const Icon(Icons.add), label: const Text('New conversation')))),
    Expanded(child: loading ? const Center(child: CircularProgressIndicator()) : conversations.isEmpty ? const Padding(padding: EdgeInsets.all(24), child: Text('Your conversations will appear here.')) : ListView.builder(itemCount: conversations.length, itemBuilder: (context, index) {
      final conversation = conversations[index];
      return ListTile(selected: conversation.id == selectedId, title: Text(conversation.title, maxLines: 2, overflow: TextOverflow.ellipsis), onTap: () => onSelect(conversation), trailing: IconButton(tooltip: 'Delete conversation', icon: const Icon(Icons.delete_outline), onPressed: () => onDelete(conversation)));
    })),
  ]));
}

class ChatHeader extends StatelessWidget {
  const ChatHeader({super.key, required this.title, required this.compact, required this.onOpenConversations});
  final String title;
  final bool compact;
  final VoidCallback onOpenConversations;
  @override
  Widget build(BuildContext context) => Container(height: 72, padding: const EdgeInsets.symmetric(horizontal: 20), decoration: const BoxDecoration(color: Colors.white, border: Border(bottom: BorderSide(color: Color(0xFFDDE5E8)))), child: Row(children: [
    if (compact) IconButton(tooltip: 'Conversations', onPressed: onOpenConversations, icon: const Icon(Icons.forum_outlined)),
    Expanded(child: Text(title, style: Theme.of(context).textTheme.titleLarge, maxLines: 1, overflow: TextOverflow.ellipsis)),
    const Icon(Icons.auto_awesome_outlined, color: Color(0xFF007C83)),
  ]));
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
  Widget build(BuildContext context) => Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 680), child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [
    Container(width: 52, height: 52, decoration: BoxDecoration(color: const Color(0xFFEAF6F5), borderRadius: BorderRadius.circular(8)), child: const Icon(Icons.auto_awesome, color: Color(0xFF007C83))),
    const SizedBox(height: 18), Text('Ask Avenqo about your business', style: Theme.of(context).textTheme.headlineMedium, textAlign: TextAlign.center),
    const SizedBox(height: 10), const Text('Ask a business question and Avenqo will use the information available to your company.', textAlign: TextAlign.center),
    const SizedBox(height: 22), Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [for (final item in _AssistantPageState.suggestions) ActionChip(avatar: const Icon(Icons.arrow_outward, size: 16), label: Text(item), onPressed: () => onSuggestion(item))]),
    const SizedBox(height: 20), TextButton.icon(onPressed: () => context.go('/connections'), icon: const Icon(Icons.sync_alt), label: const Text('Connect your business data')),
  ]))));
}

class UserMessage extends StatelessWidget {
  const UserMessage({super.key, required this.message});
  final ChatMessage message;
  @override
  Widget build(BuildContext context) => Align(alignment: Alignment.centerRight, child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 680), child: Container(margin: const EdgeInsets.only(bottom: 18), padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: const Color(0xFF16324F), borderRadius: BorderRadius.circular(8)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Text('You', style: TextStyle(color: Colors.white70, fontWeight: FontWeight.w700)), const SizedBox(height: 6), SelectableText(message.content, style: const TextStyle(color: Colors.white))]))));
}

class AssistantMessage extends StatelessWidget {
  const AssistantMessage({super.key, required this.message, required this.onRetry});
  final ChatMessage message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Align(alignment: Alignment.centerLeft, child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 760), child: Container(margin: const EdgeInsets.only(bottom: 18), padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: Colors.white, border: Border.all(color: const Color(0xFFDDE5E8)), borderRadius: BorderRadius.circular(8)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    const Row(children: [Icon(Icons.auto_awesome_outlined, size: 18, color: Color(0xFF007C83)), SizedBox(width: 8), Text('Avenqo AI', style: TextStyle(fontWeight: FontWeight.w700))]), const SizedBox(height: 10),
    if (message.content.isNotEmpty) MarkdownBody(data: message.content, selectable: true),
    if (message.error != null) MessageError(message: message.error!, onRetry: onRetry),
    if (message.sources.isNotEmpty) MessageSources(sources: message.sources),
  ]))));
}

class StreamingMessage extends StatelessWidget {
  const StreamingMessage({super.key});
  @override
  Widget build(BuildContext context) => const Padding(padding: EdgeInsets.only(bottom: 16), child: Row(children: [SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(width: 10), Text('Avenqo is thinking...')]));
}

class MessageSources extends StatelessWidget {
  const MessageSources({super.key, required this.sources});
  final List<ChatSource> sources;
  @override
  Widget build(BuildContext context) => ExpansionTile(tilePadding: EdgeInsets.zero, title: Text('Sources · ${sources.length}', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)), children: [for (final source in sources) ListTile(dense: true, leading: const Icon(Icons.description_outlined, size: 18), title: Text(source.name))]);
}

class MessageError extends StatelessWidget {
  const MessageError({super.key, required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Container(margin: const EdgeInsets.only(top: 8), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: const Color(0xFFFFF4F2), borderRadius: BorderRadius.circular(6)), child: Row(children: [const Icon(Icons.error_outline, color: Color(0xFFB42318)), const SizedBox(width: 8), Expanded(child: Text(message)), TextButton(onPressed: onRetry, child: const Text('Retry'))]));
}

class ChatErrorState extends StatelessWidget {
  const ChatErrorState({super.key, required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => MaterialBanner(content: Text(message), actions: [TextButton(onPressed: onRetry, child: const Text('Retry'))]);
}

class ChatComposer extends StatelessWidget {
  const ChatComposer({super.key, required this.controller, required this.generating, required this.onSend, required this.onStop});
  final TextEditingController controller;
  final bool generating;
  final ValueChanged<String?> onSend;
  final Future<void> Function() onStop;
  @override
  Widget build(BuildContext context) => Container(color: Colors.white, padding: const EdgeInsets.fromLTRB(20, 12, 20, 20), child: SafeArea(top: false, child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
    Expanded(child: Focus(onKeyEvent: (node, event) {
      if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.enter && !HardwareKeyboard.instance.isShiftPressed) {
        onSend(null);
        return KeyEventResult.handled;
      }
      return KeyEventResult.ignored;
    }, child: TextField(controller: controller, minLines: 1, maxLines: 5, textInputAction: TextInputAction.newline, decoration: const InputDecoration(hintText: 'Ask Avenqo anything about your business...')))), const SizedBox(width: 10),
    generating ? Tooltip(message: 'Stop generating', child: IconButton.filledTonal(onPressed: onStop, icon: const Icon(Icons.stop))) : Tooltip(message: 'Send message', child: IconButton.filled(onPressed: () => onSend(null), icon: const Icon(Icons.arrow_upward))),
  ])));
}