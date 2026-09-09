import 'dart:async';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/api/api_exception.dart';
import '../../core/api/ride_api.dart';
import '../../core/api/upload_target.dart';
import '../../core/uploads/evidence_upload_service.dart';
import '../../shared/design/vistaar_colors.dart';
import '../../shared/widgets/primary_button.dart';

/// GPS Dispute — shared by both roles (customer and driver own the same
/// ride's dispute equally, api-contracts.md §77), built 2026-09-04 to
/// close the last remaining shared mobile gap flagged in this app's own
/// status document: a GPS dispute is auto-opened by the backend
/// (BR-124/BR-125, ADR-0032) when a driver's Mark Arrived/Complete Ride
/// call fails GPS verification too many times — the driver reaches this
/// screen directly from that error ([RideExecutionScreen] catches
/// `GPS_VERIFICATION_FAILED`'s `dispute_id`, see that screen's own doc
/// comment); the customer reaches it via [RideStatusScreen]'s new "GPS
/// Dispute" banner, itself powered by the discovery endpoint ADR-0074
/// added specifically because nothing else ever told a customer a
/// dispute existed on their own ride.
///
/// PHOTO/VIDEO evidence's Camera/Gallery buttons
/// (`EvidenceUploadService`, 2026-09-04) fill the evidence-reference
/// field with a real presigned-upload result, same as
/// `SarthiOnboardingScreen`'s document sections; DOCUMENT still uses a
/// plain text field (no separate raw-file picker exists in this app —
/// see `_EvidenceForm._pickAndUpload`'s own doc comment for why that's
/// an acceptable, not silently glossed-over, scope line). TEXT evidence
/// needs no reference at all.
class GpsDisputeScreen extends StatefulWidget {
  const GpsDisputeScreen({required this.rideId, required this.disputeId, super.key});

  final String rideId;
  final String disputeId;

  @override
  State<GpsDisputeScreen> createState() => _GpsDisputeScreenState();
}

class _GpsDisputeScreenState extends State<GpsDisputeScreen> {
  GpsDispute? _dispute;
  bool _isLoading = true;
  String? _loadErrorMessage;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _loadErrorMessage = null;
    });
    try {
      final dispute = await context.read<RideApi>().getGpsDispute(
        widget.rideId,
        widget.disputeId,
      );
      if (!mounted) return;
      setState(() => _dispute = dispute);
    } on ApiException catch (error) {
      if (mounted) setState(() => _loadErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _submitEvidence(String evidenceType, String value) async {
    try {
      await context.read<RideApi>().submitGpsDisputeEvidence(
        widget.rideId,
        widget.disputeId,
        evidenceType: evidenceType,
        uri: evidenceType == 'TEXT' ? null : (value.isEmpty ? null : value),
        text: evidenceType == 'TEXT' ? value : null,
      );
      await _load();
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  String _humanizeStatus(String status) {
    switch (status) {
      case 'ARRIVAL':
        return 'Pickup';
      case 'COMPLETION':
        return 'Drop-off';
      default:
        return status;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('GPS Dispute')),
      body: SafeArea(
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : _dispute == null
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _loadErrorMessage ?? 'Could not load this dispute.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              )
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(
                  padding: const EdgeInsets.all(24),
                  children: [
                    _buildSummary(context, _dispute!),
                    const SizedBox(height: 24),
                    Text('Evidence', style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 8),
                    if (_dispute!.evidence.isEmpty)
                      const Text('No evidence submitted yet.')
                    else
                      for (final e in _dispute!.evidence) _buildEvidenceTile(context, e),
                    if (_dispute!.isOpen) ...[
                      const SizedBox(height: 24),
                      const Divider(),
                      const SizedBox(height: 16),
                      _EvidenceForm(
                        onSubmit: _submitEvidence,
                        requestUploadUrl: (contentType) => context
                            .read<RideApi>()
                            .requestGpsDisputeEvidenceUploadUrl(
                              widget.rideId,
                              widget.disputeId,
                              contentType: contentType,
                            ),
                      ),
                    ],
                  ],
                ),
              ),
      ),
    );
  }

  Widget _buildSummary(BuildContext context, GpsDispute dispute) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        // VISTAAR's centralized warning token, not a literal orange —
        // brand-color compliance sweep, 2026-09-08.
        color: dispute.isOpen
            ? VistaarColors.warningContainer
            : Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${_humanizeStatus(dispute.verificationType)} verification dispute',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text('Status: ${dispute.status}'),
          if (dispute.isOpen)
            Text(
              'Submit evidence by '
              '${dispute.evidenceDeadline.toLocal().toString().split('.').first}',
            ),
          if (dispute.decision != null) ...[
            Text('Decision: ${dispute.decision}'),
            if (dispute.decidedReason != null) Text(dispute.decidedReason!),
          ],
        ],
      ),
    );
  }

  Widget _buildEvidenceTile(BuildContext context, GpsDisputeEvidence evidence) {
    return Card(
      child: ListTile(
        title: Text(evidence.evidenceType),
        subtitle: Text(
          evidence.textExplanation ?? evidence.uri ?? '',
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: Text(
          evidence.submittedAt.toLocal().toString().split(' ').first,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ),
    );
  }
}

class _EvidenceForm extends StatefulWidget {
  const _EvidenceForm({required this.onSubmit, required this.requestUploadUrl});

  final Future<void> Function(String evidenceType, String value) onSubmit;

  /// Requests a presigned-upload target for the Camera/Gallery buttons
  /// below (2026-09-04) — [_GpsDisputeScreenState] supplies the real
  /// `RideApi.requestGpsDisputeEvidenceUploadUrl` call, already scoped
  /// to this dispute.
  final Future<UploadTarget> Function(String contentType) requestUploadUrl;

  @override
  State<_EvidenceForm> createState() => _EvidenceFormState();
}

class _EvidenceFormState extends State<_EvidenceForm> {
  static const _types = [
    ('TEXT', 'Text explanation'),
    ('PHOTO', 'Photo'),
    ('VIDEO', 'Video'),
    ('DOCUMENT', 'Document'),
  ];

  String _type = 'TEXT';
  final _valueController = TextEditingController();
  bool _isSubmitting = false;
  bool _isUploading = false;
  String? _uploadErrorMessage;

  @override
  void dispose() {
    _valueController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final value = _valueController.text.trim();
    if (value.isEmpty) return;
    setState(() => _isSubmitting = true);
    await widget.onSubmit(_type, value);
    if (mounted) {
      _valueController.clear();
      setState(() => _isSubmitting = false);
    }
  }

  /// Captures/picks the actual photo or video (2026-09-04) — the
  /// resulting `uri` fills [_valueController] exactly as if typed by
  /// hand; the field stays editable as a manual override. PHOTO/VIDEO
  /// only — DOCUMENT still uses the plain text field (no separate raw-
  /// file picker exists in this app; a real photo of a document already
  /// covers PHOTO, the far more common evidence shape here).
  Future<void> _pickAndUpload(ImageSource source) async {
    setState(() {
      _isUploading = true;
      _uploadErrorMessage = null;
    });
    final uploads = context.read<EvidenceUploadService>();
    try {
      final uri = _type == 'VIDEO'
          ? await uploads.pickAndUploadVideo(
              source: source,
              requestUploadUrl: widget.requestUploadUrl,
            )
          : await uploads.pickAndUploadImage(
              source: source,
              requestUploadUrl: widget.requestUploadUrl,
            );
      if (mounted && uri != null) {
        setState(() => _valueController.text = uri);
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _uploadErrorMessage = error.message);
    } finally {
      if (mounted) setState(() => _isUploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canCapture = _type == 'PHOTO' || _type == 'VIDEO';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Submit Evidence', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          initialValue: _type,
          decoration: const InputDecoration(
            labelText: 'Evidence type',
            border: OutlineInputBorder(),
          ),
          items: [
            for (final (value, label) in _types)
              DropdownMenuItem(value: value, child: Text(label)),
          ],
          onChanged: (value) => setState(() => _type = value ?? _type),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _valueController,
          maxLines: _type == 'TEXT' ? 4 : 1,
          decoration: InputDecoration(
            labelText: _type == 'TEXT' ? 'Explanation' : 'Evidence reference',
            border: const OutlineInputBorder(),
          ),
        ),
        if (canCapture) ...[
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
        ],
        const SizedBox(height: 8),
        PrimaryButton(
          label: 'Submit',
          isLoading: _isSubmitting,
          onPressed: _submit,
        ),
      ],
    );
  }
}
