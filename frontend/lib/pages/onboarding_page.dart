import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';

class _Brand {
  const _Brand._();
  static const blue = Color(0xFF087CF0);
  static const ink = Color(0xFF080B12);
}

/// Questionnaire d'onboarding affiché après la première connexion (statut
/// `pending`). Persiste directement via `auth.api` (comme `AdminDashboardPage`)
/// plutôt que via des méthodes dédiées sur `AuthController`, puisqu'il s'agit
/// d'un écran isolé et ponctuel.
class OnboardingPage extends StatefulWidget {
  const OnboardingPage({super.key, required this.auth});

  final AuthController auth;

  @override
  State<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends State<OnboardingPage> {
  final Set<String> _selectedGoals = {};
  final Set<String> _selectedTools = {};
  String? _teamSize;
  final _industryController = TextEditingController();
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    _industryController.dispose();
    super.dispose();
  }

  List<(String, String)> _goals(OnboardingStrings t) => [
        ('increase_sales', t.goalIncreaseSales),
        ('reduce_churn', t.goalReduceChurn),
        ('optimize_pricing', t.goalOptimizePricing),
        ('improve_inventory', t.goalImproveInventory),
        ('understand_customers', t.goalUnderstandCustomers),
        ('automate_reports', t.goalAutomateReports),
      ];

  List<(String, String)> _tools(OnboardingStrings t) => [
        ('pos', t.toolPos),
        ('ecommerce', t.toolEcommerce),
        ('spreadsheets', t.toolSpreadsheets),
        ('accounting', t.toolAccounting),
        ('crm', t.toolCrm),
        ('none', t.toolNone),
      ];

  List<(String, String)> _teamSizes(OnboardingStrings t) => [
        ('solo', t.teamSizeSolo),
        ('2_10', t.teamSizeSmall),
        ('11_50', t.teamSizeMedium),
        ('50_plus', t.teamSizeLarge),
      ];

  Future<void> _submit(OnboardingStrings t, {String destination = '/dashboard'}) async {
    if (_selectedGoals.isEmpty) {
      setState(() => _error = t.goalsRequired);
      return;
    }
    if (_teamSize == null) {
      setState(() => _error = t.teamSizeRequired);
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.auth.api.post(
        '/onboarding/complete',
        body: {
          'business_goals': _selectedGoals.toList(),
          'current_tools': _selectedTools.toList(),
          'team_size': _teamSize,
          if (_industryController.text.trim().isNotEmpty)
            'refined_industry': _industryController.text.trim(),
        },
      );
      await widget.auth.refreshAccount();
      if (mounted) context.go(destination);
    } on ApiException {
      if (mounted) setState(() => _error = t.genericError);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _skip(OnboardingStrings t) async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.auth.api.post('/onboarding/skip');
      await widget.auth.refreshAccount();
      if (mounted) context.go('/dashboard');
    } on ApiException {
      if (mounted) setState(() => _error = t.genericError);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).onboarding;
    final colors = AvenqoColors.of(context);
    final wide = MediaQuery.sizeOf(context).width >= 900;

    final form = ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 640),
      child: SingleChildScrollView(
        padding: EdgeInsets.all(wide ? 40 : 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _StepProgress(colors: colors),
            const SizedBox(height: 20),
            Text(
              t.title,
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: colors.ink),
            ),
            const SizedBox(height: 8),
            Text(t.subtitle, style: TextStyle(color: colors.muted, fontSize: 15)),
            const SizedBox(height: 28),
            Text(t.goalsLabel, style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                for (final (code, label) in _goals(t))
                  FilterChip(
                    label: Text(label),
                    selected: _selectedGoals.contains(code),
                    onSelected: _submitting
                        ? null
                        : (selected) => setState(() {
                              if (selected) {
                                _selectedGoals.add(code);
                              } else {
                                _selectedGoals.remove(code);
                              }
                            }),
                  ),
              ],
            ),
            const SizedBox(height: 24),
            Text(t.toolsLabel, style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                for (final (code, label) in _tools(t))
                  FilterChip(
                    label: Text(label),
                    selected: _selectedTools.contains(code),
                    onSelected: _submitting
                        ? null
                        : (selected) => setState(() {
                              if (selected) {
                                _selectedTools.add(code);
                              } else {
                                _selectedTools.remove(code);
                              }
                            }),
                  ),
              ],
            ),
            const SizedBox(height: 24),
            Text(t.teamSizeLabel, style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                for (final (code, label) in _teamSizes(t))
                  ChoiceChip(
                    label: Text(label),
                    selected: _teamSize == code,
                    onSelected: _submitting ? null : (_) => setState(() => _teamSize = code),
                  ),
              ],
            ),
            const SizedBox(height: 24),
            Text(t.refineIndustryLabel, style: TextStyle(fontWeight: FontWeight.w700, color: colors.ink)),
            const SizedBox(height: 10),
            TextField(
              controller: _industryController,
              enabled: !_submitting,
              decoration: InputDecoration(
                hintText: t.refineIndustryHint,
                filled: true,
                fillColor: colors.surface,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: BorderSide(color: colors.line),
                ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(_error!, style: const TextStyle(color: Colors.redAccent)),
            ],
            const SizedBox(height: 32),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                FilledButton(
                  onPressed: _submitting ? null : () => _submit(t),
                  style: FilledButton.styleFrom(backgroundColor: _Brand.blue),
                  child: _submitting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : Text(t.continueCta),
                ),
                OutlinedButton.icon(
                  onPressed: _submitting ? null : () => _submit(t, destination: '/connections'),
                  icon: const Icon(Icons.upload_file, size: 18),
                  label: const Text('Charger mes données'),
                ),
                TextButton(
                  onPressed: _submitting ? null : () => _skip(t),
                  child: Text(t.skipCta, style: const TextStyle(color: _Brand.ink)),
                ),
              ],
            ),
          ],
        ),
      ),
    );

    return Scaffold(
      backgroundColor: colors.canvas,
      body: SafeArea(
        child: wide
            ? Row(
                children: [
                  Expanded(flex: 3, child: Center(child: form)),
                  Expanded(flex: 2, child: _OnboardingValuePanel()),
                ],
              )
            : Center(child: form),
      ),
    );
  }
}

class _StepProgress extends StatelessWidget {
  const _StepProgress({required this.colors});

  final AvenqoColors colors;

  @override
  Widget build(BuildContext context) {
    const steps = ['Organisation', 'Configuration', 'Données', 'Prêt'];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < steps.length; i++) ...[
            Container(
              width: 22,
              height: 22,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: i <= 1 ? _Brand.blue : colors.line,
                shape: BoxShape.circle,
              ),
              child: Text(
                '${i + 1}',
                style: TextStyle(color: i <= 1 ? Colors.white : colors.muted, fontSize: 11, fontWeight: FontWeight.w700),
              ),
            ),
            const SizedBox(width: 6),
            Text(
              steps[i],
              style: TextStyle(
                color: i <= 1 ? colors.ink : colors.muted,
                fontWeight: i == 1 ? FontWeight.w700 : FontWeight.w500,
                fontSize: 12.5,
              ),
            ),
            if (i != steps.length - 1) ...[
              const SizedBox(width: 8),
              Container(width: 16, height: 1, color: colors.line),
              const SizedBox(width: 8),
            ],
          ],
        ],
      ),
    );
  }
}

class _OnboardingValuePanel extends StatelessWidget {
  const _OnboardingValuePanel();

  static const _items = [
    ('Conversation IA', Icons.auto_awesome),
    ('Données isolées par entreprise', Icons.lock_outline),
    ('Modules optionnels', Icons.extension_outlined),
    ('Analyses & recommandations', Icons.insights_outlined),
    ('Quotas IA', Icons.speed_outlined),
    ('Administration & équipe', Icons.group_outlined),
    ('Connexions sécurisées', Icons.sync_alt),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      color: _Brand.ink,
      padding: const EdgeInsets.all(40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text(
            'Ce que vous activez avec Avenqo',
            style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 24),
          for (final (label, icon) in _items)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(color: _Brand.blue.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(9)),
                    child: Icon(icon, color: _Brand.blue, size: 16),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: Text(label, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13.5))),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
