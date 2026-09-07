/// Crypto Intelligence - mobile and web client.
///
/// The app is a renderer. Every threshold, verdict and edge decision is made
/// by the backend, so the phone, the web build and the research output can
/// never disagree about what the data says.
///
/// It performs analysis only and never places orders.
library;
import 'package:flutter/material.dart';

import 'api/client.dart';
import 'config.dart';
import 'screens/chart_screen.dart';
import 'screens/knowledge_screen.dart';
import 'screens/markets_screen.dart';
import 'screens/report_screen.dart';
import 'screens/research_screen.dart';
import 'screens/today_screen.dart';
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

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      home: HomeShell(client: _client),
    );
  }
}

class HomeShell extends StatefulWidget {
  final ApiClient client;

  const HomeShell({super.key, required this.client});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final screens = [
      TodayScreen(client: widget.client),
      MarketsScreen(client: widget.client),
      ChartScreen(client: widget.client),
      ReportScreen(client: widget.client),
      ResearchScreen(client: widget.client),
      KnowledgeScreen(client: widget.client),
    ];

    return Scaffold(
      extendBody: true,
      body: IndexedStack(index: _index, children: screens),
      bottomNavigationBar: MobileBottomNav(
        selectedIndex: _index,
        onSelected: (value) => setState(() => _index = value),
        destinations: const [
          MobileNavDestination(icon: Icons.home_rounded, label: 'Aujourd’hui'),
          MobileNavDestination(icon: Icons.bar_chart_rounded, label: 'Marchés'),
          MobileNavDestination(icon: Icons.candlestick_chart_outlined, label: 'Graphique'),
          MobileNavDestination(icon: Icons.article_outlined, label: 'Rapport'),
          MobileNavDestination(icon: Icons.science_outlined, label: 'Recherche'),
          MobileNavDestination(icon: Icons.menu_book_outlined, label: 'Connaissances'),
        ],
      ),
    );
  }
}
