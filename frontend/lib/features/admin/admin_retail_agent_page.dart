import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/agents/retail_agent_shell.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/pages/customers_page.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/pages/products_page.dart';
import 'package:avenqo/pages/recommendations_page.dart';
import 'package:avenqo/pages/sales_page.dart';

typedef AdminRetailCompaniesLoader =
    Future<List<Map<String, dynamic>>> Function(ApiClient api);

Future<List<Map<String, dynamic>>> _loadCompanies(ApiClient api) async =>
    ((await api.get('/admin/companies')) as List<dynamic>)
        .cast<Map<String, dynamic>>();

class AdminRetailAgentPage extends StatefulWidget {
  const AdminRetailAgentPage({
    super.key,
    required this.api,
    this.auth,
    this.selectedCompanyId,
    this.onSelectCompany,
    this.onViewCompany,
    AdminRetailCompaniesLoader? loader,
  }) : loader = loader ?? _loadCompanies,
       assert(selectedCompanyId == null || auth != null);

  final ApiClient api;
  final AuthController? auth;
  final String? selectedCompanyId;
  final ValueChanged<String>? onSelectCompany;
  final ValueChanged<String>? onViewCompany;
  final AdminRetailCompaniesLoader loader;

  @override
  State<AdminRetailAgentPage> createState() => _AdminRetailAgentPageState();
}

class _AdminRetailAgentPageState extends State<AdminRetailAgentPage> {
  late String? _selectedCompanyId = widget.selectedCompanyId;
  late Future<dynamic> _future = _load();

  Future<dynamic> _load() async {
    final companyId = _selectedCompanyId;
    if (companyId == null) return widget.loader(widget.api);
    try {
      return await widget.api.post(
        '/admin/companies/${Uri.encodeComponent(companyId)}/retail/context',
      );
    } on ApiException catch (error) {
      if (error.statusCode != 404 && error.statusCode != 422) rethrow;
      _selectedCompanyId = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) context.replace('/admin/agents/retail');
      });
      return widget.loader(widget.api);
    }
  }

  @override
  void didUpdateWidget(covariant AdminRetailAgentPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.selectedCompanyId != _selectedCompanyId) {
      _selectedCompanyId = widget.selectedCompanyId;
      _future = _load();
    }
  }

  void _selectCompany(String companyId) {
    setState(() {
      _selectedCompanyId = companyId;
      _future = _load();
    });
    final onSelect = widget.onSelectCompany;
    if (onSelect != null) {
      onSelect(companyId);
    } else {
      context.go(
        '/admin/agents/retail?company=${Uri.encodeQueryComponent(companyId)}',
      );
    }
  }

  Future<void> _leave({required bool switchCompany}) async {
    final companyId = _selectedCompanyId;
    try {
      if (companyId != null) {
        await widget.api.post(
          '/admin/companies/${Uri.encodeComponent(companyId)}/retail/context/exit',
        );
      }
    } on Object {
      // The explicit company ID is the context; a failed exit audit must not
      // retain it in the UI or URL.
    } finally {
      if (!mounted) return;
      setState(() {
        _selectedCompanyId = null;
        _future = widget.loader(widget.api);
      });
      context.go(switchCompany ? '/admin/agents/retail' : '/admin/agents');
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    return FutureBuilder<dynamic>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const AdminLoadingState();
        }
        if (snapshot.hasError) {
          return ListView(
            padding: const EdgeInsets.all(24),
            children: [
              AdminErrorState(
                message: strings.value(
                  _selectedCompanyId == null
                      ? 'loadTenantsError'
                      : 'tenantContextError',
                ),
              ),
              const SizedBox(height: 16),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: () {
                    setState(() {
                      _selectedCompanyId = null;
                      _future = widget.loader(widget.api);
                    });
                    context.go('/admin/agents/retail');
                  },
                  icon: const Icon(Icons.swap_horiz),
                  label: Text(strings.value('switchCompany')),
                ),
              ),
            ],
          );
        }
        if (_selectedCompanyId == null) {
          return _CompanySelector(
            companies: (snapshot.data as List<dynamic>)
                .cast<Map<String, dynamic>>(),
            onSelect: _selectCompany,
            onView: widget.onViewCompany,
          );
        }
        final contextData = snapshot.data as Map<String, dynamic>;
        return _AdminRetailWorkspace(
          key: ValueKey(contextData['company_id']),
          api: widget.api,
          auth: widget.auth!,
          companyId: contextData['company_id'].toString(),
          companyName: contextData['company_name'].toString(),
          onSwitch: () => _leave(switchCompany: true),
          onExit: () => _leave(switchCompany: false),
        );
      },
    );
  }
}

class _AdminRetailWorkspace extends StatefulWidget {
  const _AdminRetailWorkspace({
    super.key,
    required this.api,
    required this.auth,
    required this.companyId,
    required this.companyName,
    required this.onSwitch,
    required this.onExit,
  });

  final ApiClient api;
  final AuthController auth;
  final String companyId;
  final String companyName;
  final VoidCallback onSwitch;
  final VoidCallback onExit;

  @override
  State<_AdminRetailWorkspace> createState() => _AdminRetailWorkspaceState();
}

class _AdminRetailWorkspaceState extends State<_AdminRetailWorkspace> {
  int _section = 0;

  String get _base => '/admin/companies/${widget.companyId}/retail';

  Widget _page() => switch (_section) {
    0 => DashboardPage(
      auth: widget.auth,
      companyNameOverride: widget.companyName,
      readOnly: true,
      loader: (_) async => DashboardData.fromJson(
        await widget.api.get('$_base/dashboard') as Map<String, dynamic>,
      ),
    ),
    1 => SalesPage(
      api: widget.api,
      readOnly: true,
      loader: (period) async =>
          await widget.api.get(
                '$_base/sales/summary?period=${Uri.encodeQueryComponent(period)}',
              )
              as Map<String, dynamic>,
    ),
    2 => CustomersPage(
      api: widget.api,
      readOnly: true,
      loader: (page, search) async {
        final query = Uri(
          queryParameters: {
            'page': '$page',
            'page_size': '25',
            if (search.isNotEmpty) 'search': search,
          },
        ).query;
        return await widget.api.get('$_base/customers/summary?$query')
            as Map<String, dynamic>;
      },
    ),
    3 => ProductsPage(
      api: widget.api,
      readOnly: true,
      loader: (page, search, category, performance, sortBy) async {
        final query = Uri(
          queryParameters: {
            'page': '$page',
            'page_size': '25',
            'sort_by': sortBy,
            'sort_direction': 'desc',
            if (search.isNotEmpty) 'search': search,
            'category': ?category,
            'performance': ?performance,
          },
        ).query;
        return await widget.api.get('$_base/products/summary?$query')
            as Map<String, dynamic>;
      },
      detailLoader: (id) async =>
          await widget.api.get('$_base/products/${Uri.encodeComponent(id)}')
              as Map<String, dynamic>,
    ),
    _ => RecommendationsPage(
      api: widget.api,
      loader: () async =>
          await widget.api.get('$_base/recommendations')
              as Map<String, dynamic>,
      onNavigate: (route) {
        final index = [
          '/retail',
          '/sales',
          '/customers',
          '/products',
          '/recommendations',
        ].indexWhere(route.endsWith);
        if (index >= 0) setState(() => _section = index);
      },
    ),
  };

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    final localeCode = AvenqoLocaleScope.of(context).code;
    final colors = AvenqoColors.of(context);
    final companyLabelSeparator = localeCode.startsWith('fr') ? ' : ' : ': ';
    return Column(
      children: [
        Material(
          color: AdminBrand.blue.withValues(alpha: 0.08),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            child: Row(
              children: [
                const Icon(
                  Icons.admin_panel_settings_outlined,
                  color: AdminBrand.blue,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '${strings.value('adminViewLabel')}'
                    '$companyLabelSeparator${widget.companyName}',
                    style: TextStyle(
                      color: colors.ink,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                TextButton.icon(
                  onPressed: widget.onSwitch,
                  icon: const Icon(Icons.swap_horiz),
                  label: Text(strings.value('switchCompany')),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: widget.onExit,
                  icon: const Icon(Icons.logout),
                  label: Text(strings.value('exitTenantView')),
                ),
              ],
            ),
          ),
        ),
        Material(
          color: colors.surface,
          child: SizedBox(
            height: 52,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              itemCount: retailAgentDestinations.length,
              separatorBuilder: (_, _) => const SizedBox(width: 6),
              itemBuilder: (context, index) => TextButton.icon(
                onPressed: () => setState(() => _section = index),
                icon: Icon(retailAgentDestinations[index].icon, size: 17),
                label: Text(
                  strings.value(retailAgentDestinations[index].labelKey),
                ),
                style: TextButton.styleFrom(
                  foregroundColor: _section == index
                      ? AdminBrand.blue
                      : colors.muted,
                  backgroundColor: _section == index
                      ? AdminBrand.blue.withValues(alpha: 0.1)
                      : Colors.transparent,
                ),
              ),
            ),
          ),
        ),
        Expanded(
          child: KeyedSubtree(
            key: ValueKey('${widget.companyId}-$_section'),
            child: _page(),
          ),
        ),
      ],
    );
  }
}

class _CompanySelector extends StatelessWidget {
  const _CompanySelector({required this.companies, this.onSelect, this.onView});

  final List<Map<String, dynamic>> companies;
  final ValueChanged<String>? onSelect;
  final ValueChanged<String>? onView;

  @override
  Widget build(BuildContext context) {
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        AdminSectionHeader(
          title: strings.value('adminSelectTenantTitle'),
          subtitle: strings.value('adminSelectTenantSubtitle'),
        ),
        const SizedBox(height: 16),
        if (companies.isEmpty)
          AdminEmptyState(
            message: strings.value('noTenants'),
            icon: Icons.apartment_outlined,
          )
        else
          AdminCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                for (var index = 0; index < companies.length; index++) ...[
                  if (index > 0) const Divider(height: 1),
                  _CompanyChoice(
                    company: companies[index],
                    actionLabel: strings.value('selectTenantAction'),
                    onSelect: () {
                      final id = companies[index]['id'].toString();
                      (onSelect ??
                          (value) => context.go(
                            '/admin/agents/retail?company=$value',
                          ))(id);
                    },
                    onView: () {
                      final id = companies[index]['id'].toString();
                      (onView ??
                          (value) => context.go('/admin/companies/$value'))(id);
                    },
                  ),
                ],
              ],
            ),
          ),
      ],
    );
  }
}

class _CompanyChoice extends StatelessWidget {
  const _CompanyChoice({
    required this.company,
    required this.actionLabel,
    required this.onSelect,
    required this.onView,
  });

  final Map<String, dynamic> company;
  final String actionLabel;
  final VoidCallback onSelect;
  final VoidCallback onView;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final strings = AvenqoLocaleScope.translationsOf(context).agents;
    return Material(
      color: Colors.transparent,
      child: ListTile(
        leading: const Icon(Icons.apartment_outlined),
        title: Text(
          company['name']?.toString() ?? '—',
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Text(
          company['plan_code']?.toString() ?? '—',
          style: TextStyle(color: colors.muted),
        ),
        trailing: Wrap(
          spacing: 8,
          children: [
            IconButton(
              onPressed: onView,
              tooltip: strings.value('viewCompanyDetails'),
              icon: const Icon(Icons.open_in_new),
            ),
            TextButton(onPressed: onSelect, child: Text(actionLabel)),
          ],
        ),
        onTap: onSelect,
      ),
    );
  }
}
