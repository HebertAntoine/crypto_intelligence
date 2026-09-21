/// ➕ Saisir une vidéo Lexa.
///
/// The member notes what the video said: levels, how they count (a touch or
/// closes on a timeframe), the passage. Only what was said — a condition the
/// video did not give stays « non précisée », a value Lexa did not state as a
/// share of capital stays empty. Our own amounts are set later, in « Mon budget »
/// on the plan page: they are never recorded as Lexa's.
library;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'lexa_client.dart';
import 'lexa_models.dart';
import 'lexa_ui.dart';

const _panel = Color(0xFF0E1A28);
const _border = Color(0xFF245386);
const _muted = Color(0xFFB7C6DF);
const _lexaTint = Color(0xFFB083F0);

const _entryKinds = {'BUY_ZONE', 'REINFORCEMENT'};
const _targetKinds = {'TARGET', 'TAKE_PROFIT'};
const _conditionKinds = {
  'CONFIRMATION',
  'BREAKOUT',
  'INVALIDATION',
  'SUPPORT',
  'RESISTANCE'
};
const _closeTimeframes = {
  '': 'Non précisée dans la vidéo',
  '1H': 'Clôture 1 h',
  '4H': 'Clôture 4 h',
  '1D': 'Clôture journalière',
  '1W': 'Clôture hebdomadaire',
};

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

Widget _small(String text, {Color color = _muted}) => Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(text, style: TextStyle(color: color, fontSize: 12.5)),
    );

class _LevelDraft {
  String kind;
  final value = TextEditingController();
  final lexaPct = TextEditingController();
  final timestamp = TextEditingController();
  final source = TextEditingController();
  final closes = TextEditingController(text: '1');
  final window = TextEditingController();
  String timeframe = '';
  String operator;
  bool inferred = false;
  bool toVerify = false;

  _LevelDraft(this.kind)
      : operator = const {'INVALIDATION', 'SUPPORT'}.contains(kind)
            ? 'BELOW'
            : 'ABOVE';
}

class _AssetDraft {
  final asset = TextEditingController();
  final price = TextEditingController();
  final summary = TextEditingController();
  final context = TextEditingController();
  final reviewDays = TextEditingController(text: '7');
  final validDays = TextEditingController(text: '21');
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
  final _url = TextEditingController();
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
        final pct = parseFrNumber(l.lexaPct.text);
        if (l.lexaPct.text.trim().isNotEmpty && pct == null) {
          return (null, '$name : pourcentage illisible « ${l.lexaPct.text} ».');
        }
        final conditions = <Map<String, dynamic>>[];
        if (_conditionKinds.contains(l.kind) && l.timeframe.isNotEmpty) {
          final closes = int.tryParse(l.closes.text.trim()) ?? 1;
          conditions.add({
            'condition_type': 'CLOSE',
            'timeframe': l.timeframe,
            'operator': l.operator,
            'required_closes': closes < 1 ? 1 : closes,
            'confirmation_window': int.tryParse(l.window.text.trim()),
            'description': l.source.text.trim(),
            'basis': l.inferred ? 'INFERRED' : 'EXPLICIT',
          });
        }
        levels.add({
          'kind': l.kind,
          'value': value,
          'allocation_pct': pct,
          'timestamp':
              l.timestamp.text.trim().isEmpty ? null : l.timestamp.text.trim(),
          'source_text': l.source.text.trim(),
          'confidence': l.toVerify ? 'LOW' : (l.inferred ? 'MEDIUM' : 'HIGH'),
          'basis': l.inferred ? 'INFERRED' : 'EXPLICIT',
          'conditions': conditions,
        });
      }
      final review = int.tryParse(a.reviewDays.text.trim());
      final valid = int.tryParse(a.validDays.text.trim());
      assets.add({
        'asset': name,
        'price_at_video': parseFrNumber(a.price.text),
        'stance': a.stance,
        'summary': a.summary.text.trim(),
        'market_context': a.context.text.trim(),
        if (review != null)
          'review_at':
              date.add(Duration(days: review)).toUtc().toIso8601String(),
        if (valid != null)
          'expires_at':
              date.add(Duration(days: valid)).toUtc().toIso8601String(),
        'levels': levels,
      });
    }
    return (
      {
        'title': _title.text.trim(),
        'published_at': date.toUtc().toIso8601String(),
        'video_url': _url.text.trim(),
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
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
          backgroundColor: AppColors.background,
          title: lexaLabel('➕ Nouvelle vidéo')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
            children: [
              _card(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _small('Note uniquement ce que la vidéo dit. Une valeur '
                        'incertaine se coche « À vérifier » ; une condition non '
                        'dite reste « Non précisée ». Tes montants se règlent '
                        'ensuite dans « Mon budget ».'),
                    TextField(
                        controller: _title,
                        decoration: _dec('Titre de la vidéo')),
                    TextField(
                        controller: _date,
                        decoration: _dec('Date de publication',
                            hint: 'JJ/MM/AAAA HH:MM')),
                    TextField(
                        controller: _url,
                        decoration: _dec(
                            'Lien de la vidéo (facultatif, jamais le fichier)')),
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
                  child: Text('⚠️ $_error',
                      style: const TextStyle(color: AppColors.warn)),
                ),
              FilledButton(
                onPressed: _saving ? null : _save,
                child:
                    Text(_saving ? 'Enregistrement…' : 'Enregistrer la vidéo'),
              ),
            ],
          ),
        ),
      ),
    );
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
              decoration: _dec('Position annoncée par Lexa'),
              items: [
                for (final e in lexaStances.entries)
                  DropdownMenuItem(value: e.key, child: Text(e.value)),
              ],
              onChanged: (v) => setState(() => a.stance = v ?? 'UNSPECIFIED'),
            ),
            TextField(
                controller: a.summary,
                maxLines: 2,
                decoration:
                    _dec('Ce que dit Lexa, en une phrase (facultatif)')),
            TextField(
                controller: a.context,
                maxLines: 2,
                decoration:
                    _dec('Contexte de marché, dans ses mots (facultatif)')),
            Row(children: [
              Expanded(
                child: TextField(
                    controller: a.reviewDays,
                    keyboardType: TextInputType.number,
                    decoration: _dec('Réévaluer dans (jours)')),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                    controller: a.validDays,
                    keyboardType: TextInputType.number,
                    decoration: _dec('Valable (jours)')),
              ),
            ]),
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
                      decoration: _dec('Prix (\$)', hint: '2,4531')),
                ),
                const SizedBox(width: 8),
                if (_entryKinds.contains(l.kind) ||
                    _targetKinds.contains(l.kind)) ...[
                  Expanded(
                    flex: 2,
                    child: TextField(
                        controller: l.lexaPct,
                        keyboardType: TextInputType.number,
                        decoration: _dec('% dit par Lexa')),
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
            if (_conditionKinds.contains(l.kind)) ...[
              DropdownButtonFormField<String>(
                value: l.timeframe,
                isExpanded: true,
                decoration: _dec('Condition dite dans la vidéo'),
                items: [
                  for (final e in _closeTimeframes.entries)
                    DropdownMenuItem(value: e.key, child: Text(e.value)),
                ],
                onChanged: (v) => setState(() => l.timeframe = v ?? ''),
              ),
              if (l.timeframe.isNotEmpty)
                Row(children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: l.operator,
                      decoration: _dec('Sens'),
                      items: const [
                        DropdownMenuItem(
                            value: 'ABOVE', child: Text('au-dessus')),
                        DropdownMenuItem(
                            value: 'BELOW', child: Text('en dessous')),
                      ],
                      onChanged: (v) =>
                          setState(() => l.operator = v ?? 'ABOVE'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                        controller: l.closes,
                        keyboardType: TextInputType.number,
                        decoration: _dec('Clôtures requises')),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                        controller: l.window,
                        keyboardType: TextInputType.number,
                        decoration: _dec('Maintien (bougies)')),
                  ),
                ]),
            ],
            TextField(
                controller: l.source,
                decoration: _dec('Phrase de la vidéo (facultatif)')),
            Row(children: [
              Expanded(
                child: CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  value: l.inferred,
                  onChanged: (v) => setState(() => l.inferred = v ?? false),
                  title: const Text('🟡 Déduit du contexte'),
                ),
              ),
              Expanded(
                child: CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  value: l.toVerify,
                  onChanged: (v) => setState(() => l.toVerify = v ?? false),
                  title: const Text('⚠️ À vérifier'),
                ),
              ),
            ]),
          ],
        ),
      );
}
