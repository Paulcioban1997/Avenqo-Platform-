import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

typedef AdminCreditLoader = Future<List<Map<String, dynamic>>> Function(ApiClient api);

Future<List<Map<String, dynamic>>> _loadAdminCredits(ApiClient api) async =>
    ((await api.get('/admin/companies')) as List<dynamic>)
        .cast<Map<String, dynamic>>();

class AdminAiUsagePage extends StatelessWidget {
  const AdminAiUsagePage({
    super.key,
    required this.api,
    AdminCreditLoader? loader,
  }) : loader = loader ?? _loadAdminCredits;

  final ApiClient api;
  final AdminCreditLoader loader;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    final creditsT = AvenqoLocaleScope.translationsOf(context).phase4e;
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: loader(api),
      builder: (context, snapshot) {
        final companies = snapshot.data ?? const <Map<String, dynamic>>[];
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(
              title: s.aiUsageTitle,
              subtitle: creditsT.adminSubtitle,
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.aiUsageError)
            else if (companies.isEmpty)
              AdminEmptyState(message: creditsT.noCompanies, icon: Icons.business_outlined)
            else
              LayoutBuilder(
                builder: (context, constraints) => constraints.maxWidth >= 860
                    ? _AdminCreditsTable(companies: companies, strings: creditsT)
                    : _AdminCreditsList(companies: companies, strings: creditsT),
              ),
          ],
        );
      },
    );
  }
}

String _credits(Object? value, Phase4eStrings strings) => value == null
    ? strings.customAllowance
    : NumberFormat.decimalPattern().format(value);

AdminStatusTone _subscriptionTone(String status) {
  if (status == 'active' || status == 'trialing') return AdminStatusTone.positive;
  if (status == 'past_due') return AdminStatusTone.warning;
  if (status == 'canceled' || status == 'unpaid') return AdminStatusTone.negative;
  return AdminStatusTone.neutral;
}

class _AdminCreditsTable extends StatelessWidget {
  const _AdminCreditsTable({required this.companies, required this.strings});
  final List<Map<String, dynamic>> companies;
  final Phase4eStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return AdminCard(
      padding: EdgeInsets.zero,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          headingTextStyle: TextStyle(color: colors.muted, fontWeight: FontWeight.w700),
          dataTextStyle: TextStyle(color: colors.ink),
          columns: [
            DataColumn(label: Text(strings.company)),
            DataColumn(label: Text(strings.plan)),
            DataColumn(label: Text(strings.subscription)),
            DataColumn(label: Text(strings.monthlyAllowance), numeric: true),
            DataColumn(label: Text(strings.monthlyRemaining), numeric: true),
            DataColumn(label: Text(strings.purchasedRemaining), numeric: true),
            DataColumn(label: Text(strings.totalRemaining), numeric: true),
            DataColumn(label: Text(strings.aiUsage), numeric: true),
          ],
          rows: [for (final company in companies) _row(company, strings)],
        ),
      ),
    );
  }
}

DataRow _row(Map<String, dynamic> company, Phase4eStrings strings) {
  final status = company['subscription_status']?.toString() ?? 'inactive';
  return DataRow(cells: [
    DataCell(Text(company['name']?.toString() ?? '—', style: const TextStyle(fontWeight: FontWeight.w700))),
    DataCell(Text(company['plan_code']?.toString() ?? '—')),
    DataCell(AdminStatusBadge(label: status.toUpperCase(), tone: _subscriptionTone(status))),
    DataCell(Text(_credits(company['monthly_credits'], strings))),
    DataCell(Text(_credits(company['monthly_credits_remaining'], strings))),
    DataCell(Text(_credits(company['purchased_credits_remaining'], strings))),
    DataCell(Text(_credits(company['total_credits_remaining'], strings))),
    DataCell(Text(_credits(company['ai_requests_current_period'], strings))),
  ]);
}

class _AdminCreditsList extends StatelessWidget {
  const _AdminCreditsList({required this.companies, required this.strings});
  final List<Map<String, dynamic>> companies;
  final Phase4eStrings strings;

  @override
  Widget build(BuildContext context) => Column(
        children: [
          for (final company in companies) ...[
            _AdminCompanyCreditCard(company: company, strings: strings),
            const SizedBox(height: 12),
          ],
        ],
      );
}

class _AdminCompanyCreditCard extends StatelessWidget {
  const _AdminCompanyCreditCard({required this.company, required this.strings});
  final Map<String, dynamic> company;
  final Phase4eStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final status = company['subscription_status']?.toString() ?? 'inactive';
    return AdminCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(child: Text(company['name']?.toString() ?? '—', style: TextStyle(color: colors.ink, fontSize: 17, fontWeight: FontWeight.w800))),
            AdminStatusBadge(label: status.toUpperCase(), tone: _subscriptionTone(status)),
          ]),
          const SizedBox(height: 4),
          Text(company['plan_code']?.toString() ?? '—', style: TextStyle(color: colors.muted)),
          const SizedBox(height: 16),
          Wrap(
            spacing: 20,
            runSpacing: 12,
            children: [
              _AdminValue(label: strings.monthlyAllowance, value: _credits(company['monthly_credits'], strings)),
              _AdminValue(label: strings.monthlyRemaining, value: _credits(company['monthly_credits_remaining'], strings)),
              _AdminValue(label: strings.purchasedRemaining, value: _credits(company['purchased_credits_remaining'], strings)),
              _AdminValue(label: strings.totalRemaining, value: _credits(company['total_credits_remaining'], strings)),
              _AdminValue(label: strings.aiUsage, value: _credits(company['ai_requests_current_period'], strings)),
            ],
          ),
        ],
      ),
    );
  }
}

class _AdminValue extends StatelessWidget {
  const _AdminValue({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return SizedBox(
      width: 145,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: colors.muted, fontSize: 12)),
          const SizedBox(height: 3),
          Text(value, maxLines: 2, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}
