/// 🎙️ Écouter une vidéo Lexa — tout le reste se fait tout seul.
///
/// The member plays the video normally. The app listens (microphone, or the
/// audio of a shared tab on a computer), the PC transcribes locally, the
/// chain extracts and verifies the levels, and the plan appears in the Lexa
/// tab. The very first video waits for the member's check; after that,
/// imports are automatic if they switch it on.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../widgets/color_emoji.dart';
import '../widgets/mobile_kit.dart';
import 'lexa_client.dart';
import 'lexa_test_screen.dart';
import 'lexa_ui.dart';
import 'recorder/recorder.dart';

class LexaListenScreen extends StatefulWidget {
  final LexaClient client;
  final LexaRecorder? recorder;
  final Duration pollEvery;

  const LexaListenScreen({
    super.key,
    required this.client,
    this.recorder,
    this.pollEvery = const Duration(seconds: 4),
  });

  @override
  State<LexaListenScreen> createState() => _LexaListenScreenState();
}

enum _Phase { ready, listening, working, done }

class _LexaListenScreenState extends State<LexaListenScreen> {
  late final LexaRecorder _recorder = widget.recorder ?? LexaRecorder();
  final _title = TextEditingController();
  DateTime _published = DateTime.now();
  bool _shareTab = false;
  _Phase _phase = _Phase.ready;
  String? _sid;
  String? _error;
  int _sent = 0;
  final _watch = Stopwatch();
  Timer? _tick;
  Map<String, dynamic>? _status;
  Map<String, dynamic>? _run;
  bool _autoImport = false;
  bool _autoAllowed = false;

  bool get _desktopWeb =>
      kIsWeb &&
      defaultTargetPlatform != TargetPlatform.iOS &&
      defaultTargetPlatform != TargetPlatform.android;

  @override
  void initState() {
    super.initState();
    widget.client.autoImport().then((v) {
      if (mounted) {
        setState(() {
          _autoImport = v['enabled'] == true;
          _autoAllowed = v['allowed'] == true;
        });
      }
    }).catchError((_) {});
  }

  @override
  void dispose() {
    _tick?.cancel();
    if (_recorder.running) _recorder.stop();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() => _error = null);
    try {
      final sid = await widget.client.startListen(
        title: _title.text.trim(),
        publishedAt: DateTime(_published.year, _published.month, _published.day,
                _published.hour, _published.minute)
            .toUtc()
            .toIso8601String(),
      );
      _sid = sid;
      await _recorder.start(
        shareTab: _shareTab,
        onChunk: (bytes, mime) async {
          await widget.client.sendChunk(sid, bytes, mime);
          if (mounted) setState(() => _sent++);
        },
      );
      _watch
        ..reset()
        ..start();
      setState(() => _phase = _Phase.listening);
      _poll();
    } catch (e) {
      setState(() => _error = e is LexaException
          ? e.message
          : 'Impossible d\'écouter : autorise le micro pour cette page. ($e)');
    }
  }

  Future<void> _stop() async {
    setState(() => _phase = _Phase.working);
    _watch.stop();
    try {
      await _recorder.stop();
      await widget.client.finishListen(_sid!);
    } on LexaException catch (e) {
      setState(() => _error = e.message);
    }
  }

  void _poll() {
    _tick?.cancel();
    Future<void> tick() async {
      if (!mounted || _sid == null) return;
      try {
        final st = await widget.client.listenStatus(_sid!);
        if (!mounted) return;
        setState(() => _status = st);
        final state = st['state'];
        if (state == 'TO_VALIDATE' && st['run_id'] != null && _run == null) {
          final run = await widget.client.testRun('${st['run_id']}');
          if (mounted) setState(() => _run = run);
        }
        if (state == 'IMPORTED' ||
            state == 'TO_VALIDATE' ||
            state == 'FAILED') {
          setState(() => _phase = _Phase.done);
          return;
        }
      } on LexaException catch (e) {
        if (mounted) setState(() => _error = e.message);
      }
      _tick = Timer(widget.pollEvery, tick);
    }

    tick();
  }

  String _elapsed() {
    final s = _watch.elapsed.inSeconds;
    return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF06101C),
      appBar: AppBar(
        backgroundColor: const Color(0xFF06101C),
        title: lexaLabel('🎙️ Écouter une vidéo'),
      ),
      body: MobileGradientFrame(
        child: LexaEmojiFonts(
          child: MobileScrollView(
            padding: const EdgeInsets.fromLTRB(18, 12, 18, 120),
            children: [
              ...switch (_phase) {
                _Phase.ready => _ready(),
                _Phase.listening => _listening(),
                _Phase.working => _working(),
                _Phase.done => _done(),
              },
              if (_error != null) ...[
                const SizedBox(height: 12),
                GlassPanel(
                  borderColor: lexaOrange,
                  child: Text('⚠️ $_error',
                      style: const TextStyle(color: Colors.white)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _ready() => [
        GlassPanel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const LexaSectionTitle(emoji: '🎬', text: 'Comment ça marche'),
              const SizedBox(height: 8),
              const Text(
                '1. Lance la vidéo Lexa normalement, sur la plateforme.\n'
                '2. Appuie sur « Démarrer l\'écoute » et laisse la vidéo jouer.\n'
                '3. À la fin, appuie sur « Terminer » : la transcription, les '
                'niveaux, le plan et le suivi se font tout seuls.',
                style:
                    TextStyle(color: lexaWhite, fontSize: 14.5, height: 1.45),
              ),
              lexaNote(_desktopWeb
                  ? 'Sur ordinateur, « Onglet » capte le son de l\'onglet de la '
                      'vidéo sans micro (meilleure qualité).'
                  : 'Sur iPhone : lis la vidéo sur un autre écran (ordinateur, '
                      'TV) et pose le téléphone près du haut-parleur, écran allumé.'),
              lexaNote(
                  'Aucun son n\'est conservé : chaque morceau est effacé dès '
                  'qu\'il est transcrit, sur ton PC.'),
            ],
          ),
        ),
        const SizedBox(height: 14),
        GlassPanel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _title,
                style: const TextStyle(color: Colors.white),
                decoration: const InputDecoration(
                    labelText: 'Titre de la vidéo (facultatif)'),
              ),
              const SizedBox(height: 8),
              LexaLine('Date de la vidéo', dayMonth(_published)),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () async {
                    final day = await showDatePicker(
                      context: context,
                      initialDate: _published,
                      firstDate:
                          DateTime.now().subtract(const Duration(days: 365)),
                      lastDate: DateTime.now(),
                    );
                    if (day != null) setState(() => _published = day);
                  },
                  child: const Text('Changer la date'),
                ),
              ),
              if (_desktopWeb)
                Wrap(spacing: 8, children: [
                  LexaChip(
                      label: '🎙️ Micro',
                      selected: !_shareTab,
                      onTap: () => setState(() => _shareTab = false)),
                  LexaChip(
                      label: '🖥️ Onglet',
                      selected: _shareTab,
                      onTap: () => setState(() => _shareTab = true)),
                ]),
              const SizedBox(height: 10),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: _autoImport,
                onChanged: _autoAllowed
                    ? (v) async {
                        try {
                          final r = await widget.client.setAutoImport(v);
                          setState(() => _autoImport = r['enabled'] == true);
                        } on LexaException catch (e) {
                          setState(() => _error = e.message);
                        }
                      }
                    : null,
                title: const Text('Créer le plan automatiquement',
                    style: TextStyle(color: Colors.white)),
                subtitle: Text(
                    _autoAllowed
                        ? 'Seules les valeurs retrouvées dans la vidéo sont importées.'
                        : 'S\'active après ta validation de la première vidéo.',
                    style: const TextStyle(color: lexaMuted, fontSize: 12.5)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const ValueKey('lexa-listen-start'),
          onPressed: _recorder.supported ? _start : null,
          style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16)),
          child: lexaLabel(_recorder.supported
              ? '🎙️ Démarrer l\'écoute'
              : '🎙️ Écoute disponible dans le navigateur uniquement'),
        ),
      ];

  List<Widget> _listening() {
    final preview = (_status?['preview'] as List? ?? const []).cast<Map>();
    return [
      GlassPanel(
        borderColor: lexaRed,
        child: Column(
          children: [
            const ColorEmoji(emoji: '🔴', size: 28),
            const SizedBox(height: 8),
            Text('Écoute en cours — ${_elapsed()}',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text(
                '$_sent morceau(x) envoyé(s) · ${_status?['segments'] ?? 0} phrase(s) transcrite(s)',
                style: const TextStyle(color: lexaMuted)),
            lexaNote('Laisse la vidéo jouer jusqu\'au bout, écran allumé.'),
          ],
        ),
      ),
      if (preview.isNotEmpty) ...[
        const SizedBox(height: 14),
        GlassPanel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const LexaSectionTitle(emoji: '📝', text: 'Dernières phrases'),
              for (final p in preview)
                lexaNote('[${fmtTimestamp(p['start_s'] as int?)}] ${p['text']}',
                    color: lexaWhite),
            ],
          ),
        ),
      ],
      const SizedBox(height: 16),
      FilledButton(
        key: const ValueKey('lexa-listen-stop'),
        onPressed: _stop,
        style: FilledButton.styleFrom(
            backgroundColor: lexaRed,
            padding: const EdgeInsets.symmetric(vertical: 16)),
        child: lexaLabel('⏹️ Terminer'),
      ),
    ];
  }

  List<Widget> _working() {
    final state = _status?['state'];
    final text = state == 'ANALYSING'
        ? 'Analyse des niveaux par le modèle local… (environ une minute par crypto)'
        : 'Fin de la transcription…';
    return [
      GlassPanel(
        child: Column(children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 14),
          Text(text,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white, fontSize: 16)),
          lexaNote('Tu peux quitter cette page : le PC continue tout seul.'),
        ]),
      ),
    ];
  }

  List<Widget> _done() {
    final st = _status ?? const {};
    final state = st['state'];
    if (state == 'IMPORTED') {
      return [
        GlassPanel(
          borderColor: lexaGreen,
          child: Column(children: [
            const ColorEmoji(emoji: '✅', size: 30),
            const SizedBox(height: 8),
            const Text('Plan créé',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w800)),
            lexaNote('Les niveaux retrouvés dans la vidéo sont suivis dans '
                'l\'onglet Lexa, avec leurs passages.'),
            const SizedBox(height: 10),
            FilledButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Voir les plans')),
          ]),
        ),
      ];
    }
    if (state == 'FAILED') {
      return [
        GlassPanel(
          borderColor: lexaOrange,
          child: Text('⚠️ ${st['error'] ?? 'Analyse impossible.'}',
              style: const TextStyle(color: Colors.white)),
        ),
      ];
    }
    return [
      GlassPanel(
        borderColor: lexaOrange,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const LexaSectionTitle(emoji: '🧪', text: 'À vérifier une fois'),
            lexaNote('Première vidéo : vérifie le rapport, puis importe-le. '
                'Ensuite, active « Créer le plan automatiquement » et les '
                'prochaines vidéos se feront toutes seules.'),
            if ((st['uncertain_numbers'] as num? ?? 0) > 0)
              lexaNote(
                  '⚠️ ${st['uncertain_numbers']} nombre(s) reconstitué(s) '
                  'depuis la parole : vérifie-les.',
                  color: lexaOrange),
          ],
        ),
      ),
      const SizedBox(height: 12),
      if (_run != null) LexaTestRunView(run: _run!),
      if (st['run_id'] != null)
        Padding(
          padding: const EdgeInsets.only(top: 10),
          child: FilledButton(
            key: const ValueKey('lexa-listen-import'),
            onPressed: () async {
              try {
                await widget.client.importTestRun('${st['run_id']}');
                final r = await widget.client.setAutoImport(true);
                if (!mounted) return;
                setState(() {
                  _autoImport = r['enabled'] == true;
                  _status = {...st, 'state': 'IMPORTED'};
                });
              } on LexaException catch (e) {
                setState(() => _error = e.message);
              }
            },
            child: lexaLabel('✅ C\'est juste — créer le plan'),
          ),
        ),
    ];
  }
}
