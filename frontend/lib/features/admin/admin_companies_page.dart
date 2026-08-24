import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

/// Répertoire cross-tenant : métadonnées administratives uniquement (jamais
/// les données commerciales privées d'une entreprise cliente).
class AdminCompaniesPage extends StatefulWidget {
  const AdminCompaniesPage({super.key, required this.api});
  final ApiClient api;

  @override
  State<AdminCompaniesPage> createState() => _AdminCompaniesPageState();
}

class _AdminCompaniesPageState extends State<AdminCompaniesPage> {
  late final Future<dynamic> _future = widget.api.get('/admin/companies');
  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<dynamic>(
      future: _future,
      builder: (context, snapshot) {
        final all = (snapshot.data as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();
        final companies = _query.isEmpty
            ? all
            : all.where((c) => (c['name']?.toString().toLowerCase() ?? '').contains(_query.toLowerCase())).toList();
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(
              title: s.companiesTitle,
              subtitle: '${all.length} ${s.companiesSubtitle}',
              trailing: SizedBox(
                width: 260,
                child: TextField(
                  controller: _search,
                  onChanged: (v) => setState(() => _query = v),
                  decoration: InputDecoration(
                    hintText: s.searchCompaniesHint,
                    prefixIcon: const Icon(Icons.search, size: 20),
                    isDense: true,
                    filled: true,
                    fillColor: Colors.white,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide(color: colors.line),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.companiesError)
            else if (companies.isEmpty)
              AdminEmptyState(
                message: all.isEmpty ? s.noCompaniesYet : '${s.noCompaniesMatch} “$_query”.',
                icon: Icons.apartment_outlined,
              )
            else
              AdminCard(
                padding: EdgeInsets.zero,
                child: Column(
                  children: [
                    for (var i = 0; i < companies.length; i++) ...[
                      if (i > 0) Divider(height: 1, color: colors.line),
                      _CompanyRow(company: companies[i], strings: s),
                    ],
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}

class _CompanyRow extends StatelessWidget {
  const _CompanyRow({required this.company, required this.strings});
  final Map<String, dynamic> company;
  final AdminStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => context.go('/admin/companies/${company['id']}'),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          child: Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: AdminBrand.blue.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.apartment_outlined, color: AdminBrand.blue, size: 18),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      company['name']?.toString() ?? strings.companyFallbackName,
                      style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${company['country'] ?? '—'} · ${strings.joinedLabel} ${company['joined_at'] ?? '—'}',
                      style: TextStyle(color: colors.muted, fontSize: 12.5),
                    ),
                  ],
                ),
              ),
              AdminStatusBadge(
                label: '${company['plan_code'] ?? '—'}'.toUpperCase(),
                tone: AdminStatusTone.neutral,
              ),
              const SizedBox(width: 10),
              AdminStatusBadge(
                label: '${company['subscription_status'] ?? '—'}'.toUpperCase(),
                tone: toneForProviderStatus('${company['subscription_status'] ?? ''}'),
              ),
              const SizedBox(width: 10),
              Icon(Icons.chevron_right, color: colors.muted),
            ],
          ),
        ),
      ),
    );
  }
}

