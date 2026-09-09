import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/support_api.dart';
import '../../shared/widgets/primary_button.dart';
import 'support_case_screen.dart';

/// Contact Support — build order step 8
/// (docs/16-mobile/mobile-app-implementation-plan.md §4.9/§5.7). Creates
/// a support case (api-contracts.md §44, ADR-0022) and, on success,
/// replaces itself with [SupportCaseScreen] showing the case and its
/// (one, so far) message. Reachable from both home screens (general
/// contact) and both ride screens ([rideId] pre-filled, for a ride-
/// specific issue or a fare/penalty dispute — BR-121, domain-design.md
/// §17.3's `DisputePenalty`, both filed through this same endpoint per
/// ADR-0028/ADR-0029, "Dispute-as-Support").
///
/// `category` has no canonical enum anywhere (api-contracts.md §44) —
/// shown as free text, same treatment this app already gives
/// `incident_type`/cancellation reasons. A case filed here can be found
/// again later via the My Support Cases list screen (added 2026-09-04)
/// — it no longer becomes unreachable once this screen's stack is left.
class ContactSupportScreen extends StatefulWidget {
  const ContactSupportScreen({this.rideId, super.key});

  final String? rideId;

  @override
  State<ContactSupportScreen> createState() => _ContactSupportScreenState();
}

class _ContactSupportScreenState extends State<ContactSupportScreen> {
  final _categoryController = TextEditingController();
  final _messageController = TextEditingController();
  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void dispose() {
    _categoryController.dispose();
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final message = _messageController.text.trim();
    if (message.isEmpty) {
      setState(() => _errorMessage = 'Enter a message.');
      return;
    }
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });
    final api = context.read<SupportApi>();
    try {
      final category = _categoryController.text.trim();
      final created = await api.createCase(
        category: category.isEmpty ? null : category,
        rideId: widget.rideId,
        message: message,
      );
      // The create response never echoes the message thread back
      // (SupportApi.createCase's own doc comment) — fetch the case for
      // real before showing it.
      final full = await api.getCase(created.caseId);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (_) => SupportCaseScreen(initialCase: full),
        ),
      );
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Contact Support')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (widget.rideId != null) ...[
                Text(
                  'About ride ${widget.rideId}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
              ],
              TextField(
                controller: _categoryController,
                decoration: const InputDecoration(
                  labelText: 'Category (optional)',
                  hintText: 'e.g. PAYMENT, RIDE_FARE_DISPUTE',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _messageController,
                minLines: 4,
                maxLines: 8,
                maxLength: 4000,
                decoration: const InputDecoration(
                  labelText: 'How can we help?',
                  border: OutlineInputBorder(),
                  alignLabelWithHint: true,
                ),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: 8),
                Text(
                  _errorMessage!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              PrimaryButton(
                label: 'Submit',
                isLoading: _isSubmitting,
                onPressed: _submit,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
