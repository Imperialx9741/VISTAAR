import 'package:flutter/material.dart';

import '../../shared/design/vistaar_nav_shell.dart';
import '../profile/sarthi_account_hub_screen.dart';
import '../rides/ride_history_screen.dart';
import '../wallet/wallet_screen.dart';
import 'sarthi_home_tab.dart';

/// Landing screen for the Sarthi (driver) role. Rebuilt 2026-09-08
/// (Phase 3 of the owner-requested UI/UX redesign, navigation shell) as
/// a [VistaarNavShell] hosting four tabs, per the Phase 1 audit's
/// proposed navigation: Home ([SarthiHomeTab], Go Online/Offline and
/// offer handling — still the first thing a Sarthi sees, unchanged),
/// Wallet ([WalletScreen], reused as-is — the ₹20 minimum-balance and
/// outstanding-debt-recovered-on-next-recharge rules live entirely in
/// that unchanged screen and its API layer, not touched here), Activity
/// ([RideHistoryScreen], the same screen and endpoint the User role's
/// Activity tab uses — no separate screen invented), and Account
/// ([SarthiAccountHubScreen] — Onboarding, My Strikes, Support, Sign
/// out, previously five separate AppBar icons). Every destination
/// screen is one that already existed before this change; this file
/// only reorganizes how they're reached.
class SarthiHomeScreen extends StatelessWidget {
  const SarthiHomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const VistaarNavShell(
      destinations: [
        VistaarNavDestination(
          label: 'Home',
          icon: Icons.home_outlined,
          selectedIcon: Icons.home,
          screen: SarthiHomeTab(),
        ),
        VistaarNavDestination(
          label: 'Wallet',
          icon: Icons.account_balance_wallet_outlined,
          selectedIcon: Icons.account_balance_wallet,
          screen: WalletScreen(),
        ),
        VistaarNavDestination(
          label: 'Activity',
          icon: Icons.receipt_long_outlined,
          selectedIcon: Icons.receipt_long,
          screen: RideHistoryScreen(),
        ),
        VistaarNavDestination(
          label: 'Account',
          icon: Icons.person_outline,
          selectedIcon: Icons.person,
          screen: SarthiAccountHubScreen(),
        ),
      ],
    );
  }
}
