import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/app_theme.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/app/theme_controller.dart';
import 'package:avenqo/app/theme_scope.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/auth/auth_page.dart';
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
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class AvenqoApp extends StatefulWidget {
  AvenqoApp({super.key, required this.auth, required this.locale, ThemeController? theme})
      : theme = theme ?? ThemeController();

  final AuthController auth;
  final LocaleController locale;
  final ThemeController theme;

  @override
  State<AvenqoApp> createState() => _AvenqoAppState();
}

class _AvenqoAppState extends State<AvenqoApp> {
  late final GoRouter _router = _createRouter();

  GoRouter _createRouter() {
    final publicPaths = {
      '/',
      '/pricing',
      '/login',
      '/register',
      '/forgot-password',
      '/verify-email',
      '/reset-password',
    };
    return GoRouter(
      initialLocation: '/',
      refreshListenable: widget.auth,
      redirect: (context, state) {
        if (!widget.auth.initialized) {
          return null;
        }
        final path = state.uri.path;
        final isPublic = publicPaths.contains(path);
        final isAdminPath = path == '/admin' || path.startsWith('/admin/');
        if (!widget.auth.isAuthenticated && !isPublic) {
          return '/login';
        }
        if (isAdminPath && !widget.auth.isPlatformAdmin) {
          // Défense en profondeur : le backend refuse déjà (403) via
          // `require_platform_admin`, mais on évite aussi d'afficher l'écran.
          return '/dashboard';
        }
        if (widget.auth.isAuthenticated && path == '/login') {
          return widget.auth.isPlatformAdmin ? '/admin' : '/dashboard';
        }
        // Onboarding : forcé une seule fois tant que le statut reste "pending"
        // (jamais reforcé après complétion/abandon — un banner du dashboard
        // permet de le reprendre volontairement s'il a été passé).
        final onboardingStatus = widget.auth.company?['onboarding_status'] as String?;
        final isOnboardingPath = path == '/onboarding';
        if (widget.auth.isAuthenticated &&
            !widget.auth.isPlatformAdmin &&
            !isAdminPath &&
            onboardingStatus == 'pending' &&
            !isOnboardingPath) {
          return '/onboarding';
        }
        return null;
      },
      routes: [
        GoRoute(path: '/', builder: (context, state) => const HomePage()),
        GoRoute(
          path: '/onboarding',
          builder: (context, state) => OnboardingPage(auth: widget.auth),
        ),
        GoRoute(
          path: '/pricing',
          builder: (context, state) => PricingPage(api: widget.auth.api),
        ),
        GoRoute(
          path: '/login',
          builder: (context, state) =>
              AuthPage(auth: widget.auth, mode: AuthMode.login),
        ),
        GoRoute(
          path: '/register',
          builder: (context, state) =>
              AuthPage(auth: widget.auth, mode: AuthMode.register),
        ),
        GoRoute(
          path: '/forgot-password',
          builder: (context, state) =>
              AuthPage(auth: widget.auth, mode: AuthMode.forgot),
        ),
        GoRoute(
          path: '/verify-email',
          builder: (context, state) =>
              AuthPage(auth: widget.auth, mode: AuthMode.verify),
        ),
        GoRoute(
          path: '/reset-password',
          builder: (context, state) =>
              AuthPage(auth: widget.auth, mode: AuthMode.reset),
        ),
        ShellRoute(
          builder: (context, state, child) => AppShell(
            auth: widget.auth,
            currentPath: state.uri.path,
            child: child,
          ),
          routes: [
            for (final destination in appDestinations)
              GoRoute(
                path: destination.path,
                builder: (context, state) =>
                    _protectedPage(destination.path, widget.auth),
              ),
          ],
        ),
        ShellRoute(
          builder: (context, state, child) => AdminShell(
            auth: widget.auth,
            currentPath: state.uri.path,
            child: child,
          ),
          routes: [
            GoRoute(
              path: '/admin',
              builder: (context, state) => AdminDashboardPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/companies',
              builder: (context, state) => AdminCompaniesPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/companies/:id',
              builder: (context, state) => AdminCompanyDetailPage(
                api: widget.auth.api,
                companyId: state.pathParameters['id']!,
              ),
            ),
            GoRoute(
              path: '/admin/audit-log',
              builder: (context, state) => AdminAuditLogPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/subscriptions',
              builder: (context, state) => AdminSubscriptionsPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/billing',
              builder: (context, state) => AdminBillingPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/ai-usage',
              builder: (context, state) => AdminAiUsagePage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/providers',
              builder: (context, state) => AdminProvidersPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/system-health',
              builder: (context, state) => AdminSystemHealthPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/support',
              builder: (context, state) => AdminSupportPage(api: widget.auth.api),
            ),
            GoRoute(
              path: '/admin/settings',
              builder: (context, state) => AdminSettingsPage(auth: widget.auth),
            ),
          ],
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.theme,
      builder: (context, _) {
        final app = !widget.auth.initialized
            ? MaterialApp(
                title: 'Avenqo',
                theme: AppTheme.light,
                darkTheme: AppTheme.dark,
                themeMode: widget.theme.mode,
                home: const Scaffold(body: Center(child: CircularProgressIndicator())),
              )
            : MaterialApp.router(
                title: 'Avenqo',
                debugShowCheckedModeBanner: false,
                theme: AppTheme.light,
                darkTheme: AppTheme.dark,
                themeMode: widget.theme.mode,
                routerConfig: _router,
              );
        return AvenqoThemeScope(
          controller: widget.theme,
          child: AvenqoLocaleScope(controller: widget.locale, child: app),
        );
      },
    );
  }
}

Widget _protectedPage(String path, AuthController auth) {
  return switch (path) {
    '/dashboard' => DashboardPage(auth: auth),
    '/assistant' => AssistantPage(api: auth.api),
    '/support' => SupportPage(api: auth.api),
    '/team' => EmployeesPage(api: auth.api),
    '/billing' => BillingPage(api: auth.api),
    '/connections' => ConnectionsPage(api: auth.api),
    '/settings' => SettingsPage(auth: auth),
    _ => BusinessPage(destination: destinationFor(path)),
  };
}
