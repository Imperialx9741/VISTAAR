import 'package:flutter/material.dart';

import '../../shared/design/vistaar_nav_shell.dart';
import '../profile/account_hub_screen.dart';
import '../promotions/offers_hub_screen.dart';
import '../rides/ride_history_screen.dart';
import 'user_home_tab.dart';

/// Landing screen for the User (customer) role. Rebuilt 2026-09-08
/// (Phase 3 of the owner-requested UI/UX redesign, navigation shell) as
/// a [VistaarNavShell] hosting four tabs, per the Phase 1 audit's
/// proposed navigation: Home ([UserHomeTab], the booking entry point —
/// still the first thing a User sees, unchanged), Activity
/// ([RideHistoryScreen], reused as-is — no separate screen invented),
/// Offers ([OffersHubScreen] — Promotions + Referrals, previously two
/// separate AppBar icons), and Account ([AccountHubScreen] — Profile,
/// Scheduled Rides, Support, Sign out, previously five separate AppBar
/// icons). Every destination screen is one that already existed before
/// this change; this file only reorganizes how they're reached.
class UserHomeScreen extends StatelessWidget {
  const UserHomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const VistaarNavShell(
      destinations: [
        VistaarNavDestination(
          label: 'Home',
          icon: Icons.home_outlined,
          selectedIcon: Icons.home,
          screen: UserHomeTab(),
        ),
        VistaarNavDestination(
          label: 'Activity',
          icon: Icons.receipt_long_outlined,
          selectedIcon: Icons.receipt_long,
          screen: RideHistoryScreen(),
        ),
        VistaarNavDestination(
          label: 'Offers',
          icon: Icons.local_offer_outlined,
          selectedIcon: Icons.local_offer,
          screen: OffersHubScreen(),
        ),
        VistaarNavDestination(
          label: 'Account',
          icon: Icons.person_outline,
          selectedIcon: Icons.person,
          screen: AccountHubScreen(),
        ),
      ],
    );
  }
}
