class Conversation {
  const Conversation({
    required this.id,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String title;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory Conversation.fromJson(Map<String, dynamic> json) => Conversation(
    id: json['id'] as String,
    title: json['title'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
    updatedAt: DateTime.parse(json['updated_at'] as String),
  );
}

class ChatSource {
  const ChatSource({
    required this.type,
    required this.identifier,
    required this.name,
    required this.metadata,
  });

  final String type;
  final String identifier;
  final String name;
  final Map<String, dynamic> metadata;

  factory ChatSource.fromJson(Map<String, dynamic> json) => ChatSource(
    type: json['type'] as String,
    identifier: json['identifier'] as String,
    name: json['name'] as String,
    metadata: (json['metadata'] as Map<String, dynamic>?) ?? const {},
  );
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    required this.createdAt,
    this.sources = const [],
    this.error,
  });

  final String id;
  final ChatRole role;
  final String content;
  final DateTime createdAt;
  final List<ChatSource> sources;
  final String? error;

  ChatMessage copyWith({
    String? content,
    String? error,
    List<ChatSource>? sources,
  }) => ChatMessage(
    id: id,
    role: role,
    content: content ?? this.content,
    createdAt: createdAt,
    sources: sources ?? this.sources,
    error: error ?? this.error,
  );

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
    id: json['id'] as String,
    role: ChatRole.fromApi(json['role'] as String),
    content: json['content'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
  );
}

enum ChatRole {
  user,
  assistant;

  factory ChatRole.fromApi(String value) =>
      value == 'user' ? ChatRole.user : ChatRole.assistant;
}

class ConversationDetail {
  const ConversationDetail({
    required this.conversation,
    required this.messages,
  });

  final Conversation conversation;
  final List<ChatMessage> messages;

  factory ConversationDetail.fromJson(Map<String, dynamic> json) =>
      ConversationDetail(
        conversation: Conversation.fromJson(json),
        messages: (json['messages'] as List<dynamic>)
            .map((item) => ChatMessage.fromJson(item as Map<String, dynamic>))
            .toList(),
      );
}

class ChatStreamEvent {
  const ChatStreamEvent({this.chunk, this.sources = const [], this.status});

  final String? chunk;
  final List<ChatSource> sources;
  final String? status;

  factory ChatStreamEvent.fromJson(Map<String, dynamic> json) =>
      ChatStreamEvent(
        chunk: json['chunk']?.toString(),
        sources: (json['sources'] as List<dynamic>? ?? const [])
            .map((item) => ChatSource.fromJson(item as Map<String, dynamic>))
            .toList(),
        status: json['message']?.toString(),
      );
}

class CentralAIResponse {
  const CentralAIResponse({
    required this.status,
    required this.agentAvailability,
    required this.conversationId,
    this.selectedAgent,
    this.answer,
    this.remainingAiCredits,
  });

  final String? selectedAgent;
  final String status;
  final String? answer;
  final int? remainingAiCredits;
  final String agentAvailability;
  final String conversationId;

  factory CentralAIResponse.fromJson(Map<String, dynamic> json) =>
      CentralAIResponse(
        selectedAgent: json['selected_agent'] as String?,
        status: json['status'] as String,
        answer: json['answer'] as String?,
        remainingAiCredits: json['remaining_ai_credits'] as int?,
        agentAvailability: json['agent_availability'] as String,
        conversationId: json['conversation_id'] as String,
      );
}
