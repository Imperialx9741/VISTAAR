/// A presigned S3 POST target (ADR-0031; presigned POST since ADR-0065,
/// 2026-09-03) — the shared response shape every "request an upload
/// URL" endpoint in this backend returns (`POST /api/v1/drivers/me/
/// uploads`, `POST /api/v1/rides/{ride_id}/gps-disputes/{dispute_id}/
/// evidence/upload-url`). The client POSTs the file directly to
/// [uploadUrl] as multipart form data with every key in [uploadFields]
/// included as a form field and the file itself as the **last** field
/// (S3's own requirement) — see `EvidenceUploadService.upload()`. [uri]
/// is then supplied as-is to whichever endpoint's own `evidence_uri`/
/// `uri`/`profile_photo_uri` field expects it.
class UploadTarget {
  const UploadTarget({
    required this.uploadUrl,
    required this.uploadFields,
    required this.uri,
  });

  factory UploadTarget.fromJson(Map<String, dynamic> json) => UploadTarget(
    uploadUrl: json['upload_url'] as String,
    uploadFields: (json['upload_fields'] as Map<String, dynamic>).map(
      (key, value) => MapEntry(key, value as String),
    ),
    uri: json['uri'] as String,
  );

  final String uploadUrl;
  final Map<String, String> uploadFields;
  final String uri;
}
