import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/ai_chat/ai_chat_models.dart';

class AiChatApi {
  const AiChatApi(this._client);

  final ApiClient _client;

  Future<List<Conversation>> listConversations() async {
    final response = await _client.get('/ai/chat/conversations') as List<dynamic>;
    return response
        .map((item) => Conversation.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<Conversation> createConversation(String title) async {
    final response = await _client.post(
      '/ai/chat/conversations',
      body: {'title': title},
    ) as Map<String, dynamic>;
    return Conversation.fromJson(response);
  }

  Future<ConversationDetail> getConversation(String id) async {
    final response = await _client.get('/ai/chat/conversations/$id') as Map<String, dynamic>;
    return ConversationDetail.fromJson(response);
  }

  Future<void> deleteConversation(String id) async {
    await _client.delete('/ai/chat/conversations/$id');
  }

  Future<CentralAIResponse> sendCentralMessage(
    String conversationId,
    String content,
  ) async {
    final response = await _client.post(
      '/ai/central/conversations/$conversationId/messages',
      body: {'content': content},
    ) as Map<String, dynamic>;
    return CentralAIResponse.fromJson(response);
  }

  Stream<ChatStreamEvent> streamMessage(String conversationId, String content) =>
      _client.postSseEvents(
        '/ai/chat/conversations/$conversationId/messages/stream',
        body: {'content': content},
      ).map(ChatStreamEvent.fromJson);
}