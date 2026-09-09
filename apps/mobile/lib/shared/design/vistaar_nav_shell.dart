import 'package:flutter/material.dart';

/// One entry in a [VistaarNavShell]'s bottom navigation bar.
class VistaarNavDestination {
  const VistaarNavDestination({
    required this.label,
    required this.icon,
    required this.selectedIcon,
    required this.screen,
  });

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final Widget screen;
}

/// The persistent bottom-navigation shell behind both role home screens
/// (Phase 3 of the owner-requested UI/UX redesign, 2026-09-08 — see the
/// Phase 1 audit's "proposed navigation structure": this app had zero
/// bottom-nav/tabs anywhere before this, every secondary screen reached
/// only via an AppBar icon). One shared, reusable shell — not a
/// per-role reimplementation — driven entirely by the
/// [VistaarNavDestination] list each role's own home screen supplies.
///
/// Each destination's screen is built lazily, the first time its tab is
/// selected, and then kept alive (not rebuilt or disposed) for the rest
/// of the shell's lifetime — an [IndexedStack] over a per-index "has
/// this been visited" flag, not a full eager [IndexedStack]. This
/// matters for two real reasons, not just an optimization: it avoids
/// firing every tab's API calls (ride history, wallet balance, ...) the
/// instant a role's home screen mounts, before the user has ever opened
/// those tabs (Phase 10's own "performance over decorative work,
/// smooth on mid-range Android phones"); and it means the Home tab's
/// own state (Sarthi's location-update stream and offer polling, most
/// importantly) is preserved when the driver switches to another tab
/// and back, exactly as if it were still the only screen on the stack —
/// going online must not silently stop just because the driver checked
/// their wallet.
class VistaarNavShell extends StatefulWidget {
  const VistaarNavShell({super.key, required this.destinations});

  final List<VistaarNavDestination> destinations;

  @override
  State<VistaarNavShell> createState() => _VistaarNavShellState();
}

class _VistaarNavShellState extends State<VistaarNavShell> {
  int _index = 0;
  late final List<bool> _visited = List<bool>.generate(
    widget.destinations.length,
    (i) => i == 0,
  );

  void _onSelect(int index) {
    setState(() {
      _index = index;
      _visited[index] = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: [
          for (var i = 0; i < widget.destinations.length; i++)
            _visited[i] ? widget.destinations[i].screen : const SizedBox.shrink(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: _onSelect,
        destinations: [
          for (final destination in widget.destinations)
            NavigationDestination(
              icon: Icon(destination.icon),
              selectedIcon: Icon(destination.selectedIcon),
              label: destination.label,
            ),
        ],
      ),
    );
  }
}
