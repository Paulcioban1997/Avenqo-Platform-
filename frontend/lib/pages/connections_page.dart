import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/file_picker/app_file_picker.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

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

/// Centre de gestion des données Avenqo (remplace le placeholder générique).
/// Réutilise exclusivement les endpoints existants (`/datasets`,
/// `/datasets/upload`, `/datasets/{id}/profile`, `/datasets/{id}/mapping`).
class ConnectionsPage extends StatefulWidget {
  const ConnectionsPage({
    super.key,
    required this.api,
    this.pickFiles = pickDataFiles,
    this.pollInterval = const Duration(seconds: 3),
  });
  final ApiClient api;
  final FilePickerFn pickFiles;
  final Duration pollInterval;

  @override
  State<ConnectionsPage> createState() => _ConnectionsPageState();
}

class _ConnectionsPageState extends State<ConnectionsPage> {
  _ViewState _state = _ViewState.loading;
  List<Map<String, dynamic>> _datasets = [];
  String? _errorMessage;
  String? _duplicateNotice;
  final List<_PendingFile> _pending = [];
  List<_UploadItem> _uploadItems = [];
  final Set<String> _deletingDatasetIds = <String>{};
  Timer? _pollTimer;
  bool _refreshing = false;

  @override
  void initState() {
    super.initState();
    _loadDatasets();
  }

  Future<void> _loadDatasets() async {
    setState(() => _state = _ViewState.loading);
    try {
      try {
        await widget.api.post('/datasets/reconcile');
      } on ApiException {
        // Listing remains available if reconciliation is temporarily unavailable.
      }
      final datasets = await widget.api.get('/datasets') as List<dynamic>;
      setState(() {
        _datasets = datasets.cast<Map<String, dynamic>>();
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

  /// Rafraîchit la liste des jeux de données sans changer l'écran affiché
  /// (utilisé après un import pour ne pas écraser le résumé de succès).
  Future<void> _refreshDatasetsInBackground() async {
    if (_refreshing) return;
    _refreshing = true;
    try {
      final datasets = await widget.api.get('/datasets') as List<dynamic>;
      if (mounted) {
        setState(() => _datasets = datasets.cast<Map<String, dynamic>>());
        _syncPolling();
      }
    } on ApiException {
      // Le résumé d'import reste affiché ; la liste sera retentée à la prochaine visite de l'écran.
    } finally {
      _refreshing = false;
    }
  }

  void _syncPolling() {
    final shouldPoll = _datasets.any((dataset) {
      final status = dataset['pipeline_status']?.toString();
      return status == 'analyzing' ||
          status == 'preparing_data' ||
          status == 'training_ai';
    });
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

  Future<void> _deleteDataset(String datasetId) async {
    if (_deletingDatasetIds.contains(datasetId)) return;
    setState(() => _deletingDatasetIds.add(datasetId));
    try {
      await widget.api.delete('/datasets/$datasetId');
      if (!mounted) return;
      setState(() {
        _datasets.removeWhere(
          (dataset) => dataset['id']?.toString() == datasetId,
        );
        _deletingDatasetIds.remove(datasetId);
      });
    } on ApiException catch (exc) {
      if (!mounted) return;
      setState(() => _deletingDatasetIds.remove(datasetId));
      ScaffoldMessenger.maybeOf(
        context,
      )?.showSnackBar(SnackBar(content: Text(exc.message)));
    } on Object {
      if (!mounted) return;
      setState(() => _deletingDatasetIds.remove(datasetId));
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        SnackBar(
          content: Text(
            AvenqoLocaleScope.translationsOf(
              context,
            ).company.connectionsGenericError,
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
            constraints: const BoxConstraints(maxWidth: 900),
            child: switch (_state) {
              _ViewState.loading => _CenteredSpinner(
                label: t.connectionsLoading,
              ),
              _ViewState.idle => _ConnectedDataView(
                datasets: _datasets,
                deletingDatasetIds: _deletingDatasetIds,
                onAddFiles: _addFiles,
                onDeleteDataset: _deleteDataset,
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

/// Panneau principal : import + dropdown de TOUS les datasets du tenant,
/// quel que soit leur statut. Chaque ligne reste supprimable indépendamment.
class _ConnectedDataView extends StatelessWidget {
  const _ConnectedDataView({
    required this.datasets,
    required this.deletingDatasetIds,
    required this.onAddFiles,
    required this.onDeleteDataset,
    required this.onViewCleaning,
    required this.onReviewMapping,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.t,
  });

  final List<Map<String, dynamic>> datasets;
  final Set<String> deletingDatasetIds;
  final VoidCallback onAddFiles;
  final Future<void> Function(String datasetId) onDeleteDataset;
  final void Function(Map<String, dynamic> dataset) onViewCleaning;
  final void Function(Map<String, dynamic> dataset) onReviewMapping;
  final VoidCallback onGoToDashboard;
  final VoidCallback onAskAvenqo;
  final CompanyStrings t;

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
                for (var i = 0; i < datasets.length; i++)
                  _DatasetRow(
                    dataset: datasets[i],
                    isLast: i == datasets.length - 1,
                    isDeleting: deletingDatasetIds.contains(
                      datasets[i]['id']?.toString(),
                    ),
                    onDeleteDataset: onDeleteDataset,
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
      ],
    );
  }
}

class _DatasetRow extends StatelessWidget {
  const _DatasetRow({
    required this.dataset,
    required this.isLast,
    required this.isDeleting,
    required this.onDeleteDataset,
    required this.onViewCleaning,
    required this.onReviewMapping,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.t,
  });

  final Map<String, dynamic> dataset;
  final bool isLast;
  final bool isDeleting;
  final Future<void> Function(String datasetId) onDeleteDataset;
  final void Function(Map<String, dynamic> dataset) onViewCleaning;
  final void Function(Map<String, dynamic> dataset) onReviewMapping;
  final VoidCallback onGoToDashboard;
  final VoidCallback onAskAvenqo;
  final CompanyStrings t;

  Future<void> _confirmDelete(BuildContext context, String id) async {
    final name = dataset['name']?.toString() ?? '—';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t.connectionsRemoveFile),
        content: Row(
          children: [
            const Icon(Icons.delete_outline, color: _Brand.red),
            const SizedBox(width: 12),
            Expanded(child: Text(name, overflow: TextOverflow.ellipsis)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(
              MaterialLocalizations.of(dialogContext).cancelButtonLabel,
            ),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: FilledButton.styleFrom(backgroundColor: _Brand.red),
            icon: const Icon(Icons.delete_outline, size: 18),
            label: Text(t.connectionsRemoveFile),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await onDeleteDataset(id);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final status =
        dataset['pipeline_status']?.toString() ?? dataset['status']?.toString();
    final id = dataset['id']?.toString();
    final isReady = status == 'ready' || status == 'validated';
    final needsAttention = status == 'attention_required';
    final isError =
        status == 'failed' || status == 'invalid' || status == 'rejected';
    final statusLabel = switch (status) {
      'ready' || 'validated' => t.connectionsReadyTitle,
      'preparing_data' => t.connectionsPreparingData,
      'training_ai' => t.connectionsTrainingAi,
      'attention_required' => t.connectionsAttentionRequired,
      'failed' || 'invalid' || 'rejected' => t.connectionsProcessingError,
      _ => t.connectionsAnalyzing,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        border: isLast ? null : Border(bottom: BorderSide(color: colors.line)),
      ),
      child: Row(
        children: [
          Icon(
            isError
                ? Icons.error_outline
                : isReady
                ? Icons.check_circle
                : Icons.hourglass_top,
            color: isError
                ? _Brand.red
                : (isReady ? _Brand.green : _Brand.blue),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
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
                const SizedBox(height: 2),
                Text(
                  statusLabel,
                  style: TextStyle(
                    color: isError
                        ? _Brand.red
                        : (isReady ? _Brand.green : _Brand.blue),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  [
                    if (dataset['rows_count'] != null)
                      '${dataset['rows_count']} ${t.connectionsStatRowsLabel.toLowerCase()}',
                    if (dataset['columns_count'] != null)
                      '${dataset['columns_count']} ${t.connectionsStatColumnsLabel.toLowerCase()}',
                    if (dataset['uploaded_at'] != null)
                      '${t.connectionsImportedAtLabel} ${dataset['uploaded_at'].toString().split('T').first}',
                  ].join(' · '),
                  style: TextStyle(color: colors.muted, fontSize: 12),
                ),
              ],
            ),
          ),
          if (isReady || needsAttention)
            IconButton(
              tooltip: t.connectionsCleaning['view'],
              onPressed: isDeleting ? null : () => onViewCleaning(dataset),
              icon: const Icon(Icons.table_view_outlined),
            ),
          if (needsAttention)
            IconButton(
              tooltip: t.connectionsMappingTitle,
              onPressed: isDeleting ? null : () => onReviewMapping(dataset),
              icon: const Icon(Icons.tune),
            ),
          if (isReady) ...[
            IconButton(
              tooltip: t.connectionsGoDashboard,
              onPressed: isDeleting ? null : onGoToDashboard,
              icon: const Icon(Icons.dashboard_outlined),
            ),
            IconButton(
              tooltip: t.connectionsAskAvenqo,
              onPressed: isDeleting ? null : onAskAvenqo,
              icon: const Icon(Icons.smart_toy_outlined),
            ),
          ],
          if (id != null) ...[
            const SizedBox(width: 4),
            if (isDeleting)
              const SizedBox(
                width: 40,
                height: 40,
                child: Padding(
                  padding: EdgeInsets.all(10),
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              )
            else
              IconButton(
                tooltip: t.connectionsRemoveFile,
                onPressed: () => _confirmDelete(context, id),
                icon: const Icon(Icons.delete_outline, color: _Brand.red),
              ),
          ],
        ],
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
  String? _error;

  Future<Map<String, dynamic>> _load() async =>
      await widget.api.get('/datasets/${widget.datasetId}/profile')
          as Map<String, dynamic>;

  void _initialize(Map<String, dynamic> profile) {
    if (_initialized) return;
    final accepted = (profile['accepted_mapping'] as Map<String, dynamic>? ?? const {});
    final conflicts = (profile['required_confirmation'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    final conflictingColumns = {
      for (final conflict in conflicts)
        for (final column in (conflict['columns'] as List<dynamic>? ?? const []))
          column.toString(),
    };
    for (final suggestion
        in (profile['mapping_suggestions'] as List<dynamic>? ?? const [])) {
      final item = suggestion as Map<String, dynamic>;
      final column = item['original_column'].toString();
      _selected[column] = conflictingColumns.contains(column)
          ? null
          : accepted[column]?.toString();
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
      final response = await widget.api.post(
        '/datasets/${widget.datasetId}/mapping',
        body: {'mapping': mapping},
      ) as Map<String, dynamic>;
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
    return AlertDialog(
      title: Text(widget.t.connectionsMappingTitle),
      content: SizedBox(
        width: 680,
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
            return SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(widget.t.connectionsMappingSubtitle),
                  const SizedBox(height: 16),
                  for (final item in suggestions) ...[
                    Text(
                      item['original_column'].toString(),
                      style: const TextStyle(fontWeight: FontWeight.w700),
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
                          for (final value
                              in (item['alternatives'] as List<dynamic>? ?? const []))
                            value.toString(),
                        })
                          DropdownMenuItem<String?>(
                            value: option,
                            child: Text(option),
                          ),
                      ],
                      onChanged: _submitting
                          ? null
                          : (value) => _selected[item['original_column'].toString()] = value,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      item['reason']?.toString() ?? '',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 14),
                  ],
                  if (_error != null)
                    Text(_error!, style: const TextStyle(color: _Brand.red)),
                ],
              ),
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: _submitting ? null : () => Navigator.of(context).pop(false),
          child: Text(MaterialLocalizations.of(context).cancelButtonLabel),
        ),
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
    return AlertDialog(
      title: Text(widget.t.connectionsCleaning['view']!),
      content: SizedBox(
        width: 820,
        height: 560,
        child: FutureBuilder<Map<String, dynamic>>(
          future: _detail,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError || snapshot.data == null) {
              return Center(child: Text(widget.t.connectionsGenericError));
            }
            final detail = snapshot.data!;
            final summary = detail['summary'] as Map<String, dynamic>;
            final isReady = detail['status'] == 'ready';
            final before = (detail['original_preview'] as List<dynamic>)
                .cast<Map<String, dynamic>>();
            final after = (detail['cleaned_preview'] as List<dynamic>)
                .cast<Map<String, dynamic>>();
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  detail['name'].toString(),
                  style: TextStyle(
                    color: colors.ink,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${isReady ? widget.t.connectionsReadyTitle : widget.t.connectionsAttentionRequired} · v${detail['version']}',
                  style: TextStyle(color: colors.muted),
                ),
                if (!isReady) ...[
                  const SizedBox(height: 8),
                  Text(
                    widget.t.connectionsMappingSubtitle,
                    style: TextStyle(color: colors.muted),
                  ),
                ],
                const SizedBox(height: 18),
                Text(
                  widget.t.connectionsCleaning['summary']!,
                  style: TextStyle(
                    color: colors.ink,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 10,
                  runSpacing: 8,
                  children: [
                    _CleaningMetric(
                      icon: Icons.table_rows_outlined,
                      value:
                          '${summary['original_row_count']} → ${summary['cleaned_row_count']} ${widget.t.connectionsStatRowsLabel.toLowerCase()}',
                    ),
                    _CleaningMetric(
                      icon: Icons.view_column_outlined,
                      value:
                          '${summary['column_count']} ${widget.t.connectionsStatColumnsLabel.toLowerCase()}',
                    ),
                    _CleaningMetric(
                      icon: Icons.content_copy_outlined,
                      value: '${summary['duplicate_rows_removed']}',
                    ),
                    _CleaningMetric(
                      icon: Icons.account_tree_outlined,
                      value:
                          '${(summary['mappings_applied'] as Map<String, dynamic>).length}',
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Expanded(
                  child: DefaultTabController(
                    length: 2,
                    child: Column(
                      children: [
                        TabBar(
                          tabs: [
                            Tab(text: widget.t.connectionsCleaning['before']),
                            Tab(text: widget.t.connectionsCleaning['after']),
                          ],
                        ),
                        Expanded(
                          child: TabBarView(
                            children: [
                              _PreviewTable(rows: before),
                              _PreviewTable(rows: after),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                if (isReady)
                  Wrap(
                    spacing: 8,
                    children: [
                      for (final format in const [
                        'CSV',
                        'XLSX',
                        'PDF',
                        'DOCX',
                      ])
                        OutlinedButton.icon(
                          onPressed: _exporting
                              ? null
                              : () => _export(format.toLowerCase()),
                          icon: const Icon(Icons.download_outlined, size: 18),
                          label: Text(format),
                        ),
                    ],
                  ),
              ],
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(MaterialLocalizations.of(context).closeButtonLabel),
        ),
      ],
    );
  }
}

class _CleaningMetric extends StatelessWidget {
  const _CleaningMetric({required this.icon, required this.value});

  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) =>
      Chip(avatar: Icon(icon, size: 16), label: Text(value));
}

class _PreviewTable extends StatelessWidget {
  const _PreviewTable({required this.rows});

  final List<Map<String, dynamic>> rows;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    final columns = rows.first.keys.take(8).toList();
    return Scrollbar(
      child: SingleChildScrollView(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: [
              for (final column in columns) DataColumn(label: Text(column)),
            ],
            rows: [
              for (final row in rows.take(20))
                DataRow(
                  cells: [
                    for (final column in columns)
                      DataCell(
                        ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 180),
                          child: Text(
                            row[column]?.toString() ?? '',
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
    );
  }
}

/// Étape de revue avant envoi : les fichiers choisis restent modifiables
/// (ajout/suppression) tant que l'utilisateur n'a pas cliqué sur "Importer".
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
