import 'package:flutter/material.dart';
import 'package:avenqo/app/destinations.dart';

class DynamicPage extends StatelessWidget {
  const DynamicPage({super.key, required this.destination});

  final AppDestination destination;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(
          destination.label,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 6),
        Text(destination.description),
        const SizedBox(height: 24),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(destination.icon, size: 32),
                const SizedBox(width: 16),
                const Expanded(
                  child: Text(
                    'Cette route est prête dans l’architecture Flutter. '
                    'Ses données seront activées dans la phase métier correspondante.',
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
