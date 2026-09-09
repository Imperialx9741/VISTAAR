// Widget tests for RechargeWalletScreen (api-contracts.md §35,
// ADR-0060). The real `RazorpayCheckout` (`RealRazorpayCheckout`,
// wrapping razorpay_flutter's native plugin) is never exercised here —
// it needs a real Android/iOS device/emulator's platform channel, which
// this test environment has none of (the same limitation this
// codebase's Contacts-picker work already documented for
// `flutter_contacts`). Instead, every test injects `FakeRazorpayCheckout`
// via `RechargeWalletScreen(checkout: ...)` — the constructor-level test
// seam this screen was built with specifically so its own business
// logic (order creation → checkout invocation → confirm → wallet
// balance) is verifiable without the native plugin at all.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/wallet_api.dart';
import 'package:vistaar_mobile/core/payments/razorpay_checkout.dart';
import 'package:vistaar_mobile/features/wallet/recharge_wallet_screen.dart';

class FakeRazorpayCheckout implements RazorpayCheckout {
  final List<({String keyId, String orderId, int amountPaise, String currency})>
  openCalls = [];
  void Function(String orderId, String paymentId, String signature)?
  _successHandler;
  void Function(String message)? _errorHandler;
  bool disposed = false;

  @override
  void open({
    required String keyId,
    required String orderId,
    required int amountPaise,
    required String currency,
    String? description,
  }) {
    openCalls.add((
      keyId: keyId,
      orderId: orderId,
      amountPaise: amountPaise,
      currency: currency,
    ));
  }

  @override
  void onSuccess(
    void Function(String orderId, String paymentId, String signature) handler,
  ) {
    _successHandler = handler;
  }

  @override
  void onError(void Function(String message) handler) {
    _errorHandler = handler;
  }

  @override
  void dispose() => disposed = true;

  void simulateSuccess({
    String orderId = 'order_fake_1',
    String paymentId = 'pay_fake_1',
    String signature = 'sig',
  }) => _successHandler?.call(orderId, paymentId, signature);

  void simulateError(String message) => _errorHandler?.call(message);
}

Widget _wrap(http.Client mockHttpClient, FakeRazorpayCheckout checkout) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<WalletApi>(
        create: (_) => WalletApi(apiClient, () => 'sarthi-token'),
      ),
    ],
    child: MaterialApp(home: RechargeWalletScreen(checkout: checkout)),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

void main() {
  // --- Quick-amount chips (Phase 6 of the redesign, "Sarthi home +
  // wallet", 2026-09-08) -----------------------------------------------

  testWidgets('tapping a quick-amount chip fills the amount field', (
    tester,
  ) async {
    final checkout = FakeRazorpayCheckout();
    await tester.pumpWidget(
      _wrap(MockClient((_) async => http.Response('unused', 500)), checkout),
    );

    await tester.tap(find.text('₹500'));
    await tester.pump();

    expect(
      tester.widget<TextField>(find.byType(TextField)).controller?.text,
      '500',
    );
  });

  testWidgets('an amount below the minimum is rejected locally, no request '
      'sent', (tester) async {
    final checkout = FakeRazorpayCheckout();
    var requested = false;
    await tester.pumpWidget(
      _wrap(
        MockClient((_) async {
          requested = true;
          return http.Response('unused', 500);
        }),
        checkout,
      ),
    );

    await tester.enterText(find.byType(TextField), '100');
    await tester.tap(find.text('Recharge'));
    await tester.pumpAndSettle();

    expect(requested, isFalse);
    expect(checkout.openCalls, isEmpty);
    expect(find.textContaining('at least ₹200'), findsOneWidget);
  });

  testWidgets(
    'a valid amount creates an order and opens the checkout with the '
    'amount in paise',
    (tester) async {
      final checkout = FakeRazorpayCheckout();
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            expect(request.url.path, '/api/v1/drivers/me/wallet/recharge');
            return http.Response(
              _envelope({
                'order_id': 'order_abc',
                'amount': 500.0,
                'currency': 'INR',
                'client_key': 'rzp_test_fake',
              }),
              201,
            );
          }),
          checkout,
        ),
      );

      await tester.enterText(find.byType(TextField), '500');
      await tester.tap(find.text('Recharge'));
      // Not pumpAndSettle(): the screen deliberately stays "busy"
      // (spinning PrimaryButton) once the checkout is open, with no
      // synchronous settle point until a success/error callback fires
      // — see RechargeWalletScreen._startRecharge's own doc comment.
      await tester.pump();
      await tester.pump();

      expect(checkout.openCalls, hasLength(1));
      expect(checkout.openCalls.single.orderId, 'order_abc');
      expect(checkout.openCalls.single.keyId, 'rzp_test_fake');
      expect(checkout.openCalls.single.amountPaise, 50000);
      expect(checkout.openCalls.single.currency, 'INR');
    },
  );

  testWidgets(
    'a gateway error while creating the order is shown and resets the '
    'button',
    (tester) async {
      final checkout = FakeRazorpayCheckout();
      await tester.pumpWidget(
        _wrap(
          MockClient(
            (_) async => http.Response(
              _errorEnvelope(
                'PAYMENT_GATEWAY_ERROR',
                'Could not start the recharge. Please try again.',
              ),
              502,
            ),
          ),
          checkout,
        ),
      );

      await tester.enterText(find.byType(TextField), '500');
      await tester.tap(find.text('Recharge'));
      await tester.pumpAndSettle();

      expect(
        find.text('Could not start the recharge. Please try again.'),
        findsOneWidget,
      );
      expect(checkout.openCalls, isEmpty);
    },
  );

  testWidgets(
    'a successful checkout confirms the payment and pops with the new '
    'wallet balance',
    (tester) async {
      final checkout = FakeRazorpayCheckout();
      final requestedPaths = <String>[];
      double? poppedBalance;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () async {
                  poppedBalance = await Navigator.of(context).push<double>(
                    MaterialPageRoute(
                      builder: (_) => Provider<WalletApi>(
                        create: (_) => WalletApi(
                          ApiClient(
                            httpClient: MockClient((request) async {
                              requestedPaths.add(request.url.path);
                              if (request.url.path.endsWith('/recharge')) {
                                return http.Response(
                                  _envelope({
                                    'order_id': 'order_abc',
                                    'amount': 500.0,
                                    'currency': 'INR',
                                    'client_key': 'rzp_test_fake',
                                  }),
                                  201,
                                );
                              }
                              return http.Response(
                                _envelope({
                                  'status': 'CREDITED',
                                  'wallet_balance': 700.0,
                                }),
                                200,
                              );
                            }),
                          ),
                          () => 'sarthi-token',
                        ),
                        child: RechargeWalletScreen(checkout: checkout),
                      ),
                    ),
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '500');
      await tester.tap(find.text('Recharge'));
      await tester.pump();
      await tester.pump();

      checkout.simulateSuccess();
      await tester.pumpAndSettle();

      expect(
        requestedPaths,
        containsAllInOrder([
          '/api/v1/drivers/me/wallet/recharge',
          '/api/v1/drivers/me/wallet/recharge/confirm',
        ]),
      );
      expect(find.byType(RechargeWalletScreen), findsNothing);
      expect(poppedBalance, 700.0);
    },
  );

  testWidgets(
    'a recharge that recovers an outstanding debt shows a dialog before '
    'popping (ADR-0062)',
    (tester) async {
      final checkout = FakeRazorpayCheckout();
      double? poppedBalance;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: ElevatedButton(
                onPressed: () async {
                  poppedBalance = await Navigator.of(context).push<double>(
                    MaterialPageRoute(
                      builder: (_) => Provider<WalletApi>(
                        create: (_) => WalletApi(
                          ApiClient(
                            httpClient: MockClient((request) async {
                              if (request.url.path.endsWith('/recharge')) {
                                return http.Response(
                                  _envelope({
                                    'order_id': 'order_abc',
                                    'amount': 500.0,
                                    'currency': 'INR',
                                    'client_key': 'rzp_test_fake',
                                  }),
                                  201,
                                );
                              }
                              return http.Response(
                                _envelope({
                                  'status': 'CREDITED',
                                  'wallet_balance': 470.0,
                                  'debt_recovered': 30.0,
                                  'outstanding_debt_remaining': 0.0,
                                }),
                                200,
                              );
                            }),
                          ),
                          () => 'sarthi-token',
                        ),
                        child: RechargeWalletScreen(checkout: checkout),
                      ),
                    ),
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '500');
      await tester.tap(find.text('Recharge'));
      await tester.pump();
      await tester.pump();

      checkout.simulateSuccess();
      // Not pumpAndSettle(): the underlying screen is still "busy"
      // (spinning PrimaryButton) while the dialog sits on top of it —
      // same reason every other post-simulateSuccess() step in this
      // file uses plain pump() instead.
      await tester.pump();
      await tester.pump();

      // The dialog blocks the pop until dismissed.
      expect(find.text('Recharge applied to unpaid penalty'), findsOneWidget);
      expect(find.byType(RechargeWalletScreen), findsOneWidget);
      expect(poppedBalance, isNull);

      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();

      expect(find.byType(RechargeWalletScreen), findsNothing);
      expect(poppedBalance, 470.0);
    },
  );

  testWidgets(
    'a checkout-reported failure is shown and the driver can retry',
    (tester) async {
      final checkout = FakeRazorpayCheckout();
      await tester.pumpWidget(
        _wrap(
          MockClient(
            (_) async => http.Response(
              _envelope({
                'order_id': 'order_abc',
                'amount': 500.0,
                'currency': 'INR',
                'client_key': 'rzp_test_fake',
              }),
              201,
            ),
          ),
          checkout,
        ),
      );

      await tester.enterText(find.byType(TextField), '500');
      await tester.tap(find.text('Recharge'));
      await tester.pump();
      await tester.pump();

      checkout.simulateError('Payment was declined.');
      await tester.pumpAndSettle();

      expect(find.text('Payment was declined.'), findsOneWidget);
      expect(find.byType(RechargeWalletScreen), findsOneWidget);
    },
  );

  testWidgets(
    'an unverified payment on confirm shows the backend error, credits '
    'nothing',
    (tester) async {
      final checkout = FakeRazorpayCheckout();
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path.endsWith('/recharge')) {
              return http.Response(
                _envelope({
                  'order_id': 'order_abc',
                  'amount': 500.0,
                  'currency': 'INR',
                  'client_key': 'rzp_test_fake',
                }),
                201,
              );
            }
            return http.Response(
              _errorEnvelope(
                'PAYMENT_VERIFICATION_FAILED',
                'This payment could not be verified.',
              ),
              402,
            );
          }),
          checkout,
        ),
      );

      await tester.enterText(find.byType(TextField), '500');
      await tester.tap(find.text('Recharge'));
      await tester.pump();
      await tester.pump();

      checkout.simulateSuccess();
      await tester.pumpAndSettle();

      expect(
        find.text('This payment could not be verified.'),
        findsOneWidget,
      );
      expect(find.byType(RechargeWalletScreen), findsOneWidget);
    },
  );

  testWidgets('disposing the screen disposes the checkout', (tester) async {
    final checkout = FakeRazorpayCheckout();
    await tester.pumpWidget(
      _wrap(MockClient((_) async => http.Response('unused', 500)), checkout),
    );
    await tester.pumpWidget(const SizedBox());

    expect(checkout.disposed, isTrue);
  });
}
