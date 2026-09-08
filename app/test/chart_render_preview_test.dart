/// Rend le graphique dans un fichier image, pour inspection.
///
/// Ce n'est pas une assertion: c'est le seul moyen de regarder réellement ce
/// que le peintre produit, au lieu d'affirmer qu'un tracé est correct sans
/// l'avoir vu.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/chart/candle_chart.dart';
import 'package:crypto_intelligence_app/chart/chart_layers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

const _out = String.fromEnvironment('PREVIEW_DIR', defaultValue: '');

Map<String, dynamic> _json(String name) =>
    jsonDecode(File('assets/api_snapshots/$name').readAsStringSync())
        as Map<String, dynamic>;

ChartRead _snapshot(String name) => ChartRead.fromJson(_json(name));

/// La lecture structurelle livrée pour la même vue: zones, range, position.
StructuralLocation? _location(String asset, String timeframe) {
  final file = File('assets/api_snapshots/structure__${asset}__timeframe-$timeframe.json');
  if (!file.existsSync()) return null;
  return StructureRead.fromJson(
    jsonDecode(file.readAsStringSync()) as Map<String, dynamic>,
  ).location;
}

/// Charge une vraie police sous le nom par défaut.
///
/// Sans elle, `flutter test` peint chaque glyphe en rectangle plein: on
/// vérifie les positions mais on ne peut rien lire. Or ce qui est écrit sur un
/// graphique fait partie de ce qu'il faut vérifier.
Future<void> _loadRealFont() async {
  for (final path in const [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
  ]) {
    final file = File(path);
    if (!file.existsSync()) continue;
    for (final family in const ['Roboto', 'FlutterTest', 'Ahem', 'packages/flutter_test/FlutterTest']) {
      final loader = FontLoader(family)
        ..addFont(Future.value(file.readAsBytesSync().buffer.asByteData()));
      await loader.load();
    }
    final loader = FontLoader('_unused_')
      ..addFont(Future.value(file.readAsBytesSync().buffer.asByteData()));
    await loader.load();
  }
}

void main() {
  if (_out.isEmpty) return;

  // Actif, unité, fichier /chart. La lecture structurelle est chargée en
  // parallèle: c'est la combinaison figures + zones + range qui charge le
  // haut du cadre, donc c'est elle qu'il faut regarder.
  for (final entry in const {
    'eth-4h': ('ETH', '4h', 'chart__ETH__period-7d__timeframe-4h.json'),
    'eth-1h': ('ETH', '1h', 'chart__ETH__period-7d__timeframe-1h.json'),
    'sol-1d': ('SOL', '1d', 'chart__SOL__period-3m__timeframe-1d.json'),
    'btc-1d': ('BTC', '1d', 'chart__BTC__period-3m__timeframe-1d.json'),
    'btc-1w': ('BTC', '1w', 'chart__BTC__period-max__timeframe-1w.json'),
  }.entries) {
    testWidgets('aperçu ${entry.key}', (tester) async {
      await _loadRealFont();
      final (asset, timeframe, file) = entry.value;
      final read = _snapshot(file);
      tester.view.physicalSize = const Size(900, 620);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: RepaintBoundary(
            child: SizedBox(
              width: 900,
              height: 620,
              child: CandleChart(
                candles: read.candles,
                timeframe: read.timeframe,
                layers: ChartLayerSet.initial(),
                pair: read.pair.isEmpty ? read.symbol : read.pair,
                source: read.source,
                patterns: read.structuralPatterns,
                location: _location(asset, timeframe),
              ),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await expectLater(
        find.byType(CandleChart),
        matchesGoldenFile('$_out/${entry.key}.png'),
      );
    });
  }
}
