/// Three pages behind the home's "why is the market moving?" lines.
///
///   🪙 Marché        who is taking part in the move
///   💰 Institutions  the two measures of regulated demand, side by side
///   🟣 Catalyseurs   what is specific to this asset, and its stage
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/market_intel_models.dart';
import '../widgets/mobile_kit.dart';

Color toneColour(String tone) => switch (tone) {
      'GREEN' => const Color(0xFF55DD8B),
      'RED' => const Color(0xFFFF6676),
      'ORANGE' => const Color(0xFFFF9A4D),
      'YELLOW' => const Color(0xFFFFB34F),
      'BLUE' => const Color(0xFF4FA8FF),
      _ => mobileMuted,
    };

String _fr(double value, [int decimals = 0]) {
  final text = value.toStringAsFixed(decimals);
  final parts = text.split('.');
  final digits = parts.first.replaceAll('-', '');
  final buffer = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buffer.write(' ');
    buffer.write(digits[i]);
  }
  final sign = value < 0 ? '-' : '';
  return parts.length > 1 ? '$sign$buffer,${parts[1]}' : '$sign$buffer';
}

String _musd(double value) {
  if (value.abs() >= 1000) return '${_fr(value / 1000, 2)} Md\$';
  return '${_fr(value, 0)} M\$';
}

String _signedPct(double value) => '${value >= 0 ? '+' : ''}${_fr(value, 1)} %';

/// Shared frame: a back arrow, a title, and a scrolling body.
class _IntelScaffold extends StatelessWidget {
  final String title;
  final Widget body;

  const _IntelScaffold({required this.title, required this.body});

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFF040C18),
        body: SafeArea(
          bottom: false,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 4, 18, 0),
                child: Row(
                  children: [
                    IconButton(
                      key: const ValueKey('intel-back'),
                      tooltip: 'Retour',
                      onPressed: () => Navigator.of(context).maybePop(),
                      icon: const Icon(Icons.arrow_back_ios_new_rounded,
                          color: Colors.white),
                    ),
                    Expanded(
                      child: Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 19,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(child: body),
            ],
          ),
        ),
      );
}

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) =>
      const Center(child: CircularProgressIndicator());
}

class _Unavailable extends StatelessWidget {
  final String message;

  const _Unavailable(this.message);

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: mobileMuted, height: 1.4)),
        ),
      );
}

// ---------------------------------------------------------------------------
// 🪙 Marché
// ---------------------------------------------------------------------------

class MarketPage extends StatefulWidget {
  final ApiClient client;
  final String asset;

  const MarketPage({super.key, required this.client, required this.asset});

  @override
  State<MarketPage> createState() => _MarketPageState();
}

class _MarketPageState extends State<MarketPage> {
  late final Future<MarketStateRead> _future = widget.client.marketState(widget.asset);

  @override
  Widget build(BuildContext context) => _IntelScaffold(
        title: '🪙 Marché',
        body: FutureBuilder<MarketStateRead>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) return const _Loading();
            final state = snapshot.data;
            if (state == null) {
              return const _Unavailable(
                  'Lecture de la participation du marché indisponible.');
            }
            final measures = state.measures;
            return ListView(
              key: const ValueKey('market-page'),
              padding: const EdgeInsets.fromLTRB(18, 8, 18, 120),
              children: [
                GlassPanel(
                  key: const ValueKey('market-phase'),
                  borderColor: toneColour(_regimeTone(state.regime)).withValues(alpha: .6),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'PHASE DU MARCHÉ',
                        style: TextStyle(
                          color: Color(0xFF8FA8C4),
                          fontSize: 11.5,
                          letterSpacing: .8,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '${state.emoji} ${state.label}',
                        style: TextStyle(
                          color: toneColour(_regimeTone(state.regime)),
                          fontSize: 24,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        state.explanation,
                        style: const TextStyle(
                            color: Color(0xFFD5E1F2), fontSize: 13.5, height: 1.4),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                GlassPanel(
                  key: const ValueKey('market-measures'),
                  borderColor: const Color(0xFF245E90),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('📊 Participation mesurée',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w800)),
                      const SizedBox(height: 10),
                      for (final row in [
                        ('Dominance BTC', measures['btc_dominance'], ' %'),
                        ('Surperforment BTC (30 j)', measures['outperform_30d'], ' %'),
                        ('Surperforment BTC (7 j)', measures['outperform_7d'], ' %'),
                        ('En hausse (30 j)', measures['positive_30d'], ' %'),
                        ('Volumes hors BTC', measures['alt_volume_share'], ' %'),
                        ('ETH/BTC (30 j)', measures['eth_btc_change_30d'], ' %'),
                        ('TOTAL2 (30 j)', measures['total2_change_30d'], ' %'),
                        ('TOTAL3 (30 j)', measures['total3_change_30d'], ' %'),
                        ('Stablecoins (30 j)', measures['stablecoin_change_30d'], ' %'),
                      ])
                        if (row.$2 != null)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 5),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(row.$1,
                                      style: const TextStyle(
                                          color: mobileMuted, fontSize: 13)),
                                ),
                                Text(
                                  '${_fr(row.$2!, 1)}${row.$3}',
                                  style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w700),
                                ),
                              ],
                            ),
                          ),
                      const SizedBox(height: 8),
                      Text(state.windowNote,
                          style: const TextStyle(
                              color: mobileMuted, fontSize: 11.5, height: 1.3)),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                GlassPanel(
                  key: const ValueKey('market-altseason'),
                  borderColor: const Color(0xFF26405E),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('🔎 Conditions d’une rotation vers les altcoins',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      const Text(
                        'Les quatre conditions doivent être réunies : une seule ne suffit jamais.',
                        style: TextStyle(color: mobileMuted, fontSize: 11.5),
                      ),
                      const SizedBox(height: 8),
                      for (final condition in state.conditions)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 5),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(condition.met ? '✅' : '⬜',
                                  style: const TextStyle(fontSize: 14)),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(condition.text,
                                    style: const TextStyle(
                                        color: Color(0xFFD5E1F2),
                                        fontSize: 12.5,
                                        height: 1.3)),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
                if (state.missing.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  GlassPanel(
                    borderColor: const Color(0xFF26405E),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('⚪ Mesures manquantes',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 14,
                                fontWeight: FontWeight.w800)),
                        const SizedBox(height: 6),
                        for (final item in state.missing)
                          Text('• $item',
                              style: const TextStyle(color: mobileMuted, fontSize: 12.5)),
                      ],
                    ),
                  ),
                ],
              ],
            );
          },
        ),
      );
}

String _regimeTone(String regime) => switch (regime) {
      'ALTSEASON_CONFIRMED' || 'BROAD_CRYPTO_RALLY' => 'GREEN',
      'ALTSEASON_EARLY' => 'BLUE',
      'BTC_LED_RALLY' || 'ETH_LED_RALLY' || 'SELECTIVE_ALT_RALLY' => 'ORANGE',
      'RISK_OFF' => 'RED',
      'MIXED' => 'YELLOW',
      _ => 'WHITE',
    };

// ---------------------------------------------------------------------------
// 💰 Institutions
// ---------------------------------------------------------------------------

class InstitutionsPage extends StatefulWidget {
  final ApiClient client;
  final String asset;

  const InstitutionsPage({super.key, required this.client, required this.asset});

  @override
  State<InstitutionsPage> createState() => _InstitutionsPageState();
}

class _InstitutionsPageState extends State<InstitutionsPage> {
  late final Future<InstitutionsRead> _future = widget.client.institutions(widget.asset);

  @override
  Widget build(BuildContext context) => _IntelScaffold(
        title: '💰 Institutions',
        body: FutureBuilder<InstitutionsRead>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) return const _Loading();
            final demand = snapshot.data;
            if (demand == null) {
              return const _Unavailable('Lecture des flux institutionnels indisponible.');
            }
            return ListView(
              key: const ValueKey('institutions-page'),
              padding: const EdgeInsets.fromLTRB(18, 8, 18, 120),
              children: [
                GlassPanel(
                  key: const ValueKey('institutions-state'),
                  borderColor: toneColour(demand.divergence ? 'ORANGE' : 'GREEN')
                      .withValues(alpha: .5),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${demand.emoji} ${demand.label}',
                          style: TextStyle(
                            color: toneColour(_demandTone(demand.state)),
                            fontSize: 22,
                            fontWeight: FontWeight.w900,
                          )),
                      const SizedBox(height: 8),
                      for (final sentence in demand.sentences)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 3),
                          child: Text(sentence,
                              style: const TextStyle(
                                  color: Color(0xFFD5E1F2),
                                  fontSize: 13,
                                  height: 1.35)),
                        ),
                      const SizedBox(height: 8),
                      Text(demand.note,
                          style: const TextStyle(
                              color: mobileMuted, fontSize: 11.5, height: 1.3)),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                _SourceCard(emoji: '💵', source: demand.etf),
                const SizedBox(height: 10),
                _SourceCard(emoji: '🌍', source: demand.global),
                if (demand.others.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  GlassPanel(
                    key: const ValueKey('institutions-others'),
                    borderColor: const Color(0xFF26405E),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('📊 Les autres actifs',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 15,
                                fontWeight: FontWeight.w800)),
                        const SizedBox(height: 8),
                        for (final entry in demand.others.entries)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 5),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(entry.key,
                                      style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 13.5,
                                          fontWeight: FontWeight.w700)),
                                ),
                                Text(
                                  '${entry.value.emoji} ${entry.value.label}',
                                  style: TextStyle(
                                      color: toneColour(_demandTone(entry.value.state)),
                                      fontSize: 12.5),
                                ),
                              ],
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ],
            );
          },
        ),
      );
}

String _demandTone(String state) => switch (state) {
      'STRONG_INFLOW' || 'INFLOW' => 'GREEN',
      'OUTFLOW' || 'STRONG_OUTFLOW' => 'RED',
      'DIVERGENCE' => 'ORANGE',
      'NEUTRAL' => 'YELLOW',
      _ => 'WHITE',
    };

class _SourceCard extends StatelessWidget {
  final String emoji;
  final FlowSourceRead source;

  const _SourceCard({required this.emoji, required this.source});

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: ValueKey('flow-source-${source.name}'),
        borderColor: const Color(0xFF245E90),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(emoji, style: const TextStyle(fontSize: 18)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(source.name,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14.5,
                          fontWeight: FontWeight.w800)),
                ),
                if (source.stale)
                  const Text('🕒 périmée',
                      style: TextStyle(color: Color(0xFFFFB34F), fontSize: 11.5)),
              ],
            ),
            const SizedBox(height: 8),
            if (!source.available)
              const Text('⚪ Source indisponible',
                  style: TextStyle(color: mobileMuted, fontSize: 12.5))
            else ...[
              for (final entry in source.windows.entries)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          switch (entry.key) {
                            '1d' => 'Dernière séance',
                            '7d' => 'Semaine',
                            '30d' => '30 jours',
                            '4w' => 'Quatre semaines',
                            _ => entry.key,
                          },
                          style: const TextStyle(color: mobileMuted, fontSize: 12.5),
                        ),
                      ),
                      Text(
                        _musd(entry.value),
                        style: TextStyle(
                          color: entry.value >= 0
                              ? const Color(0xFF55DD8B)
                              : const Color(0xFFFF6676),
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              if (source.streak.abs() >= 2)
                Text(
                  '🔥 ${source.streak.abs()} périodes consécutives '
                  '${source.streak > 0 ? "d’entrées" : "de sorties"}',
                  style: const TextStyle(color: mobileMuted, fontSize: 12),
                ),
              if (source.percentile != null)
                Text('Rang historique : ${_fr(source.percentile!, 0)}e centile',
                    style: const TextStyle(color: mobileMuted, fontSize: 12)),
              if (source.shareOfAum != null)
                Text('${_fr(source.shareOfAum!.abs(), 2)} % des encours',
                    style: const TextStyle(color: mobileMuted, fontSize: 12)),
            ],
            const SizedBox(height: 6),
            Text(source.note,
                style: const TextStyle(color: mobileMuted, fontSize: 11.5, height: 1.3)),
          ],
        ),
      );
}

// ---------------------------------------------------------------------------
// 🟣 Catalyseurs
// ---------------------------------------------------------------------------

class CatalystsPage extends StatefulWidget {
  final ApiClient client;
  final String asset;

  const CatalystsPage({super.key, required this.client, required this.asset});

  @override
  State<CatalystsPage> createState() => _CatalystsPageState();
}

class _CatalystsPageState extends State<CatalystsPage> {
  late final Future<CatalystsRead> _future = widget.client.catalysts(widget.asset);

  @override
  Widget build(BuildContext context) => _IntelScaffold(
        title: '🟣 Catalyseurs ${widget.asset}',
        body: FutureBuilder<CatalystsRead>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) return const _Loading();
            final reading = snapshot.data;
            if (reading == null) {
              return const _Unavailable('Lecture des catalyseurs indisponible.');
            }
            return ListView(
              key: const ValueKey('catalysts-page'),
              padding: const EdgeInsets.fromLTRB(18, 8, 18, 120),
              children: [
                GlassPanel(
                  key: const ValueKey('catalysts-economics'),
                  borderColor: const Color(0xFF245E90),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('⚖️ Économie du protocole',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w800)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: _Stat(
                              label: 'Offre',
                              value: reading.supplyLabel,
                              detail: reading.supplyGrowthAnnualPct == null
                                  ? ''
                                  : '${_signedPct(reading.supplyGrowthAnnualPct!)} par an',
                            ),
                          ),
                          Expanded(
                            child: _Stat(label: 'Demande', value: reading.demandLabel),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      for (final sentence in reading.economicsSentences)
                        Text(sentence,
                            style: const TextStyle(
                                color: Color(0xFFD5E1F2), fontSize: 12.5, height: 1.35)),
                      for (final missing in reading.economicsMissing)
                        Text('⚪ $missing',
                            style: const TextStyle(color: mobileMuted, fontSize: 11.5)),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                if (reading.catalysts.isEmpty)
                  GlassPanel(
                    key: const ValueKey('catalysts-empty'),
                    borderColor: const Color(0xFF26405E),
                    child: Text(reading.headline,
                        style: const TextStyle(color: mobileMuted, height: 1.4)),
                  ),
                for (final catalyst in reading.catalysts) ...[
                  _CatalystCard(catalyst: catalyst),
                  const SizedBox(height: 10),
                ],
                if (reading.leads.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  GlassPanel(
                    key: const ValueKey('catalysts-leads'),
                    borderColor: const Color(0xFF26405E),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('📰 Pistes média à vérifier',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 14.5,
                                fontWeight: FontWeight.w800)),
                        const SizedBox(height: 6),
                        for (final lead in reading.leads)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Text(
                              '• ${lead['title']} (${lead['source']})',
                              style: const TextStyle(
                                  color: mobileMuted, fontSize: 12.5, height: 1.3),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                Text(reading.note,
                    key: const ValueKey('catalysts-note'),
                    style: const TextStyle(
                        color: mobileMuted, fontSize: 11.5, height: 1.3)),
              ],
            );
          },
        ),
      );
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  final String detail;

  const _Stat({required this.label, required this.value, this.detail = ''});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(color: mobileMuted, fontSize: 11)),
          Text(value,
              style: const TextStyle(
                  color: Colors.white, fontSize: 14, fontWeight: FontWeight.w800)),
          if (detail.isNotEmpty)
            Text(detail, style: const TextStyle(color: mobileMuted, fontSize: 11.5)),
        ],
      );
}

class _CatalystCard extends StatelessWidget {
  final CatalystRead catalyst;

  const _CatalystCard({required this.catalyst});

  @override
  Widget build(BuildContext context) {
    final reaction = catalyst.reaction;
    return GlassPanel(
      key: ValueKey('catalyst-${catalyst.title}'),
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(catalyst.title,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14.5,
                        fontWeight: FontWeight.w800)),
              ),
              Text(catalyst.category,
                  style: const TextStyle(color: mobileMuted, fontSize: 11.5)),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF123E6B),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(catalyst.stageLabel,
                    style: const TextStyle(
                        color: Colors.white, fontSize: 11.5, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 8),
              if (catalyst.publishedAt != null)
                Text(
                  '${catalyst.publishedAt!.day.toString().padLeft(2, '0')}/'
                  '${catalyst.publishedAt!.month.toString().padLeft(2, '0')}',
                  style: const TextStyle(color: mobileMuted, fontSize: 11.5),
                ),
            ],
          ),
          if (catalyst.stageCaveat.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text('⚠️ ${catalyst.stageCaveat}',
                key: const ValueKey('catalyst-caveat'),
                style: const TextStyle(color: Color(0xFFFFB34F), fontSize: 12)),
          ],
          const SizedBox(height: 6),
          Text('💡 ${catalyst.whyItMatters}',
              style: const TextStyle(
                  color: Color(0xFFD5E1F2), fontSize: 12.5, height: 1.35)),
          if (reaction != null) ...[
            const SizedBox(height: 6),
            Text('${reaction.emoji} Marché : ${reaction.label.toLowerCase()}',
                style: const TextStyle(
                    color: Colors.white, fontSize: 12.5, fontWeight: FontWeight.w700)),
            if (reaction.sentence.isNotEmpty)
              Text(reaction.sentence,
                  style: const TextStyle(color: mobileMuted, fontSize: 11.5, height: 1.3)),
          ],
          const SizedBox(height: 6),
          Text(
            'Source ${catalyst.sourceType == "PRIMARY" || catalyst.sourceType == "OFFICIAL" ? "primaire" : "secondaire"}'
            ' · confiance ${switch (catalyst.confidence) {
              'HIGH' => 'élevée',
              'MODERATE' => 'moyenne',
              _ => 'faible',
            }}'
            '${catalyst.corroborations.isEmpty ? '' : ' · ${catalyst.corroborations.length} reprise(s)'}',
            style: const TextStyle(color: mobileMuted, fontSize: 11.5),
          ),
        ],
      ),
    );
  }
}
