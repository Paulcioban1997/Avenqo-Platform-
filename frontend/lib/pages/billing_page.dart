import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/file_picker/app_file_picker.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:url_launcher/url_launcher.dart';

typedef BillingDataLoader = Future<BillingData> Function(ApiClient api);
typedef ExternalUrlLauncher = Future<bool> Function(Uri uri);

Future<bool> _launchExternal(Uri uri) =>
    launchUrl(uri, mode: LaunchMode.externalApplication);

class BillingData {
  const BillingData({
    required this.subscription,
    required this.invoices,
    required this.balance,
    required this.packs,
    this.invoiceTotal,
  });

  final Map<String, dynamic> subscription;
  final List<dynamic> invoices;
  final Map<String, dynamic> balance;
  final List<Map<String, dynamic>> packs;
  final int? invoiceTotal;
}

Future<BillingData> _loadBillingData(ApiClient api) async {
  final values = await Future.wait([
    api.get('/billing/subscription'),
    api.get('/billing/invoices/history?offset=0&limit=20'),
    api.get('/billing/ai-credits'),
    api.get('/billing/credit-packs'),
  ]);
  return BillingData(
    subscription: values[0] as Map<String, dynamic>,
    invoices: (values[1] as Map<String, dynamic>)['items'] as List<dynamic>,
    balance: values[2] as Map<String, dynamic>,
    packs: (values[3] as List<dynamic>).cast<Map<String, dynamic>>(),
    invoiceTotal: (values[1] as Map<String, dynamic>)['total'] as int,
  );
}

class BillingPage extends StatefulWidget {
  const BillingPage({
    super.key,
    required this.api,
    BillingDataLoader? loader,
    ExternalUrlLauncher? launcher,
  })  : loader = loader ?? _loadBillingData,
        launcher = launcher ?? _launchExternal;

  final ApiClient api;
  final BillingDataLoader loader;
  final ExternalUrlLauncher launcher;

  @override
  State<BillingPage> createState() => _BillingPageState();
}

class _BillingPageState extends State<BillingPage> {
  late Future<BillingData> _future = widget.loader(widget.api);

  Future<void> _openPortal(BuildContext context) async {
    try {
      final response =
          await widget.api.post('/billing/portal') as Map<String, dynamic>;
      await widget.launcher(Uri.parse(response['url'] as String));
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> _startCheckout(BuildContext context, String planCode) async {
    try {
      final response = await widget.api.post(
        '/billing/checkout',
        body: {'plan_code': planCode},
      ) as Map<String, dynamic>;
      await widget.launcher(Uri.parse(response['url'] as String));
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> _buyCredits(BuildContext context, String packCode) async {
    try {
      final response = await widget.api.post(
        '/billing/credit-packs/checkout',
        body: {'pack_code': packCode},
      ) as Map<String, dynamic>;
      await widget.launcher(Uri.parse(response['url'] as String));
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.message)),
        );
      }
    }
  }

  Future<void> _cancelSubscription(BuildContext context, Phase4eStrings strings) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.billingValue('cancelTitle')),
        content: Text(strings.billingValue('cancelMessage')),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(strings.billingValue('keepSubscription')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(strings.billingValue('cancelConfirm')),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    try {
      await widget.api.post('/billing/cancel');
      if (mounted) _retry();
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.message)),
        );
      }
    }
  }

  void _retry() => setState(() {
        _future = widget.loader(widget.api);
      });

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final creditsT = AvenqoLocaleScope.translationsOf(context).phase4e;
    return FutureBuilder<BillingData>(
      future: _future,
      builder: (context, snapshot) {
        final data = snapshot.data;
        final subscription = data?.subscription;
        final invoices = data?.invoices ?? const [];
        final planCode = subscription?['plan_code']?.toString() ?? 'demo';
        final billingStatus =
            subscription?['status']?.toString().toLowerCase() ?? 'inactive';
        final localeCode = AvenqoLocaleScope.of(context).code;
        final currentPeriodEnd = DateTime.tryParse(
          subscription?['current_period_end']?.toString() ?? '',
        );
        final needsCheckout = const {
          'inactive',
          'canceled',
          'incomplete',
          'incomplete_expired',
          'unpaid',
        }.contains(billingStatus);
        // Politique deny-by-default côté UI : seules les offres explicitement
        // self-service peuvent déclencher Checkout. Enterprise et toute future
        // offre commerciale restent donc protégées même si leur code change.
        final isSelfServicePlan = const {
          'demo',
          'professional',
        }.contains(planCode);

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
                  child: Row(
                    children: [
                      Expanded(child: Text(t.billingUnavailable)),
                      IconButton(
                        onPressed: _retry,
                        icon: const Icon(Icons.refresh),
                        tooltip: t.connectionsRetry,
                      ),
                    ],
                  ),
                ),
              )
            else ...[
              Card(
                child: ListTile(
                  title: Text(
                    '${t.billingPlanPrefix}${creditsT.planName(planCode)}',
                  ),
                  subtitle: Text(
                    '${t.billingStatusPrefix}${creditsT.subscriptionStatus(billingStatus)}',
                  ),
                  trailing: subscription?['cancel_at_period_end'] == true
                      ? Chip(label: Text(t.billingCancelScheduled))
                      : null,
                ),
              ),
              if (needsCheckout && isSelfServicePlan) ...[
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: FilledButton.icon(
                    onPressed: () => _startCheckout(context, planCode),
                    icon: const Icon(Icons.credit_card),
                    label: Text(t.settingsManageSubscription),
                  ),
                ),
              ],
              if (const {'active', 'trialing'}.contains(billingStatus)) ...[
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: () => _cancelSubscription(context, creditsT),
                  icon: const Icon(Icons.event_busy_outlined),
                  label: Text(creditsT.billingValue('cancelSubscription')),
                ),
              ],
              if (billingStatus == 'canceling_at_period_end' && currentPeriodEnd != null) ...[
                const SizedBox(height: 8),
                Text(
                  creditsT.billingValue('effectiveEnd').replaceFirst(
                    '{date}',
                    DateFormat.yMMMd(localeCode).format(currentPeriodEnd.toLocal()),
                  ),
                ),
              ],
              if (const {'active', 'trialing'}.contains(billingStatus) &&
                  subscription?['cancel_at_period_end'] != true &&
                  currentPeriodEnd != null) ...[
                const SizedBox(height: 8),
                Text(
                  creditsT.billingValue('nextRenewal').replaceFirst(
                    '{date}',
                    DateFormat.yMMMd(localeCode).format(currentPeriodEnd.toLocal()),
                  ),
                ),
              ],
              const SizedBox(height: 20),
              _CreditWallet(
                balance: data!.balance,
                strings: creditsT,
              ),
              const SizedBox(height: 24),
              _CreditPacks(
                packs: data.packs,
                enabled: const {'active', 'trialing'}.contains(billingStatus),
                strings: creditsT,
                onPurchase: (code) => _buyCredits(context, code),
              ),
              const SizedBox(height: 28),
              Text(
                t.billingInvoicesTitle,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 10),
              _InvoiceHistory(
                api: widget.api,
                launcher: widget.launcher,
                initialInvoices: invoices.cast<Map<String, dynamic>>(),
                initialTotal: data.invoiceTotal ?? invoices.length,
                localeCode: localeCode,
                strings: creditsT,
                invoiceFallback: t.billingInvoiceFallback,
              ),
            ],
          ],
        );
      },
    );
  }
}

class _InvoiceHistory extends StatefulWidget {
  const _InvoiceHistory({required this.api, required this.launcher, required this.initialInvoices, required this.initialTotal, required this.localeCode, required this.strings, required this.invoiceFallback});
  final ApiClient api;
  final ExternalUrlLauncher launcher;
  final List<Map<String, dynamic>> initialInvoices;
  final int initialTotal;
  final String localeCode;
  final Phase4eStrings strings;
  final String invoiceFallback;

  @override
  State<_InvoiceHistory> createState() => _InvoiceHistoryState();
}

class _InvoiceHistoryState extends State<_InvoiceHistory> {
  static const _pageSize = 20;
  late List<Map<String, dynamic>> _invoices = widget.initialInvoices;
  late int _total = widget.initialTotal;
  int _offset = 0;
  bool _loading = false;

  Future<void> _loadPage(int offset) async {
    setState(() => _loading = true);
    try {
      final response = await widget.api.get('/billing/invoices/history?offset=$offset&limit=$_pageSize') as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _offset = offset;
        _total = response['total'] as int;
        _invoices = (response['items'] as List<dynamic>).cast<Map<String, dynamic>>();
      });
    } on ApiException catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _download(Map<String, dynamic> invoice, String format) async {
    try {
      final file = await widget.api.download('/billing/invoices/${invoice['id']}/export/$format');
      await saveExportFile(file.fileName, file.bytes);
    } on ApiException catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_invoices.isEmpty) return Text(widget.strings.billingValue('noInvoices'));
    return Column(children: [
      for (final invoice in _invoices) _invoiceRow(invoice),
      if (_total > _pageSize) Row(mainAxisAlignment: MainAxisAlignment.end, children: [
        IconButton(tooltip: widget.strings.billingValue('previous'), onPressed: _loading || _offset == 0 ? null : () => _loadPage((_offset - _pageSize).clamp(0, _total)), icon: const Icon(Icons.chevron_left)),
        Text('${(_offset ~/ _pageSize) + 1} / ${(_total / _pageSize).ceil()}'),
        IconButton(tooltip: widget.strings.billingValue('next'), onPressed: _loading || _offset + _pageSize >= _total ? null : () => _loadPage(_offset + _pageSize), icon: const Icon(Icons.chevron_right)),
      ]),
    ]);
  }

  Widget _invoiceRow(Map<String, dynamic> invoice) {
    final periodStart = DateTime.tryParse(invoice['period_start']?.toString() ?? '');
    final periodEnd = DateTime.tryParse(invoice['period_end']?.toString() ?? '');
    final issuedAt = DateTime.tryParse(invoice['issued_at']?.toString() ?? '');
    final status = widget.strings.invoiceStatus(invoice['status'].toString());
    final currency = invoice['currency'].toString().toUpperCase();
    final period = periodStart != null && periodEnd != null
        ? widget.strings.billingValue('invoicePeriod').replaceFirst('{start}', DateFormat.yMMMd(widget.localeCode).format(periodStart.toLocal())).replaceFirst('{end}', DateFormat.yMMMd(widget.localeCode).format(periodEnd.toLocal()))
        : null;
    final total = NumberFormat.currency(locale: widget.localeCode, symbol: '', decimalDigits: 2).format((invoice['total'] as num) / 100).trim();
    return ListTile(
      leading: const Icon(Icons.receipt_outlined),
      title: Text(invoice['number']?.toString() ?? widget.invoiceFallback),
      subtitle: Text([if (issuedAt != null) DateFormat.yMMMd(widget.localeCode).format(issuedAt.toLocal()), widget.strings.planName(invoice['plan_code']?.toString() ?? ''), status, ?period].join(' · ')),
      trailing: Wrap(spacing: 2, crossAxisAlignment: WrapCrossAlignment.center, children: [
        Text('$total $currency'),
        if (invoice['hosted_invoice_url'] != null) IconButton(tooltip: widget.strings.billingValue('viewInvoice'), onPressed: () => widget.launcher(Uri.parse(invoice['hosted_invoice_url'].toString())), icon: const Icon(Icons.open_in_new)),
        if (invoice['invoice_pdf'] != null) IconButton(tooltip: widget.strings.billingValue('downloadPdf'), onPressed: () => widget.launcher(Uri.parse(invoice['invoice_pdf'].toString())), icon: const Icon(Icons.picture_as_pdf_outlined)),
        IconButton(tooltip: widget.strings.billingValue('downloadCsv'), onPressed: () => _download(invoice, 'csv'), icon: const Icon(Icons.table_view_outlined)),
        IconButton(tooltip: widget.strings.billingValue('downloadXlsx'), onPressed: () => _download(invoice, 'xlsx'), icon: const Icon(Icons.grid_on_outlined)),
      ]),
    );
  }
}

String _formatCredits(Object? value) =>
    value == null ? '—' : NumberFormat.decimalPattern().format(value);

class _CreditWallet extends StatelessWidget {
  const _CreditWallet({required this.balance, required this.strings});

  final Map<String, dynamic> balance;
  final Phase4eStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final included = balance['monthly_included'] as int?;
    final used = balance['monthly_used'] as int? ?? 0;
    final progress = included == null || included <= 0
        ? null
        : (used / included).clamp(0.0, 1.0);
    final allowance = included == null
        ? strings.customAllowance
        : _formatCredits(included);

    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LayoutBuilder(
            builder: (context, constraints) {
              final title = Row(
                children: [
                  const Icon(Icons.auto_awesome, color: Color(0xFF087CF0)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(strings.creditsTitle, style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: colors.ink)),
                        const SizedBox(height: 3),
                        Text(strings.creditsSubtitle, style: TextStyle(color: colors.muted)),
                      ],
                    ),
                  ),
                ],
              );
              final period = Text(
                '${strings.billingPeriod}: ${balance['billing_period'] ?? '—'}',
                style: TextStyle(color: colors.muted, fontSize: 12),
              );
              if (constraints.maxWidth < 520) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [title, const SizedBox(height: 10), period],
                );
              }
              return Row(children: [Expanded(child: title), const SizedBox(width: 16), period]);
            },
          ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _CreditMetric(label: strings.monthlyAllowance, value: allowance),
              _CreditMetric(label: strings.monthlyRemaining, value: included == null ? strings.customAllowance : _formatCredits(balance['monthly_remaining'])),
              _CreditMetric(label: strings.purchasedRemaining, value: _formatCredits(balance['purchased_remaining'])),
              _CreditMetric(label: strings.totalRemaining, value: included == null ? strings.customAllowance : _formatCredits(balance['total_remaining']), emphasized: true),
            ],
          ),
          if (progress != null) ...[
            const SizedBox(height: 20),
            LinearProgressIndicator(
              value: progress,
              minHeight: 8,
              borderRadius: BorderRadius.circular(4),
            ),
            const SizedBox(height: 8),
            Text(
              strings.monthlyProgress
                  .replaceFirst('{used}', _formatCredits(used))
                  .replaceFirst('{included}', _formatCredits(included)),
              style: TextStyle(color: colors.muted, fontSize: 12),
            ),
          ],
          const SizedBox(height: 10),
          Text(strings.resetExplanation, style: TextStyle(color: colors.muted, fontSize: 12)),
        ],
      ),
    );
  }
}

class _CreditMetric extends StatelessWidget {
  const _CreditMetric({required this.label, required this.value, this.emphasized = false});
  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return SizedBox(
      width: 190,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: emphasized ? const Color(0xFF087CF0).withValues(alpha: 0.08) : colors.canvas,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: TextStyle(color: colors.muted, fontSize: 12)),
              const SizedBox(height: 6),
              Text(value, maxLines: 2, style: TextStyle(color: colors.ink, fontSize: 18, fontWeight: FontWeight.w800)),
            ],
          ),
        ),
      ),
    );
  }
}

class _CreditPacks extends StatelessWidget {
  const _CreditPacks({required this.packs, required this.enabled, required this.strings, required this.onPurchase});
  final List<Map<String, dynamic>> packs;
  final bool enabled;
  final Phase4eStrings strings;
  final ValueChanged<String> onPurchase;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(strings.packsTitle, style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: colors.ink)),
        const SizedBox(height: 4),
        Text(strings.packsSubtitle, style: TextStyle(color: colors.muted)),
        if (!enabled) ...[
          const SizedBox(height: 10),
          Text(strings.purchaseRequiresActive, style: const TextStyle(color: Color(0xFFB6790A), fontWeight: FontWeight.w600)),
        ],
        const SizedBox(height: 14),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final pack in packs)
              SizedBox(
                width: 220,
                child: Card(
                  margin: EdgeInsets.zero,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${_formatCredits(pack['credits'])} ${strings.creditsUnit}', style: TextStyle(color: colors.ink, fontSize: 17, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 4),
                        Text(strings.priceUsd.replaceFirst('{price}', '${pack['price_usd'] ?? '—'}'), style: TextStyle(color: colors.muted)),
                        const SizedBox(height: 14),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            onPressed: enabled ? () => onPurchase(pack['code'].toString()) : null,
                            icon: const Icon(Icons.add_card_outlined),
                            label: Text(strings.purchase),
                          ),
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
  }
}
