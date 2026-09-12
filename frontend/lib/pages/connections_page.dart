import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/file_picker/app_file_picker.dart';
import 'package:avenqo/features/connectors/connector_hub.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/widgets/avenqo_data_table.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:url_launcher/url_launcher.dart';

// Ré-export pour compatibilité : les tests et consommateurs existants
// importent `PickedFile` depuis cette page.
export 'package:avenqo/core/file_picker/picked_file.dart' show PickedFile;

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const green = Color(0xFF1B9E5A);
  static const red = Color(0xFFD1414B);
}

const _defaultModuleCode = 'retail';

enum _ViewState { loading, idle, selecting, uploading, summary, error }

typedef FilePickerFn = Future<List<PickedFile>> Function();
typedef ConnectorUrlLauncher = Future<bool> Function(Uri uri);

Future<bool> _openConnectorUrl(Uri uri) => launchUrl(uri);

/// Centre de gestion des données Avenqo (remplace le placeholder générique).
/// Réutilise exclusivement les endpoints existants (`/datasets`,
/// `/datasets/upload`, `/datasets/{id}/profile`, `/datasets/{id}/mapping`).
class ConnectionsPage extends StatefulWidget {
  const ConnectionsPage({
    super.key,
    required this.api,
    this.pickFiles = pickDataFiles,
    this.pollInterval = const Duration(seconds: 3),
    this.openConnectorUrl = _openConnectorUrl,
  });
  final ApiClient api;
  final FilePickerFn pickFiles;
  final Duration pollInterval;
  final ConnectorUrlLauncher openConnectorUrl;

  @override
  State<ConnectionsPage> createState() => _ConnectionsPageState();
}

class _ConnectionsPageState extends State<ConnectionsPage> {
  _ViewState _state = _ViewState.loading;
  List<Map<String, dynamic>> _datasets = [];
  List<Map<String, dynamic>> _connectorCatalog = [];
  List<Map<String, dynamic>> _commerceConnections = [];
  bool _connectorCatalogUnavailable = false;
  String? _authorizingProvider;
  final Set<String> _busyConnectionIds = <String>{};
  String? _errorMessage;
  String? _duplicateNotice;
  final List<_PendingFile> _pending = [];
  List<_UploadItem> _uploadItems = [];
  final Set<String> _deletingDatasetIds = <String>{};
  final Set<String> _selectedDatasetIds = <String>{};
  Timer? _pollTimer;
  bool _refreshing = false;

  @override
  void initState() {
    super.initState();
    _loadDatasets();
  }

  Future<void> _loadDatasets() async {
    setState(() => _state = _ViewState.loading);
    final connectorFuture = _fetchConnectorData();
    try {
      try {
        await widget.api.post('/datasets/reconcile');
      } on ApiException {
        // Listing remains available if reconciliation is temporarily unavailable.
      }
      final datasets = await widget.api.get('/datasets') as List<dynamic>;
      final connectorData = await connectorFuture;
      setState(() {
        _datasets = datasets.cast<Map<String, dynamic>>();
        _connectorCatalog = connectorData.catalog;
        _commerceConnections = connectorData.connections;
        _connectorCatalogUnavailable = connectorData.unavailable;
        _state = _ViewState.idle;
      });
      _syncPolling();
    } on ApiException catch (exc) {
      setState(() {
        _errorMessage = exc.isTimeout
            ? AvenqoLocaleScope.translationsOf(
                context,
              ).company.connectionsGenericError
            : exc.message;
        _state = _ViewState.error;
      });
    } on Object {
      setState(() {
        _errorMessage = AvenqoLocaleScope.translationsOf(
          context,
        ).company.connectionsGenericError;
        _state = _ViewState.error;
      });
    }
  }

  Future<_ConnectorData> _fetchConnectorData() async {
    final responses = await Future.wait<dynamic>([
      _safeConnectorGet('/connectors'),
      _safeConnectorGet('/connectors/connections'),
    ]);
    final catalog = _mapsFrom(responses[0])
        .where(
          (item) => item['provider'] != null && item['customer_status'] != null,
        )
        .toList(growable: false);
    final connections = _mapsFrom(responses[1])
        .where(
          (item) => item['id'] != null && item['external_account_id'] != null,
        )
        .toList(growable: false);
    return _ConnectorData(
      catalog: catalog,
      connections: connections,
      unavailable: responses.any((response) => response == null),
    );
  }

  Future<dynamic> _safeConnectorGet(String path) async {
    try {
      return await widget.api.get(path);
    } on Object {
      return null;
    }
  }

  Future<void> _refreshConnectorData() async {
    final connectorData = await _fetchConnectorData();
    if (!mounted) return;
    setState(() {
      _connectorCatalog = connectorData.catalog;
      _commerceConnections = connectorData.connections;
      _connectorCatalogUnavailable = connectorData.unavailable;
    });
    _syncPolling();
  }

  /// Rafraîchit la liste des jeux de données sans changer l'écran affiché
  /// (utilisé après un import pour ne pas écraser le résumé de succès).
  Future<void> _refreshDatasetsInBackground() async {
    if (_refreshing) return;
    _refreshing = true;
    try {
      final datasets = await widget.api.get('/datasets') as List<dynamic>;
      if (mounted) {
        setState(() => _datasets = datasets.cast<Map<String, dynamic>>());
        if (_commerceConnections.any(_connectionIsBusy)) {
          await _refreshConnectorData();
        }
        _syncPolling();
      }
    } on ApiException {
      // Le résumé d'import reste affiché ; la liste sera retentée à la prochaine visite de l'écran.
    } finally {
      _refreshing = false;
    }
  }

  void _syncPolling() {
    final shouldPoll =
        _datasets.any((dataset) {
          final pipelineStatus = dataset['pipeline_status']?.toString();
          final trainingStatus = dataset['training_status']?.toString();
          return pipelineStatus == 'analyzing' ||
              trainingStatus == 'preparing_data' ||
              trainingStatus == 'training_ai';
        }) ||
        _commerceConnections.any(_connectionIsBusy);
    if (!shouldPoll) {
      _pollTimer?.cancel();
      _pollTimer = null;
      return;
    }
    _pollTimer ??= Timer.periodic(
      widget.pollInterval,
      (_) => _refreshDatasetsInBackground(),
    );
  }

  bool _connectionIsBusy(Map<String, dynamic> connection) {
    final status = connection['status']?.toString().toUpperCase();
    return status == 'SYNCING' ||
        status == 'PROCESSING' ||
        status == 'CONNECTING';
  }

  String _connectorText(String key) {
    final t = AvenqoLocaleScope.translationsOf(context).company;
    return t.connectorHub[key] ??
        CompanyStrings.fallback().connectorHub[key] ??
        key;
  }

  Future<void> _connectShopify() async {
    var shopValue = '';
    final shop = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(_connectorText('shopDomainTitle')),
        content: TextFormField(
          key: const ValueKey('shopify-domain'),
          autofocus: true,
          keyboardType: TextInputType.url,
          decoration: InputDecoration(
            hintText: _connectorText('shopDomainHint'),
          ),
          onChanged: (value) => shopValue = value.trim(),
          onFieldSubmitted: (value) =>
              Navigator.of(dialogContext).pop(value.trim()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: Text(_connectorText('cancel')),
          ),
          FilledButton.icon(
            key: const ValueKey('authorize-shopify'),
            onPressed: () => Navigator.of(dialogContext).pop(shopValue),
            icon: const Icon(Icons.open_in_new, size: 18),
            label: Text(_connectorText('authorize')),
          ),
        ],
      ),
    );
    if (shop == null || shop.isEmpty || !mounted) return;
    setState(() => _authorizingProvider = 'shopify');
    try {
      final response =
          await widget.api.post(
                '/connectors/shopify/authorize',
                body: {'shop_domain': shop},
              )
              as Map<String, dynamic>;
      final authorizationUrl = Uri.tryParse(
        response['authorization_url']?.toString() ?? '',
      );
      if (authorizationUrl == null ||
          !authorizationUrl.hasScheme ||
          !await widget.openConnectorUrl(authorizationUrl)) {
        throw ApiException(_connectorText('launchFailed'));
      }
    } on ApiException catch (error) {
      _showConnectorError(error.message);
    } on Object {
      _showConnectorError(_connectorText('launchFailed'));
    } finally {
      if (mounted) setState(() => _authorizingProvider = null);
    }
  }

  void _connectProvider(String provider) {
    if (provider == 'shopify') {
      _connectShopify();
    } else if (provider == 'woocommerce') {
      _connectWooCommerce();
    }
  }

  Future<void> _connectWooCommerce() async {
    var storeUrl = '';
    var consumerKey = '';
    var consumerSecret = '';
    var manual = false;
    final request = await showDialog<_WooCommerceConnectionRequest>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(_connectorText('wooTitle')),
          content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    key: const ValueKey('woocommerce-store-url'),
                    autofocus: true,
                    keyboardType: TextInputType.url,
                    decoration: InputDecoration(
                      labelText: _connectorText('wooStoreUrl'),
                      hintText: _connectorText('wooStoreUrlHint'),
                    ),
                    onChanged: (value) => storeUrl = value.trim(),
                  ),
                  const SizedBox(height: 12),
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: Text(_connectorText('wooManualMode')),
                    subtitle: Text(_connectorText('wooManualDescription')),
                    value: manual,
                    onChanged: (value) => setDialogState(() => manual = value),
                  ),
                  if (manual) ...[
                    const SizedBox(height: 8),
                    TextField(
                      key: const ValueKey('woocommerce-consumer-key'),
                      autocorrect: false,
                      enableSuggestions: false,
                      obscureText: true,
                      decoration: InputDecoration(
                        labelText: _connectorText('wooConsumerKey'),
                      ),
                      onChanged: (value) => consumerKey = value.trim(),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      key: const ValueKey('woocommerce-consumer-secret'),
                      autocorrect: false,
                      enableSuggestions: false,
                      obscureText: true,
                      decoration: InputDecoration(
                        labelText: _connectorText('wooConsumerSecret'),
                      ),
                      onChanged: (value) => consumerSecret = value.trim(),
                    ),
                  ],
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(_connectorText('cancel')),
            ),
            FilledButton.icon(
              key: const ValueKey('authorize-woocommerce'),
              onPressed: () => Navigator.of(dialogContext).pop(
                _WooCommerceConnectionRequest(
                  storeUrl: storeUrl,
                  consumerKey: manual ? consumerKey : null,
                  consumerSecret: manual ? consumerSecret : null,
                ),
              ),
              icon: Icon(manual ? Icons.key : Icons.open_in_new, size: 18),
              label: Text(
                _connectorText(manual ? 'wooConnectManual' : 'wooAuthorize'),
              ),
            ),
          ],
        ),
      ),
    );
    if (request == null || request.storeUrl.isEmpty || !mounted) return;
    if (request.isManual &&
        ((request.consumerKey?.isEmpty ?? true) ||
            (request.consumerSecret?.isEmpty ?? true))) {
      _showConnectorError(_connectorText('wooCredentialsRequired'));
      return;
    }
    setState(() => _authorizingProvider = 'woocommerce');
    try {
      if (request.isManual) {
        await widget.api.post(
          '/connectors/woocommerce/manual',
          body: {
            'store_url': request.storeUrl,
            'consumer_key': request.consumerKey,
            'consumer_secret': request.consumerSecret,
          },
        );
        await _refreshConnectorData();
      } else {
        final response =
            await widget.api.post(
                  '/connectors/woocommerce/authorize',
                  body: {'store_url': request.storeUrl},
                )
                as Map<String, dynamic>;
        final authorizationUrl = Uri.tryParse(
          response['authorization_url']?.toString() ?? '',
        );
        if (authorizationUrl == null ||
            !authorizationUrl.hasScheme ||
            !await widget.openConnectorUrl(authorizationUrl)) {
          throw ApiException(_connectorText('wooLaunchFailed'));
        }
      }
    } on ApiException catch (error) {
      _showConnectorError(error.message);
    } on Object {
      _showConnectorError(_connectorText('wooLaunchFailed'));
    } finally {
      if (mounted) setState(() => _authorizingProvider = null);
    }
  }

  Future<void> _syncConnection(Map<String, dynamic> connection) async {
    final id = connection['id']?.toString();
    if (id == null || _busyConnectionIds.contains(id)) return;
    setState(() => _busyConnectionIds.add(id));
    try {
      await widget.api.post('/connectors/connections/$id/sync');
      if (!mounted) return;
      setState(() {
        final index = _commerceConnections.indexWhere(
          (item) => item['id']?.toString() == id,
        );
        if (index >= 0) {
          _commerceConnections[index] = {
            ..._commerceConnections[index],
            'status': 'SYNCING',
            'sync_status': 'SYNCING',
          };
        }
      });
      _syncPolling();
    } on ApiException catch (error) {
      _showConnectorError(error.message);
    } finally {
      if (mounted) setState(() => _busyConnectionIds.remove(id));
    }
  }

  Future<void> _reauthorizeWooCommerce(Map<String, dynamic> connection) async {
    final id = connection['id']?.toString();
    if (id == null || _busyConnectionIds.contains(id)) return;
    setState(() => _busyConnectionIds.add(id));
    try {
      final response =
          await widget.api.post('/connectors/connections/$id/reauthorize')
              as Map<String, dynamic>;
      final authorizationUrl = Uri.tryParse(
        response['authorization_url']?.toString() ?? '',
      );
      if (authorizationUrl == null ||
          !authorizationUrl.hasScheme ||
          !await widget.openConnectorUrl(authorizationUrl)) {
        throw ApiException(_connectorText('wooLaunchFailed'));
      }
    } on ApiException catch (error) {
      _showConnectorError(error.message);
    } on Object {
      _showConnectorError(_connectorText('wooLaunchFailed'));
    } finally {
      if (mounted) setState(() => _busyConnectionIds.remove(id));
    }
  }

  Future<void> _disconnectConnection(Map<String, dynamic> connection) async {
    final id = connection['id']?.toString();
    if (id == null || _busyConnectionIds.contains(id)) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(_connectorText('disconnect')),
        content: Text(_connectorText('disconnectConfirm')),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(_connectorText('cancel')),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: FilledButton.styleFrom(backgroundColor: _Brand.red),
            icon: const Icon(Icons.link_off, size: 18),
            label: Text(_connectorText('disconnect')),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _busyConnectionIds.add(id));
    try {
      final response =
          await widget.api.post('/connectors/connections/$id/disconnect')
              as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        final index = _commerceConnections.indexWhere(
          (item) => item['id']?.toString() == id,
        );
        if (index >= 0) _commerceConnections[index] = response;
      });
    } on ApiException catch (error) {
      _showConnectorError(error.message);
    } finally {
      if (mounted) setState(() => _busyConnectionIds.remove(id));
    }
  }

  void _showConnectorError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(
      context,
    )?.showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  /// Ouvre le sélecteur natif en mode multi-sélection : l'utilisateur peut
  /// choisir plusieurs fichiers en une seule fois. Les fichiers déjà présents
  /// dans la sélection en attente (même nom + même taille) ne sont pas
  /// ajoutés une seconde fois.
  Future<void> _addFiles() async {
    final picked = await widget.pickFiles();
    if (picked.isEmpty) return;

    var duplicateFound = false;
    for (final file in picked) {
      if (file.bytes.isEmpty) continue;
      final isDuplicate = _pending.any(
        (p) => p.fileName == file.name && p.bytes.length == file.bytes.length,
      );
      if (isDuplicate) {
        duplicateFound = true;
        continue;
      }
      _pending.add(_PendingFile(fileName: file.name, bytes: file.bytes));
    }
    if (_pending.isEmpty) {
      setState(() {
        _errorMessage = AvenqoLocaleScope.translationsOf(
          context,
        ).company.connectionsFileEmptyError;
        _state = _ViewState.error;
      });
      return;
    }
    setState(() {
      _duplicateNotice = duplicateFound
          ? AvenqoLocaleScope.translationsOf(
              context,
            ).company.connectionsDuplicateFileNotice
          : null;
      _state = _ViewState.selecting;
    });
  }

  void _removePending(_PendingFile file) {
    setState(() => _pending.remove(file));
  }

  Future<void> _uploadPending() async {
    final files = List<_PendingFile>.from(_pending);
    setState(() {
      _pending.clear();
      _duplicateNotice = null;
      _uploadItems = [
        for (final file in files)
          _UploadItem(fileName: file.fileName, fileSize: file.bytes.length),
      ];
      _state = _ViewState.uploading;
    });

    for (var i = 0; i < files.length; i++) {
      final file = files[i];
      try {
        final response =
            await widget.api.postMultipart(
                  '/datasets/upload',
                  fields: const {'module_code': _defaultModuleCode},
                  fileBytes: file.bytes,
                  fileName: file.fileName,
                  onProgress: (sent, total) {
                    if (total > 0 && mounted) {
                      setState(() => _uploadItems[i].progress = sent / total);
                    }
                  },
                )
                as Map<String, dynamic>;
        final datasetId = response['dataset_id']?.toString();
        if (mounted) {
          setState(() {
            _uploadItems[i].progress = 1;
            _uploadItems[i].done = true;
            _uploadItems[i].datasetId = datasetId;
          });
        }
      } on ApiException catch (exc) {
        if (mounted) {
          setState(() => _uploadItems[i].error = exc.message);
        }
      }
    }

    if (mounted) setState(() => _state = _ViewState.summary);
    await _refreshDatasetsInBackground();
  }

  Future<void> _deleteDatasets(List<String> datasetIds) async {
    if (datasetIds.isEmpty || datasetIds.any(_deletingDatasetIds.contains)) {
      return;
    }
    setState(() => _deletingDatasetIds.addAll(datasetIds));
    try {
      await widget.api.post(
        '/datasets/delete-selection',
        body: {'dataset_ids': datasetIds},
      );
      final datasets = await widget.api.get('/datasets') as List<dynamic>;
      final connectorData = await _fetchConnectorData();
      if (!mounted) return;
      setState(() {
        _datasets = datasets.cast<Map<String, dynamic>>();
        _commerceConnections = connectorData.connections;
        _connectorCatalog = connectorData.catalog;
        _connectorCatalogUnavailable = connectorData.unavailable;
        _deletingDatasetIds.removeAll(datasetIds);
        _selectedDatasetIds.removeAll(datasetIds);
      });
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(
          content: Text(
            AvenqoLocaleScope.translationsOf(
              context,
            ).company.connectionsDeleteSuccess,
          ),
        ),
      );
    } on Object {
      if (!mounted) return;
      setState(() => _deletingDatasetIds.removeAll(datasetIds));
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(
          content: Text(
            AvenqoLocaleScope.translationsOf(
              context,
            ).company.connectionsDeleteFailure,
          ),
        ),
      );
    }
  }

  void _showCleaningDetails(Map<String, dynamic> dataset) {
    final id = dataset['id']?.toString();
    if (id == null) return;
    showDialog<void>(
      context: context,
      builder: (_) => _DatasetCleaningDialog(
        api: widget.api,
        datasetId: id,
        t: AvenqoLocaleScope.translationsOf(context).company,
      ),
    );
  }

  Future<void> _showMappingDetails(Map<String, dynamic> dataset) async {
    final id = dataset['id']?.toString();
    if (id == null) return;
    final promoted = await showDialog<bool>(
      context: context,
      builder: (_) => _DatasetMappingDialog(
        api: widget.api,
        datasetId: id,
        t: AvenqoLocaleScope.translationsOf(context).company,
      ),
    );
    if (promoted == true && mounted) {
      await _loadDatasets();
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final t = AvenqoLocaleScope.translationsOf(context).company;
    return Container(
      color: colors.canvas,
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1120),
            child: switch (_state) {
              _ViewState.loading => _CenteredSpinner(
                label: t.connectionsLoading,
              ),
              _ViewState.idle => _ConnectedDataView(
                datasets: _datasets,
                connectorCatalog: _connectorCatalog,
                commerceConnections: _commerceConnections,
                busyConnectionIds: _busyConnectionIds,
                authorizingProvider: _authorizingProvider,
                connectorCatalogUnavailable: _connectorCatalogUnavailable,
                onConnect: _connectProvider,
                onSyncConnection: _syncConnection,
                onReauthorizeConnection: _reauthorizeWooCommerce,
                onDisconnectConnection: _disconnectConnection,
                onRefreshConnectors: _refreshConnectorData,
                deletingDatasetIds: _deletingDatasetIds,
                selectedDatasetIds: _selectedDatasetIds,
                onSelectionChanged: (datasetId, selected) => setState(() {
                  if (selected) {
                    _selectedDatasetIds.add(datasetId);
                  } else {
                    _selectedDatasetIds.remove(datasetId);
                  }
                }),
                onAddFiles: _addFiles,
                onDeleteDatasets: _deleteDatasets,
                onViewCleaning: _showCleaningDetails,
                onReviewMapping: _showMappingDetails,
                onGoToDashboard: () => context.go('/dashboard'),
                onAskAvenqo: () => context.go('/assistant'),
                t: t,
              ),
              _ViewState.selecting => _SelectingView(
                pending: _pending,
                duplicateNotice: _duplicateNotice,
                onAddMore: _addFiles,
                onRemove: _removePending,
                onUpload: _uploadPending,
                t: t,
              ),
              _ViewState.uploading => _UploadingView(items: _uploadItems, t: t),
              _ViewState.summary => _SummaryView(
                items: _uploadItems,
                onContinue: () => setState(() => _state = _ViewState.idle),
                onGoToDashboard: () => context.go('/dashboard'),
                onAskAvenqo: () => context.go('/assistant'),
                onAddFiles: _addFiles,
                t: t,
              ),
              _ViewState.error => _ErrorView(
                message: _errorMessage ?? t.connectionsGenericError,
                onRetry: _loadDatasets,
                retryLabel: t.connectionsRetry,
              ),
            },
          ),
        ],
      ),
    );
  }
}

class _CenteredSpinner extends StatelessWidget {
  const _CenteredSpinner({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 80),
      child: Column(
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(label, style: TextStyle(color: colors.muted)),
        ],
      ),
    );
  }
}

String _formatSize(int bytes) {
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} Ko';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} Mo';
}

String _pluralize(int n, String one, String other) {
  final template = n == 1 ? one : other;
  return template.replaceAll('{n}', '$n');
}

String _cleaningText(CompanyStrings t, String key) =>
    t.connectionsCleaning[key] ??
    CompanyStrings.fallback().connectionsCleaning[key] ??
    key.replaceAll('_', ' ');

String _humanizeCode(String value) {
  if (value.isEmpty) return '—';
  final normalized = value.replaceAll('_', ' ');
  return normalized[0].toUpperCase() + normalized.substring(1);
}

String? _trainingStatusLabel(CompanyStrings t, String? status) =>
    switch (status) {
      'preparing_data' => t.connectionsPreparingData,
      'training_ai' => t.connectionsTrainingAi,
      'training_failed' => _cleaningText(t, 'trainingFailed'),
      _ => null,
    };

Color _trainingStatusColor(String? status) => switch (status) {
  'training_failed' => _Brand.red,
  _ => _Brand.blue,
};

class _PendingFile {
  _PendingFile({required this.fileName, required this.bytes});
  final String fileName;
  final Uint8List bytes;
}

class _UploadItem {
  _UploadItem({required this.fileName, required this.fileSize});
  final String fileName;
  final int fileSize;
  double progress = 0;
  bool done = false;
  String? datasetId;
  String? error;
}

class _ConnectorData {
  const _ConnectorData({
    required this.catalog,
    required this.connections,
    required this.unavailable,
  });

  final List<Map<String, dynamic>> catalog;
  final List<Map<String, dynamic>> connections;
  final bool unavailable;
}

class _WooCommerceConnectionRequest {
  const _WooCommerceConnectionRequest({
    required this.storeUrl,
    this.consumerKey,
    this.consumerSecret,
  });

  final String storeUrl;
  final String? consumerKey;
  final String? consumerSecret;

  bool get isManual => consumerKey != null || consumerSecret != null;
}

List<Map<String, dynamic>> _mapsFrom(dynamic value) {
  if (value is! List) return [];
  return value
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList(growable: false);
}

/// Panneau principal : import + dropdown de TOUS les datasets du tenant,
/// quel que soit leur statut. Chaque ligne reste supprimable indépendamment.
class _ConnectedDataView extends StatelessWidget {
  const _ConnectedDataView({
    required this.datasets,
    required this.connectorCatalog,
    required this.commerceConnections,
    required this.busyConnectionIds,
    required this.authorizingProvider,
    required this.connectorCatalogUnavailable,
    required this.onConnect,
    required this.onSyncConnection,
    required this.onReauthorizeConnection,
    required this.onDisconnectConnection,
    required this.onRefreshConnectors,
    required this.deletingDatasetIds,
    required this.selectedDatasetIds,
    required this.onSelectionChanged,
    required this.onAddFiles,
    required this.onDeleteDatasets,
    required this.onViewCleaning,
    required this.onReviewMapping,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.t,
  });

  final List<Map<String, dynamic>> datasets;
  final List<Map<String, dynamic>> connectorCatalog;
  final List<Map<String, dynamic>> commerceConnections;
  final Set<String> busyConnectionIds;
  final String? authorizingProvider;
  final bool connectorCatalogUnavailable;
  final ValueChanged<String> onConnect;
  final Future<void> Function(Map<String, dynamic> connection) onSyncConnection;
  final Future<void> Function(Map<String, dynamic> connection)
  onReauthorizeConnection;
  final Future<void> Function(Map<String, dynamic> connection)
  onDisconnectConnection;
  final VoidCallback onRefreshConnectors;
  final Set<String> deletingDatasetIds;
  final Set<String> selectedDatasetIds;
  final void Function(String datasetId, bool selected) onSelectionChanged;
  final VoidCallback onAddFiles;
  final Future<void> Function(List<String> datasetIds) onDeleteDatasets;
  final void Function(Map<String, dynamic> dataset) onViewCleaning;
  final void Function(Map<String, dynamic> dataset) onReviewMapping;
  final VoidCallback onGoToDashboard;
  final VoidCallback onAskAvenqo;
  final CompanyStrings t;

  Future<void> _confirmDelete(
    BuildContext context,
    List<Map<String, dynamic>> selected,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t.connectionsDeleteTitle),
        content: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(t.connectionsDeleteWarning),
              const SizedBox(height: 16),
              for (final dataset in selected.take(5))
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text('• ${dataset['name'] ?? '—'}'),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(t.connectionsDeleteCancel),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: FilledButton.styleFrom(backgroundColor: _Brand.red),
            icon: const Icon(Icons.delete_outline, size: 18),
            label: Text(t.connectionsDeletePermanently),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await onDeleteDatasets(
      selected
          .map((dataset) => dataset['id']?.toString())
          .whereType<String>()
          .toList(growable: false),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(32),
          decoration: BoxDecoration(
            color: colors.surface,
            border: Border.all(color: colors.line),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  color: _Brand.blue.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(
                  Icons.cloud_upload_outlined,
                  color: _Brand.blue,
                  size: 28,
                ),
              ),
              const SizedBox(height: 18),
              Text(
                t.connectionsNoDataTitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: colors.ink,
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                t.connectionsNoDataFormats,
                style: TextStyle(color: colors.muted),
              ),
              const SizedBox(height: 22),
              FilledButton.icon(
                onPressed: onAddFiles,
                style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
                icon: const Icon(Icons.upload_file, size: 18),
                label: Text(t.connectionsAddFiles),
              ),
            ],
          ),
        ),
        if (datasets.isNotEmpty) ...[
          const SizedBox(height: 20),
          Material(
            color: colors.surface,
            shape: RoundedRectangleBorder(
              side: BorderSide(color: colors.line),
              borderRadius: BorderRadius.circular(12),
            ),
            clipBehavior: Clip.antiAlias,
            child: ExpansionTile(
              key: const PageStorageKey<String>('connected-datasets-dropdown'),
              initiallyExpanded: false,
              tilePadding: const EdgeInsets.symmetric(
                horizontal: 20,
                vertical: 6,
              ),
              childrenPadding: EdgeInsets.zero,
              leading: Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: _Brand.blue.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(
                  Icons.folder_copy_outlined,
                  color: _Brand.blue,
                  size: 20,
                ),
              ),
              title: Text(
                t.connectionsConnectedDataTitle,
                style: TextStyle(
                  color: colors.ink,
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                ),
              ),
              subtitle: Text(
                '${datasets.length}',
                style: TextStyle(color: colors.muted, fontSize: 12),
              ),
              children: [
                Divider(height: 1, color: colors.line),
                if (selectedDatasetIds.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 4),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            t.connectionsSelectedCount.replaceFirst(
                              '{n}',
                              '${selectedDatasetIds.length}',
                            ),
                          ),
                        ),
                        FilledButton.icon(
                          onPressed: deletingDatasetIds.isNotEmpty
                              ? null
                              : () => _confirmDelete(
                                  context,
                                  datasets
                                      .where(
                                        (dataset) =>
                                            selectedDatasetIds.contains(
                                              dataset['id']?.toString(),
                                            ),
                                      )
                                      .toList(growable: false),
                                ),
                          style: FilledButton.styleFrom(
                            backgroundColor: _Brand.red,
                          ),
                          icon: const Icon(Icons.delete_outline, size: 18),
                          label: Text(t.connectionsDeleteSelected),
                        ),
                      ],
                    ),
                  ),
                for (var i = 0; i < datasets.length; i++)
                  _DatasetRow(
                    dataset: datasets[i],
                    sourceConnection: commerceConnections
                        .cast<Map<String, dynamic>?>()
                        .firstWhere(
                          (connection) =>
                              connection?['dataset_id']?.toString() ==
                              datasets[i]['id']?.toString(),
                          orElse: () => null,
                        ),
                    isLast: i == datasets.length - 1,
                    isDeleting: deletingDatasetIds.contains(
                      datasets[i]['id']?.toString(),
                    ),
                    isSelected: selectedDatasetIds.contains(
                      datasets[i]['id']?.toString(),
                    ),
                    onSelectionChanged: onSelectionChanged,
                    onDeleteDataset: (dataset) =>
                        _confirmDelete(context, [dataset]),
                    onViewCleaning: onViewCleaning,
                    onReviewMapping: onReviewMapping,
                    onGoToDashboard: onGoToDashboard,
                    onAskAvenqo: onAskAvenqo,
                    t: t,
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 32),
        ConnectorHub(
          catalog: connectorCatalog,
          connections: commerceConnections,
          busyConnectionIds: busyConnectionIds,
          authorizingProvider: authorizingProvider,
          catalogUnavailable: connectorCatalogUnavailable,
          onConnect: onConnect,
          onSync: onSyncConnection,
          onReauthorize: onReauthorizeConnection,
          onDisconnect: onDisconnectConnection,
          onRefresh: onRefreshConnectors,
          t: t,
        ),
      ],
    );
  }
}

class _DatasetRow extends StatelessWidget {
  const _DatasetRow({
    required this.dataset,
    required this.sourceConnection,
    required this.isLast,
    required this.isDeleting,
    required this.isSelected,
    required this.onSelectionChanged,
    required this.onDeleteDataset,
    required this.onViewCleaning,
    required this.onReviewMapping,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.t,
  });

  final Map<String, dynamic> dataset;
  final Map<String, dynamic>? sourceConnection;
  final bool isLast;
  final bool isDeleting;
  final bool isSelected;
  final void Function(String datasetId, bool selected) onSelectionChanged;
  final Future<void> Function(Map<String, dynamic> dataset) onDeleteDataset;
  final void Function(Map<String, dynamic> dataset) onViewCleaning;
  final void Function(Map<String, dynamic> dataset) onReviewMapping;
  final VoidCallback onGoToDashboard;
  final VoidCallback onAskAvenqo;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final status =
        dataset['pipeline_status']?.toString() ?? dataset['status']?.toString();
    final trainingStatus = dataset['training_status']?.toString();
    final trainingLabel = _trainingStatusLabel(t, trainingStatus);
    final id = dataset['id']?.toString();
    final isReady = status == 'ready' || status == 'validated' || status == 'attention_required';
    final needsAttention = false;
    final isError =
        status == 'failed' || status == 'invalid' || status == 'rejected';
    final statusLabel = switch (status) {
      'ready' || 'validated' || 'attention_required' => t.connectionsReadyTitle,
      'preparing_data' => t.connectionsPreparingData,
      'training_ai' => t.connectionsTrainingAi,
      'failed' || 'invalid' || 'rejected' => t.connectionsProcessingError,
      _ => t.connectionsAnalyzing,
    };
    final sourceName = sourceConnection?['display_name']?.toString();
    final sourceDate =
        sourceConnection?['last_successful_sync'] ?? dataset['uploaded_at'];
    final metadata = [
      sourceConnection == null
          ? t.connectionsUploadedSource
          : [
              t.connectionsSynchronizedSource,
              sourceConnection?['provider']?.toString().toUpperCase(),
              if (sourceName != null && sourceName.isNotEmpty) sourceName,
            ].whereType<String>().join(' · '),
      if (dataset['rows_count'] != null)
        '${dataset['rows_count']} ${t.connectionsStatRowsLabel.toLowerCase()}',
      if (dataset['columns_count'] != null)
        '${dataset['columns_count']} ${t.connectionsStatColumnsLabel.toLowerCase()}',
      if (sourceDate != null)
        '${t.connectionsImportedAtLabel} ${sourceDate.toString().split('T').first}',
    ].join(' · ');
    final actions = <Widget>[
      if (isReady || isError)
        TextButton.icon(
          onPressed: isDeleting ? null : () => onViewCleaning(dataset),
          icon: const Icon(Icons.table_view_outlined, size: 18),
          label: Text(_cleaningText(t, 'view')),
        ),
      if (isReady)
        IconButton(
          tooltip: 'Correspondance des colonnes',
          onPressed: isDeleting ? null : () => onReviewMapping(dataset),
          icon: const Icon(Icons.tune),
        ),
      if (isReady)
        IconButton(
          tooltip: t.connectionsGoDashboard,
          onPressed: isDeleting ? null : onGoToDashboard,
          icon: const Icon(Icons.dashboard_outlined),
        ),
      if (isReady)
        IconButton(
          tooltip: t.connectionsAskAvenqo,
          onPressed: isDeleting ? null : onAskAvenqo,
          icon: const Icon(Icons.smart_toy_outlined),
        ),
      if (id != null)
        isDeleting
            ? const SizedBox(
                width: 40,
                height: 40,
                child: Padding(
                  padding: EdgeInsets.all(10),
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              )
            : IconButton(
                tooltip: t.connectionsDeleteData,
                onPressed: () => onDeleteDataset(dataset),
                icon: const Icon(Icons.delete_outline, color: _Brand.red),
              ),
    ];

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        border: isLast ? null : Border(bottom: BorderSide(color: colors.line)),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 760;
          final titleBlock = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                dataset['name']?.toString() ?? '—',
                style: TextStyle(
                  color: colors.ink,
                  fontWeight: FontWeight.w700,
                ),
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Text(
                statusLabel,
                style: TextStyle(
                  color: isError
                      ? _Brand.red
                      : (isReady ? _Brand.green : _Brand.blue),
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (trainingLabel != null) ...[
                const SizedBox(height: 2),
                Text(
                  trainingLabel,
                  style: TextStyle(
                    color: _trainingStatusColor(trainingStatus),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
              if (metadata.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  metadata,
                  style: TextStyle(color: colors.muted, fontSize: 12),
                ),
              ],
            ],
          );
          final leadingIcon = Icon(
            isError
                ? Icons.error_outline
                : isReady
                ? Icons.check_circle
                : Icons.hourglass_top,
            color: isError
                ? _Brand.red
                : (isReady ? _Brand.green : _Brand.blue),
          );
          final actionBar = Wrap(
            spacing: 4,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            alignment: compact ? WrapAlignment.start : WrapAlignment.end,
            children: actions,
          );

          if (compact) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Checkbox(
                      value: isSelected,
                      onChanged: isDeleting || id == null
                          ? null
                          : (value) => onSelectionChanged(id, value ?? false),
                    ),
                    leadingIcon,
                    const SizedBox(width: 12),
                    Expanded(child: titleBlock),
                  ],
                ),
                if (actions.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  actionBar,
                ],
              ],
            );
          }

          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Checkbox(
                value: isSelected,
                onChanged: isDeleting || id == null
                    ? null
                    : (value) => onSelectionChanged(id, value ?? false),
              ),
              leadingIcon,
              const SizedBox(width: 12),
              Expanded(child: titleBlock),
              if (actions.isNotEmpty) ...[
                const SizedBox(width: 12),
                Flexible(child: actionBar),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _DatasetMappingDialog extends StatefulWidget {
  const _DatasetMappingDialog({
    required this.api,
    required this.datasetId,
    required this.t,
  });

  final ApiClient api;
  final String datasetId;
  final CompanyStrings t;

  @override
  State<_DatasetMappingDialog> createState() => _DatasetMappingDialogState();
}

class _DatasetMappingDialogState extends State<_DatasetMappingDialog> {
  late final Future<Map<String, dynamic>> _profile = _load();
  final Map<String, String?> _selected = {};
  bool _initialized = false;
  bool _submitting = false;
  bool _hasChanges = false;
  bool _showAdvanced = false;
  String? _error;

  Future<Map<String, dynamic>> _load() async =>
      await widget.api.get('/datasets/${widget.datasetId}/profile')
          as Map<String, dynamic>;

  void _initialize(Map<String, dynamic> profile) {
    if (_initialized) return;
    final accepted =
        (profile['accepted_mapping'] as Map<String, dynamic>? ?? const {});
    final conflicts =
        (profile['required_confirmation'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();
    final conflictingColumns = {
      for (final conflict in conflicts)
        for (final column
            in (conflict['columns'] as List<dynamic>? ?? const []))
          column.toString(),
    };
    for (final suggestion
        in (profile['mapping_suggestions'] as List<dynamic>? ?? const [])) {
      final item = suggestion as Map<String, dynamic>;
      final column = item['original_column'].toString();
      _selected[column] = conflictingColumns.contains(column)
          ? null
          : (accepted[column]?.toString() ?? item['suggested_field']?.toString());
    }
    _initialized = true;
  }

  Future<void> _submit() async {
    if (_submitting) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final mapping = {
        for (final entry in _selected.entries)
          if (entry.value != null) entry.key: entry.value!,
      };
      final response =
          await widget.api.post(
                '/datasets/${widget.datasetId}/mapping',
                body: {'mapping': mapping},
              )
              as Map<String, dynamic>;
      if (!mounted) return;
      if (response['status'] == 'ready') {
        Navigator.of(context).pop(true);
      } else {
        setState(() => _error = widget.t.connectionsMappingSubtitle);
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return AlertDialog(
      title: Row(
        children: [
          const Icon(Icons.check_circle, color: _Brand.green, size: 24),
          const SizedBox(width: 10),
          Expanded(child: Text(widget.t.connectionsMappingTitle)),
        ],
      ),
      content: SizedBox(
        width: 720,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _profile,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError || snapshot.data == null) {
              return Text(widget.t.connectionsGenericError);
            }
            final profile = snapshot.data!;
            _initialize(profile);
            final suggestions =
                (profile['mapping_suggestions'] as List<dynamic>? ?? const [])
                    .cast<Map<String, dynamic>>();
            final accepted =
                (profile['accepted_mapping'] as Map<String, dynamic>? ?? const {});
            final columns =
                (profile['columns'] as List<dynamic>? ?? const [])
                    .cast<Map<String, dynamic>>();

            final colTypes = {
              for (final c in columns)
                c['name']?.toString() ?? '': c['semantic_type']?.toString() ?? 'text',
            };

            final totalCount = suggestions.isNotEmpty ? suggestions.length : columns.length;
            final mappedCount = suggestions.where((s) {
              final col = s['original_column']?.toString() ?? '';
              return _selected[col] != null || accepted[col] != null;
            }).length;
            final unmappedCount = math.max(0, totalCount - mappedCount);

            return SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Status summary card
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: _Brand.green.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: _Brand.green.withValues(alpha: 0.3)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Row(
                          children: [
                            Icon(Icons.verified, color: _Brand.green, size: 20),
                            SizedBox(width: 8),
                            Flexible(
                              child: Text(
                                'Données prêtes · Auto-mapping automatique validé',
                                style: TextStyle(
                                  color: _Brand.green,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 14,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '$totalCount colonnes détectées · $mappedCount reconnues automatiquement · $unmappedCount conservées sans mapping · 0 erreur bloquante',
                          style: TextStyle(color: colors.ink, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'Correspondance des colonnes détectées :',
                    style: TextStyle(
                      color: colors.ink,
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 10),
                  // Column mapping list
                  for (final item in suggestions) ...[
                    Builder(
                      builder: (context) {
                        final col = item['original_column']?.toString() ?? '';
                        final canonical = _selected[col] ?? accepted[col];
                        final semType = colTypes[col] ?? 'texte';
                        final confidence = item['confidence']?.toString().toUpperCase() ?? 'NONE';
                        final isMapped = canonical != null && canonical.isNotEmpty;

                        return Container(
                          margin: const EdgeInsets.only(bottom: 8),
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            color: colors.surface,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: colors.line),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                flex: 3,
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      col,
                                      style: TextStyle(
                                        color: colors.ink,
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13,
                                        fontFamily: 'monospace',
                                      ),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      'Type : $semType',
                                      style: TextStyle(
                                        color: colors.muted,
                                        fontSize: 11,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              const Icon(Icons.arrow_forward, size: 16, color: Colors.grey),
                              const SizedBox(width: 8),
                              Expanded(
                                flex: 4,
                                child: Row(
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: isMapped
                                            ? _Brand.blue.withValues(alpha: 0.12)
                                            : colors.muted.withValues(alpha: 0.12),
                                        borderRadius: BorderRadius.circular(6),
                                        border: Border.all(
                                          color: isMapped
                                              ? _Brand.blue.withValues(alpha: 0.4)
                                              : colors.line,
                                        ),
                                      ),
                                      child: Text(
                                        isMapped ? canonical : 'Conservée brute (non mappée)',
                                        style: TextStyle(
                                          color: isMapped ? _Brand.blue : colors.muted,
                                          fontWeight: isMapped ? FontWeight.w700 : FontWeight.normal,
                                          fontSize: 12,
                                        ),
                                      ),
                                    ),
                                    const Spacer(),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: confidence == 'HIGH'
                                            ? _Brand.green.withValues(alpha: 0.1)
                                            : (confidence == 'MEDIUM'
                                                ? _Brand.blue.withValues(alpha: 0.1)
                                                : colors.muted.withValues(alpha: 0.1)),
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                      child: Text(
                                        confidence == 'HIGH'
                                            ? 'Auto (Haute)'
                                            : (confidence == 'MEDIUM' ? 'Auto (Moyenne)' : 'Brute'),
                                        style: TextStyle(
                                          fontSize: 10,
                                          fontWeight: FontWeight.w700,
                                          color: confidence == 'HIGH'
                                              ? _Brand.green
                                              : (confidence == 'MEDIUM' ? _Brand.blue : colors.muted),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ],
                  const SizedBox(height: 12),
                  // Advanced toggle
                  InkWell(
                    onTap: () => setState(() => _showAdvanced = !_showAdvanced),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Row(
                        children: [
                          Icon(
                            _showAdvanced ? Icons.keyboard_arrow_down : Icons.keyboard_arrow_right,
                            size: 20,
                            color: colors.muted,
                          ),
                          const SizedBox(width: 6),
                          Text(
                            'Paramètres avancés / Modifier manuellement',
                            style: TextStyle(
                              color: colors.muted,
                              fontWeight: FontWeight.w600,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (_showAdvanced) ...[
                    const SizedBox(height: 10),
                    for (final item in suggestions) ...[
                      Text(
                        item['original_column'].toString(),
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
                      ),
                      const SizedBox(height: 4),
                      DropdownButtonFormField<String?>(
                        initialValue: _selected[item['original_column'].toString()],
                        isExpanded: true,
                        items: [
                          DropdownMenuItem<String?>(
                            value: null,
                            child: Text(widget.t.connectionsMappingIgnore),
                          ),
                          for (final option in {
                            if (item['suggested_field'] != null)
                              item['suggested_field'].toString(),
                            for (final value in (item['alternatives'] as List<dynamic>? ?? const []))
                              value.toString(),
                          })
                            DropdownMenuItem<String?>(
                              value: option,
                              child: Text(option),
                            ),
                        ],
                        onChanged: _submitting
                            ? null
                            : (value) => setState(() {
                                  _selected[item['original_column'].toString()] = value;
                                  _hasChanges = true;
                                }),
                      ),
                      const SizedBox(height: 10),
                    ],
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!, style: const TextStyle(color: _Brand.red)),
                  ],
                ],
              ),
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: _submitting
              ? null
              : () => Navigator.of(context).pop(false),
          child: Text(_hasChanges ? MaterialLocalizations.of(context).cancelButtonLabel : 'Fermer'),
        ),
        if (_hasChanges)
          FilledButton(
            onPressed: _submitting ? null : _submit,
            child: Text(widget.t.connectionsConfirmMapping),
          ),
      ],
    );
  }
}

class _DatasetCleaningDialog extends StatefulWidget {
  const _DatasetCleaningDialog({
    required this.api,
    required this.datasetId,
    required this.t,
  });

  final ApiClient api;
  final String datasetId;
  final CompanyStrings t;

  @override
  State<_DatasetCleaningDialog> createState() => _DatasetCleaningDialogState();
}

class _DatasetCleaningDialogState extends State<_DatasetCleaningDialog> {
  late final Future<Map<String, dynamic>> _detail = _load();
  bool _exporting = false;

  String _apercuSearch = '';
  int _apercuPage = 0;
  int _apercuPageSize = 10;

  String _columnsSearch = '';
  String _modificationsSearch = '';

  Future<Map<String, dynamic>> _load() async =>
      await widget.api.get('/datasets/${widget.datasetId}/cleaning')
          as Map<String, dynamic>;

  Future<void> _export(String format) async {
    if (_exporting) return;
    setState(() => _exporting = true);
    try {
      final file = await widget.api.download(
        '/datasets/${widget.datasetId}/export/$format',
      );
      await saveExportFile(file.fileName, file.bytes);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.maybeOf(
          context,
        )?.showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final size = MediaQuery.sizeOf(context);
    final dialogWidth = math.min(size.width - 24, 1100.0);
    final dialogHeight = math.min(size.height * 0.92, 860.0);

    return AlertDialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
      contentPadding: EdgeInsets.zero,
      backgroundColor: colors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: colors.line),
      ),
      content: SizedBox(
        width: dialogWidth,
        height: dialogHeight,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _detail,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError || snapshot.data == null) {
              final error = snapshot.error;
              final message = error is ApiException
                  ? error.message
                  : widget.t.connectionsGenericError;
              return Center(child: Text(message));
            }

            final detail = snapshot.data!;
            final header = detail['header'] as Map<String, dynamic>? ?? const {};
            final summary = detail['summary'] as Map<String, dynamic>? ?? const {};
            final isReady = detail['status'] == 'ready';

            final rawBusinessPreview = (detail['business_preview'] as List<dynamic>? ??
                    detail['cleaned_preview'] as List<dynamic>? ??
                    const [])
                .cast<Map<String, dynamic>>();

            final columns = (detail['columns'] as List<dynamic>? ?? const [])
                .cast<Map<String, dynamic>>();

            final modifications = (detail['modifications'] as List<dynamic>? ?? const [])
                .cast<Map<String, dynamic>>();

            final quality = detail['quality'] as Map<String, dynamic>? ?? const {};

            final entityViews =
                (detail['entity_views'] as Map<String, dynamic>? ?? const {})
                    .map(
                      (name, records) => MapEntry(
                        name,
                        (records as List<dynamic>? ?? const [])
                            .cast<Map<String, dynamic>>(),
                      ),
                    );

            final technicalPreview = (detail['technical_preview'] as List<dynamic>? ??
                    detail['original_preview'] as List<dynamic>? ??
                    const [])
                .cast<Map<String, dynamic>>();

            final exportFormats =
                (detail['export_formats'] as List<dynamic>? ?? const ['csv', 'json'])
                    .map((item) => item.toString().toUpperCase())
                    .toList();

            final datasetName = header['dataset_name']?.toString() ??
                detail['name']?.toString() ??
                'Dataset';
            final sourceLabel = header['source']?.toString() ?? 'Commerce / Retail';
            final rowCount = header['row_count'] ?? summary['cleaned_row_count'] ?? rawBusinessPreview.length;
            final columnCount = header['column_count'] ?? summary['column_count'] ?? (rawBusinessPreview.isNotEmpty ? rawBusinessPreview.first.length : columns.length);
            final qualityScore = header['quality_score'] ?? summary['quality_score_after'] ?? 100;
            final lastSync = header['last_sync']?.toString() ?? '';
            final statusLabel = header['status_label']?.toString() ??
                (isReady ? 'Données prêtes' : 'Attention requise');

            return DefaultTabController(
              length: 6,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // --- HEADER PROFESSIONNEL ---
                  Container(
                    padding: const EdgeInsets.fromLTRB(20, 16, 16, 14),
                    decoration: BoxDecoration(
                      color: colors.canvas,
                      borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
                      border: Border(bottom: BorderSide(color: colors.line)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Row(
                                children: [
                                  Flexible(
                                    child: Text(
                                      datasetName,
                                      style: TextStyle(
                                        color: colors.ink,
                                        fontSize: 18,
                                        fontWeight: FontWeight.w800,
                                      ),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  const SizedBox(width: 10),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                    decoration: BoxDecoration(
                                      color: _Brand.blue.withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(6),
                                      border: Border.all(color: _Brand.blue.withValues(alpha: 0.3)),
                                    ),
                                    child: Text(
                                      sourceLabel,
                                      style: const TextStyle(
                                        color: _Brand.blue,
                                        fontWeight: FontWeight.w700,
                                        fontSize: 12,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            // Exports
                            for (final format in exportFormats) ...[
                              OutlinedButton.icon(
                                style: OutlinedButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                  minimumSize: Size.zero,
                                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                ),
                                onPressed: _exporting ? null : () => _export(format.toLowerCase()),
                                icon: const Icon(Icons.download_outlined, size: 15),
                                label: Text(format, style: const TextStyle(fontSize: 12)),
                              ),
                              const SizedBox(width: 6),
                            ],
                            IconButton(
                              icon: const Icon(Icons.close, size: 20),
                              onPressed: () => Navigator.of(context).pop(),
                              tooltip: MaterialLocalizations.of(context).closeButtonLabel,
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 12,
                          runSpacing: 6,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            _HeaderPill(
                              icon: Icons.table_rows_outlined,
                              text: '$rowCount lignes',
                              colors: colors,
                            ),
                            _HeaderPill(
                              icon: Icons.view_column_outlined,
                              text: '$columnCount colonnes',
                              colors: colors,
                            ),
                            _HeaderPill(
                              icon: Icons.verified_outlined,
                              text: 'Qualité : $qualityScore%',
                              color: _Brand.green,
                              colors: colors,
                            ),
                            if (lastSync.isNotEmpty)
                              _HeaderPill(
                                icon: Icons.sync,
                                text: 'Dernière synchro : $lastSync',
                                colors: colors,
                              ),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: (isReady ? _Brand.green : _Brand.red).withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                isReady ? '✅ $statusLabel' : '⚠️ $statusLabel',
                                style: TextStyle(
                                  color: isReady ? _Brand.green : _Brand.red,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),

                  // --- 6 ONGLETS PRINCIPAUX ---
                  Container(
                    decoration: BoxDecoration(
                      color: colors.canvas,
                      border: Border(bottom: BorderSide(color: colors.line)),
                    ),
                    child: TabBar(
                      isScrollable: true,
                      tabAlignment: TabAlignment.start,
                      labelColor: _Brand.blue,
                      unselectedLabelColor: colors.muted,
                      indicatorColor: _Brand.blue,
                      indicatorWeight: 3,
                      tabs: [
                        const Tab(
                          iconMargin: EdgeInsets.only(bottom: 2),
                          icon: Icon(Icons.table_chart_outlined, size: 16),
                          text: 'APERÇU',
                        ),
                        Tab(
                          iconMargin: const EdgeInsets.only(bottom: 2),
                          icon: const Icon(Icons.view_column_outlined, size: 16),
                          text: 'COLONNES (${columns.length})',
                        ),
                        Tab(
                          iconMargin: const EdgeInsets.only(bottom: 2),
                          icon: const Icon(Icons.difference_outlined, size: 16),
                          text: 'MODIFICATIONS (${modifications.length})',
                        ),
                        const Tab(
                          iconMargin: EdgeInsets.only(bottom: 2),
                          icon: Icon(Icons.inventory_2_outlined, size: 16),
                          text: 'ENTITÉS MÉTIER',
                        ),
                        Tab(
                          iconMargin: const EdgeInsets.only(bottom: 2),
                          icon: const Icon(Icons.verified_outlined, size: 16),
                          text: 'QUALITÉ ($qualityScore%)',
                        ),
                        const Tab(
                          iconMargin: EdgeInsets.only(bottom: 2),
                          icon: Icon(Icons.dns_outlined, size: 16),
                          text: 'TECHNIQUE',
                        ),
                      ],
                    ),
                  ),

                  // --- CONTENU DES ONGLETS ---
                  Expanded(
                    child: TabBarView(
                      children: [
                        // Tab 1: APERÇU
                        _ApercuTab(
                          rows: rawBusinessPreview,
                          searchQuery: _apercuSearch,
                          page: _apercuPage,
                          pageSize: _apercuPageSize,
                          onSearchChanged: (q) => setState(() {
                            _apercuSearch = q;
                            _apercuPage = 0;
                          }),
                          onPageChanged: (p) => setState(() => _apercuPage = p),
                          onPageSizeChanged: (ps) => setState(() {
                            _apercuPageSize = ps;
                            _apercuPage = 0;
                          }),
                          colors: colors,
                          emptyLabel: _cleaningText(widget.t, 'previewEmpty'),
                        ),

                        // Tab 2: COLONNES
                        _ColumnsTab(
                          columns: columns,
                          searchQuery: _columnsSearch,
                          onSearchChanged: (q) => setState(() => _columnsSearch = q),
                          colors: colors,
                          t: widget.t,
                        ),

                        // Tab 3: MODIFICATIONS
                        _ModificationsTab(
                          modifications: modifications,
                          searchQuery: _modificationsSearch,
                          onSearchChanged: (q) => setState(() => _modificationsSearch = q),
                          colors: colors,
                          t: widget.t,
                        ),

                        // Tab 4: ENTITÉS MÉTIER
                        _EntityViewsTab(
                          entities: entityViews,
                          colors: colors,
                          emptyLabel: _cleaningText(widget.t, 'previewEmpty'),
                        ),

                        // Tab 5: QUALITÉ
                        _QualityTab(
                          quality: quality,
                          summary: summary,
                          colors: colors,
                          t: widget.t,
                        ),

                        // Tab 6: TECHNIQUE
                        _TechniqueTab(
                          rows: technicalPreview,
                          datasetId: widget.datasetId,
                          version: detail['version']?.toString() ?? '1',
                          colors: colors,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _HeaderPill extends StatelessWidget {
  const _HeaderPill({
    required this.icon,
    required this.text,
    required this.colors,
    this.color,
  });

  final IconData icon;
  final String text;
  final AvenqoColors colors;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final fg = color ?? colors.muted;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: fg),
        const SizedBox(width: 4),
        Text(
          text,
          style: TextStyle(
            color: fg,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _ApercuTab extends StatelessWidget {
  const _ApercuTab({
    required this.rows,
    required this.searchQuery,
    required this.page,
    required this.pageSize,
    required this.onSearchChanged,
    required this.onPageChanged,
    required this.onPageSizeChanged,
    required this.colors,
    required this.emptyLabel,
  });

  final List<Map<String, dynamic>> rows;
  final String searchQuery;
  final int page;
  final int pageSize;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<int> onPageSizeChanged;
  final AvenqoColors colors;
  final String emptyLabel;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return Center(
        child: Text(emptyLabel, style: TextStyle(color: colors.muted)),
      );
    }

    final query = searchQuery.trim().toLowerCase();
    final filtered = query.isEmpty
        ? rows
        : rows.where((r) {
            return r.values.any((v) => v?.toString().toLowerCase().contains(query) ?? false);
          }).toList();

    final totalRows = filtered.length;
    final maxPage = (totalRows / pageSize).ceil();
    final currentPage = maxPage == 0 ? 0 : page.clamp(0, maxPage - 1);
    final startIndex = currentPage * pageSize;
    final pagedRows = filtered.skip(startIndex).take(pageSize).toList();

    final allColumns = <String>{};
    for (final r in rows) {
      allColumns.addAll(r.keys);
    }
    final columns = allColumns.toList();

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // Barre de recherche et pagination controls
          Row(
            children: [
              Expanded(
                child: SizedBox(
                  height: 38,
                  child: TextField(
                    onChanged: onSearchChanged,
                    decoration: InputDecoration(
                      hintText: 'Rechercher dans l\'aperçu...',
                      hintStyle: TextStyle(color: colors.muted, fontSize: 13),
                      prefixIcon: Icon(Icons.search, size: 18, color: colors.muted),
                      suffixIcon: searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.clear, size: 16),
                              onPressed: () => onSearchChanged(''),
                            )
                          : null,
                      contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 10),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(color: colors.line),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(color: colors.line),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                '${startIndex + 1}-${math.min(startIndex + pageSize, totalRows)} sur $totalRows',
                style: TextStyle(color: colors.muted, fontSize: 12, fontWeight: FontWeight.w600),
              ),
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.chevron_left, size: 20),
                onPressed: currentPage > 0 ? () => onPageChanged(currentPage - 1) : null,
                tooltip: 'Page précédente',
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right, size: 20),
                onPressed: (currentPage + 1) < maxPage ? () => onPageChanged(currentPage + 1) : null,
                tooltip: 'Page suivante',
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Table avec scroll horizontal
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) => Container(
                decoration: BoxDecoration(
                  border: Border.all(color: colors.line),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: AvenqoDataTable(
                    semanticLabel: 'Aperçu des données nettoyées',
                    minWidth: math.max(columns.length * 160.0, constraints.maxWidth),
                    maxHeight: constraints.maxHeight,
                    fixedLeftColumns: 1,
                    columns: [
                      for (final col in columns)
                        DataColumn(
                          label: Text(
                            col,
                            style: TextStyle(
                              color: colors.ink,
                              fontWeight: FontWeight.w700,
                              fontSize: 12,
                            ),
                          ),
                        ),
                    ],
                    rows: [
                      for (final row in pagedRows)
                        DataRow(
                          cells: [
                            for (final col in columns)
                              DataCell(
                                ConstrainedBox(
                                  constraints: const BoxConstraints(maxWidth: 240),
                                  child: Text(
                                    row[col]?.toString() ?? '—',
                                    style: TextStyle(
                                      color: colors.ink,
                                      fontSize: 12,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              ),
                          ],
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ColumnsTab extends StatelessWidget {
  const _ColumnsTab({
    required this.columns,
    required this.searchQuery,
    required this.onSearchChanged,
    required this.colors,
    required this.t,
  });

  final List<Map<String, dynamic>> columns;
  final String searchQuery;
  final ValueChanged<String> onSearchChanged;
  final AvenqoColors colors;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    if (columns.isEmpty) {
      return Center(
        child: Text('Aucune colonne analysée.', style: TextStyle(color: colors.muted)),
      );
    }

    final query = searchQuery.trim().toLowerCase();
    final filtered = query.isEmpty
        ? columns
        : columns.where((c) {
            final name = c['cleaned_name']?.toString().toLowerCase() ?? '';
            final orig = c['original_name']?.toString().toLowerCase() ?? '';
            final type = c['final_type']?.toString().toLowerCase() ?? '';
            return name.contains(query) || orig.contains(query) || type.contains(query);
          }).toList();

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 38,
            child: TextField(
              onChanged: onSearchChanged,
              decoration: InputDecoration(
                hintText: 'Filtrer les colonnes (nom, type)...',
                hintStyle: TextStyle(color: colors.muted, fontSize: 13),
                prefixIcon: Icon(Icons.search, size: 18, color: colors.muted),
                suffixIcon: searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 16),
                        onPressed: () => onSearchChanged(''),
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 10),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: colors.line),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: colors.line),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final isWide = constraints.maxWidth > 700;
                return GridView.builder(
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: isWide ? 3 : 1,
                    childAspectRatio: isWide ? 1.7 : 2.4,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                  ),
                  itemCount: filtered.length,
                  itemBuilder: (context, index) {
                    final col = filtered[index];
                    final name = col['cleaned_name']?.toString() ?? col['original_name']?.toString() ?? '—';
                    final originalType = col['original_type']?.toString() ?? 'text';
                    final finalType = col['final_type']?.toString() ?? originalType;
                    final nullsBefore = col['nulls_before'] ?? 0;
                    final nullsAfter = col['nulls_after'] ?? 0;
                    final modifiedCount = col['modified_count'] ?? 0;
                    final qualityScore = col['quality_score'] ?? 100;

                    return Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: colors.canvas,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: colors.line),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  name,
                                  style: TextStyle(
                                    color: colors.ink,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 14,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: _Brand.blue.withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  finalType,
                                  style: const TextStyle(
                                    color: _Brand.blue,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 11,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const Divider(height: 14),
                          _CardRow(
                            label: 'Type :',
                            value: originalType == finalType ? finalType : '$originalType → $finalType',
                            colors: colors,
                          ),
                          const SizedBox(height: 3),
                          _CardRow(
                            label: 'Valeurs nulles :',
                            value: '$nullsAfter${nullsBefore != nullsAfter ? " (avant: $nullsBefore)" : ""}',
                            colors: colors,
                          ),
                          const SizedBox(height: 3),
                          _CardRow(
                            label: 'Valeurs modifiées :',
                            value: '$modifiedCount',
                            valueColor: modifiedCount > 0 ? _Brand.green : null,
                            colors: colors,
                          ),
                          const Spacer(),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                'Qualité :',
                                style: TextStyle(color: colors.muted, fontSize: 11),
                              ),
                              Text(
                                '$qualityScore%',
                                style: const TextStyle(
                                  color: _Brand.green,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _CardRow extends StatelessWidget {
  const _CardRow({
    required this.label,
    required this.value,
    required this.colors,
    this.valueColor,
  });

  final String label;
  final String value;
  final AvenqoColors colors;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: TextStyle(color: colors.muted, fontSize: 12)),
        Text(
          value,
          style: TextStyle(
            color: valueColor ?? colors.ink,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _ModificationsTab extends StatelessWidget {
  const _ModificationsTab({
    required this.modifications,
    required this.searchQuery,
    required this.onSearchChanged,
    required this.colors,
    required this.t,
  });

  final List<Map<String, dynamic>> modifications;
  final String searchQuery;
  final ValueChanged<String> onSearchChanged;
  final AvenqoColors colors;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    final query = searchQuery.trim().toLowerCase();
    final filtered = query.isEmpty
        ? modifications
        : modifications.where((m) {
            final entity = m['entity']?.toString().toLowerCase() ?? '';
            final col = m['column']?.toString().toLowerCase() ?? '';
            final reason = m['reason']?.toString().toLowerCase() ?? '';
            final src = m['source']?.toString().toLowerCase() ?? '';
            return entity.contains(query) || col.contains(query) || reason.contains(query) || src.contains(query);
          }).toList();

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: 38,
            child: TextField(
              onChanged: onSearchChanged,
              decoration: InputDecoration(
                hintText: 'Rechercher une modification (ex: Avenqo Headphones X, stock)...',
                hintStyle: TextStyle(color: colors.muted, fontSize: 13),
                prefixIcon: Icon(Icons.search, size: 18, color: colors.muted),
                suffixIcon: searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 16),
                        onPressed: () => onSearchChanged(''),
                      )
                    : null,
                contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 10),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: colors.line),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide(color: colors.line),
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          if (filtered.isEmpty)
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.check_circle_outline, size: 40, color: _Brand.green),
                    const SizedBox(height: 8),
                    Text(
                      'Aucune modification enregistrée pour cette recherche.',
                      style: TextStyle(color: colors.muted, fontSize: 14),
                    ),
                  ],
                ),
              ),
            )
          else
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) => Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: colors.line),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: AvenqoDataTable(
                      semanticLabel: 'Table de diff des modifications',
                      minWidth: math.max(880.0, constraints.maxWidth),
                      maxHeight: constraints.maxHeight,
                      fixedLeftColumns: 1,
                      columns: const [
                        DataColumn(label: Text('Entité', style: TextStyle(fontWeight: FontWeight.w700))),
                        DataColumn(label: Text('Colonne', style: TextStyle(fontWeight: FontWeight.w700))),
                        DataColumn(label: Text('Avant', style: TextStyle(fontWeight: FontWeight.w700))),
                        DataColumn(label: Text('Après', style: TextStyle(fontWeight: FontWeight.w700))),
                        DataColumn(label: Text('Différence', style: TextStyle(fontWeight: FontWeight.w700))),
                        DataColumn(label: Text('Raison', style: TextStyle(fontWeight: FontWeight.w700))),
                        DataColumn(label: Text('Source', style: TextStyle(fontWeight: FontWeight.w700))),
                        DataColumn(label: Text('Date', style: TextStyle(fontWeight: FontWeight.w700))),
                      ],
                      rows: [
                        for (final m in filtered)
                          DataRow(
                            cells: [
                              DataCell(
                                Text(
                                  m['entity']?.toString() ?? '—',
                                  style: TextStyle(
                                    color: colors.ink,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 13,
                                  ),
                                ),
                              ),
                              DataCell(
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: colors.muted.withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: Text(
                                    m['column']?.toString() ?? '—',
                                    style: TextStyle(
                                      color: colors.ink,
                                      fontFamily: 'monospace',
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                              ),
                              DataCell(
                                Text(
                                  m['before']?.toString() ?? '—',
                                  style: TextStyle(
                                    color: colors.muted,
                                    decoration: TextDecoration.lineThrough,
                                    fontSize: 13,
                                  ),
                                ),
                              ),
                              DataCell(
                                Text(
                                  m['after']?.toString() ?? '—',
                                  style: TextStyle(
                                    color: colors.ink,
                                    fontWeight: FontWeight.w800,
                                    fontSize: 13,
                                  ),
                                ),
                              ),
                              DataCell(
                                Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      '${m['before']} → ${m['after']}',
                                      style: TextStyle(color: colors.muted, fontSize: 12),
                                    ),
                                    if (m['diff'] != null && m['diff'].toString().isNotEmpty) ...[
                                      const SizedBox(width: 8),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: _Brand.green.withValues(alpha: 0.15),
                                          borderRadius: BorderRadius.circular(4),
                                          border: Border.all(color: _Brand.green),
                                        ),
                                        child: Text(
                                          m['diff'].toString(),
                                          style: const TextStyle(
                                            color: _Brand.green,
                                            fontWeight: FontWeight.w800,
                                            fontSize: 12,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                              DataCell(
                                Text(
                                  m['reason']?.toString() ?? 'Nettoyage automatique',
                                  style: TextStyle(color: colors.muted, fontSize: 12),
                                ),
                              ),
                              DataCell(
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: _Brand.blue.withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: Text(
                                    m['source']?.toString() ?? 'Dataset',
                                    style: const TextStyle(
                                      color: _Brand.blue,
                                      fontWeight: FontWeight.w600,
                                      fontSize: 11,
                                    ),
                                  ),
                                ),
                              ),
                              DataCell(
                                Text(
                                  m['timestamp']?.toString().split('T').first ?? '—',
                                  style: TextStyle(color: colors.muted, fontSize: 12),
                                ),
                              ),
                            ],
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _EntityViewsTab extends StatelessWidget {
  const _EntityViewsTab({
    required this.entities,
    required this.colors,
    required this.emptyLabel,
  });

  final Map<String, List<Map<String, dynamic>>> entities;
  final AvenqoColors colors;
  final String emptyLabel;

  @override
  Widget build(BuildContext context) {
    final visible = entities.entries.where((e) => e.value.isNotEmpty).toList();
    if (visible.isEmpty) {
      return Center(
        child: Text(emptyLabel, style: TextStyle(color: colors.muted)),
      );
    }

    return DefaultTabController(
      length: visible.length,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            decoration: BoxDecoration(
              color: colors.canvas,
              border: Border(bottom: BorderSide(color: colors.line)),
            ),
            child: TabBar(
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              labelColor: _Brand.blue,
              unselectedLabelColor: colors.muted,
              indicatorColor: _Brand.blue,
              tabs: [
                for (final entity in visible)
                  Tab(text: '${_humanizeCode(entity.key)} (${entity.value.length})'),
              ],
            ),
          ),
          Expanded(
            child: TabBarView(
              children: [
                for (final entity in visible)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: _PreviewTable(rows: entity.value, emptyLabel: emptyLabel),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _QualityTab extends StatelessWidget {
  const _QualityTab({
    required this.quality,
    required this.summary,
    required this.colors,
    required this.t,
  });

  final Map<String, dynamic> quality;
  final Map<String, dynamic> summary;
  final AvenqoColors colors;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    final globalScore = quality['global_score'] ?? summary['quality_score_after'] ?? 100;
    final nullsCorrected = quality['nulls_corrected'] ?? summary['missing_values_detected'] ?? 0;
    final duplicatesRemoved = quality['duplicates_removed'] ?? summary['duplicate_rows_removed'] ?? 0;
    final typesConverted = quality['types_converted'] ?? summary['invalid_values_corrected'] ?? 0;
    final valuesModified = quality['values_modified'] ?? 0;
    final outliersCount = quality['outliers_count'] ?? 0;
    final columnsCorrected = quality['columns_corrected'] ?? 0;
    final rowsModified = quality['rows_modified'] ?? 0;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Score global banner
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  _Brand.green.withValues(alpha: 0.15),
                  _Brand.blue.withValues(alpha: 0.08),
                ],
              ),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _Brand.green.withValues(alpha: 0.3)),
            ),
            child: Row(
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: _Brand.green.withValues(alpha: 0.2),
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: Text(
                      '$globalScore%',
                      style: const TextStyle(
                        color: _Brand.green,
                        fontWeight: FontWeight.w900,
                        fontSize: 18,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Score global de qualité du dataset',
                        style: TextStyle(
                          color: colors.ink,
                          fontWeight: FontWeight.w800,
                          fontSize: 16,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Nettoyage intelligent appliqué sans altération des schémas source. Données prêtes pour Retail Intelligence.',
                        style: TextStyle(color: colors.muted, fontSize: 13),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          Text(
            'Indicateurs de nettoyage',
            style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700, fontSize: 15),
          ),
          const SizedBox(height: 12),

          // Grille de métriques
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              _MetricCard(
                icon: Icons.do_not_disturb_alt_outlined,
                title: 'Nulls corrigés',
                value: '$nullsCorrected',
                color: _Brand.blue,
                colors: colors,
              ),
              _MetricCard(
                icon: Icons.content_copy_outlined,
                title: 'Doublons supprimés',
                value: '$duplicatesRemoved',
                color: _Brand.blue,
                colors: colors,
              ),
              _MetricCard(
                icon: Icons.transform_outlined,
                title: 'Types convertis',
                value: '$typesConverted',
                color: _Brand.blue,
                colors: colors,
              ),
              _MetricCard(
                icon: Icons.edit_note_outlined,
                title: 'Valeurs modifiées',
                value: '$valuesModified',
                color: _Brand.green,
                colors: colors,
              ),
              _MetricCard(
                icon: Icons.warning_amber_outlined,
                title: 'Outliers détectés',
                value: '$outliersCount',
                color: _Brand.red,
                colors: colors,
              ),
              _MetricCard(
                icon: Icons.view_column_outlined,
                title: 'Colonnes corrigées',
                value: '$columnsCorrected',
                color: _Brand.blue,
                colors: colors,
              ),
              _MetricCard(
                icon: Icons.table_rows_outlined,
                title: 'Lignes modifiées',
                value: '$rowsModified',
                color: _Brand.green,
                colors: colors,
              ),
            ],
          ),
          const SizedBox(height: 24),

          Text(
            'Règles automatiques appliquées',
            style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700, fontSize: 15),
          ),
          const SizedBox(height: 10),

          const _RuleCheckItem(title: 'Nettoyage des espaces blancs et retours chariot aux extrémités (trim)'),
          const _RuleCheckItem(title: 'Normalisation Unicode NFKC des chaînes'),
          const _RuleCheckItem(title: 'Conversion automatique des types numériques stockés sous forme de chaînes'),
          const _RuleCheckItem(title: 'Normalisation des dates vers la norme standard ISO 8601'),
          const _RuleCheckItem(title: 'Normalisation des valeurs booléennes (oui/non, true/false, 1/0)'),
          const _RuleCheckItem(title: 'Détection d\'outliers numériques anormaux et protection de cohérence'),
          const _RuleCheckItem(title: 'Préservation absolue des snapshots bruts et auditabilité multi-tenant'),
        ],
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.icon,
    required this.title,
    required this.value,
    required this.color,
    required this.colors,
  });

  final IconData icon;
  final String title;
  final String value;
  final Color color;
  final AvenqoColors colors;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 150,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.canvas,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: colors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: color),
              const Spacer(),
              Text(
                value,
                style: TextStyle(
                  color: colors.ink,
                  fontWeight: FontWeight.w800,
                  fontSize: 16,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            title,
            style: TextStyle(color: colors.muted, fontSize: 11),
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _RuleCheckItem extends StatelessWidget {
  const _RuleCheckItem({required this.title});
  final String title;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          const Icon(Icons.check_circle, size: 16, color: _Brand.green),
          const SizedBox(width: 8),
          Expanded(
            child: Text(title, style: TextStyle(color: colors.ink, fontSize: 13)),
          ),
        ],
      ),
    );
  }
}

class _TechniqueTab extends StatelessWidget {
  const _TechniqueTab({
    required this.rows,
    required this.datasetId,
    required this.version,
    required this.colors,
  });

  final List<Map<String, dynamic>> rows;
  final String datasetId;
  final String version;
  final AvenqoColors colors;

  @override
  Widget build(BuildContext context) {
    final columns = rows.isNotEmpty ? rows.first.keys.toList() : <String>[];

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: colors.canvas,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: colors.line),
            ),
            child: Row(
              children: [
                Icon(Icons.info_outline, size: 18, color: colors.muted),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Identifiants techniques (UUIDs, tenant_id, company_id, hash) et snapshots bruts isolés pour traçabilité.',
                    style: TextStyle(color: colors.muted, fontSize: 12),
                  ),
                ),
                Text(
                  'Dataset : $datasetId · v$version',
                  style: TextStyle(
                    color: colors.muted,
                    fontFamily: 'monospace',
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Expanded(
            child: rows.isEmpty
                ? Center(
                    child: Text('Aucune donnée technique disponible.', style: TextStyle(color: colors.muted)),
                  )
                : LayoutBuilder(
                    builder: (context, constraints) => Container(
                      decoration: BoxDecoration(
                        border: Border.all(color: colors.line),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: AvenqoDataTable(
                          semanticLabel: 'Table technique',
                          minWidth: math.max(columns.length * 180.0, constraints.maxWidth),
                          maxHeight: constraints.maxHeight,
                          fixedLeftColumns: 1,
                          columns: [
                            for (final col in columns)
                              DataColumn(
                                label: Text(
                                  col,
                                  style: TextStyle(
                                    color: colors.ink,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 12,
                                  ),
                                ),
                              ),
                          ],
                          rows: [
                            for (final row in rows)
                              DataRow(
                                cells: [
                                  for (final col in columns)
                                    DataCell(
                                      ConstrainedBox(
                                        constraints: const BoxConstraints(maxWidth: 240),
                                        child: Text(
                                          row[col]?.toString() ?? '—',
                                          style: TextStyle(
                                            color: colors.muted,
                                            fontFamily: 'monospace',
                                            fontSize: 11,
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _PreviewTable extends StatelessWidget {
  const _PreviewTable({required this.rows, required this.emptyLabel});

  final List<Map<String, dynamic>> rows;
  final String emptyLabel;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return Center(child: Text(emptyLabel));
    }
    final columns = rows.first.keys.toList();
    return LayoutBuilder(
      builder: (context, constraints) => AvenqoDataTable(
        semanticLabel: emptyLabel,
        minWidth: math.max(columns.length * 160.0, constraints.maxWidth),
        maxHeight: constraints.maxHeight,
        fixedLeftColumns: 1,
        columns: [
          for (final column in columns) DataColumn(label: Text(column)),
        ],
        rows: [
          for (final row in rows.take(50))
            DataRow(
              cells: [
                for (final column in columns)
                  DataCell(
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 240),
                      child: Text(
                        row[column]?.toString() ?? '—',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}


class _SelectingView extends StatelessWidget {
  const _SelectingView({
    required this.pending,
    required this.duplicateNotice,
    required this.onAddMore,
    required this.onRemove,
    required this.onUpload,
    required this.t,
  });

  final List<_PendingFile> pending;
  final String? duplicateNotice;
  final VoidCallback onAddMore;
  final void Function(_PendingFile file) onRemove;
  final VoidCallback onUpload;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (duplicateNotice != null) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: _Brand.blue.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                duplicateNotice!,
                style: const TextStyle(color: _Brand.blue),
              ),
            ),
            const SizedBox(height: 16),
          ],
          for (final file in pending)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  const Icon(
                    Icons.insert_drive_file_outlined,
                    color: _Brand.blue,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          file.fileName,
                          style: TextStyle(
                            color: colors.ink,
                            fontWeight: FontWeight.w600,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          '${_formatSize(file.bytes.length)} · ${t.connectionsReadyToUpload}',
                          style: TextStyle(color: colors.muted, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: t.connectionsRemoveFile,
                    onPressed: () => onRemove(file),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              OutlinedButton.icon(
                onPressed: onAddMore,
                icon: const Icon(Icons.add, size: 18),
                label: Text(t.connectionsAddMoreFiles),
              ),
              FilledButton(
                onPressed: pending.isEmpty ? null : onUpload,
                style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
                child: Text(
                  _pluralize(
                    pending.length,
                    t.connectionsUploadCountOne,
                    t.connectionsUploadCountOther,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _UploadingView extends StatelessWidget {
  const _UploadingView({required this.items, required this.t});
  final List<_UploadItem> items;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: colors.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final item in items) ...[
            Row(
              children: [
                Icon(
                  item.error != null
                      ? Icons.error_outline
                      : item.done
                      ? Icons.check_circle_outline
                      : Icons.insert_drive_file_outlined,
                  color: item.error != null
                      ? _Brand.red
                      : (item.done ? _Brand.green : _Brand.blue),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '${item.fileName} · ${_formatSize(item.fileSize)}',
                    style: TextStyle(
                      color: colors.ink,
                      fontWeight: FontWeight.w600,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            LinearProgressIndicator(
              value: item.done || item.error != null
                  ? 1
                  : (item.progress > 0 ? item.progress : null),
              color: item.error != null ? _Brand.red : null,
            ),
            const SizedBox(height: 4),
            Text(
              item.error ??
                  (item.done
                      ? t.connectionsUploadedFileSuccessLabel
                      : t.connectionsUploadingLabel),
              style: TextStyle(
                color: item.error != null ? _Brand.red : colors.muted,
              ),
            ),
            const SizedBox(height: 16),
          ],
        ],
      ),
    );
  }
}

/// Résumé final visible (pas une simple snackbar) : succès/échecs par
/// fichier, actions utiles uniquement si au moins un dataset est prêt.
class _SummaryView extends StatelessWidget {
  const _SummaryView({
    required this.items,
    required this.onContinue,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.onAddFiles,
    required this.t,
  });

  final List<_UploadItem> items;
  final VoidCallback onContinue;
  final VoidCallback onGoToDashboard;
  final VoidCallback onAskAvenqo;
  final VoidCallback onAddFiles;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final successCount = items.where((i) => i.done && i.error == null).length;
    final errorCount = items.where((i) => i.error != null).length;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(28),
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
              Icon(
                errorCount == 0 ? Icons.check_circle : Icons.info_outline,
                color: errorCount == 0 ? _Brand.green : _Brand.blue,
              ),
              const SizedBox(width: 10),
              Text(
                t.connectionsImportCompleteTitle,
                style: TextStyle(
                  color: colors.ink,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            _pluralize(
              successCount,
              t.connectionsImportSummarySuccessOne,
              t.connectionsImportSummarySuccessOther,
            ),
            style: TextStyle(color: colors.ink),
          ),
          if (errorCount > 0) ...[
            const SizedBox(height: 4),
            Text(
              _pluralize(
                errorCount,
                t.connectionsImportSummaryErrorsOne,
                t.connectionsImportSummaryErrorsOther,
              ),
              style: const TextStyle(color: _Brand.red),
            ),
          ],
          const SizedBox(height: 18),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  Icon(
                    item.error != null
                        ? Icons.error_outline
                        : Icons.check_circle_outline,
                    color: item.error != null ? _Brand.red : _Brand.green,
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      item.fileName,
                      style: TextStyle(color: colors.ink),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              if (successCount > 0) ...[
                FilledButton(
                  onPressed: onGoToDashboard,
                  style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
                  child: Text(t.connectionsGoDashboard),
                ),
                OutlinedButton(
                  onPressed: onAskAvenqo,
                  child: Text(t.connectionsAskAvenqo),
                ),
              ],
              OutlinedButton(
                onPressed: onAddFiles,
                child: Text(t.connectionsAddFiles),
              ),
              TextButton(
                onPressed: onContinue,
                child: Text(t.connectionsContinueLabel),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({
    required this.message,
    required this.onRetry,
    required this.retryLabel,
  });
  final String message;
  final VoidCallback onRetry;
  final String retryLabel;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border.all(color: _Brand.red.withValues(alpha: 0.4)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          const Icon(Icons.error_outline, color: _Brand.red, size: 32),
          const SizedBox(height: 12),
          Text(
            message,
            textAlign: TextAlign.center,
            style: TextStyle(color: colors.ink),
          ),
          const SizedBox(height: 16),
          OutlinedButton(onPressed: onRetry, child: Text(retryLabel)),
        ],
      ),
    );
  }
}
