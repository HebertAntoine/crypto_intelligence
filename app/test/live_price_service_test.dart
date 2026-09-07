import 'dart:async';
import 'dart:convert';

import 'package:crypto_intelligence_app/live_prices/live_price_service.dart';
import 'package:crypto_intelligence_app/widgets/live_price_builder.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

LivePriceTick _tick(String asset, double price) => LivePriceTick(
      asset: asset,
      priceEur: price,
      change24hPct: 1.25,
      marketTimestamp: DateTime.utc(2026, 9, 7, 12),
      receivedAt: DateTime.utc(2026, 9, 7, 12),
    );

class _FakeLivePriceSource implements LivePriceSource {
  final controller = StreamController<LivePriceState>.broadcast();

  @override
  LivePriceState current;

  _FakeLivePriceSource(this.current);

  @override
  Stream<LivePriceState> get updates => controller.stream;

  void push(LivePriceState state) {
    current = state;
    controller.add(state);
  }
}

void main() {
  group('Kraken ticker parser', () {
    test('reads the three direct EUR pairs from a ticker message', () {
      final receivedAt = DateTime.utc(2026, 9, 7, 12, 0, 1);
      final ticks = parseKrakenTickerMessage(
        jsonEncode({
          'channel': 'ticker',
          'type': 'snapshot',
          'data': [
            {
              'symbol': 'BTC/EUR',
              'last': 98765.4,
              'change_pct': -0.42,
              'timestamp': '2026-09-07T12:00:00Z',
            },
            {
              'symbol': 'ETH/EUR',
              'last': '4321.25',
              'change_pct': '1.75',
              'timestamp': '2026-09-07T12:00:00.500Z',
            },
            {
              'symbol': 'SOL/EUR',
              'last': 210.12,
              'change_pct': 3.2,
              'timestamp': '2026-09-07T12:00:00.750Z',
            },
          ],
        }),
        receivedAt: receivedAt,
      );

      expect(ticks.map((tick) => tick.asset), ['BTC', 'ETH', 'SOL']);
      expect(ticks[0].priceEur, 98765.4);
      expect(ticks[1].change24hPct, 1.75);
      expect(ticks[2].receivedAt, receivedAt);
    });

    test('ignores heartbeats, other currencies and malformed values', () {
      expect(
        parseKrakenTickerMessage('{"channel":"heartbeat"}'),
        isEmpty,
      );
      expect(
        parseKrakenTickerMessage({
          'channel': 'ticker',
          'data': [
            {
              'symbol': 'BTC/USD',
              'last': 100000,
              'change_pct': 1,
              'timestamp': '2026-09-07T12:00:00Z',
            },
            {
              'symbol': 'ETH/EUR',
              'last': 'not-a-price',
              'change_pct': 1,
              'timestamp': '2026-09-07T12:00:00Z',
            },
          ],
        }),
        isEmpty,
      );
    });
  });

  test('the default display cadence is exactly 500 ms', () {
    final service = LivePriceService();
    addTearDown(service.dispose);
    expect(service.displayInterval, const Duration(milliseconds: 500));
  });

  testWidgets('the builder replaces a price without rebuilding the page',
      (tester) async {
    final source = _FakeLivePriceSource(LivePriceState(
      connection: LivePriceConnection.live,
      prices: {'BTC': _tick('BTC', 90000)},
    ));
    addTearDown(source.controller.close);

    await tester.pumpWidget(MaterialApp(
      home: LivePriceBuilder(
        source: source,
        asset: 'BTC',
        builder: (context, price, connection) => Text('${price?.priceEur}'),
      ),
    ));
    expect(find.text('90000.0'), findsOneWidget);

    source.push(LivePriceState(
      connection: LivePriceConnection.live,
      prices: {'BTC': _tick('BTC', 90001)},
    ));
    await tester.pump();
    expect(find.text('90001.0'), findsOneWidget);
  });
}
