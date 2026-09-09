import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

import '../api/api_exception.dart';
import '../api/upload_target.dart';

/// Real camera/gallery capture + presigned-S3 upload, built 2026-09-04
/// to close a gap flagged in three places (`SarthiOnboardingScreen`'s
/// document sections, `GpsDisputeScreen`'s evidence form): all three
/// previously accepted only a free-text "reference" typed by hand, even
/// though the presigned-upload endpoints they'd POST to
/// (`DriverApi.requestUploadUrl`, `RideApi.
/// requestGpsDisputeEvidenceUploadUrl`) were always real and fully
/// tested — nothing in this app had ever picked an actual file to send
/// them.
///
/// `image_picker`'s own Android plugin manifest (verified directly —
/// `image_picker_android`'s AAR) declares no `CAMERA`/storage
/// permission at all: it hands off to the system camera/gallery app via
/// intent, which manages its own permission, not this app's — no
/// `AndroidManifest.xml` change was needed to add this capability.
///
/// Every real `image_picker`/`http` call is behind an injected closure
/// (optional, defaulting to the real implementation) — the same
/// "constructor-injected dependency, real implementation by default"
/// shape `ContactsApi`/`PushNotificationManager` already established,
/// for the same reason: `image_picker` needs a native platform channel
/// no widget/unit test here can provide.
class EvidenceUploadService {
  EvidenceUploadService({
    Future<XFile?> Function({required ImageSource source})? pickImage,
    Future<XFile?> Function({required ImageSource source})? pickVideo,
    Future<http.MultipartFile> Function(String field, String path)? readFile,
    http.Client? httpClient,
  }) : _pickImage =
           pickImage ??
           ((({required ImageSource source}) => ImagePicker().pickImage(
             source: source,
             imageQuality: 85,
           ))),
       _pickVideo =
           pickVideo ??
           ((({required ImageSource source}) =>
               ImagePicker().pickVideo(source: source))),
       _readFile = readFile ?? http.MultipartFile.fromPath,
       _httpClient = httpClient ?? http.Client();

  final Future<XFile?> Function({required ImageSource source}) _pickImage;
  final Future<XFile?> Function({required ImageSource source}) _pickVideo;
  // Real `dart:io` disk I/O — a real Future that only resolves via the
  // actual OS event loop, which flutter_test's fake-async `pump()` loop
  // cannot drive. Injectable so a widget test can substitute a plain
  // in-memory `MultipartFile.fromBytes` instead; the unit tests in
  // evidence_upload_service_test.dart exercise the real default
  // directly (plain `test()`, no widget pump involved, so real I/O
  // there is unproblematic).
  final Future<http.MultipartFile> Function(String field, String path)
  _readFile;
  final http.Client _httpClient;

  Future<XFile?> pickImage(ImageSource source) => _pickImage(source: source);

  Future<XFile?> pickVideo(ImageSource source) => _pickVideo(source: source);

  /// The backend's own allowed set (api-contracts.md §9 — `image/jpeg`,
  /// `image/png`, `image/webp`, `application/pdf`) plus common video
  /// types the GPS-dispute evidence endpoint accepts no narrower a set
  /// for (`shared/storage.py` validates by a general allow-list, not a
  /// per-caller one). Falls back to `image/jpeg` for an unrecognized
  /// extension rather than failing the pick outright — the upload-url
  /// endpoint itself is the real, authoritative validator.
  String contentTypeFor(String path) {
    final ext = path.split('.').last.toLowerCase();
    switch (ext) {
      case 'png':
        return 'image/png';
      case 'webp':
        return 'image/webp';
      case 'pdf':
        return 'application/pdf';
      case 'mp4':
        return 'video/mp4';
      case 'mov':
        return 'video/quicktime';
      case 'jpg':
      case 'jpeg':
      default:
        return 'image/jpeg';
    }
  }

  /// Uploads [file] to [target] — a real multipart POST, every
  /// [UploadTarget.uploadFields] key as its own text field, the file
  /// itself added last. `http.MultipartRequest` always encodes all
  /// `fields` before any `files` regardless of call order (verified
  /// directly against the `http` package's own `_finalize()`), so this
  /// satisfies S3's "file must be the last field" requirement without
  /// needing to build the multipart body by hand.
  Future<void> upload(UploadTarget target, XFile file) async {
    final request = http.MultipartRequest('POST', Uri.parse(target.uploadUrl))
      ..fields.addAll(target.uploadFields);
    request.files.add(await _readFile('file', file.path));

    final http.StreamedResponse response;
    try {
      response = await _httpClient.send(request);
    } on Object catch (error) {
      throw ApiException(
        code: 'NETWORK_ERROR',
        message: 'Could not upload the file: $error',
      );
    }

    if (response.statusCode >= 300) {
      throw ApiException(
        code: 'UPLOAD_FAILED',
        message: 'Upload failed (HTTP ${response.statusCode}).',
      );
    }
  }

  /// Picks an image from [source], requests an upload target via
  /// [requestUploadUrl], uploads it, and returns the resulting
  /// `uri` to use as `evidence_uri` — or `null` if the user cancelled
  /// the picker (no upload attempted).
  Future<String?> pickAndUploadImage({
    required ImageSource source,
    required Future<UploadTarget> Function(String contentType) requestUploadUrl,
  }) async {
    final file = await pickImage(source);
    if (file == null) return null;
    final target = await requestUploadUrl(contentTypeFor(file.path));
    await upload(target, file);
    return target.uri;
  }

  /// Same as [pickAndUploadImage], for video evidence.
  Future<String?> pickAndUploadVideo({
    required ImageSource source,
    required Future<UploadTarget> Function(String contentType) requestUploadUrl,
  }) async {
    final file = await pickVideo(source);
    if (file == null) return null;
    final target = await requestUploadUrl(contentTypeFor(file.path));
    await upload(target, file);
    return target.uri;
  }
}
