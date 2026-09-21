/// 🎬 Lexa - the member's notes on each video, rendered cleanly.
///
/// The member watches the video on the official platform and records the
/// levels it announced. This screen renders them per date and per crypto,
/// follows each level on the prices that came after, and simulates the
/// scenario on the capital of their choice.
///
/// Everything here is « Ce que dit Lexa ». Our own reading sits in a separate
/// block and neither changes the other.
library;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'lexa_client.dart';
import 'lexa_models.dart';
import 'lexa_test_screen.dart';

const _panel = Color(0xFF0E1A28);
const _border = Color(0xFF245386);
const _muted = Color(0xFFB7C6DF);
const _lexaTint = Color(0xFFB083F0);

const _entryKinds = {'BUY_ZONE', 'REINFORCEMENT'};
const _targetKinds = {'TARGET', 'TAKE_PROFIT'};
const _watchKinds = {'CONFIRMATION', 'INVALIDATION'};

Widget _card({required Widget child, Color border = _border}) => Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _panel,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: border, width: 1.2),
      ),
      child: child,
    );

Widget _title(String text) => Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Text(text,
          style: const TextStyle(
              color: AppColors.text,
              fontSize: 17,
              fontWeight: FontWeight.w700)),
    );

Widget _line(String label, String value, {Color? color}) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
              child: Text(label,
                  style: const TextStyle(color: _muted, fontSize: 14))),
          const SizedBox(width: 12),
          Flexible(
            child: Text(value,
                textAlign: TextAlign.right,
                style: TextStyle(
                    color: color ?? AppColors.text,
                    fontSize: 14,
                    fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );

Widget _small(String text, {Color color = _muted}) => Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(text, style: TextStyle(color: color, fontSize: 12.5)),
    );

Widget _page(String title, List<Widget> children, {List<Widget>? actions}) =>
    Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        title: Text(title),
        actions: actions,
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
            children: children,
          ),
        ),
      ),
    );

class _Loader<T> extends StatelessWidget {
  final Future<T> future;
  final Widget Function(T data) builder;

  const _Loader({required this.future, required this.builder});

  @override
  Widget build(BuildContext context) => FutureBuilder<T>(
        future: future,
        builder: (context, snap) {
          if (snap.hasError) {
            return _card(
              border: AppColors.warn,
              child: Text('⚠️ ${snap.error}',
                  style: const TextStyle(color: AppColors.text)),
            );
          }
          if (!snap.hasData) {
            return const Padding(
              padding: EdgeInsets.all(32),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          return builder(snap.data as T);
        },
      );
}

// --- list by date -----------------------------------------------------------

class LexaHomeScreen extends StatefulWidget {
  final LexaClient client;

  const LexaHomeScreen({super.key, required this.client});

  @override
  State<LexaHomeScreen> createState() => _LexaHomeScreenState();
}

class _LexaHomeScreenState extends State<LexaHomeScreen> {
  late Future<Map<String, dynamic>> _videos = widget.client.videos();
  String? _asset;

  void _reload() => setState(() => _videos = widget.client.videos());

  Future<void> _open(Widget page) async {
    await Navigator.of(context)
        .push(MaterialPageRoute<void>(builder: (_) => page));
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    return _page('🎬 Lexa', [
      _card(
        border: _lexaTint,
        child: const Text(
          'Tes notes des vidéos Lexa, classées par date et par crypto. '
          'Source externe : elles ne modifient jamais les décisions de l\'application.',
          style: TextStyle(color: _muted, fontSize: 14, height: 1.35),
        ),
      ),
      _Loader<Map<String, dynamic>>(
        future: _videos,
        builder: (data) {
          final videos = [
            for (final v in (data['videos'] as List? ?? const []))
              LexaVideoEntry.fromJson((v as Map).cast<String, dynamic>()),
          ];
          if (videos.isEmpty) return _empty();
          final assets = <String>{
            for (final v in videos)
              for (final a in v.assets) a.asset
          }.toList()
            ..sort();
          final shown = _asset == null
              ? videos
              : [
                  for (final v in videos)
                    if (v.assets.any((a) => a.asset == _asset)) v
                ];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  ChoiceChip(
                    label: const Text('Toutes'),
                    selected: _asset == null,
                    onSelected: (_) => setState(() => _asset = null),
                  ),
                  for (final a in assets)
                    ChoiceChip(
                      label: Text(a),
                      selected: _asset == a,
                      onSelected: (_) => setState(() => _asset = a),
                    ),
                ],
              ),
              if (_asset != null)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton(
                    onPressed: () => _open(LexaHistoryScreen(
                        client: widget.client, asset: _asset!)),
                    child: Text('📜 Historique complet $_asset'),
                  ),
                ),
              const SizedBox(height: 10),
              ..._byDate(shown),
            ],
          );
        },
      ),
    ], actions: [
      IconButton(
        tooltip: 'Tester une vidéo',
        icon: const Text('🧪', style: TextStyle(fontSize: 20)),
        onPressed: () => _open(LexaTestScreen(client: widget.client)),
      ),
      IconButton(
        tooltip: 'Capital simulé',
        icon: const Text('⚙️', style: TextStyle(fontSize: 20)),
        onPressed: () => showLexaCapitalDialog(context, widget.client)
            .then((_) => _reload()),
      ),
      IconButton(
        tooltip: 'Ajouter une vidéo',
        icon: const Icon(Icons.add_circle_outline),
        onPressed: () => _open(LexaEntryScreen(client: widget.client)),
      ),
    ]);
  }

  Widget _empty() => _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _title('Aucune vidéo enregistrée'),
            const Text(
              '1. Regarde la vidéo sur la plateforme Lexa.\n'
              '2. Appuie sur ➕ et note la crypto, les zones, la confirmation, '
              'l\'invalidation et les objectifs, avec le minutage.\n'
              '3. L\'application suit chaque niveau sur les prix qui suivent '
              'et simule le scénario sur ton capital.',
              style: TextStyle(color: _muted, fontSize: 14, height: 1.45),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: () => _open(LexaEntryScreen(client: widget.client)),
              icon: const Icon(Icons.add),
              label: const Text('Ajouter une vidéo'),
            ),
          ],
        ),
      );

  List<Widget> _byDate(List<LexaVideoEntry> videos) {
    final out = <Widget>[];
    String? day;
    for (final video in videos) {
      final label = fmtDateFr(video.publishedAt, time: false);
      if (label != day) {
        day = label;
        out.add(Padding(
          padding: const EdgeInsets.only(top: 6, bottom: 8),
          child: Text('📅 $label',
              style: const TextStyle(
                  color: _muted, fontSize: 13, fontWeight: FontWeight.w700)),
        ));
      }
      out.add(_card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(video.title,
                style: const TextStyle(
                    color: AppColors.text,
                    fontSize: 16,
                    fontWeight: FontWeight.w700)),
            _small('Publiée le ${fmtDateFr(video.publishedAt)}'),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final a in video.assets)
                  if (_asset == null || a.asset == _asset)
                    ActionChip(
                      avatar:
                          Text((lexaStances[a.stance] ?? '⚪').split(' ').first),
                      label: Text(a.asset),
                      onPressed: () => _open(LexaReportScreen(
                          client: widget.client, analysisId: a.analysisId)),
                    ),
              ],
            ),
          ],
        ),
      ));
    }
    return out;
  }
}

// --- one crypto, one video ----------------------------------------------------

class LexaReportScreen extends StatefulWidget {
  final LexaClient client;
  final int analysisId;

  const LexaReportScreen(
      {super.key, required this.client, required this.analysisId});

  @override
  State<LexaReportScreen> createState() => _LexaReportScreenState();
}

class _LexaReportScreenState extends State<LexaReportScreen> {
  late Future<Map<String, dynamic>> _report =
      widget.client.analysis(widget.analysisId);
  Future<Map<String, dynamic>>? _compare;

  void _reload() =>
      setState(() => _report = widget.client.analysis(widget.analysisId));

  @override
  Widget build(BuildContext context) {
    return _page('🎬 Analyse Lexa', [
      _Loader<Map<String, dynamic>>(
        future: _report,
        builder: (json) {
          final report = LexaReport.fromJson(json);
          return LexaReportView(
            report: report,
            onCorrect: _correct,
            onCapital: () => showLexaCapitalDialog(context, widget.client,
                    asset: report.asset, current: report.capitalEur)
                .then((_) => _reload()),
            onHistory: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => LexaHistoryScreen(
                    client: widget.client, asset: report.asset))),
            comparison: _comparison(),
          );
        },
      ),
    ]);
  }

  Widget _comparison() {
    if (_compare == null) {
      return _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _title('🔍 Lexa vs données'),
            const Text(
              'Met côte à côte la vidéo et la lecture de l\'application. '
              'Aucune des deux ne corrige l\'autre.',
              style: TextStyle(color: _muted, fontSize: 14),
            ),
            const SizedBox(height: 10),
            OutlinedButton(
              onPressed: () => setState(
                  () => _compare = widget.client.compare(widget.analysisId)),
              child: const Text('Comparer'),
            ),
          ],
        ),
      );
    }
    return _Loader<Map<String, dynamic>>(
      future: _compare!,
      builder: (data) => LexaComparisonCard(data: data),
    );
  }

  Future<void> _correct(LexaLevel level) async {
    final controller = TextEditingController();
    final value = await showDialog<double>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('✏️ Corriger ${level.kindLabel}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                'Valeur notée à l\'origine : ${fmtPrice(level.originalValue)}'),
            const SizedBox(height: 4),
            const Text('Elle reste conservée à côté de la correction.',
                style: TextStyle(fontSize: 12, color: _muted)),
            TextField(
              controller: controller,
              autofocus: true,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Valeur corrigée'),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Annuler')),
          FilledButton(
              onPressed: () =>
                  Navigator.pop(context, parseFrNumber(controller.text)),
              child: const Text('Enregistrer')),
        ],
      ),
    );
    if (value == null || !mounted) return;
    try {
      await widget.client.correctLevel(level.id, value);
      _reload();
    } on LexaException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

/// The rendered analysis. Pure: it draws what the backend computed.
class LexaReportView extends StatelessWidget {
  final LexaReport report;
  final void Function(LexaLevel level)? onCorrect;
  final VoidCallback? onCapital;
  final VoidCallback? onHistory;
  final Widget? comparison;

  const LexaReportView({
    super.key,
    required this.report,
    this.onCorrect,
    this.onCapital,
    this.onHistory,
    this.comparison,
  });

  @override
  Widget build(BuildContext context) {
    final entries = report.ofKinds(_entryKinds);
    final watch = report.ofKinds(_watchKinds);
    final targets = report.ofKinds(_targetKinds);
    final others = [
      for (final l in report.levels)
        if (!_entryKinds.contains(l.kind) &&
            !_watchKinds.contains(l.kind) &&
            !_targetKinds.contains(l.kind))
          l
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _header(),
        if (entries.isNotEmpty) _levels('🟢 Zones d\'entrée', entries),
        if (watch.isNotEmpty) _levels('🚀 Confirmation et invalidation', watch),
        if (targets.isNotEmpty) _levels('🎯 Objectifs', targets),
        if (others.isNotEmpty) _levels('📝 Autres niveaux cités', others),
        _simulation(),
        if (comparison != null) comparison!,
        _trace(),
        if (onHistory != null)
          OutlinedButton(
            onPressed: onHistory,
            child: Text('📜 Tous les scénarios ${report.asset}'),
          ),
      ],
    );
  }

  Widget _header() {
    final move = report.priceAtVideo != null &&
            report.currentPrice != null &&
            report.priceAtVideo! > 0
        ? (report.currentPrice! / report.priceAtVideo! - 1) * 100
        : null;
    return _card(
      border: _lexaTint,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(report.asset,
                  style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 28,
                      fontWeight: FontWeight.w800)),
              const Spacer(),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: _lexaTint),
                ),
                child: const Text('Ce que dit Lexa',
                    style: TextStyle(color: _lexaTint, fontSize: 12)),
              ),
            ],
          ),
          _small(report.videoTitle),
          _small('Vidéo du ${fmtDateFr(report.publishedAt)}'),
          const SizedBox(height: 10),
          _line('Position annoncée',
              '${report.stanceEmoji} ${report.stanceLabel}'),
          _line('Prix au moment de la vidéo', fmtPrice(report.priceAtVideo)),
          _line(
              'Prix actuel',
              report.currentPrice == null
                  ? 'Indisponible'
                  : '${fmtPrice(report.currentPrice)}'
                      '${move == null ? '' : '  (${move >= 0 ? '+' : ''}${move.toStringAsFixed(1).replaceAll('.', ',')} %)'}'),
          if (report.summary.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(report.summary,
                style: const TextStyle(
                    color: AppColors.text, fontSize: 14, height: 1.4)),
          ],
        ],
      ),
    );
  }

  Widget _levels(String title, List<LexaLevel> levels) => _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _title(title),
            for (final level in levels) _level(level),
          ],
        ),
      );

  Widget _level(LexaLevel level) {
    final state = level.state;
    final dates = [
      if (state.firstTouchedAt != null)
        'Premier contact ${fmtDateFr(state.firstTouchedAt)}',
      if (state.confirmedAt != null) 'Confirmé ${fmtDateFr(state.confirmedAt)}',
      if (state.invalidatedAt != null)
        'Invalidé ${fmtDateFr(state.invalidatedAt)}',
    ];
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF101E2D),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
            color: level.toVerify ? AppColors.warn : const Color(0xFF1A3149)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('${level.emoji} ${level.kindLabel}',
                    style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 15,
                        fontWeight: FontWeight.w600)),
              ),
              Text(fmtPrice(level.value),
                  style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 16,
                      fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 10,
            runSpacing: 4,
            children: [
              Text('${state.emoji} ${state.label}',
                  style: const TextStyle(color: AppColors.text, fontSize: 13)),
              if (level.allocationEur != null)
                Text(
                    '💶 ${fmtEur(level.allocationEur)}'
                    '${level.allocationPct != null ? ' (${level.allocationPct!.toStringAsFixed(0)} %)' : ''}',
                    style: const TextStyle(color: _muted, fontSize: 13)),
              if (level.timestamp != null)
                Text('🎬 Voir à ${level.timestamp}',
                    style: const TextStyle(color: mobileLink, fontSize: 13)),
            ],
          ),
          if (_watchKinds.contains(level.kind))
            _small('Condition : ${level.conditionLabel}'),
          if (state.note.isNotEmpty) _small(state.note),
          for (final d in dates) _small(d),
          if (level.toVerify)
            _small('⚠️ À vérifier : valeur incertaine dans la vidéo.',
                color: AppColors.warn),
          if (level.isCorrected)
            _small('✏️ Corrigé le ${fmtDateFr(level.correctedAt)} · '
                'valeur d\'origine ${fmtPrice(level.originalValue)}'),
          if (level.sourceText.isNotEmpty) _small('« ${level.sourceText} »'),
          if (onCorrect != null)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => onCorrect!(level),
                child: const Text('✏️ Modifier'),
              ),
            ),
        ],
      ),
    );
  }

  Widget _simulation() {
    final sim = report.simulation;
    final perf = sim.performancePct;
    final perfColor = perf == null
        ? AppColors.text
        : (perf >= 0 ? AppColors.measured : AppColors.bad);
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                  child: _title(
                      '💶 Simulation sur ${fmtEur(sim.capitalEur).replaceAll(',00', '')}')),
              if (onCapital != null)
                TextButton(onPressed: onCapital, child: const Text('Modifier')),
            ],
          ),
          _line('Montant investi', fmtEur(sim.executedEur)),
          _line('Montant en attente', fmtEur(sim.remainingEur)),
          _line('Prix moyen d\'achat', fmtPrice(sim.averagePrice)),
          _line('Achats exécutés', '${sim.fillCount}'),
          _line('Objectifs atteints', '${sim.targetsHit.length}'),
          if (sim.realisedEur > 0)
            _line('Gains encaissés', fmtEur(sim.realisedEur)),
          _line('Valeur actuelle', fmtEur(sim.currentValueEur)),
          _line(
              'Performance',
              perf == null
                  ? 'Aucun achat exécuté'
                  : '${perf >= 0 ? '+' : ''}${perf.toStringAsFixed(2).replaceAll('.', ',')} %',
              color: perfColor),
          if (sim.invalidationReached)
            _small('⚠️ L\'invalidation annoncée a été atteinte.',
                color: AppColors.warn),
          for (final a in sim.assumptions) _small('ℹ️ $a'),
          _small(sim.disclaimer),
        ],
      ),
    );
  }

  Widget _trace() => _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _title('🧾 Traçabilité'),
            _line('Source', report.source),
            _line('Vidéo', report.videoTitle),
            _line('Publiée', fmtDateFr(report.publishedAt)),
            _line('Enregistrée', fmtDateFr(report.processedAt)),
            if (report.sourceRef.isNotEmpty)
              _line('Référence', report.sourceRef),
            _line('Saisie', 'Notes manuelles'),
            _small(report.note),
          ],
        ),
      );
}

const mobileLink = Color(0xFF7CB7FF);

class LexaComparisonCard extends StatelessWidget {
  final Map<String, dynamic> data;

  const LexaComparisonCard({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    final lexa =
        LexaReport.fromJson((data['lexa'] as Map).cast<String, dynamic>());
    final ours = (data['ours'] as Map?)?.cast<String, dynamic>();
    Map<String, dynamic> part(String key) =>
        ((ours?[key] as Map?) ?? const {}).cast<String, dynamic>();
    const actions = {
      'BUY': '🟢 Achat',
      'WAIT': '🟠 Attente',
      'SELL': '🔴 Vente'
    };
    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _title('🔍 Lexa vs données'),
          const Text('🎬 Ce que dit Lexa',
              style: TextStyle(color: _lexaTint, fontWeight: FontWeight.w700)),
          _line('Position', '${lexa.stanceEmoji} ${lexa.stanceLabel}'),
          _line('Vidéo du', fmtDateFr(lexa.publishedAt)),
          const SizedBox(height: 12),
          const Text('📊 Ce que montrent nos données',
              style: TextStyle(color: mobileLink, fontWeight: FontWeight.w700)),
          if (ours == null)
            _small(
                data['ours_note'] as String? ?? 'Aucune comparaison possible.')
          else ...[
            _line('Décision (7 jours)',
                actions[ours['action']] ?? '${ours['action'] ?? '—'}'),
            _line('Tendance',
                '${part('trend')['emoji'] ?? ''} ${part('trend')['label'] ?? '—'}'),
            _line('Risque',
                '${part('risk')['emoji'] ?? ''} ${part('risk')['label'] ?? '—'}'),
            if (ours['sentence'] is String) _small(ours['sentence'] as String),
          ],
          const SizedBox(height: 8),
          _small(data['rule'] as String? ?? ''),
        ],
      ),
    );
  }
}

// --- history ------------------------------------------------------------------

class LexaHistoryScreen extends StatelessWidget {
  final LexaClient client;
  final String asset;

  const LexaHistoryScreen(
      {super.key, required this.client, required this.asset});

  @override
  Widget build(BuildContext context) {
    return _page('📜 Historique $asset', [
      _Loader<Map<String, dynamic>>(
        future: client.history(asset),
        builder: (data) {
          final reports = [
            for (final r in (data['analyses'] as List? ?? const []))
              LexaReport.fromJson((r as Map).cast<String, dynamic>()),
          ];
          if (reports.isEmpty) {
            return _card(child: const Text('Aucun scénario enregistré.'));
          }
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _small('Chaque vidéo est un scénario distinct : '
                  'un nouveau ne remplace jamais le précédent.'),
              const SizedBox(height: 10),
              for (final r in reports) _row(context, r),
            ],
          );
        },
      ),
    ]);
  }

  Widget _row(BuildContext context, LexaReport r) {
    final entry = r.ofKinds(_entryKinds);
    final perf = r.simulation.performancePct;
    return InkWell(
      onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) =>
              LexaReportScreen(client: client, analysisId: r.analysisId))),
      child: _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${fmtDateFr(r.publishedAt, time: false)} · ${r.videoTitle}',
                style: const TextStyle(
                    color: AppColors.text, fontWeight: FontWeight.w700)),
            _line('Position', '${r.stanceEmoji} ${r.stanceLabel}'),
            if (entry.isNotEmpty)
              _line('Entrées', entry.map((l) => fmtPrice(l.value)).join(' · ')),
            _line('Objectifs atteints',
                '${r.simulation.targetsHit.length} / ${r.ofKinds(_targetKinds).length}'),
            _line(
                'Simulation',
                perf == null
                    ? 'Aucun achat exécuté'
                    : '${perf >= 0 ? '+' : ''}${perf.toStringAsFixed(2).replaceAll('.', ',')} %'),
          ],
        ),
      ),
    );
  }
}

// --- capital ------------------------------------------------------------------

Future<void> showLexaCapitalDialog(BuildContext context, LexaClient client,
    {String? asset, double? current}) async {
  final controller = TextEditingController(
      text: current == null ? '' : current.toStringAsFixed(0));
  final value = await showDialog<double>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(asset == null
          ? '⚙️ Capital simulé par crypto'
          : '⚙️ Capital simulé pour $asset'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
              'Les montants de chaque zone suivent le capital. '
              'Les niveaux de prix ne changent pas.',
              style: TextStyle(fontSize: 13, color: _muted)),
          TextField(
            controller: controller,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
                labelText: 'Capital (€)', hintText: '100'),
          ),
        ],
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Annuler')),
        FilledButton(
            onPressed: () =>
                Navigator.pop(context, parseFrNumber(controller.text)),
            child: const Text('Enregistrer')),
      ],
    ),
  );
  if (value == null) return;
  try {
    await client.setCapital(value, asset: asset);
  } on LexaException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    }
  }
}

// --- manual entry ---------------------------------------------------------------

class _LevelDraft {
  String kind;
  final value = TextEditingController();
  final allocation = TextEditingController();
  final timestamp = TextEditingController();
  final source = TextEditingController();
  String condition = 'UNKNOWN';
  bool toVerify = false;

  _LevelDraft(this.kind);
}

class _AssetDraft {
  final asset = TextEditingController();
  final price = TextEditingController();
  final summary = TextEditingController();
  String stance = 'UNSPECIFIED';
  final levels = <_LevelDraft>[_LevelDraft('BUY_ZONE')];
}

class LexaEntryScreen extends StatefulWidget {
  final LexaClient client;
  final DateTime? now;

  const LexaEntryScreen({super.key, required this.client, this.now});

  @override
  State<LexaEntryScreen> createState() => _LexaEntryScreenState();
}

class _LexaEntryScreenState extends State<LexaEntryScreen> {
  final _title = TextEditingController();
  final _ref = TextEditingController();
  late final _date =
      TextEditingController(text: _fmtInput(widget.now ?? DateTime.now()));
  final _assets = <_AssetDraft>[_AssetDraft()];
  String? _error;
  bool _saving = false;

  static String _fmtInput(DateTime d) {
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(d.day)}/${two(d.month)}/${d.year} ${two(d.hour)}:${two(d.minute)}';
  }

  static DateTime? _parseInput(String raw) {
    final m =
        RegExp(r'^\s*(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?\s*$')
            .firstMatch(raw);
    if (m == null) return null;
    return DateTime(int.parse(m[3]!), int.parse(m[2]!), int.parse(m[1]!),
        int.parse(m[4] ?? '0'), int.parse(m[5] ?? '0'));
  }

  /// The request body, or a French message saying what is missing.
  (Map<String, dynamic>?, String?) _body() {
    if (_title.text.trim().isEmpty) {
      return (null, 'Le titre de la vidéo est obligatoire.');
    }
    final date = _parseInput(_date.text);
    if (date == null) {
      return (null, 'Date illisible (format JJ/MM/AAAA HH:MM).');
    }
    final assets = <Map<String, dynamic>>[];
    for (final a in _assets) {
      final name = a.asset.text.trim().toUpperCase();
      if (name.isEmpty) return (null, 'Indique la crypto de chaque bloc.');
      final levels = <Map<String, dynamic>>[];
      for (final l in a.levels) {
        if (l.value.text.trim().isEmpty) continue;
        final value = parseFrNumber(l.value.text);
        if (value == null || value <= 0) {
          return (null, '$name : valeur illisible « ${l.value.text} ».');
        }
        final pct = parseFrNumber(l.allocation.text);
        if (l.allocation.text.trim().isNotEmpty && pct == null) {
          return (
            null,
            '$name : allocation illisible « ${l.allocation.text} ».'
          );
        }
        levels.add({
          'kind': l.kind,
          'value': value,
          'allocation_pct': pct,
          'timestamp':
              l.timestamp.text.trim().isEmpty ? null : l.timestamp.text.trim(),
          'source_text': l.source.text.trim(),
          'condition': l.condition,
          'confidence': l.toVerify ? 'LOW' : 'HIGH',
        });
      }
      final price = parseFrNumber(a.price.text);
      assets.add({
        'asset': name,
        'price_at_video': price,
        'stance': a.stance,
        'summary': a.summary.text.trim(),
        'levels': levels,
      });
    }
    return (
      {
        'title': _title.text.trim(),
        'published_at': date.toUtc().toIso8601String(),
        'source_ref': _ref.text.trim(),
        'assets': assets,
      },
      null
    );
  }

  Future<void> _save() async {
    final (body, error) = _body();
    if (body == null) {
      setState(() => _error = error);
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    try {
      await widget.client.createVideo(body);
      if (mounted) Navigator.of(context).pop();
    } on LexaException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  InputDecoration _dec(String label, {String? hint}) =>
      InputDecoration(labelText: label, hintText: hint, isDense: true);

  @override
  Widget build(BuildContext context) {
    return _page('➕ Nouvelle vidéo', [
      _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _small('Note uniquement ce que la vidéo dit. Une valeur incertaine '
                'se coche « À vérifier » ; une condition non dite reste '
                '« Non précisée ».'),
            TextField(
                controller: _title, decoration: _dec('Titre de la vidéo')),
            TextField(
                controller: _date,
                decoration:
                    _dec('Date de publication', hint: 'JJ/MM/AAAA HH:MM')),
            TextField(
                controller: _ref,
                decoration: _dec('Lien ou référence (facultatif)')),
          ],
        ),
      ),
      for (final a in _assets) _assetCard(a),
      OutlinedButton.icon(
        onPressed: () => setState(() => _assets.add(_AssetDraft())),
        icon: const Icon(Icons.add),
        label: const Text('Ajouter une autre crypto'),
      ),
      const SizedBox(height: 14),
      if (_error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child:
              Text('⚠️ $_error', style: const TextStyle(color: AppColors.warn)),
        ),
      FilledButton(
        onPressed: _saving ? null : _save,
        child: Text(_saving ? 'Enregistrement…' : 'Enregistrer la vidéo'),
      ),
    ]);
  }

  Widget _assetCard(_AssetDraft a) => _card(
        border: _lexaTint,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                      controller: a.asset,
                      textCapitalization: TextCapitalization.characters,
                      decoration: _dec('Crypto', hint: 'XRP')),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                      controller: a.price,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: _dec('Prix dans la vidéo (\$)')),
                ),
                if (_assets.length > 1)
                  IconButton(
                    tooltip: 'Retirer',
                    onPressed: () => setState(() => _assets.remove(a)),
                    icon: const Icon(Icons.close),
                  ),
              ],
            ),
            DropdownButtonFormField<String>(
              value: a.stance,
              decoration: _dec('Position annoncée'),
              items: [
                for (final e in lexaStances.entries)
                  DropdownMenuItem(value: e.key, child: Text(e.value)),
              ],
              onChanged: (v) => setState(() => a.stance = v ?? 'UNSPECIFIED'),
            ),
            TextField(
                controller: a.summary,
                maxLines: 2,
                decoration: _dec('Résumé (facultatif)')),
            const SizedBox(height: 12),
            for (final l in a.levels) _levelRow(a, l),
            Wrap(
              spacing: 8,
              children: [
                for (final k in const [
                  'BUY_ZONE',
                  'REINFORCEMENT',
                  'CONFIRMATION',
                  'INVALIDATION',
                  'TARGET'
                ])
                  ActionChip(
                    label: Text('+ ${lexaKinds[k]}'),
                    onPressed: () =>
                        setState(() => a.levels.add(_LevelDraft(k))),
                  ),
              ],
            ),
          ],
        ),
      );

  Widget _levelRow(_AssetDraft a, _LevelDraft l) => Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: const Color(0xFF101E2D),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    value: l.kind,
                    isExpanded: true,
                    decoration: _dec('Type'),
                    items: [
                      for (final e in lexaKinds.entries)
                        DropdownMenuItem(value: e.key, child: Text(e.value)),
                    ],
                    onChanged: (v) => setState(() => l.kind = v ?? l.kind),
                  ),
                ),
                IconButton(
                  tooltip: 'Retirer ce niveau',
                  onPressed: () => setState(() => a.levels.remove(l)),
                  icon: const Icon(Icons.delete_outline, size: 20),
                ),
              ],
            ),
            Row(
              children: [
                Expanded(
                  flex: 3,
                  child: TextField(
                      controller: l.value,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: _dec('Prix (\$)', hint: '1,2688')),
                ),
                const SizedBox(width: 8),
                if (_entryKinds.contains(l.kind) ||
                    _targetKinds.contains(l.kind)) ...[
                  Expanded(
                    flex: 2,
                    child: TextField(
                        controller: l.allocation,
                        keyboardType: TextInputType.number,
                        decoration: _dec(_targetKinds.contains(l.kind)
                            ? '% vendu'
                            : '% du capital')),
                  ),
                  const SizedBox(width: 8),
                ],
                Expanded(
                  flex: 2,
                  child: TextField(
                      controller: l.timestamp,
                      decoration: _dec('Minutage', hint: '18:42')),
                ),
              ],
            ),
            if (_watchKinds.contains(l.kind))
              DropdownButtonFormField<String>(
                value: l.condition,
                isExpanded: true,
                decoration: _dec('Condition dite dans la vidéo'),
                items: [
                  for (final e in lexaConditions.entries)
                    DropdownMenuItem(value: e.key, child: Text(e.value)),
                ],
                onChanged: (v) => setState(() => l.condition = v ?? 'UNKNOWN'),
              ),
            TextField(
                controller: l.source,
                decoration: _dec('Phrase de la vidéo (facultatif)')),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              value: l.toVerify,
              onChanged: (v) => setState(() => l.toVerify = v ?? false),
              title: const Text('⚠️ À vérifier (valeur incertaine)'),
            ),
          ],
        ),
      );
}
