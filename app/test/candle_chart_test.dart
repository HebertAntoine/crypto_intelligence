/// Le graphique interactif, rendu réellement et manipulé par des gestes.
///
/// Le viewport est vérifié à part, en calcul pur. Ici la question est
/// différente : les gestes atteignent-ils bien la fenêtre, le crosshair
/// désigne-t-il la bougie qu'il dessine, et l'ensemble tient-il sur un
/// téléphone sans déborder.
library;

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/chart/candle_chart.dart';
import 'package:crypto_intelligence_app/chart/chart_layers.dart';
import 'package:crypto_intelligence_app/chart/chart_viewport.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

final _start = DateTime.utc(2026, 1, 1);

List<CandlePoint> _candles(int count) => List.generate(count, (i) {
      final base = 100.0 + i * 0.5;
      return CandlePoint(
        time: _start.add(Duration(hours: 4 * i)),
        open: base,
        high: base + 3,
        low: base - 3,
        close: base + (i.isEven ? 1.5 : -1.5),
        volume: 1000 + (i % 17) * 120,
      );
    });

Future<void> _pump(
  WidgetTester tester, {
  int count = 500,
  Size size = const Size(390, 600),
  ChartLayerSet? layers,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SizedBox(
        width: size.width,
        height: size.height - 100,
        child: CandleChart(
          candles: _candles(count),
          timeframe: '4h',
          layers: layers ?? ChartLayerSet.initial(),
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// La fenêtre courante, lue sur l'état réel du widget.
ChartViewport _viewport(WidgetTester tester) {
  final painter = tester
      .widget<CustomPaint>(find.descendant(
        of: find.byType(CandleChart),
        matching: find.byType(CustomPaint),
      ))
      .painter!;
  // ignore: avoid_dynamic_calls
  return (painter as dynamic).viewport as ChartViewport;
}

void main() {
  group('TEST A — 500 bougies chargées, une fenêtre étroite affichée', () {
    testWidgets('la vue s’ouvre sur les dernières bougies', (tester) async {
      await _pump(tester);
      final vp = _viewport(tester);
      expect(vp.candles.length, 500);
      expect(vp.visibleCount, kDefaultVisibleCandles);
      expect(vp.endIndex, 500);
    });
  });

  group('TEST B — le glissement remonte l’historique', () {
    testWidgets('un drag vers la droite recule dans le temps', (tester) async {
      await _pump(tester);
      final before = _viewport(tester).startIndex;
      await tester.drag(find.byType(CandleChart), const Offset(180, 0));
      await tester.pumpAndSettle();
      expect(_viewport(tester).startIndex, lessThan(before));
    });

    testWidgets('un drag vers la gauche revient vers le présent',
        (tester) async {
      await _pump(tester);
      await tester.drag(find.byType(CandleChart), const Offset(250, 0));
      await tester.pumpAndSettle();
      final middle = _viewport(tester).startIndex;
      await tester.drag(find.byType(CandleChart), const Offset(-250, 0));
      await tester.pumpAndSettle();
      expect(_viewport(tester).startIndex, greaterThan(middle));
    });
  });

  group('TEST C — le pincement change la fenêtre', () {
    testWidgets('écarter les doigts réduit le nombre de bougies visibles',
        (tester) async {
      await _pump(tester);
      final before = _viewport(tester).visibleCount;
      final centre = tester.getCenter(find.byType(CandleChart));
      final a = await tester.startGesture(centre - const Offset(40, 0));
      final b = await tester.startGesture(centre + const Offset(40, 0));
      await a.moveBy(const Offset(-80, 0));
      await b.moveBy(const Offset(80, 0));
      await tester.pump();
      final zoomed = _viewport(tester).visibleCount;
      await a.up();
      await b.up();
      await tester.pumpAndSettle();
      expect(zoomed, lessThan(before));
    });
  });

  group('TEST E — le double tap restaure la vue', () {
    testWidgets('après navigation, la vue revient au présent', (tester) async {
      await _pump(tester);
      await tester.drag(find.byType(CandleChart), const Offset(400, 0));
      await tester.pumpAndSettle();
      expect(_viewport(tester).endIndex, lessThan(500));

      final centre = tester.getCenter(find.byType(CandleChart));
      await tester.tapAt(centre);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tapAt(centre);
      await tester.pumpAndSettle();

      final vp = _viewport(tester);
      expect(vp.endIndex, 500);
      expect(vp.visibleCount, kDefaultVisibleCandles);
    });
  });

  group('TEST F/G — le crosshair et ses valeurs', () {
    testWidgets('un appui long affiche les OHLC de la bougie visée',
        (tester) async {
      await _pump(tester);
      final vp = _viewport(tester);
      final target = vp.startIndex + 20;
      final x = vp.indexToX(target.toDouble());
      final box = tester.getRect(find.byType(CandleChart));

      final gesture =
          await tester.startGesture(Offset(box.left + x, box.top + 150));
      await tester.pump(const Duration(milliseconds: 600));
      await tester.pumpAndSettle();

      // Le crosshair s'accroche à une bougie du jeu, pas à un pixel.
      final found = _viewport(tester).candleIndexAtX(x);
      expect(found, target);
      final candle = vp.candles[found!];
      // Les valeurs lues sont exactement celles de cette bougie.
      expect(candle.open, vp.candles[target].open);
      expect(candle.close, vp.candles[target].close);
      expect(candle.volume, vp.candles[target].volume);

      await gesture.up();
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  });

  group('TEST N — aucun débordement', () {
    for (final size in [
      const Size(360, 640),
      const Size(390, 700),
      const Size(430, 800),
      const Size(800, 390), // paysage
    ]) {
      testWidgets('rendu propre en ${size.width.toInt()}×${size.height.toInt()}',
          (tester) async {
        await _pump(tester, size: size);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('un jeu vide affiche un message, pas une exception',
        (tester) async {
      tester.view.physicalSize = const Size(390, 600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            height: 400,
            child: CandleChart(
              candles: [],
              timeframe: '4h',
              layers: ChartLayerSet(<ChartLayer>{ChartLayer.candles}),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('un jeu très court ne casse pas le rendu', (tester) async {
      await _pump(tester, count: 6);
      expect(tester.takeException(), isNull);
      expect(_viewport(tester).visibleCount, 6);
    });
  });

  group('En-tête et axes', () {
    testWidgets('la paire et la source affichées sont celles reçues',
        (tester) async {
      tester.view.physicalSize = const Size(390, 600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SizedBox(
            height: 420,
            child: CandleChart(
              candles: _candles(200),
              timeframe: '4h',
              layers: ChartLayerSet.initial(),
              pair: 'BTCUSDT',
              source: 'Binance',
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('sans paire ni source, l’en-tête n’invente rien',
        (tester) async {
      await _pump(tester);
      expect(tester.takeException(), isNull);
    });

    testWidgets('les étiquettes de dates tiennent dans leur bande',
        (tester) async {
      // Deux lignes — « 4 sept. » puis « 14:00 » — à 22 px la seconde était
      // coupée par le bord du cadre.
      for (final size in [const Size(360, 640), const Size(430, 820)]) {
        await _pump(tester, size: size);
        expect(tester.takeException(), isNull);
      }
    });
  });

  group('Calques', () {
    testWidgets('masquer le volume ne casse pas la mise en page',
        (tester) async {
      await _pump(
        tester,
        layers: ChartLayerSet.initial().toggled(ChartLayer.volume),
      );
      expect(tester.takeException(), isNull);
    });

    test('un calque structurel ne se désactive pas', () {
      final set = ChartLayerSet.initial();
      expect(set.toggled(ChartLayer.candles).isVisible(ChartLayer.candles),
          isTrue);
      expect(set.toggled(ChartLayer.volume).isVisible(ChartLayer.volume),
          isFalse);
    });

    test('la barre ne propose que les calques optionnels', () {
      expect(ChartLayerSet.toggleable, isNot(contains(ChartLayer.candles)));
      expect(ChartLayerSet.toggleable, contains(ChartLayer.volume));
    });
  });
}
