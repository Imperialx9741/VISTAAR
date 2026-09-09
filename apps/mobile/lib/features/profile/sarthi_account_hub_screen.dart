import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/notifications/push_notification_manager.dart';
import '../../shared/design/vistaar_card.dart';
import '../../shared/design/vistaar_spacing.dart';
import '../auth/auth_session.dart';
import '../auth/role_selection_screen.dart';
import '../onboarding/sarthi_onboarding_screen.dart';
import '../penalty/strike_history_screen.dart';
import '../support/contact_support_screen.dart';
import '../support/support_cases_list_screen.dart';

/// The Sarthi role's Account tab (Phase 3 of the redesign, navigation
/// shell, 2026-09-08) — the single home for everything
/// [SarthiHomeScreen] used to carry as AppBar action icons (Onboarding,
/// My Strikes, Support, Sign out; Wallet gets its own dedicated tab
/// instead — see [SarthiHomeScreen]), per the Phase 1 audit's proposed
/// navigation. Every destination screen and the sign-out flow itself
/// are unchanged; this is purely a menu.
class SarthiAccountHubScreen extends StatelessWidget {
  const SarthiAccountHubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Account'),
        actions: [
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => _signOut(context),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(VistaarSpacing.md),
        children: [
          VistaarCard(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const SarthiOnboardingScreen(),
              ),
            ),
            child: const _HubRow(
              icon: Icons.assignment_turned_in_outlined,
              title: 'Sarthi Onboarding',
            ),
          ),
          const SizedBox(height: VistaarSpacing.sm),
          VistaarCard(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const StrikeHistoryScreen(),
              ),
            ),
            child: const _HubRow(
              icon: Icons.warning_amber_outlined,
              title: 'My Strikes',
            ),
          ),
          const SizedBox(height: VistaarSpacing.sm),
          VistaarCard(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const SupportCasesListScreen(),
              ),
            ),
            child: const _HubRow(
              icon: Icons.list_alt_outlined,
              title: 'My Support Cases',
            ),
          ),
          const SizedBox(height: VistaarSpacing.sm),
          VistaarCard(
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const ContactSupportScreen(),
              ),
            ),
            child: const _HubRow(
              icon: Icons.support_agent_outlined,
              title: 'Contact Support',
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _signOut(BuildContext context) async {
    // Unregister this device *before* signing out — same reasoning as
    // AccountHubScreen's own _signOut(): PushNotificationManager still
    // needs a valid access token for the DELETE call, which
    // AuthSession.signOut() below is about to clear.
    await context.read<PushNotificationManager>().stop();
    if (!context.mounted) return;
    context.read<AuthSession>().signOut();
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const RoleSelectionScreen()),
      (route) => false,
    );
  }
}

class _HubRow extends StatelessWidget {
  const _HubRow({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Icon(icon, color: theme.colorScheme.primary),
        const SizedBox(width: VistaarSpacing.md),
        Expanded(child: Text(title, style: theme.textTheme.titleMedium)),
        Icon(Icons.chevron_right, color: theme.colorScheme.onSurfaceVariant),
      ],
    );
  }
}
