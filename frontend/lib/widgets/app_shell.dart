import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/auth/auth_controller.dart';

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
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.white,
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
            if (!compact) ...[
              const SizedBox(width: 10),
              const Text('RetailSense', style: TextStyle(fontSize: 14, color: Color(0xFF647476))),
            ],
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Center(
              child: Text(auth.company?['name']?.toString() ?? 'Avenqo'),
            ),
          ),
          IconButton(
            tooltip: 'Déconnexion',
            onPressed: auth.busy ? null : auth.logout,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      drawer: compact
          ? Drawer(
              child: _DestinationList(index: index, onSelect: context.go),
            )
          : null,
      body: Row(
        children: [
          if (!compact)
            SizedBox(
              width: 232,
              child: _DestinationList(index: index, onSelect: context.go),
            ),
          const VerticalDivider(width: 1),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _DestinationList extends StatelessWidget {
  const _DestinationList({required this.index, required this.onSelect});

  final int index;
  final void Function(String) onSelect;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(12, 18, 12, 12),
        itemCount: appDestinations.length,
        itemBuilder: (context, itemIndex) {
          final destination = appDestinations[itemIndex];
          final selected = itemIndex == index;
          return Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: ListTile(
              selected: selected,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
              leading: Icon(destination.icon, size: 21),
              title: Text(destination.label, style: TextStyle(fontWeight: selected ? FontWeight.w700 : FontWeight.w500)),
              onTap: () {
                if (Scaffold.maybeOf(context)?.hasDrawer ?? false) Navigator.pop(context);
                onSelect(destination.path);
              },
            ),
          );
        },
      ),
    );
  }
}
