/// The reading layer (backend `engines/interpretation.py`), as the page shows
/// it: verdict, why, what we wait for, what would change the reading, and
/// per family at most three translated cards. Nothing here is computed: every
/// figure in these texts came from an engine.
library;

Map<String, dynamic> _m(Object? raw) =>
    raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};

List<String> _s(Object? raw) =>
    [for (final x in (raw as List? ?? const [])) x.toString()];

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
