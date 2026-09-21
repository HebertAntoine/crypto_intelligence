/// 🎬 Lexa — Plans & analyses.
///
/// Organised like the Home's « À surveiller »: what to follow, by date, then
/// one card per crypto with its plan. Three views: Actifs, Calendrier,
/// Historique. Any number of cryptos — never only BTC / ETH / SOL.
///
/// Everything here comes from the local backend, which computed it. Lexa is an
/// external source: these plans never change the app's own ACHETER / ATTENDRE
/// / VENDRE.
library;

import 'package:flutter/material.dart';

import '../widgets/color_emoji.dart';
import '../widgets/mobile_kit.dart';
import 'lexa_client.dart';
import 'lexa_plan_page.dart';
import 'lexa_screen.dart';
import 'lexa_test_screen.dart';
import 'lexa_ui.dart';

const _mainAssets = ['BTC', 'ETH', 'SOL', 'XRP'];
const _typeFilters = {
  'BUY': 'Achat',
  'SELL': 'Vente',
  'CLOSE': 'Clôture',
  'TARGET': 'Objectif',
};
const _stateFilters = {
  'ACTIVE': 'Actifs',
  'DONE': 'Terminés',
  'INVALID': 'Invalidés',
};

class LexaHomeScreen extends StatefulWidget {
  final LexaClient client;

  const LexaHomeScreen({super.key, required this.client});

  @override
  State<LexaHomeScreen> createState() => _LexaHomeScreenState();
}

class _LexaHomeScreenState extends State<LexaHomeScreen> {
  String _view = 'ACTIVE';
  String _asset = 'ALL';
  String _state = 'ACTIVE';
  String? _type;
  late Future<Map<String, dynamic>> _data = _load();

  Future<Map<String, dynamic>> _load() => switch (_view) {
        'CALENDAR' => widget.client.calendar(),
        'HISTORY' => widget.client.plansHistory(),
        _ => widget.client.overview(),
      };

  void _reload() => setState(() => _data = _load());

  Future<void> _open(Widget page) async {
    await Navigator.of(context)
        .push(MaterialPageRoute<void>(builder: (_) => page));
    if (mounted) _reload();
  }

  bool _assetMatches(String asset) => switch (_asset) {
        'ALL' => true,
        'OTHERS' => !_mainAssets.contains(asset),
        _ => asset == _asset,
      };

  bool _stateMatches(String? lifecycle) => switch (_state) {
        'DONE' => lifecycle == 'COMPLETED' ||
            lifecycle == 'EXPIRED' ||
            lifecycle == 'SUPERSEDED',
        'INVALID' => lifecycle == 'INVALIDATED',
        _ => lifecycle == 'ACTIVE' ||
            lifecycle == 'WATCHING' ||
            lifecycle == 'TRIGGERED' ||
            lifecycle == null,
      };

  bool _typeMatches(String? category) => _type == null || category == _type;

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: LexaEmojiFonts(
          child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<Map<String, dynamic>>(
          future: _data,
          builder: (context, snap) {
            final children = <Widget>[
              _header(snap.data),
              const SizedBox(height: 14),
              _views(),
              const SizedBox(height: 12),
              _filters(),
              const SizedBox(height: 14),
            ];
            if (snap.hasError) {
              children.add(GlassPanel(
                borderColor: lexaOrange,
                child: Text('⚠️ ${snap.error}',
                    style: const TextStyle(color: Colors.white)),
              ));
            } else if (!snap.hasData) {
              children.add(const Padding(
                padding: EdgeInsets.all(40),
                child: Center(child: CircularProgressIndicator()),
              ));
            } else {
              children.addAll(switch (_view) {
                'CALENDAR' => _calendar(snap.data!),
                'HISTORY' => _history(snap.data!),
                _ => _active(snap.data!),
              });
            }
            return MobileScrollView(
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 170),
              children: children,
            );
          },
        ),
      )),
    );
  }

  Widget _header(Map<String, dynamic>? data) {
    final unread = (data?['unread_notifications'] as num?)?.toInt() ?? 0;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                ColorEmoji(emoji: '🎬', size: 30),
                SizedBox(width: 10),
                Text('Lexa',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 40,
                        fontWeight: FontWeight.w800,
                        height: 1.02)),
              ]),
              SizedBox(height: 6),
              Text('Plans & analyses',
                  style: TextStyle(color: mobileMuted, fontSize: 19)),
            ],
          ),
        ),
        _iconButton('🔔', 'Notifications',
            badge: unread,
            onTap: () => _open(LexaNotificationsPage(client: widget.client))),
        _iconButton('➕', 'Saisir une vidéo',
            onTap: () => _open(LexaEntryScreen(client: widget.client))),
        _iconButton('🧪', 'Tester une transcription',
            onTap: () => _open(LexaTestScreen(client: widget.client))),
      ],
    );
  }

  Widget _iconButton(String emoji, String tooltip,
          {int badge = 0, required VoidCallback onTap}) =>
      IconButton(
        tooltip: tooltip,
        onPressed: onTap,
        icon: Badge(
          isLabelVisible: badge > 0,
          label: Text('$badge'),
          child: ColorEmoji(emoji: emoji, size: 22),
        ),
      );

  Widget _views() => Row(
        children: [
          for (final v in const [
            ('ACTIVE', 'Actifs'),
            ('CALENDAR', 'Calendrier'),
            ('HISTORY', 'Historique'),
          ]) ...[
            Expanded(
              child: InkWell(
                key: ValueKey('lexa-view-${v.$1}'),
                onTap: () => setState(() {
                  _view = v.$1;
                  _data = _load();
                }),
                borderRadius: BorderRadius.circular(10),
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    color: _view == v.$1
                        ? mobileBlue.withValues(alpha: 0.22)
                        : const Color(0xFF0E1A28),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                        color: _view == v.$1 ? mobileBlue : mobileBorder),
                  ),
                  child: Text(v.$2,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: _view == v.$1
                              ? FontWeight.w800
                              : FontWeight.w600)),
                ),
              ),
            ),
            if (v.$1 != 'HISTORY') const SizedBox(width: 8),
          ],
        ],
      );

  Widget _filters() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final a in const ['ALL', ..._mainAssets, 'OTHERS'])
              LexaChip(
                label: a == 'ALL' ? 'Tout' : (a == 'OTHERS' ? 'Autres' : a),
                selected: _asset == a,
                onTap: () => setState(() => _asset = a),
              ),
          ]),
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: [
            if (_view != 'CALENDAR')
              for (final e in _stateFilters.entries)
                LexaChip(
                  label: e.value,
                  selected: _state == e.key,
                  onTap: () => setState(() => _state = e.key),
                ),
            if (_view != 'HISTORY')
              for (final e in _typeFilters.entries)
                LexaChip(
                  label: e.value,
                  selected: _type == e.key,
                  onTap: () =>
                      setState(() => _type = _type == e.key ? null : e.key),
                ),
          ]),
        ],
      );

  // --- Actifs ---------------------------------------------------------------

  List<Widget> _active(Map<String, dynamic> data) {
    final follow = [
      for (final r in (data['follow'] as List? ?? const []).cast<Map>())
        if (_assetMatches('${r['asset']}') &&
            _stateMatches(r['lifecycle'] as String?) &&
            _typeMatches(r['category'] as String?))
          r.cast<String, dynamic>(),
    ];
    final cards = [
      for (final c in (data['plans'] as List? ?? const []).cast<Map>())
        if (_assetMatches('${c['asset']}') &&
            _stateMatches(c['lifecycle'] as String?))
          c.cast<String, dynamic>(),
    ];
    if ((data['plans'] as List? ?? const []).isEmpty) return [_empty()];
    return [
      GlassPanel(
        key: const ValueKey('lexa-follow'),
        borderColor: const Color(0xFF245E90),
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const LexaSectionTitle(emoji: '👀', text: 'À suivre'),
            const SizedBox(height: 6),
            if (follow.isEmpty)
              lexaNote('Rien à suivre avec ces filtres.')
            else
              ..._bucketed(follow, (r) => _followRow(r)),
          ],
        ),
      ),
      const SizedBox(height: 16),
      const Padding(
        padding: EdgeInsets.only(left: 4, bottom: 10),
        child: LexaSectionTitle(emoji: '📊', text: 'Plans actifs'),
      ),
      for (final c in cards) ...[_planCard(c), const SizedBox(height: 14)],
      lexaNote('${data['rule'] ?? ''}'),
    ];
  }

  List<Widget> _bucketed(List<Map<String, dynamic>> rows,
      Widget Function(Map<String, dynamic>) row) {
    const labels = {
      'TODAY': "AUJOURD'HUI",
      'TOMORROW': 'DEMAIN',
      'THIS_WEEK': 'CETTE SEMAINE',
      'LATER': 'PLUS TARD',
      'PAST': 'PASSÉ',
    };
    final out = <Widget>[];
    for (final key in labels.keys) {
      final group = rows.where((r) => r['bucket'] == key).toList();
      if (key == 'PAST') {
        group.sort((a, b) => '${b['at']}'.compareTo('${a['at']}'));
      }
      if (group.isEmpty) continue;
      out.add(Padding(
        padding: const EdgeInsets.only(top: 10, bottom: 2),
        child: Text(labels[key]!,
            style: const TextStyle(
                color: lexaMuted,
                fontSize: 12,
                letterSpacing: .8,
                fontWeight: FontWeight.w800)),
      ));
      for (var i = 0; i < group.length; i++) {
        if (i > 0) out.add(const Divider(height: 1, color: lexaDivider));
        out.add(row(group[i]));
      }
    }
    return out;
  }

  Widget _followRow(Map<String, dynamic> r) => InkWell(
        key: ValueKey('lexa-follow-${r['asset']}'),
        onTap: () => _open(LexaPlanPage(
            client: widget.client, analysisId: r['analysis_id'] as int)),
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 11),
          child: Row(
            children: [
              LexaDateBadge(date: parseIso(r['at'])),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      ColorEmoji(emoji: '${r['emoji']}', size: 14),
                      const SizedBox(width: 6),
                      Text('${r['asset']}',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 15,
                              fontWeight: FontWeight.w800)),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text('${r['label']}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                color: emojiColor('${r['emoji']}'),
                                fontSize: 12.5,
                                fontWeight: FontWeight.w800)),
                      ),
                    ]),
                    const SizedBox(height: 3),
                    Text('${r['headline']}',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            color: lexaWhite, fontSize: 13, height: 1.3)),
                    if (r['key_level'] != null)
                      Text('${r['key_level']}',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                              fontWeight: FontWeight.w700)),
                    if (r['countdown'] != null)
                      Text('🕯️ ${r['countdown']}',
                          style:
                              const TextStyle(color: lexaMuted, fontSize: 12)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: mobileBlue),
            ],
          ),
        ),
      );

  Widget _planCard(Map<String, dynamic> c) {
    final now = (c['now'] as Map).cast<String, dynamic>();
    String levels(Object? v) =>
        (v as List? ?? const []).map((x) => priceOf(x)).join('\n');
    final conc = (c['concordance'] as Map?)?.cast<String, dynamic>() ?? {};
    return GlassPanel(
      key: ValueKey('lexa-card-${c['asset']}'),
      borderColor: toneColor('${now['tone']}').withValues(alpha: .7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text('${c['asset']}',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w800)),
            const Spacer(),
            Text('#${c['version']}',
                style: const TextStyle(color: lexaMuted, fontSize: 13)),
          ]),
          const SizedBox(height: 8),
          LexaStatusPill(emoji: '${now['emoji']}', label: '${now['label']}'),
          const SizedBox(height: 10),
          LexaLine('Prix actuel', priceOf(c['price'])),
          if ((c['buy'] as List? ?? const []).isNotEmpty)
            LexaLine('↓ Achat', levels(c['buy']), color: lexaGreen),
          if ((c['confirmation'] as List? ?? const []).isNotEmpty)
            LexaLine('↑ Confirmation', levels(c['confirmation'])),
          if ((c['targets'] as List? ?? const []).isNotEmpty)
            LexaLine('🎯 Objectif', levels(c['targets']), color: lexaRed),
          if (c['waiting_close'] != null)
            LexaLine('⏳ Attente', '${c['waiting_close']}', color: lexaOrange),
          if (c['revision'] != null) LexaLine('Révision', '${c['revision']}'),
          if (conc['label'] != null)
            LexaLine('🔬 Concordance', '${conc['emoji']} ${conc['label']}'),
          LexaLine('Dernière mise à jour', dayMonth(parseIso(c['updated_at']))),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerRight,
            child: OutlinedButton(
              onPressed: () => _open(LexaPlanPage(
                  client: widget.client, analysisId: c['analysis_id'] as int)),
              child: const Text('Voir le plan'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _empty() => GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const LexaSectionTitle(emoji: '🎬', text: 'Aucune analyse Lexa'),
            const SizedBox(height: 10),
            const Text(
              'Ajoute une vidéo : saisis les niveaux (➕), ou colle une transcription '
              'et vérifie le test (🧪) avant de l\'importer. L\'application suit '
              'ensuite chaque niveau, les clôtures et les dates.',
              style: TextStyle(color: lexaWhite, fontSize: 14, height: 1.4),
            ),
            const SizedBox(height: 12),
            Wrap(spacing: 10, children: [
              FilledButton(
                  onPressed: () =>
                      _open(LexaEntryScreen(client: widget.client)),
                  child: lexaLabel('➕ Saisir une vidéo')),
              OutlinedButton(
                  onPressed: () => _open(LexaTestScreen(client: widget.client)),
                  child: lexaLabel('🧪 Tester une transcription')),
            ]),
          ],
        ),
      );

  // --- Calendrier -----------------------------------------------------------

  List<Widget> _calendar(Map<String, dynamic> data) {
    final items = [
      for (final i in (data['items'] as List? ?? const []).cast<Map>())
        if ((i['asset'] == 'MARCHÉ' || _assetMatches('${i['asset']}')) &&
            _typeMatches(_type == null ? null : i['category'] as String?))
          i.cast<String, dynamic>(),
    ];
    return [
      GlassPanel(
        borderColor: const Color(0xFF245E90),
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const LexaSectionTitle(emoji: '📅', text: 'Calendrier'),
            lexaNote(
                'Heures de Paris. Clôtures : bougies Binance, à heure fixe UTC.'),
            if (items.isEmpty) lexaNote('Aucune date avec ces filtres.'),
            ..._bucketed(items, _calendarRow),
          ],
        ),
      ),
    ];
  }

  Widget _calendarRow(Map<String, dynamic> i) {
    final at = parseIso(i['at']);
    final id = i['analysis_id'];
    return InkWell(
      onTap: id is int
          ? () => _open(LexaPlanPage(client: widget.client, analysisId: id))
          : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(children: [
          LexaDateBadge(date: at),
          SizedBox(
            width: 48,
            child: Text(
                at == null
                    ? ''
                    : '${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}',
                textAlign: TextAlign.center,
                style: const TextStyle(color: lexaMuted, fontSize: 12.5)),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  ColorEmoji(emoji: '${i['emoji']}', size: 13),
                  const SizedBox(width: 6),
                  Text('${i['asset']}',
                      style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w800)),
                ]),
                Text('${i['title']}',
                    style: const TextStyle(color: lexaWhite, fontSize: 13)),
                if (i['level'] != null)
                  Text(priceOf(i['level']),
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13,
                          fontWeight: FontWeight.w700)),
                if (i['detail'] != null)
                  Text('${i['detail']}',
                      style: const TextStyle(color: lexaMuted, fontSize: 12)),
              ],
            ),
          ),
        ]),
      ),
    );
  }

  // --- Historique -----------------------------------------------------------

  List<Widget> _history(Map<String, dynamic> data) {
    final rows = [
      for (final a in (data['analyses'] as List? ?? const []).cast<Map>())
        if (_assetMatches('${a['asset']}') &&
            (_state == 'ACTIVE' || _stateMatches(a['lifecycle'] as String?)))
          a.cast<String, dynamic>(),
    ];
    return [
      GlassPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const LexaSectionTitle(emoji: '📚', text: 'Toutes les analyses'),
            lexaNote('Chaque vidéo est une version. Aucune n\'est écrasée.'),
            const SizedBox(height: 6),
            if (rows.isEmpty) lexaNote('Aucune analyse.'),
            for (var i = 0; i < rows.length; i++) ...[
              if (i > 0) const Divider(height: 1, color: lexaDivider),
              _historyRow(rows[i]),
            ],
          ],
        ),
      ),
    ];
  }

  Widget _historyRow(Map<String, dynamic> a) {
    final now = (a['now'] as Map).cast<String, dynamic>();
    final revision = (a['revision'] as Map?)?.cast<String, dynamic>();
    return InkWell(
      onTap: () => _open(LexaPlanPage(
          client: widget.client, analysisId: a['analysis_id'] as int)),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(children: [
          LexaDateBadge(date: parseIso(a['published_at'])),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${a['asset']} · Analyse Lexa #${a['version']}',
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w800)),
                Text('${a['video_title']}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: lexaWhite, fontSize: 13)),
                const SizedBox(height: 4),
                LexaStatusPill(
                    emoji: '${now['emoji']}', label: '${a['lifecycle_fr']}'),
                if (revision != null) lexaNote('${revision['label']}'),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: mobileBlue),
        ]),
      ),
    );
  }
}

/// 🔔 In-app notifications, newest first. Opening them marks them read.
class LexaNotificationsPage extends StatefulWidget {
  final LexaClient client;

  const LexaNotificationsPage({super.key, required this.client});

  @override
  State<LexaNotificationsPage> createState() => _LexaNotificationsPageState();
}

class _LexaNotificationsPageState extends State<LexaNotificationsPage> {
  late final Future<Map<String, dynamic>> _data = widget.client.notifications();

  @override
  void initState() {
    super.initState();
    _data.then((_) => widget.client.markNotificationsRead()).ignore();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFF06101C),
        appBar: AppBar(
            backgroundColor: const Color(0xFF06101C),
            title: lexaLabel('🔔 Notifications Lexa')),
        body: LexaEmojiFonts(
            child: FutureBuilder<Map<String, dynamic>>(
          future: _data,
          builder: (context, snap) {
            if (snap.hasError) return Center(child: Text('⚠️ ${snap.error}'));
            if (!snap.hasData) {
              return const Center(child: CircularProgressIndicator());
            }
            final rows =
                (snap.data!['notifications'] as List? ?? const []).cast<Map>();
            if (rows.isEmpty) {
              return const Center(
                  child: Text('Aucune notification.',
                      style: TextStyle(color: lexaMuted)));
            }
            return ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: rows.length,
              separatorBuilder: (_, __) =>
                  const Divider(height: 1, color: lexaDivider),
              itemBuilder: (context, i) {
                final n = rows[i];
                final at = parseIso(n['created_at']);
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: LexaDateBadge(date: at),
                  title: Text('${n['message']}',
                      style: TextStyle(
                          color: Colors.white,
                          fontWeight: n['read'] == true
                              ? FontWeight.w500
                              : FontWeight.w800)),
                  subtitle: Text(
                      at == null
                          ? ''
                          : '${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}',
                      style: const TextStyle(color: lexaMuted)),
                  onTap: n['analysis_id'] is int
                      ? () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                              builder: (_) => LexaPlanPage(
                                  client: widget.client,
                                  analysisId: n['analysis_id'] as int)))
                      : null,
                );
              },
            );
          },
        )),
      );
}
