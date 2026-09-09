// Widget tests for BookRideScreen (build order step 4 —
// docs/16-mobile/mobile-app-implementation-plan.md §4.1): field
// validation, the cab-tier field's conditional visibility, and
// create-ride success/error handling.
//
// The backend is mocked via `http`'s own `MockClient` (same convention
// as every other API-backed screen in this app).
//
// Updated 2026-09-08 (Phase 4 of the redesign, "User home + booking"):
// the vehicle category and cab tier pickers moved from a
// `DropdownButtonFormField` to a tappable `ChoiceChip` row — tests that
// exercised the old dropdown now tap the chip directly. Sectioning the
// form into cards (VistaarCard) also pushed several toggles below the
// default 800x600 test viewport, so taps on them now call
// `tester.ensureVisible(...)` first, the same pattern this file's own
// "Request Ride" taps already used before this change.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/ride_api.dart';
import 'package:vistaar_mobile/core/contacts/contacts_api.dart';
import 'package:vistaar_mobile/features/rides/book_ride_screen.dart';
import 'package:vistaar_mobile/features/rides/ride_status_screen.dart';
import 'package:vistaar_mobile/shared/widgets/route_map_preview.dart';

/// A successful submission pushes [RideStatusScreen], which starts its
/// own periodic poll `Timer` — cancelled only by `dispose()` or a
/// terminal ride status (neither happens here, the mock always returns
/// SEARCHING), so it stays pending unless something unmounts the tree
/// before the test ends.
Future<void> _disposeScreen(WidgetTester tester) =>
    tester.pumpWidget(const SizedBox());

/// Denies permission by default — every test that doesn't specifically
/// exercise the Contacts-picker flow gets a harmless no-op, same
/// "fake wired to no-ops by default" convention every other injected
/// dependency in this app's tests already follows. `ContactsApi`'s own
/// Contact-to-PickedContact extraction logic is covered directly in
/// test/core/contacts/contacts_api_test.dart — these widget tests only
/// need to prove BookRideScreen wires that class correctly.
Widget _wrap(http.Client mockHttpClient, {ContactsApi? contactsApi}) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<RideApi>(create: (_) => RideApi(apiClient, () => 'user-token')),
      Provider<ContactsApi>(
        create: (_) =>
            contactsApi ??
            ContactsApi(requestPermission: () async => PermissionStatus.denied),
      ),
    ],
    child: const MaterialApp(home: BookRideScreen()),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Future<void> _fillCoordinates(WidgetTester tester) async {
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Latitude').first,
    '25.5941',
  );
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Longitude').first,
    '85.1376',
  );
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Latitude').last,
    '25.6120',
  );
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Longitude').last,
    '85.1580',
  );
}

/// Scrolls [text] into view, then taps it — every toggle/button below
/// the Pickup/Destination/Vehicle cards needs this now that the form is
/// sectioned into cards tall enough to push them past the default test
/// viewport (unrelated to any real device, which simply scrolls).
Future<void> _tapText(WidgetTester tester, String text) async {
  final finder = find.text(text);
  await tester.ensureVisible(finder);
  await tester.tap(finder);
}

void main() {
  testWidgets('the cab tier field only appears when Cab is selected', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(MockClient((_) async => http.Response('unused', 500))),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Cab tier'), findsNothing);

    // Vehicle category is now a bottom-sheet picker (Rapido-benchmarked
    // redesign, 2026-09-08): open it via the summary row, then pick
    // "Cab" from the sheet.
    await _tapText(tester, 'Bike');
    await tester.pumpAndSettle();
    await _tapText(tester, 'Cab');
    await tester.pumpAndSettle();

    expect(find.textContaining('Cab tier'), findsOneWidget);
  });

  testWidgets('picking Auto from the vehicle sheet updates the summary row', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(MockClient((_) async => http.Response('unused', 500))),
    );
    await tester.pumpAndSettle();

    await _tapText(tester, 'Bike');
    await tester.pumpAndSettle();
    await _tapText(tester, 'Auto');
    await tester.pumpAndSettle();

    expect(find.text('Auto'), findsOneWidget);
    expect(find.text('Bike'), findsNothing);
  });

  testWidgets(
    'a live route preview appears once pickup and destination are both valid',
    (tester) async {
      await tester.pumpWidget(
        _wrap(MockClient((_) async => http.Response('unused', 500))),
      );
      await tester.pumpAndSettle();

      expect(find.byType(RouteMapPreview), findsNothing);

      await _fillCoordinates(tester);
      await tester.pumpAndSettle();

      expect(find.byType(RouteMapPreview), findsOneWidget);
    },
  );

  testWidgets(
    'no "Pick on Map" button when no maps key is configured for this build '
    '(2026-09-07) — the manual coordinate fields stay the only input',
    (tester) async {
      await tester.pumpWidget(
        _wrap(MockClient((_) async => http.Response('unused', 500))),
      );
      await tester.pumpAndSettle();

      // AppConfig.mapTilerApiKey is a compile-time constant that's
      // always empty in a plain `flutter test` run (no --dart-define)
      // — see route_map_preview_test.dart's own header for why. This
      // proves the button is genuinely gated, not just untriggered.
      expect(find.text('Pick on Map'), findsNothing);
      expect(find.widgetWithText(TextFormField, 'Latitude'), findsNWidgets(2));
      expect(find.widgetWithText(TextFormField, 'Longitude'), findsNWidgets(2));
    },
  );

  testWidgets('leaving a coordinate empty blocks submission', (tester) async {
    var createCalled = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((_) async {
          createCalled = true;
          return http.Response('unused', 500);
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Request Ride'));
    await tester.tap(find.text('Request Ride'));
    await tester.pumpAndSettle();

    expect(createCalled, isFalse);
    expect(find.text('Enter a number'), findsWidgets);
  });

  testWidgets(
    'a valid submission creates the ride and opens RideStatusScreen',
    (tester) async {
      String? capturedIdempotencyKey;
      Map<String, dynamic>? capturedBody;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides') {
              capturedIdempotencyKey = request.headers['Idempotency-Key'];
              capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
              return http.Response(
                _envelope({
                  'ride_id': 'ride-1',
                  'status': 'SEARCHING',
                  'fare': {
                    'base': 89.25,
                    'discount': 0,
                    'total': 89.25,
                    'currency': 'INR',
                  },
                }),
                201,
              );
            }
            if (request.url.path == '/api/v1/rides/ride-1') {
              return http.Response(
                _envelope({
                  'ride_id': 'ride-1',
                  'status': 'SEARCHING',
                  'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
                  'destination': {'latitude': 25.6120, 'longitude': 85.1580},
                  'driver': null,
                  'vehicle': null,
                  'fare': null,
                }),
                200,
              );
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await _fillCoordinates(tester);
      await tester.ensureVisible(find.text('Request Ride'));
      await tester.tap(find.text('Request Ride'));
      // Not pumpAndSettle(): the pushed RideStatusScreen ends up showing
      // SEARCHING's perpetual spinner, which never lets the tree settle.
      // Explicit pumps: process the tap -> let createRide's mocked
      // Future resolve and the push happen -> finish the push transition
      // (300ms) and let RideStatusScreen's own initial fetch resolve.
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump();

      expect(capturedIdempotencyKey, isNotNull);
      expect(capturedIdempotencyKey, isNotEmpty);
      expect(capturedBody?['vehicle_category'], 'BIKE');
      expect(capturedBody, isNot(contains('cab_tier')));
      // No payment-method selection anywhere in the app (owner decision,
      // 2026-09-03) — the request body must never carry one.
      expect(capturedBody, isNot(contains('payment_method')));
      expect(find.byType(RideStatusScreen), findsOneWidget);
    },
  );

  testWidgets(
    'an outstanding penalty shows a dialog before opening RideStatusScreen '
    '(ADR-0026)',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides') {
              return http.Response(
                _envelope({
                  'ride_id': 'ride-1',
                  'status': 'SEARCHING',
                  'fare': {
                    'base': 89.25,
                    'discount': 0,
                    'total': 89.25,
                    'currency': 'INR',
                  },
                  'outstanding_penalty': {'amount': 15.0, 'currency': 'INR'},
                  'total_payable': {
                    'ride_fare': 89.25,
                    'outstanding_penalty': 15.0,
                    'total': 104.25,
                    'currency': 'INR',
                  },
                }),
                201,
              );
            }
            if (request.url.path == '/api/v1/rides/ride-1') {
              return http.Response(
                _envelope({
                  'ride_id': 'ride-1',
                  'status': 'SEARCHING',
                  'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
                  'destination': {'latitude': 25.6120, 'longitude': 85.1580},
                  'driver': null,
                  'vehicle': null,
                  'fare': null,
                }),
                200,
              );
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();

      await _fillCoordinates(tester);
      await tester.ensureVisible(find.text('Request Ride'));
      await tester.tap(find.text('Request Ride'));
      await tester.pump();
      await tester.pump();

      // The dialog appears, and RideStatusScreen has NOT been pushed
      // yet — booking isn't blocked, but the dialog is shown first.
      expect(find.text('Outstanding balance'), findsOneWidget);
      expect(find.textContaining('₹15.00'), findsOneWidget);
      expect(find.byType(RideStatusScreen), findsNothing);

      await tester.tap(find.text('OK'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump();

      expect(find.text('Outstanding balance'), findsNothing);
      expect(find.byType(RideStatusScreen), findsOneWidget);
    },
  );

  testWidgets(
    'a failed create-ride surfaces the backend error and stays open',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient(
            (_) async => http.Response(
              _errorEnvelope('VALIDATION_FAILED', 'Invalid coordinates.'),
              422,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _fillCoordinates(tester);
      await tester.ensureVisible(find.text('Request Ride'));
      await tester.tap(find.text('Request Ride'));
      await tester.pumpAndSettle();

      expect(find.text('Invalid coordinates.'), findsOneWidget);
      expect(find.byType(BookRideScreen), findsOneWidget);
    },
  );

  // --- Schedule a Ride & Book for Someone Else (build order step 10,
  // ADR-0057) ---------------------------------------------------------

  testWidgets(
    'enabling Schedule for later without picking a time blocks submission',
    (tester) async {
      var createCalled = false;
      await tester.pumpWidget(
        _wrap(
          MockClient((_) async {
            createCalled = true;
            return http.Response('unused', 500);
          }),
        ),
      );
      await tester.pumpAndSettle();
      await _fillCoordinates(tester);

      await _tapText(tester, 'Schedule for later');
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Request Ride'));
      await tester.tap(find.text('Request Ride'));
      await tester.pumpAndSettle();

      expect(createCalled, isFalse);
      expect(find.text('Pick a date and time for the ride.'), findsOneWidget);
    },
  );

  testWidgets('scheduling a ride sends scheduled_for in the request body', (
    tester,
  ) async {
    Map<String, dynamic>? capturedBody;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/rides') {
            capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              _envelope({
                'ride_id': 'ride-1',
                'status': 'SCHEDULED',
                'fare': {
                  'base': 89.25,
                  'discount': 0,
                  'total': 89.25,
                  'currency': 'INR',
                },
              }),
              201,
            );
          }
          return http.Response(
            _envelope({
              'ride_id': 'ride-1',
              'status': 'SCHEDULED',
              'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
              'destination': {'latitude': 25.6120, 'longitude': 85.1580},
              'driver': null,
              'vehicle': null,
              'fare': null,
            }),
            200,
          );
        }),
      ),
    );
    addTearDown(() => _disposeScreen(tester));
    await tester.pumpAndSettle();
    await _fillCoordinates(tester);

    await _tapText(tester, 'Schedule for later');
    await tester.pumpAndSettle();
    await _tapText(tester, 'Pick date & time');
    await tester.pumpAndSettle();
    // The date picker's default selection is already the initial
    // date (now + 2h) — confirming immediately is enough to exercise
    // the full pick flow without needing to select a specific day.
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    // Same for the time picker that follows.
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();

    expect(find.text('Change date & time'), findsOneWidget);

    await tester.ensureVisible(find.text('Request Ride'));
    await tester.tap(find.text('Request Ride'));
    await tester.pump();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump();

    expect(capturedBody?['scheduled_for'], isNotNull);
  });

  testWidgets(
    'booking for someone else without a name or phone blocks submission',
    (tester) async {
      var createCalled = false;
      await tester.pumpWidget(
        _wrap(
          MockClient((_) async {
            createCalled = true;
            return http.Response('unused', 500);
          }),
        ),
      );
      await tester.pumpAndSettle();
      await _fillCoordinates(tester);

      await _tapText(tester, 'Book for someone else');
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Request Ride'));
      await tester.tap(find.text('Request Ride'));
      await tester.pumpAndSettle();

      expect(createCalled, isFalse);
      expect(find.text('Enter a name'), findsOneWidget);
      expect(find.text('Enter a phone number'), findsOneWidget);
    },
  );

  testWidgets(
    'booking for someone else sends linked_contact in the request body',
    (tester) async {
      Map<String, dynamic>? capturedBody;
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/rides') {
              capturedBody = jsonDecode(request.body) as Map<String, dynamic>;
              return http.Response(
                _envelope({
                  'ride_id': 'ride-1',
                  'status': 'SEARCHING',
                  'fare': {
                    'base': 89.25,
                    'discount': 0,
                    'total': 89.25,
                    'currency': 'INR',
                  },
                }),
                201,
              );
            }
            return http.Response(
              _envelope({
                'ride_id': 'ride-1',
                'status': 'SEARCHING',
                'pickup': {'latitude': 25.5941, 'longitude': 85.1376},
                'destination': {'latitude': 25.6120, 'longitude': 85.1580},
                'driver': null,
                'vehicle': null,
                'fare': null,
              }),
              200,
            );
          }),
        ),
      );
      addTearDown(() => _disposeScreen(tester));
      await tester.pumpAndSettle();
      await _fillCoordinates(tester);

      await _tapText(tester, 'Book for someone else');
      await tester.pumpAndSettle();
      await tester.enterText(
        find.widgetWithText(TextFormField, "Rider's name"),
        'Priya Singh',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, "Rider's phone"),
        '9999999999',
      );
      await tester.ensureVisible(find.text('Request Ride'));
      await tester.tap(find.text('Request Ride'));
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump();

      expect(capturedBody?['linked_contact'], {
        'name': 'Priya Singh',
        'phone': '9999999999',
      });
    },
  );

  testWidgets(
    'startForSomeoneElse pre-selects Book for someone else (Home tab quick '
    'action)',
    (tester) async {
      final apiClient = ApiClient(
        httpClient: MockClient((_) async => http.Response('unused', 500)),
      );
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            Provider<RideApi>(
              create: (_) => RideApi(apiClient, () => 'user-token'),
            ),
            Provider<ContactsApi>(
              create: (_) => ContactsApi(
                requestPermission: () async => PermissionStatus.denied,
              ),
            ),
          ],
          child: const MaterialApp(
            home: BookRideScreen(startForSomeoneElse: true),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text("Rider's name"));
      expect(find.text("Rider's name"), findsOneWidget);
      expect(find.text("Rider's phone"), findsOneWidget);
    },
  );

  testWidgets(
    '"Choose from Contacts" only appears once Book for someone else is on',
    (tester) async {
      await tester.pumpWidget(_wrap(MockClient((_) async => http.Response('unused', 500))));
      await tester.pumpAndSettle();

      expect(find.text('Choose from Contacts'), findsNothing);

      await _tapText(tester, 'Book for someone else');
      await tester.pumpAndSettle();

      expect(find.text('Choose from Contacts'), findsOneWidget);
    },
  );

  testWidgets(
    'a denied permission shows a message and leaves the fields untouched',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((_) async => http.Response('unused', 500)),
          contactsApi: ContactsApi(
            requestPermission: () async => PermissionStatus.denied,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await _tapText(tester, 'Book for someone else');
      await tester.pumpAndSettle();

      await _tapText(tester, 'Choose from Contacts');
      await tester.pumpAndSettle();

      expect(
        find.text(
          "Contacts permission denied — enter the rider's details "
          'manually below.',
        ),
        findsOneWidget,
      );
      expect(
        tester
            .widget<TextFormField>(
              find.widgetWithText(TextFormField, "Rider's name"),
            )
            .controller
            ?.text,
        '',
      );
    },
  );

  testWidgets(
    'a granted permission and a picked contact fill in the name and phone fields',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((_) async => http.Response('unused', 500)),
          contactsApi: ContactsApi(
            requestPermission: () async => PermissionStatus.granted,
            showPicker: () async => const Contact(
              displayName: 'Priya Singh',
              phones: [Phone(number: '9999999999')],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await _tapText(tester, 'Book for someone else');
      await tester.pumpAndSettle();

      await _tapText(tester, 'Choose from Contacts');
      await tester.pumpAndSettle();

      expect(find.text('Priya Singh'), findsOneWidget);
      expect(find.text('9999999999'), findsOneWidget);
    },
  );

  testWidgets(
    'a cancelled picker leaves the manual fields empty, no crash',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((_) async => http.Response('unused', 500)),
          contactsApi: ContactsApi(
            requestPermission: () async => PermissionStatus.granted,
            showPicker: () async => null,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await _tapText(tester, 'Book for someone else');
      await tester.pumpAndSettle();

      await _tapText(tester, 'Choose from Contacts');
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<TextFormField>(
              find.widgetWithText(TextFormField, "Rider's name"),
            )
            .controller
            ?.text,
        '',
      );
    },
  );
}
