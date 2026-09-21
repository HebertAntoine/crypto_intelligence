/// Lexa payloads, read as the backend wrote them. Nothing is computed here.
library;

double? _num(Object? value) => value is num ? value.toDouble() : null;

DateTime? _date(Object? value) {
  if (value is! String || value.isEmpty) return null;
  // The backend stores UTC; an offset-less string is UTC too.
  final hasZone =
      value.endsWith('Z') || RegExp(r'[+-]\d\d:\d\d$').hasMatch(value);
  return DateTime.tryParse(hasZone ? value : '${value}Z')?.toLocal();
}

class LexaVideoEntry {
  final int videoId;
  final String title;
  final DateTime? publishedAt;
  final List<LexaAssetRef> assets;

  const LexaVideoEntry(this.videoId, this.title, this.publishedAt, this.assets);

  factory LexaVideoEntry.fromJson(Map<String, dynamic> json) => LexaVideoEntry(
        json['video_id'] as int,
        json['title'] as String? ?? '',
        _date(json['published_at']),
        [
          for (final a in (json['assets'] as List? ?? const []))
            LexaAssetRef.fromJson((a as Map).cast<String, dynamic>()),
        ],
      );
}

class LexaAssetRef {
  final String asset;
  final int analysisId;
  final String stance;

  const LexaAssetRef(this.asset, this.analysisId, this.stance);

  factory LexaAssetRef.fromJson(Map<String, dynamic> json) => LexaAssetRef(
        json['asset'] as String,
        json['analysis_id'] as int,
        json['stance'] as String? ?? 'UNSPECIFIED',
      );
}

class LexaLevelState {
  final String state;
  final String emoji;
  final String label;
  final DateTime? firstTouchedAt;
  final DateTime? lastTouchedAt;
  final DateTime? confirmedAt;
  final DateTime? invalidatedAt;
  final String note;

  const LexaLevelState({
    required this.state,
    required this.emoji,
    required this.label,
    this.firstTouchedAt,
    this.lastTouchedAt,
    this.confirmedAt,
    this.invalidatedAt,
    this.note = '',
  });

  factory LexaLevelState.fromJson(Map<String, dynamic>? json) => json == null
      ? const LexaLevelState(
          state: 'NOT_WATCHED', emoji: '⚪', label: 'Non surveillé')
      : LexaLevelState(
          state: json['state'] as String,
          emoji: json['emoji'] as String? ?? '⚪',
          label: json['label'] as String? ?? '',
          firstTouchedAt: _date(json['first_touched_at']),
          lastTouchedAt: _date(json['last_touched_at']),
          confirmedAt: _date(json['confirmed_at']),
          invalidatedAt: _date(json['invalidated_at']),
          note: json['note'] as String? ?? '',
        );
}

class LexaLevel {
  final int id;
  final String kind;
  final String emoji;
  final String kindLabel;
  final double value;
  final double originalValue;
  final double? correctedValue;
  final DateTime? correctedAt;
  final double? allocationPct;
  final double? allocationEur;
  final String? timestamp;
  final String sourceText;
  final String condition;
  final String conditionLabel;
  final bool toVerify;
  final LexaLevelState state;

  const LexaLevel({
    required this.id,
    required this.kind,
    required this.emoji,
    required this.kindLabel,
    required this.value,
    required this.originalValue,
    this.correctedValue,
    this.correctedAt,
    this.allocationPct,
    this.allocationEur,
    this.timestamp,
    this.sourceText = '',
    this.condition = 'UNKNOWN',
    this.conditionLabel = '',
    this.toVerify = false,
    required this.state,
  });

  bool get isCorrected => correctedValue != null;

  factory LexaLevel.fromJson(Map<String, dynamic> json) => LexaLevel(
        id: json['id'] as int,
        kind: json['kind'] as String,
        emoji: json['emoji'] as String? ?? '📝',
        kindLabel: json['kind_label'] as String? ?? '',
        value: _num(json['value']) ?? 0,
        originalValue: _num(json['original_value']) ?? 0,
        correctedValue: _num(json['corrected_value']),
        correctedAt: _date(json['corrected_at']),
        allocationPct: _num(json['allocation_pct']),
        allocationEur: _num(json['allocation_eur']),
        timestamp: json['timestamp'] as String?,
        sourceText: json['source_text'] as String? ?? '',
        condition: json['condition'] as String? ?? 'UNKNOWN',
        conditionLabel: json['condition_label'] as String? ?? '',
        toVerify: json['to_verify'] as bool? ?? false,
        state: LexaLevelState.fromJson(
            (json['state'] as Map?)?.cast<String, dynamic>()),
      );
}

class LexaSimulation {
  final double capitalEur;
  final double executedEur;
  final double remainingEur;
  final double quantityHeld;
  final double? averagePrice;
  final double realisedEur;
  final double? currentPrice;
  final double currentValueEur;
  final double? performancePct;
  final int fillCount;
  final int exitCount;
  final List<int> targetsHit;
  final bool invalidationReached;
  final List<String> assumptions;
  final String disclaimer;

  const LexaSimulation({
    required this.capitalEur,
    required this.executedEur,
    required this.remainingEur,
    required this.quantityHeld,
    this.averagePrice,
    required this.realisedEur,
    this.currentPrice,
    required this.currentValueEur,
    this.performancePct,
    required this.fillCount,
    required this.exitCount,
    required this.targetsHit,
    required this.invalidationReached,
    required this.assumptions,
    required this.disclaimer,
  });

  factory LexaSimulation.fromJson(Map<String, dynamic> json) => LexaSimulation(
        capitalEur: _num(json['capital_eur']) ?? 0,
        executedEur: _num(json['executed_eur']) ?? 0,
        remainingEur: _num(json['remaining_eur']) ?? 0,
        quantityHeld: _num(json['quantity_held']) ?? 0,
        averagePrice: _num(json['average_price']),
        realisedEur: _num(json['realised_eur']) ?? 0,
        currentPrice: _num(json['current_price']),
        currentValueEur: _num(json['current_value_eur']) ?? 0,
        performancePct: _num(json['performance_pct']),
        fillCount: (json['fills'] as List? ?? const []).length,
        exitCount: (json['exits'] as List? ?? const []).length,
        targetsHit: [
          for (final t in (json['targets_hit'] as List? ?? const [])) t as int
        ],
        invalidationReached: json['invalidation_reached'] as bool? ?? false,
        assumptions: [
          for (final a in (json['assumptions'] as List? ?? const [])) '$a'
        ],
        disclaimer: json['disclaimer'] as String? ?? '',
      );
}

class LexaReport {
  final int analysisId;
  final String asset;
  final String videoTitle;
  final String source;
  final String sourceRef;
  final DateTime? publishedAt;
  final DateTime? processedAt;
  final double? priceAtVideo;
  final double? currentPrice;
  final String stance;
  final String stanceEmoji;
  final String stanceLabel;
  final String summary;
  final double capitalEur;
  final List<LexaLevel> levels;
  final LexaSimulation simulation;
  final String note;

  const LexaReport({
    required this.analysisId,
    required this.asset,
    required this.videoTitle,
    required this.source,
    required this.sourceRef,
    this.publishedAt,
    this.processedAt,
    this.priceAtVideo,
    this.currentPrice,
    required this.stance,
    required this.stanceEmoji,
    required this.stanceLabel,
    required this.summary,
    required this.capitalEur,
    required this.levels,
    required this.simulation,
    required this.note,
  });

  factory LexaReport.fromJson(Map<String, dynamic> json) {
    final video = (json['video'] as Map? ?? const {}).cast<String, dynamic>();
    return LexaReport(
      analysisId: json['analysis_id'] as int,
      asset: json['asset'] as String,
      videoTitle: video['title'] as String? ?? '',
      source: video['source'] as String? ?? 'Lexa',
      sourceRef: video['source_ref'] as String? ?? '',
      publishedAt: _date(json['published_at']),
      processedAt: _date(json['processed_at']),
      priceAtVideo: _num(json['price_at_video']),
      currentPrice: _num(json['current_price']),
      stance: json['stance'] as String? ?? 'UNSPECIFIED',
      stanceEmoji: json['stance_emoji'] as String? ?? '⚪',
      stanceLabel: json['stance_label'] as String? ?? 'Non précisé',
      summary: json['summary'] as String? ?? '',
      capitalEur: _num(json['capital_eur']) ?? 100,
      levels: [
        for (final l in (json['levels'] as List? ?? const []))
          LexaLevel.fromJson((l as Map).cast<String, dynamic>()),
      ],
      simulation: LexaSimulation.fromJson(
          (json['simulation'] as Map? ?? const {}).cast<String, dynamic>()),
      note: json['note'] as String? ?? '',
    );
  }

  List<LexaLevel> ofKinds(Set<String> kinds) => [
        for (final l in levels)
          if (kinds.contains(l.kind)) l
      ];
}

/// Level types, in the order the entry form offers them.
const lexaKinds = <String, String>{
  'BUY_ZONE': '🟢 Zone d\'achat',
  'REINFORCEMENT': '🟢 Renforcement',
  'CONFIRMATION': '🚀 Confirmation',
  'INVALIDATION': '❌ Invalidation',
  'TARGET': '🎯 Objectif',
  'TAKE_PROFIT': '🎯 Prise de profit',
  'SUPPORT': '🧱 Support',
  'RESISTANCE': '🧱 Résistance',
  'CURRENT_PRICE': '💲 Prix observé',
  'WARNING': '⚠️ Avertissement',
  'OTHER': '📝 Autre',
};

const lexaConditions = <String, String>{
  'UNKNOWN': 'Non précisée dans la vidéo',
  'CLOSE_1H_ABOVE': 'Clôture 1 h au-dessus',
  'CLOSE_4H_ABOVE': 'Clôture 4 h au-dessus',
  'CLOSE_1D_ABOVE': 'Clôture journalière au-dessus',
  'CLOSE_1H_BELOW': 'Clôture 1 h en dessous',
  'CLOSE_4H_BELOW': 'Clôture 4 h en dessous',
  'CLOSE_1D_BELOW': 'Clôture journalière en dessous',
};

const lexaStances = <String, String>{
  'UNSPECIFIED': '⚪ Non précisé',
  'WAIT': '🟠 Attente',
  'BUY': '🟢 Achat',
  'SELL': '🔴 Vente',
  'NEUTRAL': '⚪ Neutre',
};

/// "1,2688" or "1.2688" or "70 000" -> 1.2688 / 70000. Null when unreadable.
double? parseFrNumber(String raw) {
  final cleaned = raw
      .trim()
      .replaceAll(RegExp(r'[\s\u00a0\u202f$€]'), '')
      .replaceAll(',', '.');
  if (cleaned.isEmpty) return null;
  return double.tryParse(cleaned);
}

/// A price with as many decimals as it needs: 70 250 $ / 1,2688 $.
String fmtPrice(double? value) {
  if (value == null) return '—';
  final digits = value >= 1000 ? 0 : (value >= 1 ? 4 : 6);
  var text = value.toStringAsFixed(digits);
  if (digits > 0) {
    text = text.replaceAll(RegExp(r'0+$'), '');
    if (text.endsWith('.')) text = '${text}00';
  }
  final parts = text.split('.');
  final grouped = parts[0]
      .replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]}\u202f');
  return parts.length > 1 ? '$grouped,${parts[1]} \$' : '$grouped \$';
}

String fmtEur(double? value) =>
    value == null ? '—' : '${value.toStringAsFixed(2).replaceAll('.', ',')} €';

String fmtDateFr(DateTime? d, {bool time = true}) {
  if (d == null) return '—';
  String two(int v) => v.toString().padLeft(2, '0');
  final day = '${two(d.day)}/${two(d.month)}/${d.year}';
  return time ? '$day à ${two(d.hour)}:${two(d.minute)}' : day;
}
