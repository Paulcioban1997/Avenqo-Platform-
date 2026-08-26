import 'package:flutter/material.dart';
import 'package:avenqo/core/api_client.dart';

class PricingPage extends StatelessWidget {
  const PricingPage({super.key, required this.api, this.embedded = false});

  final ApiClient api;
  final bool embedded;

  @override
  Widget build(BuildContext context) {
    final content = FutureBuilder<dynamic>(
      future: api.get('/billing/plans', authenticated: false),
      builder: (context, snapshot) {
        final plans = snapshot.data is List
            ? snapshot.data as List<dynamic>
            : const <dynamic>[];
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return const Center(
            child: Text('Tarifs temporairement indisponibles.'),
          );
        }
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Text(
              'Plans Avenqo',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 20),
            Wrap(
              spacing: 16,
              runSpacing: 16,
              children: [
                for (final item in plans)
                  SizedBox(
                    width: 260,
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(22),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              item['name'].toString(),
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              item['monthly_price_usd'] == null
                                  ? 'Contact sales'
                                  : '\$${item['monthly_price_usd']}/mo',
                              style: Theme.of(context).textTheme.titleMedium,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              item['requires_sales_contact'] == true
                                  ? 'Custom onboarding'
                                  : 'Managed via Stripe',
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ],
        );
      },
    );
    return embedded
        ? content
        : Scaffold(
            appBar: AppBar(title: const Text('AVENQO')),
            body: content,
          );
  }
}
