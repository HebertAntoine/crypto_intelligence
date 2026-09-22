/// Renders the home to an image, for inspection against the validated mockup.
///
/// Not an assertion: the only way to look at what the page actually paints.
/// Runs only with `--dart-define=PREVIEW_DIR=dir`.
library;

import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/live_prices/live_price_service.dart';
import 'package:crypto_intelligence_app/main.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

const _out = String.fromEnvironment('PREVIEW_DIR', defaultValue: '');

class _SilentLivePrices implements LivePriceSource {
  @override
  LivePriceState get current =>
      LivePriceState(connection: LivePriceConnection.stopped);
  @override
  Stream<LivePriceState> get updates => const Stream.empty();
}

Future<void> _load(String family, String path) async {
  final file = File(path);
  if (!file.existsSync()) return;
  final loader = FontLoader(family)
    ..addFont(Future.value(file.readAsBytesSync().buffer.asByteData()));
  await loader.load();
}

/// Without real fonts `flutter test` paints every glyph as a box.
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

  for (final asset in ['BTC', 'ETH', 'SOL']) {
    testWidgets('home $asset', (tester) async {
      await tester.runAsync(_loadRealFonts);
      tester.view.physicalSize = const Size(430, 1560);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(RepaintBoundary(
        key: const ValueKey('shot'),
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: AppTheme.dark,
          home: HomeShell(
            client: ApiClient(
              baseUrl: '',
              loadAsset: (path) async => File(path).readAsStringSync(),
            ),
            livePrices: _SilentLivePrices(),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.text(asset).last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('horizon-7d')).last);
      await tester.pumpAndSettle();
      // « Comprendre le mouvement »: the narrative, the roles, and the market
      // explanation that used to take a card on the home.
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('situation-understand')),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byKey(const ValueKey('situation-understand')));
      await tester.pumpAndSettle();
      await expectLater(
        find.byKey(const ValueKey('shot')),
        matchesGoldenFile('$_out/mouvement-$asset.png'),
      );
      Navigator.of(tester.element(find.byKey(const ValueKey('movement-view'))))
          .pop();
      await tester.pumpAndSettle();
      // Let the background image decode.
      await tester.runAsync(() => Future<void>.delayed(
            const Duration(milliseconds: 300),
          ));
      await tester.pumpAndSettle();
      // Back to the top: the home shot must show what opens the page.
      await tester.dragUntilVisible(find.byKey(const ValueKey('decision-card')),
          find.byType(Scrollable).first, const Offset(0, 300));
      await tester.pumpAndSettle();

      await expectLater(
        find.byKey(const ValueKey('shot')),
        matchesGoldenFile('$_out/home-$asset.png'),
      );
    });
  }

  for (final asset in ['BTC']) {
    testWidgets('full analysis $asset', (tester) async {
      await tester.runAsync(_loadRealFonts);
      tester.view.physicalSize = const Size(430, 2600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(RepaintBoundary(
        key: const ValueKey('shot'),
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: AppTheme.dark,
          home: HomeShell(
            client: ApiClient(
              baseUrl: '',
              loadAsset: (path) async => File(path).readAsStringSync(),
            ),
            livePrices: _SilentLivePrices(),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('horizon-7d')).last);
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('see-full-analysis')),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byKey(const ValueKey('see-full-analysis')));
      await tester.pumpAndSettle();
      await expectLater(
        find.byKey(const ValueKey('shot')),
        matchesGoldenFile('$_out/full-$asset.png'),
      );
      await tester.tap(find.byKey(const ValueKey('family-derivatives')));
      await tester.pumpAndSettle();
      await expectLater(
        find.byKey(const ValueKey('shot')),
        matchesGoldenFile('$_out/family-derivatives-$asset.png'),
      );
      await tester.tap(find.byKey(const ValueKey('family-detail-back')));
      await tester.pumpAndSettle();
      // The cycle opens its own page: phase, chart, history.
      final cycle = find.byKey(const ValueKey('family-cycle'));
      await tester.scrollUntilVisible(cycle, 300,
          scrollable: find.byType(Scrollable).last);
      await tester.tap(cycle);
      await tester.pumpAndSettle();
      await expectLater(
        find.byKey(const ValueKey('shot')),
        matchesGoldenFile('$_out/cycle-$asset.png'),
      );
    });
  }
}
