import 'package:flutter/material.dart';

/// A full-width primary action button with a built-in loading state —
/// reused across every screen in the login flow so "tap → disabled →
/// spinner → re-enabled on error" behaves identically everywhere.
///
/// The label/spinner swap cross-fades (Phase 10 of the redesign,
/// "Animations", 2026-09-08) instead of popping instantly — a single,
/// deliberate change here reaches every "tap to submit" button in the
/// app at once, rather than animating each screen's button separately.
/// Short (150ms) and simple (opacity only, no size/layout animation) to
/// stay smooth on a mid-range phone and never make a driver/customer
/// wait longer to see the result of a tap.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.height = 48,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;

  /// Default (48) matches Material's own minimum touch target and is
  /// what every ordinary "submit" button in this app uses. A handful
  /// of genuinely dominant actions — Sarthi's Go Online/Offline, a
  /// ride offer's Accept — pass a taller value instead, per the
  /// owner's Rapido-benchmarked brief ("the primary action must be
  /// visually dominant" / "very large ACCEPT button"). Kept as one
  /// parameter on the shared component rather than a copy-pasted
  /// button on those two screens, so the loading-state cross-fade and
  /// styling stay identical everywhere.
  final double height;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: height,
      child: FilledButton(
        onPressed: isLoading ? null : onPressed,
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 150),
          child: isLoading
              ? const SizedBox(
                  key: ValueKey('loading'),
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2.5),
                )
              : Text(label, key: const ValueKey('label')),
        ),
      ),
    );
  }
}
