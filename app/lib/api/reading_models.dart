/// The reading layer (backend `engines/interpretation.py`), as the page shows
/// it: verdict, why, what we wait for, what would change the reading, and
/// per family at most three translated cards. Nothing here is computed: every
/// figure in these texts came from an engine.
library;

Map<String, dynamic> _m(Object? raw) =>
    raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};

List<String> _s(Object? raw) =>
    [for (final x in (raw as List? ?? const [])) x.toString()];

/// What opens when a reason is tapped: values, sources, freshness.
class ReasonDetail {
  final String title;
  final String explanation;
  final String whyItMatters;
  final String watch;
  final String impact;
  final String impactEmoji;
  final String horizon;
  final List<({String label, String value, String period, String change})> data;
  final List<({String name, String observedFr, String freshness, bool stale})> sources;
  final String note;

  const ReasonDetail({
    this.title = '',
    this.explanation = '',
    this.whyItMatters = '',
    this.watch = '',
    this.impact = '',
    this.impactEmoji = '',
    this.horizon = '',
    this.data = const [],
    this.sources = const [],
    this.note = '',
  });

  static ReasonDetail? fromJson(Object? raw) {
    final j = _m(raw);
    if (j.isEmpty) return null;
    return ReasonDetail(
      title: j['title']?.toString() ?? '',
      explanation: j['explanation']?.toString() ?? '',
      whyItMatters: j['why_it_matters']?.toString() ?? '',
      watch: j['watch']?.toString() ?? '',
      impact: j['impact']?.toString() ?? '',
      impactEmoji: j['impact_emoji']?.toString() ?? '',
      horizon: j['horizon']?.toString() ?? '',
      data: [
        for (final d in (j['data'] as List? ?? const []))
          (
            label: _m(d)['label']?.toString() ?? '',
            value: _m(d)['value']?.toString() ?? '',
            period: _m(d)['period']?.toString() ?? '',
            change: _m(d)['change']?.toString() ?? '',
          )
      ],
      sources: [
        for (final s in (j['sources'] as List? ?? const []))
          (
            name: _m(s)['name']?.toString() ?? '',
            observedFr: _m(s)['observed_fr']?.toString() ?? '',
            freshness: _m(s)['freshness']?.toString() ?? '',
            stale: _m(s)['stale'] == true,
          )
      ],
      note: j['note']?.toString() ?? '',
    );
  }
}

/// « 🧭 Résumé de la situation » and the role each factor plays.
class SituationRead {
  final String text;
  final List<String> sentences;
  final bool dominantCause;
  final Map<String, List<({String emoji, String text})>> roles;
  final Map<String, String> labels;

  const SituationRead({
    this.text = '',
    this.sentences = const [],
    this.dominantCause = false,
    this.roles = const {},
    this.labels = const {},
  });

  bool get isEmpty => text.isEmpty;

  factory SituationRead.fromJson(Object? raw) {
    final j = _m(raw);
    return SituationRead(
      text: j['text']?.toString() ?? '',
      sentences: _s(j['sentences']),
      dominantCause: j['dominant_cause'] == true,
      roles: {
        for (final e in _m(j['roles']).entries)
          e.key: [
            for (final r in (e.value as List? ?? const []))
              (
                emoji: _m(r)['emoji']?.toString() ?? '',
                text: _m(r)['text']?.toString() ?? ''
              )
          ]
      },
      labels: {
        for (final e in _m(j['labels']).entries) e.key: e.value.toString()
      },
    );
  }
}

class ReadingCard {
  final String emoji;
  final String title;
  final String what;
  final String soWhat;
  final String watch;
  final String tone;
  final String importance;
  final String importanceLabel;
  final String family;
  final String value;
  final ReasonDetail? detail;

  const ReadingCard({
    this.emoji = '',
    this.title = '',
    this.what = '',
    this.soWhat = '',
    this.watch = '',
    this.tone = 'WHITE',
    this.importance = 'WATCH',
    this.importanceLabel = '',
    this.family = '',
    this.value = '',
    this.detail,
  });

  factory ReadingCard.fromJson(Object? raw) {
    final j = _m(raw);
    return ReadingCard(
      emoji: j['emoji']?.toString() ?? '',
      title: j['title']?.toString() ?? '',
      what: j['what']?.toString() ?? '',
      soWhat: j['so_what']?.toString() ?? '',
      watch: j['watch']?.toString() ?? '',
      tone: j['tone']?.toString() ?? 'WHITE',
      importance: j['importance']?.toString() ?? 'WATCH',
      importanceLabel: j['importance_label']?.toString() ?? '',
      family: j['family']?.toString() ?? '',
      value: j['value']?.toString() ?? '',
      detail: ReasonDetail.fromJson(j['detail']),
    );
  }
}

class WaitItem {
  final String emoji;
  final String text;
  final String why;
  final String kind;

  const WaitItem(this.emoji, this.text, this.why, this.kind);

  factory WaitItem.fromJson(Object? raw) {
    final j = _m(raw);
    return WaitItem(j['emoji']?.toString() ?? '👀', j['text']?.toString() ?? '',
        j['why']?.toString() ?? '', j['kind']?.toString() ?? '');
  }
}

class ReadingBadge {
  final String emoji;
  final String label;
  final String detail;

  const ReadingBadge({this.emoji = '⚪', this.label = '', this.detail = ''});

  factory ReadingBadge.fromJson(Object? raw) {
    final j = _m(raw);
    return ReadingBadge(
      emoji: j['emoji']?.toString() ?? '⚪',
      label: j['label']?.toString() ?? '',
      detail: j['detail']?.toString() ?? '',
    );
  }
}

class ReadingRead {
  final String action;
  final String verdictEmoji;
  final String verdictLabel;
  final String horizon;
  final String headline;
  final List<ReadingCard> why;
  final List<WaitItem> waitingFor;
  final List<String> bullish;
  final List<String> bearish;
  final String? invalidation;
  final String? validationNote;
  final String? contradiction;
  final List<String> positives;
  final List<String> cautions;
  final Map<String, List<ReadingCard>> families;
  final ReadingBadge data;
  final ReadingBadge market;
  final SituationRead situation;

  const ReadingRead({
    this.action = '',
    this.verdictEmoji = '',
    this.verdictLabel = '',
    this.horizon = '',
    this.headline = '',
    this.why = const [],
    this.waitingFor = const [],
    this.bullish = const [],
    this.bearish = const [],
    this.invalidation,
    this.validationNote,
    this.contradiction,
    this.positives = const [],
    this.cautions = const [],
    this.families = const {},
    this.data = const ReadingBadge(),
    this.market = const ReadingBadge(),
    this.situation = const SituationRead(),
  });

  bool get isEmpty => headline.isEmpty;

  factory ReadingRead.fromJson(Object? raw) {
    final j = _m(raw);
    if (j.isEmpty) return const ReadingRead();
    final verdict = _m(j['verdict']);
    final change = _m(j['change_mind']);
    final contra = _m(j['contradictions']);
    return ReadingRead(
      action: verdict['action']?.toString() ?? '',
      verdictEmoji: verdict['emoji']?.toString() ?? '',
      verdictLabel: verdict['label']?.toString() ?? '',
      horizon: j['horizon']?.toString() ?? '',
      headline: j['headline']?.toString() ?? '',
      why: [
        for (final c in (j['why'] as List? ?? const [])) ReadingCard.fromJson(c)
      ],
      waitingFor: [
        for (final w in (j['waiting_for'] as List? ?? const []))
          WaitItem.fromJson(w)
      ],
      bullish: _s(change['bullish']),
      bearish: _s(change['bearish']),
      invalidation: j['invalidation']?.toString(),
      validationNote: j['validation_note']?.toString(),
      contradiction: contra['sentence']?.toString(),
      positives: _s(contra['positives']),
      cautions: _s(contra['cautions']),
      families: {
        for (final e in _m(j['families']).entries)
          e.key: [
            for (final c in (e.value as List? ?? const []))
              ReadingCard.fromJson(c)
          ]
      },
      data: ReadingBadge.fromJson(j['data']),
      market: ReadingBadge.fromJson(j['market']),
      situation: SituationRead.fromJson(j['situation']),
    );
  }
}

/// « Attendre depuis 3 jours », from recorded readings only.
class DecisionHistoryRead {
  final String label;
  final List<({DateTime? at, String label, String reason})> steps;

  const DecisionHistoryRead({this.label = '', this.steps = const []});

  static DecisionHistoryRead? fromJson(Object? raw) {
    final j = _m(raw);
    if (j.isEmpty) return null;
    return DecisionHistoryRead(
      label: j['label']?.toString() ?? '',
      steps: [
        for (final s in (j['steps'] as List? ?? const []))
          (
            at: DateTime.tryParse(_m(s)['at']?.toString() ?? '')?.toLocal(),
            label: _m(s)['label']?.toString() ?? '',
            reason: _m(s)['reason']?.toString() ?? '',
          )
      ],
    );
  }
}
