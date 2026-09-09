import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:simple_icons/simple_icons.dart';

class ConnectorHub extends StatefulWidget {
  const ConnectorHub({
    super.key,
    required this.catalog,
    required this.connections,
    required this.busyConnectionIds,
    required this.authorizingProvider,
    required this.catalogUnavailable,
    required this.onConnect,
    required this.onSync,
    required this.onDisconnect,
    required this.onRefresh,
    required this.t,
  });

  final List<Map<String, dynamic>> catalog;
  final List<Map<String, dynamic>> connections;
  final Set<String> busyConnectionIds;
  final String? authorizingProvider;
  final bool catalogUnavailable;
  final ValueChanged<String> onConnect;
  final Future<void> Function(Map<String, dynamic> connection) onSync;
  final Future<void> Function(Map<String, dynamic> connection) onDisconnect;
  final VoidCallback onRefresh;
  final CompanyStrings t;

  @override
  State<ConnectorHub> createState() => _ConnectorHubState();
}

class _ConnectorHubState extends State<ConnectorHub> {
  final MenuController _providerMenu = MenuController();
  String _providerQuery = '';
  String? _selectedProviderId;

  String _text(String key) =>
      widget.t.connectorHub[key] ??
      CompanyStrings.fallback().connectorHub[key] ??
      key;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final ecommerceProviders = widget.catalog
        .where((provider) => provider['category'] == 'ecommerce')
        .toList(growable: false);
    final marketplaceProviders = widget.catalog
        .where((provider) => provider['provider'] == 'etsy')
        .toList(growable: false);
    final supportedProviders = [...ecommerceProviders, ...marketplaceProviders];
    final normalizedQuery = _providerQuery.trim().toLowerCase();
    bool matchesQuery(Map<String, dynamic> provider) =>
        normalizedQuery.isEmpty ||
        provider['display_name']?.toString().toLowerCase().contains(
              normalizedQuery,
            ) ==
            true;
    final visibleEcommerceProviders = ecommerceProviders
        .where(matchesQuery)
        .toList(growable: false);
    final visibleMarketplaceProviders = marketplaceProviders
        .where(matchesQuery)
        .toList(growable: false);
    final selectedProvider = supportedProviders
        .cast<Map<String, dynamic>?>()
        .firstWhere(
          (provider) => provider?['provider'] == _selectedProviderId,
          orElse: () => null,
        );
    MenuItemButton providerMenuItem(Map<String, dynamic> provider) =>
        MenuItemButton(
          key: ValueKey('select-${provider['provider']}'),
          leadingIcon: _BrandMark(
            provider: provider['provider']?.toString() ?? '',
            size: 24,
          ),
          onPressed: () {
            _providerMenu.close();
            setState(() {
              _providerQuery = '';
              _selectedProviderId = provider['provider']?.toString();
            });
          },
          child: SizedBox(
            width: 250,
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    provider['display_name']?.toString() ?? '',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _text(
                    provider['customer_status'] == 'AVAILABLE'
                        ? 'available'
                        : 'comingSoon',
                  ),
                  style: TextStyle(
                    color: provider['customer_status'] == 'AVAILABLE'
                        ? const Color(0xFF1B9E5A)
                        : colors.muted,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
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
          Text(
            _text('commerceSources'),
            style: TextStyle(
              color: colors.ink,
              fontSize: 15,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 10),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: MenuAnchor(
              controller: _providerMenu,
              onClose: () {
                if (_providerQuery.isNotEmpty) {
                  setState(() => _providerQuery = '');
                }
              },
              menuChildren: [
                SizedBox(
                  width: 320,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
                    child: TextField(
                      key: const ValueKey('ecommerce-provider-search'),
                      autofocus: true,
                      onChanged: (value) =>
                          setState(() => _providerQuery = value),
                      decoration: InputDecoration(
                        hintText: _text('providerSearchHint'),
                        prefixIcon: const Icon(Icons.search, size: 20),
                        isDense: true,
                      ),
                    ),
                  ),
                ),
                if (visibleEcommerceProviders.isNotEmpty)
                  _ProviderGroupLabel(label: _text('ecommerce')),
                for (final provider in visibleEcommerceProviders)
                  providerMenuItem(provider),
                if (visibleMarketplaceProviders.isNotEmpty)
                  _ProviderGroupLabel(label: _text('marketplace')),
                for (final provider in visibleMarketplaceProviders)
                  providerMenuItem(provider),
              ],
              builder: (context, controller, child) => FilledButton.icon(
                key: const ValueKey('add-ecommerce-connector'),
                onPressed: () =>
                    controller.isOpen ? controller.close() : controller.open(),
                icon: const Icon(Icons.add),
                label: Text(_text('addOnlineStore')),
              ),
            ),
          ),
          if (selectedProvider != null) ...[
            const SizedBox(height: 16),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 680),
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 180),
                  child: _ProviderCard(
                    key: ValueKey('focused-${selectedProvider['provider']}'),
                    provider: selectedProvider,
                    hasConnection: widget.connections.any(
                      (connection) =>
                          connection['provider'] ==
                              selectedProvider['provider'] &&
                          connection['status'] != 'DISCONNECTED',
                    ),
                    authorizing:
                        widget.authorizingProvider ==
                        selectedProvider['provider'],
                    onCancel: () => setState(() => _selectedProviderId = null),
                    onConnect: () => widget.onConnect(
                      selectedProvider['provider']?.toString() ?? '',
                    ),
                    text: _text,
                  ),
                ),
              ),
            ),
          ],
        ],
      ],
    );
  }
}

class _ProviderCard extends StatelessWidget {
  const _ProviderCard({
    super.key,
    required this.provider,
    required this.hasConnection,
    required this.authorizing,
    required this.onCancel,
    required this.onConnect,
    required this.text,
  });

  final Map<String, dynamic> provider;
  final bool hasConnection;
  final bool authorizing;
  final VoidCallback onCancel;
  final VoidCallback onConnect;
  final String Function(String key) text;

  String _capabilityLabel(Object capability) => text(
    const {
          'orders': 'capabilityOrders',
          'customers': 'capabilityCustomers',
          'products': 'capabilityProducts',
          'inventory': 'capabilityInventory',
          'refunds': 'capabilityRefunds',
          'payments': 'capabilityPayments',
          'discounts': 'capabilityDiscounts',
          'variants': 'capabilityVariants',
          'locations': 'capabilityLocations',
          'fulfillments': 'capabilityFulfillments',
          'abandoned_carts': 'capabilityAbandonedCarts',
          'catalog': 'capabilityCatalog',
          'webhooks': 'capabilityWebhooks',
          'incremental_sync': 'capabilityIncrementalSync',
        }[capability.toString()] ??
        'capabilities',
  );

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final providerId = provider['provider']?.toString() ?? '';
    final customerStatus =
        provider['customer_status']?.toString() ?? 'COMING_SOON';
    final available = customerStatus == 'AVAILABLE';
    final configured = provider['configured'] == true;
    final canConnect = configured && available;
    final canTest = !available && provider['internal_test_available'] == true;
    final actionable = canConnect || canTest;
    final accent = actionable ? const Color(0xFF1B9E5A) : colors.muted;
    final capabilities =
        (provider['capabilities'] as List<dynamic>? ?? const []).cast<Object>();
    return Container(
      key: ValueKey('provider-$providerId'),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(
          color: actionable ? accent.withValues(alpha: 0.5) : colors.line,
        ),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _BrandMark(provider: providerId, size: 42),
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
            text(
              provider['category'] == 'marketplace'
                  ? 'marketplace'
                  : 'ecommerce',
            ),
            style: TextStyle(
              color: colors.muted,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            text('providerDescription'),
            style: TextStyle(color: colors.muted, height: 1.45),
          ),
          if (capabilities.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              text('capabilities'),
              style: TextStyle(
                color: colors.ink,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 5,
              runSpacing: 5,
              children: [
                for (final capability in capabilities.take(5))
                  Chip(
                    visualDensity: VisualDensity.compact,
                    label: Text(
                      _capabilityLabel(capability),
                      style: const TextStyle(fontSize: 10),
                    ),
                  ),
              ],
            ),
          ],
          const SizedBox(height: 18),
          Wrap(
            spacing: 10,
            runSpacing: 8,
            alignment: WrapAlignment.end,
            children: [
              TextButton(
                key: const ValueKey('cancel-provider-selection'),
                onPressed: onCancel,
                child: Text(text('cancel')),
              ),
              if (canTest)
                OutlinedButton.icon(
                  key: ValueKey('test-$providerId'),
                  onPressed: authorizing ? null : onConnect,
                  icon: const Icon(Icons.science_outlined, size: 18),
                  label: Text(text('testConnector')),
                )
              else
                FilledButton.icon(
                  key: ValueKey('connect-$providerId'),
                  onPressed: canConnect && !authorizing ? onConnect : null,
                  icon: authorizing
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.add_link, size: 18),
                  label: Text(
                    canConnect
                        ? text(
                            hasConnection
                                ? 'connectAnother'
                                : 'connectToAvenqo',
                          )
                        : text('comingSoon'),
                  ),
                ),
            ],
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
    final status =
        (connection['sync_status'] ?? connection['status'])
            ?.toString()
            .toUpperCase() ??
        'ERROR';
    final connectionStatus =
        connection['connection_status']?.toString().toUpperCase() ??
        (status == 'DISCONNECTED' ? 'DISCONNECTED' : 'CONNECTED');
    final active = status == 'SYNCING' || status == 'PROCESSING' || busy;
    final statusColor =
        {'ERROR', 'DEGRADED', 'FAILED', 'REAUTH_REQUIRED'}.contains(status)
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
    final statusLabel = status == 'ERROR' || status == 'FAILED'
        ? text('syncFailed')
        : status == 'DEGRADED'
        ? text('storageUnavailable')
        : text(switch (status) {
            'SYNCING' => 'syncing',
            'PROCESSING' => 'processing',
            'READY' => 'ready',
            'CONNECTED' => 'connected',
            'DISCONNECTED' => 'disconnected',
            'CONNECTING' => 'connecting',
            'AUTHORIZING' => 'authorizing',
            'REAUTH_REQUIRED' => 'reauthorizationRequired',
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
                          connection['provider']?.toString() ??
                          text('ecommerce'),
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
                      label: '${text('connection')}: $connectionLabel',
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

class _ProviderGroupLabel extends StatelessWidget {
  const _ProviderGroupLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
          color: colors.muted,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
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

class _BrandMark extends StatelessWidget {
  const _BrandMark({required this.provider, required this.size});

  final String provider;
  final double size;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final brand = _providerBrand(provider);
    return Container(
      key: ValueKey('brand-icon-$provider'),
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: brand.color.withValues(alpha: 0.1),
        border: Border.all(color: brand.color.withValues(alpha: 0.22)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: brand.asset == null
          ? Icon(
              brand.icon ?? Icons.storefront_outlined,
              color: brand.icon == null ? colors.muted : brand.color,
              size: size * 0.52,
            )
          : Padding(
              padding: EdgeInsets.all(size * 0.2),
              child: SvgPicture.asset(brand.asset!, fit: BoxFit.contain),
            ),
    );
  }
}

({IconData? icon, String? asset, Color color}) _providerBrand(
  String provider,
) => switch (provider) {
  'shopify' => (
    icon: SimpleIcons.shopify,
    asset: null,
    color: const Color(0xFF7AB55C),
  ),
  'woocommerce' => (
    icon: SimpleIcons.woocommerce,
    asset: null,
    color: const Color(0xFF96588A),
  ),
  'bigcommerce' => (
    icon: SimpleIcons.bigcommerce,
    asset: null,
    color: const Color(0xFF121118),
  ),
  'adobe-commerce' => (
    icon: null,
    asset: 'assets/brands/magento.svg',
    color: const Color(0xFFEE672F),
  ),
  'wix-ecommerce' => (
    icon: SimpleIcons.wix,
    asset: null,
    color: const Color(0xFF0C0C0C),
  ),
  'squarespace-commerce' => (
    icon: SimpleIcons.squarespace,
    asset: null,
    color: const Color(0xFF222222),
  ),
  'prestashop' => (
    icon: SimpleIcons.prestashop,
    asset: null,
    color: const Color(0xFF24B9D7),
  ),
  'ecwid' => (
    icon: null,
    asset: 'assets/brands/ecwid.svg',
    color: const Color(0xFF446CE4),
  ),
  'shopware' => (
    icon: SimpleIcons.shopware,
    asset: null,
    color: const Color(0xFF189EFF),
  ),
  'salesforce-commerce-cloud' => (
    icon: null,
    asset: 'assets/brands/salesforce.svg',
    color: const Color(0xFF00A1E0),
  ),
  'commercetools' => (
    icon: null,
    asset: 'assets/brands/commercetools.svg',
    color: const Color(0xFF6359FF),
  ),
  'vtex' => (
    icon: SimpleIcons.vtex,
    asset: null,
    color: const Color(0xFFF71963),
  ),
  'etsy' => (
    icon: SimpleIcons.etsy,
    asset: null,
    color: const Color(0xFFF1641E),
  ),
  _ => (
    icon: Icons.storefront_outlined,
    asset: null,
    color: const Color(0xFF64748B),
  ),
};
