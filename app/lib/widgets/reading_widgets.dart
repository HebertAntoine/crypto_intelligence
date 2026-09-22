/// The reading, drawn in the order it is read:
///
///   1. the situation         (four lines; the narrative is one tap away)
///   2. why                   (three compact reasons, each opening its figures)
///   3. the conditions        (🟢 opportunity / 🔴 invalidation / 📅 one date)
///   4. one trust line        (data quality ≠ market clarity), and the history
///
/// Every sentence comes from the backend's interpretation layer; the widgets
/// only lay it out. A raw metric never competes with the decision here, and
/// nothing shown on the home is shown a second time in another shape.
library;

import 'package:flutter/material.dart';

import '../api/reading_models.dart';
import 'color_emoji.dart';
import 'mobile_kit.dart';

const _green = Color(0xFF3FB950);
const _orange = Color(0xFFF0A23B);
const _red = Color(0xFFF85149);
const _white = Color(0xFFE6EEF9);
const _muted = Color(0xFF9FB3CC);
const _divider = Color(0xFF1D3853);

Color readingTone(String tone) => switch (tone) {
      'GREEN' => _green,
      'ORANGE' => _orange,
      'RED' => _red,
      'YELLOW' => const Color(0xFFE3C35A),
      _ => _white,
    };

class _Title extends StatelessWidget {
  final String emoji;
  final String text;

  const _Title(this.emoji, this.text);

  @override
  Widget build(BuildContext context) => Row(children: [
        ColorEmoji(emoji: emoji, size: 18),
        const SizedBox(width: 8),
        Expanded(
          child: Text(text,
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 19,
                  fontWeight: FontWeight.w800)),
        ),
      ]);
}

const _roleOrder = ['triggers', 'supports', 'amplifiers', 'brakes', 'context'];
const _roleEmoji = {
  'triggers': '🔺',
  'supports': '🤝',
  'amplifiers': '⚡',
  'brakes': '🧱',
  'context': '🗺️',
};

/// « 🧭 Situation actuelle » : four lines on the home, no more. The roles —
/// trigger, support, amplifier, brake, context — and the full narrative live
/// behind « Comprendre le mouvement », so the home stays a summary.
class SituationCard extends StatelessWidget {
  final SituationRead situation;
  final VoidCallback? onUnderstand;

  const SituationCard({super.key, required this.situation, this.onUnderstand});

  @override
  Widget build(BuildContext context) {
    if (situation.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('reading-situation'),
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Title('🧭', 'Situation actuelle'),
          const SizedBox(height: 8),
          Text(situation.homeText,
              key: const ValueKey('situation-text'),
              style:
                  const TextStyle(color: _white, fontSize: 14.5, height: 1.5)),
          if (onUnderstand != null)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                key: const ValueKey('situation-understand'),
                onPressed: onUnderstand,
                style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                child: const Text('Comprendre le mouvement ›'),
              ),
            ),
        ],
      ),
    );
  }
}

/// « Comprendre le mouvement » : the full narrative, then each factor with the
/// role it plays. A trigger is never listed as an amplifier, and a coincidence
/// is never presented as a cause.
class MovementView extends StatelessWidget {
  final SituationRead situation;

  /// « Pourquoi le marché monte ? », moved off the home and shown here.
  final Widget? explanation;

  const MovementView({super.key, required this.situation, this.explanation});

  @override
  Widget build(BuildContext context) => ListView(
        key: const ValueKey('movement-view'),
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 40),
        children: [
          const _Title('🧭', 'Comprendre le mouvement'),
          const SizedBox(height: 12),
          Text(situation.text,
              key: const ValueKey('movement-text'),
              style:
                  const TextStyle(color: _white, fontSize: 14.5, height: 1.55)),
          for (final role in _roleOrder)
            if ((situation.roles[role] ?? const []).isNotEmpty) ...[
              const SizedBox(height: 16),
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                ColorEmoji(emoji: _roleEmoji[role]!, size: 15),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(situation.labels[role] ?? role,
                          style: const TextStyle(
                              color: _muted,
                              fontSize: 11.5,
                              letterSpacing: .4,
                              fontWeight: FontWeight.w800)),
                      for (final item in situation.roles[role]!)
                        Text('• ${item.text}',
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 13.5,
                                height: 1.4)),
                    ],
                  ),
                ),
              ]),
            ],
          if (explanation != null) ...[
            const SizedBox(height: 20),
            explanation!,
          ],
        ],
      );
}

/// One translated card: what happens, → what it means, 👀 what we watch.
///
/// `compact` is what the home uses: the title, the one figure that carries it
/// and a single sentence. The rest of the card is a tap away, which is why the
/// same information never has to appear twice on the home.
class ReadingCardTile extends StatelessWidget {
  final ReadingCard card;
  final bool showImportance;
  final bool compact;
  final VoidCallback? onTap;

  const ReadingCardTile(
      {super.key,
      required this.card,
      this.showImportance = true,
      this.compact = false,
      this.onTap});

  @override
  Widget build(BuildContext context) {
    final color = readingTone(card.tone);
    if (compact) return _compact(color);
    final body = Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: ColorEmoji(
                emoji: card.emoji.isEmpty ? '•' : card.emoji, size: 18),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(card.title,
                    style: TextStyle(
                        color: color == _white ? Colors.white : color,
                        fontSize: 15.5,
                        fontWeight: FontWeight.w800,
                        height: 1.25)),
                if (showImportance && card.importance == 'NOW')
                  const Padding(
                    padding: EdgeInsets.only(top: 2),
                    child: Text('Important maintenant',
                        style: TextStyle(
                            color: _orange,
                            fontSize: 11.5,
                            fontWeight: FontWeight.w700)),
                  ),
                if (card.what.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(card.what,
                      style: const TextStyle(
                          color: _white, fontSize: 13.5, height: 1.4)),
                ],
                if (card.soWhat.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text('→ ${card.soWhat}',
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13.5,
                          height: 1.4,
                          fontWeight: FontWeight.w600)),
                ],
                if (card.watch.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text('À surveiller : ${card.watch}',
                      style: const TextStyle(
                          color: _muted, fontSize: 12.5, height: 1.35)),
                ],
              ],
            ),
          ),
          if (onTap != null)
            const Icon(Icons.chevron_right_rounded, color: Color(0xFF4E7CB5)),
        ],
      ),
    );
    if (onTap == null) return body;
    return InkWell(
        key: ValueKey('reason-${card.title}'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: body);
  }

  Widget _compact(Color color) {
    // One sentence: what it means for the decision, or what is happening when
    // the card has no reading of its own. Never both.
    final sentence = card.soWhat.isNotEmpty ? card.soWhat : card.what;
    // « Résistance importante — 87 396 $ » followed by « 87 396 $ » is the
    // same figure twice: the title already carries it.
    final value = card.title.contains(card.value) ? '' : card.value;
    final body = Padding(
      padding: const EdgeInsets.symmetric(vertical: 11),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: ColorEmoji(
                emoji: card.emoji.isEmpty ? '•' : card.emoji, size: 17),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(card.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        color: color == _white ? Colors.white : color,
                        fontSize: 15,
                        fontWeight: FontWeight.w800)),
                if (value.isNotEmpty)
                  Text(value,
                      style: const TextStyle(
                          color: _white,
                          fontSize: 12.5,
                          fontWeight: FontWeight.w700)),
                if (sentence.isNotEmpty)
                  Text(sentence,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: _muted, fontSize: 12.5, height: 1.35)),
              ],
            ),
          ),
          if (onTap != null)
            const Icon(Icons.chevron_right_rounded, color: Color(0xFF4E7CB5)),
        ],
      ),
    );
    if (onTap == null) return body;
    return InkWell(
        key: ValueKey('reason-${card.title}'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: body);
  }
}

/// « 🎯 Conditions à surveiller » : opportunity, invalidation, and the one date
/// the engine grades high enough to change the reading. It replaces the two
/// cards — « ce qu'on attend » and « ce qui changerait la lecture » — that
/// answered the same question in two voices.
class ConditionsCard extends StatelessWidget {
  final ConditionsRead conditions;

  const ConditionsCard({super.key, required this.conditions});

  @override
  Widget build(BuildContext context) {
    if (conditions.isEmpty) return const SizedBox.shrink();
    Widget block(String emoji, String label, List<WaitItem> items) => Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                ColorEmoji(emoji: emoji, size: 13),
                const SizedBox(width: 6),
                Text(label.toUpperCase(),
                    style: const TextStyle(
                        color: _muted,
                        fontSize: 11,
                        letterSpacing: .6,
                        fontWeight: FontWeight.w800)),
              ]),
              for (final item in items)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(item.text,
                      style: const TextStyle(
                          color: Colors.white, fontSize: 14, height: 1.35)),
                ),
            ],
          ),
        );
    final event = conditions.event;
    return GlassPanel(
      key: const ValueKey('reading-conditions'),
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Title('🎯', 'Conditions à surveiller'),
          if (conditions.opportunity.isNotEmpty)
            block('🟢', conditions.labels['opportunity'] ?? 'Opportunité',
                conditions.opportunity),
          if (conditions.invalidation.isNotEmpty)
            block('🔴', conditions.labels['invalidation'] ?? 'Invalidation',
                conditions.invalidation),
          if (event != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                ColorEmoji(emoji: event.emoji, size: 15),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(event.text,
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 14,
                              fontWeight: FontWeight.w700)),
                      // What deserves attention, and nothing about which way
                      // it points: that is only known once it is published.
                      if (event.attention.isNotEmpty)
                        Text(event.attention,
                            style: const TextStyle(
                                color: _orange, fontSize: 12, height: 1.3)),
                    ],
                  ),
                ),
              ]),
            ),
        ],
      ),
    );
  }
}

/// « Pourquoi ? » - two or three reasons, contradictions stated.
class WhyCard extends StatelessWidget {
  final ReadingRead reading;
  final VoidCallback? onSeeAll;

  const WhyCard({super.key, required this.reading, this.onSeeAll});

  @override
  Widget build(BuildContext context) {
    final title = switch (reading.action) {
      'BUY' => 'Pourquoi acheter ?',
      'SELL' => 'Pourquoi vendre ?',
      'INSUFFICIENT_DATA' => 'Pourquoi pas de lecture ?',
      _ => 'Pourquoi attendre ?',
    };
    return GlassPanel(
      key: const ValueKey('reading-why'),
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Title('🔎', title),
          // Three reasons, each one line of figures and one of meaning. The
          // contradictions are not repeated here: the decision card already
          // says « Marché : signaux partagés ».
          for (var i = 0; i < reading.why.length && i < 3; i++) ...[
            if (i > 0) const Divider(height: 1, color: _divider),
            ReadingCardTile(
              card: reading.why[i],
              compact: true,
              onTap: reading.why[i].detail == null
                  ? null
                  : () => ReasonDetailSheet.open(context, reading.why[i]),
            ),
          ],
          if (reading.validationNote != null) ...[
            const Divider(height: 1, color: _divider),
            const SizedBox(height: 10),
            Text(reading.validationNote!,
                key: const ValueKey('reading-validation'),
                style: const TextStyle(
                    color: _muted, fontSize: 12.5, height: 1.4)),
          ],
        ],
      ),
    );
  }
}

/// One line under the decision card: how far the data can be trusted, whether
/// the market itself is clear — two readings, never merged into one score —
/// when it was updated, and how long the verdict has held. The two panels this
/// replaces said the same thing in far more room.
class DecisionFooter extends StatelessWidget {
  final ReadingRead reading;
  final DecisionHistoryRead? history;
  final String updated;
  final VoidCallback? onHistory;

  const DecisionFooter(
      {super.key,
      required this.reading,
      this.history,
      this.updated = '',
      this.onHistory});

  @override
  Widget build(BuildContext context) {
    final trust = [
      if (reading.data.label.isNotEmpty)
        '${reading.data.emoji} ${reading.data.label}',
      // « Marché : Marché incertain » stutters; the label already says it.
      if (reading.market.label.isNotEmpty)
        reading.market.label.startsWith('Marché')
            ? reading.market.label
            : 'Marché : ${reading.market.label}',
      if (updated.isNotEmpty) 'mis à jour $updated',
    ].join(' · ');
    final label = history?.label ?? '';
    return Column(
      key: const ValueKey('reading-trust'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(trust,
            key: const ValueKey('decision-trust-line'),
            style: const TextStyle(color: _muted, fontSize: 11.5, height: 1.4)),
        if (label.isNotEmpty)
          InkWell(
            key: const ValueKey('decision-history-link'),
            onTap: onHistory,
            child: Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                  onHistory == null ? label : '$label · Historique ›',
                  style: const TextStyle(
                      color: Color(0xFF6FA8DC),
                      fontSize: 11.5,
                      fontWeight: FontWeight.w700)),
            ),
          ),
      ],
    );
  }
}

/// The history behind « Attendre depuis 21 h » — one line per recorded
/// reading. It is secondary information, so it opens on demand.
class DecisionHistoryView extends StatelessWidget {
  final DecisionHistoryRead history;

  /// On its own sheet every recorded step is shown; inline, the steps only
  /// tell something once the reason has changed at least once.
  final bool full;

  const DecisionHistoryView(
      {super.key, required this.history, this.full = false});

  static Future<void> open(BuildContext context, DecisionHistoryRead history) =>
      showModalBottomSheet<void>(
        context: context,
        backgroundColor: const Color(0xFF061525),
        builder: (context) => Padding(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 28),
          child: DecisionHistoryView(history: history, full: true),
        ),
      );

  @override
  Widget build(BuildContext context) {
    const months = [
      'janv.',
      'févr.',
      'mars',
      'avr.',
      'mai',
      'juin',
      'juil.',
      'août',
      'sept.',
      'oct.',
      'nov.',
      'déc.'
    ];
    return GlassPanel(
      key: const ValueKey('reading-history'),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Title('🕒', history.label),
          if (full || history.steps.length > 1)
            for (final step in history.steps)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                    '${step.at == null ? '' : '${step.at!.day} ${months[step.at!.month - 1]} — '}'
                    '${step.label} : ${step.reason}',
                    style: const TextStyle(
                        color: _white, fontSize: 12.5, height: 1.35)),
              ),
        ],
      ),
    );
  }
}

/// « En bref » at the top of a family page: at most three cards.
class FamilyEssentials extends StatelessWidget {
  final List<ReadingCard> cards;

  const FamilyEssentials({super.key, required this.cards});

  @override
  Widget build(BuildContext context) {
    if (cards.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('family-essentials'),
      borderColor: const Color(0xFF2B669B),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Title('🎯', 'En bref'),
          for (var i = 0; i < cards.length; i++) ...[
            if (i > 0) const Divider(height: 1, color: _divider),
            ReadingCardTile(
              card: cards[i],
              onTap: cards[i].detail == null
                  ? null
                  : () => ReasonDetailSheet.open(context, cards[i]),
            ),
          ],
        ],
      ),
    );
  }
}

/// The detail behind one reason: the figures, why it matters, what we watch,
/// its impact on the decision, and the sources with their freshness.
class ReasonDetailSheet extends StatelessWidget {
  final ReadingCard card;
  final ScrollController? controller;

  const ReasonDetailSheet({super.key, required this.card, this.controller});

  static Future<void> open(BuildContext context, ReadingCard card) =>
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: const Color(0xFF061525),
        builder: (context) => DraggableScrollableSheet(
          expand: false,
          initialChildSize: .7,
          maxChildSize: .95,
          builder: (context, controller) =>
              ReasonDetailSheet(card: card, controller: controller),
        ),
      );

  static const _label = TextStyle(
      color: _muted,
      fontSize: 12,
      letterSpacing: .5,
      fontWeight: FontWeight.w800);

  @override
  Widget build(BuildContext context) {
    final detail = card.detail;
    return ListView(
      key: const ValueKey('reason-detail'),
      controller: controller,
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
      children: [
        Row(children: [
          ColorEmoji(emoji: card.emoji, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(card.title,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w800)),
          ),
        ]),
        const SizedBox(height: 12),
        Text(
            detail != null && detail.explanation.isNotEmpty
                ? detail.explanation
                : card.what,
            style:
                const TextStyle(color: _white, fontSize: 14.5, height: 1.45)),
        if (detail != null) ...[
          if (detail.data.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('Données', style: _label),
            for (final row in detail.data)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Row(children: [
                  Expanded(
                      child: Text(row.label,
                          style:
                              const TextStyle(color: _white, fontSize: 13.5))),
                  Text(
                      [row.value, if (row.change.isNotEmpty) row.change]
                          .join('  '),
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13.5,
                          fontWeight: FontWeight.w700)),
                  if (row.period.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(left: 8),
                      child: Text(row.period,
                          style:
                              const TextStyle(color: _muted, fontSize: 11.5)),
                    ),
                ]),
              ),
          ],
          const SizedBox(height: 16),
          const Text('Pourquoi cela compte', style: _label),
          Text(detail.whyItMatters,
              style: const TextStyle(
                  color: Colors.white, fontSize: 14, height: 1.45)),
          if (detail.watch.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Text('Ce que nous surveillons', style: _label),
            Text(detail.watch,
                style: const TextStyle(
                    color: Colors.white, fontSize: 14, height: 1.45)),
          ],
          const SizedBox(height: 14),
          Row(children: [
            Expanded(
              child: Text(
                  'Impact sur la décision : ${detail.impactEmoji} ${detail.impact}',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700)),
            ),
            Text('Horizon : ${detail.horizon}',
                style: const TextStyle(color: _muted, fontSize: 12.5)),
          ]),
          if (detail.sources.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Text('Source', style: _label),
            for (final source in detail.sources)
              Text(
                  '${source.name} — ${source.observedFr}'
                  '${source.freshness.isEmpty ? '' : ' · donnée ${source.freshness}'}'
                  '${source.stale ? '  ⚠️ non actualisée' : ''}',
                  style: TextStyle(
                      color: source.stale ? _orange : _muted,
                      fontSize: 12.5,
                      height: 1.4)),
          ],
          if (detail.note.isNotEmpty)
            Text(detail.note,
                style: const TextStyle(color: _muted, fontSize: 12.5)),
        ],
      ],
    );
  }
}
