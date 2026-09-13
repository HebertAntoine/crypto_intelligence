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
  test('the shipped decision exposes reasons and counter-signals', () async {
    final decision = await _shippedClient().futureDecision('BTC');

    expect(decision.reasons, hasLength(greaterThanOrEqualTo(4)));
    expect(decision.counterSignals, isNotEmpty);
    expect(decision.counterSignals.first.explanation, isNotEmpty);
  });

  testWidgets(
    'BTC, ETH, SOL keep their full decision page and Graphique is last',
    (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      final client = _shippedClient();
      final timeline = await client.futureTimeline('BTC');

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.dark,
          home: HomeShell(
            client: client,
            livePrices: _SilentLivePrices(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('BTC'), findsWidgets);
      expect(find.text('ETH'), findsOneWidget);
      expect(find.text('SOL'), findsOneWidget);
      expect(find.text('Graphique'), findsOneWidget);
      expect(find.byKey(const ValueKey('nav-logo-BTC')), findsOneWidget);
      expect(find.byKey(const ValueKey('nav-logo-ETH')), findsOneWidget);
      expect(find.byKey(const ValueKey('nav-logo-SOL')), findsOneWidget);
      expect(find.text('Bitcoin'), findsOneWidget);
      expect(
        find.text('EST-CE LE BON MOMENT POUR ACHETER ?'),
        findsOneWidget,
      );
      // The main page now answers the decision in one screen: the market
      // context, the scenarios and the five families moved behind "Voir les
      // détails" instead of being stacked under the decision.
      expect(find.text('CONTEXTE ACTUEL'), findsNothing);
      expect(find.byKey(const ValueKey('see-full-details')), findsOneWidget);

      // At most five reasons, so the "why" stays readable at a glance. The
      // exact count follows the data: duplicated families are not repeated.
      expect(find.byKey(const ValueKey('decision-reason-1')), findsOneWidget);
      expect(find.byKey(const ValueKey('decision-reason-4')), findsOneWidget);
      expect(find.byKey(const ValueKey('decision-reason-6')), findsNothing);

      // Confidence is a coarse level, never an uncalibrated percentage. The
      // 24 h price change keeps its own percent sign, which is a measurement.
      expect(find.text('Confiance'), findsOneWidget);
      expect(
        find.byWidgetPredicate((widget) =>
            widget is Text &&
            const {'FAIBLE', 'MOYENNE', 'ÉLEVÉE'}.contains(widget.data)),
        findsWidgets,
      );

      final firstReasonEmoji = tester.widget<Text>(find.text('🏛️').first);
      expect(
        firstReasonEmoji.style?.fontFamilyFallback,
        contains('Apple Color Emoji'),
      );

      expect(find.byKey(const ValueKey('horizon-24h')), findsOneWidget);
      expect(find.byKey(const ValueKey('horizon-7d')), findsOneWidget);
      expect(find.byKey(const ValueKey('horizon-30d')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('horizon-24h')).last);
      await tester.pumpAndSettle();
      // Switching horizon rebuilds the reasons; the five-reason cap holds on
      // every horizon, not only the one the page opened on.
      expect(find.byKey(const ValueKey('decision-reason-1')), findsOneWidget);
      expect(find.byKey(const ValueKey('decision-reason-6')), findsNothing);

      await tester.tap(find.byKey(const ValueKey('decision-horizon')));
      await tester.pumpAndSettle();
      expect(find.text('Choisir l’horizon'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('horizon-24h')).last);
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('why-see-all')),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byKey(const ValueKey('why-see-all')));
      await tester.pumpAndSettle();
      expect(find.text('Détails des facteurs'), findsOneWidget);
      await tester.tap(find.byTooltip('Fermer'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('events-see-all')),
        450,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byKey(const ValueKey('events-see-all')));
      await tester.pumpAndSettle();
      expect(find.text('Réduire'), findsOneWidget);
      await tester.tap(
        find.byKey(ValueKey('event-${timeline.events.first.id}')),
      );
      await tester.pumpAndSettle();
      expect(find.text('Détail de l’événement'), findsOneWidget);
      await tester.tap(find.byTooltip('Fermer'));
      await tester.pumpAndSettle();

      // Scenarios, market context and the five families left the main page.
      // They are still in the app, one tap behind "Voir les détails".
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('see-full-details')),
        450,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byKey(const ValueKey('see-full-details')));
      await tester.pumpAndSettle();
      expect(find.text('Détails complets'), findsOneWidget);
      expect(find.byKey(const ValueKey('scenarios-see-details')), findsWidgets);
      await tester.tapAt(const Offset(200, 20));
      await tester.pumpAndSettle();

      await tester.tap(find.text('ETH'));
      await tester.pumpAndSettle();
      expect(find.text('Ethereum'), findsOneWidget);
      expect(
        find.text('EST-CE LE BON MOMENT POUR ACHETER ?'),
        findsOneWidget,
      );

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

  testWidgets('the asset pages do not overflow on a 360 px phone',
      (tester) async {
    tester.view.physicalSize = const Size(360, 800);
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
    await tester.tap(find.text('ETH'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('SOL'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
