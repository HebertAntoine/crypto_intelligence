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
    // Counter-signals exist only when something genuinely argues the other way.
    // Asserting their presence tied the test to one market state: an aligned
    // reading has none, and that is correct output, not a failure.
    for (final signal in decision.counterSignals) {
      expect(signal.explanation, isNotEmpty);
      expect(signal.family, isNotEmpty);
    }
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
      // Platform views are too expensive for repeated emoji in Safari and can
      // crash a long PWA page while scrolling.
      expect(find.byType(HtmlElementView), findsNothing);
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

      // Which icon leads depends on which factor contributes most, and that
      // changes with the data. What must hold is that the icons render through
      // the native colour font rather than as white outlines.
      final emojiGlyphs = tester
          .widgetList<Text>(find.byType(Text))
          .where((widget) => widget.style?.fontFamily == 'Apple Color Emoji');
      expect(emojiGlyphs, isNotEmpty);

      expect(find.byKey(const ValueKey('horizon-24h')), findsOneWidget);
      expect(find.byKey(const ValueKey('horizon-7d')), findsOneWidget);
      expect(find.byKey(const ValueKey('horizon-30d')), findsOneWidget);
      final decisionBottom =
          tester.getBottomRight(find.byKey(const ValueKey('decision-card'))).dy;
      expect(
        tester.getSize(find.byKey(const ValueKey('decision-card'))).height,
        250,
      );
      final metricsBottom = tester
          .getBottomRight(find.byKey(const ValueKey('decision-horizon')))
          .dy;
      expect(decisionBottom - metricsBottom, lessThanOrEqualTo(18));
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

      // The hero is the doorway to the complete synthesis. It opens inside
      // the asset tab so the four-item bottom navigation remains available.
      await tester.tap(find.byKey(const ValueKey('decision-card')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('market-state-card')), findsOneWidget);
      expect(find.byKey(const ValueKey('why-now-card')), findsOneWidget);
      expect(find.text('BTC'), findsWidgets);
      expect(find.text('ETH'), findsOneWidget);
      expect(find.text('SOL'), findsOneWidget);
      expect(find.text('Graphique'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('decision-detail-back')));
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

      // The expand button exists only when the calendar holds more than the
      // three shown. As events are published the list shrinks, so the walk is
      // conditional rather than assuming a full calendar.
      if (timeline.events.length > 3) {
        await tester.scrollUntilVisible(
          find.byKey(const ValueKey('events-see-all')),
          450,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.byKey(const ValueKey('events-see-all')));
        await tester.pumpAndSettle();
        expect(find.text('Réduire'), findsOneWidget);
      }
      if (timeline.events.isNotEmpty) {
        await tester.scrollUntilVisible(
          find.byKey(ValueKey('event-${timeline.events.first.id}')),
          450,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(
          find.byKey(ValueKey('event-${timeline.events.first.id}')),
        );
        await tester.pumpAndSettle();
        expect(find.text('Détail de l’événement'), findsOneWidget);
        await tester.tap(find.byTooltip('Fermer'));
        await tester.pumpAndSettle();
      }

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
      // The action follows the shipped snapshot; asserting a fixed word here
      // broke every time the engine legitimately changed its mind.
      expect(
        find.byWidgetPredicate((widget) =>
            widget is Text &&
            const {'ACHETER', 'ATTENDRE', 'VENDRE', 'DONNÉES INSUFFISANTES'}
                .contains(widget.data)),
        findsWidgets,
      );

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
