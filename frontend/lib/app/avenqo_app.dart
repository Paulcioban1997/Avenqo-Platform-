import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/app_theme.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/auth/auth_page.dart';
import 'package:avenqo/pages/billing_page.dart';
import 'package:avenqo/pages/assistant_page.dart';
import 'package:avenqo/pages/business_page.dart';
import 'package:avenqo/pages/dashboard_page.dart';
import 'package:avenqo/pages/employees_page.dart';
import 'package:avenqo/pages/home_page.dart';
import 'package:avenqo/pages/pricing_page.dart';
import 'package:avenqo/widgets/app_shell.dart';
import 'package:avenqo/i18n/locale_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';

class AvenqoApp extends StatefulWidget {
  const AvenqoApp({super.key, required this.auth, required this.locale});

  final AuthController auth;
  final LocaleController locale;

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
        if (!widget.auth.isAuthenticated && !isPublic) {
          return '/login';
        }
        if (widget.auth.isAuthenticated && path == '/login') {
          return '/dashboard';
        }
        return null;
      },
      routes: [
        GoRoute(path: '/', builder: (context, state) => const HomePage()),
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
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final app = !widget.auth.initialized
        ? MaterialApp(
            title: 'Avenqo',
            theme: AppTheme.light,
            home: const Scaffold(body: Center(child: CircularProgressIndicator())),
          )
        : MaterialApp.router(
            title: 'Avenqo',
            debugShowCheckedModeBanner: false,
            theme: AppTheme.light,
            routerConfig: _router,
          );
    return AvenqoLocaleScope(controller: widget.locale, child: app);
  }
}

Widget _protectedPage(String path, AuthController auth) {
  return switch (path) {
    '/dashboard' => DashboardPage(auth: auth),
    '/assistant' => AssistantPage(api: auth.api),
    '/team' => EmployeesPage(api: auth.api),
    '/billing' => BillingPage(api: auth.api),
    _ => BusinessPage(destination: destinationFor(path)),
  };
}
