import 'package:flutter/material.dart';

import 'vistaar_spacing.dart';

/// The one entry point for a modal bottom sheet in this app — wraps
/// `showModalBottomSheet` with the padding/safe-area handling every
/// screen would otherwise duplicate (keyboard inset, bottom system-nav
/// inset, consistent horizontal padding), and picks up
/// [BottomSheetThemeData] from `app_theme.dart` for its shape/drag
/// handle automatically.
Future<T?> showVistaarBottomSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  bool isScrollControlled = true,
}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: isScrollControlled,
    builder: (context) {
      final viewInsets = MediaQuery.viewInsetsOf(context);
      return Padding(
        padding: EdgeInsets.only(
          left: VistaarSpacing.md,
          right: VistaarSpacing.md,
          bottom: viewInsets.bottom + VistaarSpacing.md,
          top: VistaarSpacing.sm,
        ),
        child: SafeArea(top: false, child: builder(context)),
      );
    },
  );
}
