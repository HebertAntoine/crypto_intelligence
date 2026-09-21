/// One crypto's Lexa plan, in the order it is read:
///
///   1. Que faire maintenant ?     5. Pourquoi ?
///   2. Prochaine action           6. Ce que dit Lexa / notre interprétation
///   3. Niveaux (+ budget)         7. Validation par nos données
///   4. Dates                      8. Historique du plan, versions
///
/// Four sources kept apart on screen: 🎬 Lexa (her words), 💶 ton plan (your
/// amounts), 🧠 l'application (its reading of the prices), 🔬 nos données
/// (the app's own engine). Nothing here places an order.
library;

import 'package:flutter/material.dart';

import '../widgets/color_emoji.dart';
import '../widgets/mobile_kit.dart';
import 'lexa_client.dart';
import 'lexa_models.dart';
import 'lexa_ui.dart';

class LexaPlanPage extends StatefulWidget {
  final LexaClient client;
  final int analysisId;

  const LexaPlanPage(
      {super.key, required this.client, required this.analysisId});

  @override
  State<LexaPlanPage> createState() => _LexaPlanPageState();
}

class _LexaPlanPageState extends State<LexaPlanPage> {
  late int _id = widget.analysisId;
  late Future<Map<String, dynamic>> _plan = widget.client.plan(_id);

  void _reload() => setState(() => _plan = widget.client.plan(_id));

  void _show(Future<Map<String, dynamic>> next) => setState(() => _plan = next);

  Future<void> _guard(Future<Map<String, dynamic>> Function() call) async {
    try {
      _show(Future.value(await call()));
    } on LexaException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF06101C),
      body: MobileGradientFrame(
        child: RefreshIndicator(
          onRefresh: () async => _reload(),
          child: FutureBuilder<Map<String, dynamic>>(
            future: _plan,
            builder: (context, snap) {
              if (snap.hasError) {
                return ListView(padding: const EdgeInsets.all(24), children: [
                  _back(),
                  Text('⚠️ ${snap.error}',
                      style: const TextStyle(color: Colors.white)),
                ]);
              }
              if (!snap.hasData) {
                return const Center(child: CircularProgressIndicator());
              }
              return LexaPlanView(
                plan: snap.data!,
                header: _back(),
                onWhy: () => _whySheet(snap.data!),
                onEditPlan: () => _editPlan(snap.data!),
                onFill: (side) => _recordFill(snap.data!, side),
                onDeleteFill: (id) => _guard(() async {
                  await widget.client.deleteFill(id);
                  return widget.client.plan(_id);
                }),
                onStatus: (body) =>
                    _guard(() => widget.client.setPlanStatus(_id, body)),
                onCorrect: _correct,
                onVersion: (id) => setState(() {
                  _id = id;
                  _plan = widget.client.plan(id);
                }),
              );
            },
          ),
        ),
      ),
    );
  }

  /// A correction keeps the value first noted; both stay visible.
  Future<void> _correct(Map<String, dynamic> level) async {
    final controller = TextEditingController();
    final value = await showDialog<double>(
      context: context,
      builder: (context) => AlertDialog(
        title: lexaLabel('✏️ Corriger ${level['label']}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                'Valeur notée à l\'origine : ${priceOf(level['original_value'])}'),
            const Text('Elle reste conservée à côté de la correction.',
                style: TextStyle(fontSize: 12, color: lexaMuted)),
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
    if (value == null) return;
    await _guard(() async {
      await widget.client.correctLevel(level['id'] as int, value);
      return widget.client.plan(_id);
    });
  }

  Widget _back() => Align(
        alignment: Alignment.centerLeft,
        child: IconButton(
          tooltip: 'Retour',
          icon: const Icon(Icons.arrow_back_rounded, color: Colors.white),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
      );

  void _whySheet(Map<String, dynamic> plan) => showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        backgroundColor: const Color(0xFF061525),
        builder: (context) => DraggableScrollableSheet(
          expand: false,
          initialChildSize: .75,
          maxChildSize: .95,
          builder: (context, controller) =>
              LexaWhyView(plan: plan, controller: controller),
        ),
      );

  Future<void> _editPlan(Map<String, dynamic> plan) async {
    final budget = (plan['budget'] as Map).cast<String, dynamic>();
    final budgetCtl =
        TextEditingController(text: '${(budget['budget_eur'] as num).round()}');
    final controllers = <int, TextEditingController>{};
    for (final e in (budget['entries'] as List).cast<Map>()) {
      controllers[e['level_id'] as int] =
          TextEditingController(text: '${(e['amount_eur'] as num).round()}');
    }
    final pctControllers = <int, TextEditingController>{};
    for (final e in (budget['exits'] as List).cast<Map>()) {
      pctControllers[e['level_id'] as int] = TextEditingController(
          text: e['pct'] == null ? '' : '${(e['pct'] as num).round()}');
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('💶 Mon plan'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                  'Ces montants sont les tiens. Lexa donne des niveaux ; '
                  'c\'est toi qui décides combien.',
                  style: TextStyle(fontSize: 12.5, color: lexaMuted)),
              TextField(
                  controller: budgetCtl,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                      labelText: 'Budget ${plan['asset']} (€)')),
              for (final e in (budget['entries'] as List).cast<Map>())
                TextField(
                  controller: controllers[e['level_id']],
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                      labelText:
                          '${e['label']} ${priceOf(e['value'])} — montant (€)'),
                ),
              for (final e in (budget['exits'] as List).cast<Map>())
                TextField(
                  controller: pctControllers[e['level_id']],
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                      labelText:
                          '${e['label']} ${priceOf(e['value'])} — % à vendre'),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Annuler')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Enregistrer')),
        ],
      ),
    );
    if (ok != true) return;
    final items = <Map<String, dynamic>>[
      for (final e in controllers.entries)
        if (parseFrNumber(e.value.text) != null)
          {
            'level_id': e.key,
            'amount_type': 'EURO',
            'amount': parseFrNumber(e.value.text)
          },
      for (final e in pctControllers.entries)
        if (parseFrNumber(e.value.text) != null)
          {
            'level_id': e.key,
            'amount_type': 'PERCENT',
            'amount': parseFrNumber(e.value.text)
          },
    ];
    await _guard(() =>
        widget.client.putUserPlan(_id, parseFrNumber(budgetCtl.text), items));
  }

  Future<void> _recordFill(Map<String, dynamic> plan, String side) async {
    final price = TextEditingController(
        text: (plan['price'] as Map)['value']?.toString() ?? '');
    final amount = TextEditingController();
    final levels = [
      for (final lv in (plan['levels'] as List).cast<Map>())
        if (side == 'BUY'
            ? const ['BUY_ZONE', 'REINFORCEMENT', 'CONFIRMATION', 'BREAKOUT']
                .contains(lv['kind'])
            : const ['TARGET', 'TAKE_PROFIT'].contains(lv['kind']))
          lv,
    ];
    int? levelId = levels.isEmpty ? null : levels.first['id'] as int;
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setLocal) => AlertDialog(
          title: Text(side == 'BUY'
              ? '✅ Enregistrer un achat'
              : '🔴 Enregistrer une vente'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                  'Ce que TU as exécuté. L\'application ne passe jamais d\'ordre.',
                  style: TextStyle(fontSize: 12.5, color: lexaMuted)),
              if (levels.isNotEmpty)
                DropdownButtonFormField<int>(
                  value: levelId,
                  decoration: const InputDecoration(labelText: 'Niveau'),
                  items: [
                    for (final lv in levels)
                      DropdownMenuItem(
                          value: lv['id'] as int,
                          child:
                              Text('${lv['label']} ${priceOf(lv['value'])}')),
                  ],
                  onChanged: (v) => setLocal(() => levelId = v),
                ),
              TextField(
                  controller: price,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Prix d\'exécution (\$)')),
              TextField(
                  controller: amount,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(
                      labelText: side == 'BUY'
                          ? 'Montant (€)'
                          : 'Quantité vendue (${plan['asset']})')),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Annuler')),
            FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Enregistrer')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    final value = parseFrNumber(amount.text);
    await _guard(() => widget.client.addFill(_id, {
          'side': side,
          'price_usd': parseFrNumber(price.text),
          'level_id': levelId,
          if (side == 'BUY') 'amount_eur': value else 'quantity': value,
        }));
  }
}

/// The plan, drawn. Pure: what the backend computed, in the brief's order.
class LexaPlanView extends StatelessWidget {
  final Map<String, dynamic> plan;
  final Widget? header;
  final VoidCallback? onWhy;
  final VoidCallback? onEditPlan;
  final void Function(String side)? onFill;
  final void Function(int fillId)? onDeleteFill;
  final void Function(Map<String, dynamic> body)? onStatus;
  final void Function(int analysisId)? onVersion;
  final void Function(Map<String, dynamic> level)? onCorrect;

  const LexaPlanView({
    super.key,
    required this.plan,
    this.header,
    this.onWhy,
    this.onEditPlan,
    this.onFill,
    this.onDeleteFill,
    this.onStatus,
    this.onVersion,
    this.onCorrect,
  });

  Map<String, dynamic> _m(String key) =>
      ((plan[key] as Map?) ?? const {}).cast<String, dynamic>();

  List<Map<String, dynamic>> _l(Object? v) => [
        for (final x in (v as List? ?? const []))
          (x as Map).cast<String, dynamic>()
      ];

  @override
  Widget build(BuildContext context) {
    return LexaEmojiFonts(
        child: MobileScrollView(
      padding: const EdgeInsets.fromLTRB(18, 8, 18, 120),
      children: [
        if (header != null) header!,
        _hero(),
        const SizedBox(height: 14),
        if (_l(plan['next_actions']).isNotEmpty) ...[
          _next(),
          const SizedBox(height: 14),
        ],
        _levels(),
        const SizedBox(height: 14),
        _budget(),
        const SizedBox(height: 14),
        _dates(),
        const SizedBox(height: 14),
        _lexa(context),
        const SizedBox(height: 14),
        _interpretation(),
        const SizedBox(height: 14),
        _validation(),
        if (plan['revision'] != null) ...[
          const SizedBox(height: 14),
          _revision(),
        ],
        const SizedBox(height: 14),
        _timeline(),
        const SizedBox(height: 14),
        _versions(),
        const SizedBox(height: 14),
        _manage(),
        lexaNote('${plan['no_order']}'),
      ],
    ));
  }

  // 1. Que faire maintenant ?
  Widget _hero() {
    final now = _m('now');
    final price = _m('price');
    final lexa = _m('lexa');
    final video = ((lexa['video'] as Map?) ?? const {}).cast<String, dynamic>();
    final color = toneColor('${now['tone']}');
    return GlassPanel(
      key: const ValueKey('lexa-now'),
      borderColor: color,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text('${plan['asset']}',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 38,
                    fontWeight: FontWeight.w800,
                    height: 1)),
            const SizedBox(width: 10),
            const ColorEmoji(emoji: '🎬', size: 20),
            const SizedBox(width: 4),
            const Text('Plan Lexa',
                style: TextStyle(color: mobileMuted, fontSize: 16)),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            const ColorEmoji(emoji: '💰', size: 16),
            const SizedBox(width: 6),
            const Text('Prix actuel ',
                style: TextStyle(color: mobileMuted, fontSize: 15)),
            Flexible(
              child: Text(priceOf(price['value']),
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w800)),
            ),
          ]),
          const SizedBox(height: 14),
          LexaStatusPill(
              emoji: '${now['emoji']}', label: '${now['label']}', big: true),
          const SizedBox(height: 10),
          Text('${now['verdict']}',
              key: const ValueKey('lexa-verdict'),
              style: TextStyle(
                  color: color, fontSize: 30, fontWeight: FontWeight.w900)),
          const SizedBox(height: 6),
          Text('${now['reason']}',
              style: const TextStyle(
                  color: Colors.white, fontSize: 15.5, height: 1.4)),
          if (now['action_pending'] == true) ...[
            const SizedBox(height: 8),
            const LexaStatusPill(emoji: '🟠', label: 'Action en attente'),
          ],
          const SizedBox(height: 10),
          Wrap(spacing: 12, runSpacing: 4, children: [
            Text('Vidéo du ${dayMonth(parseIso(video['published_at']))}',
                style: const TextStyle(color: lexaMuted, fontSize: 12.5)),
            Text('Analyse Lexa #${plan['version']}',
                style: const TextStyle(color: lexaMuted, fontSize: 12.5)),
            if (price['at_video'] != null)
              Text('Prix pendant la vidéo : ${priceOf(price['at_video'])}',
                  style: const TextStyle(color: lexaMuted, fontSize: 12.5)),
          ]),
          if (onWhy != null)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                key: const ValueKey('lexa-why'),
                onPressed: onWhy,
                child: const Text('Pourquoi ? ›'),
              ),
            ),
        ],
      ),
    );
  }

  // 2. Prochaine action
  Widget _next() {
    final actions = _l(plan['next_actions']);
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const LexaSectionTitle(emoji: '👉', text: 'Prochaine action'),
          const SizedBox(height: 8),
          for (var i = 0; i < actions.length; i++) ...[
            if (i > 0)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 4),
                child: Text('OU',
                    style: TextStyle(
                        color: lexaMuted, fontWeight: FontWeight.w800)),
              ),
            Row(children: [
              Text('${actions[i]['direction']}',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w800)),
              const SizedBox(width: 8),
              ColorEmoji(emoji: '${actions[i]['emoji']}', size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${actions[i]['label']}',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w800)),
                    Text(
                        [
                          priceOf(actions[i]['value']),
                          fmtDistance(actions[i]['distance_pct'] as num?),
                          '${actions[i]['detail'] ?? ''}',
                        ].where((s) => s.isNotEmpty).join(' · '),
                        style: const TextStyle(color: lexaWhite, fontSize: 13)),
                  ],
                ),
              ),
            ]),
          ],
        ],
      ),
    );
  }

  // 3. Niveaux
  Widget _levels() => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Padding(
            padding: EdgeInsets.only(left: 4, bottom: 10),
            child: LexaSectionTitle(emoji: '🗺️', text: 'Plan'),
          ),
          for (final lv in _l(plan['levels'])) ...[
            _levelCard(lv),
            const SizedBox(height: 10),
          ],
        ],
      );

  Widget _levelCard(Map<String, dynamic> lv) {
    final state = (lv['state'] as Map).cast<String, dynamic>();
    final userPlan = (lv['user_plan'] as Map?)?.cast<String, dynamic>();
    return GlassPanel(
      key: ValueKey('lexa-level-${lv['id']}'),
      padding: const EdgeInsets.all(16),
      borderColor: emojiColor('${lv['emoji']}').withValues(alpha: .55),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            ColorEmoji(emoji: '${lv['emoji']}', size: 18),
            const SizedBox(width: 8),
            Text(priceOf(lv['value']),
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 21,
                    fontWeight: FontWeight.w800)),
            const SizedBox(width: 8),
            Expanded(
              child: Text('${lv['basis_fr'] ?? ''}',
                  textAlign: TextAlign.right,
                  style: const TextStyle(color: lexaMuted, fontSize: 11.5)),
            ),
          ]),
          const SizedBox(height: 2),
          Text('${lv['label']}'.toUpperCase(),
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  letterSpacing: .5,
                  fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          if (userPlan?['amount_eur'] != null)
            LexaLine('Montant prévu', eurOf(userPlan!['amount_eur'])),
          if (userPlan?['amount_eur'] != null) lexaNote('${userPlan!['note']}'),
          if (userPlan != null && userPlan.containsKey('pct'))
            LexaLine(
                'Plan de vente',
                userPlan['pct'] == null
                    ? 'Non défini'
                    : '${(userPlan['pct'] as num).round()} %'
                        '${userPlan['origin'] == 'LEXA' ? ' (dit par Lexa)' : ' (ton plan)'}'),
          LexaLine('État', '${state['emoji']} ${state['label']}'),
          if (lv['distance_fr'] != null)
            LexaLine('Distance', '${lv['distance_fr']}'),
          for (final c in _l(lv['conditions'])) _condition(c),
          if (lv['timestamp_s'] != null || '${lv['source_text']}'.isNotEmpty)
            lexaNote([
              if (lv['timestamp_s'] != null)
                '🎬 ${fmtTimestamp(lv['timestamp_s'] as int)}',
              if ('${lv['source_text']}'.isNotEmpty) '« ${lv['source_text']} »',
            ].join(' — ')),
          if (lv['to_verify'] == true)
            lexaNote('⚠️ À vérifier', color: lexaOrange),
          if (lv['corrected_value'] != null)
            lexaNote(
                '✏️ Corrigé — valeur d\'origine ${priceOf(lv['original_value'])}'),
        ],
      ),
    );
  }

  Widget _condition(Map<String, dynamic> c) {
    final ev = (c['evaluation'] as Map?)?.cast<String, dynamic>();
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF101E2D),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: lexaDivider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Condition : ${c['rule']}',
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w700)),
          if ('${c['description'] ?? ''}'.isNotEmpty)
            lexaNote('🎬 « ${c['description']} »'),
          if (ev != null) ...[
            const SizedBox(height: 6),
            Text('${ev['emoji']} ${ev['label']}',
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w800)),
            lexaNote('${ev['message']}'),
            if (ev['countdown'] != null)
              lexaNote(
                  '⏳ Clôture dans ${ev['countdown']} — 🕯️ ${ev['next_close_paris']}'),
          ] else if (c['evaluable'] != true)
            lexaNote(
                'Condition non vérifiable automatiquement : à juger par toi.'),
        ],
      ),
    );
  }

  // Budget
  Widget _budget() {
    final b = _m('budget');
    final exits = _l(b['exits']).where((e) => e['pct'] != null).toList();
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LexaSectionTitle(
            emoji: '💶',
            text: 'Mon budget',
            trailing: onEditPlan == null
                ? null
                : TextButton(
                    onPressed: onEditPlan, child: const Text('Modifier')),
          ),
          const SizedBox(height: 6),
          LexaLine('💰 Budget total', eurOf(b['budget_eur'])),
          LexaLine('Disponible', eurOf(b['available_eur'])),
          LexaLine('Déployé', eurOf(b['deployed_eur'])),
          LexaLine('Planifié', eurOf(b['planned_eur'])),
          if ((b['quantity'] as num? ?? 0) > 0) ...[
            LexaLine('Position',
                '${(b['quantity'] as num).toStringAsFixed(4)} ${plan['asset']}'),
            LexaLine('Valeur estimée', eurOf(b['position_value_eur'])),
            for (final e in exits)
              if (e['quantity'] != null)
                LexaLine('${e['label']} (${(e['pct'] as num).round()} %)',
                    '${(e['quantity'] as num).toStringAsFixed(4)} · ${eurOf(e['value_eur'])}'),
          ],
          for (final f in _l(b['fills']))
            Row(children: [
              Expanded(
                child: lexaNote(
                    '${f['side'] == 'BUY' ? '✅ Achat' : '🔴 Vente'} ${dayMonth(parseIso(f['executed_at']))} : '
                    '${(f['quantity'] as num).toStringAsFixed(4)} à ${priceOf(f['price_usd'])}'),
              ),
              if (onDeleteFill != null)
                IconButton(
                    tooltip: 'Supprimer',
                    iconSize: 18,
                    onPressed: () => onDeleteFill!(f['id'] as int),
                    icon: const Icon(Icons.close, color: lexaMuted)),
            ]),
          lexaNote('${b['rule'] ?? ''}'),
          if (onFill != null)
            Wrap(spacing: 8, children: [
              OutlinedButton(
                  onPressed: () => onFill!('BUY'),
                  child: lexaLabel('✅ Enregistrer un achat')),
              OutlinedButton(
                  onPressed: () => onFill!('SELL'),
                  child: lexaLabel('🔴 Enregistrer une vente')),
            ]),
        ],
      ),
    );
  }

  // 4. Dates
  Widget _dates() {
    final d = _m('dates');
    final closes =
        _l(plan['calendar']).where((c) => c['kind'] == 'CLOSE_DUE').toList();
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const LexaSectionTitle(emoji: '📅', text: 'Dates'),
          const SizedBox(height: 6),
          for (final c in closes)
            LexaLine('🕯️ ${c['title']}', '${c['detail'] ?? ''}',
                color: lexaOrange),
          LexaLine('Vidéo publiée', fmtDateFr(parseIso(d['published_at']))),
          LexaLine('Analyse enregistrée',
              fmtDateFr(parseIso(d['analysis_added_at']))),
          LexaLine(
              'Réévaluation',
              fmtDateFr(parseIso(d['review_at'])) +
                  (d['review_due'] == true ? ' — due' : ''),
              color: d['review_due'] == true ? lexaOrange : null),
          LexaLine('Fin de validité', fmtDateFr(parseIso(d['expires_at']))),
        ],
      ),
    );
  }

  // 6a. Ce que dit Lexa
  Widget _lexa(BuildContext context) {
    final lexa = _m('lexa');
    final video = ((lexa['video'] as Map?) ?? const {}).cast<String, dynamic>();
    final quotes = _l(lexa['quotes']);
    final start = video['timestamp_start_s'] as int? ??
        (quotes.isEmpty ? null : quotes.first['timestamp_s'] as int?);
    return GlassPanel(
      borderColor: const Color(0xFFB083F0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const LexaSectionTitle(emoji: '🎬', text: 'Ce que dit Lexa'),
          const SizedBox(height: 6),
          LexaLine('Source', 'Lexa'),
          LexaLine('Vidéo', '${video['title'] ?? '—'}'),
          if ('${lexa['summary'] ?? ''}'.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('${lexa['summary']}',
                  style: const TextStyle(color: Colors.white, height: 1.4)),
            ),
          if ('${lexa['market_context'] ?? ''}'.isNotEmpty)
            lexaNote('📊 « ${lexa['market_context']} »', color: lexaWhite),
          for (final q in quotes)
            lexaNote(
                '🎬 ${fmtTimestamp(q['timestamp_s'] as int?)} — « ${q['text']} » '
                '(${priceOf(q['level'])}${q['basis'] == 'INFERRED' ? ', 🟡 interprétation' : ''})',
                color: lexaWhite),
          if (quotes.isEmpty && '${lexa['market_context'] ?? ''}'.isEmpty)
            lexaNote('Aucune citation enregistrée pour cette analyse.'),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: () =>
                  openVideo(context, video['url'] as String?, start),
              child: lexaLabel(start == null
                  ? '🎬 Ouvrir la vidéo'
                  : '🎬 Voir le passage ${fmtTimestamp(start)}'),
            ),
          ),
        ],
      ),
    );
  }

  // 6b. Notre interprétation
  Widget _interpretation() {
    final i = _m('app_interpretation');
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const LexaSectionTitle(
              emoji: '🧠', text: 'Interprétation de l\'application'),
          const SizedBox(height: 6),
          Text('${i['text']}',
              style: const TextStyle(color: Colors.white, height: 1.4)),
          for (final d in (i['details'] as List? ?? const [])) lexaNote('• $d'),
          LexaLine('État', '${i['status']}'),
          lexaNote('${i['note'] ?? ''}'),
        ],
      ),
    );
  }

  // 7. Validation par nos données
  Widget _validation() {
    final v = _m('validation');
    return GlassPanel(
      key: const ValueKey('lexa-validation'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const LexaSectionTitle(
              emoji: '🔬', text: 'Validation par nos données'),
          const SizedBox(height: 6),
          for (final f in _l(v['families']))
            LexaLine('${f['name']}', '${f['emoji']} ${f['status'] ?? ''}'),
          const SizedBox(height: 6),
          if (v['label'] != null)
            LexaStatusPill(
                emoji: '${v['emoji']}', label: 'Concordance : ${v['label']}'),
          if (v['divergence'] == true) ...[
            const SizedBox(height: 6),
            const LexaStatusPill(
                emoji: '⚠️', label: 'Divergence : Lexa ≠ notre moteur'),
          ],
          lexaNote('${v['explanation'] ?? ''}'),
          lexaNote(
              'Nos données ne modifient pas le plan Lexa, et Lexa ne modifie '
              'jamais notre moteur.'),
        ],
      ),
    );
  }

  Widget _revision() {
    final r = _m('revision');
    return GlassPanel(
      borderColor: lexaOrange,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LexaSectionTitle(emoji: '🔄', text: '${r['label']}'),
          const SizedBox(height: 6),
          for (final c in _l(r['changes']))
            LexaLine('${c['what']}',
                '${(c['old'] as List).join(' / ')} → ${(c['new'] as List).join(' / ')}'),
          lexaNote('Raison : ${r['reason']}'),
          if (onVersion != null)
            TextButton(
                onPressed: () => onVersion!(r['previous_analysis_id'] as int),
                child: Text('Voir l\'analyse #${r['previous_version']}')),
        ],
      ),
    );
  }

  // 8. Historique
  Widget _timeline() {
    final items = _l(plan['timeline']);
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const LexaSectionTitle(emoji: '🕒', text: 'Historique du plan'),
          const SizedBox(height: 8),
          for (var i = 0; i < items.length; i++) ...[
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(
                width: 92,
                child: Text(
                    items[i]['now'] == true
                        ? 'MAINTENANT'
                        : dayMonth(parseIso(items[i]['at'])),
                    style: const TextStyle(
                        color: lexaMuted,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w800)),
              ),
              ColorEmoji(emoji: '${items[i]['emoji']}', size: 13),
              const SizedBox(width: 6),
              Expanded(
                child: Text('${items[i]['text']}',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: items[i]['now'] == true
                            ? FontWeight.w800
                            : FontWeight.w500)),
              ),
            ]),
            if (i < items.length - 1)
              const Padding(
                padding: EdgeInsets.only(left: 98),
                child: Text('↓', style: TextStyle(color: lexaMuted)),
              ),
          ],
        ],
      ),
    );
  }

  Widget _versions() {
    final versions = _l(plan['versions']);
    return GlassPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LexaSectionTitle(
              emoji: '📚', text: 'Versions — ${plan['lifecycle_fr']}'),
          if ('${plan['lifecycle_reason'] ?? ''}'.isNotEmpty)
            lexaNote('${plan['lifecycle_reason']}'),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final v in versions)
              LexaChip(
                label:
                    '#${v['version']} · ${dayMonth(parseIso(v['published_at']))}',
                selected: v['current'] == true,
                onTap: () => onVersion?.call(v['analysis_id'] as int),
              ),
          ]),
        ],
      ),
    );
  }

  Widget _manage() {
    if (onStatus == null) return const SizedBox.shrink();
    final lifecycle = plan['lifecycle'];
    final reviewDue = _m('dates')['review_due'] == true;
    return Wrap(spacing: 8, runSpacing: 8, children: [
      if (lifecycle != 'INVALIDATED')
        OutlinedButton(
            onPressed: () => onStatus!({
                  'status': 'INVALIDATED',
                  'reason': 'Invalidé par toi.',
                }),
            child: lexaLabel('❌ Marquer invalidé')),
      if (lifecycle != 'COMPLETED')
        OutlinedButton(
            onPressed: () => onStatus!({'status': 'COMPLETED'}),
            child: lexaLabel('⚪ Marquer terminé')),
      if (lifecycle == 'INVALIDATED' || lifecycle == 'COMPLETED')
        OutlinedButton(
            onPressed: () => onStatus!({'status': null}),
            child: lexaLabel('🔵 Rouvrir')),
      if (reviewDue || lifecycle == 'EXPIRED')
        OutlinedButton(
            onPressed: () => onStatus!({
                  'review_at': DateTime.now()
                      .toUtc()
                      .add(const Duration(days: 7))
                      .toIso8601String(),
                  'expires_at': DateTime.now()
                      .toUtc()
                      .add(const Duration(days: 21))
                      .toIso8601String(),
                }),
            child: lexaLabel('📅 J\'ai réévalué (+7 j)')),
    ]);
  }
}

/// « Pourquoi ? » — every reason behind the status, then the IF / THEN rules.
class LexaWhyView extends StatelessWidget {
  final Map<String, dynamic> plan;
  final ScrollController? controller;

  const LexaWhyView({super.key, required this.plan, this.controller});

  @override
  Widget build(BuildContext context) {
    final now = (plan['now'] as Map).cast<String, dynamic>();
    final why = (plan['why'] as List? ?? const []).cast<Map>();
    final rules = (plan['rules'] as List? ?? const []).cast<Map>();
    return LexaEmojiFonts(
        child: ListView(
      controller: controller,
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
      children: [
        Text('Pourquoi ${'${now['verdict']}'.toLowerCase()} ?',
            style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        for (final w in why)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              ColorEmoji(emoji: '${w['emoji']}', size: 16),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${w['title']}',
                        style: const TextStyle(
                            color: Colors.white, fontWeight: FontWeight.w800)),
                    Text('${w['text']}',
                        style: const TextStyle(color: lexaWhite, height: 1.35)),
                  ],
                ),
              ),
            ]),
          ),
        const Divider(color: lexaDivider),
        const Text('Règles du plan',
            style: TextStyle(
                color: Colors.white,
                fontSize: 17,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        for (final r in rules)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('SI ${r['if']}',
                    style: const TextStyle(color: lexaWhite, fontSize: 13)),
                Text('ALORS ${r['then']}',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w700)),
                Text('${r['state']}',
                    style: const TextStyle(color: lexaMuted, fontSize: 12)),
              ],
            ),
          ),
        lexaNote('${plan['no_order']}'),
      ],
    ));
  }
}
