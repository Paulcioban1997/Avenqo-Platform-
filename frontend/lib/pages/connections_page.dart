import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/core/api_client.dart';

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

enum _ViewState { loading, noData, uploading, mapping, processing, ready, error }

/// Centre de gestion des données Avenqo (remplace le placeholder générique).
/// Réutilise exclusivement les endpoints existants (`/datasets`,
/// `/datasets/upload`, `/datasets/{id}/profile`, `/datasets/{id}/mapping`).
class ConnectionsPage extends StatefulWidget {
  const ConnectionsPage({super.key, required this.api});
  final ApiClient api;

  @override
  State<ConnectionsPage> createState() => _ConnectionsPageState();
}

class _ConnectionsPageState extends State<ConnectionsPage> {
  _ViewState _state = _ViewState.loading;
  Map<String, dynamic>? _dataset;
  Map<String, dynamic>? _profile;
  String? _errorMessage;
  String? _selectedFileName;
  int? _selectedFileSize;
  double? _uploadProgress;
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
      if (datasets.isEmpty) {
        setState(() {
          _dataset = null;
          _state = _ViewState.noData;
        });
        return;
      }
      final latest = datasets.first as Map<String, dynamic>;
      await _applyDatasetStatus(latest);
    } on ApiException catch (exc) {
      setState(() {
        _errorMessage = exc.message;
        _state = _ViewState.error;
      });
    }
  }

  Future<void> _applyDatasetStatus(Map<String, dynamic> dataset) async {
    _dataset = dataset;
    final status = dataset['status']?.toString();
    switch (status) {
      case 'mapping_required':
        await _loadProfile(dataset['id'].toString());
        setState(() => _state = _ViewState.mapping);
      case 'ready':
      case 'validated':
        setState(() => _state = _ViewState.ready);
      case 'failed':
      case 'invalid':
      case 'rejected':
        setState(() {
          _errorMessage = "Ce fichier n'a pas pu être traité.";
          _state = _ViewState.error;
        });
      default:
        setState(() => _state = _ViewState.processing);
    }
  }

  Future<void> _loadProfile(String datasetId) async {
    try {
      _profile = await widget.api.get('/datasets/$datasetId/profile') as Map<String, dynamic>;
      _mappingOverrides.clear();
    } on ApiException catch (exc) {
      setState(() {
        _errorMessage = exc.message;
        _state = _ViewState.error;
      });
    }
  }

  Future<void> _pickAndUploadFile() async {
    final files = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: _acceptedExtensions,
      allowMultiple: false,
    );
    if (files.isEmpty) return;
    final picked = files.first;
    final bytes = await picked.readAsBytes();
    if (bytes.isEmpty) {
      setState(() {
        _errorMessage = 'Le fichier sélectionné est vide ou illisible.';
        _state = _ViewState.error;
      });
      return;
    }
    await _upload(picked.name, bytes);
  }

  Future<void> _upload(String fileName, Uint8List bytes) async {
    setState(() {
      _selectedFileName = fileName;
      _selectedFileSize = bytes.length;
      _uploadProgress = 0;
      _errorMessage = null;
      _state = _ViewState.uploading;
    });
    try {
      final response = await widget.api.postMultipart(
        '/datasets/upload',
        fields: const {'module_code': _defaultModuleCode},
        fileBytes: bytes,
        fileName: fileName,
        onProgress: (sent, total) {
          if (total > 0 && mounted) {
            setState(() => _uploadProgress = sent / total);
          }
        },
      ) as Map<String, dynamic>;
      final datasetId = response['dataset_id']?.toString();
      if (datasetId == null) {
        setState(() => _state = _ViewState.error);
        return;
      }
      final dataset = await widget.api.get('/datasets/$datasetId') as Map<String, dynamic>;
      await _applyDatasetStatus(dataset);
    } on ApiException catch (exc) {
      setState(() {
        _errorMessage = exc.message;
        _state = _ViewState.error;
      });
    }
  }

  Future<void> _submitMapping() async {
    final datasetId = _dataset?['id']?.toString();
    if (datasetId == null) return;
    final overrides = <String, String>{
      for (final entry in _mappingOverrides.entries)
        if (entry.value != null) entry.key: entry.value!,
    };
    setState(() => _state = _ViewState.processing);
    try {
      await widget.api.post('/datasets/$datasetId/mapping', body: {'mapping': overrides});
      final dataset = await widget.api.get('/datasets/$datasetId') as Map<String, dynamic>;
      await _applyDatasetStatus(dataset);
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
    return Container(
      color: colors.canvas,
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: switch (_state) {
              _ViewState.loading => const _CenteredSpinner(label: 'Chargement…'),
              _ViewState.noData => _NoDataView(onImport: _pickAndUploadFile),
              _ViewState.uploading => _UploadingView(
                  fileName: _selectedFileName,
                  fileSize: _selectedFileSize,
                  progress: _uploadProgress,
                ),
              _ViewState.processing => const _CenteredSpinner(
                  label: 'Analyse de la structure de vos données…',
                ),
              _ViewState.mapping => _MappingView(
                  profile: _profile,
                  overrides: _mappingOverrides,
                  onChanged: (column, field) => setState(() => _mappingOverrides[column] = field),
                  onSubmit: _submitMapping,
                ),
              _ViewState.ready => _ReadyView(
                  dataset: _dataset,
                  onGoToDashboard: () => context.go('/dashboard'),
                  onAskAvenqo: () => context.go('/assistant'),
                  onImportAnother: _pickAndUploadFile,
                ),
              _ViewState.error => _ErrorView(
                  message: _errorMessage ?? 'Une erreur inattendue est survenue.',
                  onRetry: _loadDatasets,
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

class _NoDataView extends StatelessWidget {
  const _NoDataView({required this.onImport});
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Container(
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
            child: const Icon(Icons.cloud_upload_outlined, color: _Brand.blue, size: 28),
          ),
          const SizedBox(height: 18),
          Text(
            'Connectez vos données pour activer les analyses et l\'IA Avenqo.',
            textAlign: TextAlign.center,
            style: TextStyle(color: colors.ink, fontSize: 17, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Text(
            'Formats acceptés : CSV, XLSX, JSON, Parquet.',
            style: TextStyle(color: colors.muted),
          ),
          const SizedBox(height: 22),
          FilledButton.icon(
            onPressed: onImport,
            style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
            icon: const Icon(Icons.upload_file, size: 18),
            label: const Text('Importer un fichier'),
          ),
        ],
      ),
    );
  }
}

class _UploadingView extends StatelessWidget {
  const _UploadingView({required this.fileName, required this.fileSize, required this.progress});
  final String? fileName;
  final int? fileSize;
  final double? progress;

  String _formatSize(int? bytes) {
    if (bytes == null) return '';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} Ko';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} Mo';
  }

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
          Row(
            children: [
              const Icon(Icons.insert_drive_file_outlined, color: _Brand.blue),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  '${fileName ?? "fichier"} · ${_formatSize(fileSize)}',
                  style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          LinearProgressIndicator(value: progress != null && progress! > 0 ? progress : null),
          const SizedBox(height: 12),
          Text('Envoi en cours…', style: TextStyle(color: colors.muted)),
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
  });

  final Map<String, dynamic>? profile;
  final Map<String, String?> overrides;
  final void Function(String column, String? field) onChanged;
  final VoidCallback onSubmit;

  static const _canonicalFields = [
    'customer_id', 'order_id', 'product_id', 'order_timestamp', 'quantity',
    'unit_price', 'total_amount', 'review_text', 'review_score', 'churn_flag',
  ];

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final suggestions = (profile?['mapping_suggestions'] as List<dynamic>? ?? const [])
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
            'Confirmez la correspondance de vos colonnes',
            style: TextStyle(color: colors.ink, fontSize: 18, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          Text(
            "Certaines colonnes nécessitent une confirmation manuelle avant l'activation des analyses.",
            style: TextStyle(color: colors.muted),
          ),
          const SizedBox(height: 20),
          for (final suggestion in suggestions) _MappingRow(
            suggestion: suggestion,
            canonicalFields: _canonicalFields,
            selected: overrides[suggestion['original_column']?.toString()] ??
                suggestion['suggested_field']?.toString(),
            onChanged: (field) => onChanged(suggestion['original_column'].toString(), field),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: onSubmit,
            style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
            child: const Text('Confirmer la correspondance'),
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
  });

  final Map<String, dynamic> suggestion;
  final List<String> canonicalFields;
  final String? selected;
  final void Function(String? field) onChanged;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final column = suggestion['original_column']?.toString() ?? '';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Text(column, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w600)),
          ),
          const Icon(Icons.arrow_forward, size: 16),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: canonicalFields.contains(selected) ? selected : null,
              hint: const Text('Ignorer cette colonne'),
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

class _ReadyView extends StatelessWidget {
  const _ReadyView({
    required this.dataset,
    required this.onGoToDashboard,
    required this.onAskAvenqo,
    required this.onImportAnother,
  });

  final Map<String, dynamic>? dataset;
  final VoidCallback onGoToDashboard;
  final VoidCallback onAskAvenqo;
  final VoidCallback onImportAnother;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final data = dataset ?? const <String, dynamic>{};
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
              const Icon(Icons.check_circle, color: _Brand.green),
              const SizedBox(width: 10),
              Text(
                'Données prêtes',
                style: TextStyle(color: colors.ink, fontSize: 18, fontWeight: FontWeight.w800),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 24,
            runSpacing: 12,
            children: [
              _Stat(label: 'Nom', value: data['name']?.toString() ?? '—'),
              _Stat(label: 'Lignes', value: '${data['rows_count'] ?? '—'}'),
              _Stat(label: 'Colonnes', value: '${data['columns_count'] ?? '—'}'),
              _Stat(label: 'Dernière mise à jour', value: data['uploaded_at']?.toString().split('T').first ?? '—'),
            ],
          ),
          const SizedBox(height: 24),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              FilledButton(
                onPressed: onGoToDashboard,
                style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
                child: const Text("Aller au tableau de bord"),
              ),
              OutlinedButton(onPressed: onAskAvenqo, child: const Text('Demander à Avenqo AI')),
              OutlinedButton(onPressed: onImportAnother, child: const Text('Importer un autre dataset')),
            ],
          ),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: colors.muted, fontSize: 12)),
        const SizedBox(height: 2),
        Text(value, style: TextStyle(color: colors.ink, fontWeight: FontWeight.w700)),
      ],
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

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
          Text(message, textAlign: TextAlign.center, style: TextStyle(color: colors.ink)),
          const SizedBox(height: 16),
          OutlinedButton(onPressed: onRetry, child: const Text('Réessayer')),
        ],
      ),
    );
  }
}
