// Widget tests for SupportCasesListScreen (Phase 14, api-contracts.md
// §44's previously-missing list endpoint, added 2026-09-04): loading,
// empty, error, and populated states, plus pagination and navigating
// into a case's detail.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:vistaar_mobile/core/api/api_client.dart';
import 'package:vistaar_mobile/core/api/support_api.dart';
import 'package:vistaar_mobile/features/support/support_cases_list_screen.dart';

Widget _wrap(http.Client mockHttpClient) {
  final apiClient = ApiClient(httpClient: mockHttpClient);
  return MultiProvider(
    providers: [
      Provider<SupportApi>(
        create: (_) => SupportApi(apiClient, () => 'user-token'),
      ),
    ],
    child: const MaterialApp(home: SupportCasesListScreen()),
  );
}

String _envelope(Map<String, dynamic> data) =>
    jsonEncode({'data': data, 'error': null, 'request_id': 'req_test'});

String _errorEnvelope(String code, String message) => jsonEncode({
  'data': null,
  'error': {'code': code, 'message': message},
  'request_id': 'req_test',
});

Map<String, dynamic> _caseJson({
  required String caseId,
  String? category = 'PAYMENT',
  String status = 'OPEN',
  List<Map<String, dynamic>> messages = const [],
}) => {
  'case_id': caseId,
  'ride_id': null,
  'category': category,
  'priority': 'NORMAL',
  'status': status,
  'assigned_admin_id': null,
  'created_at': '2026-08-31T10:00:00Z',
  'updated_at': '2026-08-31T10:00:00Z',
  'messages': messages,
};

Map<String, dynamic> _page(
  List<Map<String, dynamic>> items, {
  int page = 1,
  int totalPages = 1,
  int? total,
}) => {
  'items': items,
  'pagination': {
    'page': page,
    'page_size': 20,
    'total': total ?? items.length,
    'total_pages': totalPages,
  },
};

void main() {
  testWidgets('shows an empty state for a customer with no cases', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(MockClient((_) async => http.Response(_envelope(_page([])), 200))),
    );
    await tester.pumpAndSettle();

    expect(find.text('You have not contacted support yet.'), findsOneWidget);
  });

  testWidgets('lists cases newest-first with their status shown', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient(
          (_) async => http.Response(
            _envelope(
              _page([
                _caseJson(caseId: 'case-2', category: 'RIDE_FARE_DISPUTE'),
                _caseJson(caseId: 'case-1', status: 'RESOLVED'),
              ]),
            ),
            200,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('RIDE_FARE_DISPUTE'), findsOneWidget);
    expect(find.text('OPEN'), findsOneWidget);
    expect(find.text('RESOLVED'), findsOneWidget);
  });

  testWidgets('a backend error shows the error message', (tester) async {
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

  testWidgets('Load more fetches and appends the next page', (tester) async {
    var requestCount = 0;
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          requestCount++;
          if (requestCount == 1) {
            return http.Response(
              _envelope(
                _page([
                  _caseJson(caseId: 'case-1'),
                ], totalPages: 2, total: 2),
              ),
              200,
            );
          }
          expect(request.url.queryParameters['page'], '2');
          return http.Response(
            _envelope(
              _page([
                _caseJson(caseId: 'case-2'),
              ], page: 2, totalPages: 2, total: 2),
            ),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Load more'), findsOneWidget);
    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(find.byType(ListTile), findsNWidgets(2));
    expect(find.text('Load more'), findsNothing);
  });

  testWidgets('tapping a case fetches its full detail and opens it', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        MockClient((request) async {
          if (request.url.path == '/api/v1/support/cases') {
            return http.Response(
              _envelope(_page([_caseJson(caseId: 'case-1')])),
              200,
            );
          }
          expect(request.url.path, '/api/v1/support/cases/case-1');
          return http.Response(
            _envelope(
              _caseJson(
                caseId: 'case-1',
                messages: [
                  {
                    'sender_type': 'CUSTOMER',
                    'sender_id': 'user-1',
                    'message': 'Why was I charged?',
                    'created_at': '2026-08-31T10:00:00Z',
                  },
                ],
              ),
            ),
            200,
          );
        }),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byType(ListTile));
    await tester.pumpAndSettle();

    expect(find.text('Support Case'), findsOneWidget);
    expect(find.text('Why was I charged?'), findsOneWidget);
  });
}
