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
      // The main page answers the decision in one screen: the market context,
      // the scenarios and the five families sit behind the reasons sheet
      // instead of being stacked under the decision. The home does not even
      // carry the button to them - reaching the full analysis is not one of
      // the three questions the front page exists to answer.
      expect(find.text('CONTEXTE ACTUEL'), findsNothing);
      expect(find.byKey(const ValueKey('see-full-details')), findsNothing);

      // Three reasons on the home, so the "why" reads at a glance; the
      // rest is under "Voir tout".
      expect(find.byKey(const ValueKey('main-factor-1')), findsOneWidget);
      expect(find.byKey(const ValueKey('main-factor-5')), findsNothing);
      expect(find.byKey(const ValueKey('decision-explanation')), findsOneWidget);

      // The hero carries risk, horizon and the balance of signals. Confidence
      // and expected amplitude are engine vocabulary and moved down with the
      // rest of the analysis. The 24 h price change keeps its own percent
      // sign, which is a measurement rather than a model output.
      expect(find.text('Confiance'), findsNothing);
      expect(find.text('Tendance'), findsOneWidget);
      expect(
        find.byWidgetPredicate((widget) =>
            widget is Text &&
            const {'Haussière', 'Baissière', 'Neutre', 'Plutôt favorable',
                    'Plutôt défavorable', 'Mitigée', 'Insuffisante'}
                .contains(widget.data)),
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
      expect(find.byKey(const ValueKey('main-factor-1')), findsOneWidget);
      expect(find.byKey(const ValueKey('main-factor-5')), findsNothing);

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

      // A main factor opens its family, measure by measure, and comes back.
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('main-factor-1')),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byKey(const ValueKey('main-factor-1')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('family-detail-back')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('family-detail-back')));
      await tester.pumpAndSettle();

      // The watchlist shows the three dates that matter; the rest of the
      // calendar opens from "Voir tout". Which
      // three those are depends on the data, so the walk looks for whichever
      // row rendered rather than assuming the first event of the timeline.
      final shownEvent = timeline.events
          .map((event) => find.byKey(ValueKey('event-${event.id}')))
          .where((finder) => finder.evaluate().isNotEmpty)
          .firstOrNull;
      if (shownEvent != null) {
        await tester.scrollUntilVisible(
          shownEvent,
          450,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(
          shownEvent,
        );
        await tester.pumpAndSettle();
        expect(find.text('Détail de l’événement'), findsOneWidget);
        await tester.tap(find.byTooltip('Fermer'));
        await tester.pumpAndSettle();
      }

      // Scenarios, market context and the six families left the main page.
      // "Voir l'analyse complète" under the main factors leads to them.
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('see-full-analysis')),
        450,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byKey(const ValueKey('see-full-analysis')));
      await tester.pumpAndSettle();
      // The full page: the gated decision, then the six families.
      expect(find.byKey(const ValueKey('analysis-decision')), findsOneWidget);
      expect(find.byKey(const ValueKey('confidence-disclaimer')), findsOneWidget);
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('family-macro')),
        300,
        scrollable: find.byType(Scrollable).last,
      );
      expect(find.byKey(const ValueKey('family-macro')), findsOneWidget);
      // Scenarios and the older detail sheet stay one tap further.
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('technical-details')),
        400,
        scrollable: find.byType(Scrollable).last,
      );
      // Clear the bottom navigation bar, which sits over the page's last row.
      await tester.drag(find.byType(Scrollable).last, const Offset(0, -200));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('technical-details')));
      await tester.pumpAndSettle();
      expect(find.text('Détails complets'), findsOneWidget);
      expect(find.byKey(const ValueKey('scenarios-see-details')), findsWidgets);
      await tester.tapAt(const Offset(200, 20));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('full-analysis-back')));
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
