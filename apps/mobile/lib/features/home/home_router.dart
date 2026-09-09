import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/notifications/push_notification_manager.dart';
import '../auth/app_role.dart';
import '../auth/auth_session.dart';
import 'sarthi_home_screen.dart';
import 'user_home_screen.dart';

/// Lands here immediately after a successful OTP verify, or after
/// [SessionBootstrapper] restores a still-valid saved session on cold
/// start — the one place both paths converge, regardless of role
/// (ADR-0027: one app, two roles, not two apps). Shows the
/// role-appropriate home screen based on [AuthSession.role].
///
/// Also (ADR-0052, build order step 11): starts push-notification
/// registration here — [PushNotificationManager.start] — since this is
/// the single point every "now authenticated" path passes through,
/// unlike either home screen individually (a live login skips
/// `SessionBootstrapper` entirely via `Navigator.pushAndRemoveUntil`,
/// so a per-home-screen `initState` would miss a restored-session cold
/// start reaching the *other* role's screen and vice versa — this
/// widget is reached by both).
class HomeRouter extends StatefulWidget {
  const HomeRouter({super.key});

  @override
  State<HomeRouter> createState() => _HomeRouterState();
}

class _HomeRouterState extends State<HomeRouter> {
  @override
  void initState() {
    super.initState();
    unawaited(context.read<PushNotificationManager>().start());
  }

  @override
  Widget build(BuildContext context) {
    final role = context.watch<AuthSession>().role;
    return switch (role) {
      AppRole.user => const UserHomeScreen(),
      AppRole.sarthi => const SarthiHomeScreen(),
      null => const _NotSignedIn(),
    };
  }
}

/// Defensive fallback — should be unreachable, since nothing navigates to
/// [HomeRouter] without first calling [AuthSession.signIn].
class _NotSignedIn extends StatelessWidget {
  const _NotSignedIn();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(body: Center(child: Text('Not signed in.')));
  }
}
