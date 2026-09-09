import 'package:flutter/material.dart';

/// A reason-entry dialog shared by both cancellation flows (Customer
/// Cancellation §19, Driver Cancellation §20) — the backend enforces no
/// canonical reason enum for either
/// (`modules/ride/domain/entities.py`'s `validate_cancellation_reason()`
/// only checks non-blank, ≤100 chars), so this is free text, not a
/// fixed picker inventing categories the backend doesn't have. Returns
/// the trimmed reason, or `null` if dismissed without confirming.
Future<String?> showCancelReasonDialog(
  BuildContext context, {
  required String title,
}) {
  return showDialog<String>(
    context: context,
    builder: (context) => _CancelReasonDialog(title: title),
  );
}

class _CancelReasonDialog extends StatefulWidget {
  const _CancelReasonDialog({required this.title});

  final String title;

  @override
  State<_CancelReasonDialog> createState() => _CancelReasonDialogState();
}

class _CancelReasonDialogState extends State<_CancelReasonDialog> {
  final _controller = TextEditingController();
  String? _errorText;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _confirm() {
    final reason = _controller.text.trim();
    if (reason.isEmpty) {
      setState(() => _errorText = 'Enter a reason.');
      return;
    }
    Navigator.of(context).pop(reason);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: Text(widget.title),
      content: TextField(
        controller: _controller,
        autofocus: true,
        maxLength: 100,
        decoration: InputDecoration(labelText: 'Reason', errorText: _errorText),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Back'),
        ),
        // Error-colored, not the app's default primary green — a
        // destructive action must never look like the same "go ahead
        // and book/accept" CTA everywhere else (Rapido-benchmarked
        // brand brief, 2026-09-08 — button-hierarchy audit).
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: scheme.error,
            foregroundColor: scheme.onError,
          ),
          onPressed: _confirm,
          child: const Text('Confirm Cancellation'),
        ),
      ],
    );
  }
}
