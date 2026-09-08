/// Le contrat de géométrie, de la charge utile au pixel.
///
/// Deux choses sont vérifiées ici, et ce sont les deux seules qui comptent
/// pour ce lot :
///
///  1. l'application lit la géométrie telle que le détecteur l'a écrite, sans
///     rien compléter — une figure sans géométrie reste non traçable ;
///  2. le tracé est une **fonction pure de la fenêtre**, donc il reste collé
///     aux bougies quand on déplace ou qu'on zoome.
///
/// La charge utile utilisée est celle que le backend a réellement produite
/// pour ETH 4 h le 8 septembre 2026, recopiée sans retouche.
library;

import 'dart:convert';

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/chart/candle_chart.dart';
import 'package:crypto_intelligence_app/chart/chart_layers.dart';
import 'package:crypto_intelligence_app/chart/chart_viewport.dart';
import 'package:crypto_intelligence_app/chart/pattern_geometry.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Le `double_top` réellement renvoyé par `/api/chart/ETH?timeframe=4h`.
const _realDoubleTop = '''
{
  "name": "double_top",
  "pattern_class": "DETERMINISTIC",
  "state": "CANDIDATE",
  "recognition_confidence": 66.3,
  "detected_at": "2026-09-08T16:00:00+00:00",
  "confirmation_time": "2026-09-07T20:00:00+00:00",
  "direction_if_textbook": "BEARISH",
  "invalidation_level": 2546.66,
  "edge_state": "NOT_YET_TESTED",
  "geometry": {
    "points": [
      {"time": "2026-09-04T08:00:00+00:00", "price": 2546.66,
       "role": "first_top", "kind": "pivot"},
      {"time": "2026-09-07T00:00:00+00:00", "price": 2536.64,
       "role": "second_top", "kind": "pivot"}
    ],
    "trend_lines": [
      {"start": {"time": "2026-09-04T08:00:00+00:00", "price": 2451.98,
                 "role": "neckline", "kind": "pivot"},
       "end": {"time": "2026-09-08T16:00:00+00:00", "price": 2451.98,
               "role": "neckline", "kind": "pivot"},
       "role": "neckline", "extend": true}
    ],
    "zones": [
      {"start_time": "2026-09-04T08:00:00+00:00",
       "end_time": "2026-09-08T16:00:00+00:00",
       "low": 2451.98, "high": 2546.66, "role": "breakout"}
    ],
    "neckline": {
      "start": {"time": "2026-09-04T08:00:00+00:00", "price": 2451.98,
                "role": "neckline", "kind": "pivot"},
      "end": {"time": "2026-09-08T16:00:00+00:00", "price": 2451.98,
              "role": "neckline", "kind": "pivot"},
      "role": "neckline", "extend": true
    },
    "breakout_area": {
      "start_time": "2026-09-04T08:00:00+00:00",
      "end_time": "2026-09-08T16:00:00+00:00",
      "low": 2451.98, "high": 2546.66, "role": "breakout"
    }
  },
  "bars_span": 16
}
''';

/// Le `bull_flag` réellement renvoyé par `/api/chart/SOL?timeframe=1d` :
/// détecté, mais sans aucune géométrie.
const _realBullFlag = '''
{
  "name": "bull_flag",
  "state": "CANDIDATE",
  "recognition_confidence": 55.0,
  "direction_if_textbook": "BULLISH",
  "invalidation_level": null,
  "edge_state": "NOT_YET_TESTED",
  "geometry": {"points": [], "trend_lines": [], "zones": [],
               "neckline": null, "breakout_area": null}
}
''';

StructuralPatternRead _pattern(String source) => StructuralPatternRead.fromJson(
    jsonDecode(source) as Map<String, dynamic>);

/// Des bougies 4 h qui couvrent la fenêtre de la figure.
///
/// Les deux barres portant les sommets reçoivent exactement le prix que le
/// détecteur a relevé : c'est ce qui permet de vérifier que le point dessiné
/// tombe sur la mèche, et pas quelque part à côté.
List<CandlePoint> _candles() {
  final start = DateTime.utc(2026, 9, 1, 16);
  const tops = {
    '2026-09-04 08:00:00.000Z': 2546.66,
    '2026-09-07 00:00:00.000Z': 2536.64,
  };
  return List.generate(43, (index) {
    final time = start.add(Duration(hours: 4 * index));
    final high = tops[time.toString()] ?? 2500.0;
    return CandlePoint(
      time: time,
      open: 2470,
      high: high,
      low: 2440,
      close: 2480,
      volume: 1000,
    );
  });
}

/// Un canevas qui note ce qu'on lui demande de peindre.
///
/// Le seul moyen de prouver qu'un point tombe au bon pixel sans prétendre
/// avoir regardé l'écran.
class _RecordingCanvas implements Canvas {
  final List<Offset> circles = [];
  final List<(Offset, Offset)> lines = [];
  final List<Rect> rects = [];
  final List<RRect> rRects = [];

  @override
  void drawCircle(Offset c, double radius, Paint paint) => circles.add(c);

  @override
  void drawLine(Offset p1, Offset p2, Paint paint) => lines.add((p1, p2));

  @override
  void drawRect(Rect rect, Paint paint) => rects.add(rect);

  @override
  void drawRRect(RRect rrect, Paint paint) => rRects.add(rrect);

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

const _size = Size(600, 400);
final _plot = Rect.fromLTRB(0, 0, 538, 300);

CandleChartPainter _painterFor(
  ChartViewport viewport,
  List<StructuralPatternRead> patterns, {
  ChartLayerSet? layers,
}) =>
    CandleChartPainter(
      viewport: viewport,
      layers: layers ?? ChartLayerSet.initial(),
      body: Rect.fromLTRB(0, 0, 538, 366),
      crosshair: null,
      timeframe: '4h',
      pair: 'ETHUSDT',
      source: 'Binance',
      patterns: patterns,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Lecture de la géométrie produite par le détecteur', () {
    test('les points, droites et aires arrivent tels quels', () {
      final pattern = _pattern(_realDoubleTop);

      expect(pattern.label, 'Double sommet');
      expect(pattern.stateLabel, 'CANDIDATE');
      expect(pattern.textbookLabel, 'baissière');
      expect(pattern.edgeLabel, 'jamais testée');
      expect(pattern.invalidationLevel, 2546.66);

      expect(pattern.geometry.points, hasLength(2));
      expect(pattern.geometry.points.first.role, 'first_top');
      expect(pattern.geometry.points.first.label, 'SOMMET 1');
      expect(pattern.geometry.points.first.price, 2546.66);
      expect(pattern.geometry.points.first.time,
          DateTime.utc(2026, 9, 4, 8));
      expect(pattern.geometry.points.last.label, 'SOMMET 2');
      expect(pattern.geometry.neckline, isNotNull);
      expect(pattern.geometry.neckline!.extend, isTrue);
      expect(pattern.geometry.breakoutArea!.role, 'breakout');
    });

    test('la neckline et la zone de cassure ne sont pas dessinées deux fois',
        () {
      final geometry = _pattern(_realDoubleTop).geometry;
      // Le backend les publie à deux endroits : dans les listes ET dans leur
      // champ dédié. Les tracer deux fois les épaissirait sans rien ajouter.
      expect(geometry.lines, hasLength(1));
      expect(geometry.neckline, isNotNull);
      expect(geometry.drawableLines, hasLength(1));
      expect(geometry.zones, hasLength(1));
      expect(geometry.breakoutArea, isNotNull);
      expect(geometry.drawableZones, hasLength(1));
    });

    test('une figure sans géométrie n’est pas traçable', () {
      final pattern = _pattern(_realBullFlag);
      expect(pattern.label, 'Drapeau haussier');
      expect(pattern.geometry.isEmpty, isTrue);
      expect(pattern.isDrawable, isFalse);
    });

    test('un rôle inconnu ne devient pas une étiquette bricolée', () {
      final point = GeometryPoint.maybe(
        {'time': '2026-09-04T08:00:00+00:00', 'price': 10.0, 'role': 'xyz'},
      );
      expect(point, isNotNull);
      expect(point!.label, isEmpty);
    });

    test('un point sans prix ou sans date est rejeté, pas complété', () {
      expect(GeometryPoint.maybe({'price': 10.0}), isNull);
      expect(GeometryPoint.maybe({'time': '2026-09-04T08:00:00+00:00'}), isNull);
      expect(GeometryZone.maybe({'low': 1.0, 'high': 2.0}), isNull);
    });

    test('ChartRead lit la clé structural_patterns du backend', () {
      final read = ChartRead.fromJson({
        'asset': 'ETH',
        'candles': const <dynamic>[],
        'structural_patterns': [jsonDecode(_realDoubleTop)],
      });
      expect(read.structuralPatterns, hasLength(1));
      expect(read.structuralPatterns.single.name, 'double_top');
      expect(read.structuralPatterns.single.isDrawable, isTrue);
    });
  });

  group('Le tracé reste accroché aux bougies', () {
    final candles = _candles();
    final pattern = _pattern(_realDoubleTop);

    /// Ce que le peintre a réellement dessiné pour cette fenêtre.
    _RecordingCanvas paint(ChartViewport viewport) {
      final canvas = _RecordingCanvas();
      _painterFor(viewport, [pattern]).paint(canvas, _size);
      return canvas;
    }

    /// Le cercle le plus proche de la position attendue pour un sommet.
    Offset? circleNear(_RecordingCanvas canvas, Offset expected) {
      for (final circle in canvas.circles) {
        if ((circle - expected).distance < 0.01) return circle;
      }
      return null;
    }

    test('chaque sommet est peint à la position que donne la fenêtre', () {
      final viewport =
          ChartViewport.initial(candles: candles, plot: _plot);
      final canvas = paint(viewport);

      for (final point in pattern.geometry.points) {
        final expected = Offset(
          viewport.timeToX(point.time),
          viewport.priceToY(point.price),
        );
        expect(circleNear(canvas, expected), isNotNull,
            reason: '${point.role} n’est pas peint là où la fenêtre le place');
      }
    });

    test('le sommet tombe sur la mèche de sa propre bougie', () {
      final viewport =
          ChartViewport.initial(candles: candles, plot: _plot);
      final top = pattern.geometry.points.first;
      final bar = candles.firstWhere((c) => c.time == top.time);
      // Même instant, même prix : le point doit se superposer au haut de la
      // mèche. C'est la vraie preuve d'accrochage — un placement par index
      // aurait glissé d'une barre ou plus.
      expect(viewport.priceToY(top.price), viewport.priceToY(bar.high));
      expect(viewport.timeToX(top.time),
          viewport.timeToX(bar.time!));
    });

    test('après un déplacement, le tracé suit ses bougies', () {
      // La vue 4 h / 7 j tient en 43 bougies, donc elle est entière à
      // l'ouverture et il n'y a rien à déplacer. On zoome d'abord, comme le
      // ferait un lecteur, puis on glisse.
      final start = ChartViewport.initial(candles: candles, plot: _plot)
          .zoomedBy(2.5, _plot.width / 2);
      final moved = start.pannedByPixels(-90);
      expect(moved.startIndex, isNot(start.startIndex),
          reason: 'le déplacement doit vraiment changer la fenêtre');

      final canvas = paint(moved);
      for (final point in pattern.geometry.points) {
        final bar = candles.firstWhere((c) => c.time == point.time);
        final expected = Offset(
          moved.timeToX(bar.time!),
          moved.priceToY(bar.high),
        );
        expect(circleNear(canvas, expected), isNotNull,
            reason: '${point.role} a décroché de sa bougie après un pan');
      }
    });

    test('après un zoom, le tracé suit ses bougies', () {
      final start = ChartViewport.initial(candles: candles, plot: _plot);
      final zoomed = start.zoomedBy(2.2, _plot.width / 2);
      expect(zoomed.visibleCount, lessThan(start.visibleCount));

      final canvas = paint(zoomed);
      var seen = 0;
      for (final point in pattern.geometry.points) {
        final bar = candles.firstWhere((c) => c.time == point.time);
        final expected = Offset(
          zoomed.timeToX(bar.time!),
          zoomed.priceToY(bar.high),
        );
        if (expected.dx < _plot.left || expected.dx > _plot.right) continue;
        expect(circleNear(canvas, expected), isNotNull,
            reason: '${point.role} a décroché de sa bougie après un zoom');
        seen++;
      }
      expect(seen, greaterThan(0),
          reason: 'le zoom a tout sorti du cadre, le test ne prouve rien');
    });

    test('la neckline prolongée atteint le bord droit du cadre', () {
      final viewport =
          ChartViewport.initial(candles: candles, plot: _plot);
      final canvas = paint(viewport);
      final neck = pattern.geometry.neckline!;
      final y = viewport.priceToY(neck.start.price);
      // Horizontale, donc `extend` la pousse jusqu'au bord sans changer de
      // hauteur.
      final onNeckline = canvas.lines
          .where((line) =>
              (line.$1.dy - y).abs() < 0.01 && (line.$2.dy - y).abs() < 0.01)
          .toList();
      expect(onNeckline, isNotEmpty, reason: 'la neckline n’est pas tracée');
      final rightmost = onNeckline
          .map((line) => line.$2.dx)
          .reduce((a, b) => a > b ? a : b);
      expect(rightmost, closeTo(_plot.right, 9.0),
          reason: 'la droite prolongée s’arrête avant le bord');
    });
  });

  group('Ce que le graphique refuse de faire', () {
    final candles = _candles();

    test('calque « Figures » décoché : plus rien n’est tracé', () {
      final viewport =
          ChartViewport.initial(candles: candles, plot: _plot);
      final canvas = _RecordingCanvas();
      _painterFor(
        viewport,
        [_pattern(_realDoubleTop)],
        layers: ChartLayerSet.initial().toggled(ChartLayer.patternGeometry),
      ).paint(canvas, _size);
      // Le prix courant dessine un cercle ? non : il trace une ligne. Aucun
      // cercle ne doit rester.
      expect(canvas.circles, isEmpty);
    });

    test('une figure non traçable est annoncée, pas dessinée', () {
      final viewport =
          ChartViewport.initial(candles: candles, plot: _plot);
      final canvas = _RecordingCanvas();
      _painterFor(viewport, [_pattern(_realBullFlag)]).paint(canvas, _size);
      expect(canvas.circles, isEmpty,
          reason: 'rien ne doit être inventé pour une géométrie absente');
      // L'étiquette existe pour que le lecteur ne cherche pas sur le
      // graphique une figure que la fiche en dessous annonce.
      expect(canvas.rRects, isNotEmpty);
    });

    test('deux étiquettes ne se superposent jamais', () {
      final viewport =
          ChartViewport.initial(candles: candles, plot: _plot);
      final canvas = _RecordingCanvas();
      _painterFor(viewport, [_pattern(_realDoubleTop)]).paint(canvas, _size);
      final tags = canvas.rRects.map((r) => r.outerRect).toList();
      for (var i = 0; i < tags.length; i++) {
        for (var j = i + 1; j < tags.length; j++) {
          expect(tags[i].overlaps(tags[j]), isFalse,
              reason: 'les étiquettes ${tags[i]} et ${tags[j]} se recouvrent');
        }
      }
    });
  });
}
