// Widget tests for WalletScreen (build order step 7 —
// docs/16-mobile/mobile-app-implementation-plan.md §5.5): balance
// display, the transaction ledger, and pagination.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/wallet_api.dart';
import 'package:vistaar_mobile/features/wallet/recharge_wallet_screen.dart';
import 'package:vistaar_mobile/features/wallet/wallet_screen.dart';

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<WalletApi>(
        create: (_) => WalletApi(apiClient, () => 'sarthi-token'),
      ),
    ],
    child: const MaterialApp(home: WalletScreen()),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Map<String, dynamic> _walletJson({
  double balance = 250.0,
  double outstandingDebt = 0,
}) => {
  'balance': balance,
  'currency': 'INR',
  'outstanding_settlement': 0,
  'outstanding_debt': outstandingDebt,
};

Map<String, dynamic> _transactionJson({
  String id = 'txn-1',
  String type = 'PLATFORM_FEE',
  String direction = 'DEBIT',
  double amount = 12.5,
}) => {
  'transaction_id': id,
  'ride_id': 'ride-1',
  'transaction_type': type,
  'amount': amount,
  'direction': direction,
  'balance_before': 262.5,
  'balance_after': 250.0,
  'reference_type': 'ride',
  'reference_id': 'ride-1',
  'created_at': '2026-08-31T10:00:00Z',
};

Map<String, dynamic> _pageJson({
  required List<Map<String, dynamic>> items,
  int page = 1,
  int totalPages = 1,
}) => {
  'items': items,
  'pagination': {
    'page': page,
    'page_size': 20,
    'total': items.length,
    'total_pages': totalPages,
  },
};

void main() {
  testWidgets('shows the balance and the transaction list', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(_envelope(_walletJson(balance: 250.0)), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/wallet/transactions') {
            return http.Response(
              _envelope(_pageJson(items: [_transactionJson()])),
              200,
            );
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('INR 250.00'), findsOneWidget);
    expect(find.text('Platform Fee'), findsOneWidget);
    expect(find.text('−12.50'), findsOneWidget);
  });

  testWidgets('no transactions shows an empty state', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(_envelope(_walletJson()), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/wallet/transactions') {
            return http.Response(_envelope(_pageJson(items: [])), 200);
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No transactions yet.'), findsOneWidget);
  });

  testWidgets('Load more fetches and appends the next page', (tester) async {
    final requestedPages = <String>[];
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(_envelope(_walletJson()), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/wallet/transactions') {
            final page = request.url.queryParameters['page'] ?? '1';
            requestedPages.add(page);
            if (page == '1') {
              return http.Response(
                _envelope(
                  _pageJson(
                    items: [_transactionJson(id: 'txn-1')],
                    page: 1,
                    totalPages: 2,
                  ),
                ),
                200,
              );
            }
            return http.Response(
              _envelope(
                _pageJson(
                  items: [
                    _transactionJson(
                      id: 'txn-2',
                      type: 'DRIVER_PENALTY',
                      direction: 'DEBIT',
                      amount: 30.0,
                    ),
                  ],
                  page: 2,
                  totalPages: 2,
                ),
              ),
              200,
            );
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Load more'), findsOneWidget);
    expect(find.text('Driver Penalty'), findsNothing);

    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(requestedPages, containsAllInOrder(['1', '2']));
    expect(find.text('Driver Penalty'), findsOneWidget);
    expect(find.text('Load more'), findsNothing);
  });

  testWidgets('a failed initial load surfaces the backend error', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _errorEnvelope('AUTH_REQUIRED', 'Not signed in.'),
            401,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Not signed in.'), findsOneWidget);
  });

  testWidgets(
    'Recharge Wallet opens RechargeWalletScreen (api-contracts.md §35, '
    'ADR-0060)',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/drivers/me/wallet') {
              return http.Response(_envelope(_walletJson()), 200);
            }
            if (request.url.path == '/api/v1/drivers/me/wallet/transactions') {
              return http.Response(_envelope(_pageJson(items: [])), 200);
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Recharge Wallet'));
      await tester.pumpAndSettle();

      expect(find.byType(RechargeWalletScreen), findsOneWidget);
    },
  );

  testWidgets('a positive credit transaction shows a plus sign', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(_envelope(_walletJson()), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/wallet/transactions') {
            return http.Response(
              _envelope(
                _pageJson(
                  items: [
                    _transactionJson(
                      type: 'JOINING_BONUS',
                      direction: 'CREDIT',
                      amount: 100.0,
                    ),
                  ],
                ),
              ),
              200,
            );
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Joining Bonus'), findsOneWidget);
    expect(find.text('+100.00'), findsOneWidget);
  });

  testWidgets(
    'an outstanding cancellation-penalty debt is shown (ADR-0062)',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          MockClient((request) async {
            if (request.url.path == '/api/v1/drivers/me/wallet') {
              return http.Response(
                _envelope(_walletJson(outstandingDebt: 30.0)),
                200,
              );
            }
            if (request.url.path == '/api/v1/drivers/me/wallet/transactions') {
              return http.Response(_envelope(_pageJson(items: [])), 200);
            }
            return http.Response('unexpected', 404);
          }),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Unpaid cancellation penalty'), findsOneWidget);
      expect(find.textContaining('30.00'), findsOneWidget);
    },
  );

  testWidgets('no outstanding debt shows no penalty warning', (tester) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/drivers/me/wallet') {
            return http.Response(_envelope(_walletJson()), 200);
          }
          if (request.url.path == '/api/v1/drivers/me/wallet/transactions') {
            return http.Response(_envelope(_pageJson(items: [])), 200);
          }
          return http.Response('unexpected', 404);
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Unpaid cancellation penalty'), findsNothing);
  });
}
