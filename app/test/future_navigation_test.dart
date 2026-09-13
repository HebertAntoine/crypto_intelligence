/// Regression test for the four-page mobile navigation and the exact future
/// snapshots shipped to the static deployment.
library;

import 'dart:async';
import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/live_prices/live_price_service.dart';
import 'package:crypto_intelligence_app/main.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _SilentLivePrices implements LivePriceSource {
  @override
  LivePriceState get current =>
      LivePriceState(connection: LivePriceConnection.stopped);

  @override
  Stream<LivePriceState> get updates => const Stream.empty();
}

ApiClient _shippedClient() => ApiClient(
      baseUrl: '',
      loadAsset: (path) async {
        final file = File(path);
        if (!file.existsSync()) throw Exception('asset absent: $path');
        return file.readAsStringSync();
      },
    );

void main() {
  testWidgets(
    'BTC, ETH, SOL keep their full decision page and Graphique is last',
    (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.dark,
          home: HomeShell(
            client: _shippedClient(),
            livePrices: _SilentLivePrices(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('BTC'), findsWidgets);
      expect(find.text('ETH'), findsOneWidget);
      expect(find.text('SOL'), findsOneWidget);
      expect(find.text('Graphique'), findsOneWidget);
      expect(find.text('Bitcoin'), findsOneWidget);
      expect(find.text('EST-CE LE BON MOMENT POUR ACHETER ?'), findsOneWidget);
      expect(find.text('CONTEXTE ACTUEL'), findsOneWidget);

      await tester.tap(find.text('ETH'));
      await tester.pumpAndSettle();
      expect(find.text('Ethereum'), findsOneWidget);
      expect(find.text('EST-CE LE BON MOMENT POUR ACHETER ?'), findsOneWidget);

      await tester.tap(find.text('SOL'));
      await tester.pumpAndSettle();
      expect(find.text('Solana'), findsOneWidget);
      expect(find.text('VENDRE'), findsOneWidget);

      await tester.tap(find.text('Graphique'));
      await tester.pumpAndSettle();
      expect(find.text('Intelligence graphique'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
