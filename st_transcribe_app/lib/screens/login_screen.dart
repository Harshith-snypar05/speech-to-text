import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../services/auth_service.dart';
import '../services/platform_api.dart';
import '../theme.dart';
import '../widgets/brand.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _nameController = TextEditingController();
  bool _register = false;
  String? _error;
  bool _submitting = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _error = null;
      _submitting = true;
    });
    final err = _register
        ? await AuthService.register(
            _nameController.text,
            _emailController.text,
            _passwordController.text,
          )
        : await AuthService.login(
            _emailController.text,
            _passwordController.text,
          );
    if (!mounted) return;
    setState(() {
      _submitting = false;
      _error = err;
      if (AuthService.unverifiedEmail.value != null) {
        _passwordController.clear();
      }
    });
  }

  Future<void> _resend(String email) async {
    setState(() => _submitting = true);
    final text = await AuthService.resendVerification(email);
    if (!mounted) return;
    setState(() => _submitting = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Widget _checkEmail(String email, AppColors colors) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Center(child: ScriptLivLogo(height: 52)),
        const SizedBox(height: 28),
        Text(
          'Verify your email',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w800,
            color: colors.textPrimary,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'We sent a verification link to $email. Open it to confirm your address, then sign in. You cannot sign in until it is verified.',
          textAlign: TextAlign.center,
          style: TextStyle(color: colors.textSecondary),
        ),
        const SizedBox(height: 24),
        GradientButton(
          label: 'I have verified, sign in',
          onPressed: () => setState(() {
            AuthService.unverifiedEmail.value = null;
            _register = false;
            _error = null;
          }),
          busy: false,
        ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: _submitting ? null : () => _resend(email),
          child: const Text('Resend verification email'),
        ),
        const SizedBox(height: 16),
        Text(
          AppConfig.copyright,
          textAlign: TextAlign.center,
          style: TextStyle(color: colors.textSecondary, fontSize: 12),
        ),
      ],
    );
  }

  Future<void> _forgot() async {
    final email = _emailController.text.trim();
    if (email.isEmpty || !email.contains('@')) {
      setState(
        () => _error =
            'Enter your account email above, then tap Forgot password.',
      );
      return;
    }
    setState(() {
      _error = null;
      _submitting = true;
    });
    String text;
    try {
      text =
          '${await PlatformApi.forgotPassword(email)} Open the link in the email to choose a new password.';
    } on ApiException catch (e) {
      text = e.message;
    } catch (_) {
      text = 'Could not reach the server. Try again.';
    }
    if (!mounted) return;
    setState(() => _submitting = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 380),
              child: AuthService.unverifiedEmail.value != null
                  ? _checkEmail(AuthService.unverifiedEmail.value!, colors)
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Center(child: ScriptLivLogo(height: 52)),
                        const SizedBox(height: 28),
                        Text(
                          _register ? 'Create your account' : 'Welcome back',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.w800,
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _register
                              ? 'Basic plan: 300 free minutes every month.'
                              : 'Sign in to start transcribing.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: colors.textSecondary),
                        ),
                        const SizedBox(height: 24),
                        if (_register) ...[
                          TextField(
                            controller: _nameController,
                            textCapitalization: TextCapitalization.words,
                            decoration: const InputDecoration(
                              labelText: 'Name',
                              border: OutlineInputBorder(),
                            ),
                          ),
                          const SizedBox(height: 12),
                        ],
                        TextField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          decoration: const InputDecoration(
                            labelText: 'Email',
                            border: OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _passwordController,
                          obscureText: true,
                          onSubmitted: (_) => _submit(),
                          decoration: const InputDecoration(
                            labelText: 'Password',
                            border: OutlineInputBorder(),
                          ),
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 10),
                          Text(
                            _error!,
                            style: TextStyle(
                              color: colors.recordRed,
                              fontSize: 13,
                            ),
                          ),
                        ],
                        const SizedBox(height: 20),
                        GradientButton(
                          label: _register ? 'Create account' : 'Log In',
                          onPressed: _submit,
                          busy: _submitting,
                        ),
                        if (!_register)
                          Align(
                            alignment: Alignment.centerRight,
                            child: TextButton(
                              onPressed: _submitting ? null : _forgot,
                              child: const Text('Forgot password?'),
                            ),
                          ),
                        const SizedBox(height: 8),
                        TextButton(
                          onPressed: _submitting
                              ? null
                              : () => setState(() {
                                  _register = !_register;
                                  _error = null;
                                }),
                          child: Text(
                            _register
                                ? 'Have an account? Sign in'
                                : 'New here? Create an account',
                          ),
                        ),
                        const SizedBox(height: 16),
                        Text(
                          AppConfig.copyright,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: colors.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
