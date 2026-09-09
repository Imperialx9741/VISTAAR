import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/ride_api.dart';
import '../../core/config/app_config.dart';
import '../../core/contacts/contacts_api.dart';
import '../../shared/design/vistaar_bottom_sheet.dart';
import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../../shared/widgets/primary_button.dart';
import '../../shared/widgets/route_map_preview.dart';
import '../location/location_picker_screen.dart';
import 'ride_status_screen.dart';

const List<(String, String, IconData)> _vehicleCategories = [
  ('BIKE', 'Bike', Icons.two_wheeler_outlined),
  ('AUTO', 'Auto', Icons.electric_rickshaw_outlined),
  ('CAB', 'Cab', Icons.directions_car_outlined),
];

const List<(String, String)> _cabTiers = [
  ('ECO', 'Eco'),
  ('PREMIUM', 'Premium'),
  ('PREMIUM_PLUS', 'Premium+'),
];

/// Book a Ride — build order step 4
/// (docs/16-mobile/mobile-app-implementation-plan.md §4.1). Pickup and
/// destination are picked on a real map (2026-09-07, MapTiler map
/// rendering — `LocationPickerScreen`) whenever
/// `AppConfig.hasMapTilerApiKey` is true; the underlying latitude/
/// longitude fields stay visible and editable underneath as a manual
/// override/fallback (and the *only* input when no maps key is
/// configured for this build) — Pick on Map simply fills them, so
/// nothing about validation or submission changed.
/// Vehicle category + fare are not shown before submitting either — no
/// fare-estimate endpoint exists (GAP-1) — the real fare comes back the
/// instant `POST /api/v1/rides` succeeds, shown on [RideStatusScreen].
///
/// Also (build order step 10, ADR-0057): **Schedule for later** — a
/// date/time picker; the 1-24 hour window itself is enforced
/// server-side (BR-137), same "client does shape only, the backend is
/// authoritative" treatment every other business rule in this app
/// already gets — this screen doesn't duplicate that check. **Book for
/// someone else** — name/phone text entry for the linked contact, now
/// with an optional **Choose from Contacts** button (owner-approved
/// 2026-09-01, `mobile-app-implementation-plan.md` §6.2) that opens the
/// device's native contact picker via [ContactsApi] and prefills these
/// same fields; manual entry stays exactly as it was and remains the
/// fallback whenever Contacts permission is denied or nothing usable
/// was picked (§6.2's own documented "if denied" behavior).
///
/// Visual pass, 2026-09-08 (Phase 4 of the redesign — the "User home +
/// booking" phase): sectioned into cards, vehicle category and cab
/// tier moved from a dropdown to a tappable chip row (closer to the
/// Rapido/Uber-style vehicle picker the owner's brief asked for as a
/// UX reference), and a short, honest note added explaining that the
/// fare only appears after the ride is created — since no fare-estimate
/// endpoint exists, a "before you book" fare figure would be invented
/// data, which the brief explicitly rules out. All fields, validation,
/// and the create-ride call itself are unchanged; [startForSomeoneElse]
/// is the one new, additive entry point — it only pre-selects a toggle
/// that already existed, from [UserHomeTab]'s "Book for Someone Else"
/// quick action.
class BookRideScreen extends StatefulWidget {
  const BookRideScreen({super.key, this.startForSomeoneElse = false});

  final bool startForSomeoneElse;

  @override
  State<BookRideScreen> createState() => _BookRideScreenState();
}

class _BookRideScreenState extends State<BookRideScreen> {
  final _formKey = GlobalKey<FormState>();
  final _pickupLatController = TextEditingController();
  final _pickupLngController = TextEditingController();
  final _destinationLatController = TextEditingController();
  final _destinationLngController = TextEditingController();
  final _contactNameController = TextEditingController();
  final _contactPhoneController = TextEditingController();

  String _vehicleCategory = _vehicleCategories.first.$1;
  String _cabTier = _cabTiers.first.$1;
  bool _isScheduled = false;
  DateTime? _scheduledFor;
  late bool _isForSomeoneElse = widget.startForSomeoneElse;
  bool _isSubmitting = false;
  bool _isPickingContact = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    // The live route preview (Rapido-benchmarked redesign, 2026-09-08 —
    // "map-first") reads these controllers' current text on every
    // build; without a listener, typing a coordinate manually would
    // never actually trigger that rebuild (Pick on Map already calls
    // setState itself, but manual entry alone doesn't touch this
    // State's own setState at all otherwise).
    for (final controller in [
      _pickupLatController,
      _pickupLngController,
      _destinationLatController,
      _destinationLngController,
    ]) {
      controller.addListener(_onCoordinateFieldChanged);
    }
  }

  void _onCoordinateFieldChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _pickupLatController.dispose();
    _pickupLngController.dispose();
    _destinationLatController.dispose();
    _destinationLngController.dispose();
    _contactNameController.dispose();
    _contactPhoneController.dispose();
    super.dispose();
  }

  Future<void> _pickScheduledFor() async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: _scheduledFor ?? now.add(const Duration(hours: 2)),
      firstDate: now,
      lastDate: now.add(const Duration(days: 2)),
    );
    if (date == null || !mounted) return;
    final initialTime = TimeOfDay.fromDateTime(
      _scheduledFor ?? now.add(const Duration(hours: 2)),
    );
    final time = await showTimePicker(
      context: context,
      initialTime: initialTime,
    );
    if (time == null || !mounted) return;
    setState(() {
      _scheduledFor = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
    });
  }

  /// Requests Contacts permission — not before, and not at app launch;
  /// this is the only place in the app that ever does (§6.2) — then
  /// opens the native picker and prefills the name/phone fields above
  /// on a usable selection. Denied permission, a cancelled picker, or a
  /// contact with no phone number all resolve the same way: nothing
  /// changes, and the manual fields directly below stay exactly as they
  /// were, ready to type into.
  Future<void> _pickFromContacts() async {
    final contactsApi = context.read<ContactsApi>();
    setState(() => _isPickingContact = true);
    try {
      final granted = await contactsApi.requestPermission();
      if (!granted) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                "Contacts permission denied — enter the rider's details "
                'manually below.',
              ),
            ),
          );
        }
        return;
      }

      final picked = await contactsApi.pickContact();
      if (picked == null) return; // cancelled, or no usable phone number
      setState(() {
        _contactNameController.text = picked.name;
        _contactPhoneController.text = picked.phone;
      });
    } finally {
      if (mounted) setState(() => _isPickingContact = false);
    }
  }

  /// Fills [latController]/[lngController] with the picked point —
  /// pushed as a full screen (not embedded), since a usable map needs
  /// more room than this form's own scroll view can spare. A dismissed
  /// picker (back button, no confirm) leaves the fields exactly as they
  /// were.
  Future<void> _pickOnMap({
    required String title,
    required TextEditingController latController,
    required TextEditingController lngController,
  }) async {
    final initial =
        double.tryParse(latController.text.trim()) != null &&
            double.tryParse(lngController.text.trim()) != null
        ? RideGeoPoint(
            latitude: double.parse(latController.text.trim()),
            longitude: double.parse(lngController.text.trim()),
          )
        : null;
    final picked = await Navigator.of(context).push<RideGeoPoint>(
      MaterialPageRoute<RideGeoPoint>(
        builder: (_) =>
            LocationPickerScreen(title: title, initialCenter: initial),
      ),
    );
    if (picked == null || !mounted) return;
    setState(() {
      latController.text = picked.latitude.toStringAsFixed(6);
      lngController.text = picked.longitude.toStringAsFixed(6);
    });
  }

  /// `null` unless both fields currently hold a genuinely valid
  /// coordinate — used only to decide whether the live route preview
  /// at the top of this form has two real points to show; never used
  /// for submission (that still re-parses via the form's own
  /// validators at submit time, unchanged).
  RideGeoPoint? _parsedPoint(
    TextEditingController latController,
    TextEditingController lngController,
  ) {
    final lat = double.tryParse(latController.text.trim());
    final lng = double.tryParse(lngController.text.trim());
    if (lat == null || lng == null) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return RideGeoPoint(latitude: lat, longitude: lng);
  }

  /// A compact bottom-sheet picker — "modern bottom-sheet interactions
  /// ... for ride categories" per the owner's Rapido-benchmarked brief
  /// — replacing the previous inline chip row. [options] is a list of
  /// `(value, label)`; [icons], when supplied, draws one icon per row
  /// (vehicle categories have one; cab tiers don't). Pops with the
  /// picked value, or `null` if dismissed without choosing.
  Future<String?> _pickFromSheet({
    required String title,
    required List<(String, String)> options,
    required String selected,
    Map<String, IconData>? icons,
  }) {
    return showVistaarBottomSheet<String>(
      context: context,
      builder: (sheetContext) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: VistaarSpacing.sm),
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: Theme.of(sheetContext).textTheme.titleMedium,
            ),
          ),
          for (final (value, label) in options)
            ListTile(
              leading: icons == null ? null : Icon(icons[value]),
              title: Text(label),
              trailing: value == selected
                  ? Icon(Icons.check, color: Theme.of(sheetContext).colorScheme.primary)
                  : null,
              onTap: () => Navigator.of(sheetContext).pop(value),
            ),
        ],
      ),
    );
  }

  Future<void> _pickVehicleCategory() async {
    final picked = await _pickFromSheet(
      title: 'Choose a vehicle',
      options: [for (final (value, label, _) in _vehicleCategories) (value, label)],
      selected: _vehicleCategory,
      icons: {for (final (value, _, icon) in _vehicleCategories) value: icon},
    );
    if (picked != null && mounted) setState(() => _vehicleCategory = picked);
  }

  Future<void> _pickCabTier() async {
    final picked = await _pickFromSheet(
      title: 'Choose a cab tier',
      options: _cabTiers,
      selected: _cabTier,
    );
    if (picked != null && mounted) setState(() => _cabTier = picked);
  }

  String? _validateCoordinate(
    String? value, {
    required double min,
    required double max,
  }) {
    final parsed = double.tryParse((value ?? '').trim());
    if (parsed == null) return 'Enter a number';
    if (parsed < min || parsed > max) return 'Out of range';
    return null;
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_isScheduled && _scheduledFor == null) {
      setState(() => _errorMessage = 'Pick a date and time for the ride.');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });

    final api = context.read<RideApi>();
    try {
      final result = await api.createRide(
        pickup: RideGeoPoint(
          latitude: double.parse(_pickupLatController.text.trim()),
          longitude: double.parse(_pickupLngController.text.trim()),
        ),
        destination: RideGeoPoint(
          latitude: double.parse(_destinationLatController.text.trim()),
          longitude: double.parse(_destinationLngController.text.trim()),
        ),
        vehicleCategory: _vehicleCategory,
        cabTier: _vehicleCategory == 'CAB' ? _cabTier : null,
        // A fresh key per submit tap — see RideApi.createRide's own doc
        // comment for why that's the right call for a one-shot form,
        // unlike accept-offer's "reuse across retries" idempotency key.
        idempotencyKey: const Uuid().v4(),
        scheduledFor: _isScheduled ? _scheduledFor : null,
        linkedContact: _isForSomeoneElse
            ? LinkedContact(
                name: _contactNameController.text.trim(),
                phone: _contactPhoneController.text.trim(),
              )
            : null,
      );
      if (!mounted) return;
      // Outstanding Customer Penalty Display (ADR-0026, IMPLEMENTED
      // 2026-09-02) — "show the User any applicable outstanding
      // penalty before/while attempting to book." No separate preview
      // endpoint exists to show this *before* the ride is created (the
      // backend only computes it as part of Create Ride's own
      // response), so this is the earliest real point available:
      // shown immediately, before navigating away, never blocking the
      // booking itself (BR-057 — booking is never blocked by an unpaid
      // outstanding charge).
      final outstandingPenalty = result.outstandingPenalty;
      if (outstandingPenalty != null) {
        await showDialog<void>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Outstanding balance'),
            content: Text(
              'You have an outstanding balance of '
              '₹${outstandingPenalty.amount.toStringAsFixed(2)} from a '
              "previous ride's cancellation. This is separate from "
              "today's fare, which you still pay the Sarthi directly.",
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('OK'),
              ),
            ],
          ),
        );
      }
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => RideStatusScreen(rideId: result.rideId),
        ),
      );
    } on ApiException catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  Widget _coordinateField({
    required TextEditingController controller,
    required String label,
    required double min,
    required double max,
  }) {
    return TextFormField(
      controller: controller,
      keyboardType: const TextInputType.numberWithOptions(
        decimal: true,
        signed: true,
      ),
      inputFormatters: [
        FilteringTextInputFormatter.allow(RegExp(r'^-?\d*\.?\d*')),
      ],
      validator: (value) => _validateCoordinate(value, min: min, max: max),
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
      ),
    );
  }

  /// One location section (Pickup or Destination) — a titled card with
  /// the "Pick on Map" affordance up top when available, and the
  /// manual coordinate fields underneath as the always-present
  /// fallback/override. Layout only; behavior is [_pickOnMap] and
  /// [_coordinateField] above, unchanged.
  Widget _locationSection({
    required IconData icon,
    required String title,
    required String mapButtonTitle,
    required TextEditingController latController,
    required TextEditingController lngController,
  }) {
    final theme = Theme.of(context);
    return VistaarCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(icon, color: theme.colorScheme.primary),
              const SizedBox(width: VistaarSpacing.sm),
              Text(title, style: theme.textTheme.titleMedium),
            ],
          ),
          const SizedBox(height: VistaarSpacing.md),
          if (AppConfig.hasMapTilerApiKey) ...[
            OutlinedButton.icon(
              onPressed: () => _pickOnMap(
                title: mapButtonTitle,
                latController: latController,
                lngController: lngController,
              ),
              icon: const Icon(Icons.map_outlined),
              label: const Text('Pick on Map'),
            ),
            const SizedBox(height: VistaarSpacing.sm),
          ],
          Row(
            children: [
              Expanded(
                child: _coordinateField(
                  controller: latController,
                  label: 'Latitude',
                  min: -90,
                  max: 90,
                ),
              ),
              const SizedBox(width: VistaarSpacing.sm),
              Expanded(
                child: _coordinateField(
                  controller: lngController,
                  label: 'Longitude',
                  min: -180,
                  max: 180,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Book a Ride')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(VistaarSpacing.md),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Map-first (Rapido-benchmarked redesign, 2026-09-08):
                // a live route preview once both points are valid —
                // real coordinates already entered below, not a new
                // data source. Absent until then, rather than showing
                // an empty/placeholder map.
                if (_parsedPoint(_pickupLatController, _pickupLngController) != null &&
                    _parsedPoint(_destinationLatController, _destinationLngController) !=
                        null) ...[
                  ClipRRect(
                    borderRadius: BorderRadius.circular(VistaarRadius.surface),
                    child: RouteMapPreview(
                      pickup: _parsedPoint(_pickupLatController, _pickupLngController)!,
                      destination:
                          _parsedPoint(_destinationLatController, _destinationLngController),
                      height: 160,
                    ),
                  ),
                  const SizedBox(height: VistaarSpacing.md),
                ],
                _locationSection(
                  icon: Icons.trip_origin,
                  title: 'Pickup',
                  mapButtonTitle: 'Pickup Location',
                  latController: _pickupLatController,
                  lngController: _pickupLngController,
                ),
                const SizedBox(height: VistaarSpacing.md),
                _locationSection(
                  icon: Icons.place_outlined,
                  title: 'Destination',
                  mapButtonTitle: 'Destination Location',
                  latController: _destinationLatController,
                  lngController: _destinationLngController,
                ),
                const SizedBox(height: VistaarSpacing.md),
                VistaarCard(
                  padding: EdgeInsets.zero,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(
                          VistaarSpacing.md,
                          VistaarSpacing.md,
                          VistaarSpacing.md,
                          0,
                        ),
                        child: Text('Vehicle', style: theme.textTheme.titleMedium),
                      ),
                      // A compact, tappable row — opens a bottom sheet
                      // (Rapido-benchmarked redesign, 2026-09-08)
                      // instead of the previous inline chip row.
                      ListTile(
                        leading: Icon(
                          _vehicleCategories
                              .firstWhere((c) => c.$1 == _vehicleCategory)
                              .$3,
                          color: theme.colorScheme.primary,
                        ),
                        title: Text(
                          _vehicleCategories
                              .firstWhere((c) => c.$1 == _vehicleCategory)
                              .$2,
                        ),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: _pickVehicleCategory,
                      ),
                      if (_vehicleCategory == 'CAB')
                        ListTile(
                          leading: const SizedBox(width: 24),
                          title: Text(
                            'Cab tier: '
                            '${_cabTiers.firstWhere((t) => t.$1 == _cabTier).$2}',
                          ),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: _pickCabTier,
                        ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(
                          VistaarSpacing.md,
                          0,
                          VistaarSpacing.md,
                          VistaarSpacing.md,
                        ),
                        child: Text(
                          'Your fare is calculated and shown once your ride '
                          'is confirmed.',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: VistaarSpacing.md),
                VistaarCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Schedule for later'),
                        subtitle: _isScheduled && _scheduledFor != null
                            ? Text(_scheduledFor.toString().split('.').first)
                            : null,
                        value: _isScheduled,
                        onChanged: (value) =>
                            setState(() => _isScheduled = value),
                      ),
                      if (_isScheduled) ...[
                        const SizedBox(height: VistaarSpacing.sm),
                        OutlinedButton(
                          onPressed: _pickScheduledFor,
                          child: Text(
                            _scheduledFor == null
                                ? 'Pick date & time'
                                : 'Change date & time',
                          ),
                        ),
                      ],
                      const Divider(height: VistaarSpacing.lg),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Book for someone else'),
                        subtitle: const Text(
                          'The pickup code is also sent to their phone by '
                          'SMS',
                        ),
                        value: _isForSomeoneElse,
                        onChanged: (value) =>
                            setState(() => _isForSomeoneElse = value),
                      ),
                      if (_isForSomeoneElse) ...[
                        const SizedBox(height: VistaarSpacing.sm),
                        OutlinedButton.icon(
                          onPressed: _isPickingContact ? null : _pickFromContacts,
                          icon: _isPickingContact
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.contacts_outlined),
                          label: const Text('Choose from Contacts'),
                        ),
                        const SizedBox(height: VistaarSpacing.md),
                        TextFormField(
                          controller: _contactNameController,
                          decoration: const InputDecoration(
                            labelText: "Rider's name",
                            border: OutlineInputBorder(),
                          ),
                          validator: (value) =>
                              _isForSomeoneElse &&
                                  (value == null || value.trim().isEmpty)
                              ? 'Enter a name'
                              : null,
                        ),
                        const SizedBox(height: VistaarSpacing.md),
                        TextFormField(
                          controller: _contactPhoneController,
                          keyboardType: TextInputType.phone,
                          decoration: const InputDecoration(
                            labelText: "Rider's phone",
                            border: OutlineInputBorder(),
                          ),
                          validator: (value) =>
                              _isForSomeoneElse &&
                                  (value == null || value.trim().isEmpty)
                              ? 'Enter a phone number'
                              : null,
                        ),
                      ],
                    ],
                  ),
                ),
                if (_errorMessage != null) ...[
                  const SizedBox(height: VistaarSpacing.md),
                  Text(
                    _errorMessage!,
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ],
                const SizedBox(height: VistaarSpacing.lg),
                PrimaryButton(
                  label: 'Request Ride',
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
