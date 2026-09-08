/// Le repère temps/prix, vérifié sans rien dessiner.
///
/// C'est la pièce dont tout le reste dépend : si une conversion est fausse,
/// une neckline se décroche de ses chandeliers au premier zoom. Ces tests
/// tiennent les propriétés que le peintre précédent ne pouvait pas avoir —
/// il étalait tout le jeu de données sur la largeur de l'écran, donc il
/// n'avait ni fenêtre, ni échelle locale, ni rien à déplacer.
library;

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/chart/chart_viewport.dart';
import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';

const _plot = Rect.fromLTWH(0, 0, 600, 400);
final _start = DateTime.utc(2026, 1, 1);

/// Un jeu régulier, avec un prix qui monte pour distinguer les bougies.
List<CandlePoint> _candles(int count, {Duration step = const Duration(hours: 4)}) =>
    List.generate(count, (i) {
      final base = 100.0 + i;
      return CandlePoint(
        time: _start.add(step * i),
        open: base,
        high: base + 2,
        low: base - 2,
        close: base + 1,
        volume: 1000 + i.toDouble(),
      );
    });

ChartViewport _viewport({int total = 500, int visible = 60}) =>
    ChartViewport.initial(
      candles: _candles(total),
      plot: _plot,
      desired: visible,
    );

void main() {
  group('TEST A — le jeu chargé et la fenêtre visible sont deux choses', () {
    test('500 bougies chargées, 60 visibles', () {
      final vp = _viewport();
      expect(vp.candles.length, 500);
      expect(vp.visibleCount, 60);
      expect(vp.visible.length, 60);
      // La fenêtre est à la fin: on ouvre sur le présent, pas sur 2017.
      expect(vp.endIndex, 500);
      expect(vp.startIndex, 440);
    });

    test('la fenêtre reste dans les bornes de zoom', () {
      expect(_viewport(visible: 5).visibleCount, kMinVisibleCandles);
      expect(_viewport(visible: 9999).visibleCount, kMaxVisibleCandles);
    });

    test('un jeu plus court que la fenêtre demandée ne déborde pas', () {
      final vp = ChartViewport.initial(
          candles: _candles(8), plot: _plot, desired: 60);
      expect(vp.visibleCount, 8);
      expect(vp.startIndex, 0);
    });

    test('un jeu vide ne casse aucune conversion', () {
      const vp = ChartViewport(
          candles: [], startIndex: 0, visibleCount: 0, plot: _plot);
      expect(vp.isEmpty, isTrue);
      expect(vp.visible, isEmpty);
      expect(vp.candleIndexAtX(300), isNull);
      expect(vp.xToTime(300), isNull);
    });
  });

  group('TEST D — l’échelle verticale se calcule sur le visible seul', () {
    test('un extrême hors fenêtre ne comprime pas la vue', () {
      final data = _candles(200);
      // Un pic ancien, très au-dessus, hors de la fenêtre visible.
      data[10] = CandlePoint(
        time: data[10].time, open: 100, high: 100000, low: 90,
        close: 95, volume: 1,
      );
      final vp = ChartViewport(
        candles: data, startIndex: 140, visibleCount: 60, plot: _plot,
      );
      // Le peintre précédent aurait écrasé 60 bougies contre 100 000.
      expect(vp.visibleMaxPrice, lessThan(1000));
      final visibleHigh =
          vp.visible.map((c) => c.high).reduce((a, b) => a > b ? a : b);
      expect(vp.visibleMaxPrice, greaterThan(visibleHigh));
    });

    test('une marge verticale entoure les extrêmes visibles', () {
      final vp = _viewport();
      final low = vp.visible.map((c) => c.low).reduce((a, b) => a < b ? a : b);
      final high =
          vp.visible.map((c) => c.high).reduce((a, b) => a > b ? a : b);
      expect(vp.visibleMinPrice, lessThan(low));
      expect(vp.visibleMaxPrice, greaterThan(high));
      final span = high - low;
      expect(low - vp.visibleMinPrice, closeTo(span * kPricePadding, 0.01));
    });

    test('un marché parfaitement plat garde une échelle utilisable', () {
      final flat = List.generate(60, (i) => CandlePoint(
            time: _start.add(Duration(hours: i)),
            open: 50, high: 50, low: 50, close: 50, volume: 1,
          ));
      final vp = ChartViewport.initial(candles: flat, plot: _plot);
      expect(vp.visibleMaxPrice, greaterThan(vp.visibleMinPrice));
      expect(vp.priceToY(50).isFinite, isTrue);
    });
  });

  group('TEST B — le déplacement remonte le temps', () {
    test('glisser vers la droite recule dans l’historique', () {
      final vp = _viewport();
      final moved = vp.pannedByPixels(200);
      expect(moved.startIndex, lessThan(vp.startIndex));
      expect(moved.visibleCount, vp.visibleCount);
      expect(moved.visibleStartTime!.isBefore(vp.visibleStartTime!), isTrue);
    });

    test('le déplacement s’arrête au début et à la fin du jeu', () {
      final vp = _viewport();
      expect(vp.pannedByPixels(100000).startIndex, 0);
      expect(vp.pannedByPixels(-100000).endIndex, vp.candles.length);
    });

    test('déplacer puis revenir retrouve la même fenêtre', () {
      final vp = _viewport();
      final there = vp.pannedByPixels(300);
      final back = there.pannedByPixels(-300);
      expect(back.startIndex, vp.startIndex);
    });
  });

  group('TEST C — le pincement change la durée visible', () {
    test('écarter les doigts montre moins de bougies', () {
      final vp = _viewport();
      final zoomed = vp.zoomedBy(2.0, _plot.center.dx);
      expect(zoomed.visibleCount, lessThan(vp.visibleCount));
    });

    test('rapprocher les doigts en montre davantage', () {
      final vp = _viewport();
      final zoomed = vp.zoomedBy(0.5, _plot.center.dx);
      expect(zoomed.visibleCount, greaterThan(vp.visibleCount));
    });

    test('le zoom respecte ses bornes', () {
      var vp = _viewport();
      for (var i = 0; i < 20; i++) {
        vp = vp.zoomedBy(2.0, _plot.center.dx);
      }
      expect(vp.visibleCount, kMinVisibleCandles);
      for (var i = 0; i < 30; i++) {
        vp = vp.zoomedBy(0.5, _plot.center.dx);
      }
      expect(vp.visibleCount, kMaxVisibleCandles);
    });

    test('le point sous le doigt reste sous le doigt', () {
      final vp = _viewport();
      const focal = 200.0;
      final anchorTime = vp.xToTime(focal)!;
      final zoomed = vp.zoomedBy(1.8, focal);
      // À une demi-bougie près : la fenêtre est discrète, pas continue.
      expect(
        zoomed.timeToX(anchorTime),
        closeTo(focal, zoomed.candleWidth),
      );
    });
  });

  group('TEST E — le double tap restaure une vue raisonnable', () {
    test('la vue revient sur les dernières bougies', () {
      final vp = _viewport().pannedByPixels(5000).zoomedBy(3.0, 100);
      final reset = vp.reset();
      expect(reset.visibleCount, kDefaultVisibleCandles);
      expect(reset.endIndex, reset.candles.length);
    });
  });

  group('TEST F/G — le crosshair désigne la bonne bougie', () {
    test('l’index trouvé sous une abscisse est celui dessiné à cette abscisse',
        () {
      final vp = _viewport();
      for (final index in [440, 455, 470, 499]) {
        final x = vp.indexToX(index.toDouble());
        expect(vp.candleIndexAtX(x), index);
      }
    });

    test('les OHLC lus correspondent exactement à la bougie visée', () {
      final vp = _viewport();
      const target = 462;
      final x = vp.indexToX(target.toDouble());
      final found = vp.candleIndexAtX(x)!;
      final candle = vp.candles[found];
      expect(candle.open, vp.candles[target].open);
      expect(candle.high, vp.candles[target].high);
      expect(candle.low, vp.candles[target].low);
      expect(candle.close, vp.candles[target].close);
      expect(candle.volume, vp.candles[target].volume);
    });

    test('hors du jeu, aucune bougie n’est inventée', () {
      final vp = _viewport();
      expect(vp.candleIndexAtX(-500), isNull);
      expect(vp.candleIndexAtX(100000), isNull);
    });
  });

  group('TEST H/I — une coordonnée reste attachée à sa bougie', () {
    test('un horodatage garde sa bougie après zoom', () {
      final vp = _viewport();
      final time = vp.candles[470].time!;
      final zoomed = vp.zoomedBy(2.0, _plot.center.dx);
      expect(zoomed.candleIndexAtX(zoomed.timeToX(time)), 470);
    });

    test('un horodatage garde sa bougie après déplacement', () {
      final vp = _viewport();
      final time = vp.candles[450].time!;
      final moved = vp.pannedByPixels(120);
      expect(moved.candleIndexAtX(moved.timeToX(time)), 450);
    });

    test('un prix garde son ordonnée relative après zoom', () {
      final vp = _viewport();
      // Un prix au milieu de la fenêtre reste au milieu si la fenêtre ne
      // change pas verticalement de façon inattendue.
      const price = 540.0;
      final before = vp.priceToY(price);
      expect(vp.yToPrice(before), closeTo(price, 0.001));
    });

    test('un redimensionnement ne déplace pas la fenêtre temporelle', () {
      final vp = _viewport();
      final time = vp.candles[460].time!;
      final resized = vp.withPlot(const Rect.fromLTWH(0, 0, 900, 500));
      expect(resized.startIndex, vp.startIndex);
      expect(resized.visibleCount, vp.visibleCount);
      expect(resized.candleIndexAtX(resized.timeToX(time)), 460);
    });
  });

  group('Conversions inverses', () {
    test('x → temps → x est stable', () {
      final vp = _viewport();
      for (final x in [10.0, 150.0, 300.0, 590.0]) {
        final time = vp.xToTime(x)!;
        expect(vp.timeToX(time), closeTo(x, 0.5));
      }
    });

    test('prix → y → prix est stable', () {
      final vp = _viewport();
      for (final price in [460.0, 500.0, 545.0]) {
        expect(vp.yToPrice(vp.priceToY(price)), closeTo(price, 0.001));
      }
    });

    test('un horodatage hors du jeu est prolongé, pas écrasé sur le bord', () {
      final vp = _viewport();
      final future = vp.candles.last.time!.add(const Duration(days: 5));
      // Une neckline projetée doit sortir de l'écran par la droite.
      expect(vp.timeToX(future), greaterThan(vp.timeToX(vp.candles.last.time!)));
      final past = vp.candles.first.time!.subtract(const Duration(days: 5));
      expect(vp.timeToX(past), lessThan(vp.timeToX(vp.candles.first.time!)));
    });
  });
}
