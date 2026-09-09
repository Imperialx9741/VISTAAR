import 'package:flutter/material.dart';

import 'vistaar_colors.dart';

/// VISTAAR's mark — a gold rounded-square badge with a bold "V", on a
/// deep-green ground. Mobile had no logo asset at all before this
/// (2026-09-08, owner-directed Rapido-benchmarked redesign + admin-web
/// color parity) — the role-selection screen used a generic
/// `Icons.directions_car_filled` instead. This widget is a deliberate,
/// pixel-for-pixel port of `apps/admin-web`'s own mark
/// (`Sidebar.module.css` `.brandMark`: 30x30, 7px corner radius, gold
/// background, bold deep-green "V", `font-weight: 800`) so both apps
/// show the same logo, not two similar-but-different ones — per the
/// owner's explicit "the vistaar app logo is also same as admin
/// dashboard color" instruction. [size] scales the whole badge
/// (defaults to admin-web's own 30dp); the corner radius and font
/// weight scale with it so the mark stays proportionally identical at
/// any size rather than just growing a fixed-radius square.
class VistaarLogoMark extends StatelessWidget {
  const VistaarLogoMark({super.key, this.size = 30});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: VistaarColors.accent,
        borderRadius: BorderRadius.circular(size * (7 / 30)),
      ),
      child: Text(
        'V',
        style: TextStyle(
          color: VistaarColors.seed,
          fontWeight: FontWeight.w800,
          fontSize: size * (15 / 30),
          height: 1,
        ),
      ),
    );
  }
}

/// The mark plus the "VISTAAR" wordmark next to it, matching admin-
/// web's `.brand` block layout (mark, then name stacked over an
/// optional subtitle). Used wherever the app previously showed
/// "VISTAAR" as plain text with no mark at all (the role-selection
/// screen; anywhere else a splash/brand moment is added later) — never
/// introduces new copy, [subtitle] is optional and omitted by callers
/// that don't need admin-web's "Admin Console" equivalent line.
class VistaarWordmark extends StatelessWidget {
  const VistaarWordmark({
    super.key,
    this.markSize = 44,
    this.subtitle,
    this.alignment = MainAxisAlignment.center,
  });

  final double markSize;
  final String? subtitle;
  final MainAxisAlignment alignment;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: alignment,
      children: [
        VistaarLogoMark(size: markSize),
        const SizedBox(width: 12),
        Flexible(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'VISTAAR',
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.2,
                ),
              ),
              if (subtitle != null)
                Text(
                  subtitle!,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
