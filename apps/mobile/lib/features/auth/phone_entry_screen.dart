import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/auth_api.dart';
import '../../shared/widgets/primary_button.dart';
import 'app_role.dart';
import 'otp_verify_screen.dart';

/// Step 2 of the login flow (ADR-0027): phone number entry, then
/// `POST /api/v1/auth/otp/request` (api-contracts.md §6.1) for whichever
/// [role] was picked on the previous screen.
class PhoneEntryScreen extends StatefulWidget {
  const PhoneEntryScreen({super.key, required this.role});

  final AppRole role;

  @override
  State<PhoneEntryScreen> createState() => _PhoneEntryScreenState();
}

class _PhoneEntryScreenState extends State<PhoneEntryScreen> {
  final _formKey = GlobalKey<FormState>();
  final _phoneController = TextEditingController();
  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void dispose() {
    _phoneController.dispose();
    super.dispose();
  }

  String? _validatePhone(String? value) {
    final digits = value?.trim() ?? '';
    if (digits.length != 10) {
      return 'Enter a valid 10-digit mobile number';
    }
    return null;
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final phone = '+91${_phoneController.text.trim()}';
    final authApi = context.read<AuthApi>();
    try {
      final challenge = await authApi.requestOtp(
        phone: phone,
        accountType: widget.role.accountType,
      );
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => OtpVerifyScreen(
            role: widget.role,
            phone: phone,
            initialChallenge: challenge,
          ),
        ),
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
      appBar: AppBar(title: Text(widget.role.displayName)),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  "What's your mobile number?",
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                Text(
                  "We'll send a one-time code to verify it.",
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 24),
                TextFormField(
                  controller: _phoneController,
                  keyboardType: TextInputType.phone,
                  autofocus: true,
                  maxLength: 10,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  validator: _validatePhone,
                  decoration: const InputDecoration(
                    prefixText: '+91  ',
                    labelText: 'Mobile number',
                    border: OutlineInputBorder(),
                    counterText: '',
                  ),
                ),
                if (_errorMessage != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    _errorMessage!,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ],
                const SizedBox(height: 16),
                PrimaryButton(
                  label: 'Send OTP',
                  isLoading: _isSubmitting,
                  onPressed: _submit,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
