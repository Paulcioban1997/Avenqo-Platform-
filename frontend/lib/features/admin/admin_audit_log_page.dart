import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/features/admin/admin_theme.dart';
import 'package:avenqo/i18n/locale_scope.dart';

/// Lecture seule : un platform_admin consulte l'audit log mais ne peut
/// jamais le modifier depuis cette interface.
class AdminAuditLogPage extends StatelessWidget {
  const AdminAuditLogPage({super.key, required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final s = AvenqoLocaleScope.translationsOf(context).admin;
    final colors = AvenqoColors.of(context);
    return FutureBuilder<dynamic>(
      future: api.get('/admin/audit-log'),
      builder: (context, snapshot) {
        final entries = (snapshot.data as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            AdminSectionHeader(title: s.auditLogTitle, subtitle: '${entries.length} ${s.auditLogSubtitle}'),
            const SizedBox(height: 20),
            if (snapshot.connectionState != ConnectionState.done)
              const AdminLoadingState()
            else if (snapshot.hasError)
              AdminErrorState(message: s.auditLogError)
            else if (entries.isEmpty)
              AdminEmptyState(message: s.noAuditEntries, icon: Icons.fact_check_outlined)
            else
              AdminCard(
                padding: EdgeInsets.zero,
                child: Column(
                  children: [
                    for (var i = 0; i < entries.length; i++) ...[
                      if (i > 0) Divider(height: 1, color: colors.line),
                      _AuditRow(entry: entries[i]),
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

class _AuditRow extends StatelessWidget {
  const _AuditRow({required this.entry});
  final Map<String, dynamic> entry;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      child: Row(
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: AdminBrand.blue.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(9),
            ),
            child: const Icon(Icons.receipt_long_outlined, color: AdminBrand.blue, size: 16),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(entry['action']?.toString() ?? '—', style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
                const SizedBox(height: 3),
                Text(
                  '${entry['target_type'] ?? '—'} · ${entry['created_at'] ?? '—'}',
                  style: TextStyle(color: colors.muted, fontSize: 12.5),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

