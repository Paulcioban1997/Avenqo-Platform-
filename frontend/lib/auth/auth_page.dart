import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/auth/auth_controller.dart';
import 'package:avenqo/core/api_client.dart';

enum AuthMode { login, register, forgot, verify, reset }

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

  String get _title => switch (widget.mode) {
    AuthMode.login => 'Connexion',
    AuthMode.register => 'Créer une organisation',
    AuthMode.forgot => 'Mot de passe oublié',
    AuthMode.verify => 'Vérifier votre email',
    AuthMode.reset => 'Nouveau mot de passe',
  };

  Future<void> _submit() async {
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
          _show('Compte créé. Vérifiez votre adresse email.');
        case AuthMode.forgot:
          await widget.auth.forgotPassword(_email.text);
          _show('Si le compte existe, un email a été envoyé.');
        case AuthMode.verify:
          await widget.auth.verifyEmail(_token.text);
          _show('Adresse email vérifiée. Vous pouvez vous connecter.');
        case AuthMode.reset:
          await widget.auth.resetPassword(_token.text, _password.text);
          _show('Mot de passe modifié. Vous pouvez vous connecter.');
      }
    } on ApiException catch (error) {
      _show(error.message, isError: true);
    } catch (_) {
      _show('Le service est temporairement indisponible.', isError: true);
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
    return Scaffold(
      appBar: AppBar(
        title: const Text('AVENQO'),
        actions: [
          TextButton(
            onPressed: () => context.go('/'),
            child: const Text('Accueil'),
          ),
        ],
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        _title,
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      const SizedBox(height: 24),
                      if (widget.mode == AuthMode.register) ...[
                        _field(_company, 'Organisation'),
                        _field(
                          _companyEmail,
                          'Email de facturation',
                          email: true,
                        ),
                        Row(
                          children: [
                            Expanded(child: _field(_firstName, 'Prénom')),
                            const SizedBox(width: 12),
                            Expanded(child: _field(_lastName, 'Nom')),
                          ],
                        ),
                      ],
                      if ([
                        AuthMode.login,
                        AuthMode.register,
                        AuthMode.forgot,
                      ].contains(widget.mode))
                        _field(_email, 'Email', email: true),
                      if ([
                        AuthMode.login,
                        AuthMode.register,
                        AuthMode.reset,
                      ].contains(widget.mode))
                        _field(_password, 'Mot de passe', password: true),
                      if ([
                        AuthMode.verify,
                        AuthMode.reset,
                      ].contains(widget.mode))
                        _field(_token, 'Jeton reçu par email'),
                      if (_message != null) ...[
                        Text(
                          _message!,
                          style: TextStyle(
                            color: _isError
                                ? Colors.red.shade700
                                : Colors.green.shade700,
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                      FilledButton(
                        onPressed: widget.auth.busy ? null : _submit,
                        child: widget.auth.busy
                            ? const SizedBox.square(
                                dimension: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : Text(_title),
                      ),
                      if (widget.mode == AuthMode.login) ...[
                        TextButton(
                          onPressed: () => context.go('/forgot-password'),
                          child: const Text('Mot de passe oublié'),
                        ),
                        TextButton(
                          onPressed: () => context.go('/register'),
                          child: const Text('Créer une organisation'),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    bool email = false,
    bool password = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: TextFormField(
        controller: controller,
        obscureText: password,
        keyboardType: email ? TextInputType.emailAddress : TextInputType.text,
        decoration: InputDecoration(labelText: label),
        validator: (value) =>
            value == null || value.trim().isEmpty ? 'Champ requis' : null,
      ),
    );
  }
}
