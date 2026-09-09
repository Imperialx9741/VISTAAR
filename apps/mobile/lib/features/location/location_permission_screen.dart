import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../../shared/widgets/primary_button.dart';
import '../auth/app_role.dart';
import '../auth/phone_entry_screen.dart';

/// Step inserted right after role selection (owner decision, 2026-08-29
/// — docs/16-mobile/mobile-app-implementation-plan.md §6.1), before phone
/// entry: asks for "when in use" location access, with role-appropriate
/// copy. Background location ("Always") is NOT requested here — that's
/// requested separately, only once a Sarthi (driver) actually goes
/// online (a screen this app doesn't have yet).
///
/// The app stays usable either way: if location is denied, this screen
/// still continues on to login — a User can type a pickup address by
/// hand once ride booking exists, and a Sarthi simply can't go online
/// until location is granted (surfaced on that screen when it exists,
/// not here). This screen never blocks login on a location decision.
///
/// If permission is already granted (a returning user, mid-session
/// re-login after sign-out), this screen skips itself immediately —
/// it never re-prompts someone who already said yes.
class LocationPermissionScreen extends StatefulWidget {
  const LocationPermissionScreen({super.key, required this.role});

  final AppRole role;

  @override
  State<LocationPermissionScreen> createState() =>
      _LocationPermissionScreenState();
}

class _LocationPermissionScreenState extends State<LocationPermissionScreen>
    with WidgetsBindingObserver {
  bool _isChecking = true;
  bool _isRequesting = false;
  LocationPermission? _status;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _checkInitialStatus();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Re-checks permission status on returning to the app — the only way
  /// to notice a grant made from the OS Settings screen (opened via the
  /// "Open Settings" button below), since nothing else in this screen's
  /// lifecycle would otherwise observe it.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !_isChecking) {
      _refreshStatus();
    }
  }

  Future<void> _checkInitialStatus() async {
    final permission = await Geolocator.checkPermission();
    if (!mounted) return;
    if (_isGranted(permission)) {
      _continue();
      return;
    }
    setState(() {
      _status = permission;
      _isChecking = false;
    });
  }

  Future<void> _refreshStatus() async {
    final permission = await Geolocator.checkPermission();
    if (!mounted) return;
    if (_isGranted(permission)) {
      _continue();
      return;
    }
    setState(() => _status = permission);
  }

  bool _isGranted(LocationPermission permission) =>
      permission == LocationPermission.always ||
      permission == LocationPermission.whileInUse;

  Future<void> _requestPermission() async {
    setState(() => _isRequesting = true);
    final permission = await Geolocator.requestPermission();
    if (!mounted) return;
    setState(() {
      _status = permission;
      _isRequesting = false;
    });
    if (_isGranted(permission)) {
      _continue();
    }
  }

  void _continue() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => PhoneEntryScreen(role: widget.role),
      ),
    );
  }

  String get _roleReason => widget.role == AppRole.sarthi
      ? 'VISTAAR uses your location to show you nearby ride requests.'
      : 'VISTAAR uses your location to match you with nearby drivers.';

  @override
  Widget build(BuildContext context) {
    if (_isChecking) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final deniedForever = _status == LocationPermission.deniedForever;

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.location_on_outlined, size: 56),
              const SizedBox(height: 16),
              Text(
                'Allow location access',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                _roleReason,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              if (deniedForever) ...[
                const SizedBox(height: 12),
                Text(
                  widget.role == AppRole.sarthi
                      ? "Location is currently off for VISTAAR. You can "
                            "still sign in, but you won't be able to go "
                            'online until it is enabled.'
                      : 'Location is currently off for VISTAAR. You can '
                            'still sign in and enter your pickup address by '
                            'hand.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              const SizedBox(height: 32),
              PrimaryButton(
                label: deniedForever ? 'Open Settings' : 'Allow location',
                isLoading: _isRequesting,
                onPressed: deniedForever
                    ? Geolocator.openAppSettings
                    : _requestPermission,
              ),
              const SizedBox(height: 12),
              Center(
                child: TextButton(
                  onPressed: _continue,
                  child: const Text('Not now'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
