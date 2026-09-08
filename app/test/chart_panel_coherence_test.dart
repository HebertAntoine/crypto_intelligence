/// La fiche « Pattern détecté » et le graphique doivent parler de la même
/// figure.
///
/// `/structure` détecte sur tout l'historique conservé, `/chart` sur la seule
/// fenêtre affichée. Les deux trouvaient donc des figures différentes, et
/// l'écran mettait en avant celle de `/structure` pendant que le graphique
/// dessinait l'autre — ou rien. Le lecteur voyait « ETE inversée » annoncée en
/// gros au-dessus d'un graphique où elle n'était nulle part.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/screens/chart_screen.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Un client servant les instantanés livrés, sauf ceux qu'on remplace.
ApiClient _client(Map<String, Object> overrides) => ApiClient(
      baseUrl: '',
      loadAsset: (path) async {
        final name = path.split('/').last;
        final override = overrides[name];
        if (override != null) return jsonEncode(override);
        final file = File(path);
        if (!file.existsSync()) throw Exception('asset absent: $path');
        return file.readAsStringSync();
      },
    );

/// Une réponse `/structure` qui annonce une figure, avec le range minimal dont
/// l'écran a besoin.
Map<String, Object?> _structureWith(List<String> patterns) => {
      'asset': 'SOL',
      'timeframe': '4h',
      'location': const {'price': 200.0, 'location': 'MID_RANGE'},
      'market_structure': const {},
      'patterns': [
        for (final name in patterns)
          {
            'name': name,
            'pattern_class': 'DETERMINISTIC',
            'state': 'CANDIDATE',
            'recognition_confidence': 61.0,
            'direction_if_textbook': 'BULLISH',
            'key_levels': const <String, double>{},
            'invalidation_rule': '',
            'edge_state': 'NOT_YET_TESTED',
            'notes': '',
          },
      ],
    };

/// Une réponse `/chart` sans aucune figure dans la fenêtre.
Map<String, Object?> _chartWithoutPatterns() => {
      'asset': 'SOL',
      'timeframe': '4h',
      'period': '7d',
      'available': true,
      'candles': const <dynamic>[],
      'summary': const {'available': true},
      'structural_patterns': const <dynamic>[],
    };

Future<void> _openSol4h(WidgetTester tester, ApiClient client) async {
  tester.view.physicalSize = const Size(2200, 2000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    MaterialApp(theme: AppTheme.dark, home: ChartScreen(client: client)),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text('SOL').first);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
      'une figure hors de la fenêtre n’est pas annoncée comme dessinée',
      (tester) async {
    final client = _client({
      'structure__SOL__timeframe-4h.json':
          _structureWith(['inverse_head_and_shoulders']),
      'chart__SOL__period-7d__timeframe-4h.json': _chartWithoutPatterns(),
    });

    await _openSol4h(tester, client);
    expect(tester.takeException(), isNull);

    // Le titre ne promet pas une figure que le graphique ne trace pas...
    expect(find.text('Pattern détecté'), findsNothing);
    expect(find.text('Structure détectée'), findsWidgets);
    // ... mais la détection réelle n'est pas effacée pour autant.
    expect(
      find.textContaining('hors de la fenêtre affichée'),
      findsOneWidget,
    );
  });

  testWidgets('sans divergence, aucune mention parasite n’apparaît',
      (tester) async {
    final client = _client({
      'structure__SOL__timeframe-4h.json': _structureWith(const []),
      'chart__SOL__period-7d__timeframe-4h.json': _chartWithoutPatterns(),
    });

    await _openSol4h(tester, client);
    expect(tester.takeException(), isNull);
    expect(find.textContaining('hors de la fenêtre affichée'), findsNothing);
  });
}
