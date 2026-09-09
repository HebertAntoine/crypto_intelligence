/// Tracé des seules figures dont la géométrie peut être vérifiée sur les
/// bougies affichées.
///
/// Ce fichier ne contient aucun détecteur. Il ne déduit pas une figure de son
/// nom et ne fabrique aucun sommet manquant : il valide puis place les points,
/// droites et zones temps/prix fournis par le backend. Une figure incomplète,
/// inconnue ou extérieure aux bougies est simplement absente du tracé.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../chart/pattern_geometry.dart';

/// Noms produits par les détecteurs qui publient aujourd'hui un contrat de
/// géométrie complet.
const drawablePatternNames = <String>{
  'double_top',
  'double_bottom',
  'triple_top',
  'triple_bottom',
  'head_and_shoulders',
  'inverse_head_and_shoulders',
  'ascending_triangle',
  'descending_triangle',
  'symmetrical_triangle',
  'rising_wedge',
  'falling_wedge',
  'bull_flag',
  'bear_flag',
};

/// Couleur stable par figure, indépendante du score et de l'état courant.
///
/// Deux figures simultanées restent ainsi identifiables. Ces couleurs ne sont
/// pas un signal d'achat ou de vente : leur seul rôle est l'identification.
Color realPatternColor(String name) => switch (name) {
      'double_top' => const Color(0xFFFF6175),
      'double_bottom' => const Color(0xFF31DFA3),
      'triple_top' => const Color(0xFFFF8C5A),
      'triple_bottom' => const Color(0xFF21D6CA),
      'head_and_shoulders' => const Color(0xFFFF63D8),
      'inverse_head_and_shoulders' => const Color(0xFF8A7DFF),
      'ascending_triangle' => const Color(0xFF47D7FF),
      'descending_triangle' => const Color(0xFFFFC34D),
      'symmetrical_triangle' => const Color(0xFFB083FF),
      'rising_wedge' => const Color(0xFFFFA64D),
      'falling_wedge' => const Color(0xFF5BBEFF),
      'bull_flag' => const Color(0xFF42E6A4),
      'bear_flag' => const Color(0xFFFF5C70),
      _ => const Color(0xFF9BACBF),
    };

/// Libellé français d'un rôle d'ancre.
///
/// Les pivots de triangles et de biseaux sont volontairement numérotés par
/// le peintre : leur rôle JSON est commun (`upper_pivot`/`lower_pivot`).
String realPatternPointLabel(GeometryPoint point) => switch (point.role) {
      'first_top' => 'SOMMET 1',
      'second_top' => 'SOMMET 2',
      'third_top' => 'SOMMET 3',
      'first_bottom' => 'CREUX 1',
      'second_bottom' => 'CREUX 2',
      'third_bottom' => 'CREUX 3',
      'head' => 'TÊTE',
      'left_shoulder' => 'ÉPAULE G.',
      'right_shoulder' => 'ÉPAULE D.',
      'pole_start' => 'DÉPART DU MÂT',
      'pole_end' => 'FIN DU MÂT',
      'upper_pivot' => 'SOMMET',
      'lower_pivot' => 'CREUX',
      _ => '',
    };

String realPatternLineLabel(GeometryLine line) => switch (line.role) {
      'neckline' => 'NECKLINE',
      'upper' => 'BORNE HAUTE',
      'lower' => 'BORNE BASSE',
      'pole' => 'MÂT',
      _ => '',
    };

String realPatternStateLabel(String state) => switch (state) {
      'CANDIDATE' => 'CANDIDATE',
      'FORMING' => 'EN FORMATION',
      'CONFIRMED' => 'CONFIRMÉE',
      'FAILED' => 'INVALIDÉE',
      'INVALIDATED' => 'INVALIDÉE',
      'EXPIRED' => 'EXPIRÉE',
      _ => state,
    };

/// Une figure validée avec les seuls pivots qu'il est légitime de relier.
@immutable
class VerifiedPatternGeometry {
  final StructuralPatternRead pattern;

  /// Pour doubles, triples et ETE : les pivots publiés, dans l'ordre du
  /// temps. Aucun creux ou sommet intermédiaire n'est ajouté par l'app.
  final List<GeometryPoint> skeleton;

  const VerifiedPatternGeometry({
    required this.pattern,
    required this.skeleton,
  });

  Color get color => realPatternColor(pattern.name);

  DateTime get endTime {
    final candidates = <DateTime>[
      if (pattern.spanEnd != null) pattern.spanEnd!,
      if (pattern.detectedAt != null) pattern.detectedAt!,
      ...pattern.geometry.points.map((point) => point.time),
      ...pattern.geometry.drawableLines.map((line) => line.end.time),
      ...pattern.geometry.drawableZones.map((zone) => zone.endTime),
    ];
    return candidates
        .reduce((left, right) => left.isAfter(right) ? left : right);
  }
}

/// Valide le contrat propre à chaque famille contre les bougies affichées.
///
/// En plus de la présence des rôles, les timestamps doivent correspondre
/// exactement à des bougies. Les pivots/points de clôture doivent aussi
/// correspondre au prix observé sur cette bougie. Les points `projected` des
/// droites de régression ne prétendent pas être un OHLC : leur date et leur
/// prix fini suffisent.
VerifiedPatternGeometry? verifyRealPatternGeometry(
  StructuralPatternRead pattern,
  List<CandlePoint> candles,
) {
  if (!drawablePatternNames.contains(pattern.name) || candles.isEmpty) {
    return null;
  }

  final lookup = _CandleLookup(candles);
  final geometry = pattern.geometry;
  if (geometry.isEmpty ||
      !geometry.points.every((point) => lookup.verifies(point, pattern)) ||
      !geometry.drawableLines.every(lookup.verifiesLine) ||
      !geometry.drawableZones.every(lookup.verifiesZone)) {
    return null;
  }

  final points = geometry.points;
  final roles = points.map((point) => point.role).toSet();
  final lineRoles = geometry.drawableLines.map((line) => line.role).toSet();
  final zoneRoles = geometry.drawableZones.map((zone) => zone.role).toSet();

  bool hasRoles(Iterable<String> required) => required.every(roles.contains);

  bool valid;
  List<GeometryPoint> skeleton = const [];
  switch (pattern.name) {
    case 'double_top':
      valid = hasRoles(const ['first_top', 'second_top']) &&
          lineRoles.contains('neckline') &&
          zoneRoles.contains('breakout');
      skeleton = _inTimeOrder(points.where(
          (point) => point.role == 'first_top' || point.role == 'second_top'));
    case 'double_bottom':
      valid = hasRoles(const ['first_bottom', 'second_bottom']) &&
          lineRoles.contains('neckline') &&
          zoneRoles.contains('breakout');
      skeleton = _inTimeOrder(points.where((point) =>
          point.role == 'first_bottom' || point.role == 'second_bottom'));
    case 'triple_top':
      valid = hasRoles(const ['first_top', 'second_top', 'third_top']) &&
          lineRoles.contains('neckline') &&
          zoneRoles.contains('breakout');
      skeleton = _inTimeOrder(points.where((point) =>
          point.role == 'first_top' ||
          point.role == 'second_top' ||
          point.role == 'third_top'));
    case 'triple_bottom':
      valid =
          hasRoles(const ['first_bottom', 'second_bottom', 'third_bottom']) &&
              lineRoles.contains('neckline') &&
              zoneRoles.contains('breakout');
      skeleton = _inTimeOrder(points.where((point) =>
          point.role == 'first_bottom' ||
          point.role == 'second_bottom' ||
          point.role == 'third_bottom'));
    case 'head_and_shoulders':
    case 'inverse_head_and_shoulders':
      valid = hasRoles(const ['left_shoulder', 'head', 'right_shoulder']) &&
          lineRoles.contains('neckline') &&
          zoneRoles.contains('breakout');
      skeleton = _inTimeOrder(points.where((point) =>
          point.role == 'left_shoulder' ||
          point.role == 'head' ||
          point.role == 'right_shoulder'));
    case 'ascending_triangle':
    case 'descending_triangle':
    case 'symmetrical_triangle':
      valid = _countRole(points, 'upper_pivot') >= 3 &&
          _countRole(points, 'lower_pivot') >= 3 &&
          lineRoles.contains('upper') &&
          lineRoles.contains('lower') &&
          zoneRoles.contains('breakout');
    case 'rising_wedge':
    case 'falling_wedge':
      valid = _countRole(points, 'upper_pivot') >= 3 &&
          _countRole(points, 'lower_pivot') >= 3 &&
          lineRoles.contains('upper') &&
          lineRoles.contains('lower');
    case 'bull_flag':
    case 'bear_flag':
      valid = hasRoles(const ['pole_start', 'pole_end']) &&
          lineRoles.contains('pole') &&
          zoneRoles.contains('consolidation');
    default:
      valid = false;
  }

  if (!valid) return null;
  return VerifiedPatternGeometry(pattern: pattern, skeleton: skeleton);
}

/// Figures réellement traçables, les plus récentes conservées quand la vue
/// serait illisible. Le tri est stable et indépendant de la confiance.
List<VerifiedPatternGeometry> verifiedRealPatterns(
  ChartRead chart, {
  List<CandlePoint>? candles,
  int maximum = 8,
}) {
  if (maximum <= 0) return const [];
  final plottedCandles = candles ?? chart.candles;
  final verified = chart.structuralPatterns
      .map((pattern) => verifyRealPatternGeometry(pattern, plottedCandles))
      .whereType<VerifiedPatternGeometry>()
      .toList()
    ..sort((left, right) => left.endTime.compareTo(right.endTime));
  if (verified.length <= maximum) return verified;
  return verified.sublist(verified.length - maximum);
}

/// Overlay empilable sur le panneau de prix d'un graphique.
///
/// [priceMinimum], [priceMaximum], [horizontalPadding] et [verticalPadding]
/// doivent être les mêmes que ceux du peintre des bougies. Le widget garde
/// ainsi une responsabilité unique : convertir la géométrie validée avec
/// l'échelle que le graphique utilise déjà.
class RealPatternOverlay extends StatelessWidget {
  final ChartRead chart;

  /// Les bougies réellement peintes. Peut différer de `chart.candles` quand
  /// l'écran superpose les figures du backend à la série Binance paginée.
  final List<CandlePoint>? candles;
  final double priceMinimum;
  final double priceMaximum;
  final double horizontalPadding;
  final double verticalPadding;
  final int maximumPatterns;
  final bool showLabels;
  final bool showZones;

  const RealPatternOverlay({
    super.key,
    required this.chart,
    this.candles,
    required this.priceMinimum,
    required this.priceMaximum,
    this.horizontalPadding = 14,
    this.verticalPadding = 12,
    this.maximumPatterns = 8,
    this.showLabels = true,
    this.showZones = true,
  });

  @override
  Widget build(BuildContext context) {
    final plottedCandles = candles ?? chart.candles;
    final patterns = verifiedRealPatterns(
      chart,
      candles: plottedCandles,
      maximum: maximumPatterns,
    );
    return IgnorePointer(
      child: CustomPaint(
        key: const Key('real-pattern-overlay'),
        painter: RealPatternPainter(
          candles: plottedCandles,
          patterns: patterns,
          priceMinimum: priceMinimum,
          priceMaximum: priceMaximum,
          horizontalPadding: horizontalPadding,
          verticalPadding: verticalPadding,
          showLabels: showLabels,
          showZones: showZones,
        ),
        size: Size.infinite,
      ),
    );
  }
}

/// Peintre public pour que l'accrochage aux bougies puisse être testé sans
/// capture d'écran.
class RealPatternPainter extends CustomPainter {
  final List<CandlePoint> candles;
  final List<VerifiedPatternGeometry> patterns;
  final double priceMinimum;
  final double priceMaximum;
  final double horizontalPadding;
  final double verticalPadding;
  final bool showLabels;
  final bool showZones;

  const RealPatternPainter({
    required this.candles,
    required this.patterns,
    required this.priceMinimum,
    required this.priceMaximum,
    required this.horizontalPadding,
    required this.verticalPadding,
    required this.showLabels,
    required this.showZones,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty ||
        patterns.isEmpty ||
        !priceMinimum.isFinite ||
        !priceMaximum.isFinite ||
        priceMaximum <= priceMinimum ||
        size.isEmpty) {
      return;
    }

    final scale = _PatternScale(
      candles: candles,
      size: size,
      minimum: priceMinimum,
      maximum: priceMaximum,
      horizontalPadding: horizontalPadding,
      verticalPadding: verticalPadding,
    );
    final labels = _LabelRegistry(size);

    canvas.save();
    canvas.clipRect(Offset.zero & size);
    for (final verified in patterns) {
      final pattern = verified.pattern;
      final color = verified.color;
      if (showZones) {
        for (final zone in pattern.geometry.drawableZones) {
          _paintZone(canvas, scale, zone, color);
        }
      }
      for (final line in pattern.geometry.drawableLines) {
        _paintLine(canvas, scale, line, color, pattern.state);
      }
      _paintSkeleton(canvas, scale, verified, color);
      for (final point in pattern.geometry.points) {
        _paintPoint(canvas, scale, point, color);
      }
      if (showLabels) {
        _paintLabels(canvas, scale, labels, verified, color);
      }
    }
    canvas.restore();
  }

  void _paintZone(
    Canvas canvas,
    _PatternScale scale,
    GeometryZone zone,
    Color color,
  ) {
    final left = scale.x(zone.startTime);
    final right = scale.x(zone.endTime);
    final top = scale.y(zone.high);
    final bottom = scale.y(zone.low);
    final rect = Rect.fromLTRB(
      math.min(left, right),
      math.min(top, bottom),
      math.max(left, right),
      math.max(top, bottom),
    );
    if (rect.width <= 0 || rect.height <= 0) return;

    // Une zone sémantique n'est pas la « boîte de la figure ». Le remplissage
    // est léger et seules ses deux bornes de prix sont soulignées : aucun
    // rectangle générique n'est dessiné autour des pivots.
    canvas.drawRect(rect, Paint()..color = color.withValues(alpha: .055));
    final boundary = Paint()
      ..color = color.withValues(alpha: .42)
      ..strokeWidth = 1;
    _dashedLine(canvas, Offset(rect.left, rect.top),
        Offset(rect.right, rect.top), boundary);
    _dashedLine(canvas, Offset(rect.left, rect.bottom),
        Offset(rect.right, rect.bottom), boundary);
  }

  void _paintLine(
    Canvas canvas,
    _PatternScale scale,
    GeometryLine line,
    Color color,
    String state,
  ) {
    final start = Offset(scale.x(line.start.time), scale.y(line.start.price));
    var end = Offset(scale.x(line.end.time), scale.y(line.end.price));
    if (line.extend && end.dx > start.dx) {
      final slope = (end.dy - start.dy) / (end.dx - start.dx);
      end = Offset(
          scale.size.width, end.dy + slope * (scale.size.width - end.dx));
    }

    final opacity = state == 'FAILED' || state == 'INVALIDATED' ? .55 : .94;
    final paint = Paint()
      ..color = color.withValues(alpha: opacity)
      ..strokeWidth = line.role == 'pole' ? 2.6 : 1.8
      ..strokeCap = StrokeCap.round;
    if (line.role == 'neckline') {
      _dashedLine(canvas, start, end, paint, dash: 6, gap: 4);
    } else {
      canvas.drawLine(start, end, paint);
    }
  }

  void _paintSkeleton(
    Canvas canvas,
    _PatternScale scale,
    VerifiedPatternGeometry geometry,
    Color color,
  ) {
    if (geometry.skeleton.length < 2) return;
    final path = Path();
    for (var index = 0; index < geometry.skeleton.length; index += 1) {
      final point = geometry.skeleton[index];
      final at = Offset(scale.x(point.time), scale.y(point.price));
      if (index == 0) {
        path.moveTo(at.dx, at.dy);
      } else {
        path.lineTo(at.dx, at.dy);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = color.withValues(alpha: .72)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5
        ..strokeJoin = StrokeJoin.round,
    );
  }

  void _paintPoint(
    Canvas canvas,
    _PatternScale scale,
    GeometryPoint point,
    Color color,
  ) {
    final at = Offset(scale.x(point.time), scale.y(point.price));
    canvas.drawCircle(at, 4.2, Paint()..color = const Color(0xFF061426));
    canvas.drawCircle(
      at,
      4.2,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.9,
    );
  }

  void _paintLabels(
    Canvas canvas,
    _PatternScale scale,
    _LabelRegistry labels,
    VerifiedPatternGeometry geometry,
    Color color,
  ) {
    final pattern = geometry.pattern;
    final points = pattern.geometry.points;
    if (points.isEmpty) return;
    final xs = points.map((point) => scale.x(point.time)).toList();
    final ys = points.map((point) => scale.y(point.price)).toList();
    final centerX = (xs.reduce(math.min) + xs.reduce(math.max)) / 2;
    final topY = ys.reduce(math.min);
    labels.paint(
      canvas,
      '${pattern.label.toUpperCase()} · '
      '${realPatternStateLabel(pattern.state)}',
      Offset(centerX, topY - 25),
      color,
      centered: true,
      priority: true,
    );

    // Les labels de pivots sont utiles pour ETE/doubles/triples. Sur huit
    // pivots de triangle, répéter « sommet/creux » masquerait les bougies :
    // les deux vraies bornes nommées suffisent à rendre la forme lisible.
    final labelPivots =
        !pattern.name.contains('triangle') && !pattern.name.contains('wedge');
    if (labelPivots) {
      for (final point in points) {
        final label = realPatternPointLabel(point);
        if (label.isEmpty) continue;
        labels.paint(
          canvas,
          label,
          Offset(scale.x(point.time), scale.y(point.price) - 18),
          color,
          centered: true,
        );
      }
    }

    for (final line in pattern.geometry.drawableLines) {
      final label = realPatternLineLabel(line);
      if (label.isEmpty || line.role == 'pole') continue;
      labels.paint(
        canvas,
        label,
        Offset(scale.x(line.end.time), scale.y(line.end.price) + 4),
        color,
      );
    }
  }

  @override
  bool shouldRepaint(covariant RealPatternPainter oldDelegate) =>
      !identical(oldDelegate.candles, candles) ||
      !identical(oldDelegate.patterns, patterns) ||
      oldDelegate.priceMinimum != priceMinimum ||
      oldDelegate.priceMaximum != priceMaximum ||
      oldDelegate.horizontalPadding != horizontalPadding ||
      oldDelegate.verticalPadding != verticalPadding ||
      oldDelegate.showLabels != showLabels ||
      oldDelegate.showZones != showZones;
}

class _CandleLookup {
  final Map<int, CandlePoint> _byTime;

  _CandleLookup(List<CandlePoint> candles)
      : _byTime = {
          for (final candle in candles)
            if (candle.time != null)
              candle.time!.toUtc().millisecondsSinceEpoch: candle,
        };

  bool verifies(GeometryPoint point, StructuralPatternRead pattern) {
    if (!point.price.isFinite || point.price <= 0) return false;
    final candle = _byTime[point.time.toUtc().millisecondsSinceEpoch];
    if (candle == null) return false;
    if (point.kind == 'projected') return true;

    final expected = switch (point.kind) {
      'close' => candle.close,
      _ => _pivotPrice(candle, point.role, pattern.name),
    };
    if (expected == null) return false;
    return _samePrice(point.price, expected);
  }

  bool verifiesLine(GeometryLine line) =>
      _validEndpoint(line.start) && _validEndpoint(line.end);

  bool verifiesZone(GeometryZone zone) =>
      _hasTime(zone.startTime) &&
      _hasTime(zone.endTime) &&
      zone.low.isFinite &&
      zone.high.isFinite &&
      zone.low > 0 &&
      zone.high >= zone.low;

  bool _validEndpoint(GeometryPoint point) =>
      _hasTime(point.time) && point.price.isFinite && point.price > 0;

  bool _hasTime(DateTime time) =>
      _byTime.containsKey(time.toUtc().millisecondsSinceEpoch);

  static double? _pivotPrice(
    CandlePoint candle,
    String role,
    String patternName,
  ) {
    if (role.contains('top') || role == 'upper_pivot') return candle.high;
    if (role.contains('bottom') || role == 'lower_pivot') return candle.low;
    if (role == 'head' || role.contains('shoulder')) {
      return patternName == 'inverse_head_and_shoulders'
          ? candle.low
          : candle.high;
    }
    return null;
  }

  static bool _samePrice(double left, double right) {
    final tolerance = math.max(1e-6, math.max(left.abs(), right.abs()) * 1e-8);
    return (left - right).abs() <= tolerance;
  }
}

class _PatternScale {
  final List<CandlePoint> candles;
  final Size size;
  final double minimum;
  final double maximum;
  final double horizontalPadding;
  final double verticalPadding;
  late final Map<int, int> _indexes = {
    for (var index = 0; index < candles.length; index += 1)
      if (candles[index].time != null)
        candles[index].time!.toUtc().millisecondsSinceEpoch: index,
  };

  _PatternScale({
    required this.candles,
    required this.size,
    required this.minimum,
    required this.maximum,
    required this.horizontalPadding,
    required this.verticalPadding,
  });

  double x(DateTime time) {
    final index = _indexes[time.toUtc().millisecondsSinceEpoch];
    assert(index != null, 'La validation doit précéder le tracé.');
    final width = math.max(1.0, size.width - horizontalPadding * 2);
    final stride = width / candles.length;
    return horizontalPadding + stride * (index! + .5);
  }

  double y(double price) {
    final drawable = math.max(1.0, size.height - verticalPadding * 2);
    final ratio = ((price - minimum) / (maximum - minimum)).clamp(0.0, 1.0);
    return size.height - verticalPadding - drawable * ratio;
  }
}

class _LabelRegistry {
  final Size size;
  final List<Rect> _occupied = [];

  _LabelRegistry(this.size);

  void paint(
    Canvas canvas,
    String value,
    Offset anchor,
    Color color, {
    bool centered = false,
    bool priority = false,
  }) {
    final painter = TextPainter(
      text: TextSpan(
        text: value,
        style: TextStyle(
          color: color,
          fontSize: priority ? 10.5 : 9,
          fontWeight: FontWeight.w800,
          height: 1,
        ),
      ),
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )..layout(maxWidth: math.min(210, size.width - 8));

    final desiredLeft = centered ? anchor.dx - painter.width / 2 : anchor.dx;
    final base = Rect.fromLTWH(
      desiredLeft - 4,
      anchor.dy - 2,
      painter.width + 8,
      painter.height + 4,
    );
    final slot = _findSlot(base, priority: priority);
    if (slot == null) return;
    canvas.drawRRect(
      RRect.fromRectAndRadius(slot, const Radius.circular(3)),
      Paint()..color = const Color(0xFF061426).withValues(alpha: .84),
    );
    painter.paint(canvas, Offset(slot.left + 4, slot.top + 2));
    _occupied.add(slot);
  }

  Rect? _findSlot(Rect wanted, {required bool priority}) {
    final attempts = priority ? 12 : 7;
    for (var index = 0; index < attempts; index += 1) {
      final offset =
          index == 0 ? 0.0 : (index.isOdd ? 1 : -1) * 14.0 * ((index + 1) ~/ 2);
      var candidate = wanted.shift(Offset(0, offset));
      candidate = candidate.shift(Offset(
        candidate.left < 2
            ? 2 - candidate.left
            : candidate.right > size.width - 2
                ? size.width - 2 - candidate.right
                : 0,
        0,
      ));
      if (candidate.top < 2 || candidate.bottom > size.height - 2) continue;
      if (_occupied.any(candidate.overlaps)) continue;
      return candidate;
    }
    return null;
  }
}

List<GeometryPoint> _inTimeOrder(Iterable<GeometryPoint> source) {
  final result = source.toList()
    ..sort((left, right) => left.time.compareTo(right.time));
  return result;
}

int _countRole(List<GeometryPoint> points, String role) =>
    points.where((point) => point.role == role).length;

void _dashedLine(
  Canvas canvas,
  Offset start,
  Offset end,
  Paint paint, {
  double dash = 5,
  double gap = 4,
}) {
  final distance = (end - start).distance;
  if (distance <= 0) return;
  final direction = (end - start) / distance;
  for (var traveled = 0.0; traveled < distance; traveled += dash + gap) {
    final until = math.min(traveled + dash, distance);
    canvas.drawLine(
      start + direction * traveled,
      start + direction * until,
      paint,
    );
  }
}
