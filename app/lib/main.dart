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
import 'screens/markets_screen.dart';
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
  String _analysisAsset = 'BTC';

  @override
  Widget build(BuildContext context) {
    final screens = [
      MarketsScreen(
        client: widget.client,
        livePrices: widget.livePrices,
        onAssetSelected: (asset) => setState(() {
          _analysisAsset = asset;
          _index = 1;
        }),
      ),
      FutureAnalysisScreen(
        client: widget.client,
        livePrices: widget.livePrices,
        initialAsset: _analysisAsset,
      ),
      ChartScreen(client: widget.client),
    ];

    return Scaffold(
      extendBody: true,
      body: IndexedStack(index: _index, children: screens),
      bottomNavigationBar: MobileBottomNav(
        selectedIndex: _index,
        onSelected: (value) => setState(() => _index = value),
        destinations: const [
          MobileNavDestination(icon: Icons.bar_chart_rounded, label: 'Marchés'),
          MobileNavDestination(icon: Icons.radar_rounded, label: 'Analyse'),
          MobileNavDestination(
              icon: Icons.candlestick_chart_outlined, label: 'Graphique'),
        ],
      ),
    );
  }
}
