// Widget tests for SarthiOnboardingScreen (Phase 3, built 2026-09-04 —
// see that screen's own doc comment for why this exists): profile
// creation, document submission, and vehicle registration, each driven
// against a real MockClient standing in for the backend.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/driver_api.dart';
import 'package:vistaar_mobile/core/api/vehicle_api.dart';
import 'package:vistaar_mobile/core/uploads/evidence_upload_service.dart';
import 'package:vistaar_mobile/features/onboarding/sarthi_onboarding_screen.dart';

Widget _wrap(http.Client mockHttpClient, {EvidenceUploadService? uploads}) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<DriverApi>(create: (_) => DriverApi(apiClient, () => 'token')),
      Provider<VehicleApi>(create: (_) => VehicleApi(apiClient, () => 'token')),
      // A picker that always cancels (returns null) unless a test
      // supplies its own — every existing test below never taps
      // Camera/Gallery, so this default is never exercised by them.
      Provider<EvidenceUploadService>(
        create: (_) =>
            uploads ?? EvidenceUploadService(pickImage: ({required source}) async => null),
      ),
    ],
    child: const MaterialApp(home: SarthiOnboardingScreen()),
  );
}

String _envelope(Object? data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Map<String, dynamic> _profileJson({
  String verificationStatus = 'PENDING',
}) => {
  'driver_id': 'driver-1',
  'phone': '+919999999999',
  'full_name': 'Ravi Kumar',
  'profile_photo_uri': null,
  'verification_status': verificationStatus,
  'operational_status': 'OFFLINE',
  'strikes': 0,
  'created_at': '2026-09-04T00:00:00Z',
  'updated_at': '2026-09-04T00:00:00Z',
};

Map<String, dynamic> _vehicleJson({
  String verificationStatus = 'PENDING',
  String operationalStatus = 'INACTIVE',
}) => {
  'vehicle_id': 'vehicle-1',
  'category': 'CAB',
  'cab_tier': 'ECO',
  'registration_number': 'BR01AB1234',
  'make': null,
  'model': null,
  'verification_status': verificationStatus,
  'operational_status': operationalStatus,
  'created_at': '2026-09-04T00:00:00Z',
  'updated_at': '2026-09-04T00:00:00Z',
};

void main() {
  testWidgets('a brand-new driver sees the name form, not a load error', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _errorEnvelope('RESOURCE_NOT_FOUND', 'Driver profile not found.'),
            404,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Onboarding in progress'), findsOneWidget);
    expect(find.text('Driver: Not started'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Full name'), findsOneWidget);
    // Nothing past the profile step is shown yet.
    expect(find.text('Personal Documents'), findsNothing);
  });

  testWidgets('saving a name creates the profile and reveals document/vehicle sections', (
    tester,
  ) async {
    var profileCreated = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'GET' && request.url.path == '/api/v1/drivers/me') {
            if (!profileCreated) {
              return http.Response(
                _errorEnvelope('RESOURCE_NOT_FOUND', 'Not found.'),
                404,
              );
            }
            return http.Response(_envelope(_profileJson()), 200);
          }
          if (request.method == 'PATCH' &&
              request.url.path == '/api/v1/drivers/me') {
            profileCreated = true;
            return http.Response(_envelope(_profileJson()), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/documents') {
            return http.Response(_envelope({'documents': []}), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/vehicles') {
            return http.Response(_envelope({'vehicles': []}), 200);
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Full name'),
      'Ravi Kumar',
    );
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(find.text('Personal Documents'), findsOneWidget);
    expect(find.text('Register Your Vehicle'), findsOneWidget);
  });

  testWidgets('submitting a driver document posts the selected type and reference', (
    tester,
  ) async {
    Map<String, dynamic>? submittedBody;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'GET' && request.url.path == '/api/v1/drivers/me') {
            return http.Response(_envelope(_profileJson()), 200);
          }
          if (request.method == 'POST' &&
              request.url.path == '/api/v1/drivers/me/documents') {
            submittedBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              _envelope({
                'document_id': 'doc-1',
                'document_type': 'GOVERNMENT_ID',
                'document_number': null,
                'evidence_uri': 'ref-1',
                'verification_status': 'PENDING',
                'expires_at': null,
                'created_at': '2026-09-04T00:00:00Z',
                'updated_at': '2026-09-04T00:00:00Z',
                'verification_case_id': 'case-1',
              }),
              201,
            );
          }
          if (request.url.path == '/api/v1/drivers/me/documents') {
            return http.Response(_envelope({'documents': []}), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/vehicles') {
            return http.Response(_envelope({'vehicles': []}), 200);
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Document reference (optional)'),
      'ref-1',
    );
    await tester.tap(find.text('Submit Document'));
    await tester.pumpAndSettle();

    expect(submittedBody?['document_type'], 'GOVERNMENT_ID');
    expect(submittedBody?['evidence_uri'], 'ref-1');
  });

  testWidgets(
    'tapping Camera uploads the photo and fills the reference field',
    (tester) async {
      Map<String, dynamic>? submittedBody;
      // Shared between ApiClient and EvidenceUploadService below — the
      // multipart upload POST (straight to the presigned `upload_url`,
      // not through ApiClient) must hit this same mock, not a real
      // network client, or the test would attempt a real HTTP call.
      final mockHttpClient = MockClient((request) async {
        if (request.method == 'GET' && request.url.path == '/api/v1/drivers/me') {
          return http.Response(_envelope(_profileJson()), 200);
        }
        if (request.method == 'POST' &&
            request.url.path == '/api/v1/drivers/me/uploads') {
          return http.Response(
            _envelope({
              'upload_url': 'https://s3.example.com/bucket',
              'upload_fields': {'key': 'driver-uploads/x.jpg'},
              'uri': 's3://bucket/driver-uploads/x.jpg',
              'expires_at': '2026-09-04T01:00:00Z',
            }),
            200,
          );
        }
        if (request.url.toString() == 'https://s3.example.com/bucket') {
          return http.Response('', 200);
        }
        if (request.method == 'POST' &&
            request.url.path == '/api/v1/drivers/me/documents') {
          submittedBody = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            _envelope({
              'document_id': 'doc-1',
              'document_type': 'GOVERNMENT_ID',
              'document_number': null,
              'evidence_uri': 's3://bucket/driver-uploads/x.jpg',
              'verification_status': 'PENDING',
              'expires_at': null,
              'created_at': '2026-09-04T00:00:00Z',
              'updated_at': '2026-09-04T00:00:00Z',
              'verification_case_id': null,
            }),
            201,
          );
        }
        if (request.url.path == '/api/v1/drivers/me/documents') {
          return http.Response(_envelope({'documents': []}), 200);
        }
        if (request.url.path == '/api/v1/drivers/me/vehicles') {
          return http.Response(_envelope({'vehicles': []}), 200);
        }
        return http.Response('unexpected', 404);
      });
      await tester.pumpWidget(
        _wrap(
          mockHttpClient,
          uploads: EvidenceUploadService(
            pickImage: ({required source}) async => XFile('fake/x.jpg'),
            // Avoids real dart:io file I/O — flutter_test's fake-async
            // pump loop can't drive it (see EvidenceUploadService's own
            // doc comment on `_readFile`); the real default is covered
            // directly by evidence_upload_service_test.dart instead.
            readFile: (field, path) async =>
                http.MultipartFile.fromBytes(field, [1, 2, 3], filename: 'x.jpg'),
            httpClient: mockHttpClient,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Camera'));
      await tester.pumpAndSettle();

      expect(
        (tester.widget(
                  find.widgetWithText(TextField, 'Document reference (optional)'),
                )
                as TextField)
            .controller
            ?.text,
        's3://bucket/driver-uploads/x.jpg',
      );

      await tester.tap(find.text('Submit Document'));
      await tester.pumpAndSettle();

      expect(submittedBody?['evidence_uri'], 's3://bucket/driver-uploads/x.jpg');
    },
  );

  testWidgets('registering a vehicle posts the chosen category/cab tier/registration', (
    tester,
  ) async {
    Map<String, dynamic>? submittedBody;
    var vehicleRegistered = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'GET' && request.url.path == '/api/v1/drivers/me') {
            return http.Response(_envelope(_profileJson()), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/documents') {
            return http.Response(_envelope({'documents': []}), 200);
          }
          if (request.method == 'POST' &&
              request.url.path == '/api/v1/drivers/me/vehicles') {
            submittedBody = jsonDecode(request.body) as Map<String, dynamic>;
            vehicleRegistered = true;
            return http.Response(_envelope(_vehicleJson()), 201);
          }
          if (request.method == 'GET' &&
              request.url.path == '/api/v1/drivers/me/vehicles') {
            return http.Response(
              _envelope({
                'vehicles': vehicleRegistered ? [_vehicleJson()] : <dynamic>[],
              }),
              200,
            );
          }
          if (request.url.path.endsWith('/documents')) {
            return http.Response(_envelope({'documents': []}), 200);
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(
      find.widgetWithText(TextField, 'Registration number'),
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Registration number'),
      'BR01AB1234',
    );
    await tester.ensureVisible(find.text('Register Vehicle'));
    await tester.tap(find.text('Register Vehicle'));
    await tester.pumpAndSettle();

    expect(submittedBody?['category'], 'CAB');
    expect(submittedBody?['cab_tier'], 'ECO');
    expect(submittedBody?['registration_number'], 'BR01AB1234');
    // Reloaded state now shows the registered vehicle instead of the form.
    expect(find.text('Register Your Vehicle'), findsNothing);
    expect(find.textContaining('BR01AB1234'), findsOneWidget);
  });

  testWidgets('an approved-but-inactive vehicle offers Activate Vehicle', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'GET' && request.url.path == '/api/v1/drivers/me') {
            return http.Response(
              _envelope(_profileJson(verificationStatus: 'APPROVED')),
              200,
            );
          }
          if (request.url.path == '/api/v1/drivers/me/documents' ||
              request.url.path.endsWith('/documents')) {
            return http.Response(_envelope({'documents': []}), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/vehicles') {
            return http.Response(
              _envelope({
                'vehicles': [_vehicleJson(verificationStatus: 'APPROVED')],
              }),
              200,
            );
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Activate Vehicle'), findsOneWidget);
  });

  testWidgets('a load failure (once a profile exists) shows the error banner', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'GET' && request.url.path == '/api/v1/drivers/me') {
            return http.Response(_envelope(_profileJson()), 200);
          }
          return http.Response(
            _errorEnvelope('UNKNOWN_ERROR', 'Something went wrong.'),
            500,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong.'), findsOneWidget);
  });
}
