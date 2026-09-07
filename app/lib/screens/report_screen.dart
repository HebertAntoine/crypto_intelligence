/// Le rapport quotidien: seize sections dans l'ordre de lecture.
///
/// L'ordre n'est pas cosmétique. Il va du mesuré vers l'inféré, de sorte qu'un
/// lecteur qui s'arrête tôt a lu la partie la plus fiable.
///
/// EDGE MESURÉ suit immédiatement OPPORTUNITÉ D'ENTRÉE: une configuration qui
/// paraît favorable ne peut jamais être lue sans le verdict indiquant si de
/// telles configurations ont été démontrées.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';

const _assets = ['BTC', 'ETH', 'SOL'];

/// Sections dont l'intitulé anglais du backend est traduit pour l'affichage.
const _titles = <String, String>{
  'MARKET REGIME': 'RÉGIME DE MARCHÉ',
  'STRUCTURE (multi-timeframe)': 'STRUCTURE (multi-unités)',
  '⚠ CONTRADICTION WITHIN THIS REPORT': '⚠ CONTRADICTION DANS CE RAPPORT',
  'LOCATION': 'LOCALISATION',
  'ENTRY OPPORTUNITY': "OPPORTUNITÉ D'ENTRÉE",
  'MEASURED EDGE': 'EDGE MESURÉ',
  'CROWDING': 'ENCOMBREMENT',
  'VOLATILITY': 'VOLATILITÉ',
  'LIQUIDITY': 'LIQUIDITÉ',
  'CROSS-ASSET': 'INTER-ACTIFS',
  'ETF': 'ETF',
  'MACRO': 'MACRO',
  'NETWORK FUNDAMENTALS': 'FONDAMENTAUX RÉSEAU',
  'TOP CATALYSTS': 'CATALYSEURS',
  'HISTORICAL ANALOGS': 'ANALOGUES HISTORIQUES',
  'UNCERTAINTY': 'INCERTITUDE',
  'WHAT WOULD CHANGE THE VIEW?': 'CE QUI CHANGERAIT LA LECTURE',
};

class ReportScreen extends StatefulWidget {
  final ApiClient client;

  const ReportScreen({super.key, required this.client});

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  String _asset = 'BTC';
  late Future<DailyReport> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.client.dailyReport(_asset);
  }

  void _reload() =>
      setState(() => _future = widget.client.dailyReport(_asset));

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<DailyReport>(
          future: _future,
          builder: (context, snapshot) {
            return ListView(
              padding: const EdgeInsets.fromLTRB(24, 26, 24, 24),
              children: [
                MobileHeader(
                  title: 'Rapport',
                  subtitle: 'La lecture complète du jour, section par section',
                  onInfo: () => _showInfo(context),
                ),
                const SizedBox(height: 18),
                _AssetTabs(
                  selected: _asset,
                  onSelect: (value) {
                    setState(() => _asset = value);
                    _reload();
                  },
                ),
                const SizedBox(height: 18),
                if (snapshot.connectionState == ConnectionState.waiting)
                  SizedBox(
                    height: 420,
                    child: LoadingView(what: 'le rapport $_asset'),
                  )
                else if (snapshot.hasError)
                  SizedBox(
                    height: 420,
                    child: ErrorView(error: snapshot.error!, onRetry: _reload),
                  )
                else ...[
                  _Conclusion(report: snapshot.data!),
                  const SizedBox(height: 18),
                  for (var i = 0; i < snapshot.data!.sections.length; i++) ...[
                    _SectionCard(
                      index: i + 1,
                      section: snapshot.data!.sections[i],
                    ),
                    const SizedBox(height: 14),
                  ],
                ],
              ],
            );
          },
        ),
      ),
    );
  }

  void _showInfo(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: mobilePanel,
        title: const Text("Ordre de lecture", style: TextStyle(fontSize: 16)),
        content: const Text(
          "Les sections vont du mesuré vers l'inféré. EDGE MESURÉ suit "
          "immédiatement OPPORTUNITÉ D'ENTRÉE, pour qu'une configuration "
          "favorable ne puisse jamais être lue sans savoir si ce type de "
          "configuration a été démontré.\n\n"
          "Une section sans données affiche INDISPONIBLE et sa raison, jamais "
          "un blanc: un trou silencieux se lit comme « rien à signaler », un "
          "trou explicite se lit comme « nous ne savons pas ».",
          style: TextStyle(fontSize: 13, height: 1.45, color: mobileMuted),
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

class _AssetTabs extends StatelessWidget {
  final String selected;
  final ValueChanged<String> onSelect;

  const _AssetTabs({required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (final asset in _assets)
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(right: 10),
              child: GestureDetector(
                onTap: () => onSelect(asset),
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 13),
                  decoration: BoxDecoration(
                    color: asset == selected
                        ? mobileBlue.withValues(alpha: 0.18)
                        : mobilePanel.withValues(alpha: 0.7),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: asset == selected
                          ? mobileBlue.withValues(alpha: 0.85)
                          : mobileBorder,
                      width: 1.3,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      asset,
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                        color: asset == selected ? mobileBlue : mobileMuted,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _Conclusion extends StatelessWidget {
  final DailyReport report;

  const _Conclusion({required this.report});

  @override
  Widget build(BuildContext context) {
    return GlassPanel(
      borderColor: mobileBlue.withValues(alpha: 0.7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'CONCLUSION',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.2,
                    color: mobileBlue,
                  ),
                ),
              ),
              Text(
                report.generatedAt.split('T').first,
                style: const TextStyle(fontSize: 11.5, color: mobileMuted),
              ),
            ],
          ),
          const SizedBox(height: 12),
          for (final line in report.conclusion)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                line,
                style: const TextStyle(
                  fontSize: 14.5,
                  height: 1.5,
                  color: Colors.white,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final int index;
  final ReportSection section;

  const _SectionCard({required this.index, required this.section});

  bool get _isContradiction => section.title.startsWith('⚠');

  bool get _isEdge => section.title == 'MEASURED EDGE';

  Color get _accent {
    if (_isContradiction) return AppColors.warn;
    if (_isEdge) return AppColors.measured;
    return mobileMuted;
  }

  @override
  Widget build(BuildContext context) {
    final title = _titles[section.title] ?? section.title;
    return GlassPanel(
      padding: const EdgeInsets.all(18),
      borderColor: _isContradiction
          ? AppColors.warn.withValues(alpha: 0.65)
          : mobileBorder,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 26,
                child: Text(
                  '$index',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    color: mobileMuted,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.9,
                    color: _accent,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (!section.available)
            Padding(
              padding: const EdgeInsets.only(left: 26),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const MobilePill(
                    label: 'INDISPONIBLE',
                    color: mobileMuted,
                    dense: true,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    section.reason,
                    style: const TextStyle(
                      fontSize: 12,
                      color: mobileMuted,
                      height: 1.4,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ],
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.only(left: 26),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final line in section.lines)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 5),
                      child: Text(
                        line,
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.42,
                          color: _isContradiction
                              ? Colors.white
                              : const Color(0xFFDCE7F5),
                        ),
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
