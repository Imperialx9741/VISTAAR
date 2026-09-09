import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/driver_api.dart';
import '../../core/api/vehicle_api.dart';
import '../../core/uploads/evidence_upload_service.dart';
import '../../shared/design/vistaar_colors.dart';
import '../../shared/widgets/primary_button.dart';

/// Sarthi Onboarding — Phase 3 (KYC/document submission, vehicle
/// management), built 2026-09-04 to close this app's single highest-
/// priority remaining gap: the backend has always fully supported
/// document submission, vehicle registration, and admin approval
/// (modules/driver, modules/vehicle), but until this screen there was
/// no way to reach any of it from the app — a Sarthi could not
/// complete onboarding at all.
///
/// One screen, not several, deliberately: KYC documents, vehicle
/// registration, and vehicle documents are all steps of the *same*
/// linear process (BR-097/BR-122/BR-123, `POST .../online`'s own
/// documented precondition chain, api-contracts.md §10) and a Sarthi
/// benefits from seeing all of it — and its real approval status — in
/// one place rather than hunting across screens.
///
/// `_DocumentSection`'s Camera/Gallery buttons (`EvidenceUploadService`,
/// 2026-09-04) fill `evidence_uri` with a real presigned-upload result
/// (`POST /me/uploads`, ADR-0065); the text field itself stays present
/// and editable as a manual-reference fallback, not removed.
class SarthiOnboardingScreen extends StatefulWidget {
  const SarthiOnboardingScreen({super.key});

  @override
  State<SarthiOnboardingScreen> createState() => _SarthiOnboardingScreenState();
}

class _SarthiOnboardingScreenState extends State<SarthiOnboardingScreen> {
  bool _isLoading = true;
  String? _loadErrorMessage;

  DriverProfile? _profile;
  List<DriverDocument> _driverDocuments = const [];
  List<Vehicle> _vehicles = const [];
  List<VehicleDocument> _vehicleDocuments = const [];

  final _fullNameController = TextEditingController();

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _fullNameController.dispose();
    super.dispose();
  }

  /// A brand-new account has no driver.drivers row yet
  /// (`GET /me` -> RESOURCE_NOT_FOUND, api-contracts.md §9) — that is
  /// the expected starting state here, not an error to surface.
  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _loadErrorMessage = null;
    });
    final driverApi = context.read<DriverApi>();
    final vehicleApi = context.read<VehicleApi>();
    try {
      DriverProfile? profile;
      try {
        profile = await driverApi.getProfile();
      } on ApiException catch (error) {
        if (error.code != 'RESOURCE_NOT_FOUND') rethrow;
      }

      List<DriverDocument> driverDocuments = const [];
      List<Vehicle> vehicles = const [];
      List<VehicleDocument> vehicleDocuments = const [];
      if (profile != null) {
        driverDocuments = await driverApi.listDocuments();
        vehicles = await vehicleApi.listVehicles();
        if (vehicles.isNotEmpty) {
          vehicleDocuments = await vehicleApi.listDocuments(vehicles.first.vehicleId);
        }
      }

      if (!mounted) return;
      setState(() {
        _profile = profile;
        _fullNameController.text = profile?.fullName ?? '';
        _driverDocuments = driverDocuments;
        _vehicles = vehicles;
        _vehicleDocuments = vehicleDocuments;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => _loadErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _saveProfileName() async {
    final fullName = _fullNameController.text.trim();
    if (fullName.isEmpty) return;
    try {
      await context.read<DriverApi>().updateProfile(fullName: fullName);
      await _load();
    } on ApiException catch (error) {
      if (mounted) _showError(error.message);
    }
  }

  Future<void> _submitDriverDocument(String documentType, String reference) async {
    try {
      await context.read<DriverApi>().submitDocument(
        documentType: documentType,
        evidenceUri: reference.isEmpty ? null : reference,
      );
      await _load();
    } on ApiException catch (error) {
      if (mounted) _showError(error.message);
    }
  }

  Future<void> _addVehicle({
    required String category,
    String? cabTier,
    required String registrationNumber,
  }) async {
    try {
      await context.read<VehicleApi>().addVehicle(
        category: category,
        cabTier: cabTier,
        registrationNumber: registrationNumber,
      );
      await _load();
    } on ApiException catch (error) {
      if (mounted) _showError(error.message);
    }
  }

  Future<void> _submitVehicleDocument(String documentType, String reference) async {
    if (_vehicles.isEmpty) return;
    try {
      await context.read<VehicleApi>().submitDocument(
        vehicleId: _vehicles.first.vehicleId,
        documentType: documentType,
        evidenceUri: reference.isEmpty ? null : reference,
      );
      await _load();
    } on ApiException catch (error) {
      if (mounted) _showError(error.message);
    }
  }

  Future<void> _activateVehicle() async {
    if (_vehicles.isEmpty) return;
    try {
      await context.read<VehicleApi>().activateVehicle(_vehicles.first.vehicleId);
      await _load();
    } on ApiException catch (error) {
      if (mounted) _showError(error.message);
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sarthi Onboarding')),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    if (_loadErrorMessage != null) ...[
                      _ErrorBanner(message: _loadErrorMessage!),
                      const SizedBox(height: 16),
                    ],
                    _buildStatusSummary(context),
                    const SizedBox(height: 24),
                    _buildProfileSection(context),
                    if (_profile != null) ...[
                      const SizedBox(height: 24),
                      _DocumentSection(
                        title: 'Personal Documents',
                        documentTypes: const ['GOVERNMENT_ID', 'DRIVING_LICENSE'],
                        documents: _driverDocuments
                            .map(
                              (d) => _DocumentRow(
                                type: d.documentType,
                                status: d.verificationStatus,
                                createdAt: d.createdAt,
                              ),
                            )
                            .toList(growable: false),
                        onSubmit: _submitDriverDocument,
                      ),
                      const SizedBox(height: 24),
                      _buildVehicleSection(context),
                      if (_vehicles.isNotEmpty) ...[
                        const SizedBox(height: 24),
                        _DocumentSection(
                          title: 'Vehicle Documents',
                          documentTypes: const ['RC', 'INSURANCE'],
                          documents: _vehicleDocuments
                              .map(
                                (d) => _DocumentRow(
                                  type: d.documentType,
                                  status: d.verificationStatus,
                                  createdAt: d.createdAt,
                                ),
                              )
                              .toList(growable: false),
                          onSubmit: _submitVehicleDocument,
                        ),
                      ],
                    ],
                  ],
                ),
              ),
      ),
    );
  }

  Widget _buildStatusSummary(BuildContext context) {
    final activeVehicles = _vehicles.where((v) => v.isActive);
    final activeVehicle = activeVehicles.isEmpty ? null : activeVehicles.first;
    final ready = (_profile?.isApproved ?? false) &&
        activeVehicle != null &&
        activeVehicle.isApproved;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        // VISTAAR's centralized success token, not a literal green —
        // brand-color compliance sweep, 2026-09-08.
        color: ready
            ? VistaarColors.successContainer
            : Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            ready ? 'Ready to go online' : 'Onboarding in progress',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text('Driver: ${_profile?.verificationStatus ?? 'Not started'}'),
          Text(
            'Vehicle: ${_vehicles.isEmpty ? 'Not registered' : _vehicles.first.verificationStatus}',
          ),
        ],
      ),
    );
  }

  Widget _buildProfileSection(BuildContext context) {
    if (_profile != null) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Your Name', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        TextField(
          controller: _fullNameController,
          decoration: const InputDecoration(
            labelText: 'Full name',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        PrimaryButton(label: 'Save', onPressed: _saveProfileName),
      ],
    );
  }

  Widget _buildVehicleSection(BuildContext context) {
    if (_vehicles.isEmpty) {
      return _AddVehicleForm(onAdd: _addVehicle);
    }
    final vehicle = _vehicles.first;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Vehicle', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('${vehicle.category} — ${vehicle.registrationNumber}'),
          subtitle: Text(
            '${vehicle.verificationStatus} · ${vehicle.operationalStatus}',
          ),
        ),
        if (vehicle.isApproved && !vehicle.isActive) ...[
          const SizedBox(height: 8),
          PrimaryButton(label: 'Activate Vehicle', onPressed: _activateVehicle),
        ],
      ],
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Text(
      message,
      textAlign: TextAlign.center,
      style: TextStyle(color: Theme.of(context).colorScheme.error),
    );
  }
}

class _DocumentRow {
  const _DocumentRow({
    required this.type,
    required this.status,
    required this.createdAt,
  });
  final String type;
  final String status;
  final DateTime createdAt;
}

class _DocumentSection extends StatefulWidget {
  const _DocumentSection({
    required this.title,
    required this.documentTypes,
    required this.documents,
    required this.onSubmit,
  });

  final String title;
  final List<String> documentTypes;
  final List<_DocumentRow> documents;
  final Future<void> Function(String documentType, String reference) onSubmit;

  @override
  State<_DocumentSection> createState() => _DocumentSectionState();
}

class _DocumentSectionState extends State<_DocumentSection> {
  late String _selectedType = widget.documentTypes.first;
  final _referenceController = TextEditingController();
  bool _isSubmitting = false;
  bool _isUploading = false;
  String? _uploadErrorMessage;

  @override
  void dispose() {
    _referenceController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _isSubmitting = true);
    await widget.onSubmit(_selectedType, _referenceController.text.trim());
    if (mounted) {
      _referenceController.clear();
      setState(() => _isSubmitting = false);
    }
  }

  /// Photographs/picks the actual document (2026-09-04) — the resulting
  /// `uri` fills [_referenceController] exactly as if typed by hand, so
  /// [_submit] above needs no change at all; the field stays editable
  /// as a manual override.
  Future<void> _pickAndUpload(ImageSource source) async {
    setState(() {
      _isUploading = true;
      _uploadErrorMessage = null;
    });
    final uploads = context.read<EvidenceUploadService>();
    final driverApi = context.read<DriverApi>();
    try {
      final uri = await uploads.pickAndUploadImage(
        source: source,
        requestUploadUrl: (contentType) =>
            driverApi.requestUploadUrl(contentType: contentType),
      );
      if (mounted && uri != null) {
        setState(() => _referenceController.text = uri);
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _uploadErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isUploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(widget.title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (widget.documents.isEmpty)
          const Text('No documents submitted yet.')
        else
          for (final doc in widget.documents)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(doc.type),
              trailing: Chip(
                label: Text(doc.status),
                visualDensity: VisualDensity.compact,
              ),
            ),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          initialValue: _selectedType,
          decoration: const InputDecoration(
            labelText: 'Document type',
            border: OutlineInputBorder(),
          ),
          items: widget.documentTypes
              .map((type) => DropdownMenuItem(value: type, child: Text(type)))
              .toList(growable: false),
          onChanged: (value) {
            if (value != null) setState(() => _selectedType = value);
          },
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _referenceController,
          decoration: const InputDecoration(
            labelText: 'Document reference (optional)',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _isUploading
                    ? null
                    : () => _pickAndUpload(ImageSource.camera),
                icon: const Icon(Icons.camera_alt_outlined),
                label: const Text('Camera'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _isUploading
                    ? null
                    : () => _pickAndUpload(ImageSource.gallery),
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Gallery'),
              ),
            ),
          ],
        ),
        if (_isUploading) ...[
          const SizedBox(height: 8),
          const Center(
            child: SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2.5),
            ),
          ),
        ],
        if (_uploadErrorMessage != null) ...[
          const SizedBox(height: 8),
          Text(
            _uploadErrorMessage!,
            textAlign: TextAlign.center,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 8),
        PrimaryButton(
          label: 'Submit Document',
          isLoading: _isSubmitting,
          onPressed: _submit,
        ),
      ],
    );
  }
}

class _AddVehicleForm extends StatefulWidget {
  const _AddVehicleForm({required this.onAdd});

  final Future<void> Function({
    required String category,
    String? cabTier,
    required String registrationNumber,
  })
  onAdd;

  @override
  State<_AddVehicleForm> createState() => _AddVehicleFormState();
}

class _AddVehicleFormState extends State<_AddVehicleForm> {
  static const _categories = ['BIKE', 'AUTO', 'CAB'];
  static const _cabTiers = ['ECO', 'PREMIUM', 'PREMIUM_PLUS'];

  String _category = 'CAB';
  String _cabTier = 'ECO';
  final _registrationController = TextEditingController();
  bool _isSubmitting = false;

  @override
  void dispose() {
    _registrationController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final registration = _registrationController.text.trim();
    if (registration.isEmpty) return;
    setState(() => _isSubmitting = true);
    await widget.onAdd(
      category: _category,
      cabTier: _category == 'CAB' ? _cabTier : null,
      registrationNumber: registration,
    );
    if (mounted) setState(() => _isSubmitting = false);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Register Your Vehicle', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          initialValue: _category,
          decoration: const InputDecoration(
            labelText: 'Category',
            border: OutlineInputBorder(),
          ),
          items: _categories
              .map((c) => DropdownMenuItem(value: c, child: Text(c)))
              .toList(growable: false),
          onChanged: (value) {
            if (value != null) setState(() => _category = value);
          },
        ),
        if (_category == 'CAB') ...[
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            initialValue: _cabTier,
            decoration: const InputDecoration(
              labelText: 'Cab tier',
              border: OutlineInputBorder(),
            ),
            items: _cabTiers
                .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                .toList(growable: false),
            onChanged: (value) {
              if (value != null) setState(() => _cabTier = value);
            },
          ),
        ],
        const SizedBox(height: 8),
        TextField(
          controller: _registrationController,
          decoration: const InputDecoration(
            labelText: 'Registration number',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 8),
        PrimaryButton(
          label: 'Register Vehicle',
          isLoading: _isSubmitting,
          onPressed: _submit,
        ),
      ],
    );
  }
}
