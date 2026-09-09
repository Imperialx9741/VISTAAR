import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../features/auth/auth_session.dart';
import '../../features/auth/role_selection_screen.dart';
import '../../features/home/home_router.dart';
import '../../shared/design/vistaar_logo.dart';

/// The app's real entry widget (set as `MaterialApp.home`). Calls
/// [AuthSession.restore] once, then shows [HomeRouter] if a valid saved
/// session was found, or [RoleSelectionScreen] otherwise. This is the
/// only place that decides "logged in already?" on cold start — every
/// other screen assumes [AuthSession] already reflects the truth.
///
/// The wait for [AuthSession.restore] to finish had no branding at all
/// before this (2026-09-08, Rapido-benchmarked redesign) — a bare
/// spinner on a blank `Scaffold`, the one moment on cold start that had
/// no VISTAAR identity on screen at all. Now shows [VistaarLogoMark]
/// while it waits, closing that gap without changing what this widget
/// actually decides or how long it takes to decide it.
class SessionBootstrapper extends StatefulWidget {
  const SessionBootstrapper({super.key});

  @override
  State<SessionBootstrapper> createState() => _SessionBootstrapperState();
}

class _SessionBootstrapperState extends State<SessionBootstrapper> {
  late final Future<void> _restoreFuture;

  @override
  void initState() {
    super.initState();
    _restoreFuture = context.read<AuthSession>().restore();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _restoreFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(
            body: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  VistaarLogoMark(size: 72),
                  SizedBox(height: 24),
                  CircularProgressIndicator(),
                ],
              ),
            ),
          );
        }
        final isAuthenticated = context.watch<AuthSession>().isAuthenticated;
        return isAuthenticated ? const HomeRouter() : const RoleSelectionScreen();
      },
    );
  }
}
