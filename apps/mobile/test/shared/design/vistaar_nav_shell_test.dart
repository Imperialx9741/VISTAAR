import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vistaar_mobile/shared/design/vistaar_nav_shell.dart';

class _CountingScreen extends StatefulWidget {
  const _CountingScreen({required this.bodyText, required this.onBuild});

  final String bodyText;
  final VoidCallback onBuild;

  @override
  State<_CountingScreen> createState() => _CountingScreenState();
}

class _CountingScreenState extends State<_CountingScreen> {
  int _tapCount = 0;

  @override
  void initState() {
    super.initState();
    widget.onBuild();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Text(widget.bodyText),
          TextButton(
            onPressed: () => setState(() => _tapCount++),
            child: Text('${widget.bodyText} taps: $_tapCount'),
          ),
        ],
      ),
    );
  }
}

/// Destination labels ("Tab0", "Tab1", ...) and on-screen body text
/// ("Screen0", "Screen1", ...) are deliberately different strings — the
/// nav bar's own labels stay in the tree regardless of which tab is
/// selected (`NavigationBar`'s default `alwaysShow` label behavior), so
/// a body reusing the same text as its own destination label would
/// make `find.text(...)` ambiguous between the two.
Widget _shell(List<void Function()> onBuildCallbacks) {
  return MaterialApp(
    home: VistaarNavShell(
      destinations: [
        for (var i = 0; i < onBuildCallbacks.length; i++)
          VistaarNavDestination(
            label: 'Tab$i',
            icon: Icons.circle_outlined,
            selectedIcon: Icons.circle,
            screen: _CountingScreen(
              bodyText: 'Screen$i',
              onBuild: onBuildCallbacks[i],
            ),
          ),
      ],
    ),
  );
}

void main() {
  testWidgets('builds only the first tab initially', (tester) async {
    var tab0Builds = 0;
    var tab1Builds = 0;

    await tester.pumpWidget(_shell([() => tab0Builds++, () => tab1Builds++]));

    expect(tab0Builds, 1);
    expect(tab1Builds, 0);
    expect(find.text('Screen0'), findsOneWidget);
    expect(find.text('Screen1'), findsNothing);
  });

  testWidgets('builds a tab lazily the first time it is selected', (tester) async {
    var tab1Builds = 0;

    await tester.pumpWidget(_shell([() {}, () => tab1Builds++]));
    expect(tab1Builds, 0);

    await tester.tap(find.text('Tab1'));
    await tester.pumpAndSettle();

    expect(tab1Builds, 1);
    expect(find.text('Screen1'), findsOneWidget);
  });

  testWidgets("preserves a tab's state when switching away and back", (tester) async {
    await tester.pumpWidget(_shell([() {}, () {}]));

    // Tap the Tab0 counting button once, then switch to Tab1 and back.
    await tester.tap(find.text('Screen0 taps: 0'));
    await tester.pump();
    expect(find.text('Screen0 taps: 1'), findsOneWidget);

    await tester.tap(find.text('Tab1'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Tab0'));
    await tester.pumpAndSettle();

    // Still 1, not reset to 0 — the tab was never rebuilt from scratch.
    expect(find.text('Screen0 taps: 1'), findsOneWidget);
  });
}
