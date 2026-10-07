/// Le radar macro tel que la page le montre : cinq moteurs, quinze surveillés.
///
/// Ce que ces tests figent :
///   - importance et direction sont deux échelles distinctes à l'écran ;
///   - un moteur sans source est déclaré, jamais affiché comme neutre ;
///   - la Home ne répète pas « Macro » en ligne et en bloc ;
///   - chaque moteur ouvre ses chiffres, ses sources et sa prochaine échéance.
library;

import 'dart:async';
import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/api/macro_models.dart';
import 'package:crypto_intelligence_app/live_prices/live_price_service.dart';
import 'package:crypto_intelligence_app/main.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:crypto_intelligence_app/widgets/macro_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _SilentLivePrices implements LivePriceSource {
  @override
  LivePriceState get current =>
      LivePriceState(connection: LivePriceConnection.stopped);

  @override
  Stream<LivePriceState> get updates => const Stream.empty();
}

ApiClient _shippedClient() => ApiClient(
      baseUrl: '',
      loadAsset: (path) async {
        final file = File(path);
        if (!file.existsSync()) throw Exception('asset absent: $path');
        return file.readAsStringSync();
      },
    );

Future<void> _openBtc(WidgetTester tester) async {
  tester.view.physicalSize = const Size(430, 932);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark,
      home: HomeShell(
        client: _shippedClient(),
        livePrices: _SilentLivePrices(),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test('les quinze moteurs sont surveillés, cinq sont mis en avant', () async {
    final radar = await _shippedClient().macroDrivers();
    expect(radar.drivers.length, 15);
    expect(radar.watched, 15);
    expect(radar.top.length, lessThanOrEqualTo(5));

    // Le TOP est un classement, pas une liste figée.
    final scores = radar.top.map((d) => d.importance).toList();
    final sorted = [...scores]..sort((a, b) => b.compareTo(a));
    expect(scores, sorted);
    for (final driver in radar.top) {
      expect(driver.available, isTrue,
          reason: 'un moteur sans source ne peut pas expliquer le marché');
      expect(driver.importance, greaterThan(0));
    }
  });

  test('importance et direction restent deux échelles séparées', () async {
    final radar = await _shippedClient().macroDrivers();
    for (final driver in radar.drivers) {
      expect(
        const {'FAVORABLE', 'UNFAVORABLE', 'NEUTRAL', 'MIXED', 'UNKNOWN'},
        contains(driver.direction),
      );
      expect(
        const {'NONE', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL'},
        contains(driver.attention),
      );
      // Une attention élevée n'impose aucune direction : c'est tout l'objet
      // de la séparation.
      if (driver.direction == 'UNKNOWN' && driver.available) {
        expect(driver.summary.isNotEmpty, isTrue);
      }
    }
  });

  test('aucune probabilité n\'est produite', () async {
    final radar = await _shippedClient().macroDrivers();
    for (final driver in radar.drivers) {
      expect(driver.summary.contains('% de chances'), isFalse);
      expect(driver.summary.toLowerCase().contains('probabilité'), isFalse);
    }
  });

  testWidgets('la Home montre les cinq moteurs et le chemin vers les quinze',
      (tester) async {
    await _openBtc(tester);
    final radar = await _shippedClient().macroDrivers();

    final block = find.byKey(const ValueKey('macro-drivers'));
    await tester.scrollUntilVisible(block, 300,
        scrollable: find.byType(Scrollable).first);
    expect(block, findsOneWidget);
    expect(find.text('Pourquoi le marché bouge ?'), findsOneWidget);

    for (final driver in radar.top) {
      expect(find.byKey(ValueKey('macro-driver-${driver.key}')), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('macro-see-all')), findsOneWidget);
    expect(find.text('Voir les 15 moteurs ›'), findsOneWidget);
  });

  testWidgets('« Macro » n\'est pas lu deux fois sur la Home', (tester) async {
    await _openBtc(tester);
    // Le bloc des moteurs remplace la ligne « Macro » des familles : la même
    // famille ne doit pas apparaître en ligne et en bloc.
    await tester.scrollUntilVisible(
        find.byKey(const ValueKey('main-factors')), 300,
        scrollable: find.byType(Scrollable).first);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('main-factors')),
        matching: find.text('Macro'),
      ),
      findsNothing,
    );
  });

  testWidgets('un moteur ouvre ses chiffres, ses sources et son échéance',
      (tester) async {
    await _openBtc(tester);
    final radar = await _shippedClient().macroDrivers();
    final first = radar.top.first;

    final row = find.byKey(ValueKey('macro-driver-${first.key}'));
    await tester.scrollUntilVisible(row, 300,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(row);
    await tester.pumpAndSettle();

    expect(find.byKey(ValueKey('macro-driver-page-${first.key}')), findsOneWidget);
    expect(find.byKey(const ValueKey('macro-driver-summary')), findsOneWidget);
    expect(find.text('POURQUOI CELA COMPTE'), findsOneWidget);
    if (first.values.isNotEmpty) {
      expect(find.text('VALEURS CLÉS'), findsOneWidget);
      // Chaque chiffre porte la période qu'il décrit, jamais l'heure du cycle.
      expect(find.textContaining(first.values.first.value), findsWidgets);
    }
    // Le poids est expliqué, pas asséné.
    expect(find.text('POURQUOI CE POIDS'), findsOneWidget);
  });

  testWidgets('la page des quinze déclare ceux qui n\'ont pas de source',
      (tester) async {
    await _openBtc(tester);
    final radar = await _shippedClient().macroDrivers();

    final seeAll = find.byKey(const ValueKey('macro-see-all'));
    await tester.scrollUntilVisible(seeAll, 300,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(seeAll);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('macro-drivers-page')), findsOneWidget);
    final measured = radar.drivers.where((d) => d.available).length;
    expect(find.byType(MacroDriverRow), findsNWidgets(measured));
    if (radar.unavailable.isNotEmpty) {
      expect(find.byKey(const ValueKey('macro-unavailable')), findsOneWidget);
    }
  });

  test('chaque direction a un mot et une couleur, y compris l\'inconnu', () {
    const unknown = MacroDriver(direction: 'UNKNOWN');
    expect(unknown.directionLabel.$2, 'Sens inconnu');
    expect(const MacroDriver(direction: 'FAVORABLE').directionLabel.$2, 'Soutien');
    expect(const MacroDriver(direction: 'UNFAVORABLE').directionLabel.$2, 'Pression');
    expect(const MacroDriver(direction: 'MIXED').directionLabel.$2, 'Partagé');
    expect(directionColor('UNKNOWN'), isNot(directionColor('FAVORABLE')));
  });
}
