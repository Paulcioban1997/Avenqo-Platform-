import 'package:flutter/material.dart';
import 'package:avenqo/core/api_client.dart';

class AssistantPage extends StatefulWidget {
  const AssistantPage({super.key, required this.api});
  final ApiClient api;

  @override
  State<AssistantPage> createState() => _AssistantPageState();
}

class _AssistantPageState extends State<AssistantPage> {
  final _controller = TextEditingController();
  final _messages = <({bool fromUser, String text})>[];
  bool _sending = false;

  static const _suggestions = [
    'Pourquoi les ventes baissent ?',
    'Quels clients risquent de partir ?',
    'Compare ce mois avec le précédent.',
    'Quelles actions me recommandes-tu ?',
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send([String? suggestion]) async {
    final question = (suggestion ?? _controller.text).trim();
    if (question.isEmpty || _sending) return;
    setState(() {
      _messages.add((fromUser: true, text: question));
      _controller.clear();
      _sending = true;
    });
    try {
      final response = await widget.api.post('/retail/assistant', body: {'question': question}) as Map<String, dynamic>;
      if (!mounted) return;
      setState(() => _messages.add((fromUser: false, text: response['answer']?.toString() ?? 'Je n’ai pas pu préparer cette réponse.')));
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _messages.add((fromUser: false, text: error.message)));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SizedBox(
        height: constraints.maxHeight,
        child: Column(
          children: [
            Expanded(
              child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 28, 20, 16),
            children: [
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 820),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text('Assistant Avenqo', style: Theme.of(context).textTheme.headlineMedium),
                      const SizedBox(height: 6),
                      const Text('Interrogez votre activité en langage naturel.'),
                      const SizedBox(height: 28),
                      if (_messages.isEmpty) ...[
                        Container(
                          padding: const EdgeInsets.all(22),
                          decoration: BoxDecoration(color: const Color(0xFFEAF6F5), borderRadius: BorderRadius.circular(8)),
                          child: const Text('Bonjour. Je peux analyser vos ventes, vos clients et vos produits, puis vous proposer des actions concrètes.'),
                        ),
                        const SizedBox(height: 18),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [for (final suggestion in _suggestions) ActionChip(avatar: const Icon(Icons.arrow_outward, size: 16), label: Text(suggestion), onPressed: () => _send(suggestion))],
                        ),
                      ],
                      for (final message in _messages)
                        Align(
                          alignment: message.fromUser ? Alignment.centerRight : Alignment.centerLeft,
                          child: Container(
                            constraints: const BoxConstraints(maxWidth: 640),
                            margin: const EdgeInsets.only(top: 12),
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
                            decoration: BoxDecoration(
                              color: message.fromUser ? const Color(0xFF16324F) : Colors.white,
                              border: message.fromUser ? null : Border.all(color: const Color(0xFFDDE5E8)),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(message.text, style: TextStyle(color: message.fromUser ? Colors.white : null)),
                          ),
                        ),
                      if (_sending) const Padding(padding: EdgeInsets.all(16), child: Align(alignment: Alignment.centerLeft, child: SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2)))),
                    ],
                  ),
                ),
              ),
            ],
              ),
            ),
            Container(
          color: Colors.white,
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 820),
              child: TextField(
                controller: _controller,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
                decoration: InputDecoration(hintText: 'Posez une question sur votre entreprise…', suffixIcon: IconButton(tooltip: 'Envoyer', onPressed: _sending ? null : _send, icon: const Icon(Icons.arrow_upward))),
              ),
            ),
          ),
            ),
          ],
        ),
      ),
    );
  }
}