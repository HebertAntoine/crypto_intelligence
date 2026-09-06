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
import 'screens/research_screen.dart';
import 'screens/today_screen.dart';
import 'theme/app_theme.dart';

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
      ChartScreen(client: widget.client),
      ResearchScreen(client: widget.client),
      KnowledgeScreen(client: widget.client),
    ];
    const titles = ['Aujourd’hui', 'Marchés', 'Recherche', 'Connaissances'];

    return Scaffold(
      appBar: _index == 0
          ? null
          : AppBar(
              title: Text(
                titles[_index],
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
              actions: [
                IconButton(
                  tooltip: 'État du backend',
                  icon: const Icon(Icons.info_outline, size: 20),
                  onPressed: () => _showBackendInfo(context),
                ),
              ],
            ),
      body: IndexedStack(index: _index, children: screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        backgroundColor: const Color(0xFF111A24),
        indicatorColor: const Color(0xFF213D66),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_rounded), label: 'Aujourd’hui'),
          NavigationDestination(icon: Icon(Icons.bar_chart_rounded), label: 'Marchés'),
          NavigationDestination(icon: Icon(Icons.science_outlined), label: 'Recherche'),
          NavigationDestination(icon: Icon(Icons.menu_book_outlined), label: 'Connaissances'),
        ],
      ),
    );
  }

  Future<void> _showBackendInfo(BuildContext context) async {
    Map<String, dynamic>? health;
    Object? error;
    try {
      health = await widget.client.health();
    } catch (e) {
      error = e;
    }
    if (!context.mounted) return;

    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Backend', style: TextStyle(fontSize: 15)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              AppConfig.usesSameOrigin
                  ? 'Même origine, avec snapshots intégrés en secours'
                  : AppConfig.apiBaseUrl,
              style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
            const SizedBox(height: 10),
            if (error != null)
              Text('Injoignable : $error', style: const TextStyle(fontSize: 12, color: AppColors.bad))
            else ...[
              Text('Statut : ${health?['status']}', style: const TextStyle(fontSize: 12)),
              Text('Version: ${health?['version']}', style: const TextStyle(fontSize: 12)),
              Text(
                'Mode simulation : ${health?['mock_mode']}',
                style: const TextStyle(fontSize: 12),
              ),
            ],
            const SizedBox(height: 12),
            const Text(
              AppConfig.disclaimer,
              style: TextStyle(fontSize: 11, color: AppColors.textMuted, height: 1.35),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Fermer'),
          ),
        ],
      ),
    );
  }
}
