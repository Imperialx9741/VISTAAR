import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/auth_api.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/widgets/primary_button.dart';
import '../home/home_router.dart';
import 'app_role.dart';
import 'auth_session.dart';

const int _otpLength = 6;

const int _resendCooldownSeconds = 30;

/// Step 3 of the login flow (ADR-0027): OTP entry, then
/// `POST /api/v1/auth/otp/verify` (api-contracts.md §7). On success,
/// records the session in [AuthSession] and replaces the whole
/// navigation stack with the role-appropriate home screen — the user
/// should never be able to navigate "back" into the login flow once
/// authenticated.
class OtpVerifyScreen extends StatefulWidget {
  const OtpVerifyScreen({
    super.key,
    required this.role,
    required this.phone,
    required this.initialChallenge,
  });

  final AppRole role;
  final String phone;
  final OtpChallenge initialChallenge;

  @override
  State<OtpVerifyScreen> createState() => _OtpVerifyScreenState();
}

class _OtpVerifyScreenState extends State<OtpVerifyScreen> {
  final _formKey = GlobalKey<FormState>();
  final _otpController = TextEditingController();
  late OtpChallenge _challenge;
  bool _isSubmitting = false;
  bool _isResending = false;
  String? _errorMessage;
  int _resendSecondsRemaining = _resendCooldownSeconds;
  Timer? _resendTimer;

  @override
  void initState() {
    super.initState();
    _challenge = widget.initialChallenge;
    _startResendCountdown();
    // Rapido-benchmarked redesign (2026-09-08): the boxed-digit row
    // below is painted from `_otpController.text` directly rather than
    // the field's own built-in glyph rendering (which stays invisible,
    // overlaid on top, purely to keep receiving real keyboard/paste
    // input and this screen's existing Form validation) — a listener
    // is required so typing repaints those boxes; a StatefulWidget does
    // not rebuild on its own just because a controller it owns changes.
    _otpController.addListener(_onOtpChanged);
  }

  void _onOtpChanged() => setState(() {});

  @override
  void dispose() {
    _resendTimer?.cancel();
    _otpController
      ..removeListener(_onOtpChanged)
      ..dispose();
    super.dispose();
  }

  void _startResendCountdown() {
    _resendTimer?.cancel();
    setState(() => _resendSecondsRemaining = _resendCooldownSeconds);
    _resendTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_resendSecondsRemaining <= 1) {
        timer.cancel();
        setState(() => _resendSecondsRemaining = 0);
      } else {
        setState(() => _resendSecondsRemaining -= 1);
      }
    });
  }

  String? _validateOtp(String? value) {
    if ((value ?? '').trim().length != 6) {
      return 'Enter the 6-digit code';
    }
    return null;
  }

  Future<void> _resend() async {
    setState(() {
      _isResending = true;
      _errorMessage = null;
    });
    final authApi = context.read<AuthApi>();
    try {
      final challenge = await authApi.requestOtp(
        phone: widget.phone,
        accountType: widget.role.accountType,
      );
      if (!mounted) return;
      setState(() => _challenge = challenge);
      _startResendCountdown();
    } on ApiException catch (error) {
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isResending = false);
    }
  }

  Future<void> _submit() async {
    // The real `TextFormField` backing the boxed-digit row is fully
    // invisible (Opacity 0, see `_buildOtpBoxes`), so its own built-in
    // validator error text is never shown on screen — surfaced here
    // instead through the same `_errorMessage` banner the backend-error
    // path below already uses, so "Enter the 6-digit code" is still
    // visible to the user, not silently swallowed.
    if (!(_formKey.currentState?.validate() ?? false)) {
      setState(() => _errorMessage = _validateOtp(_otpController.text));
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final authApi = context.read<AuthApi>();
    try {
      final tokens = await authApi.verifyOtp(
        challengeId: _challenge.challengeId,
        otp: _otpController.text.trim(),
      );
      if (!mounted) return;
      context.read<AuthSession>().signIn(role: widget.role, tokens: tokens);
      await Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => const HomeRouter()),
        (route) => false,
      );
    } on ApiException catch (error) {
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Verify OTP')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Enter the code sent to',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Text(
                  widget.phone,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const SizedBox(height: 24),
                _buildOtpBoxes(context),
                if (_errorMessage != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    _errorMessage!,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ],
                const SizedBox(height: 16),
                PrimaryButton(
                  label: 'Verify',
                  isLoading: _isSubmitting,
                  onPressed: _submit,
                ),
                const SizedBox(height: 16),
                Center(
                  child: TextButton(
                    onPressed: (_resendSecondsRemaining > 0 || _isResending)
                        ? null
                        : _resend,
                    child: Text(
                      _resendSecondsRemaining > 0
                          ? 'Resend OTP in ${_resendSecondsRemaining}s'
                          : (_isResending ? 'Resending…' : 'Resend OTP'),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// The Rapido-style boxed-digit OTP row (2026-09-08 redesign) — a
  /// visual row of [_otpLength] individual boxes rendered from
  /// [_otpController]'s current text, layered under one real, fully
  /// functional `TextFormField` that is made invisible (transparent
  /// text/cursor, no visible decoration) rather than replaced.
  /// Deliberately kept as ONE real text field, not [_otpLength]
  /// separate ones: this app's own tests (`widget_test.dart`) already
  /// call `tester.enterText(find.byType(TextFormField), '123456')`
  /// against this screen, which only works against exactly one field
  /// receiving the whole string at once — six separate fields would
  /// need per-digit focus-advance wiring and would break that
  /// `find.byType` assumption on the very first tap. This overlay
  /// approach gets the boxed *look* Rapido uses without touching how
  /// input actually reaches [_otpController] or the [Form]'s own
  /// [_validateOtp] validation, both of which are untouched below.
  Widget _buildOtpBoxes(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final digits = _otpController.text;
    return SizedBox(
      height: 56,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              for (var i = 0; i < _otpLength; i++)
                Container(
                  width: 44,
                  height: 56,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(VistaarRadius.control),
                    border: Border.all(
                      color: i < digits.length
                          ? scheme.primary
                          : scheme.outlineVariant,
                      width: i < digits.length ? 2 : 1,
                    ),
                    color: scheme.surfaceContainerHighest.withValues(alpha: 0.3),
                  ),
                  child: Text(
                    i < digits.length ? digits[i] : '',
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                ),
            ],
          ),
          Opacity(
            // Not fully invisible via a transparent style alone — the
            // blinking text cursor and Android's own autofill/keyboard
            // suggestion strip both still render from an
            // IgnorePointer:false, textColor:transparent field. Full
            // Opacity(0) hides all of that while the field underneath
            // keeps focus, keyboard, and input working exactly as
            // before.
            opacity: 0,
            child: TextFormField(
              controller: _otpController,
              keyboardType: TextInputType.number,
              autofocus: true,
              maxLength: _otpLength,
              textAlign: TextAlign.center,
              showCursor: false,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              validator: _validateOtp,
              decoration: const InputDecoration(
                border: InputBorder.none,
                counterText: '',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
