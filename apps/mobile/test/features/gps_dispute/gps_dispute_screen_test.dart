// Widget tests for GpsDisputeScreen (shared by both roles, built
// 2026-09-04, ADR-0032/ADR-0074 — see that screen's own doc comment for
// why this exists): status display, evidence list, and submitting
// text/reference evidence, each driven against a real MockClient
// standing in for the backend.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/core/uploads/evidence_upload_service.dart';
import 'package:vistaar_mobile/features/gps_dispute/gps_dispute_screen.dart';

Widget _wrap(http.Client mockHttpClient, {EvidenceUploadService? uploads}) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<RideApi>(create: (_) => RideApi(apiClient, () => 'token')),
      // A picker that always cancels (returns null) unless a test
      // supplies its own — every existing test below never taps
      // Camera/Gallery, so this default is never exercised by them.
      Provider<EvidenceUploadService>(
        create: (_) =>
            uploads ?? EvidenceUploadService(pickImage: ({required source}) async => null),
      ),
    ],
    child: const MaterialApp(
      home: GpsDisputeScreen(rideId: 'ride-1', disputeId: 'dispute-1'),
    ),
  );
}

String _envelope(Object? data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

Map<String, dynamic> _disputeJson({
  String status = 'OPEN',
  String? decision,
  String? decidedReason,
  List<Map<String, dynamic>> evidence = const [],
}) => {
  'dispute_id': 'dispute-1',
  'ride_id': 'ride-1',
  'gps_verification_id': 'verification-1',
  'verification_type': 'ARRIVAL',
  'opened_at': '2026-09-04T10:00:00Z',
  'evidence_deadline': '2026-09-05T10:00:00Z',
  'status': status,
  'decision': decision,
  'decided_by': decision == null ? null : 'admin-1',
  'decided_reason': decidedReason,
  'decided_at': decision == null ? null : '2026-09-05T00:00:00Z',
  'evidence': evidence,
};

void main() {
  testWidgets('shows the dispute status and an empty evidence state', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((_) async => http.Response(_envelope(_disputeJson()), 200)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Status: OPEN'), findsOneWidget);
    expect(find.text('No evidence submitted yet.'), findsOneWidget);
    expect(find.text('Submit Evidence'), findsOneWidget);
  });

  testWidgets('shows previously submitted evidence', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _envelope(
              _disputeJson(
                evidence: [
                  {
                    'submitted_by': 'driver-1',
                    'evidence_type': 'TEXT',
                    'uri': null,
                    'text_explanation': 'I was at the correct gate.',
                    'submitted_at': '2026-09-04T11:00:00Z',
                  },
                ],
              ),
            ),
            200,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('TEXT'), findsOneWidget);
    expect(find.text('I was at the correct gate.'), findsOneWidget);
  });

  testWidgets('a RESOLVED dispute shows the decision and no evidence form', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _envelope(
              _disputeJson(
                status: 'RESOLVED',
                decision: 'APPROVE',
                decidedReason: 'GPS was genuinely inaccurate indoors.',
              ),
            ),
            200,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Decision: APPROVE'), findsOneWidget);
    expect(
      find.text('GPS was genuinely inaccurate indoors.'),
      findsOneWidget,
    );
    expect(find.text('Submit Evidence'), findsNothing);
  });

  testWidgets('submitting TEXT evidence posts text, not uri', (tester) async {
    Map<String, dynamic>? submittedBody;
    var submitted = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'POST') {
            submittedBody = jsonDecode(request.body) as Map<String, dynamic>;
            submitted = true;
            return http.Response(
              _envelope({
                'submitted_by': 'customer-1',
                'evidence_type': 'TEXT',
                'uri': null,
                'text_explanation': 'Explanation here.',
                'submitted_at': '2026-09-04T11:00:00Z',
              }),
              201,
            );
          }
          return http.Response(
            _envelope(
              _disputeJson(
                evidence: submitted
                    ? [
                        {
                          'submitted_by': 'customer-1',
                          'evidence_type': 'TEXT',
                          'uri': null,
                          'text_explanation': 'Explanation here.',
                          'submitted_at': '2026-09-04T11:00:00Z',
                        },
                      ]
                    : <Map<String, dynamic>>[],
              ),
            ),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextField, 'Explanation'),
      'Explanation here.',
    );
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();

    expect(submittedBody?['evidence_type'], 'TEXT');
    expect(submittedBody?['text'], 'Explanation here.');
    expect(submittedBody?['uri'], null);
  });

  testWidgets('submitting PHOTO evidence posts the reference as uri', (
    tester,
  ) async {
    Map<String, dynamic>? submittedBody;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.method == 'POST') {
            submittedBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              _envelope({
                'submitted_by': 'driver-1',
                'evidence_type': 'PHOTO',
                'uri': 'ref-123',
                'text_explanation': null,
                'submitted_at': '2026-09-04T11:00:00Z',
              }),
              201,
            );
          }
          return http.Response(_envelope(_disputeJson()), 200);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Text explanation'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Photo').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Evidence reference'),
      'ref-123',
    );
    await tester.tap(find.text('Submit'));
    await tester.pumpAndSettle();

    expect(submittedBody?['evidence_type'], 'PHOTO');
    expect(submittedBody?['uri'], 'ref-123');
    expect(submittedBody?['text'], null);
  });

  testWidgets(
    'tapping Camera for PHOTO uploads and fills the reference field',
    (tester) async {
      final mockHttpClient = MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/evidence/upload-url')) {
          return http.Response(
            _envelope({
              'upload_url': 'https://s3.example.com/bucket',
              'upload_fields': {'key': 'gps-dispute-evidence/x.jpg'},
              'uri': 's3://bucket/gps-dispute-evidence/x.jpg',
              'expires_at': '2026-09-04T01:00:00Z',
            }),
            200,
          );
        }
        if (request.url.toString() == 'https://s3.example.com/bucket') {
          return http.Response('', 200);
        }
        return http.Response(_envelope(_disputeJson()), 200);
      });
      await tester.pumpWidget(
        _wrap(
          mockHttpClient,
          uploads: EvidenceUploadService(
            pickImage: ({required source}) async => XFile('fake/x.jpg'),
            readFile: (field, path) async =>
                http.MultipartFile.fromBytes(field, [1, 2, 3], filename: 'x.jpg'),
            httpClient: mockHttpClient,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Text explanation'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Photo').last);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Camera'));
      await tester.pumpAndSettle();

      expect(
        (tester.widget(
                  find.widgetWithText(TextField, 'Evidence reference'),
                )
                as TextField)
            .controller
            ?.text,
        's3://bucket/gps-dispute-evidence/x.jpg',
      );
    },
  );

  testWidgets('a load failure shows the error message', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            jsonEncode({
              'data': null,
              'error': {'code': 'RIDE_NOT_FOUND', 'message': 'Ride not found.'},
              'request_id': 'req_test',
            }),
            404,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ride not found.'), findsOneWidget);
  });
}
