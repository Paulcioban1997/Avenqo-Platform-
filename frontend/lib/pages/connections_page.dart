import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/core/web_file_picker.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const green = Color(0xFF1B9E5A);
  static const red = Color(0xFFD1414B);
}

/// Formats acceptés par le pipeline d'ingestion universel côté backend
/// (`CompanyDatasetLoader` : CSV/XLSX/JSON/Parquet).
const _acceptedExtensions = ['csv', 'xlsx', 'json', 'parquet'];
const _defaultModuleCode = 'retail';

enum _ViewState { loading, idle, selecting, uploading, summary, mapping, error }

/// Fichier choisi par l'utilisateur, découplé de `PlatformFile` (classe `base`
/// non sous-classable hors de son package) afin de rester injectable en test.
class PickedFile {
  const PickedFile(this.name, this.bytes);
  final String name;
  final Uint8List bytes;
}

typedef FilePickerFn = Future<List<PickedFile>> Function();

Future<List<PickedFile>> _defaultFilePicker() async {
  if (kIsWeb) {
    // Flutter Web : sélecteur natif navigateur déclenché immédiatement dans
    // le handler de clic. Aucun await réseau/dialog avant — sinon le navigateur
    // rejette l'ouverture du file picker (geste utilisateur perdu).
    return WebFilePicker.pick(
      accept: '.csv,.xlsx,.json,.parquet',
      multiple: true,
    );
  }
  // Mobile/Desktop : file_picker plugin (fonctionne sur ces plateformes).
  final result = await FilePicker.pickFiles(
    type: FileType.custom,
    allowedExtensions: _acceptedExtensions,
    // ignore: deprecated_member_use — API multi-fichiers correcte pour v12.
    allowMultiple: true,
  );
  final files = <PickedFile>[];
  for (final platformFile in result) {
    files.add(PickedFile(platformFile.name, await platformFile.readAsBytes()));
  }
  return files;
}

/// Centre de gestion des données Avenqo (remplace le placeholder générique).
/// Réutilise exclusivement les endpoints existants (`/datasets`,
/// `/datasets/upload`, `/datasets/{id}/profile`, `/datasets/{id}/mapping`).
class ConnectionsPage extends StatefulWidget {
  const ConnectionsPage({
    super.key,
    required this.api,
    this.pickFiles = _defaultFilePicker,
  });
  final ApiClient api;
  final FilePickerFn pickFiles;

  @override
  State<ConnectionsPage> createState() => _ConnectionsPageState();
}

class _ConnectionsPageState extends State<ConnectionsPage> {
  _ViewState _state = _ViewState.loading;
  List<Map<String, dynamic>> _datasets = [];
  Map<String, dynamic>? _profile;
  String? _mappingDatasetId;
  String? _errorMessage;
  String? _duplicateNotice;
  final List<_PendingFile> _pending = [];
  List<_UploadItem> _uploadItems = [];
  final Map<String, String?> _mappingOverrides = {};

  @override
  void initState() {
    super.initState();
    _loadDatasets();
  }

  Future<void> _loadDatasets() async {
    setState(() => _state = _ViewState.loading);
    try {
      final datasets = await widget.api.get('/datasets') as List<dynamic>;
      setState(() {
        _datasets = datasets.cast<Map<String, dynamic>>();
        _state = _ViewState.idle;
      });
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
    try {
      final datasets = await widget.api.get('/datasets') as List<dynamic>;
      if (mounted) {
        setState(() => _datasets = datasets.cast<Map<String, dynamic>>());
      }
    } on ApiException {
      // Le résumé d'import reste affiché ; la liste sera retentée à la prochaine visite de l'écran.
    }
  }

  Future<void> _loadProfile(String datasetId) async {
    try {
      _profile =
          await widget.api.get('/datasets/$datasetId/profile')
              as Map<String, dynamic>;
      _mappingOverrides.clear();
    } on ApiException catch (exc) {
      setState(() {
        _errorMessage = exc.message;
        _state = _ViewState.error;
      });
    }
  }

  Future<void> _openMapping(String datasetId) async {
    setState(() => _mappingDatasetId = datasetId);
    await _loadProfile(datasetId);
    if (mounted) setState(() => _state = _ViewState.mapping);
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
            _uploadItems[i].mappingRequired =
                response['status']?.toString() == 'mapping_required';
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

  Future<void> _submitMapping() async {
    final datasetId = _mappingDatasetId;
    if (datasetId == null) return;
    final overrides = <String, String>{
      for (final entry in _mappingOverrides.entries)
        if (entry.value != null) entry.key: entry.value!,
    };
    try {
      await widget.api.post(
        '/datasets/$datasetId/mapping',
        body: {'mapping': overrides},
      );
      await _loadDatasets();
    } on ApiException catch (exc) {
      setState(() {
        _errorMessage = exc.message;
        _state = _ViewState.error;
      });
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
                onAddFiles: _addFiles,
                onCompleteMapping: _openMapping,
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
              _ViewState.mapping => _MappingView(
                profile: _profile,
                overrides: _mappingOverrides,
                onChanged: (column, field) =>
                    setState(() => _mappingOverrides[column] = field),
                onSubmit: _submitMapping,
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
  bool mappingRequired = false;
  String? datasetId;
  String? error;
}

/// Panneau principal : liste des données déjà connectées pour ce tenant
/// (jamais masquée, même vide) et bouton "Ajouter des fichiers" toujours
/// disponible pour permettre l'import de plusieurs jeux de données distincts
/// (ventes, clients, produits...).
class _ConnectedDataView extends StatelessWidget {
  const _ConnectedDataView({
    required this.datasets,
    required this.onAddFiles,
    required this.onCompleteMapping,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.t,
  });

  final List<Map<String, dynamic>> datasets;
  final VoidCallback onAddFiles;
  final void Function(String datasetId) onCompleteMapping;
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
          Text(
            t.connectionsConnectedDataTitle,
            style: TextStyle(
              color: colors.ink,
              fontSize: 16,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 12),
          Container(
            decoration: BoxDecoration(
              color: colors.surface,
              border: Border.all(color: colors.line),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              children: [
                for (var i = 0; i < datasets.length; i++)
                  _DatasetRow(
                    dataset: datasets[i],
                    isLast: i == datasets.length - 1,
                    onCompleteMapping: onCompleteMapping,
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
    required this.onCompleteMapping,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.t,
  });

  final Map<String, dynamic> dataset;
  final bool isLast;
  final void Function(String datasetId) onCompleteMapping;
  final VoidCallback onGoToDashboard;
  final VoidCallback onAskAvenqo;
  final CompanyStrings t;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final status = dataset['status']?.toString();
    final id = dataset['id']?.toString();
    final isReady = status == 'ready' || status == 'validated';
    final isMappingRequired = status == 'mapping_required';
    final isError =
        status == 'failed' || status == 'invalid' || status == 'rejected';
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
                : isMappingRequired
                ? Icons.rule_outlined
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
          if (isMappingRequired && id != null)
            TextButton(
              onPressed: () => onCompleteMapping(id),
              child: Text(t.connectionsMappingRequiredBadge),
            )
          else if (isReady) ...[
            IconButton(
              tooltip: t.connectionsGoDashboard,
              onPressed: onGoToDashboard,
              icon: const Icon(Icons.dashboard_outlined),
            ),
            IconButton(
              tooltip: t.connectionsAskAvenqo,
              onPressed: onAskAvenqo,
              icon: const Icon(Icons.smart_toy_outlined),
            ),
          ],
        ],
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

class _MappingView extends StatelessWidget {
  const _MappingView({
    required this.profile,
    required this.overrides,
    required this.onChanged,
    required this.onSubmit,
    required this.t,
  });

  final Map<String, dynamic>? profile;
  final Map<String, String?> overrides;
  final void Function(String column, String? field) onChanged;
  final VoidCallback onSubmit;
  final CompanyStrings t;

  static const _canonicalFields = [
    'customer_id',
    'order_id',
    'product_id',
    'order_timestamp',
    'quantity',
    'unit_price',
    'total_amount',
    'review_text',
    'review_score',
    'churn_flag',
  ];

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final suggestions =
        (profile?['mapping_suggestions'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>();
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
          Text(
            t.connectionsMappingTitle,
            style: TextStyle(
              color: colors.ink,
              fontSize: 18,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            t.connectionsMappingSubtitle,
            style: TextStyle(color: colors.muted),
          ),
          const SizedBox(height: 20),
          for (final suggestion in suggestions)
            _MappingRow(
              suggestion: suggestion,
              canonicalFields: _canonicalFields,
              selected:
                  overrides[suggestion['original_column']?.toString()] ??
                  suggestion['suggested_field']?.toString(),
              onChanged: (field) =>
                  onChanged(suggestion['original_column'].toString(), field),
              ignoreLabel: t.connectionsMappingIgnore,
            ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: onSubmit,
            style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
            child: Text(t.connectionsConfirmMapping),
          ),
        ],
      ),
    );
  }
}

class _MappingRow extends StatelessWidget {
  const _MappingRow({
    required this.suggestion,
    required this.canonicalFields,
    required this.selected,
    required this.onChanged,
    required this.ignoreLabel,
  });

  final Map<String, dynamic> suggestion;
  final List<String> canonicalFields;
  final String? selected;
  final void Function(String? field) onChanged;
  final String ignoreLabel;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final column = suggestion['original_column']?.toString() ?? '';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Text(
              column,
              style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600),
            ),
          ),
          const Icon(Icons.arrow_forward, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: canonicalFields.contains(selected)
                  ? selected
                  : null,
              hint: Text(ignoreLabel),
              isExpanded: true,
              items: [
                for (final field in canonicalFields)
                  DropdownMenuItem(value: field, child: Text(field)),
              ],
              onChanged: onChanged,
            ),
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
