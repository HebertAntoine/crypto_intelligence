/// Why the market is moving: participation, institutions, catalysts.
library;

double? _number(Object? raw) => raw is num ? raw.toDouble() : null;

List<String> _strings(Object? raw) =>
    (raw as List? ?? const []).map((item) => item.toString()).toList();

Map<String, dynamic> _map(Object? raw) =>
    raw is Map ? Map<String, dynamic>.from(raw) : const <String, dynamic>{};

List<Map<String, dynamic>> _maps(Object? raw) => (raw as List? ?? const [])
    .whereType<Map>()
    .map((item) => Map<String, dynamic>.from(item))
    .toList();

/// One family's contribution to the explanation, tappable to its own page.
class ExplanationLine {
  final String emoji;
  final String family;
  final String title;
  final String detail;
  final String tone;
  final String route;

  const ExplanationLine({
    required this.emoji,
    required this.family,
    required this.title,
    required this.detail,
    required this.tone,
    required this.route,
  });

  factory ExplanationLine.fromJson(Map<String, dynamic> json) => ExplanationLine(
        emoji: json['emoji']?.toString() ?? '•',
        family: json['family']?.toString() ?? '',
        title: json['title']?.toString() ?? '',
        detail: json['detail']?.toString() ?? '',
        tone: json['tone']?.toString() ?? 'WHITE',
        route: json['route']?.toString() ?? '',
      );
}

/// One of the conditions an "altcoin season" claim has to satisfy.
class AltseasonCondition {
  final String text;
  final double threshold;
  final bool met;

  const AltseasonCondition({
    required this.text,
    required this.threshold,
    required this.met,
  });

  factory AltseasonCondition.fromJson(Map<String, dynamic> json) => AltseasonCondition(
        text: json['text']?.toString() ?? '',
        threshold: _number(json['threshold']) ?? 0,
        met: json['met'] == true,
      );
}

class MarketStateRead {
  final String asset;
  final String regime;
  final String label;
  final String emoji;
  final Map<String, double> measures;
  final List<AltseasonCondition> conditions;
  final List<String> missing;
  final String explanation;
  final String windowNote;
  final String question;
  final String conclusion;
  final List<ExplanationLine> lines;

  const MarketStateRead({
    required this.asset,
    required this.regime,
    required this.label,
    required this.emoji,
    required this.measures,
    required this.conditions,
    required this.missing,
    required this.explanation,
    required this.windowNote,
    required this.question,
    required this.conclusion,
    required this.lines,
  });

  double? measure(String key) => measures[key];

  factory MarketStateRead.fromJson(Map<String, dynamic> json) {
    final breadth = _map(json['breadth']);
    final explanation = _map(json['explanation']);
    return MarketStateRead(
      asset: json['asset']?.toString() ?? 'BTC',
      regime: breadth['regime']?.toString() ?? 'INSUFFICIENT_DATA',
      label: breadth['label']?.toString() ?? '',
      emoji: breadth['emoji']?.toString() ?? '⚪',
      measures: {
        for (final entry in _map(breadth['measures']).entries)
          if (_number(entry.value) != null) entry.key: _number(entry.value)!,
      },
      conditions: _maps(breadth['altseason_conditions'])
          .map(AltseasonCondition.fromJson)
          .toList(),
      missing: _strings(breadth['missing']),
      explanation: breadth['explanation']?.toString() ?? '',
      windowNote: breadth['window_note']?.toString() ?? '',
      question: explanation['question']?.toString() ?? '',
      conclusion: explanation['conclusion']?.toString() ?? '',
      lines: _maps(explanation['lines']).map(ExplanationLine.fromJson).toList(),
    );
  }
}

/// One measured source of institutional demand.
class FlowSourceRead {
  final String name;
  final bool available;
  final bool stale;
  final Map<String, double> windows;
  final int streak;
  final double? percentile;
  final double? shareOfAum;
  final String note;

  const FlowSourceRead({
    required this.name,
    required this.available,
    required this.stale,
    required this.windows,
    required this.streak,
    required this.note,
    this.percentile,
    this.shareOfAum,
  });

  factory FlowSourceRead.fromJson(Map<String, dynamic> json) => FlowSourceRead(
        name: json['name']?.toString() ?? '',
        available: json['available'] == true,
        stale: json['stale'] == true,
        windows: {
          for (final entry in _map(json['windows']).entries)
            if (_number(entry.value) != null) entry.key: _number(entry.value)!,
        },
        streak: (_number(json['streak']) ?? 0).round(),
        percentile: _number(json['percentile']),
        shareOfAum: _number(json['share_of_aum_pct']),
        note: json['note']?.toString() ?? '',
      );
}

class InstitutionsRead {
  final String asset;
  final String state;
  final String label;
  final String emoji;
  final bool divergence;
  final FlowSourceRead etf;
  final FlowSourceRead global;
  final List<String> sentences;
  final String note;
  final Map<String, InstitutionsRead> others;

  const InstitutionsRead({
    required this.asset,
    required this.state,
    required this.label,
    required this.emoji,
    required this.divergence,
    required this.etf,
    required this.global,
    required this.sentences,
    required this.note,
    this.others = const {},
  });

  factory InstitutionsRead.fromJson(Map<String, dynamic> json) {
    final demand = json.containsKey('demand') ? _map(json['demand']) : json;
    return InstitutionsRead(
      asset: (json['asset'] ?? demand['asset'])?.toString() ?? '',
      state: demand['state']?.toString() ?? 'INSUFFICIENT_DATA',
      label: demand['label']?.toString() ?? '',
      emoji: demand['emoji']?.toString() ?? '⚪',
      divergence: demand['divergence'] == true,
      etf: FlowSourceRead.fromJson(_map(demand['etf'])),
      global: FlowSourceRead.fromJson(_map(demand['coinshares'])),
      sentences: _strings(demand['sentences']),
      note: demand['note']?.toString() ?? '',
      others: {
        for (final entry in _map(json['others']).entries)
          entry.key: InstitutionsRead.fromJson(_map(entry.value)),
      },
    );
  }
}

/// What the market did with a catalyst, measured on its own windows.
class CatalystReactionRead {
  final String state;
  final String label;
  final String emoji;
  final Map<String, double> after;
  final double? beforePct;
  final String sentence;

  const CatalystReactionRead({
    required this.state,
    required this.label,
    required this.emoji,
    required this.after,
    required this.sentence,
    this.beforePct,
  });

  factory CatalystReactionRead.fromJson(Map<String, dynamic> json) => CatalystReactionRead(
        state: json['state']?.toString() ?? 'UNKNOWN',
        label: json['label']?.toString() ?? '',
        emoji: json['emoji']?.toString() ?? '⚪',
        after: {
          for (final entry in _map(json['after']).entries)
            if (_number(entry.value) != null) entry.key: _number(entry.value)!,
        },
        beforePct: _number(json['before_pct']),
        sentence: json['sentence']?.toString() ?? '',
      );
}

class CatalystRead {
  final String title;
  final String description;
  final String category;
  final String stageLabel;
  final String stageCaveat;
  final String source;
  final String sourceType;
  final String? sourceUrl;
  final DateTime? publishedAt;
  final String importance;
  final String confidence;
  final String whyItMatters;
  final Map<String, dynamic> economicEffect;
  final List<String> corroborations;
  final CatalystReactionRead? reaction;

  const CatalystRead({
    required this.title,
    required this.description,
    required this.category,
    required this.stageLabel,
    required this.stageCaveat,
    required this.source,
    required this.sourceType,
    required this.importance,
    required this.confidence,
    required this.whyItMatters,
    required this.economicEffect,
    required this.corroborations,
    this.sourceUrl,
    this.publishedAt,
    this.reaction,
  });

  String get supplyEffect => economicEffect['supply_effect']?.toString() ?? 'UNKNOWN';

  factory CatalystRead.fromJson(Map<String, dynamic> json) => CatalystRead(
        title: json['title']?.toString() ?? '',
        description: json['description']?.toString() ?? '',
        category: json['category']?.toString() ?? '',
        stageLabel: json['stage_label']?.toString() ?? '',
        stageCaveat: json['stage_caveat']?.toString() ?? '',
        source: json['source']?.toString() ?? '',
        sourceType: json['source_type']?.toString() ?? '',
        sourceUrl: json['source_url']?.toString(),
        publishedAt: DateTime.tryParse(json['published_at']?.toString() ?? ''),
        importance: json['importance']?.toString() ?? 'MEDIUM',
        confidence: json['confidence']?.toString() ?? 'MODERATE',
        whyItMatters: json['why_it_matters']?.toString() ?? '',
        economicEffect: _map(json['economic_effect']),
        corroborations: _strings(json['corroborations']),
        reaction: json['market_reaction'] is Map
            ? CatalystReactionRead.fromJson(_map(json['market_reaction']))
            : null,
      );
}

class CatalystsRead {
  final String asset;
  final String headline;
  final List<CatalystRead> catalysts;
  final List<Map<String, dynamic>> announcements;
  final List<Map<String, dynamic>> leads;
  final String note;
  final String supplyLabel;
  final String demandLabel;
  final double? supplyGrowthAnnualPct;
  final List<String> economicsSentences;
  final List<String> economicsMissing;

  const CatalystsRead({
    required this.asset,
    required this.headline,
    required this.catalysts,
    required this.announcements,
    required this.leads,
    required this.note,
    required this.supplyLabel,
    required this.demandLabel,
    required this.economicsSentences,
    required this.economicsMissing,
    this.supplyGrowthAnnualPct,
  });

  factory CatalystsRead.fromJson(Map<String, dynamic> json) {
    final reading = _map(json['catalysts']);
    final economics = _map(json['economics']);
    return CatalystsRead(
      asset: json['asset']?.toString() ?? '',
      headline: reading['headline']?.toString() ?? '',
      catalysts: _maps(reading['catalysts']).map(CatalystRead.fromJson).toList(),
      announcements: _maps(reading['announcements']),
      leads: _maps(reading['leads']),
      note: reading['note']?.toString() ?? '',
      supplyLabel: economics['supply_label']?.toString() ?? '',
      demandLabel: economics['demand_label']?.toString() ?? '',
      supplyGrowthAnnualPct: _number(economics['supply_growth_annual_pct']),
      economicsSentences: _strings(economics['sentences']),
      economicsMissing: _strings(economics['missing']),
    );
  }
}
