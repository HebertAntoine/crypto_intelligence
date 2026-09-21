/// The reading, drawn in the order it is read:
///
///   1. what we wait for      (never « ATTENDRE » without it)
///   2. why                   (two or three reasons, what → so what → watch)
///   3. what would change it  (🟢 plus positif / 🔴 plus prudent, invalidation)
///   4. two separate trusts   (data quality ≠ market clarity), and the history
///
/// Every sentence comes from the backend's interpretation layer; the widgets
/// only lay it out. A raw metric never competes with the decision here.
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

/// One translated card: what happens, → what it means, 👀 what we watch.
class ReadingCardTile extends StatelessWidget {
  final ReadingCard card;
  final bool showImportance;

  const ReadingCardTile(
      {super.key, required this.card, this.showImportance = true});

  @override
  Widget build(BuildContext context) {
    final color = readingTone(card.tone);
    return Padding(
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
        ],
      ),
    );
  }
}

/// « 👀 Ce qu'on attend » - one to three concrete conditions.
class WaitingForCard extends StatelessWidget {
  final ReadingRead reading;

  const WaitingForCard({super.key, required this.reading});

  @override
  Widget build(BuildContext context) {
    if (reading.waitingFor.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('reading-waiting'),
      borderColor: _orange.withValues(alpha: .8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Title('👀', 'Ce qu\'on attend'),
          const SizedBox(height: 6),
          for (var i = 0; i < reading.waitingFor.length; i++) ...[
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ColorEmoji(emoji: reading.waitingFor[i].emoji, size: 17),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(reading.waitingFor[i].text,
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 15.5,
                                fontWeight: FontWeight.w800,
                                height: 1.25)),
                        if (reading.waitingFor[i].why.isNotEmpty)
                          Text(reading.waitingFor[i].why,
                              style: const TextStyle(
                                  color: _muted, fontSize: 12.5, height: 1.35)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
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
          for (var i = 0; i < reading.why.length; i++) ...[
            if (i > 0) const Divider(height: 1, color: _divider),
            ReadingCardTile(card: reading.why[i]),
          ],
          if (reading.contradiction != null) ...[
            const Divider(height: 1, color: _divider),
            const SizedBox(height: 10),
            Text(reading.contradiction!,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w800)),
            if (reading.positives.isNotEmpty)
              Text('🟢 Points positifs : ${reading.positives.join(' · ')}',
                  style: const TextStyle(
                      color: _white, fontSize: 12.5, height: 1.4)),
            if (reading.cautions.isNotEmpty)
              Text('🟠 Points de prudence : ${reading.cautions.join(' · ')}',
                  style: const TextStyle(
                      color: _white, fontSize: 12.5, height: 1.4)),
          ],
          if (reading.validationNote != null) ...[
            const Divider(height: 1, color: _divider),
            const SizedBox(height: 10),
            Text(reading.validationNote!,
                key: const ValueKey('reading-validation'),
                style: const TextStyle(color: _muted, fontSize: 12.5, height: 1.4)),
          ],
          if (onSeeAll != null)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                  onPressed: onSeeAll,
                  child: const Text('Voir l\'analyse complète ›')),
            ),
        ],
      ),
    );
  }
}

/// « Ce qui changerait la lecture » - the decision is conditional.
class ChangeMindCard extends StatelessWidget {
  final ReadingRead reading;

  const ChangeMindCard({super.key, required this.reading});

  @override
  Widget build(BuildContext context) {
    if (reading.bullish.isEmpty &&
        reading.bearish.isEmpty &&
        reading.invalidation == null) {
      return const SizedBox.shrink();
    }
    Widget block(String emoji, String label, List<String> items) => Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            ColorEmoji(emoji: emoji, size: 15),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w800)),
                  for (final item in items)
                    Text('• $item',
                        style: const TextStyle(
                            color: _white, fontSize: 13.5, height: 1.4)),
                ],
              ),
            ),
          ]),
        );
    return GlassPanel(
      key: const ValueKey('reading-change'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Title('🔀', 'Ce qui changerait la lecture'),
          if (reading.bullish.isNotEmpty)
            block('🟢', 'Pour devenir plus positif', reading.bullish),
          if (reading.bearish.isNotEmpty)
            block('🔴', 'Pour devenir plus prudent', reading.bearish),
          if (reading.invalidation != null) ...[
            const SizedBox(height: 10),
            Text('❌ ${reading.invalidation}',
                style: const TextStyle(
                    color: _muted, fontSize: 12.5, height: 1.4)),
          ],
        ],
      ),
    );
  }
}

/// Data quality and market clarity, side by side and never merged; the
/// horizon and how long the verdict has held.
class ReadingTrustLine extends StatelessWidget {
  final ReadingRead reading;
  final DecisionHistoryRead? history;
  final String updated;

  const ReadingTrustLine(
      {super.key, required this.reading, this.history, this.updated = ''});

  @override
  Widget build(BuildContext context) {
    Widget chip(String title, ReadingBadge badge) => Expanded(
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFF0E1A28),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _divider),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(color: _muted, fontSize: 11.5)),
                const SizedBox(height: 3),
                Row(children: [
                  ColorEmoji(emoji: badge.emoji, size: 13),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(badge.label,
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w800)),
                  ),
                ]),
                if (badge.detail.isNotEmpty)
                  Text(badge.detail,
                      style: const TextStyle(
                          color: _muted, fontSize: 11, height: 1.3)),
              ],
            ),
          ),
        );
    return Column(
      key: const ValueKey('reading-trust'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          chip('Données', reading.data),
          const SizedBox(width: 8),
          chip('Marché', reading.market),
        ]),
        const SizedBox(height: 8),
        Text(
            [
              if (reading.horizon.isNotEmpty) 'Lecture à ${reading.horizon}',
              if (updated.isNotEmpty) 'mis à jour $updated',
            ].join(' · '),
            style: const TextStyle(color: _muted, fontSize: 11.5)),
        if (history != null && history!.label.isNotEmpty) ...[
          const SizedBox(height: 10),
          DecisionHistoryView(history: history!),
        ],
      ],
    );
  }
}

class DecisionHistoryView extends StatelessWidget {
  final DecisionHistoryRead history;

  const DecisionHistoryView({super.key, required this.history});

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
          // One reading repeats the verdict above: the steps only tell
          // something once the reason has changed at least once.
          if (history.steps.length > 1)
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
            ReadingCardTile(card: cards[i]),
          ],
        ],
      ),
    );
  }
}
