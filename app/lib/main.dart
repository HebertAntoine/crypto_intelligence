/// Crypto Intelligence - mobile and web client.
///
/// The app renders backend analysis and a separate direct market-price stream.
/// Every threshold, verdict and edge decision remains backend-owned, while the
/// BTC/ETH/SOL price widgets follow the app-owned public WebSocket.
///
/// It performs analysis only and never places orders.
library;

import 'package:flutter/material.dart';

import 'api/client.dart';
import 'config.dart';
import 'live_prices/live_price_service.dart';
import 'screens/chart_screen.dart';
import 'screens/future_analysis_screen.dart';
import 'theme/app_theme.dart';
import 'widgets/mobile_kit.dart';

void main() => runApp(const CryptoIntelligenceApp());

class CryptoIntelligenceApp extends StatefulWidget {
  const CryptoIntelligenceApp({super.key});

  @override
  State<CryptoIntelligenceApp> createState() => _CryptoIntelligenceAppState();
}

class _CryptoIntelligenceAppState extends State<CryptoIntelligenceApp> {
  final ApiClient _client = ApiClient();
  late final LivePriceService _livePrices;

  @override
  void initState() {
    super.initState();
    _livePrices = LivePriceService()..start();
  }

  @override
  void dispose() {
    _livePrices.dispose();
    _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      home: HomeShell(client: _client, livePrices: _livePrices),
    );
  }
}

class HomeShell extends StatefulWidget {
  final ApiClient client;
  final LivePriceSource livePrices;

  const HomeShell({
    super.key,
    required this.client,
    required this.livePrices,
  });

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  late final List<Widget?> _screens;

  @override
  void initState() {
    super.initState();
    // Only load the first asset at startup. The other analytical pages are
    // created on first visit, then kept alive by the IndexedStack so their
    // selected horizon and scroll position do not disappear between tabs.
    _screens = [_screenFor(0), null, null, null];
  }

  Widget _screenFor(int index) => switch (index) {
        0 => FutureAnalysisScreen(
            key: const ValueKey('btc-page'),
            client: widget.client,
            livePrices: widget.livePrices,
            initialAsset: 'BTC',
            lockAsset: true,
          ),
        1 => FutureAnalysisScreen(
            key: const ValueKey('eth-page'),
            client: widget.client,
            livePrices: widget.livePrices,
            initialAsset: 'ETH',
            lockAsset: true,
          ),
        2 => FutureAnalysisScreen(
            key: const ValueKey('sol-page'),
            client: widget.client,
            livePrices: widget.livePrices,
            initialAsset: 'SOL',
            lockAsset: true,
          ),
        _ => ChartScreen(
            key: const ValueKey('chart-page'),
            client: widget.client,
          ),
      };

  void _selectPage(int value) {
    if (value == _index) return;
    setState(() {
      _screens[value] ??= _screenFor(value);
      _index = value;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      body: IndexedStack(
        index: _index,
        children: _screens
            .map((screen) => screen ?? const SizedBox.shrink())
            .toList(),
      ),
      bottomNavigationBar: MobileBottomNav(
        selectedIndex: _index,
        onSelected: _selectPage,
        destinations: const [
          MobileNavDestination(
              icon: Icons.currency_bitcoin_rounded, label: 'BTC'),
          MobileNavDestination(icon: Icons.diamond_outlined, label: 'ETH'),
          MobileNavDestination(icon: Icons.blur_on_rounded, label: 'SOL'),
          MobileNavDestination(
              icon: Icons.candlestick_chart_outlined, label: 'Graphique'),
        ],
      ),
    );
  }
}
