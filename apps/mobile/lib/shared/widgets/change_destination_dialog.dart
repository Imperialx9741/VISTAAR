import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/ride_api.dart';
import '../../core/config/app_config.dart';
import '../../features/location/location_picker_screen.dart';

/// A small dialog collecting a new destination latitude/longitude —
/// used by `RideStatusScreen`'s Change Destination action
/// (api-contracts.md §25). A near-duplicate of
/// `change_pickup_dialog.dart` rather than a shared/parameterized
/// widget — this codebase's own established convention for small,
/// screen-specific dialogs (same reasoning `RequestPickupChangeBody`/
/// `RequestDestinationChangeBody` stay separate classes on the backend
/// despite an identical shape). A **Pick on Map** button (2026-09-07)
/// fills the same fields below when `AppConfig.hasMapTilerApiKey` is
/// true; see `change_pickup_dialog.dart`'s own doc comment for the full
/// account. Returns the entered `(latitude, longitude)`, or `null` if
/// dismissed without submitting.
Future<(double, double)?> showChangeDestinationDialog(BuildContext context) {
  return showDialog<(double, double)>(
    context: context,
    builder: (context) => const _ChangeDestinationDialog(),
  );
}

class _ChangeDestinationDialog extends StatefulWidget {
  const _ChangeDestinationDialog();

  @override
  State<_ChangeDestinationDialog> createState() =>
      _ChangeDestinationDialogState();
}

class _ChangeDestinationDialogState extends State<_ChangeDestinationDialog> {
  final _formKey = GlobalKey<FormState>();
  final _latController = TextEditingController();
  final _lngController = TextEditingController();

  @override
  void dispose() {
    _latController.dispose();
    _lngController.dispose();
    super.dispose();
  }

  String? _validate(String? value, {required double min, required double max}) {
    final parsed = double.tryParse((value ?? '').trim());
    if (parsed == null) return 'Enter a number';
    if (parsed < min || parsed > max) return 'Out of range';
    return null;
  }

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    Navigator.of(context).pop((
      double.parse(_latController.text.trim()),
      double.parse(_lngController.text.trim()),
    ));
  }

  Future<void> _pickOnMap() async {
    final initial =
        double.tryParse(_latController.text.trim()) != null &&
            double.tryParse(_lngController.text.trim()) != null
        ? RideGeoPoint(
            latitude: double.parse(_latController.text.trim()),
            longitude: double.parse(_lngController.text.trim()),
          )
        : null;
    final picked = await Navigator.of(context).push<RideGeoPoint>(
      MaterialPageRoute<RideGeoPoint>(
        builder: (_) => LocationPickerScreen(
          title: 'New Destination Location',
          initialCenter: initial,
        ),
      ),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _latController.text = picked.latitude.toStringAsFixed(6);
      _lngController.text = picked.longitude.toStringAsFixed(6);
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Change destination'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (AppConfig.hasMapTilerApiKey) ...[
              OutlinedButton.icon(
                onPressed: _pickOnMap,
                icon: const Icon(Icons.map_outlined),
                label: const Text('Pick on Map'),
              ),
              const SizedBox(height: 12),
            ],
            TextFormField(
              controller: _latController,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
                signed: true,
              ),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'^-?\d*\.?\d*')),
              ],
              validator: (value) => _validate(value, min: -90, max: 90),
              decoration: const InputDecoration(labelText: 'New latitude'),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _lngController,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
                signed: true,
              ),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'^-?\d*\.?\d*')),
              ],
              validator: (value) => _validate(value, min: -180, max: 180),
              decoration: const InputDecoration(labelText: 'New longitude'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Back'),
        ),
        FilledButton(
          onPressed: _submit,
          child: const Text('Change Destination'),
        ),
      ],
    );
  }
}
