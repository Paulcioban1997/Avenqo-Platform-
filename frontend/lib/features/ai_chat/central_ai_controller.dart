import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/ai_chat_api.dart';
import 'package:avenqo/features/ai_chat/ai_chat_models.dart';
import 'package:flutter/widgets.dart';

class CentralAIController extends ChangeNotifier {
  CentralAIController(ApiClient api) : _chat = AiChatApi(api);

  final AiChatApi _chat;
  List<Conversation> conversations = const [];
  List<ChatMessage> messages = const [];
  Conversation? selected;
  bool loadingConversations = true;
  bool loadingMessages = false;
  bool generating = false;
  String? errorCode;
  int? remainingAiCredits;
  bool creditsExhausted = false;
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    await loadConversations();
  }

  Future<void> loadConversations() async {
    loadingConversations = true;
    errorCode = null;
    notifyListeners();
    try {
      conversations = await _chat.listConversations();
    } on ApiException {
      errorCode = 'load';
    } finally {
      loadingConversations = false;
      notifyListeners();
    }
  }

  Future<void> selectConversation(Conversation conversation) async {
    if (generating) return;
    selected = conversation;
    messages = const [];
    loadingMessages = true;
    errorCode = null;
    notifyListeners();
    try {
      final detail = await _chat.getConversation(conversation.id);
      if (selected?.id == conversation.id) messages = detail.messages;
    } on ApiException catch (error) {
      if (error.statusCode == 404) {
        conversations = conversations.where((item) => item.id != conversation.id).toList();
        selected = null;
      }
      errorCode = 'open';
    } finally {
      loadingMessages = false;
      notifyListeners();
    }
  }

  void newConversation() {
    if (generating) return;
    selected = null;
    messages = const [];
    errorCode = null;
    notifyListeners();
  }

  Future<void> send(
    String content, {
    required String Function(String status) statusMessage,
    String? pageContext,
    String? locale,
  }) async {
    content = content.trim();
    if (content.isEmpty || generating) return;
    try {
      var conversation = selected;
      if (conversation == null) {
        conversation = await _chat.createConversation(_titleFor(content));
        selected = conversation;
        conversations = [conversation, ...conversations];
      }
      final now = DateTime.now();
      generating = true;
      errorCode = null;
      creditsExhausted = false;
      messages = [
        ...messages,
        ChatMessage(id: 'local-user-${now.microsecondsSinceEpoch}', role: ChatRole.user, content: content, createdAt: now),
        ChatMessage(id: 'local-assistant-${now.microsecondsSinceEpoch}', role: ChatRole.assistant, content: '', createdAt: now),
      ];
      notifyListeners();
      final result = await _chat.sendCentralMessage(
        conversation.id,
        content,
        pageContext: pageContext,
        locale: locale,
      );
      final response = result.answer ?? statusMessage(result.status);
      final last = messages.last;
      messages = [...messages.take(messages.length - 1), last.copyWith(content: response)];
      remainingAiCredits = result.remainingAiCredits;
      creditsExhausted = result.status == 'credits_exhausted';
    } on ApiException catch (error) {
      errorCode = error.statusCode == 401 ? 'session' : 'request';
    } finally {
      generating = false;
      notifyListeners();
    }
  }

  Future<void> retryLastMessage({
    required String Function(String status) statusMessage,
    String? pageContext,
    String? locale,
  }) async {
    for (final message in messages.reversed) {
      if (message.role == ChatRole.user) {
        await send(message.content, statusMessage: statusMessage, pageContext: pageContext, locale: locale);
        return;
      }
    }
  }

  Future<void> deleteConversation(Conversation conversation) async {
    if (generating) return;
    try {
      await _chat.deleteConversation(conversation.id);
      conversations = conversations.where((item) => item.id != conversation.id).toList();
      if (selected?.id == conversation.id) {
        selected = null;
        messages = const [];
      }
    } on ApiException {
      errorCode = 'delete';
    }
    notifyListeners();
  }

  String _titleFor(String content) => content.length > 54 ? '${content.substring(0, 54)}...' : content;
}

class CentralAIControllerScope extends InheritedNotifier<CentralAIController> {
  const CentralAIControllerScope({
    super.key,
    required CentralAIController controller,
    required super.child,
  }) : super(notifier: controller);

  static CentralAIController? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<CentralAIControllerScope>()?.notifier;
}