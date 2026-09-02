import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/app_theme.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/auth/auth_page.dart';
import 'package:avenqo/auth/subscription_route_guard.dart';
import 'package:avenqo/pages/billing_page.dart';
import 'package:avenqo/pages/assistant_page.dart';
import 'package:avenqo/pages/support_page.dart';
import 'package:avenqo/pages/business_page.dart';
import 'package:avenqo/pages/connections_page.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/pages/employees_page.dart';
import 'package:avenqo/pages/home_page.dart';
import 'package:avenqo/pages/onboarding_page.dart';
import 'package:avenqo/pages/pricing_page.dart';
import 'package:avenqo/pages/settings_page.dart';
import 'package:avenqo/pages/sales_page.dart';
import 'package:avenqo/pages/customers_page.dart';
import 'package:avenqo/pages/products_page.dart';
import 'package:avenqo/pages/recommendations_page.dart';
import 'package:avenqo/pages/agents_page.dart';
import 'package:avenqo/agents/retail_agent_shell.dart';
import 'package:avenqo/widgets/app_shell.dart';
import 'package:avenqo/widgets/admin_shell.dart';
import 'package:avenqo/features/admin/admin_dashboard_page.dart';
import 'package:avenqo/features/admin/admin_companies_page.dart';
import 'package:avenqo/features/admin/admin_company_detail_page.dart';
import 'package:avenqo/features/admin/admin_audit_log_page.dart';
import 'package:avenqo/features/admin/admin_subscriptions_page.dart';
import 'package:avenqo/features/admin/admin_billing_page.dart';
import 'package:avenqo/features/admin/admin_ai_usage_page.dart';
import 'package:avenqo/features/admin/admin_providers_page.dart';
import 'package:avenqo/features/admin/admin_system_health_page.dart';
import 'package:avenqo/features/admin/admin_support_page.dart';
import 'package:avenqo/features/admin/admin_settings_page.dart';
import 'package:avenqo/features/admin/admin_agents_page.dart';
import 'package:avenqo/features/admin/admin_retail_agent_page.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_info.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class AvenqoApp extends StatefulWidget {
  AvenqoApp({super.key, required this.auth, required this.locale, ThemeController? theme}) : theme = theme ?? ThemeController();
  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;
  @override State<AvenqoApp> createState() => _AvenqoAppState();
}

class _AvenqoAppState extends State<AvenqoApp> {
  late final GoRouter _router = _createRouter();
  GoRouter _createRouter() => GoRouter(
    refreshListenable: widget.auth,
    redirect: (context, state) {
      if (!widget.auth.initialized) return null;
      return subscriptionRedirect(path: state.uri.path, isAuthenticated: widget.auth.isAuthenticated, isPlatformAdmin: widget.auth.isPlatformAdmin, hasActiveSubscription: widget.auth.hasActiveSubscription, onboardingStatus: widget.auth.company?['onboarding_status'] as String?);
    },
    routes: [
      GoRoute(path: '/', builder: (context, state) => HomePage(initialSection: state.uri.queryParameters['section'])),
      GoRoute(path: '/onboarding', builder: (context, state) => OnboardingPage(auth: widget.auth)),
      GoRoute(path: '/pricing', builder: (context, state) => PricingPage(api: widget.auth.api)),
      GoRoute(path: '/login', builder: (context, state) => Stack(children: [AuthPage(auth: widget.auth, mode: AuthMode.login), Positioned(right: 20, bottom: 20, child: SafeArea(child: Material(color: Colors.transparent, child: TextButton.icon(onPressed: () => context.go('/verify-email'), icon: const Icon(Icons.mark_email_unread_outlined), label: const Text('Vérifier / renvoyer l’email')))))])),
      GoRoute(path: '/register', builder: (context, state) => AuthPage(auth: widget.auth, mode: AuthMode.register)),
      GoRoute(path: '/forgot-password', builder: (context, state) => AuthPage(auth: widget.auth, mode: AuthMode.forgot)),
      GoRoute(path: '/verify-email', builder: (context, state) => AuthPage(auth: widget.auth, mode: AuthMode.verify, initialToken: state.uri.queryParameters['token'], initialEmail: state.uri.queryParameters['email'], emailDeliveryUnavailable: state.uri.queryParameters['delivery'] == 'unavailable')),
      GoRoute(path: '/reset-password', builder: (context, state) => AuthPage(auth: widget.auth, mode: AuthMode.reset, initialToken: state.uri.queryParameters['token'])),
      ShellRoute(builder: (context, state, child) => AppShell(auth: widget.auth, currentPath: state.uri.path, child: child), routes: [
        for (final destination in appDestinations) GoRoute(path: destination.path, builder: (context, state) => _protectedPage(destination.path, widget.auth)),
        ShellRoute(builder: (context, state, child) => RetailAgentShell(currentPath: state.uri.path, child: child), routes: [for (final destination in retailAgentDestinations) GoRoute(path: destination.path, builder: (context, state) => _retailPage(destination.path, widget.auth))]),
        for (final legacyPath in _legacyRetailRoutes.keys) GoRoute(path: legacyPath, redirect: (context, state) => _legacyRetailRoutes[legacyPath]),
      ]),
      ShellRoute(builder: (context, state, child) => AdminShell(auth: widget.auth, currentPath: state.uri.path, child: child), routes: [
        GoRoute(path: '/admin', builder: (context, state) => AdminDashboardPage(api: widget.auth.api)),
        GoRoute(path: '/admin/companies', builder: (context, state) => AdminCompaniesPage(api: widget.auth.api)),
        GoRoute(path: '/admin/agents', builder: (context, state) => const AdminAgentsPage()),
        GoRoute(path: '/admin/agents/retail', builder: (context, state) => AdminRetailAgentPage(api: widget.auth.api, auth: widget.auth, selectedCompanyId: state.uri.queryParameters['company'])),
        GoRoute(path: '/admin/companies/:id', builder: (context, state) => AdminCompanyDetailPage(api: widget.auth.api, companyId: state.pathParameters['id']!)),
        GoRoute(path: '/admin/audit-log', builder: (context, state) => AdminAuditLogPage(api: widget.auth.api)),
        GoRoute(path: '/admin/subscriptions', builder: (context, state) => AdminSubscriptionsPage(api: widget.auth.api)),
        GoRoute(path: '/admin/billing', builder: (context, state) => AdminBillingPage(api: widget.auth.api)),
        GoRoute(path: '/admin/ai-usage', builder: (context, state) => AdminAiUsagePage(api: widget.auth.api)),
        GoRoute(path: '/admin/providers', builder: (context, state) => AdminProvidersPage(api: widget.auth.api)),
        GoRoute(path: '/admin/system-health', builder: (context, state) => AdminSystemHealthPage(api: widget.auth.api)),
        GoRoute(path: '/admin/support', builder: (context, state) => AdminSupportPage(api: widget.auth.api)),
        GoRoute(path: '/admin/settings', builder: (context, state) => AdminSettingsPage(auth: widget.auth)),
      ]),
    ],
  );

  @override Widget build(BuildContext context) => ListenableBuilder(
    listenable: Listenable.merge([widget.theme, widget.locale]),
    builder: (context, _) {
      final rawLocale = _localeFromCode(widget.locale.code);
      final effectiveLocale = GlobalMaterialLocalizations.delegate.isSupported(rawLocale) ? rawLocale : const Locale('en');
      final supportedLocales = _supportedLocalesFrom(widget.locale.availableLocales);
      final isRtl = widget.locale.currentLocaleInfo?.isRtl ?? false;
      final app = !widget.auth.initialized
        ? MaterialApp(title: 'Avenqo', theme: AppTheme.light, darkTheme: AppTheme.dark, themeMode: widget.theme.mode, locale: effectiveLocale, supportedLocales: supportedLocales, localizationsDelegates: const [GlobalMaterialLocalizations.delegate, GlobalWidgetsLocalizations.delegate, GlobalCupertinoLocalizations.delegate], builder: (context, child) => Directionality(textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr, child: child!), home: const Scaffold(body: Center(child: CircularProgressIndicator())))
        : MaterialApp.router(title: 'Avenqo', debugShowCheckedModeBanner: false, theme: AppTheme.light, darkTheme: AppTheme.dark, themeMode: widget.theme.mode, locale: effectiveLocale, supportedLocales: supportedLocales, localizationsDelegates: const [GlobalMaterialLocalizations.delegate, GlobalWidgetsLocalizations.delegate, GlobalCupertinoLocalizations.delegate], builder: (context, child) => Directionality(textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr, child: child!), routerConfig: _router);
      return AvenqoThemeScope(controller: widget.theme, child: AvenqoLocaleScope(controller: widget.locale, child: app));
    },
  );
}

Locale _localeFromCode(String code) { final parts = code.split('-'); return parts.length == 2 ? Locale(parts[0], parts[1]) : Locale(code); }
List<Locale> _supportedLocalesFrom(List<LocaleInfo> locales) { final supported = <Locale>{const Locale('en')}; for (final locale in locales) { final candidate = _localeFromCode(locale.code); if (GlobalMaterialLocalizations.delegate.isSupported(candidate)) supported.add(candidate); } return supported.toList(growable: false); }
Widget _protectedPage(String path, AuthController auth) => switch (path) { '/agents' => const AgentsPage(), '/assistant' => AssistantPage(api: auth.api), '/support' => SupportPage(api: auth.api), '/team' => EmployeesPage(api: auth.api), '/billing' => BillingPage(api: auth.api), '/connections' => ConnectionsPage(api: auth.api), '/settings' => SettingsPage(auth: auth), _ => BusinessPage(destination: destinationFor(path)), };
const _legacyRetailRoutes = <String, String>{'/dashboard': '/retail', '/sales': '/retail/sales', '/customers': '/retail/customers', '/products': '/retail/products', '/recommendations': '/retail/recommendations'};
Widget _retailPage(String path, AuthController auth) { final companyId = auth.company?['id']; return switch (path) { '/retail' => DashboardPage(auth: auth), '/retail/sales' => SalesPage(key: ValueKey('sales-$companyId'), api: auth.api), '/retail/customers' => CustomersPage(key: ValueKey('customers-$companyId'), api: auth.api), '/retail/products' => ProductsPage(key: ValueKey('products-$companyId'), api: auth.api), '/retail/recommendations' => RecommendationsPage(key: ValueKey('recommendations-$companyId'), api: auth.api), _ => DashboardPage(auth: auth), }; }
