import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/ai_chat_models.dart';

/// Avenqo Support AI (Phase 32) — mirrors [AiChatApi] but targets the
/// separate `/support/chat` endpoints (own conversations/messages, never
/// mixed with the Business Assistant's `/ai/chat`). Reuses the same
/// response shapes (`Conversation`, `ChatMessage`, `ChatSource`,
/// `ChatStreamEvent`) since the wire format is intentionally identical.
class AiSupportApi {
  const AiSupportApi(this._client);

  final ApiClient _client;

  Future<List<Conversation>> listConversations() async {
    final response = await _client.get('/support/chat/conversations') as List<dynamic>;
    return response
        .map((item) => Conversation.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<Conversation> createConversation(String title) async {
    final response = await _client.post(
      '/support/chat/conversations',
      body: {'title': title},
    ) as Map<String, dynamic>;
    return Conversation.fromJson(response);
  }

  Future<ConversationDetail> getConversation(String id) async {
    final response = await _client.get('/support/chat/conversations/$id') as Map<String, dynamic>;
    return ConversationDetail.fromJson(response);
  }

  Future<void> deleteConversation(String id) async {
    await _client.delete('/support/chat/conversations/$id');
  }

  Stream<ChatStreamEvent> streamMessage(String conversationId, String content) =>
      _client.postSseEvents(
        '/support/chat/conversations/$conversationId/messages/stream',
        body: {'content': content},
      ).map(ChatStreamEvent.fromJson);
}
