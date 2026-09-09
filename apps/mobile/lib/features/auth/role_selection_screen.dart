import 'package:flutter/material.dart';

import '../../shared/design/vistaar_logo.dart';
import '../location/location_permission_screen.dart';
import 'app_role.dart';

/// The app's entry screen (ADR-0027): the user picks which of the two
/// roles they're logging in as before anything else happens. Both
/// buttons lead to [LocationPermissionScreen] next (owner decision,
/// 2026-08-29 — the permission prompt's own copy needs to know the role
/// first), which itself continues on to the phone entry/OTP flow — only
/// the `account_type` sent to the backend ultimately differs.
class RoleSelectionScreen extends StatelessWidget {
  const RoleSelectionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const VistaarWordmark(markSize: 56),
              const SizedBox(height: 8),
              Text(
                'Continue as',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const SizedBox(height: 32),
              _RoleCard(
                role: AppRole.user,
                icon: Icons.person_outline,
                subtitle: 'Book a ride',
              ),
              const SizedBox(height: 16),
              _RoleCard(
                role: AppRole.sarthi,
                icon: Icons.two_wheeler_outlined,
                subtitle: 'Drive and earn',
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RoleCard extends StatelessWidget {
  const _RoleCard({
    required this.role,
    required this.icon,
    required this.subtitle,
  });

  final AppRole role;
  final IconData icon;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => LocationPermissionScreen(role: role),
            ),
          );
        },
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            children: [
              Icon(icon, size: 32),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      role.displayName,
                      style: Theme.of(context).textTheme.titleMedium
                          ?.copyWith(fontWeight: FontWeight.w600),
                    ),
                    Text(
                      subtitle,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}
