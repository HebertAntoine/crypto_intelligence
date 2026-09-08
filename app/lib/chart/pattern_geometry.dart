/// La géométrie d'une figure, telle que le détecteur l'a produite.
///
/// Contrat entre le backend et le graphique : le backend détecte et fournit
/// des coordonnées **temps + prix**, le graphique les place. L'application ne
/// redétecte rien et ne complète rien — une figure sans géométrie n'est pas
/// dessinée, elle est absente.
///
/// C'est ce qui empêche le dessin et l'analyse de diverger : il n'existe qu'un
/// seul endroit où une figure est reconnue.
library;

import 'package:flutter/foundation.dart';

double? _double(dynamic value) => (value as num?)?.toDouble();
String _string(dynamic value, [String fallback = '']) =>
    value as String? ?? fallback;

/// Un point nommé de la figure : un sommet, un creux, une épaule.
@immutable
class GeometryPoint {
  final DateTime time;
  final double price;

  /// « first_top », « head », « left_shoulder »… tel que le détecteur l'a
  /// nommé. Le libellé affiché en dérive, la donnée reste celle du moteur.
  final String role;
  final String kind;

  const GeometryPoint({
    required this.time,
    required this.price,
    this.role = '',
    this.kind = 'pivot',
  });

  static GeometryPoint? maybe(dynamic value) {
    if (value is! Map) return null;
    final time = DateTime.tryParse('${value['time'] ?? ''}');
    final price = _double(value['price']);
    if (time == null || price == null) return null;
    return GeometryPoint(
      time: time.toUtc(),
      price: price,
      role: _string(value['role']),
      kind: _string(value['kind'], 'pivot'),
    );
  }

  /// Le rôle en français, pour l'étiquette. Un rôle inconnu n'est pas traduit
  /// à la volée : il reste vide plutôt que d'afficher un identifiant.
  String get label => switch (role) {
        'first_top' => 'SOMMET 1',
        'second_top' => 'SOMMET 2',
        'third_top' => 'SOMMET 3',
        'first_bottom' => 'CREUX 1',
        'second_bottom' => 'CREUX 2',
        'third_bottom' => 'CREUX 3',
        'head' => 'TÊTE',
        'left_shoulder' => 'ÉPAULE G.',
        'right_shoulder' => 'ÉPAULE D.',
        'valley' => 'VALLÉE',
        'peak' => 'SOMMET',
        _ => '',
      };
}

/// Un segment entre deux points, éventuellement prolongé vers la droite.
@immutable
class GeometryLine {
  final GeometryPoint start;
  final GeometryPoint end;
  final String role;

  /// Vrai quand la droite garde un sens au-delà du dernier point : les
  /// bornes d'un triangle, oui ; une neckline tracée entre deux sommets
  /// achevés, non.
  final bool extend;

  const GeometryLine({
    required this.start,
    required this.end,
    this.role = '',
    this.extend = false,
  });

  static GeometryLine? maybe(dynamic value) {
    if (value is! Map) return null;
    final start = GeometryPoint.maybe(value['start']);
    final end = GeometryPoint.maybe(value['end']);
    if (start == null || end == null) return null;
    return GeometryLine(
      start: start,
      end: end,
      role: _string(value['role']),
      extend: value['extend'] as bool? ?? false,
    );
  }

  String get label => switch (role) {
        'neckline' => 'NECKLINE',
        'upper' => 'BORNE HAUTE',
        'lower' => 'BORNE BASSE',
        'pole' => 'MÂT',
        _ => '',
      };

  bool sameAs(GeometryLine other) =>
      other.role == role &&
      other.start.time == start.time &&
      other.start.price == start.price &&
      other.end.time == end.time &&
      other.end.price == end.price;
}

/// Une aire rectangulaire : une bande de cassure, une zone d'invalidation.
@immutable
class GeometryZone {
  final DateTime startTime;
  final DateTime endTime;
  final double low;
  final double high;
  final String role;

  const GeometryZone({
    required this.startTime,
    required this.endTime,
    required this.low,
    required this.high,
    this.role = '',
  });

  static GeometryZone? maybe(dynamic value) {
    if (value is! Map) return null;
    final start = DateTime.tryParse('${value['start_time'] ?? ''}');
    final end = DateTime.tryParse('${value['end_time'] ?? ''}');
    final low = _double(value['low']);
    final high = _double(value['high']);
    if (start == null || end == null || low == null || high == null) return null;
    return GeometryZone(
      startTime: start.toUtc(),
      endTime: end.toUtc(),
      low: low,
      high: high,
      role: _string(value['role']),
    );
  }

  String get label => switch (role) {
        'breakout' => 'ZONE DE CASSURE',
        'invalidation' => 'INVALIDATION',
        'target' => 'OBJECTIF',
        _ => '',
      };

  bool sameAs(GeometryZone other) =>
      other.role == role &&
      other.startTime == startTime &&
      other.endTime == endTime &&
      other.low == low &&
      other.high == high;
}

@immutable
class PatternGeometry {
  final List<GeometryPoint> points;
  final List<GeometryLine> lines;
  final List<GeometryZone> zones;
  final GeometryLine? neckline;
  final GeometryZone? breakoutArea;

  const PatternGeometry({
    this.points = const [],
    this.lines = const [],
    this.zones = const [],
    this.neckline,
    this.breakoutArea,
  });

  static const empty = PatternGeometry();

  /// Les droites à tracer, sans doublon.
  ///
  /// Le backend publie la neckline deux fois: dans `trend_lines` avec son
  /// rôle, et dans le champ dédié. La dessiner deux fois l'épaissirait sans
  /// rien ajouter, alors on ne garde qu'un exemplaire.
  List<GeometryLine> get drawableLines {
    final all = [...lines];
    final neck = neckline;
    if (neck != null && !all.any(neck.sameAs)) all.add(neck);
    return all;
  }

  /// Les aires à remplir, sans doublon — même raison que pour la neckline.
  List<GeometryZone> get drawableZones {
    final all = [...zones];
    final breakout = breakoutArea;
    if (breakout != null && !all.any(breakout.sameAs)) all.add(breakout);
    return all;
  }

  /// Vrai quand il n'y a rien à dessiner. Le détecteur a peut-être trouvé la
  /// figure, mais sans géométrie elle ne peut pas être montrée — et une figure
  /// annoncée sans être dessinée serait pire que pas de figure du tout.
  bool get isEmpty =>
      points.isEmpty && lines.isEmpty && zones.isEmpty && neckline == null;

  factory PatternGeometry.fromJson(Map<String, dynamic> json) => PatternGeometry(
        points: ((json['points'] as List?) ?? const [])
            .map(GeometryPoint.maybe)
            .whereType<GeometryPoint>()
            .toList(),
        lines: ((json['trend_lines'] as List?) ?? const [])
            .map(GeometryLine.maybe)
            .whereType<GeometryLine>()
            .toList(),
        zones: ((json['zones'] as List?) ?? const [])
            .map(GeometryZone.maybe)
            .whereType<GeometryZone>()
            .toList(),
        neckline: GeometryLine.maybe(json['neckline']),
        breakoutArea: GeometryZone.maybe(json['breakout_area']),
      );
}

/// Une figure structurelle avec sa géométrie.
///
/// `recognitionConfidence` décrit **la netteté de la forme**, pas une
/// probabilité de hausse. `edgeState` répond séparément à « cette forme a-t-elle
/// démontré un avantage ». Les deux ne se remplacent jamais.
@immutable
class StructuralPatternRead {
  final String name;
  final String patternClass;
  final String state;
  final double recognitionConfidence;
  final String edgeState;
  final String directionIfTextbook;
  final double? invalidationLevel;
  final DateTime? detectedAt;
  final DateTime? confirmationTime;
  final PatternGeometry geometry;

  const StructuralPatternRead({
    required this.name,
    required this.patternClass,
    required this.state,
    required this.recognitionConfidence,
    required this.edgeState,
    required this.directionIfTextbook,
    required this.invalidationLevel,
    required this.detectedAt,
    required this.confirmationTime,
    required this.geometry,
  });

  /// Vrai quand le détecteur a fourni de quoi dessiner.
  ///
  /// Une figure détectée sans géométrie n'est pas tracée. L'annoncer sans la
  /// montrer laisserait le lecteur la chercher là où elle n'est pas.
  bool get isDrawable => !geometry.isEmpty;

  /// Le nom français de la figure.
  String get label => switch (name) {
        'double_top' => 'Double sommet',
        'double_bottom' => 'Double creux',
        'triple_top' => 'Triple sommet',
        'triple_bottom' => 'Triple creux',
        'head_and_shoulders' => 'Épaule-tête-épaule',
        'inverse_head_and_shoulders' => 'ETE inversée',
        'ascending_triangle' => 'Triangle ascendant',
        'descending_triangle' => 'Triangle descendant',
        'symmetrical_triangle' => 'Triangle symétrique',
        'rising_wedge' => 'Biseau ascendant',
        'falling_wedge' => 'Biseau descendant',
        'bull_flag' => 'Drapeau haussier',
        'bear_flag' => 'Drapeau baissier',
        'rectangle' => 'Rectangle',
        _ => name.replaceAll('_', ' '),
      };

  /// Où en est la figure : proposée, confirmée, invalidée.
  String get stateLabel => switch (state) {
        'CANDIDATE' => 'CANDIDATE',
        'FORMING' => 'EN FORMATION',
        'CONFIRMED' => 'CONFIRMÉE',
        'INVALIDATED' => 'INVALIDÉE',
        'EXPIRED' => 'EXPIRÉE',
        _ => state,
      };

  /// Ce que dit la théorie du manuel — pas ce que le système prévoit.
  String get textbookLabel => switch (directionIfTextbook) {
        'BULLISH' => 'haussière',
        'BEARISH' => 'baissière',
        'NEUTRAL' => 'neutre',
        _ => directionIfTextbook.toLowerCase(),
      };

  /// Ce que la mesure a démontré, séparément de la forme.
  String get edgeLabel => switch (edgeState) {
        'POSITIVE_EDGE' => 'avantage mesuré',
        'NEGATIVE_EDGE' => 'avantage négatif mesuré',
        'NO_MEASURABLE_EDGE' => 'aucun avantage mesurable',
        'UNSTABLE' => 'résultat instable',
        'INSUFFICIENT_DATA' => 'données insuffisantes',
        'NOT_YET_TESTED' => 'jamais testée',
        _ => edgeState,
      };

  factory StructuralPatternRead.fromJson(Map<String, dynamic> json) =>
      StructuralPatternRead(
        name: _string(json['name']),
        patternClass: _string(json['pattern_class']),
        state: _string(json['state'], 'CANDIDATE'),
        recognitionConfidence: _double(json['recognition_confidence']) ?? 0,
        edgeState: _string(json['edge_state'], 'NOT_YET_TESTED'),
        directionIfTextbook: _string(json['direction_if_textbook'], 'NEUTRAL'),
        invalidationLevel: _double(json['invalidation_level']),
        detectedAt: DateTime.tryParse('${json['detected_at'] ?? ''}')?.toUtc(),
        confirmationTime:
            DateTime.tryParse('${json['confirmation_time'] ?? ''}')?.toUtc(),
        geometry: PatternGeometry.fromJson(
          ((json['geometry'] as Map?) ?? const {}).cast<String, dynamic>(),
        ),
      );
}
