import 'package:flutter/material.dart';

import '../../core/api/support_api.dart';

/// Shows one support case and its message thread — reached either right
/// after [ContactSupportScreen] creates it, or by tapping a case in
/// SupportCasesListScreen (added 2026-09-04), both of which pass in an
/// already-freshly-fetched [initialCase] (api-contracts.md §44). There
/// is no pull-to-refresh/live-update here on purpose: posting a
/// follow-up message has no endpoint (`SupportApi`'s own doc comment)
/// and a human admin's reply isn't pushed anywhere this app could poll
/// for it either — reopening the case from the list screen is how a
/// customer/driver checks for an update today.
class SupportCaseScreen extends StatelessWidget {
  const SupportCaseScreen({required this.initialCase, super.key});

  final SupportCase initialCase;

  @override
  Widget build(BuildContext context) {
    final supportCase = initialCase;
    return Scaffold(
      appBar: AppBar(title: const Text('Support Case')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Case ${supportCase.caseId}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Status: ${supportCase.status}',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    if (supportCase.category != null)
                      Text('Category: ${supportCase.category}'),
                    Text('Priority: ${supportCase.priority}'),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'Our support team has your message and will respond '
                'through this process shortly.',
              ),
              const SizedBox(height: 16),
              for (final message in supportCase.messages)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        message.senderType,
                        style: Theme.of(context).textTheme.labelMedium,
                      ),
                      Text(message.message),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
