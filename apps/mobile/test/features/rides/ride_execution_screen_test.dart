// Widget tests for RideExecutionScreen (build order step 5 —
// docs/16-mobile/mobile-app-implementation-plan.md §5.4): Mark Arrived,
// Start Ride (OTP entry), and Complete Ride, across the ACCEPTED ->
// ARRIVED -> STARTED -> CLOSED lifecycle.
//
// The backend is mocked via `http`'s own `MockClient`; the device
// position via a [FakeGeolocatorPlatform] (geolocator's own documented
// testing seam) — same conventions as sarthi_home_screen_test.dart.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geolocator_platform_interface/geolocator_platform_interface.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/core/api/safety_api.dart';
import 'package:vistaar_mobile/core/api/support_api.dart';
import 'package:vistaar_mobile/features/gps_dispute/gps_dispute_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_execution_screen.dart';
import 'package:vistaar_mobile/shared/widgets/route_map_preview.dart';

/// Only overrides [getCurrentPosition] — the one call this screen
/// actually makes (Mark Arrived, Complete Ride).
class FakeGeolocatorPlatform extends GeolocatorPlatform {
  int callCount = 0;

  @override
  Future<Position> getCurrentPosition({
    LocationSettings? locationSettings,
  }) async {
    callCount++;
    return Position(
      latitude: 25.5941,
      longitude: 85.1376,
      timestamp: DateTime.now(),
      accuracy: 8,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: 0,
      headingAccuracy: 0,
      speed: 0,
      speedAccuracy: 0,
    );
  }
}

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<RideApi>(
        create: (_) => RideApi(apiClient, () => 'sarthi-token'),
      ),
      Provider<SafetyApi>(
        create: (_) => SafetyApi(apiClient, () => 'sarthi-token'),
      ),
      Provider<SupportApi>(
        create: (_) => SupportApi(apiClient, () => 'sarthi-token'),
      ),
    ],
    child: const MaterialApp(home: RideExecutionScreen(rideId: 'ride-1')),
  );
}

/// The poll [Timer] this screen starts only stops on a terminal status
/// or `dispose()` — several tests below never reach CLOSED/CANCELLED,
/// so without this the widget-test framework fails them for a "Timer
/// still pending" at teardown.
Future<void> _disposeScreen(WidgetTester tester) =>
    tester.pumpWidget(const SizedBox());

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

String _errorEnvelopeWithDetails(
  String code,
  String message,
  Map<String, dynamic> details,
) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message, 'details': details},
  'request_id': 'req_test',
});

Map<String, dynamic> _rideJson({
  required String status,
  Map<String, dynamic>? fare,
}) => {
  'ride_id': 'ride-1',
  'status': status,
  'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
  'destination': {'latitude': 25.6120, 'longitude': 85.1580},
  'driver': null,
  'vehicle': null,
  'fare': fare,
};

void main() {
  setUp(() {
    GeolocatorPlatform.instance = FakeGeolocatorPlatform();
  });

  testWidgets('ACCEPTED shows Head to pickup and a Mark Arrived button', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async =>
              http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    // A RouteMapPreview for the ride's pickup/destination (2026-09-07)
    // — degrading to its own fallback without a maps key configured
    // for this build, same as route_map_preview_test.dart.
    expect(find.byType(RouteMapPreview), findsOneWidget);
    expect(find.text('Head to pickup'), findsOneWidget);
    expect(find.text('Mark Arrived'), findsOneWidget);
    expect(find.text('Cancel'), findsOneWidget);
  });

  testWidgets(
    'a terminal GPS failure on Mark Arrived opens GpsDisputeScreen',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/arrived') {
              return http.Response(
                _errorEnvelopeWithDetails(
                  'GPS_VERIFICATION_FAILED',
                  'GPS verification failed too many times.',
                  {'dispute_id': 'dispute-1'},
                ),
                409,
              );
            }
            if (request.url.path == '/api/v1/rides/ride-1/gps-disputes/dispute-1') {
              return http.Response(
                _envelope({
                  'dispute_id': 'dispute-1',
                  'ride_id': 'ride-1',
                  'gps_verification_id': 'verification-1',
                  'verification_type': 'ARRIVAL',
                  'opened_at': '2026-09-04T10:00:00Z',
                  'evidence_deadline': '2026-09-05T10:00:00Z',
                  'status': 'OPEN',
                  'decision': null,
                  'decided_by': null,
                  'decided_reason': null,
                  'decided_at': null,
                  'evidence': <dynamic>[],
                }),
                200,
              );
            }
            return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Mark Arrived'));
      await tester.pumpAndSettle();

      expect(find.byType(GpsDisputeScreen), findsOneWidget);
    },
  );

  testWidgets(
    'Cancel on ACCEPTED sends the entered reason and re-fetches to CANCELLED',
    (tester) async {
      var status = 'ACCEPTED';
      Map<String, dynamic>? capturedBody;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/driver-cancel') {
              capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
              status = 'CANCELLED';
              return http.Response(
                _envelope({'ride_status': 'CANCELLED'}),
                200,
              );
            }
            return http.Response(_envelope(_rideJson(status: status)), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Vehicle broke down');
      await tester.tap(find.text('Confirm Cancellation'));
      await tester.pumpAndSettle();

      expect(capturedBody?['reason'], 'Vehicle broke down');
      expect(find.text('Ride cancelled'), findsOneWidget);
      expect(find.text('Done'), findsOneWidget);
    },
  );

  testWidgets(
    'dismissing the cancel dialog without a reason does not call the backend',
    (tester) async {
      var cancelCalled = false;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/driver-cancel') {
              cancelCalled = true;
            }
            return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Back'));
      await tester.pumpAndSettle();

      expect(cancelCalled, isFalse);
      expect(find.text('Cancel'), findsOneWidget);
    },
  );

  testWidgets('a failed driver-cancel surfaces the backend error', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/driver-cancel') {
            return http.Response(
              _errorEnvelope(
                'INSUFFICIENT_WALLET_BALANCE',
                'Your wallet balance is too low to cancel.',
              ),
              422,
            );
          }
          return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Vehicle broke down');
    await tester.tap(find.text('Confirm Cancellation'));
    await tester.pumpAndSettle();

    expect(
      find.text('Your wallet balance is too low to cancel.'),
      findsOneWidget,
    );
  });

  testWidgets(
    'ARRIVED does not offer Cancel (driver-cancel is ACCEPTED-only)',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient(
            (_) async =>
                http.Response(_envelope(_rideJson(status: 'ARRIVED')), 200),
          ),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      expect(find.text('Cancel'), findsNothing);
    },
  );

  testWidgets(
    'Mark Arrived sends the device position and re-fetches to ARRIVED',
    (tester) async {
      var status = 'ACCEPTED';
      final fakeGeo = FakeGeolocatorPlatform();
      GeolocatorPlatform.instance = fakeGeo;
      Map<String, dynamic>? capturedArriveBody;

      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/arrived') {
              capturedArriveBody =
                  jsonDecode(request.body) as Map<String, dynamic>;
              status = 'ARRIVED';
              return http.Response(
                _envelope({'status': 'ARRIVED', 'waiting_started_at': null}),
                200,
              );
            }
            return http.Response(_envelope(_rideJson(status: status)), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Mark Arrived'));
      await tester.pumpAndSettle();

      expect(fakeGeo.callCount, greaterThanOrEqualTo(1));
      expect(capturedArriveBody?['latitude'], 25.5941);
      expect(capturedArriveBody?['longitude'], 85.1376);
      expect(find.text('Waiting for the customer'), findsOneWidget);
      expect(find.text('Start Ride'), findsOneWidget);
    },
  );

  testWidgets(
    'a GPS-radius failure on Mark Arrived surfaces the error and stays ACCEPTED',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/arrived') {
              return http.Response(
                _errorEnvelope(
                  'NOT_WITHIN_PICKUP_RADIUS',
                  'You are too far from the pickup point.',
                ),
                409,
              );
            }
            return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Mark Arrived'));
      await tester.pumpAndSettle();

      expect(
        find.text('You are too far from the pickup point.'),
        findsOneWidget,
      );
      expect(find.text('Head to pickup'), findsOneWidget);
    },
  );

  testWidgets('leaving the OTP field empty blocks Start Ride locally', (
    tester,
  ) async {
    var startCalled = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/start') {
            startCalled = true;
          }
          return http.Response(_envelope(_rideJson(status: 'ARRIVED')), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Start Ride'));
    await tester.pumpAndSettle();

    expect(startCalled, isFalse);
    expect(find.text('Enter the code the customer gives you.'), findsOneWidget);
  });

  testWidgets('Start Ride submits the entered OTP and re-fetches to STARTED', (
    tester,
  ) async {
    var status = 'ARRIVED';
    String? capturedOtp;

    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/start') {
            capturedOtp =
                (jsonDecode(request.body) as Map<String, dynamic>)['otp']
                    as String?;
            status = 'STARTED';
            return http.Response(_envelope({'status': 'STARTED'}), 200);
          }
          return http.Response(_envelope(_rideJson(status: status)), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), '123456');
    await tester.tap(find.text('Start Ride'));
    await tester.pumpAndSettle();

    expect(capturedOtp, '123456');
    expect(find.text('Ride in progress'), findsOneWidget);
    expect(find.text('Complete Ride'), findsOneWidget);
  });

  testWidgets('a wrong OTP surfaces the backend error and stays ARRIVED', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/start') {
            return http.Response(
              _errorEnvelope('OTP_INVALID', 'That code is not correct.'),
              422,
            );
          }
          return http.Response(_envelope(_rideJson(status: 'ARRIVED')), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), '000000');
    await tester.tap(find.text('Start Ride'));
    await tester.pumpAndSettle();

    expect(find.text('That code is not correct.'), findsOneWidget);
    expect(find.text('Waiting for the customer'), findsOneWidget);
  });

  testWidgets(
    'Complete Ride sends the device position and re-fetches to CLOSED, with a Done button',
    (tester) async {
      var status = 'STARTED';
      final fakeGeo = FakeGeolocatorPlatform();
      GeolocatorPlatform.instance = fakeGeo;

      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => _wrapChild(
                      MockClient((request) async {
                        if (request.url.path ==
                            '/api/v1/rides/ride-1/complete') {
                          status = 'CLOSED';
                          return http.Response(
                            _envelope({'status': 'CLOSED'}),
                            200,
                          );
                        }
                        return http.Response(
                          _envelope(
                            _rideJson(
                              status: status,
                              fare: status == 'CLOSED'
                                  ? {
                                      'base': 89.25,
                                      'discount': 0,
                                      'total': 89.25,
                                      'currency': 'INR',
                                    }
                                  : null,
                            ),
                          ),
                          200,
                        );
                      }),
                    ),
                  ),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Complete Ride'));
      await tester.pumpAndSettle();

      expect(fakeGeo.callCount, greaterThanOrEqualTo(1));
      expect(find.text('Ride completed'), findsOneWidget);
      expect(find.textContaining('89.25'), findsOneWidget);
      expect(find.text('Done'), findsOneWidget);

      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.byType(RideExecutionScreen), findsNothing);
    },
  );

  testWidgets('a load failure surfaces the backend error', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _errorEnvelope('RIDE_NOT_FOUND', 'Ride not found.'),
            404,
          ),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    expect(find.text('Ride not found.'), findsOneWidget);
  });

  // SOS tests below use STARTED rather than ACCEPTED — ACCEPTED's own
  // driver-cancel button is also labeled "Cancel", which would collide
  // with the SOS dialog's "Cancel" button once the dialog is open.

  testWidgets('SOS is offered while STARTED', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async =>
              http.Response(_envelope(_rideJson(status: 'STARTED')), 200),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();
    expect(find.byTooltip('SOS'), findsOneWidget);
  });

  testWidgets('SOS is not offered once CLOSED', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async =>
              http.Response(_envelope(_rideJson(status: 'CLOSED')), 200),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();
    expect(find.byTooltip('SOS'), findsNothing);
  });

  testWidgets('triggering SOS with a chosen reason notifies the caller', (
    tester,
  ) async {
    final fakeGeo = FakeGeolocatorPlatform();
    GeolocatorPlatform.instance = fakeGeo;
    Map<String, dynamic>? capturedBody;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/sos') {
            capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              _envelope({'incident_id': 'incident-1', 'status': 'OPEN'}),
              201,
            );
          }
          return http.Response(_envelope(_rideJson(status: 'STARTED')), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('SOS'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Unsafe situation / harassment'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Trigger SOS'));
    await tester.pumpAndSettle();

    expect(capturedBody?['incident_type'], 'UNSAFE_SITUATION');
    expect(
      find.text("VISTAAR's safety team has been notified."),
      findsOneWidget,
    );
  });

  testWidgets('Contact Support opens the pre-filled contact screen', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async =>
              http.Response(_envelope(_rideJson(status: 'STARTED')), 200),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Contact Support'));
    await tester.pumpAndSettle();

    expect(find.text('About ride ride-1'), findsOneWidget);
  });
}

/// Wraps [RideExecutionScreen] with its [RideApi] provider only (no
/// `MaterialApp`) — used by the one test above that needs a real
/// `Navigator` (to observe the "Done" button's pop) wrapped in its own
/// single `MaterialApp` shell, avoiding a second nested `MaterialApp`
/// inside a pushed route.
Widget _wrapChild(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<RideApi>(
        create: (_) => RideApi(apiClient, () => 'sarthi-token'),
      ),
    ],
    child: const RideExecutionScreen(rideId: 'ride-1'),
  );
}
