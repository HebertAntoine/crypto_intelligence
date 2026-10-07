/// 🎬 Historique des analyses — jour par jour, puis crypto par crypto.
///
/// Une page d'information, et rien d'autre : elle montre ce qui a été annoncé
/// un jour donné, pour chaque crypto, avec les niveaux tels qu'ils ont été
/// relevés. Rien n'y est recalculé et rien n'y est saisi.
///
/// Ce qui a été dit un 7 octobre ne change pas : les lignes viennent telles
/// quelles de la base privée, et les valeurs corrigées à la main l'emportent
/// sur les valeurs d'origine, qui restent enregistrées.
library;

import 'package:flutter/material.dart';

import '../widgets/color_emoji.dart';
import '../widgets/mobile_kit.dart';
import 'lexa_client.dart';
import 'lexa_ui.dart';

class LexaHistoryScreen extends StatefulWidget {
  final LexaClient client;

  const LexaHistoryScreen({super.key, required this.client});

  @override
  State<LexaHistoryScreen> createState() => _LexaHistoryScreenState();
}

class _LexaHistoryScreenState extends State<LexaHistoryScreen> {
  late Future<Map<String, dynamic>> _data = widget.client.historyByDay();
  String _asset = 'ALL';

  void _reload() => setState(() => _data = widget.client.historyByDay());

  @override
  Widget build(BuildContext context) {
    return LexaEmojiFonts(
      child: Scaffold(
        backgroundColor: const Color(0xFF061525),
        body: SafeArea(
          bottom: false,
          child: FutureBuilder<Map<String, dynamic>>(
            future: _data,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snapshot.hasError) {
                return _error('${snapshot.error}');
              }
              return _body(snapshot.data ?? const {});
            },
          ),
        ),
      ),
    );
  }

  Widget _error(String message) => ListView(
        padding: const EdgeInsets.all(22),
        children: [
          const Text('🎬 Historique',
              style: TextStyle(
                  color: Colors.white, fontSize: 26, fontWeight: FontWeight.w900)),
          const SizedBox(height: 10),
          Text('Lecture impossible : $message',
              style: const TextStyle(color: lexaMuted, fontSize: 13.5, height: 1.4)),
          const SizedBox(height: 14),
          FilledButton(onPressed: _reload, child: const Text('Réessayer')),
        ],
      );

  Widget _body(Map<String, dynamic> data) {
    final days = (data['days'] as List? ?? const [])
        .map((d) => Map<String, dynamic>.from(d as Map))
        .toList();
    // The filter chips are built from the days themselves: a crypto that was
    // never analysed has no reason to appear.
    final assets = <String>{
      for (final day in days)
        for (final asset in (day['assets'] as List? ?? const [])) '$asset',
    }.toList()
      ..sort();
    final visible = _asset == 'ALL'
        ? days
        : [
            for (final day in days)
              if ((day['assets'] as List? ?? const []).contains(_asset))
                {
                  ...day,
                  'analyses': [
                    for (final a in (day['analyses'] as List? ?? const []))
                      if ((a as Map)['asset'] == _asset) a
                  ],
                }
          ];

    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: MobileScrollView(
        key: const ValueKey('lexa-history'),
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 150),
        children: [
          const Text('🎬 Historique',
              key: ValueKey('lexa-history-title'),
              style: TextStyle(
                  color: Colors.white, fontSize: 28, fontWeight: FontWeight.w900)),
          Text(
              '${data['analyses_count'] ?? 0} analyses · '
              '${data['days_count'] ?? 0} journées · '
              '${data['assets_count'] ?? 0} cryptos',
              style: const TextStyle(color: lexaMuted, fontSize: 13)),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _chip('Tout', 'ALL'),
              for (final asset in assets) _chip(asset, asset),
            ],
          ),
          const SizedBox(height: 16),
          if (visible.isEmpty)
            lexaNote('Aucune analyse enregistrée pour ce filtre.')
          else
            for (final day in visible) _day(day),
        ],
      ),
    );
  }

  Widget _chip(String label, String value) {
    final selected = _asset == value;
    return LexaChip(
      label: label,
      selected: selected,
      onTap: () => setState(() => _asset = value),
    );
  }

  Widget _day(Map<String, dynamic> day) {
    final analyses = (day['analyses'] as List? ?? const [])
        .map((a) => Map<String, dynamic>.from(a as Map))
        .toList();
    if (analyses.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text('${day['label']}'.toUpperCase(),
                  key: ValueKey('lexa-day-${day['date']}'),
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      letterSpacing: .8,
                      fontWeight: FontWeight.w900)),
            ),
            Text('${analyses.length} analyse${analyses.length > 1 ? 's' : ''}',
                style: const TextStyle(color: lexaMuted, fontSize: 11.5)),
          ]),
          const SizedBox(height: 4),
          const Divider(height: 1, color: lexaDivider),
          for (final analysis in analyses) _analysis(analysis),
        ],
      ),
    );
  }

  Widget _analysis(Map<String, dynamic> analysis) {
    final levels = (analysis['levels'] as List? ?? const [])
        .map((l) => Map<String, dynamic>.from(l as Map))
        .toList();
    final summary = '${analysis['summary'] ?? ''}'.trim();
    final revalidate = analysis['requires_revalidation'] == true;
    return Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text('${analysis['asset']}',
                style: const TextStyle(
                    color: Colors.white, fontSize: 16, fontWeight: FontWeight.w900)),
            const SizedBox(width: 8),
            Text('${analysis['stance_fr'] ?? ''}',
                style: const TextStyle(
                    color: lexaBlue, fontSize: 12.5, fontWeight: FontWeight.w700)),
            const Spacer(),
            if ('${analysis['price_at_video_fr'] ?? ''}' != '—')
              Text('vidéo : ${analysis['price_at_video_fr']}',
                  style: const TextStyle(color: lexaMuted, fontSize: 11.5)),
          ]),
          if (summary.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(summary,
                style: const TextStyle(
                    color: Color(0xFFD5E1F2), fontSize: 13, height: 1.4)),
          ],
          for (final level in levels) _level(level),
          // An old or explicitly dated plan stays visible but says so: it
          // cannot pass for a current reading.
          if (revalidate)
            lexaNote('⚠️ Plan à revalider avant toute lecture actuelle.'),
        ],
      ),
    );
  }

  Widget _level(Map<String, dynamic> level) {
    final high = '${level['high_fr'] ?? ''}';
    final allocation = level['allocation_pct'];
    final inferred = level['basis'] == 'INFERRED';
    return Padding(
      padding: const EdgeInsets.only(top: 5, left: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ColorEmoji(emoji: '${level['emoji'] ?? '•'}', size: 13),
          const SizedBox(width: 7),
          Expanded(
            child: Text('${level['kind_fr'] ?? ''}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: lexaMuted, fontSize: 12.5)),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
                high.isEmpty
                    ? '${level['value_fr']}'
                    : '${level['value_fr']} – $high',
                textAlign: TextAlign.right,
                style: const TextStyle(
                    color: Colors.white, fontSize: 12.5, fontWeight: FontWeight.w700)),
          ),
          if (allocation is num) ...[
            const SizedBox(width: 6),
            Text('${allocation.round()} %',
                style: const TextStyle(color: lexaBlue, fontSize: 11.5)),
          ],
          if (inferred) ...[
            const SizedBox(width: 6),
            // Said in the video, or read from its context: the two are never
            // presented as the same thing.
            const Text('déduit',
                style: TextStyle(color: Color(0xFFE3C35A), fontSize: 10.5)),
          ],
        ],
      ),
    );
  }
}
