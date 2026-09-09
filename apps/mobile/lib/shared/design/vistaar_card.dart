import 'package:flutter/material.dart';

import 'vistaar_spacing.dart';

/// The one card shape used everywhere a screen groups related content
/// (ride summary, wallet balance, offer, profile row) — reads its look
/// from [CardThemeData] in `app_theme.dart`, so this widget only fixes
/// the padding/layout contract, not the visual style, per Phase 2
/// (design system): "reusable components rather than styling each
/// screen independently."
class VistaarCard extends StatelessWidget {
  const VistaarCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(VistaarSpacing.md),
    this.onTap,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final cardTheme = Theme.of(context).cardTheme;
    final content = Padding(padding: padding, child: child);

    // Deliberately one Material layer, not a Card wrapping an InkWell —
    // stacking those double-paints the shape/elevation and (on some
    // Android skins) visibly doubles the corner radius shadow.
    return Material(
      color: cardTheme.color,
      elevation: cardTheme.elevation ?? 0,
      shape: cardTheme.shape,
      clipBehavior: Clip.antiAlias,
      child: onTap == null ? content : InkWell(onTap: onTap, child: content),
    );
  }
}
