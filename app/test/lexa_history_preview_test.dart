/// Rend l'historique Lexa en image, pour le regarder plutôt que l'imaginer.
///
/// Ce n'est pas une assertion : c'est le seul moyen de voir ce que la page
/// peint réellement. Ne tourne qu'avec `--dart-define=PREVIEW_DIR=dossier`,
/// et sur la fixture fictive — jamais sur la base privée.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto_intelligence_app/lexa/lexa_client.dart';
import 'package:crypto_intelligence_app/lexa/lexa_history_screen.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _out = String.fromEnvironment('PREVIEW_DIR', defaultValue: '');

Future<void> _load(String family, String path) async {
  final file = File(path);
  if (!file.existsSync()) return;
  final loader = FontLoader(family)
    ..addFont(Future.value(file.readAsBytesSync().buffer.asByteData()));
  await loader.load();
}

Future<void> _loadRealFonts() async {
  for (final family in const ['Roboto', 'FlutterTest', 'Ahem', '.SF Pro Text']) {
    await _load(family, '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf');
    await _load(family, '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf');
  }
  for (final family in const ['Apple Color Emoji', 'Noto Color Emoji']) {
    await _load(family, '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf');
  }
}

void main() {
  if (_out.isEmpty) return;

  testWidgets('historique Lexa', (tester) async {
    await tester.runAsync(_loadRealFonts);
    final fixtures = jsonDecode(
        File('test/fixtures/lexa_fictive.json').readAsStringSync()) as Map<String, dynamic>;
    final client = LexaClient(
      baseUrl: 'http://127.0.0.1:8100',
      client: MockClient((request) async => http.Response(
          jsonEncode(fixtures['history_by_day']), 200,
          headers: {'content-type': 'application/json; charset=utf-8'})),
    );

    tester.view.physicalSize = const Size(430, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(RepaintBoundary(
      key: const ValueKey('shot'),
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.dark,
        home: LexaHistoryScreen(client: client),
      ),
    ));
    await tester.pumpAndSettle();
    await expectLater(find.byKey(const ValueKey('shot')),
        matchesGoldenFile('$_out/lexa-historique.png'));
  });
}
