import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/features/admin/admin_destinations.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/widgets/language_selector.dart';
import 'package:avenqo/widgets/theme_toggle_button.dart';

/// Shell visuellement distinct du workspace client (fond sombre premium,
/// badge "PLATFORM") pour qu'un platform_admin ne confonde jamais son espace
/// avec le tableau de bord d'une entreprise cliente.
class AdminShell extends StatelessWidget {
  const AdminShell({
    super.key,
    required this.auth,
    required this.currentPath,
    required this.child,
  });

  final AuthController auth;
  final String currentPath;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final selected = adminDestinations.indexWhere(
      (destination) => currentPath == destination.path ||
          (destination.path == '/admin/companies' && currentPath.startsWith('/admin/companies')),
    );
    final index = selected < 0 ? 0 : selected;
    final compact = MediaQuery.sizeOf(context).width < 960;
    final strings = AvenqoLocaleScope.translationsOf(context).admin;

    return Scaffold(
      backgroundColor: AvenqoColors.of(context).canvas,
      appBar: AppBar(
        backgroundColor: AdminBrand.navy,
        foregroundColor: Colors.white,
        elevation: 0,
        titleSpacing: 20,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                color: AdminBrand.blue,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.shield_outlined, size: 17, color: Colors.white),
            ),
            const SizedBox(width: 12),
            Text(strings.commandCenterTitle, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(width: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.12),
                border: Border.all(color: Colors.white24),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                strings.platformBadge,
                style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, letterSpacing: 0.4),
              ),
            ),
          ],
        ),
        actions: [
          const ThemeToggleButton(foregroundColor: Colors.white70),
          const LanguageSelector(),
          const SizedBox(width: 4),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 14,
                  backgroundColor: AdminBrand.blue.withValues(alpha: 0.25),
                  child: Text(
                    (auth.user?['email']?.toString() ?? 'A').substring(0, 1).toUpperCase(),
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 12),
                  ),
                ),
                if (!compact) ...[
                  const SizedBox(width: 8),
                  Text(
                    auth.user?['email']?.toString() ?? 'admin',
                    style: const TextStyle(color: Colors.white70, fontSize: 13),
                  ),
                ],
              ],
            ),
          ),
          IconButton(
            tooltip: strings.backToWorkspace,
            onPressed: () => context.go('/dashboard'),
            icon: const Icon(Icons.workspaces_outlined),
          ),
          IconButton(
            tooltip: strings.logOut,
            onPressed: auth.busy ? null : auth.logout,
            icon: const Icon(Icons.logout),
          ),
          const SizedBox(width: 6),
        ],
      ),
      drawer: compact
          ? Drawer(backgroundColor: AdminBrand.navy, child: _AdminNav(index: index, onSelect: context.go))
          : null,
      body: Row(
        children: [
          if (!compact)
            Material(
              color: AdminBrand.navy,
              child: SizedBox(
                width: 248,
                child: _AdminNav(index: index, onSelect: context.go),
              ),
            ),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _AdminNav extends StatelessWidget {
  const _AdminNav({required this.index, required this.onSelect});

  final int index;
  final void Function(String) onSelect;

  @override
  Widget build(BuildContext context) {
    final labels = adminNavLabels(AvenqoLocaleScope.translationsOf(context));
    return SafeArea(
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(14, 20, 14, 12),
        itemCount: adminDestinations.length,
        itemBuilder: (context, itemIndex) {
          final destination = adminDestinations[itemIndex];
          final selected = itemIndex == index;
          return Padding(
            padding: const EdgeInsets.only(bottom: 3),
            child: Material(
              color: selected ? AdminBrand.blue.withValues(alpha: 0.16) : Colors.transparent,
              borderRadius: BorderRadius.circular(10),
              child: InkWell(
                borderRadius: BorderRadius.circular(10),
                hoverColor: Colors.white.withValues(alpha: 0.06),
                onTap: () {
                  if (Scaffold.maybeOf(context)?.hasDrawer ?? false) Navigator.pop(context);
                  onSelect(destination.path);
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                  child: Row(
                    children: [
                      if (selected)
                        Container(
                          width: 3,
                          height: 16,
                          margin: const EdgeInsets.only(right: 9),
                          decoration: BoxDecoration(color: AdminBrand.blue, borderRadius: BorderRadius.circular(2)),
                        )
                      else
                        const SizedBox(width: 12),
                      Icon(
                        destination.icon,
                        size: 19,
                        color: selected ? Colors.white : Colors.white60,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          labels[itemIndex],
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          softWrap: false,
                          style: TextStyle(
                            color: selected ? Colors.white : Colors.white70,
                            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                            fontSize: 13.5,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
