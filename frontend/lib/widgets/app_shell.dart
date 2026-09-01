import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/widgets/language_selector.dart';
import 'package:avenqo/widgets/theme_toggle_button.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
}

class AppShell extends StatelessWidget {
  const AppShell({
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
    final selected = appDestinations.indexWhere(
      (destination) => destination.path == currentPath,
    );
    final index = selected < 0 ? 0 : selected;
    final compact = MediaQuery.sizeOf(context).width < 960;
    final showAskCta = currentPath != '/assistant';
    final askCta = AvenqoLocaleScope.translationsOf(context).dashboardHome.askAvenqoCta;
    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary,
                borderRadius: BorderRadius.circular(7),
              ),
              child: const Icon(Icons.insights, color: Colors.white, size: 19),
            ),
            const SizedBox(width: 10),
            const Text('Avenqo', style: TextStyle(fontWeight: FontWeight.w700)),
          ],
        ),
        actions: [
          if (showAskCta && !compact)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: FilledButton.icon(
                onPressed: () => context.go('/assistant'),
                style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
                icon: const Icon(Icons.auto_awesome, size: 16),
                label: Text(askCta),
              ),
            ),
          const ThemeToggleButton(),
          const LanguageSelector(),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 180),
                child: Text(
                  auth.company?['name']?.toString() ?? 'Avenqo',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: AvenqoLocaleScope.translationsOf(context).company.settingsLogout,
            onPressed: auth.busy ? null : auth.logout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      drawer: compact
          ? Drawer(
              child: _SidebarContent(
                index: index,
                onSelect: context.go,
                showAdminEntry: auth.isPlatformAdmin,
                auth: auth,
              ),
            )
          : null,
      body: Row(
        children: [
          if (!compact)
            SizedBox(
              width: 260,
              child: _SidebarContent(
                index: index,
                onSelect: context.go,
                showAdminEntry: auth.isPlatformAdmin,
                auth: auth,
              ),
            ),
          const VerticalDivider(width: 1),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _SidebarContent extends StatelessWidget {
  const _SidebarContent({
    required this.index,
    required this.onSelect,
    required this.auth,
    this.showAdminEntry = false,
  });

  final int index;
  final void Function(String) onSelect;
  final AuthController auth;
  final bool showAdminEntry;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: _DestinationList(
        index: index,
        onSelect: onSelect,
        showAdminEntry: showAdminEntry,
        auth: auth,
      ),
    );
  }
}

class _CompanyIdentityCard extends StatelessWidget {
  const _CompanyIdentityCard({required this.auth, required this.onSelect});

  final AuthController auth;
  final void Function(String) onSelect;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final t = AvenqoLocaleScope.translationsOf(context).company;
    final company = auth.company ?? const <String, dynamic>{};
    final planCode = company['subscription_plan']?.toString();
    final companyName = company['name']?.toString() ?? 'Avenqo';
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(color: _Brand.blue.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(9)),
                child: const Icon(Icons.apartment, color: _Brand.blue, size: 18),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  companyName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700, fontSize: 13.5),
                ),
              ),
            ],
          ),
          if (planCode != null) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: _Brand.blue.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                '${planCode[0].toUpperCase()}${planCode.substring(1)}',
                style: const TextStyle(color: _Brand.blue, fontWeight: FontWeight.w700, fontSize: 11),
              ),
            ),
          ],
          const SizedBox(height: 10),
          TextButton(
            style: TextButton.styleFrom(padding: EdgeInsets.zero, alignment: Alignment.centerLeft),
            onPressed: () => onSelect('/billing'),
            child: Text(t.settingsManageSubscription, style: const TextStyle(fontSize: 12.5)),
          ),
        ],
      ),
    );
  }
}

class _DestinationList extends StatelessWidget {
  const _DestinationList({
    required this.index,
    required this.onSelect,
    required this.auth,
    this.showAdminEntry = false,
  });

  final int index;
  final void Function(String) onSelect;
  final AuthController auth;
  final bool showAdminEntry;

  @override
  Widget build(BuildContext context) {
    final translations = AvenqoLocaleScope.translationsOf(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(12, 18, 12, 12),
      children: [
        for (var itemIndex = 0; itemIndex < appDestinations.length; itemIndex++) ...[
          if (appDestinations[itemIndex].sectionBreakBefore)
            const Padding(padding: EdgeInsets.symmetric(vertical: 8), child: Divider()),
          _buildTile(
            context,
            localizeDestination(appDestinations[itemIndex], translations),
            itemIndex == index,
          ),
        ],
        if (showAdminEntry) ...[
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Divider(),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: ListTile(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
              leading: const Icon(Icons.admin_panel_settings_outlined, size: 21),
              title: const Text('Avenqo Admin', style: TextStyle(fontWeight: FontWeight.w700)),
              onTap: () {
                if (Scaffold.maybeOf(context)?.hasDrawer ?? false) Navigator.pop(context);
                onSelect('/admin');
              },
            ),
          ),
        ],
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 8),
          child: Divider(),
        ),
        _CompanyIdentityCard(auth: auth, onSelect: onSelect),
      ],
    );
  }

  Widget _buildTile(BuildContext context, AppDestination destination, bool selected) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: ListTile(
        selected: selected,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        leading: Icon(destination.icon, size: 21),
        title: Text(
          destination.label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          softWrap: false,
          style: TextStyle(fontWeight: selected ? FontWeight.w700 : FontWeight.w500),
        ),
        onTap: () {
          if (Scaffold.maybeOf(context)?.hasDrawer ?? false) Navigator.pop(context);
          onSelect(destination.path);
        },
      ),
    );
  }
}
