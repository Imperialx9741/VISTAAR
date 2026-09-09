// Unit tests for EvidenceUploadService (2026-09-04 — see that
// service's own doc comment for why this exists): content-type
// detection, pick-cancelled short-circuiting, and the real multipart
// upload, each driven against injected fakes/a real MockClient
// standing in for the native picker and the backend/S3.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';

import 'package:vistaar_mobile/core/api/api_exception.dart';
import 'package:vistaar_mobile/core/api/upload_target.dart';
import 'package:vistaar_mobile/core/uploads/evidence_upload_service.dart';

Future<XFile> _tempImageFile() async {
  final file = File(
    '${Directory.systemTemp.path}/evidence_upload_service_test_'
    '${DateTime.now().microsecondsSinceEpoch}.jpg',
  );
  await file.writeAsBytes([1, 2, 3, 4]);
  addTearDown(() => file.deleteSync());
  return XFile(file.path);
}

void main() {
  group('contentTypeFor', () {
    final service = EvidenceUploadService();

    test('maps known extensions', () {
      expect(service.contentTypeFor('a.jpg'), 'image/jpeg');
      expect(service.contentTypeFor('a.JPEG'), 'image/jpeg');
      expect(service.contentTypeFor('a.png'), 'image/png');
      expect(service.contentTypeFor('a.webp'), 'image/webp');
      expect(service.contentTypeFor('a.pdf'), 'application/pdf');
      expect(service.contentTypeFor('a.mp4'), 'video/mp4');
      expect(service.contentTypeFor('a.mov'), 'video/quicktime');
    });

    test('falls back to image/jpeg for an unrecognized extension', () {
      expect(service.contentTypeFor('a.heic'), 'image/jpeg');
    });
  });

  group('upload', () {
    test('sends every upload_field plus the file as a real multipart POST', (
        ) async {
      late http.Request captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response('', 200);
      });
      final service = EvidenceUploadService(httpClient: client);
      final file = await _tempImageFile();

      await service.upload(
        const UploadTarget(
          uploadUrl: 'https://s3.example.com/bucket',
          uploadFields: {'key': 'evidence/abc.jpg', 'policy': 'xyz'},
          uri: 's3://bucket/evidence/abc.jpg',
        ),
        file,
      );

      expect(captured.url.toString(), 'https://s3.example.com/bucket');
      expect(
        captured.headers['content-type'],
        contains('multipart/form-data'),
      );
      final body = String.fromCharCodes(captured.bodyBytes);
      expect(body, contains('evidence/abc.jpg'));
      expect(body, contains('xyz'));
      // Fields before the file — S3's own requirement (verified against
      // the `http` package's own MultipartRequest._finalize(), which
      // always encodes all fields first regardless of call order; this
      // asserts that guarantee held for this actual request).
      expect(body.indexOf('xyz'), lessThan(body.indexOf('filename=')));
    });

    test('throws ApiException on a non-2xx response', () async {
      final client = MockClient(
        (_) async => http.Response('access denied', 403),
      );
      final service = EvidenceUploadService(httpClient: client);
      final file = await _tempImageFile();

      await expectLater(
        service.upload(
          const UploadTarget(
            uploadUrl: 'https://s3.example.com/bucket',
            uploadFields: {},
            uri: 's3://bucket/x.jpg',
          ),
          file,
        ),
        throwsA(
          isA<ApiException>().having((e) => e.code, 'code', 'UPLOAD_FAILED'),
        ),
      );
    });
  });

  group('pickAndUploadImage', () {
    test('returns null without requesting an upload when the picker is cancelled', (
        ) async {
      var requested = false;
      final service = EvidenceUploadService(
        pickImage: ({required source}) async => null,
      );

      final result = await service.pickAndUploadImage(
        source: ImageSource.camera,
        requestUploadUrl: (contentType) async {
          requested = true;
          return const UploadTarget(
            uploadUrl: 'https://s3.example.com',
            uploadFields: {},
            uri: 's3://x',
          );
        },
      );

      expect(result, isNull);
      expect(requested, isFalse);
    });

    test('picks, uploads, and returns the target uri', () async {
      final client = MockClient((_) async => http.Response('', 200));
      String? requestedContentType;
      final service = EvidenceUploadService(
        pickImage: ({required source}) async => _tempImageFile(),
        httpClient: client,
      );

      final result = await service.pickAndUploadImage(
        source: ImageSource.gallery,
        requestUploadUrl: (contentType) async {
          requestedContentType = contentType;
          return const UploadTarget(
            uploadUrl: 'https://s3.example.com/bucket',
            uploadFields: {'key': 'evidence/x.jpg'},
            uri: 's3://bucket/evidence/x.jpg',
          );
        },
      );

      expect(result, 's3://bucket/evidence/x.jpg');
      expect(requestedContentType, 'image/jpeg');
    });
  });
}
