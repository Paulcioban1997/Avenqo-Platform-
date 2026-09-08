import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:flutter/material.dart';

class ConnectorHub extends StatefulWidget {
  const ConnectorHub({
    super.key,
    required this.catalog,
    required this.connections,
    required this.busyConnectionIds,
    required this.authorizingShopify,
    required this.catalogUnavailable,
    required this.onConnectShopify,
    required this.onSync,
    required this.onDisconnect,
    required this.onRefresh,
    required this.t,
  });

  final List<Map<String, dynamic>> catalog;
  final List<Map<String, dynamic>> connections;
  final Set<String> busyConnectionIds;
  final bool authorizingShopify;
  final bool catalogUnavailable;
  final VoidCallback onConnectShopify;
  final Future<void> Function(Map<String, dynamic> connection) onSync;
  final Future<void> Function(Map<String, dynamic> connection) onDisconnect;
  final VoidCallback onRefresh;
  final CompanyStrings t;

  @override
  State<ConnectorHub> createState() => _ConnectorHubState();
}

class _ConnectorHubState extends State<ConnectorHub> {
  String _query = '';

  String _text(String key) =>
      widget.t.connectorHub[key] ??
      CompanyStrings.fallback().connectorHub[key] ??
      key;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final normalizedQuery = _query.trim().toLowerCase();
    final providers = widget.catalog
        .where((provider) {
          if (normalizedQuery.isEmpty) return true;
          return provider['display_name']?.toString().toLowerCase().contains(
                normalizedQuery,
              ) ==
              true;
        })
        .toList(growable: false);
    final hasShopifyConnection = widget.connections.any(
      (connection) =>
          connection['provider'] == 'shopify' &&
          connection['status'] != 'DISCONNECTED',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _text('title'),
                    style: TextStyle(
                      color: colors.ink,
                      fontSize: 24,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _text('subtitle'),
                    style: TextStyle(color: colors.muted),
                  ),
                ],
              ),
            ),
            IconButton(
              tooltip: _text('refresh'),
              onPressed: widget.onRefresh,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        if (widget.connections.isNotEmpty) ...[
          const SizedBox(height: 24),
          Text(
            _text('connectedStores'),
            style: TextStyle(
              color: colors.ink,
              fontSize: 15,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 10),
          Material(
            color: colors.surface,
            shape: RoundedRectangleBorder(
              side: BorderSide(color: colors.line),
              borderRadius: BorderRadius.circular(8),
            ),
            clipBehavior: Clip.antiAlias,
            child: Column(
              children: [
                for (var index = 0; index < widget.connections.length; index++)
                  _ConnectionRow(
                    connection: widget.connections[index],
                    isLast: index == widget.connections.length - 1,
                    busy: widget.busyConnectionIds.contains(
                      widget.connections[index]['id']?.toString(),
                    ),
                    onSync: () => widget.onSync(widget.connections[index]),
                    onDisconnect: () =>
                        widget.onDisconnect(widget.connections[index]),
                    text: _text,
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 24),
        if (widget.catalogUnavailable)
          _ConnectorNotice(
            message: _text('catalogUnavailable'),
            onRetry: widget.onRefresh,
          )
        else ...[
          SizedBox(
            width: 360,
            child: TextField(
              key: const ValueKey('connector-search'),
              onChanged: (value) => setState(() => _query = value),
              decoration: InputDecoration(
                hintText: _text('searchHint'),
                prefixIcon: const Icon(Icons.search),
                isDense: true,
              ),
            ),
          ),
          const SizedBox(height: 16),
          LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth >= 900
                  ? 3
                  : constraints.maxWidth >= 560
                  ? 2
                  : 1;
              final width =
                  (constraints.maxWidth - ((columns - 1) * 12)) / columns;
              return Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  for (final provider in providers)
                    SizedBox(
                      width: width,
                      child: _ProviderCard(
                        provider: provider,
                        hasShopifyConnection: hasShopifyConnection,
                        authorizing: widget.authorizingShopify,
                        onConnectShopify: widget.onConnectShopify,
                        text: _text,
                      ),
                    ),
                ],
              );
            },
          ),
        ],
      ],
    );
  }
}

class _ProviderCard extends StatelessWidget {
  const _ProviderCard({
    required this.provider,
    required this.hasShopifyConnection,
    required this.authorizing,
    required this.onConnectShopify,
    required this.text,
  });

  final Map<String, dynamic> provider;
  final bool hasShopifyConnection;
  final bool authorizing;
  final VoidCallback onConnectShopify;
  final String Function(String key) text;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final providerId = provider['provider']?.toString() ?? '';
    final available = provider['implementation_status'] == 'AVAILABLE';
    final configured = provider['configured'] == true;
    final category = provider['category']?.toString() ?? '';
    final canConnect = providerId == 'shopify' && available && configured;
    final accent = available ? const Color(0xFF1B9E5A) : colors.muted;
    return Container(
      key: ValueKey('provider-$providerId'),
      constraints: const BoxConstraints(minHeight: 148),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(
          color: available ? accent.withValues(alpha: 0.5) : colors.line,
        ),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  _providerIcon(providerId, category),
                  color: accent,
                  size: 21,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  provider['display_name']?.toString() ?? providerId,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: colors.ink,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Flexible(
                flex: 2,
                child: _StatusBadge(
                  label: text(available ? 'available' : 'comingSoon'),
                  color: accent,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            text(category),
            style: TextStyle(color: colors.muted, fontSize: 12),
          ),
          const SizedBox(height: 14),
          if (available)
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: FilledButton.icon(
                key: const ValueKey('connect-shopify'),
                onPressed: canConnect && !authorizing ? onConnectShopify : null,
                icon: authorizing
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.add_link, size: 18),
                label: Text(
                  configured
                      ? text(
                          hasShopifyConnection ? 'connectAnother' : 'connect',
                        )
                      : text('unavailable'),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ConnectionRow extends StatelessWidget {
  const _ConnectionRow({
    required this.connection,
    required this.isLast,
    required this.busy,
    required this.onSync,
    required this.onDisconnect,
    required this.text,
  });

  final Map<String, dynamic> connection;
  final bool isLast;
  final bool busy;
  final VoidCallback onSync;
  final VoidCallback onDisconnect;
  final String Function(String key) text;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final status = (connection['sync_status'] ?? connection['status'])
        ?.toString()
        .toUpperCase() ??
      'ERROR';
    final connectionStatus = connection['connection_status']
        ?.toString()
        .toUpperCase() ??
      (status == 'DISCONNECTED' ? 'DISCONNECTED' : 'CONNECTED');
    final active = status == 'SYNCING' || status == 'PROCESSING' || busy;
    final statusColor = status == 'ERROR' || status == 'DEGRADED'
        ? const Color(0xFFD1414B)
        : status == 'DISCONNECTED'
        ? colors.muted
        : status == 'READY' || status == 'CONNECTED'
        ? const Color(0xFF1B9E5A)
        : const Color(0xFF087CF0);
    final lastSync = connection['last_successful_sync']?.toString();
    final metadata = lastSync == null
        ? text('neverSynced')
        : '${text('lastSync')} ${lastSync.split('T').first}';
    final french = text('sync') == 'Synchroniser maintenant';
    final statusLabel = status == 'ERROR'
      ? (french ? 'Synchronisation échouée' : 'Synchronization failed')
      : status == 'DEGRADED'
      ? (french ? 'Stockage indisponible' : 'Storage unavailable')
      : text(switch (status) {
      'SYNCING' => 'syncing',
      'PROCESSING' => 'processing',
      'READY' => 'ready',
      'CONNECTED' => 'connected',
      'DISCONNECTED' => 'disconnected',
      'CONNECTING' => 'connecting',
      _ => 'error',
    });
    final connectionLabel = connectionStatus == 'DISCONNECTED'
        ? text('disconnected')
        : text('connected');

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        border: isLast ? null : Border(bottom: BorderSide(color: colors.line)),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final details = Row(
            children: [
              const Icon(Icons.storefront_outlined, color: Color(0xFF087CF0)),
              const SizedBox(width: 12),
              Expanded(
                flex: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      connection['display_name']?.toString() ??
                          connection['external_account_id']?.toString() ??
                          'Shopify',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: colors.ink,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      metadata,
                      style: TextStyle(color: colors.muted, fontSize: 12),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  alignment: WrapAlignment.end,
                  children: [
                    _StatusBadge(
                      label: '${french ? 'Connexion' : 'Connection'}: $connectionLabel',
                      color: connectionStatus == 'DISCONNECTED'
                          ? colors.muted
                          : const Color(0xFF1B9E5A),
                    ),
                    _StatusBadge(label: statusLabel, color: statusColor),
                  ],
                ),
              ),
            ],
          );
          final actions = Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (active)
                const SizedBox(
                  width: 40,
                  height: 40,
                  child: Padding(
                    padding: EdgeInsets.all(11),
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              else
                IconButton(
                  tooltip: text('sync'),
                  onPressed: status == 'DISCONNECTED' ? null : onSync,
                  icon: const Icon(Icons.sync),
                ),
              IconButton(
                tooltip: text('disconnect'),
                onPressed: active || status == 'DISCONNECTED'
                    ? null
                    : onDisconnect,
                icon: const Icon(Icons.link_off, color: Color(0xFFD1414B)),
              ),
            ],
          );
          if (constraints.maxWidth < 620) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                details,
                const SizedBox(height: 8),
                Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: actions,
                ),
              ],
            );
          }
          return Row(
            children: [
              Expanded(child: details),
              const SizedBox(width: 12),
              actions,
            ],
          );
        },
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: color.withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(6),
    ),
    child: Text(
      label,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      textAlign: TextAlign.center,
      style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w800),
    ),
  );
}

class _ConnectorNotice extends StatelessWidget {
  const _ConnectorNotice({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_outlined, color: Color(0xFFD1414B)),
          const SizedBox(width: 12),
          Expanded(
            child: Text(message, style: TextStyle(color: colors.ink)),
          ),
          IconButton(
            tooltip: textDirectionAwareRefresh(context),
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
    );
  }
}

String textDirectionAwareRefresh(BuildContext context) =>
    MaterialLocalizations.of(context).refreshIndicatorSemanticLabel;

IconData _providerIcon(String provider, String category) {
  if (provider == 'shopify') return Icons.shopping_bag_outlined;
  return switch (category) {
    'marketplace' => Icons.store_mall_directory_outlined,
    'payments' => Icons.payments_outlined,
    'marketing' => Icons.campaign_outlined,
    'fulfillment' => Icons.local_shipping_outlined,
    'analytics' => Icons.query_stats_outlined,
    _ => Icons.storefront_outlined,
  };
}
