/// VISTAAR's spacing and shape scale (Phase 2 design system, 2026-09-08).
/// Every screen previously picked its own `EdgeInsets`/`SizedBox` gaps
/// and `BorderRadius` values ad hoc — this file is the single source
/// so new and redesigned screens compose instead of guessing.
class VistaarSpacing {
  const VistaarSpacing._();

  /// 8pt base scale — the standard Material spacing unit, so gaps stay
  /// visually consistent without every screen re-deriving a number.
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
  static const double xxl = 48;

  /// Screen-edge padding, used on every top-level screen body.
  static const double screenPadding = md;
}

/// Two corner-radius tiers, deliberately not more — a large "surface"
/// radius for cards/sheets/dialogs and a smaller "control" radius for
/// buttons/inputs/chips, so the app reads as considered rather than
/// (per the owner's own brief) "excessive rounded cards".
class VistaarRadius {
  const VistaarRadius._();

  static const double control = 12;
  static const double surface = 20;
}
