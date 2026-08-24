import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/avenqo_colors.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';
import 'package:avenqo/i18n/locale_scope.dart';
import 'package:avenqo/i18n/translations.dart';
import 'package:avenqo/widgets/language_selector.dart';

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
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  ({String title, String subtitle}) _copy(AuthStrings t) => switch (widget.mode) {
        AuthMode.login => (title: t.loginTitle, subtitle: t.loginSubtitle),
        AuthMode.register => (title: t.registerTitle, subtitle: t.registerSubtitle),
        AuthMode.forgot => (title: t.forgotTitle, subtitle: t.forgotSubtitle),
        AuthMode.verify => (title: t.verifyTitle, subtitle: t.verifySubtitle),
        AuthMode.reset => (title: t.resetTitle, subtitle: t.resetSubtitle),
      };

  Future<void> _submit(AuthStrings t) async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _message = null);
    try {
      switch (widget.mode) {
        case AuthMode.login:
          await widget.auth.login(_email.text, _password.text);
          if (mounted) context.go('/dashboard');
        case AuthMode.register:
          await widget.auth.register({
            'company_name': _company.text,
            'company_email': _companyEmail.text,
            'first_name': _firstName.text,
            'last_name': _lastName.text,
            'email': _email.text,
            'password': _password.text,
            'country': 'Canada',
            'timezone': 'America/Toronto',
            'industry': 'Technology',
          });
          _show(t.registerSuccess);
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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _CompactHeader(tagline: t.tagline),
                    const SizedBox(height: 20),
                    form,
                  ],
                ),
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
                        constraints: const BoxConstraints(maxWidth: 460),
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
    );
  }

  Widget _buildForm(AuthStrings t) {
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
          if ([
            AuthMode.verify,
            AuthMode.reset,
          ].contains(widget.mode))
            _field(_token, t.emailToken, t: t),
          if (_message != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: _isError ? const Color(0xFFFFF4F2) : const Color(0xFFF0FBF6),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                _message!,
                style: TextStyle(
                  color: _isError ? const Color(0xFFB42318) : const Color(0xFF1B7A4A),
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
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: widget.auth.busy
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : Text(_copy(t).title, style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
          if (widget.mode == AuthMode.login) ...[
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => context.go('/forgot-password'),
              child: Text(t.forgotPassword, style: TextStyle(color: AvenqoColors.of(context).muted)),
            ),
            TextButton(
              onPressed: () => context.go('/register'),
              child: Text(t.createOrganisation, style: const TextStyle(color: _Brand.blueDark, fontWeight: FontWeight.w700)),
            ),
          ],
          if (widget.mode != AuthMode.login) ...[
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => context.go('/login'),
              child: Text(t.backToLogin, style: const TextStyle(color: _Brand.blueDark, fontWeight: FontWeight.w700)),
            ),
          ],
        ],
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    required AuthStrings t,
    bool email = false,
    bool password = false,
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
                  icon: Icon(_obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                  color: AvenqoColors.of(context).muted,
                  onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                )
              : null,
        ),
        validator: (value) => value == null || value.trim().isEmpty ? t.requiredField : null,
      ),
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
                gradient: RadialGradient(colors: [_Brand.blue.withValues(alpha: 0.25), Colors.transparent]),
              ),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              InkWell(
                onTap: () => context.go('/'),
                child: const Row(
                  children: [
                    Icon(Icons.change_history, color: _Brand.blue, size: 26),
                    SizedBox(width: 10),
                    Text('Avenqo', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 26)),
                  ],
                ),
              ),
              const SizedBox(height: 28),
              Text(
                tagline,
                style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w800, height: 1.25),
              ),
              const SizedBox(height: 16),
              Text(
                t.common.isolatedData,
                style: const TextStyle(color: Colors.white70, fontSize: 15, height: 1.6),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CompactHeader extends StatelessWidget {
  const _CompactHeader({required this.tagline});

  final String tagline;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    return Row(
      children: [
        InkWell(
          onTap: () => context.go('/'),
          child: Row(
            children: [
              const Icon(Icons.change_history, color: _Brand.blue, size: 22),
              const SizedBox(width: 8),
              Text('Avenqo', style: TextStyle(color: colors.ink, fontWeight: FontWeight.w800, fontSize: 20)),
            ],
          ),
        ),
        const Spacer(),
        LanguageSelector(foregroundColor: colors.muted),
      ],
    );
  }
}

class _FormCard extends StatelessWidget {
  const _FormCard({required this.title, required this.subtitle, required this.child});

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
        Row(
          children: [
            Expanded(
              child: Text(
                title,
                style: TextStyle(color: colors.ink, fontSize: 26, fontWeight: FontWeight.w800),
              ),
            ),
            LanguageSelector(foregroundColor: colors.muted),
          ],
        ),
        const SizedBox(height: 8),
        Text(subtitle, style: TextStyle(color: colors.muted, fontSize: 14, height: 1.5)),
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

