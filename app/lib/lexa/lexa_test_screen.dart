/// 🧪 Tester la chaîne sur UNE vidéo.
///
/// The member pastes the timestamped transcript of one video they are allowed
/// to obtain. The backend runs the whole chain on this machine and returns the
/// report, the validation report, the transcript and the JSON. Nothing is
/// imported: the member validates first.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/app_theme.dart';
import 'lexa_client.dart';

const _muted = Color(0xFFB7C6DF);
const _panel = Color(0xFF0E1A28);
const _border = Color(0xFF245386);

class LexaTestScreen extends StatefulWidget {
  final LexaClient client;
  final Duration pollEvery;

  const LexaTestScreen({
    super.key,
    required this.client,
    this.pollEvery = const Duration(seconds: 3),
  });

  @override
  State<LexaTestScreen> createState() => _LexaTestScreenState();
}

class _LexaTestScreenState extends State<LexaTestScreen> {
  final _title = TextEditingController();
  final _date = TextEditingController();
  final _transcript = TextEditingController();
  Map<String, dynamic>? _run;
  String? _error;
  bool _busy = false;
  Timer? _timer;
  int _generation = 0;
  late Future<Map<String, dynamic>> _history = widget.client.testRuns();

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String? _isoDate() {
    final m =
        RegExp(r'^\s*(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?\s*$')
            .firstMatch(_date.text);
    if (m == null) return null;
    return DateTime(int.parse(m[3]!), int.parse(m[2]!), int.parse(m[1]!),
            int.parse(m[4] ?? '0'), int.parse(m[5] ?? '0'))
        .toUtc()
        .toIso8601String();
  }

  Future<void> _start() async {
    if (_title.text.trim().isEmpty || _transcript.text.trim().isEmpty) {
      setState(() =>
          _error = 'Indique le titre et colle la transcription horodatée.');
      return;
    }
    if (_date.text.trim().isNotEmpty && _isoDate() == null) {
      setState(() => _error = 'Date illisible (format JJ/MM/AAAA HH:MM).');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _run = null;
    });
    try {
      final id = await widget.client.startTestRun(
        transcript: _transcript.text,
        title: _title.text.trim(),
        publishedAt: _isoDate(),
      );
      _follow(id);
    } on LexaException catch (e) {
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  /// One request at a time: the next poll starts after the previous answer,
  /// so a late « RUNNING » can never overwrite a « DONE ».
  void _follow(String id) {
    _timer?.cancel();
    final generation = ++_generation;
    Future<void> tick() async {
      try {
        final run = await widget.client.testRun(id);
        if (!mounted || generation != _generation) return;
        final running = (run['status'] as Map?)?['state'] == 'RUNNING';
        setState(() {
          _run = run;
          if (!running) {
            _busy = false;
            _history = widget.client.testRuns();
          }
        });
        if (running) _timer = Timer(widget.pollEvery, tick);
      } on LexaException catch (e) {
        if (mounted && generation == _generation) {
          setState(() {
            _busy = false;
            _error = e.message;
            // No stale spinner: the run is still on disk, reopen it below.
            if ((_run?['status'] as Map?)?['state'] == 'RUNNING') _run = null;
          });
        }
      }
    }

    setState(() => _busy = true);
    tick();
  }

  InputDecoration _dec(String label, {String? hint}) =>
      InputDecoration(labelText: label, hintText: hint, isDense: true);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        title: const Text('🧪 Tester une vidéo'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 120),
            children: [
              _box(const Text(
                'Colle la transcription horodatée d\'UNE vidéo : transcription '
                'YouTube (« Afficher la transcription »), texte ou sous-titres fournis '
                'par Lexa. L\'enregistrement des vidéos LexaMoon n\'est pas permis par '
                'leurs CGV.\n\nLa lecture se fait sur cet ordinateur (modèle local). '
                'Chaque prix doit être retrouvé dans la transcription, sinon il est '
                'rejeté. Rien n\'est importé avant ta validation.',
                style: TextStyle(color: _muted, fontSize: 13.5, height: 1.4),
              )),
              TextField(
                  controller: _title, decoration: _dec('Titre de la vidéo')),
              TextField(
                  controller: _date,
                  decoration: _dec('Date de publication (facultatif)',
                      hint: 'JJ/MM/AAAA HH:MM — permet de suivre les niveaux')),
              const SizedBox(height: 8),
              TextField(
                controller: _transcript,
                minLines: 8,
                maxLines: 16,
                decoration: _dec('Transcription horodatée',
                    hint:
                        '[12:31] Si XRP revient vers …\nou\n12:31\nSi XRP revient vers …'),
                style: const TextStyle(fontSize: 13),
              ),
              const SizedBox(height: 12),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text('⚠️ $_error',
                      style: const TextStyle(color: AppColors.warn)),
                ),
              FilledButton(
                onPressed: _busy ? null : _start,
                child: Text(_busy ? 'Analyse en cours…' : 'Lancer le test'),
              ),
              const SizedBox(height: 16),
              if (_run != null) LexaTestRunView(run: _run!),
              const SizedBox(height: 16),
              _previous(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _previous() => FutureBuilder<Map<String, dynamic>>(
        future: _history,
        builder: (context, snap) {
          final runs = (snap.data?['runs'] as List?) ?? const [];
          if (runs.isEmpty) return const SizedBox.shrink();
          return _box(Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Tests précédents',
                  style: TextStyle(
                      color: AppColors.text, fontWeight: FontWeight.w700)),
              for (final r in runs.cast<Map>())
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text('${r['title']}'),
                  subtitle: Text('${r['run_id']} · ${_stateFr(r['state'])}'),
                  onTap: _busy ? null : () => _follow('${r['run_id']}'),
                ),
            ],
          ));
        },
      );
}

String _stateFr(Object? state) => switch (state) {
      'RUNNING' => '⏳ En cours',
      'DONE' => '✅ Terminé',
      'FAILED' => '🔴 Échec',
      _ => '—',
    };

Widget _box(Widget child) => Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _panel,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _border, width: 1.2),
      ),
      child: child,
    );

/// A run's four outputs, one at a time.
class LexaTestRunView extends StatefulWidget {
  final Map<String, dynamic> run;

  const LexaTestRunView({super.key, required this.run});

  @override
  State<LexaTestRunView> createState() => _LexaTestRunViewState();
}

class _LexaTestRunViewState extends State<LexaTestRunView> {
  String _tab = 'report';

  @override
  Widget build(BuildContext context) {
    final status = (widget.run['status'] as Map?) ?? const {};
    final state = status['state'];
    if (state == 'RUNNING') {
      return _box(const Row(children: [
        SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2)),
        SizedBox(width: 12),
        Expanded(
          child: Text(
              'Lecture de la transcription par le modèle local… '
              'Compte environ une minute par crypto.',
              style: TextStyle(color: _muted)),
        ),
      ]));
    }
    if (state == 'FAILED') {
      return _box(Text(
          '🔴 Le test a échoué : ${status['error'] ?? 'erreur inconnue'}',
          style: const TextStyle(color: AppColors.text)));
    }
    final extraction = widget.run['extraction'];
    final texts = {
      'report': widget.run['report'] as String? ?? '',
      'validation': widget.run['validation'] as String? ?? '',
      'transcript': widget.run['transcript'] as String? ?? '',
      'json': extraction == null
          ? ''
          : const JsonEncoder.withIndent('  ').convert(extraction),
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'report', label: Text('Rapport')),
            ButtonSegment(value: 'validation', label: Text('Validation')),
            ButtonSegment(value: 'transcript', label: Text('Transcription')),
            ButtonSegment(value: 'json', label: Text('JSON')),
          ],
          selected: {_tab},
          onSelectionChanged: (s) => setState(() => _tab = s.first),
        ),
        const SizedBox(height: 10),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: () =>
                Clipboard.setData(ClipboardData(text: texts[_tab]!)),
            icon: const Icon(Icons.copy, size: 16),
            label: const Text('Copier'),
          ),
        ),
        _box(MarkdownLite(text: texts[_tab]!, monospace: _tab == 'json')),
      ],
    );
  }
}

/// Just enough Markdown for the reports: headings, bold, quotes, tables.
class MarkdownLite extends StatelessWidget {
  final String text;
  final bool monospace;

  const MarkdownLite({super.key, required this.text, this.monospace = false});

  @override
  Widget build(BuildContext context) {
    if (monospace) {
      return SelectableText(text,
          style: const TextStyle(
              fontFamily: 'monospace', fontSize: 12, color: AppColors.text));
    }
    final lines = text.split('\n');
    final children = <Widget>[];
    var i = 0;
    while (i < lines.length) {
      final line = lines[i];
      if (line.startsWith('|')) {
        final rows = <List<String>>[];
        while (i < lines.length && lines[i].startsWith('|')) {
          final cells = lines[i]
              .split('|')
              .sublist(1)
              .map((c) => c.trim())
              .toList()
            ..removeLast();
          if (!cells.every((c) => RegExp(r'^-+$').hasMatch(c))) rows.add(cells);
          i++;
        }
        children.add(_table(rows));
        continue;
      }
      children.add(_line(line));
      i++;
    }
    return SelectionArea(
      child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }

  Widget _line(String line) {
    if (line.trim().isEmpty) return const SizedBox(height: 6);
    final heading = RegExp(r'^(#{1,3}) (.*)$').firstMatch(line);
    if (heading != null) {
      final size = {1: 20.0, 2: 18.0, 3: 15.5}[heading[1]!.length]!;
      return Padding(
        padding: const EdgeInsets.only(top: 10, bottom: 4),
        child: Text(heading[2]!,
            style: TextStyle(
                color: AppColors.text,
                fontSize: size,
                fontWeight: FontWeight.w800)),
      );
    }
    final quote = line.startsWith('> ');
    return Padding(
      padding: EdgeInsets.only(left: quote ? 10 : 0, bottom: 2),
      child: Text.rich(
        _bold(quote ? line.substring(2) : line),
        style: TextStyle(
            color: quote ? AppColors.warn : AppColors.text,
            fontSize: 13.5,
            height: 1.4),
      ),
    );
  }

  TextSpan _bold(String line) {
    final parts = line.split('**');
    return TextSpan(children: [
      for (var n = 0; n < parts.length; n++)
        TextSpan(
            text: parts[n],
            style:
                n.isOdd ? const TextStyle(fontWeight: FontWeight.w800) : null),
    ]);
  }

  Widget _table(List<List<String>> rows) {
    if (rows.isEmpty) return const SizedBox.shrink();
    final width = rows.map((r) => r.length).reduce((a, b) => a > b ? a : b);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Table(
        defaultColumnWidth: const IntrinsicColumnWidth(),
        border: TableBorder.all(color: const Color(0xFF1A3149)),
        children: [
          for (var r = 0; r < rows.length; r++)
            TableRow(
              decoration:
                  r == 0 ? const BoxDecoration(color: Color(0xFF143966)) : null,
              children: [
                for (var c = 0; c < width; c++)
                  Padding(
                    padding: const EdgeInsets.all(6),
                    child: Text(c < rows[r].length ? rows[r][c] : '',
                        style: TextStyle(
                            color: AppColors.text,
                            fontSize: 12.5,
                            fontWeight:
                                r == 0 ? FontWeight.w700 : FontWeight.normal)),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}
