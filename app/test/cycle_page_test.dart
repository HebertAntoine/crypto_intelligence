/// The cycle page: a phase, a chart, history - and never a forecast.
library;

import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/api/cycle_models.dart';
import 'package:crypto_intelligence_app/screens/cycle_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

ApiClient _shippedClient() => ApiClient(
      baseUrl: '',
      loadAsset: (path) async {
        final file = File(path);
        if (!file.existsSync()) throw Exception('asset absent: $path');
        return file.readAsStringSync();
      },
    );

Future<void> _open(WidgetTester tester, String asset) async {
  await tester.pumpWidget(MaterialApp(
    home: CyclePage(client: _shippedClient(), asset: asset),
  ));
  await tester.pumpAndSettle();
}

Iterable<String> _texts(WidgetTester tester) => tester
    .widgetList<Text>(find.byType(Text))
    .map((widget) => widget.data ?? widget.textSpan?.toPlainText() ?? '');

void main() {
  testWidgets('the page opens on the phase, its direction and three figures',
      (tester) async {
    await _open(tester, 'BTC');

    expect(find.text('PHASE ACTUELLE'), findsOneWidget);
    expect(find.byKey(const ValueKey('cycle-phase')), findsOneWidget);
    expect(find.byKey(const ValueKey('cycle-direction')), findsOneWidget);

    final cycle = await _shippedClient().cycle('BTC');
    expect(find.text('${cycle.phaseEmoji} ${cycle.phaseLabel}'), findsOneWidget);
    // Three figures on the main card, never a wall of numbers.
    expect(find.textContaining('Depuis le halving'), findsOneWidget);
    expect(find.textContaining('Distance de l’ATH'), findsOneWidget);
    expect(find.textContaining('Phase depuis'), findsOneWidget);
  });

  testWidgets('the chart carries the phases, the halvings and today',
      (tester) async {
    await _open(tester, 'BTC');
    final cycle = await _shippedClient().cycle('BTC');

    expect(find.byKey(const ValueKey('cycle-chart')), findsOneWidget);
    expect(find.byKey(const ValueKey('cycle-today')), findsOneWidget);
    expect(cycle.chart.points.length, greaterThan(200));
    expect(cycle.chart.phases, isNotEmpty);
    // Every halving of the history, plus the next one flagged as an estimate.
    expect(cycle.chart.halvings.where((h) => !h.estimated).length, greaterThanOrEqualTo(3));
    expect(cycle.chart.halvings.any((h) => h.estimated), isTrue);
    expect(
      cycle.chart.annotations.any((a) => a.kind == 'ATH'),
      isTrue,
      reason: 'les sommets viennent des données',
    );
  });

  testWidgets('the page never announces a future top or bottom', (tester) async {
    await _open(tester, 'BTC');

    // The whole page, read to the end: nothing anywhere announces a date.
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('cycle-disclaimer')),
      500,
      scrollable: find.byType(Scrollable).first,
    );
    final page = _texts(tester).join(' ').toLowerCase();
    for (final forbidden in const [
      'bull run prévu',
      'prochain ath',
      'sommet prévu',
      'bear market terminé',
      'dans 54 jours',
    ]) {
      expect(page.contains(forbidden), isFalse, reason: forbidden);
    }
    expect(find.byKey(const ValueKey('cycle-disclaimer')), findsOneWidget);
    expect(find.textContaining('non prédictive'), findsWidgets);
  });

  testWidgets('a bottom is only named once a later high confirmed it',
      (tester) async {
    final cycle = await _shippedClient().cycle('BTC');
    final ongoing = cycle.cycles.where((c) => c.ongoing);
    for (final stats in ongoing) {
      expect(stats.bottomConfirmed, isFalse);
    }
    await _open(tester, 'BTC');
    final page = _texts(tester).join(' ');
    if (cycle.chart.localLow.isNotEmpty) {
      expect(page.contains('Plus bas local actuel'), isTrue);
    }
    expect(page.contains('le creux est atteint'), isFalse);
  });

  testWidgets('what would change the phase is shown, in both directions',
      (tester) async {
    await _open(tester, 'BTC');

    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('cycle-next-step')),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.byKey(const ValueKey('cycle-next-step')), findsOneWidget);
    expect(find.textContaining('Prochaine étape'), findsOneWidget);
    expect(find.textContaining('Invalidation'), findsOneWidget);
  });

  testWidgets('the monthly archive lists past readings', (tester) async {
    await _open(tester, 'BTC');
    final cycle = await _shippedClient().cycle('BTC');
    if (cycle.snapshots.isEmpty) return;

    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('cycle-snapshots')),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('Historique mensuel'), findsOneWidget);
    expect(find.text(cycle.snapshots.first.monthLabel.toUpperCase()), findsOneWidget);
  });

  testWidgets('previous cycles are compared as history only', (tester) async {
    await _open(tester, 'BTC');

    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('cycle-previous')),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('Cycles précédents'), findsOneWidget);
    expect(find.textContaining('100 au jour du halving'), findsOneWidget);
  });

  testWidgets('ETH reads the Bitcoin regime, never its own halving cycle',
      (tester) async {
    await _open(tester, 'ETH');
    final cycle = await _shippedClient().cycle('ETH');

    expect(cycle.isBtc, isFalse);
    expect(find.text('🔄 Régime crypto'), findsOneWidget);
    expect(find.textContaining('Depuis le halving'), findsNothing);
    expect(find.byKey(const ValueKey('cycle-relative')), findsOneWidget);
    expect(find.textContaining("n'a pas de halving"), findsOneWidget);
  });

  test('short phase runs are merged so the chart shows cycles, not noise', () {
    final runs = [
      CyclePhaseRun(
        phase: 'EXPANSION', label: 'Expansion', tone: 'GREEN',
        start: DateTime(2024), end: DateTime(2024, 6), days: 180,
      ),
      CyclePhaseRun(
        phase: 'TRANSITION', label: 'Transition', tone: 'ORANGE',
        start: DateTime(2024, 6), end: DateTime(2024, 6, 10), days: 10,
      ),
      CyclePhaseRun(
        phase: 'EXPANSION', label: 'Expansion', tone: 'GREEN',
        start: DateTime(2024, 6, 10), end: DateTime(2024, 12), days: 170,
      ),
    ];
    final bands = mergedBands(runs);
    expect(bands.length, 1);
    expect(bands.first.tone, 'GREEN');
    expect(bands.first.end, DateTime(2024, 12));
  });
}
