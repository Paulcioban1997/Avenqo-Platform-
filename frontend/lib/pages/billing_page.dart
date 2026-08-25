import 'package:flutter/material.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:url_launcher/url_launcher.dart';

class BillingPage extends StatelessWidget {
  const BillingPage({super.key, required this.api});
  final ApiClient api;

  Future<void> _openPortal(BuildContext context) async {
    try {
      final response =
          await api.post('/billing/portal') as Map<String, dynamic>;
      await launchUrl(
        Uri.parse(response['url'] as String),
        mode: LaunchMode.externalApplication,
      );
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).company;
    return FutureBuilder<dynamic>(
      future: Future.wait([
        api.get('/billing/subscription'),
        api.get('/billing/invoices'),
      ]),
      builder: (context, snapshot) {
        final values = snapshot.data is List
            ? snapshot.data as List<dynamic>
            : null;
        final subscription = values?[0] as Map<String, dynamic>?;
        final invoices = values?[1] as List<dynamic>? ?? const [];
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    t.billingTitle,
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                ),
                FilledButton.icon(
                  onPressed: () => _openPortal(context),
                  icon: const Icon(Icons.open_in_new),
                  label: Text(t.billingPortalButton),
                ),
              ],
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const Center(child: CircularProgressIndicator())
            else if (snapshot.hasError)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text(t.billingUnavailable),
                ),
              )
            else ...[
              Card(
                child: ListTile(
                  title: Text(
                    '${t.billingPlanPrefix}${subscription?['plan_code'] ?? 'demo'}',
                  ),
                  subtitle: Text(
                    '${t.billingStatusPrefix}${subscription?['status'] ?? 'inactive'}',
                  ),
                  trailing: subscription?['cancel_at_period_end'] == true
                      ? Chip(label: Text(t.billingCancelScheduled))
                      : null,
                ),
              ),
              const SizedBox(height: 20),
              Text(t.billingInvoicesTitle, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 10),
              for (final invoice in invoices)
                ListTile(
                  leading: const Icon(Icons.receipt_outlined),
                  title: Text(invoice['number']?.toString() ?? t.billingInvoiceFallback),
                  subtitle: Text(invoice['status'].toString()),
                  trailing: Text(
                    '${(invoice['amount_paid'] as num) / 100} ${invoice['currency'].toString().toUpperCase()}',
                  ),
                ),
            ],
          ],
        );
      },
    );
  }
}
