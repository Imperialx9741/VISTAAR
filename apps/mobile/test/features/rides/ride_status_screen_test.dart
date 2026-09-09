// Widget tests for RideStatusScreen (build order steps 4 and 8 —
// docs/16-mobile/mobile-app-implementation-plan.md §4.2, §4.9): status
// display, driver/vehicle/fare once present, the ARRIVED-only OTP
// reveal, and (step 8) SOS + the Contact Support link.
//
// The backend is mocked via `http`'s own `MockClient`; the device
// position via a [FakeGeolocatorPlatform] (geolocator's own documented
// testing seam) — same convention as ride_execution_screen_test.dart.

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
import 'package:vistaar_mobile/features/rides/ride_status_screen.dart';
import 'package:vistaar_mobile/shared/widgets/route_map_preview.dart';

/// Only overrides [getCurrentPosition] — the one call this screen's SOS
/// action makes.
class FakeGeolocatorPlatform extends GeolocatorPlatform {
  @override
  Future<Position> getCurrentPosition({
    LocationSettings? locationSettings,
  }) async {
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

/// [RideStatusScreen] starts a periodic poll [Timer] that only stops on
/// a terminal ride status or `dispose()` — several tests below never
/// reach a terminal status, so without this the widget-test framework
/// would fail them for a "Timer still pending" at teardown. Pumping an
/// unrelated widget unmounts the screen, triggering `dispose()`.
Future<void> _disposeScreen(WidgetTester tester) =>
    tester.pumpWidget(const SizedBox());

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<RideApi>(create: (_) => RideApi(apiClient, () => 'user-token')),
      Provider<SafetyApi>(
        create: (_) => SafetyApi(apiClient, () => 'user-token'),
      ),
      Provider<SupportApi>(
        create: (_) => SupportApi(apiClient, () => 'user-token'),
      ),
    ],
    child: const MaterialApp(home: RideStatusScreen(rideId: 'ride-1')),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Map<String, dynamic> _rideJson({
  required String status,
  Map<String, dynamic>? driver,
  Map<String, dynamic>? vehicle,
  Map<String, dynamic>? fare,
  String? scheduledFor,
}) => {
  'ride_id': 'ride-1',
  'status': status,
  'scheduled_for': scheduledFor,
  'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
  'destination': {'latitude': 25.6120, 'longitude': 85.1580},
  'driver': driver,
  'vehicle': vehicle,
  'fare': fare,
};

void main() {
  setUp(() {
    GeolocatorPlatform.instance = FakeGeolocatorPlatform();
  });

  testWidgets('shows a spinner while SEARCHING, no driver/vehicle/OTP', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async =>
              http.Response(_envelope(_rideJson(status: 'SEARCHING')), 200),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    // Not pumpAndSettle(): SEARCHING's own spinner is a perpetual
    // animation that never lets the tree settle. Two pumps are enough
    // for the mocked (delay-free) fetch to resolve and rebuild.
    await tester.pump();
    await tester.pump();

    expect(find.text('Looking for a driver…'), findsOneWidget);
    expect(find.text('Show pickup code'), findsNothing);
  });

  testWidgets(
    'shows a RouteMapPreview for the ride\'s pickup/destination '
    '(2026-09-07) — degrading to its own fallback without a maps key '
    'configured for this build, same as route_map_preview_test.dart',
    (tester) async {
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

      expect(find.byType(RouteMapPreview), findsOneWidget);
    },
  );

  testWidgets('shows driver, vehicle, and fare once ACCEPTED', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _envelope(
              _rideJson(
                status: 'ACCEPTED',
                driver: {
                  'driver_id': 'driver-1',
                  'full_name': 'Ravi Kumar',
                  'profile_photo_uri': null,
                },
                vehicle: {
                  'vehicle_id': 'vehicle-1',
                  'category': 'CAB',
                  'registration_number': 'BR-01-AB-1234',
                  'make': 'Maruti',
                  'model': 'Dzire',
                },
                fare: {
                  'base': 89.25,
                  'discount': 0,
                  'total': 89.25,
                  'currency': 'INR',
                },
              ),
            ),
            200,
          ),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    expect(find.text('Driver is on the way'), findsOneWidget);
    expect(find.text('Ravi Kumar'), findsOneWidget);
    expect(find.textContaining('Maruti Dzire'), findsOneWidget);
    expect(find.textContaining('89.25'), findsOneWidget);
    // Not ARRIVED yet — OTP is not offered.
    expect(find.text('Show pickup code'), findsNothing);
  });

  testWidgets('ARRIVED offers Show pickup code, which reveals the OTP', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/otp/refresh') {
            return http.Response(_envelope({'otp': '654321'}), 200);
          }
          return http.Response(_envelope(_rideJson(status: 'ARRIVED')), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    expect(find.text('Show pickup code'), findsOneWidget);

    await tester.tap(find.text('Show pickup code'));
    await tester.pumpAndSettle();

    expect(find.text('Pickup code: 654321'), findsOneWidget);
  });

  testWidgets(
    'a failed OTP reveal (ride not yet ARRIVED) surfaces the backend error',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/otp/refresh') {
              return http.Response(
                _errorEnvelope(
                  'RIDE_NOT_IN_EXPECTED_STATE',
                  'This ride is not ARRIVED.',
                ),
                409,
              );
            }
            return http.Response(_envelope(_rideJson(status: 'ARRIVED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Show pickup code'));
      await tester.pumpAndSettle();

      expect(find.text('This ride is not ARRIVED.'), findsOneWidget);
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

  testWidgets(
    'ACCEPTED offers Cancel Ride; confirming with no charge shows that',
    (tester) async {
      var status = 'ACCEPTED';
      Map<String, dynamic>? capturedBody;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/cancel') {
              capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
              status = 'CANCELLED';
              return http.Response(
                _envelope({
                  'ride_status': 'CANCELLED',
                  'charge': {
                    'amount': 0,
                    'currency': 'INR',
                    'expires_at': null,
                    'penalty_id': null,
                  },
                }),
                200,
              );
            }
            return http.Response(_envelope(_rideJson(status: status)), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      expect(find.text('Cancel Ride'), findsOneWidget);
      await tester.tap(find.text('Cancel Ride'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'Change of plans');
      await tester.tap(find.text('Confirm Cancellation'));
      await tester.pumpAndSettle();

      expect(capturedBody?['reason'], 'Change of plans');
      expect(find.text('No cancellation charge.'), findsOneWidget);
      expect(find.text('Ride cancelled'), findsOneWidget);
    },
  );

  testWidgets('an ACCEPTED cancellation with a charge shows the amount', (
    tester,
  ) async {
    var status = 'ACCEPTED';
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/cancel') {
            status = 'CANCELLED';
            return http.Response(
              _envelope({
                'ride_status': 'CANCELLED',
                'charge': {
                  'amount': 15,
                  'currency': 'INR',
                  'expires_at': '2026-09-30T00:00:00Z',
                  'penalty_id': 'penalty-1',
                },
              }),
              200,
            );
          }
          return http.Response(_envelope(_rideJson(status: status)), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Cancel Ride'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Driver too far');
    await tester.tap(find.text('Confirm Cancellation'));
    await tester.pumpAndSettle();

    expect(find.text('Cancellation charge: INR 15.00'), findsOneWidget);
  });

  testWidgets(
    'dismissing the cancel dialog without a reason does not call the backend',
    (tester) async {
      var cancelCalled = false;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/cancel') {
              cancelCalled = true;
            }
            return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Cancel Ride'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Back'));
      await tester.pumpAndSettle();

      expect(cancelCalled, isFalse);
      expect(find.text('Cancel Ride'), findsOneWidget);
    },
  );

  testWidgets('STARTED does not offer Cancel Ride', (tester) async {
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

    expect(find.text('Cancel Ride'), findsNothing);
  });

  testWidgets('a failed cancellation surfaces the backend error', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/cancel') {
            return http.Response(
              _errorEnvelope(
                'RIDE_NOT_CANCELLABLE',
                'This ride is not in a cancellable state.',
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

    await tester.tap(find.text('Cancel Ride'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Change of plans');
    await tester.tap(find.text('Confirm Cancellation'));
    await tester.pumpAndSettle();

    expect(
      find.text('This ride is not in a cancellable state.'),
      findsOneWidget,
    );
  });

  testWidgets('ACCEPTED offers Change Pickup', (tester) async {
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

    expect(find.text('Change Pickup'), findsOneWidget);
  });

  testWidgets('STARTED does not offer Change Pickup', (tester) async {
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

    expect(find.text('Change Pickup'), findsNothing);
  });

  testWidgets(
    'Change Pickup submits the entered coordinates and shows a confirmation',
    (tester) async {
      Map<String, dynamic>? capturedBody;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/pickup-change') {
              capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
              return http.Response(
                _envelope({'applied': true, 'distance_meters': 42.0}),
                200,
              );
            }
            return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Change Pickup'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'New latitude'),
        '25.6000',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New longitude'),
        '85.1400',
      );
      await tester.tap(find.text('Change Pickup').last);
      await tester.pumpAndSettle();

      expect(capturedBody?['latitude'], 25.6);
      expect(capturedBody?['longitude'], 85.14);
      expect(find.text('Pickup updated.'), findsOneWidget);
    },
  );

  testWidgets(
    'a pickup change beyond the threshold surfaces the backend rejection',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/pickup-change') {
              return http.Response(
                _errorEnvelope(
                  'PICKUP_CHANGE_TOO_FAR',
                  'This pickup is too far from your current one. Cancel '
                      'this ride and book a new one to change it by this '
                      'much.',
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

      await tester.tap(find.text('Change Pickup'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New latitude'),
        '25.7000',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New longitude'),
        '85.3000',
      );
      await tester.tap(find.text('Change Pickup').last);
      await tester.pumpAndSettle();

      expect(
        find.text(
          'This pickup is too far from your current one. Cancel this '
          'ride and book a new one to change it by this much.',
        ),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'dismissing the change-pickup dialog without submitting does not call the backend',
    (tester) async {
      var changeCalled = false;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/pickup-change') {
              changeCalled = true;
            }
            return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Change Pickup'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Back'));
      await tester.pumpAndSettle();

      expect(changeCalled, isFalse);
      expect(find.text('Change Pickup'), findsOneWidget);
    },
  );

  testWidgets('STARTED offers Change Destination; ACCEPTED does not', (
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

    expect(find.text('Change Destination'), findsOneWidget);
  });

  testWidgets('ACCEPTED does not offer Change Destination', (tester) async {
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

    expect(find.text('Change Destination'), findsNothing);
  });

  testWidgets(
    'a WITHIN_ROUTE destination change applies immediately, no confirm call',
    (tester) async {
      var confirmCalled = false;
      Map<String, dynamic>? capturedBody;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/destination-change') {
              capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
              return http.Response(
                _envelope({'applied': true, 'case': 'WITHIN_ROUTE'}),
                200,
              );
            }
            if (request.url.path ==
                '/api/v1/rides/ride-1/destination-change/confirm') {
              confirmCalled = true;
            }
            return http.Response(_envelope(_rideJson(status: 'STARTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Change Destination'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New latitude'),
        '25.6050',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New longitude'),
        '85.1450',
      );
      await tester.tap(find.text('Change Destination').last);
      await tester.pumpAndSettle();

      expect(capturedBody?['latitude'], 25.605);
      expect(capturedBody?['longitude'], 85.145);
      expect(confirmCalled, isFalse);
      expect(find.text('Destination updated.'), findsOneWidget);
    },
  );

  testWidgets(
    'a fare-changing destination case is rejected automatically and explained',
    (tester) async {
      bool? capturedConfirmedValue;
      String? capturedChangeRequestId;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/destination-change') {
              return http.Response(
                _envelope({
                  'applied': false,
                  'case': 'BEYOND_ORIGINAL',
                  'change_request_id': 'change-1',
                  'status': 'AWAITING_CUSTOMER_CONFIRMATION',
                  'requested_at': '2026-08-31T10:00:00Z',
                }),
                201,
              );
            }
            if (request.url.path ==
                '/api/v1/rides/ride-1/destination-change/confirm') {
              final body = jsonDecode(request.body) as Map<String, dynamic>;
              capturedConfirmedValue = body['confirmed'] as bool?;
              capturedChangeRequestId = body['change_request_id'] as String?;
              return http.Response(
                _envelope({'status': 'REJECTED', 'ride_status': 'STARTED'}),
                200,
              );
            }
            return http.Response(_envelope(_rideJson(status: 'STARTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Change Destination'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New latitude'),
        '25.7000',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New longitude'),
        '85.3000',
      );
      await tester.tap(find.text('Change Destination').last);
      await tester.pumpAndSettle();

      expect(capturedChangeRequestId, 'change-1');
      expect(capturedConfirmedValue, isFalse);
      expect(find.textContaining('needs a fare adjustment'), findsOneWidget);
    },
  );

  testWidgets(
    'dismissing the change-destination dialog without submitting does not call the backend',
    (tester) async {
      var changeCalled = false;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/destination-change') {
              changeCalled = true;
            }
            return http.Response(_envelope(_rideJson(status: 'STARTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Change Destination'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Back'));
      await tester.pumpAndSettle();

      expect(changeCalled, isFalse);
      expect(find.text('Change Destination'), findsOneWidget);
    },
  );

  testWidgets(
    'a failed destination-change request surfaces the backend error',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/destination-change') {
              return http.Response(
                _errorEnvelope(
                  'DESTINATION_CHANGE_ALREADY_REQUESTED',
                  'A destination change request is already pending for this ride.',
                ),
                409,
              );
            }
            return http.Response(_envelope(_rideJson(status: 'STARTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Change Destination'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New latitude'),
        '25.6050',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'New longitude'),
        '85.1450',
      );
      await tester.tap(find.text('Change Destination').last);
      await tester.pumpAndSettle();

      expect(
        find.text(
          'A destination change request is already pending for this ride.',
        ),
        findsOneWidget,
      );
    },
  );

  testWidgets('SOS is offered while ACCEPTED', (tester) async {
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
          return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('SOS'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Accident'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Trigger SOS'));
    await tester.pumpAndSettle();

    expect(capturedBody?['incident_type'], 'ACCIDENT');
    expect(capturedBody?['latitude'], 25.5941);
    expect(capturedBody?['longitude'], 85.1376);
    expect(
      find.text("VISTAAR's safety team has been notified."),
      findsOneWidget,
    );
  });

  testWidgets(
    'dismissing the SOS dialog without choosing a reason does not call the backend',
    (tester) async {
      var sosCalled = false;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/sos') {
              sosCalled = true;
            }
            return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('SOS'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(sosCalled, isFalse);
    },
  );

  testWidgets('a failed SOS trigger surfaces the backend error', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides/ride-1/sos') {
            return http.Response(
              _errorEnvelope('RIDE_NOT_FOUND', 'Ride not found.'),
              404,
            );
          }
          return http.Response(_envelope(_rideJson(status: 'ACCEPTED')), 200);
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('SOS'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Medical emergency'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Trigger SOS'));
    await tester.pumpAndSettle();

    expect(find.text('Ride not found.'), findsOneWidget);
  });

  testWidgets('Contact Support opens the pre-filled contact screen', (
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

    await tester.tap(find.text('Contact Support'));
    await tester.pumpAndSettle();

    expect(find.text('About ride ride-1'), findsOneWidget);
  });

  // --- Schedule a Ride (build order step 10, ADR-0057) --------------------

  testWidgets('SCHEDULED shows the scheduled time and offers Cancel Ride', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _envelope(
              _rideJson(
                status: 'SCHEDULED',
                scheduledFor: '2026-09-01T14:00:00Z',
              ),
            ),
            200,
          ),
        ),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();

    expect(find.text('Ride scheduled'), findsOneWidget);
    expect(find.textContaining('2026-09-01'), findsOneWidget);
    expect(find.text('Cancel Ride'), findsOneWidget);
  });

  testWidgets(
    'cancelling a SCHEDULED ride shows the charge the backend returns',
    (tester) async {
      var status = 'SCHEDULED';
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/cancel') {
              status = 'CANCELLED';
              return http.Response(
                _envelope({
                  'ride_status': 'CANCELLED',
                  'charge': {
                    'amount': 30,
                    'currency': 'INR',
                    'expires_at': '2026-09-30T00:00:00Z',
                    'penalty_id': 'penalty-1',
                  },
                }),
                200,
              );
            }
            return http.Response(
              _envelope(
                _rideJson(status: status, scheduledFor: '2026-09-01T14:00:00Z'),
              ),
              200,
            );
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Cancel Ride'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Change of plans');
      await tester.tap(find.text('Confirm Cancellation'));
      await tester.pumpAndSettle();

      expect(find.text('Cancellation charge: INR 30.00'), findsOneWidget);
    },
  );

  testWidgets(
    'an open GPS dispute shows a banner that opens GpsDisputeScreen',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides/ride-1/gps-disputes') {
              return http.Response(
                _envelope({
                  'disputes': [
                    {
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
                    },
                  ],
                }),
                200,
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
            return http.Response(_envelope(_rideJson(status: 'ARRIVED')), 200);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      expect(
        find.text('A GPS dispute is open on this ride — evidence needed.'),
        findsOneWidget,
      );

      await tester.tap(find.text('View'));
      await tester.pumpAndSettle();

      expect(find.byType(GpsDisputeScreen), findsOneWidget);
    },
  );
}
