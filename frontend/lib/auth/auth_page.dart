import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:avenqo/widgets/language_selector.dart';
import 'package:avenqo/widgets/theme_toggle_button.dart';

enum AuthMode { login, register, forgot, verify, reset }

/// Palette Avenqo, alignée sur lib/pages/home_page.dart (source de vérité
/// visuelle) : même bleu/encre que la landing page. `blue`/`blueDark`/`ink`
/// sont l'accent de marque fixe (ink sert uniquement au panneau héro sombre
/// _BrandPanel) ; le texte/fond de contenu passe par [AvenqoColors.of].
class _Brand {
  const _Brand._();

  static const blue = Color(0xFF087CF0);
  static const blueDark = Color(0xFF0757C9);
  static const ink = Color(0xFF080B12);
}

class AuthPage extends StatefulWidget {
  const AuthPage({super.key, required this.auth, required this.mode});

  final AuthController auth;
  final AuthMode mode;

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _token = TextEditingController();
  final _company = TextEditingController();
  final _companyEmail = TextEditingController();
  final _firstName = TextEditingController();
  final _lastName = TextEditingController();
  final _website = TextEditingController();
  final _country = TextEditingController(text: 'Canada');
  final _region = TextEditingController(text: 'North America');
  final _companySize = TextEditingController();
  final _jobTitle = TextEditingController();
  final _phone = TextEditingController();
  final _passwordConfirmation = TextEditingController();
  int _signupStep = 0;
  String _signupIndustry = 'Retail';
  String _signupPlan = 'demo';
  final _signupModules = <String>{};
  String? _message;
  bool _isError = false;
  bool _obscurePassword = true;

  @override
  void dispose() {
    for (final controller in [
      _email,
      _password,
      _token,
      _company,
      _companyEmail,
      _firstName,
      _lastName,
      _website,
      _country,
      _region,
      _companySize,
      _jobTitle,
      _phone,
      _passwordConfirmation,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  ({String title, String subtitle}) _copy(AuthStrings t) =>
      switch (widget.mode) {
        AuthMode.login => (title: t.loginTitle, subtitle: t.loginSubtitle),
        AuthMode.register => (
          title: t.registerTitle,
          subtitle: t.registerSubtitle,
        ),
        AuthMode.forgot => (title: t.forgotTitle, subtitle: t.forgotSubtitle),
        AuthMode.verify => (title: t.verifyTitle, subtitle: t.verifySubtitle),
        AuthMode.reset => (title: t.resetTitle, subtitle: t.resetSubtitle),
      };

  Future<void> _submit(AuthStrings t) async {
    if (!_formKey.currentState!.validate()) return;
    if (widget.mode == AuthMode.register &&
        _signupStep == 3 &&
        _password.text != _passwordConfirmation.text) {
      _show(t.genericError, isError: true);
      return;
    }
    setState(() => _message = null);
    try {
      switch (widget.mode) {
        case AuthMode.login:
          await widget.auth.login(_email.text, _password.text);
          if (mounted) context.go('/dashboard');
        case AuthMode.register:
          if (_signupStep < 4) {
            setState(() => _signupStep++);
            return;
          }
          await widget.auth.register(_signupPayload());
          if (mounted) context.go('/billing');
        case AuthMode.forgot:
          await widget.auth.forgotPassword(_email.text);
          _show(t.forgotSuccess);
        case AuthMode.verify:
          await widget.auth.verifyEmail(_token.text);
          _show(t.verifySuccess);
        case AuthMode.reset:
          await widget.auth.resetPassword(_token.text, _password.text);
          _show(t.resetSuccess);
      }
    } on ApiException catch (error) {
      _show(error.message, isError: true);
    } catch (error) {
      // Erreur non-métier (réseau, CORS, parsing...) : on log le détail en
      // dev pour pouvoir diagnostiquer sans jamais l'exposer à l'utilisateur.
      debugPrint('AuthPage._submit: unexpected error: $error');
      _show(t.genericError, isError: true);
    }
  }

  Map<String, dynamic> _signupPayload() => {
    'company_name': _company.text,
    'company_email': _companyEmail.text,
    'billing_email': _companyEmail.text,
    'first_name': _firstName.text,
    'last_name': _lastName.text,
    'job_title': _jobTitle.text,
    'phone': _phone.text,
    'email': _email.text,
    'password': _password.text,
    'country': _country.text,
    'region': _region.text,
    'company_size': _companySize.text,
    'preferred_language': Localizations.localeOf(context).languageCode,
    'timezone': 'America/Toronto',
    'industry': _signupIndustry,
    'plan_code': _signupPlan,
    'selected_modules': _signupModules.toList(),
  };

  void _show(String message, {bool isError = false}) {
    if (!mounted) return;
    setState(() {
      _message = message;
      _isError = isError;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context).auth;
    final copy = _copy(t);
    return Scaffold(
      backgroundColor: AvenqoColors.of(context).canvas,
      body: SafeArea(
        child: Column(
          children: [
            const _AuthHeader(),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final wide = constraints.maxWidth > 980;
                  final form = _FormCard(
                    title: copy.title,
                    subtitle: copy.subtitle,
                    child: _buildForm(t),
                  );
                  if (!wide) {
                    return SingleChildScrollView(
                      padding: const EdgeInsets.all(20),
                      child: form,
                    );
                  }
                  return Row(
                    children: [
                      Expanded(child: _BrandPanel(tagline: t.tagline)),
                      Expanded(
                        child: Center(
                          child: SingleChildScrollView(
                            padding: const EdgeInsets.all(32),
                            child: ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 760),
                              child: form,
                            ),
                          ),
                        ),
                      ),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildForm(AuthStrings t) {
    if (widget.mode == AuthMode.register) return _buildSignupForm(t);
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.mode == AuthMode.register) ...[
            _field(_company, t.organisation, t: t),
            _field(_companyEmail, t.billingEmail, t: t, email: true),
            Row(
              children: [
                Expanded(child: _field(_firstName, t.firstName, t: t)),
                const SizedBox(width: 12),
                Expanded(child: _field(_lastName, t.lastName, t: t)),
              ],
            ),
          ],
          if ([
            AuthMode.login,
            AuthMode.register,
            AuthMode.forgot,
          ].contains(widget.mode))
            _field(_email, t.email, t: t, email: true),
          if ([
            AuthMode.login,
            AuthMode.register,
            AuthMode.reset,
          ].contains(widget.mode))
            _field(_password, t.password, t: t, password: true),
          if ([AuthMode.verify, AuthMode.reset].contains(widget.mode))
            _field(_token, t.emailToken, t: t),
          if (_message != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: _isError
                    ? const Color(0xFFFFF4F2)
                    : const Color(0xFFF0FBF6),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                _message!,
                style: TextStyle(
                  color: _isError
                      ? const Color(0xFFB42318)
                      : const Color(0xFF1B7A4A),
                  fontSize: 13,
                ),
              ),
            ),
            const SizedBox(height: 14),
          ],
          FilledButton(
            onPressed: widget.auth.busy ? null : () => _submit(t),
            style: FilledButton.styleFrom(
              backgroundColor: _Brand.blue,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            child: widget.auth.busy
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : Text(
                    _copy(t).title,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
          ),
          if (widget.mode == AuthMode.login) ...[
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => context.go('/forgot-password'),
              child: Text(
                t.forgotPassword,
                style: TextStyle(color: AvenqoColors.of(context).muted),
              ),
            ),
            TextButton(
              onPressed: () => context.go('/register'),
              child: Text(
                t.createOrganisation,
                style: const TextStyle(
                  color: _Brand.blueDark,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
          if (widget.mode != AuthMode.login) ...[
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => context.go('/login'),
              child: Text(
                t.backToLogin,
                style: const TextStyle(
                  color: _Brand.blueDark,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSignupForm(AuthStrings t) {
    final translations = AvenqoLocaleScope.translationsOf(context);
    final onboarding = translations.onboarding;
    final steps = [
      t.organisation,
      translations.pricing.kicker,
      translations.steps.items[1].title,
      t.registerTitle,
      translations.finalCta.label,
    ];
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _SignupProgress(step: _signupStep, labels: steps),
          const SizedBox(height: 24),
          switch (_signupStep) {
            0 => _signupOrganisation(t, onboarding),
            1 => _signupPlans(translations.pricing),
            2 => _signupModulesStep(translations),
            3 => _signupOwner(t),
            _ => _signupConfirmation(t, translations),
          },
          const SizedBox(height: 24),
          if (_message != null) ...[
            Text(
              _message!,
              style: TextStyle(
                color: _isError ? Colors.redAccent : Colors.green,
              ),
            ),
            const SizedBox(height: 12),
          ],
          Row(
            children: [
              if (_signupStep > 0)
                TextButton(
                  onPressed: widget.auth.busy
                      ? null
                      : () => setState(() => _signupStep--),
                  child: Text(t.backToLogin),
                ),
              const Spacer(),
              FilledButton(
                onPressed: widget.auth.busy ? null : () => _submit(t),
                child: widget.auth.busy
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : Text(
                        _signupStep == 4
                            ? t.registerTitle
                            : onboarding.continueCta,
                      ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _signupOrganisation(AuthStrings t, OnboardingStrings onboarding) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _field(_company, t.organisation, t: t),
          _field(_website, 'Website (optional)', t: t, optional: true),
          DropdownButtonFormField<String>(
            initialValue: _signupIndustry,
            decoration: InputDecoration(
              labelText: onboarding.refineIndustryLabel,
            ),
            items:
                const [
                      'Retail',
                      'E-commerce',
                      'Professional Services',
                      'Technology',
                      'Manufacturing',
                      'Healthcare',
                      'Other',
                    ]
                    .map(
                      (value) =>
                          DropdownMenuItem(value: value, child: Text(value)),
                    )
                    .toList(),
            onChanged: (value) =>
                setState(() => _signupIndustry = value ?? _signupIndustry),
          ),
          const SizedBox(height: 14),
          _field(_companySize, onboarding.teamSizeLabel, t: t),
          _field(_country, 'Country', t: t),
          _field(_region, 'Region', t: t),
          _field(_companyEmail, t.billingEmail, t: t, email: true),
        ],
      );

  Widget _signupModulesStep(Translations translations) {
    final colors = AvenqoColors.of(context);
    final limit = _moduleLimit;
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
                    translations.steps.items[1].title,
                    style: TextStyle(
                      color: colors.ink,
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    translations.steps.items[1].text,
                    style: TextStyle(color: colors.muted, height: 1.4),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: _Brand.blue.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                '${_signupModules.length} / $limit',
                style: const TextStyle(
                  color: _Brand.blueDark,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        LayoutBuilder(
          builder: (context, constraints) {
            final columns = constraints.maxWidth >= 560 ? 2 : 1;
            const spacing = 12.0;
            final width =
                (constraints.maxWidth - spacing * (columns - 1)) / columns;
            return Wrap(
              spacing: spacing,
              runSpacing: spacing,
              children: [
                for (final module in avenqoAgentRegistry)
                  SizedBox(
                    width: width,
                    child: _SignupModuleCard(
                      key: ValueKey('signup-module-${module.id}'),
                      module: module,
                      strings: translations.agents,
                      selected: _signupModules.contains(module.id),
                      onTap: () => _toggleModule(module.id),
                    ),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }

  int get _moduleLimit => switch (_signupPlan) {
    'demo' => 2,
    'professional' => 8,
    _ => avenqoAgentRegistry.length,
  };

  void _toggleModule(String moduleId) {
    setState(() {
      if (!_signupModules.remove(moduleId) &&
          _signupModules.length < _moduleLimit) {
        _signupModules.add(moduleId);
      }
    });
  }

  Widget _signupOwner(AuthStrings t) => Column(
    children: [
      Row(
        children: [
          Expanded(child: _field(_firstName, t.firstName, t: t)),
          const SizedBox(width: 12),
          Expanded(child: _field(_lastName, t.lastName, t: t)),
        ],
      ),
      _field(_jobTitle, 'Role / title', t: t),
      _field(_email, t.email, t: t, email: true),
      _field(_password, t.password, t: t, password: true),
      _field(_passwordConfirmation, 'Confirm password', t: t, password: true),
      _field(_phone, 'Phone (optional)', t: t, optional: true),
    ],
  );

  Widget _signupPlans(PricingStrings pricing) => Column(
    children: [
      for (var index = 0; index < pricing.plans.length; index++)
        Card(
          color: _signupPlan == _planCode(index)
              ? Theme.of(context).colorScheme.primaryContainer
              : null,
          child: ListTile(
            onTap: () => setState(() {
              _signupPlan = _planCode(index);
              final retained = _signupModules.take(_moduleLimit).toSet();
              _signupModules
                ..clear()
                ..addAll(retained);
            }),
            leading: Icon(
              _signupPlan == _planCode(index)
                  ? Icons.radio_button_checked
                  : Icons.radio_button_unchecked,
              color: Theme.of(context).colorScheme.primary,
            ),
            title: Text(
              pricing.plans[index].tier,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            subtitle: Text(pricing.plans[index].priceLabel),
          ),
        ),
    ],
  );

  String _planCode(int index) => switch (index) {
    0 => 'demo',
    1 => 'professional',
    _ => 'enterprise',
  };

  Widget _signupConfirmation(
    AuthStrings t,
    Translations translations,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        t.registerTitle,
        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
      ),
      const SizedBox(height: 8),
      Text(
        '${_company.text} · $_signupIndustry · ${_signupPlan.toUpperCase()}',
      ),
      Text('${_firstName.text} ${_lastName.text} · ${_email.text}'),
      const SizedBox(height: 4),
      Text(
        _signupModules
            .map((id) => translations.agents.value(agentById(id).nameKey))
            .join(' · '),
      ),
      const SizedBox(height: 8),
      Text(translations.finalCta.title),
    ],
  );

  Widget _field(
    TextEditingController controller,
    String label, {
    required AuthStrings t,
    bool email = false,
    bool password = false,
    bool optional = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextFormField(
        controller: controller,
        obscureText: password && _obscurePassword,
        keyboardType: email ? TextInputType.emailAddress : TextInputType.text,
        decoration: InputDecoration(
          labelText: label,
          suffixIcon: password
              ? IconButton(
                  icon: Icon(
                    _obscurePassword
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined,
                  ),
                  color: AvenqoColors.of(context).muted,
                  onPressed: () =>
                      setState(() => _obscurePassword = !_obscurePassword),
                )
              : null,
        ),
        validator: (value) {
          final text = value?.trim() ?? '';
          if (text.isEmpty && optional) return null;
          if (text.isEmpty) return t.requiredField;
          if (controller == _website) {
            final candidate =
                text.startsWith('http://') || text.startsWith('https://')
                ? text
                : 'https://$text';
            final uri = Uri.tryParse(candidate);
            if (uri == null || uri.host.isEmpty || !uri.host.contains('.')) {
              return t.genericError;
            }
          }
          return null;
        },
      ),
    );
  }
}

class _SignupModuleCard extends StatelessWidget {
  const _SignupModuleCard({
    super.key,
    required this.module,
    required this.strings,
    required this.selected,
    required this.onTap,
  });

  final AvenqoAgentDefinition module;
  final AgentStrings strings;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Material(
      color: selected ? _Brand.blue.withValues(alpha: 0.08) : colors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(
          color: selected ? _Brand.blue : colors.line,
          width: selected ? 1.5 : 1,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: _Brand.blue.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(7),
                ),
                child: Icon(
                  _moduleIcon(module.iconIdentifier),
                  color: _Brand.blue,
                  size: 21,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      strings.value(module.nameKey),
                      style: TextStyle(
                        color: colors.ink,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      strings.value(module.descriptionKey),
                      style: TextStyle(
                        color: colors.muted,
                        fontSize: 12,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Icon(
                selected ? Icons.check_circle : Icons.circle_outlined,
                color: selected ? _Brand.blue : colors.muted,
                size: 21,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

IconData _moduleIcon(String identifier) => switch (identifier) {
  'storefront' => Icons.storefront_outlined,
  'campaign' => Icons.campaign_outlined,
  'contacts' => Icons.contacts_outlined,
  'groups' => Icons.groups_outlined,
  'account_balance' => Icons.account_balance_outlined,
  'document_scanner' => Icons.document_scanner_outlined,
  'mic' => Icons.mic_none_outlined,
  'perm_media' => Icons.perm_media_outlined,
  'gavel' => Icons.gavel_outlined,
  'calendar_month' => Icons.calendar_month_outlined,
  'account_tree' => Icons.account_tree_outlined,
  _ => Icons.extension_outlined,
};

class _SignupProgress extends StatelessWidget {
  const _SignupProgress({required this.step, required this.labels});

  final int step;
  final List<String> labels;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Wrap(
      spacing: 6,
      runSpacing: 8,
      children: [
        for (var index = 0; index < labels.length; index++)
          Text(
            '${index + 1}. ${labels[index]}',
            style: TextStyle(
              color: index == step ? colors.ink : colors.muted,
              fontWeight: index == step ? FontWeight.w800 : FontWeight.w500,
              fontSize: 11,
            ),
          ),
      ],
    );
  }
}

class _BrandPanel extends StatelessWidget {
  const _BrandPanel({required this.tagline});

  final String tagline;

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context);
    return Container(
      color: _Brand.ink,
      padding: const EdgeInsets.all(48),
      child: Stack(
        children: [
          Positioned(
            top: -60,
            right: -60,
            child: Container(
              width: 240,
              height: 240,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    _Brand.blue.withValues(alpha: 0.25),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
          Center(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    tagline,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 30,
                      fontWeight: FontWeight.w800,
                      height: 1.25,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    t.common.isolatedData,
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 15,
                      height: 1.6,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AuthHeader extends StatelessWidget {
  const _AuthHeader();

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final logoSize = MediaQuery.sizeOf(context).width < 480 ? 36.0 : 42.0;
    return Material(
      color: colors.surface,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        child: Row(
          children: [
            InkWell(
              onTap: () => context.go('/'),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Image.asset(
                    'assets/brand/avenqo-official.png',
                    key: const ValueKey('official-avenqo-logo'),
                    width: logoSize,
                    height: logoSize,
                    fit: BoxFit.contain,
                    semanticLabel: 'Logo Avenqo',
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'Avenqo',
                    style: TextStyle(
                      color: colors.ink,
                      fontWeight: FontWeight.w800,
                      fontSize: 20,
                    ),
                  ),
                ],
              ),
            ),
            const Spacer(),
            Flexible(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerRight,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    ThemeToggleButton(foregroundColor: colors.muted),
                    LanguageSelector(foregroundColor: colors.muted),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FormCard extends StatelessWidget {
  const _FormCard({
    required this.title,
    required this.subtitle,
    required this.child,
  });

  final String title;
  final String subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final t = AvenqoLocaleScope.translationsOf(context);
    final colors = AvenqoColors.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          title,
          style: TextStyle(
            color: colors.ink,
            fontSize: 26,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          subtitle,
          style: TextStyle(color: colors.muted, fontSize: 14, height: 1.5),
        ),
        const SizedBox(height: 28),
        Card(
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(color: colors.line),
          ),
          child: Padding(padding: const EdgeInsets.all(28), child: child),
        ),
        const SizedBox(height: 16),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => context.go('/'),
            icon: Icon(Icons.arrow_back, size: 16, color: colors.muted),
            label: Text(t.auth.home, style: TextStyle(color: colors.muted)),
          ),
        ),
      ],
    );
  }
}
