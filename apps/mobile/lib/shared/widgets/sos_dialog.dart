import 'package:flutter/material.dart';

/// `incident_type` presets shown to the caller. No canonical enum is
/// documented anywhere for this field (api-contracts.md §41 shape-
/// validates only — non-blank, ≤50 chars) — these are this app's own
/// choice of common cases, sent to the backend as plain shape-validated
/// text, same treatment `document_type`/`category` free-text fields get
/// elsewhere in this codebase.
const List<(String label, String incidentType)> _sosPresets = [
  ('Medical emergency', 'MEDICAL_EMERGENCY'),
  ('Accident', 'ACCIDENT'),
  ('Unsafe situation / harassment', 'UNSAFE_SITUATION'),
  ('Other emergency', 'OTHER'),
];

/// SOS confirmation dialog (BR-112, api-contracts.md §41) — shared by
/// both roles' ride screens. Requires picking one preset before the
/// confirm button enables, a deliberate extra tap so a stray touch can't
/// trigger a real safety escalation. Returns the chosen `incident_type`,
/// or `null` if dismissed without confirming.
Future<String?> showSosDialog(BuildContext context) {
  return showDialog<String>(
    context: context,
    builder: (context) => const _SosDialog(),
  );
}

class _SosDialog extends StatefulWidget {
  const _SosDialog();

  @override
  State<_SosDialog> createState() => _SosDialogState();
}

class _SosDialogState extends State<_SosDialog> {
  String? _selected;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Trigger SOS?'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'This alerts VISTAAR\'s safety team immediately, with your '
            'current location and this ride\'s details. It does not call '
            'police or an ambulance directly — if you need emergency '
            'services right now, contact them yourself first.',
          ),
          const SizedBox(height: 12),
          RadioGroup<String>(
            groupValue: _selected,
            onChanged: (value) => setState(() => _selected = value),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final (label, incidentType) in _sosPresets)
                  RadioListTile<String>(
                    contentPadding: EdgeInsets.zero,
                    title: Text(label),
                    value: incidentType,
                  ),
              ],
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _selected == null
              ? null
              : () => Navigator.of(context).pop(_selected),
          style: FilledButton.styleFrom(
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
          child: const Text('Trigger SOS'),
        ),
      ],
    );
  }
}
