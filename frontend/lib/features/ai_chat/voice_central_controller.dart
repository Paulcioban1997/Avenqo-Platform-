import 'package:flutter/foundation.dart';

import 'package:avenqo/core/api_client.dart';

class VoiceSessionState {
  const VoiceSessionState({
    required this.status,
    this.sessionId,
    this.conversationId,
    this.locale,
    this.answer,
    this.error,
  });

  final String status;
  final String? sessionId;
  final String? conversationId;
  final String? locale;
  final String? answer;
  final String? error;
}

/// Voice Central contract for Flutter. Audio capture adapters can feed final
/// transcripts here without adding business routing or a second conversation.
class VoiceCentralController extends ChangeNotifier {
  VoiceCentralController(this._api);

  final ApiClient _api;
  VoiceSessionState state = const VoiceSessionState(status: 'idle');

  Future<void> start({required String conversationId, required String locale, required String requestId}) async {
    try {
      final response = await _api.post(
        '/ai/voice/sessions',
        body: {'conversation_id': conversationId, 'locale': locale, 'request_id': requestId},
      ) as Map<String, dynamic>;
      state = VoiceSessionState(
        status: 'listening',
        sessionId: response['id']?.toString(),
        conversationId: conversationId,
        locale: response['locale']?.toString() ?? locale,
      );
    } on ApiException catch (error) {
      state = VoiceSessionState(status: 'error', conversationId: conversationId, locale: locale, error: error.message);
    }
    notifyListeners();
  }

  Future<void> submitTranscript(String transcript, {required String requestId}) async {
    final sessionId = state.sessionId;
    if (sessionId == null || transcript.trim().isEmpty) return;
    state = VoiceSessionState(
      status: 'processing',
      sessionId: sessionId,
      conversationId: state.conversationId,
      locale: state.locale,
    );
    notifyListeners();
    try {
      final response = await _api.post(
        '/ai/voice/sessions/$sessionId/turn',
        body: {'transcript': transcript, 'request_id': requestId},
      ) as Map<String, dynamic>;
      state = VoiceSessionState(
        status: response['tts_status'] == 'external_configuration_required' ? 'text_fallback' : 'speaking',
        sessionId: sessionId,
        conversationId: response['conversation_id']?.toString() ?? state.conversationId,
        locale: state.locale,
        answer: response['answer']?.toString(),
      );
    } on ApiException catch (error) {
      state = VoiceSessionState(
        status: 'error',
        sessionId: sessionId,
        conversationId: state.conversationId,
        locale: state.locale,
        error: error.message,
      );
    }
    notifyListeners();
  }

  Future<void> end() async {
    final sessionId = state.sessionId;
    if (sessionId != null) {
      try {
        await _api.post('/ai/voice/sessions/$sessionId/end');
      } catch (_) {
        // Local state still terminates if the network is unavailable.
      }
    }
    state = const VoiceSessionState(status: 'idle');
    notifyListeners();
  }
}
