import 'package:flutter/material.dart';

import 'vistaar_colors.dart';
import 'vistaar_spacing.dart';

/// The visual meaning a [StatusChip] communicates — deliberately just
/// these four, matching [VistaarColors]'s own semantic set, so a
/// screen picks a *meaning* (this ride is active vs. this recharge
/// failed) rather than a color.
enum StatusTone { neutral, success, warning, danger }

/// A small filled label for ride/wallet/offer/case status — "Online",
/// "Matching", "Payment failed", "Resolved" — used anywhere a screen
/// currently builds its own ad hoc `Container` + `BoxDecoration` for
/// this (Phase 2 audit finding: no shared status indicator existed
/// anywhere in the app before this).
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.label, this.tone = StatusTone.neutral});

  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (Color background, Color foreground) = switch (tone) {
      StatusTone.neutral => (scheme.surfaceContainerHighest, scheme.onSurfaceVariant),
      StatusTone.success => (VistaarColors.successContainer, VistaarColors.onSuccessContainer),
      StatusTone.warning => (VistaarColors.warningContainer, VistaarColors.onWarningContainer),
      StatusTone.danger => (scheme.errorContainer, scheme.onErrorContainer),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: VistaarSpacing.sm, vertical: VistaarSpacing.xs),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(VistaarRadius.control),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium?.copyWith(color: foreground),
      ),
    );
  }
}
