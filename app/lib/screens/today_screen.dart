/// Ecran "Aujourd’hui".
///
/// Le backend reste la source de verite pour les verdicts; cette page met ces
/// donnees dans une interface mobile proche de la maquette fournie.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/freshness.dart';
import '../diagnostics/entry_verdict.dart';
import '../diagnostics/today_diagnostics.dart';
import '../api/models.dart';
import '../live_prices/live_price_service.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/live_price_builder.dart';
import '../api/today_page.dart';
import '../widgets/mobile_kit.dart';
import '../widgets/today_blocks.dart';

class TodayScreen extends StatefulWidget {
  final ApiClient client;
  final LivePriceSource? livePrices;

  const TodayScreen({super.key, required this.client, this.livePrices});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> with WidgetsBindingObserver {
  late Future<List<TodayRead>> _future;
  Timer? _refreshTimer;
  DateTime _lastFetch = DateTime.fromMillisecondsSinceEpoch(0);

  static const _assets = ['BTC', 'ETH', 'SOL'];

  /// Une carte développée à la fois. Les trois actifs développés faisaient
  /// une page de plusieurs écrans où plus rien ne se comparait; replié, chaque
  /// actif garde la réponse (direction, timing, avantage, décision, position)
  /// et range le reste derrière un geste.
  String _expanded = _assets.first;

  /// En dessous, un retour au premier plan ne relance pas d'appel: revenir
  /// dans l'app trois fois en dix secondes ne doit pas produire trois séries
  /// de requêtes.
  static const _minimumBetweenFetches = Duration(seconds: 10);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _future = _load();
    // Pas de rechargement périodique: voir la page se reconstruire toute
    // seule pendant qu'on la lit est désagréable et n'apporte rien. Le
    // rafraîchissement se déclenche à l'ouverture, au retour au premier plan,
    // au bouton Recharger et au tirage vers le bas.
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // L'analyse est refaite au retour au premier plan: rouvrir l'app doit
    // donner l'état du moment, pas celui de la dernière fois qu'on l'a
    // quittée.
    if (state == AppLifecycleState.resumed && mounted) {
      if (DateTime.now().difference(_lastFetch) >= _minimumBetweenFetches) {
        _reload();
      }
    }
  }

  Future<List<TodayRead>> _load() {
    _lastFetch = DateTime.now();
    return widget.client.todayAll(_assets);
  }

  void _reload() {
    setState(() => _future = _load());
  }

  Future<void> _refresh() async {
    final future = _load();
    setState(() => _future = future);
    try {
      await future;
    } catch (_) {
      // FutureBuilder renders the error state; RefreshIndicator only needs
      // the gesture to complete.
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _refreshTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return _TodayVisualFrame(
      child: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<TodayRead>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const LoadingView(what: 'analyse du jour');
            }
            if (snapshot.hasError) {
              return ErrorView(error: snapshot.error!, onRetry: _reload);
            }

            final reads = snapshot.data ?? const [];
            if (reads.isEmpty) {
              return ErrorView(
                  error: 'Aucune analyse disponible.', onRetry: _reload);
            }
            final provenance =
                _provenanceForReads(widget.client.lastProvenance, reads);

            return MobileScrollView(
              padding: const EdgeInsets.fromLTRB(10, 26, 10, 260),
              children: [
                _TodayHeader(provenance: provenance, reads: reads),
                const SizedBox(height: 20),
                // Le bandeau d'instantané a été retiré: la provenance et
                // l'âge sont déjà portés par le sous-titre de l'en-tête et
                // par la ligne de fraîcheur de chaque actif, qui sont
                // recalculés contre l'horloge. Le répéter en tête de page
                // n'ajoutait rien et occupait la première hauteur d'écran.
                for (final read in reads) ...[
                  _MarketCard(
                    read: read,
                    provenance: provenance,
                    livePrices: widget.livePrices,
                    expanded: read.asset == _expanded,
                    onToggle: () => setState(
                      () =>
                          _expanded = read.asset == _expanded ? '' : read.asset,
                    ),
                  ),
                  // Sans encadrement, c'est l'espace qui separe les trois
                  // actifs: il doit etre plus franc qu'avec une bordure.
                  const SizedBox(height: 40),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Fond propre à la première page.
///
/// L'illustration reste fixe pendant le défilement pour conserver la montagne
/// Bitcoin comme décor général. Les voiles bleus assurent le contraste des
/// données sans masquer la lumière de l'image fournie.
class _TodayVisualFrame extends StatelessWidget {
  final Widget child;

  const _TodayVisualFrame({required this.child});

  @override
  Widget build(BuildContext context) => Stack(
        fit: StackFit.expand,
        children: [
          const ColoredBox(color: Color(0xFF020C1C)),
          Image.asset(
            'assets/visuals/today_background.png',
            key: const ValueKey('today-background'),
            fit: BoxFit.cover,
            alignment: Alignment.topCenter,
            filterQuality: FilterQuality.high,
          ),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                stops: [0, .28, .68, 1],
                colors: [
                  Color(0x16000A18),
                  Color(0x4800183B),
                  Color(0xB8041026),
                  Color(0xF0020B19),
                ],
              ),
            ),
          ),
          SafeArea(
            bottom: false,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 900),
                child: child,
              ),
            ),
          ),
        ],
      );
}

class _TodayHeader extends StatelessWidget {
  final DataProvenance provenance;

  /// Nécessaire pour distinguer prix en direct et analyse enregistrée.
  final List<TodayRead> reads;

  const _TodayHeader({required this.provenance, required this.reads});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Le titre retrecit plutot que de pousser les boutons hors de
              // l'ecran: il debordait de 14 px sur un telephone etroit.
              const FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  'Aujourd’hui',
                  maxLines: 1,
                  style: TextStyle(
                    color: AppColors.text,
                    fontSize: 40,
                    fontWeight: FontWeight.w800,
                    height: 0.98,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _subtitleForLayers(provenance, reads),
                style: const TextStyle(
                  color: Color(0xFFB6C1D2),
                  fontSize: 20,
                  height: 1.15,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        // Un seul bouton, donc plus de Wrap: à deux, le second passait à la
        // ligne faute de place et laissait un carré isolé sous la date. Le
        // rafraîchissement reste accessible par le tirage vers le bas, à
        // l'ouverture et au retour au premier plan.
        Flexible(
          child: Align(
            alignment: Alignment.centerRight,
            child: _HeaderButton(
              icon: Icons.calendar_today_rounded,
              label: _formatFrenchDate(DateTime.now()),
              onTap: () => _showDateInfo(context, provenance),
            ),
          ),
        ),
      ],
    );
  }

  void _showDateInfo(BuildContext context, DataProvenance provenance) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Données affichées'),
        content: Text(
          provenance.describe(),
          style: const TextStyle(color: AppColors.textMuted, height: 1.35),
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

class _MarketCard extends StatelessWidget {
  final TodayRead read;
  final LivePriceSource? livePrices;

  /// D'ou vient ce payload: le diagnostic ouvert au clic en a besoin.
  final DataProvenance provenance;

  /// Développée, la carte répond aux huit questions. Repliée, elle en garde
  /// les cinq premières et range le reste: trois actifs entièrement déroulés
  /// donnaient une page qu'on ne pouvait plus parcourir.
  final bool expanded;
  final VoidCallback onToggle;

  const _MarketCard({
    required this.read,
    required this.provenance,
    required this.livePrices,
    required this.expanded,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final meta = AssetVisuals.forAsset(read.asset);
    final page = read.page;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(17),
        onTap: null,
        // Sans encadrement: la bordure, le fond et les ombres prenaient de la
        // largeur pour separer trois cartes que l'espacement vertical separe
        // deja. Le contenu occupe maintenant toute la largeur disponible.
        child: Ink(
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _AssetHeader(
                read: read,
                meta: meta,
                livePrices: livePrices,
              ),
              const SizedBox(height: 14),
              _AnalysisStampLine(read: read),

              // Deux blocs qui ne portent pas le même identifiant d'analyse
              // décrivent deux instants. On le dit plutôt que de les empiler.
              if (!read.isCoherent) ...[
                const SizedBox(height: 12),
                const AnalysisMismatchBanner(),
              ],

              const SizedBox(height: 14),
              // Direction, timing, avantage: trois lectures indépendantes.
              // Quand le backend ne les envoie pas encore, l'ancienne ligne de
              // régime reste affichée plutôt que rien.
              if (page.isEmpty)
                _CompactRegimeRow(read: read)
              else
                DirectionTimingEdgeRow(
                  readings: page.readings,
                  onTap: () => _showReadingsDetail(context, page),
                ),

              const SizedBox(height: 12),
              _EntryAnswerPanel(read: read),

              if (!page.isEmpty) ...[
                const SizedBox(height: 12),
                StructuralPositionBar(
                  position: page.position,
                  onTap: () => _showPositionDetail(context, page),
                ),
                if (page.levels.available) ...[
                  const SizedBox(height: 8),
                  NearestLevelsRow(levels: page.levels),
                ],
              ],

              const SizedBox(height: 12),
              _MarketPressureSummary(
                pressure: read.pressure,
                breakdown: page.isEmpty ? null : page.pressure,
              ),

              if (!page.isEmpty) ...[
                if (expanded) ...[
                  if (page.immediateContext.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    ImmediateContextBlock(items: page.immediateContext),
                  ],
                  const SizedBox(height: 12),
                  PositioningEtfBlock(
                    positioning: page.positioning,
                    etf: page.etf,
                  ),
                  if (page.catalysts.items.isNotEmpty ||
                      page.catalysts.alert != null) ...[
                    const SizedBox(height: 12),
                    CatalystsBlock(catalysts: page.catalysts),
                  ],
                  if (!page.changeConditions.isEmpty) ...[
                    const SizedBox(height: 12),
                    ChangeConditionsBlock(conditions: page.changeConditions),
                  ],
                  if (page.timeframes.rows.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    TimeframeStrip(
                      summary: page.timeframes,
                      contradictions: page.contradictions,
                      onTap: () => _showTimeframeDetail(context, page),
                    ),
                  ],
                  const SizedBox(height: 12),
                  DataCoverageBlock(
                    coverage: page.coverage,
                    onTap: () => _showCoverageDetail(context, page),
                  ),
                  if (page.lastChange.available) ...[
                    const SizedBox(height: 12),
                    LastChangeLine(change: page.lastChange),
                  ],
                ],
                const SizedBox(height: 10),
                _ExpandToggle(expanded: expanded, onTap: onToggle),
              ],
            ],
          ),
        ),
      ),
    );
  }

  // Kept as an internal diagnostic renderer for targeted debugging; the
  // production card no longer opens it because its public detail is concise.
  // ignore: unused_element
  void _showDetails(
    BuildContext context,
    TodayRead read,
    AssetVisuals meta,
    DataProvenance provenance,
  ) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: mobilePanel,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.70,
        minChildSize: 0.35,
        maxChildSize: 0.92,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(22, 18, 22, 32),
          children: [
            Row(
              children: [
                CryptoLogo(asset: read.asset, size: 82),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    '${read.asset} · ${meta.name}',
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 24,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            // Le diagnostic passe avant les valeurs: savoir d'ou elles
            // viennent et si elles tiennent conditionne la lecture de tout
            // ce qui suit.
            _DiagnosticsPanel(
              diagnostics: buildDiagnostics(read, provenance),
            ),
            const SizedBox(height: 18),
            LivePriceBuilder(
              source: livePrices,
              asset: read.asset,
              builder: (context, live, connection) => Column(
                children: [
                  _TodaySheetLine(
                    label: 'Prix',
                    value: _marketPriceLabel(read.marketData, live),
                  ),
                  _TodaySheetLine(
                    label: '24h',
                    value: _marketChangeLabel(read.marketData, live),
                  ),
                  _TodaySheetLine(
                    label: 'Fraîcheur',
                    value: live == null
                        ? _marketFreshnessLabel(read.marketData)
                        : _liveFreshnessLabel(live, connection),
                  ),
                  _TodaySheetLine(
                    label: 'Source du prix',
                    value: live == null
                        ? _marketProvidersLabel(read.marketData)
                        : 'Kraken · WebSocket direct de l’app',
                  ),
                ],
              ),
            ),
            _TodaySheetLine(
              label: 'Direction',
              value:
                  '${_directionLabel(read.summary.marketDirection)} (${read.summary.directionConfidence} %)',
            ),
            _TodaySheetLine(
              label: 'Source',
              value: read.directionSource.isEmpty
                  ? 'Non précisée'
                  : 'Régime de prix simplifié: tendance, position EMA, '
                      'momentum, ADX. Ce n’est pas le moteur de régime '
                      'multi-domaines complet, qui exige un cycle de pipeline.',
            ),
            _TodaySheetLine(
              label: 'Avantage statistique',
              value:
                  '${_edgeLabel(read.edgeState)} · ${read.admittedCount} validé, ${read.rejectedCount} rejeté',
            ),
            _TodaySheetLine(
                label: 'Encombrement du marché',
                value: _crowdingLabel(read.crowdingLevel)),
            _TodaySheetLine(label: 'Funding', value: _fundingLabel(read)),
            _TodaySheetLine(
              label: 'Volatilité',
              value: _volatilityLabel(read.volatilityRegime),
            ),
            _TodaySheetLine(
              label: 'Incertitude',
              value:
                  '${_uncertaintyLabel(read.uncertaintyLevel)} ${read.uncertaintyScore.toStringAsFixed(0)}/100',
            ),
            if (read.families.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Text(
                'État des familles',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              // Chaque famille a sa propre cadence: un prix de 6 min est
              // vieux, un flux ETF de 6 h est normal. Le libellé porte la
              // fraîcheur et l'âge, jamais un « Disponible » qui masquerait
              // une donnée présente mais trop ancienne pour servir.
              for (final entry in read.families.entries)
                _TodaySheetLine(
                  label: familyLabel(entry.key),
                  value: _familySummary(entry.value),
                ),
            ],
            if (read.uncertaintyDrivers.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Text(
                'Facteurs principaux',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              for (final driver in read.uncertaintyDrivers)
                Text(
                  '• ${_driverFr(driver.driver)}: ${_driverDetailFr(driver.detail)}',
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 15,
                    height: 1.34,
                  ),
                ),
            ],
            if (read.summary.caveats.isNotEmpty) ...[
              const SizedBox(height: 14),
              const Text(
                'Points de vigilance',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              for (final caveat in read.summary.caveats)
                Text(
                  '• ${_caveatFr(caveat)}',
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 15,
                    height: 1.34,
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Ce que l'app a recu pour cet actif, et si c'est exploitable.
///
/// Deroule par defaut plutot que replie: quand un chiffre parait faux, la
/// premiere question est d'ou il vient, et il ne faut pas avoir a la chercher.
class _DiagnosticsPanel extends StatelessWidget {
  final TodayDiagnostics diagnostics;

  const _DiagnosticsPanel({required this.diagnostics});

  static Color _colour(CheckStatus status) => switch (status) {
        CheckStatus.ok => AppColors.measured,
        CheckStatus.warning => AppColors.warn,
        CheckStatus.failed => AppColors.bad,
        CheckStatus.unknown => AppColors.textMuted,
      };

  static IconData _icon(CheckStatus status) => switch (status) {
        CheckStatus.ok => Icons.check_circle_outline,
        CheckStatus.warning => Icons.error_outline,
        CheckStatus.failed => Icons.cancel_outlined,
        CheckStatus.unknown => Icons.help_outline,
      };

  @override
  Widget build(BuildContext context) {
    final tone = _colour(diagnostics.overall);

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: tone.withValues(alpha: 0.45), width: 1.2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(_icon(diagnostics.overall), color: tone, size: 26),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'DONNÉES REÇUES · ${diagnostics.asset}',
                      style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.3,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      diagnostics.summary,
                      style: TextStyle(color: tone, fontSize: 15),
                    ),
                  ],
                ),
              ),
            ],
          ),
          for (final section in diagnostics.sections) ...[
            const SizedBox(height: 16),
            Row(
              children: [
                Text(
                  section.title.toUpperCase(),
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.6,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Container(
                    height: 1,
                    color: AppColors.border.withValues(alpha: 0.6),
                  ),
                ),
              ],
            ),
            for (final check in section.checks)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Icon(
                        _icon(check.status),
                        color: _colour(check.status),
                        size: 18,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                child: Text(
                                  check.name,
                                  style: const TextStyle(
                                    color: AppColors.text,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Text(
                                check.status.label,
                                style: TextStyle(
                                  color: _colour(check.status),
                                  fontSize: 13,
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 2),
                          // La valeur brute telle qu'elle est arrivee, pas une
                          // reformulation: c'est elle qu'on veut pouvoir
                          // comparer a la source.
                          SelectableText(
                            check.received,
                            style: const TextStyle(
                              color: AppColors.text,
                              fontSize: 15,
                              fontFamily: 'monospace',
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            check.detail,
                            style: const TextStyle(
                              color: mobileMuted,
                              fontSize: 14,
                              height: 1.3,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _TodaySheetLine extends StatelessWidget {
  final String label;
  final String value;

  const _TodaySheetLine({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 112,
            child: Text(
              label,
              style: const TextStyle(color: mobileMuted, fontSize: 15),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                color: AppColors.text,
                fontSize: 15,
                height: 1.3,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AssetHeader extends StatelessWidget {
  final TodayRead read;
  final AssetVisuals meta;
  final LivePriceSource? livePrices;

  const _AssetHeader({
    required this.read,
    required this.meta,
    required this.livePrices,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        CryptoLogo(asset: read.asset, size: 82),
        const SizedBox(width: 22),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                read.asset,
                style: const TextStyle(
                  color: AppColors.text,
                  fontSize: 31,
                  fontWeight: FontWeight.w800,
                  height: 1,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                meta.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: Color(0xFFB6C1D2), fontSize: 24, height: 1),
              ),
            ],
          ),
        ),
        // Flexible, pas Column nue: le bloc de droite contient un prix, une
        // pastille et une ligne de fraicheur dont la largeur depend des
        // donnees. Fige, il debordait de 211 px des que la largeur de
        // reference du design a ete reduite pour agrandir le texte.
        Flexible(
          child: LivePriceBuilder(
            source: livePrices,
            asset: read.asset,
            builder: (context, live, connection) => Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerRight,
                  child: Text(
                    _marketPriceLabel(read.marketData, live),
                    maxLines: 1,
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                _ChangePill(
                  label: _marketChangeLabel(read.marketData, live),
                  positive: (live?.change24hPct ??
                          read.marketData?.change24hPct ??
                          0) >=
                      0,
                  // A Kraken tick is current market data. The HTTP fallback
                  // keeps its stricter timestamp-derived freshness policy.
                  available: live != null ||
                      (read.marketData?.change24hPct != null &&
                          (read.marketData?.derived().isTrustworthy ?? false)),
                ),
                const SizedBox(height: 6),
                Text(
                  live == null
                      ? _marketFreshnessShort(read.marketData)
                      : _liveFreshnessShort(connection),
                  textAlign: TextAlign.right,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: mobileMuted, fontSize: 12),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// La surface n'expose que le régime et l'incertitude. Les métriques qui le
/// composent restent dans les facteurs sourcés de l'explication.
class _CompactRegimeRow extends StatelessWidget {
  final TodayRead read;

  const _CompactRegimeRow({required this.read});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
      decoration: BoxDecoration(
        color: const Color(0xFF101927).withValues(alpha: .55),
        borderRadius: BorderRadius.circular(13),
        border: Border.all(color: const Color(0xFF23364C)),
      ),
      child: Row(
        children: [
          const Text(
            'RÉGIME',
            style: TextStyle(
              color: mobileMuted,
              fontSize: 14,
              fontWeight: FontWeight.w800,
              letterSpacing: .5,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _directionLabel(read.summary.marketDirection),
              textAlign: TextAlign.right,
              style: TextStyle(
                color: _directionColor(read.summary.marketDirection),
                fontSize: 17,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Text(
            'Incertitude ${read.uncertaintyScore.toStringAsFixed(0)}/100',
            style: const TextStyle(color: mobileMuted, fontSize: 14),
          ),
        ],
      ),
    );
  }
}

/// La reponse directe: peut-on acheter, oui ou non.
///
/// Elle est mise en evidence parce que c'est la question posee, et que la
/// reponse habituelle - non - se lisait auparavant comme un « indetermine »
/// qui n'engageait a rien. Un non teste est une information; un haussement
/// d'epaules n'en est pas une.
/// « Analyse calculée à 21:46 », et l'avertissement quand le prix a bougé.
///
/// Sans cette ligne, une décision présentée au présent semble recalculée à
/// chaque tick du prix, ce qu'elle n'est pas.
class _AnalysisStampLine extends StatelessWidget {
  final TodayRead read;

  const _AnalysisStampLine({required this.read});

  @override
  Widget build(BuildContext context) {
    final stamp = read.analysis;
    final moment = stamp.computedAtUtc?.toLocal();
    final drifted = stamp.staleForCurrentPrice;
    if (moment == null && !drifted) return const SizedBox.shrink();

    final texte = drifted
        ? 'Analyse calculée à ${_clockLabel(moment ?? DateTime.now())} sur un '
            'prix de ${_analysisPriceLabel(stamp.priceAtAnalysis)}. Le prix a '
            'bougé de ${_driftLabel(stamp.driftPct)} depuis : actualisation '
            'recommandée.'
        : 'Analyse calculée à ${_clockLabel(moment!)}';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          drifted ? Icons.update_rounded : Icons.schedule_rounded,
          size: 17,
          color: drifted ? AppColors.warn : mobileMuted,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            texte,
            style: TextStyle(
              color: drifted ? AppColors.warn : mobileMuted,
              fontSize: 14.5,
              height: 1.3,
            ),
          ),
        ),
      ],
    );
  }
}

String _analysisPriceLabel(double? value) =>
    value == null ? '—' : _numberFr(value, digits: 0);

String _driftLabel(double? value) => value == null
    ? '—'
    : '${value >= 0 ? '+' : ''}${value.toStringAsFixed(2)} %';

class _EntryAnswerPanel extends StatelessWidget {
  final TodayRead read;

  const _EntryAnswerPanel({required this.read});

  @override
  Widget build(BuildContext context) {
    final opportunity = read.opportunity;
    final tone = _opportunityColour(opportunity.state);
    final icon = _opportunityIcon(opportunity.state);
    final visual = _opportunityVisual(opportunity);
    final decisionSentence = read.page.decision.sentence.trim();
    final explanation = decisionSentence.isNotEmpty
        ? decisionSentence
        : opportunity.summary.isEmpty
            ? 'Les données ne permettent pas encore une explication structurée.'
            : opportunity.summary;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: () => _showOpportunityDetails(context, read, tone),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(22),
          child: Stack(
            children: [
              Positioned.fill(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 420),
                  child: Image.asset(
                    visual.asset,
                    key: ValueKey(visual.asset),
                    fit: BoxFit.cover,
                    alignment: Alignment.centerRight,
                    filterQuality: FilterQuality.high,
                  ),
                ),
              ),
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      stops: const [0, .58, 1],
                      colors: [
                        const Color(0xFF061121).withValues(alpha: .96),
                        const Color(0xFF071426).withValues(alpha: .82),
                        visual.overlay.withValues(alpha: .24),
                      ],
                    ),
                  ),
                ),
              ),
              Container(
                constraints: const BoxConstraints(minHeight: 225),
                padding: const EdgeInsets.fromLTRB(20, 20, 18, 18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _TodayIconTile(icon: icon, tone: visual.accent),
                        const SizedBox(width: 13),
                        const Expanded(
                          child: Text(
                            'EST-CE UNE BONNE OPPORTUNITÉ\nD’ACHAT MAINTENANT ?',
                            style: TextStyle(
                              color: Color(0xFFD8E8FF),
                              fontSize: 14,
                              height: 1.32,
                              fontWeight: FontWeight.w800,
                              letterSpacing: .75,
                            ),
                          ),
                        ),
                        Icon(Icons.chevron_right_rounded,
                            color: visual.accent, size: 28),
                      ],
                    ),
                    const SizedBox(height: 9),
                    Text(
                      _opportunityLabel(opportunity.state),
                      style: TextStyle(
                        color: visual.accent,
                        fontSize: 31,
                        fontWeight: FontWeight.w900,
                        height: 1.02,
                        shadows: [
                          Shadow(
                            color: visual.glow.withValues(alpha: .55),
                            blurRadius: 14,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 335),
                      child: Text(
                        explanation,
                        maxLines: 4,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Color(0xFFF2F7FF),
                          fontSize: 15.5,
                          height: 1.35,
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    _TodayOutlineAction(
                      label: 'Voir pourquoi',
                      tone: visual.accent,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Le détail: deux lignes de résumé, puis les points qui pèsent, chacun
  /// avec son sens. Un point manquant est montré comme manquant - ne pas
  /// savoir est aussi une raison de ne pas agir.
  // Compatibility renderer for older snapshot tests.
  // ignore: unused_element
  void _showJustification(
    BuildContext context,
    TodayRead read,
    EntryVerdict verdict,
    Color tone,
  ) {
    final points = verdictPoints(read);
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: mobilePanel,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.75,
        minChildSize: 0.4,
        maxChildSize: 0.95,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 32),
          children: [
            Text(
              verdictQuestion(read),
              style: const TextStyle(
                color: Color(0xFFB6C1D2),
                fontSize: 15,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.4,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              verdict.headline,
              style: TextStyle(
                color: tone,
                fontSize: 32,
                fontWeight: FontWeight.w800,
                height: 1.05,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              verdict.reason,
              style: const TextStyle(
                color: AppColors.text,
                fontSize: 17,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 22),
            const Text(
              'CE QUI PÈSE',
              style: TextStyle(
                color: Color(0xFFB6C1D2),
                fontSize: 14,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.6,
              ),
            ),
            const SizedBox(height: 10),
            for (final point in points)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Icon(
                        _pointIcon(point.sign),
                        color: _pointColour(point.sign),
                        size: 19,
                      ),
                    ),
                    const SizedBox(width: 11),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            point.title,
                            style: const TextStyle(
                              color: AppColors.text,
                              fontSize: 16.5,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          if (point.detail.isNotEmpty) ...[
                            const SizedBox(height: 2),
                            Text(
                              point.detail,
                              style: const TextStyle(
                                color: mobileMuted,
                                fontSize: 15,
                                height: 1.32,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            if (read.opportunity.whatWouldImprove.isNotEmpty ||
                read.opportunity.whatWouldDeteriorate.isNotEmpty) ...[
              const SizedBox(height: 18),
              const Text(
                'QU’EST-CE QUI FERAIT CHANGER CETTE LECTURE ?',
                style: TextStyle(
                  color: Color(0xFFB6C1D2),
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.6,
                ),
              ),
              const SizedBox(height: 10),
              for (final condition in read.opportunity.whatWouldImprove)
                _ChangeLine(
                  text: condition,
                  colour: AppColors.measured,
                  icon: Icons.trending_up_rounded,
                ),
              for (final condition in read.opportunity.whatWouldDeteriorate)
                _ChangeLine(
                  text: condition,
                  colour: AppColors.bad,
                  icon: Icons.trending_down_rounded,
                ),
            ],
            if (read.opportunity.whatWouldChangeStructure.isNotEmpty) ...[
              const SizedBox(height: 18),
              const Text(
                'CE QUI CHANGERAIT LA STRUCTURE',
                style: TextStyle(
                  color: Color(0xFFB6C1D2),
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.6,
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'Sans signe : une cassure peut invalider la structure sans '
                'dégrader le marché.',
                style: TextStyle(color: mobileMuted, fontSize: 13.5),
              ),
              const SizedBox(height: 8),
              for (final condition in read.opportunity.whatWouldChangeStructure)
                _ChangeLine(
                  text: condition,
                  colour: AppColors.accent,
                  icon: Icons.swap_horiz_rounded,
                ),
            ],
            if (read.opportunity.guardRails.isNotEmpty) ...[
              const SizedBox(height: 18),
              const Text(
                'CE QUI PLAFONNE LA LECTURE',
                style: TextStyle(
                  color: Color(0xFFB6C1D2),
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.6,
                ),
              ),
              const SizedBox(height: 8),
              for (final rail in read.opportunity.guardRails)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(
                    '• $rail',
                    style: const TextStyle(
                        color: mobileMuted, fontSize: 15, height: 1.32),
                  ),
                ),
            ],
            const SizedBox(height: 16),
            Text(
              read.opportunity.disclaimer.isEmpty
                  ? 'Cette page n’est pas un conseil et ne passe jamais '
                      'd’ordre. Elle dit ce qui a été mesuré, et ce qui ne l’a '
                      'pas été.'
                  : read.opportunity.disclaimer,
              style: const TextStyle(
                  color: mobileMuted, fontSize: 14, height: 1.35),
            ),
          ],
        ),
      ),
    );
  }

  static IconData _pointIcon(PointSign sign) => switch (sign) {
        PointSign.favourable => Icons.add_circle_outline,
        PointSign.against => Icons.remove_circle_outline,
        PointSign.neutral => Icons.remove,
        PointSign.missing => Icons.help_outline,
      };

  static Color _pointColour(PointSign sign) => switch (sign) {
        PointSign.favourable => AppColors.measured,
        PointSign.against => AppColors.bad,
        PointSign.neutral => AppColors.accent,
        PointSign.missing => AppColors.textMuted,
      };
}

String _opportunityLabel(String state) => switch (state.toUpperCase()) {
      'VERY_FAVORABLE' || 'STRONG_OPPORTUNITY' => 'OPPORTUNITÉ FORTE',
      'FAVORABLE' || 'OPPORTUNITY' => 'OPPORTUNITÉ',
      'WATCH' => 'À SURVEILLER',
      'WAIT' => 'ATTENDRE',
      'UNFAVORABLE' => 'DÉFAVORABLE',
      _ => 'DONNÉES INSUFFISANTES',
    };

class _OpportunityVisual {
  final String asset;
  final Color accent;
  final Color glow;
  final Color overlay;

  const _OpportunityVisual({
    required this.asset,
    required this.accent,
    required this.glow,
    required this.overlay,
  });
}

/// Association déterministe entre la décision du backend et l'illustration.
///
/// L'écran ne recalcule jamais le verdict. La seule nuance locale concerne
/// WAIT: la falaise orange illustre un risque déjà mesuré; le sablier jaune
/// illustre une temporisation sans signal franchement défavorable.
_OpportunityVisual _opportunityVisual(BuyOpportunity opportunity) {
  final state = opportunity.state.toUpperCase();
  if (state == 'VERY_FAVORABLE' || state == 'STRONG_OPPORTUNITY') {
    return const _OpportunityVisual(
      asset: 'assets/visuals/opportunity_very_favorable.png',
      accent: Color(0xFF40FFA6),
      glow: Color(0xFF16E98A),
      overlay: Color(0xFF08794F),
    );
  }
  if (state == 'FAVORABLE' || state == 'OPPORTUNITY') {
    return const _OpportunityVisual(
      asset: 'assets/visuals/opportunity_favorable.png',
      accent: Color(0xFF66F38E),
      glow: Color(0xFF14D86E),
      overlay: Color(0xFF087546),
    );
  }
  if (state == 'WATCH') {
    return const _OpportunityVisual(
      asset: 'assets/visuals/opportunity_insufficient.png',
      accent: Color(0xFF72C8FF),
      glow: Color(0xFF168EFF),
      overlay: Color(0xFF0759A5),
    );
  }
  if (state == 'WAIT' && opportunity.negatives.isNotEmpty) {
    return const _OpportunityVisual(
      asset: 'assets/visuals/opportunity_risk.png',
      accent: Color(0xFFFFA24B),
      glow: Color(0xFFFF6A16),
      overlay: Color(0xFFA53B07),
    );
  }
  if (state == 'WAIT') {
    return const _OpportunityVisual(
      asset: 'assets/visuals/opportunity_wait.png',
      accent: Color(0xFFFFD35C),
      glow: Color(0xFFFFB72E),
      overlay: Color(0xFF8F6512),
    );
  }
  if (state == 'UNFAVORABLE') {
    return const _OpportunityVisual(
      asset: 'assets/visuals/opportunity_unfavorable.png',
      accent: Color(0xFFFF6472),
      glow: Color(0xFFFF2E43),
      overlay: Color(0xFF8E0D22),
    );
  }
  return const _OpportunityVisual(
    asset: 'assets/visuals/opportunity_insufficient.png',
    accent: Color(0xFF72C8FF),
    glow: Color(0xFF168EFF),
    overlay: Color(0xFF0759A5),
  );
}

class _TodayIconTile extends StatelessWidget {
  final IconData icon;
  final Color tone;

  const _TodayIconTile({required this.icon, required this.tone});

  @override
  Widget build(BuildContext context) => Container(
        width: 47,
        height: 47,
        decoration: BoxDecoration(
          color: tone.withValues(alpha: .13),
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: tone.withValues(alpha: .62)),
          boxShadow: [
            BoxShadow(color: tone.withValues(alpha: .18), blurRadius: 16),
          ],
        ),
        child: Icon(icon, color: tone, size: 27),
      );
}

class _TodayOutlineAction extends StatelessWidget {
  final String label;
  final Color tone;

  const _TodayOutlineAction({required this.label, required this.tone});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 9),
        decoration: BoxDecoration(
          color: const Color(0xFF071426).withValues(alpha: .68),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: tone, width: 1.2),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                color: tone,
                fontSize: 15,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(width: 5),
            Icon(Icons.chevron_right_rounded, color: tone, size: 20),
          ],
        ),
      );
}

Color _opportunityColour(String state) => switch (state.toUpperCase()) {
      'VERY_FAVORABLE' ||
      'FAVORABLE' ||
      'STRONG_OPPORTUNITY' ||
      'OPPORTUNITY' =>
        AppColors.measured,
      'WATCH' || 'WAIT' => AppColors.warn,
      'UNFAVORABLE' => AppColors.bad,
      _ => AppColors.textMuted,
    };

IconData _opportunityIcon(String state) => switch (state.toUpperCase()) {
      'VERY_FAVORABLE' ||
      'FAVORABLE' ||
      'STRONG_OPPORTUNITY' ||
      'OPPORTUNITY' =>
        Icons.check_circle_outline,
      'WATCH' => Icons.visibility_outlined,
      'WAIT' => Icons.schedule_rounded,
      'UNFAVORABLE' => Icons.do_not_disturb_on_outlined,
      _ => Icons.help_outline,
    };

void _showOpportunityDetails(
  BuildContext context,
  TodayRead read,
  Color tone,
) {
  final opportunity = read.opportunity;
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: mobilePanel,
    builder: (context) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: .82,
      minChildSize: .45,
      maxChildSize: .96,
      builder: (context, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(22, 20, 22, 36),
        children: [
          Text(
            'POURQUOI ${_opportunityLabel(opportunity.state)} ?',
            style: TextStyle(
              color: tone,
              fontSize: 28,
              fontWeight: FontWeight.w800,
              height: 1.05,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            opportunity.summary.isEmpty
                ? 'Les données majeures ne permettent pas une explication fiable.'
                : opportunity.summary,
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 17,
              height: 1.4,
            ),
          ),
          _FactorGroup(
            title: 'CE QUI AIDE',
            factors: opportunity.positives,
            icon: Icons.add_circle_outline,
            tone: AppColors.measured,
          ),
          _FactorGroup(
            title: 'CE QUI FAIT ATTENDRE',
            factors: opportunity.waits,
            icon: Icons.schedule_rounded,
            tone: AppColors.warn,
          ),
          _FactorGroup(
            title: 'CE QUI PÈSE NÉGATIVEMENT',
            factors: opportunity.negatives,
            icon: Icons.remove_circle_outline,
            tone: AppColors.bad,
          ),
          _FactorGroup(
            title: 'CE QUI MANQUE',
            factors: opportunity.missing,
            icon: Icons.help_outline,
            tone: AppColors.textMuted,
          ),
          _ConditionsBlock(
            improve: opportunity.whatWouldImprove,
            deteriorate: opportunity.whatWouldDeteriorate,
          ),
        ],
      ),
    ),
  );
}

class _FactorGroup extends StatelessWidget {
  final String title;
  final List<OpportunityFactor> factors;
  final IconData icon;
  final Color tone;

  const _FactorGroup({
    required this.title,
    required this.factors,
    required this.icon,
    required this.tone,
  });

  @override
  Widget build(BuildContext context) {
    if (factors.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              color: tone,
              fontSize: 14,
              fontWeight: FontWeight.w800,
              letterSpacing: .55,
            ),
          ),
          const SizedBox(height: 10),
          for (final factor in factors.take(5))
            Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Icon(icon, color: tone, size: 19),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          factor.title,
                          style: const TextStyle(
                            color: AppColors.text,
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        if (factor.explanation.isNotEmpty) ...[
                          const SizedBox(height: 3),
                          Text(
                            factor.explanation,
                            style: const TextStyle(
                              color: mobileMuted,
                              fontSize: 14,
                              height: 1.32,
                            ),
                          ),
                        ],
                        const SizedBox(height: 4),
                        Text(
                          _factorSourceLine(factor),
                          style: const TextStyle(
                            color: Color(0xFF7F90A7),
                            fontSize: 12.5,
                          ),
                        ),
                      ],
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

String _factorSourceLine(OpportunityFactor factor) {
  final parts = <String>[
    factor.source.isEmpty ? 'Source non précisée' : factor.source,
    if (factor.timeframe.isNotEmpty) factor.timeframe,
    _factorFreshnessLabel(factor.freshness),
    if (factor.asOf != null && factor.asOf!.isNotEmpty)
      _dateTimeLabel(factor.asOf!),
  ];
  return parts.join(' · ');
}

String _factorFreshnessLabel(String raw) => switch (raw.toUpperCase()) {
      'LIVE' => 'temps réel',
      'RECENT' || 'MIN_15' || 'HOUR_1' || 'TODAY' => 'récent',
      'DELAYED' => 'retardé',
      'STALE' => 'périmé',
      _ => 'indisponible',
    };

class _ConditionsBlock extends StatelessWidget {
  final List<String> improve;
  final List<String> deteriorate;

  const _ConditionsBlock({required this.improve, required this.deteriorate});

  @override
  Widget build(BuildContext context) {
    if (improve.isEmpty && deteriorate.isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(top: 22),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF101927),
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: const Color(0xFF23364C)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (improve.isNotEmpty) ...[
              const Text('CE QUI AMÉLIORERAIT LA LECTURE',
                  style: TextStyle(
                    color: AppColors.measured,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  )),
              const SizedBox(height: 7),
              for (final condition in improve.take(4))
                Text('• $condition',
                    style: const TextStyle(
                        color: AppColors.text, fontSize: 14, height: 1.35)),
            ],
            if (improve.isNotEmpty && deteriorate.isNotEmpty)
              const SizedBox(height: 16),
            if (deteriorate.isNotEmpty) ...[
              const Text('CE QUI DÉGRADERAIT LA LECTURE',
                  style: TextStyle(
                    color: AppColors.bad,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  )),
              const SizedBox(height: 7),
              for (final condition in deteriorate.take(4))
                Text('• $condition',
                    style: const TextStyle(
                        color: AppColors.text, fontSize: 14, height: 1.35)),
            ],
          ],
        ),
      ),
    );
  }
}

class _MarketPressureSummary extends StatelessWidget {
  final MarketPressure pressure;

  /// La décomposition par famille, quand le backend l'envoie. Null sur un
  /// backend plus ancien: la feuille retombe alors sur la liste des sources.
  final PressureBreakdown? breakdown;

  const _MarketPressureSummary({required this.pressure, this.breakdown});

  @override
  Widget build(BuildContext context) {
    final balance = pressure.balance;
    final tone = _PressurePanel._balanceColour(balance);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(22),
        onTap: () => breakdown == null
            ? _showPressureDetails(context, pressure)
            : _showPressureBreakdown(context, breakdown!),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(22),
          child: Stack(
            children: [
              Positioned.fill(
                child: Image.asset(
                  'assets/visuals/market_pressure.png',
                  key: const ValueKey('market-pressure-background'),
                  fit: BoxFit.cover,
                  alignment: Alignment.bottomCenter,
                  filterQuality: FilterQuality.high,
                ),
              ),
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      stops: const [0, .58, 1],
                      colors: [
                        const Color(0xFF061326).withValues(alpha: .97),
                        const Color(0xFF06172D).withValues(alpha: .84),
                        const Color(0xFF06172D).withValues(alpha: .30),
                      ],
                    ),
                  ),
                ),
              ),
              Container(
                constraints: const BoxConstraints(minHeight: 196),
                padding: const EdgeInsets.fromLTRB(18, 17, 18, 16),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(22),
                  border: Border.all(
                    color: const Color(0xFF48BFFF).withValues(alpha: .86),
                    width: 1.35,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF25B7FF).withValues(alpha: .22),
                      blurRadius: 26,
                      spreadRadius: -8,
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const _TodayIconTile(
                          icon: Icons.groups_2_outlined,
                          tone: Color(0xFF8BCBFF),
                        ),
                        const SizedBox(width: 13),
                        const Expanded(
                          child: Text(
                            'QUI ACHÈTE, QUI VEND ?',
                            style: TextStyle(
                              color: Color(0xFFD8E8FF),
                              fontSize: 14,
                              fontWeight: FontWeight.w800,
                              letterSpacing: .65,
                            ),
                          ),
                        ),
                        Text(
                          pressure.label,
                          style: TextStyle(
                            color: tone,
                            fontSize: 16,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(width: 3),
                        const Icon(Icons.chevron_right_rounded,
                            color: Color(0xFFAEDAFF), size: 26),
                      ],
                    ),
                    if (balance != null) ...[
                      const SizedBox(height: 16),
                      _PressureBar(balance: balance),
                    ],
                    const SizedBox(height: 11),
                    ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 330),
                        child: Text(
                          pressure.summary.isEmpty
                              ? '${pressure.measured} source(s) mesurée(s).'
                              : pressure.summary,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Color(0xFFEAF4FF),
                            fontSize: 14.5,
                            height: 1.3,
                          ),
                        )),
                    const SizedBox(height: 8),
                    Text(
                      breakdown != null && breakdown!.familiesLine.isNotEmpty
                          ? breakdown!.familiesLine
                          : '${pressure.measured} source(s) mesurée(s)',
                      style: const TextStyle(
                        color: Color(0xFF84C9FF),
                        fontSize: 13.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 12),
                    const _TodayOutlineAction(
                      label: 'Voir les sources',
                      tone: Color(0xFF72C8FF),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

void _showPressureDetails(BuildContext context, MarketPressure pressure) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: mobilePanel,
    builder: (context) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: .74,
      minChildSize: .4,
      maxChildSize: .94,
      builder: (context, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(22, 20, 22, 34),
        children: [
          const Text('QUI ACHÈTE, QUI VEND ?',
              style: TextStyle(color: mobileMuted, fontSize: 14)),
          const SizedBox(height: 4),
          Text(pressure.label,
              style: TextStyle(
                color: _PressurePanel._balanceColour(pressure.balance),
                fontSize: 28,
                fontWeight: FontWeight.w800,
              )),
          if (pressure.balance != null) ...[
            const SizedBox(height: 14),
            _PressureBar(balance: pressure.balance!),
          ],
          const SizedBox(height: 12),
          Text(pressure.summary,
              style: const TextStyle(
                  color: AppColors.text, fontSize: 16, height: 1.35)),
          const SizedBox(height: 22),
          for (final component in pressure.components)
            _PressureSourceRow(component: component),
          if (pressure.contradictions.isNotEmpty) ...[
            const SizedBox(height: 10),
            const Text('CONTRADICTIONS',
                style: TextStyle(
                    color: AppColors.warn,
                    fontSize: 13,
                    fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            for (final item in pressure.contradictions)
              Text('• $item',
                  style: const TextStyle(
                      color: AppColors.text, fontSize: 14, height: 1.35)),
          ],
        ],
      ),
    ),
  );
}

class _PressureSourceRow extends StatelessWidget {
  final PressureComponent component;

  const _PressureSourceRow({required this.component});

  @override
  Widget build(BuildContext context) {
    final tone = component.available
        ? _PressurePanel._scoreColour(component.score)
        : AppColors.textMuted;
    return Padding(
      padding: const EdgeInsets.only(bottom: 15),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            component.available
                ? Icons.check_circle_outline
                : Icons.help_outline,
            color: tone,
            size: 19,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(component.label,
                    style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 16,
                        fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(component.available ? component.detail : component.reason,
                    style: const TextStyle(
                        color: mobileMuted, fontSize: 14, height: 1.3)),
                const SizedBox(height: 3),
                Text(
                  '${component.source.isEmpty ? 'Source non précisée' : component.source} · '
                  '${_factorFreshnessLabel(component.freshness)}',
                  style:
                      const TextStyle(color: Color(0xFF7F90A7), fontSize: 12.5),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Qui achète, qui vend, et sur quelles sources.
///
/// La barre ne descend jamais d'une intuition: chaque composante affichée est
/// une mesure, avec sa source. Ce qui manque est écrit comme manquant plutôt
/// que compté comme neutre - ignorer n'est pas équilibrer.
/// Une condition qui ferait bouger la lecture, dans un sens ou dans l'autre.
class _ChangeLine extends StatelessWidget {
  final String text;
  final Color colour;
  final IconData icon;

  const _ChangeLine({
    required this.text,
    required this.colour,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(icon, color: colour, size: 17),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                  color: AppColors.text, fontSize: 15.5, height: 1.32),
            ),
          ),
        ],
      ),
    );
  }
}

class _PressurePanel extends StatelessWidget {
  final MarketPressure pressure;

  const _PressurePanel({required this.pressure});

  @override
  Widget build(BuildContext context) {
    final balance = pressure.balance;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF101927).withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF23364C)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'QUI ACHÈTE, QUI VEND',
                  style: TextStyle(
                    color: Color(0xFFB6C1D2),
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.4,
                  ),
                ),
              ),
              Text(
                pressure.label,
                style: TextStyle(
                  color: _balanceColour(balance),
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (balance == null)
            const Text(
              'Aucune composante mesurable: la pression du marché ne peut pas '
              'être établie.',
              style: TextStyle(color: mobileMuted, fontSize: 15),
            )
          else ...[
            _PressureBar(balance: balance),
            const SizedBox(height: 6),
            const Row(
              children: [
                Text('Vente',
                    style: TextStyle(color: AppColors.bad, fontSize: 13)),
                Spacer(),
                Text('Achat',
                    style: TextStyle(color: AppColors.measured, fontSize: 13)),
              ],
            ),
          ],
          const SizedBox(height: 14),
          for (final component in pressure.components)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Icon(
                      component.available
                          ? Icons.check_circle_outline
                          : Icons.remove_circle_outline,
                      size: 17,
                      color: component.available
                          ? _scoreColour(component.score)
                          : AppColors.textMuted,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          component.label,
                          style: const TextStyle(
                            color: AppColors.text,
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          component.available
                              ? component.detail
                              : component.reason,
                          style: const TextStyle(
                            color: mobileMuted,
                            fontSize: 14,
                            height: 1.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          if (pressure.note.isNotEmpty)
            Text(
              pressure.note,
              style: const TextStyle(
                  color: mobileMuted, fontSize: 13, height: 1.3),
            ),
        ],
      ),
    );
  }

  static Color _balanceColour(double? balance) {
    if (balance == null) return AppColors.textMuted;
    if (balance >= 58) return AppColors.measured;
    if (balance <= 42) return AppColors.bad;
    return AppColors.accent;
  }

  static Color _scoreColour(double? score) {
    if (score == null) return AppColors.textMuted;
    if (score > 15) return AppColors.measured;
    if (score < -15) return AppColors.bad;
    return AppColors.accent;
  }
}

/// La barre elle-même: rouge à gauche, verte à droite, curseur sur l'équilibre.
class _PressureBar extends StatelessWidget {
  final double balance;

  const _PressureBar({required this.balance});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final position = (balance.clamp(0, 100) / 100) * width;
        return SizedBox(
          height: 22,
          child: Stack(
            children: [
              Container(
                height: 14,
                margin: const EdgeInsets.only(top: 4),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(7),
                  gradient: LinearGradient(
                    colors: [
                      AppColors.bad.withValues(alpha: 0.75),
                      const Color(0xFF3A4A5E),
                      AppColors.measured.withValues(alpha: 0.75),
                    ],
                  ),
                ),
              ),
              Positioned(
                left: (position - 3).clamp(0.0, width - 6),
                child: Container(
                  width: 6,
                  height: 22,
                  decoration: BoxDecoration(
                    color: AppColors.text,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ignore: unused_element
class _VerdictPanel extends StatelessWidget {
  final TodayRead read;

  const _VerdictPanel({required this.read});

  @override
  Widget build(BuildContext context) {
    final freshness = read.marketData?.derived();
    final tone = _VerdictTone.of(read, freshness);

    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            tone.accent.withValues(alpha: 0.25),
            tone.backdrop.withValues(alpha: 0.84),
            const Color(0xFF122328).withValues(alpha: 0.88),
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: tone.accent, width: 1.5),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: tone.accent.withValues(alpha: 0.28),
            ),
            child: Icon(tone.icon, color: tone.bright, size: 34),
          ),
          const SizedBox(width: 22),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  tone.heading,
                  style: TextStyle(
                    color: tone.bright,
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                    height: 1.05,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _verdictBody(read, freshness: freshness),
                  style: const TextStyle(
                      color: AppColors.text, fontSize: 18, height: 1.36),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Couleur, icône et titre du bandeau, dérivés de l'état.
///
/// Le bandeau était vert en dur — dégradé, bordure, icône « trending_up » et
/// titre — quelle que soit la direction. Un marché fortement baissier
/// s'affichait donc dans un panneau vert montant. Et le vert est, dans ce
/// projet, réservé à l'edge mesuré : l'employer pour la seule direction
/// effaçait précisément la séparation que le reste du système défend.
class _VerdictTone {
  final Color accent;
  final Color bright;
  final Color backdrop;
  final IconData icon;
  final String heading;

  const _VerdictTone({
    required this.accent,
    required this.bright,
    required this.backdrop,
    required this.icon,
    required this.heading,
  });

  static _VerdictTone of(TodayRead read, DerivedFreshness? freshness) {
    // Une analyse datée n'est pas une analyse suspendue. Celle-ci a bien été
    // calculée, sur des données qui étaient valides à l'époque; ce qu'il faut
    // empêcher, c'est qu'elle se présente comme actuelle. D'où le ton
    // d'avertissement plutôt que le vert ou le rouge du régime.
    if (freshness != null && freshness.blocksAnalysis) {
      return _VerdictTone(
        accent: AppColors.warn,
        bright: AppColors.warn,
        backdrop: const Color(0xFF2A2313),
        icon: Icons.history_toggle_off,
        heading: _directionLabel(read.summary.marketDirection),
      );
    }

    final direction = read.summary.marketDirection.toUpperCase();
    final heading = _directionLabel(read.summary.marketDirection);

    if (direction.contains('BEARISH')) {
      return _VerdictTone(
        accent: AppColors.bad,
        bright: const Color(0xFFFF8A80),
        backdrop: const Color(0xFF2A1618),
        icon: Icons.trending_down_rounded,
        heading: heading,
      );
    }
    if (direction.contains('BULLISH')) {
      // Le vert du bandeau reste celui du design actuel: c'est le cas
      // haussier, celui qui était déjà affiché ainsi.
      return _VerdictTone(
        accent: AppColors.measured,
        bright: const Color(0xFF61F29E),
        backdrop: const Color(0xFF12291E),
        icon: Icons.trending_up_rounded,
        heading: heading,
      );
    }
    return _VerdictTone(
      accent: AppColors.accent,
      bright: AppColors.accent,
      backdrop: const Color(0xFF16202B),
      icon: Icons.trending_flat_rounded,
      heading: heading,
    );
  }
}

// ignore: unused_element
class _MetricGrid extends StatelessWidget {
  final TodayRead read;

  const _MetricGrid({required this.read});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 620;
        final children = [
          _MetricBox(
            icon: Icons.bar_chart_rounded,
            title: 'Direction du marché',
            pill: _directionLabel(read.summary.marketDirection),
            pillColor: _directionColor(read.summary.marketDirection),
            caption:
                'présente sur ${read.summary.directionConfidence} % des 20 derniers jours',
          ),
          _MetricBox(
            icon: Icons.track_changes_rounded,
            title: 'Avantage statistique',
            pill: _edgeLabel(read.edgeState),
            pillColor: _edgeColor(read.edgeState),
            caption:
                '${read.admittedCount} validé, ${read.rejectedCount} rejeté',
          ),
        ];

        if (compact) {
          return Column(
            children: [
              children[0],
              const SizedBox(height: 12),
              children[1],
            ],
          );
        }

        return Row(
          children: [
            Expanded(child: children[0]),
            const SizedBox(width: 14),
            Expanded(child: children[1]),
          ],
        );
      },
    );
  }
}

class _MetricBox extends StatelessWidget {
  final IconData icon;
  final String title;
  final String pill;
  final Color pillColor;
  final String caption;

  const _MetricBox({
    required this.icon,
    required this.title,
    required this.pill,
    required this.pillColor,
    required this.caption,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 128),
      padding: const EdgeInsets.fromLTRB(18, 17, 18, 15),
      decoration: BoxDecoration(
        color: const Color(0xFF111D2B).withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF273B54), width: 1.25),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppColors.text, size: 30),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style:
                        const TextStyle(color: AppColors.text, fontSize: 18)),
                const SizedBox(height: 10),
                _OutlinePill(label: pill, color: pillColor),
                const SizedBox(height: 10),
                Text(caption,
                    style: const TextStyle(
                        color: Color(0xFFB6C1D2), fontSize: 14)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ignore: unused_element
class _DetailRows extends StatelessWidget {
  final TodayRead read;

  const _DetailRows({required this.read});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _InfoRow(
          icon: Icons.groups_rounded,
          label: 'Encombrement du marché',
          value: _crowdingLabel(read.crowdingLevel),
          valuePill: true,
          valueColor: AppColors.accent,
          sideTitle: _crowdingDirectionTitle(read.crowdingDirection),
          sideBody: "L’open interest présente deux scénarios possibles",
        ),
        _InfoRow(
          icon: Icons.bar_chart_rounded,
          label: 'Positionnement',
          value: _leverageLabel(read.leverageState),
        ),
        _InfoRow(
          icon: Icons.storage_rounded,
          label: 'Funding',
          value: _fundingLabel(read),
        ),
        _InfoRow(
          icon: Icons.show_chart_rounded,
          label: 'Volatilité',
          value: _volatilityLabel(read.volatilityRegime),
        ),
        _InfoRow(
          icon: Icons.help_rounded,
          label: 'Incertitude',
          value:
              '${_uncertaintyLabel(read.uncertaintyLevel)}  ${read.uncertaintyScore.toStringAsFixed(0)}/100',
          valuePill: true,
          valueColor: _uncertaintyColor(read.uncertaintyLevel),
          // 40/100 ne dit rien à qui ne connaît pas l'échelle: 0 = tout
          // concorde, 100 = rien n'est fiable.
          sideBody: _uncertaintyReading(read.uncertaintyScore),
        ),
        _InfoRow(
          icon: Icons.check_box_rounded,
          label: 'Moment d’entrée',
          value: _timingValue(read),
        ),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final bool valuePill;
  final Color valueColor;
  final String? sideTitle;
  final String? sideBody;

  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.valuePill = false,
    this.valueColor = AppColors.text,
    this.sideTitle,
    this.sideBody,
  });

  @override
  Widget build(BuildContext context) {
    // Libelle a gauche, valeur a droite, sur une seule ligne. La version
    // precedente empilait la valeur sous le libelle des que la largeur
    // passait sous 620 px - c'est-a-dire toujours, depuis que la largeur de
    // reference du design a ete reduite pour agrandir le texte. Le bouton (i)
    // qui l'accompagnait ouvrait une boite reprenant les memes mots que la
    // ligne; le detail complet vit dans « Pourquoi cette analyse ? ».
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              SizedBox(
                width: 44,
                child: Icon(icon, color: AppColors.text, size: 26),
              ),
              Expanded(
                child: Text(
                  label,
                  style:
                      const TextStyle(color: Color(0xFFB6C1D2), fontSize: 20),
                ),
              ),
              const SizedBox(width: 12),
              Flexible(
                child: Align(
                  alignment: Alignment.centerRight,
                  child: valuePill
                      ? _OutlinePill(
                          label: value, color: valueColor, dense: true)
                      : Text(
                          value,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                            color: AppColors.text,
                            fontSize: 19,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ),
            ],
          ),
          if (sideTitle != null || sideBody != null)
            Padding(
              padding: const EdgeInsets.only(left: 44, top: 6),
              child: _SideNote(title: sideTitle, body: sideBody),
            ),
        ],
      ),
    );
  }
}

class _SideNote extends StatelessWidget {
  final String? title;
  final String? body;

  const _SideNote({this.title, this.body});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title != null)
          Text(
            title!,
            style: const TextStyle(color: AppColors.text, fontSize: 15),
          ),
        if (body != null) ...[
          const SizedBox(height: 2),
          Text(
            body!,
            style: const TextStyle(
                color: Color(0xFFB6C1D2), fontSize: 13, height: 1.2),
          ),
        ],
      ],
    );
  }
}

// ignore: unused_element
class _WhyPanel extends StatelessWidget {
  final TodayRead read;

  const _WhyPanel({required this.read});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF121D2A).withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF31465F), width: 1.25),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.fromLTRB(18, 8, 18, 8),
          childrenPadding: const EdgeInsets.fromLTRB(20, 0, 20, 18),
          leading: Container(
            width: 52,
            height: 52,
            decoration: const BoxDecoration(
                shape: BoxShape.circle, color: Color(0xFFF4B924)),
            child: const Icon(Icons.lightbulb_outline_rounded,
                color: Colors.white, size: 30),
          ),
          title: const Text(
            'Pourquoi cette analyse ?',
            style: TextStyle(
                color: AppColors.text,
                fontSize: 20,
                fontWeight: FontWeight.w800),
          ),
          subtitle: const Text(
            'Voir le détail des indicateurs et sources',
            style: TextStyle(color: Color(0xFFB6C1D2), fontSize: 17),
          ),
          iconColor: AppColors.text,
          collapsedIconColor: AppColors.text,
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                _edgeExplanation(read),
                style: const TextStyle(
                    color: Color(0xFFB6C1D2), fontSize: 14.5, height: 1.35),
              ),
            ),
            const SizedBox(height: 12),
            for (final driver in read.uncertaintyDrivers.take(3))
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(
                    '+${driver.contribution}  ${_sentenceCase(driver.driver.replaceAll('_', ' '))} - ${driver.detail}',
                    style: const TextStyle(
                        color: AppColors.text, fontSize: 13.5, height: 1.25),
                  ),
                ),
              ),
            if (read.summary.caveats.isNotEmpty) ...[
              const SizedBox(height: 6),
              for (final caveat in read.summary.caveats.take(3))
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 5),
                    child: Text(
                      '- $caveat',
                      style: const TextStyle(
                        color: Color(0xFFB6C1D2),
                        fontSize: 13.5,
                        fontStyle: FontStyle.italic,
                        height: 1.25,
                      ),
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _HeaderButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _HeaderButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Ink(
          height: 66,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: const Color(0xFF121D2B).withValues(alpha: 0.82),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF34506F), width: 1.4),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: AppColors.text, size: 26),
              const SizedBox(width: 12),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppColors.text, fontSize: 19),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChangePill extends StatelessWidget {
  final String label;
  final bool positive;
  final bool available;

  const _ChangePill({
    required this.label,
    this.positive = true,
    this.available = true,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: (available
                ? (positive ? const Color(0xFF0D633F) : AppColors.bad)
                : AppColors.textMuted)
            .withValues(alpha: 0.26),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: available
              ? (positive ? const Color(0xFF63F39F) : AppColors.bad)
              : AppColors.textMuted,
          fontSize: 18,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _OutlinePill extends StatelessWidget {
  final String label;
  final Color color;
  final bool dense;

  const _OutlinePill({
    required this.label,
    required this.color,
    this.dense = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 260),
      padding: EdgeInsets.symmetric(
          horizontal: dense ? 13 : 15, vertical: dense ? 6 : 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: dense ? 0.18 : 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color, width: 1.45),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: color,
          fontSize: dense ? 16 : 14.5,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

String _formatFrenchDate(DateTime date) {
  const months = [
    'janv.',
    'févr.',
    'mars',
    'avr.',
    'mai',
    'juin',
    'juil.',
    'août',
    'sept.',
    'oct.',
    'nov.',
    'déc.',
  ];
  return '${date.day} ${months[date.month - 1]} ${date.year}';
}

DataProvenance _provenanceForReads(
  DataProvenance provenance,
  List<TodayRead> reads,
) {
  if (provenance.origin != DataOrigin.snapshot ||
      provenance.generatedAt != null) {
    return provenance;
  }

  // asOf and timestamp arrive as ISO strings, not DateTime. Parsing must be
  // tolerant: a snapshot whose date cannot be read is treated as undated
  // rather than as fresh, so DataProvenance.isStale flags it.
  DateTime? generatedAt;
  for (final read in reads) {
    final raw = read.marketData?.asOf ?? read.marketData?.timestamp;
    if (raw == null) continue;
    final candidate = DateTime.tryParse(raw)?.toUtc();
    if (candidate == null) continue;
    if (generatedAt == null || candidate.isAfter(generatedAt)) {
      generatedAt = candidate;
    }
  }

  return DataProvenance(DataOrigin.snapshot, generatedAt: generatedAt);
}

/// Le sous-titre décrit les deux couches séparément.
///
/// « Analyse hors ligne » n'a de sens que si rien n'est joignable. Quand le
/// prix arrive en direct et que seule l'analyse vient d'un instantané, le dire
/// ainsi est faux et déroutant.
String _subtitleForLayers(DataProvenance provenance, List<TodayRead> reads) {
  final priceFresh = reads.any(
    (read) => read.marketData?.derived().isTrustworthy ?? false,
  );
  final analysisAt = reads
      .map((read) => read.analysis.computedAtUtc)
      .whereType<DateTime>()
      .fold<DateTime?>(null, (a, b) => a == null || b.isAfter(a) ? b : a);

  final quand = analysisAt == null ? null : _clockLabel(analysisAt.toLocal());

  if (priceFresh && provenance.isSnapshot) {
    return quand == null
        ? 'Prix en direct · analyse enregistrée'
        : 'Prix en direct · analyse calculée à $quand';
  }
  if (priceFresh) {
    return quand == null
        ? 'Données actualisées'
        : 'Données actualisées · analyse de $quand';
  }
  if (provenance.isSnapshot) {
    return provenance.generatedAt == null
        ? 'Mode hors ligne · instantané sans date'
        : 'Mode hors ligne · instantané du '
            '${_formatFrenchDate(provenance.generatedAt!.toLocal())}';
  }
  return _subtitleForProvenance(provenance);
}

String _clockLabel(DateTime moment) =>
    '${moment.hour.toString().padLeft(2, '0')}:'
    '${moment.minute.toString().padLeft(2, '0')}';

String _subtitleForProvenance(DataProvenance provenance) {
  if (provenance.origin == DataOrigin.live) {
    return 'Analyse des marchés en temps réel';
  }
  if (provenance.origin == DataOrigin.snapshot) {
    if (provenance.generatedAt == null) {
      return 'Données périmées · instantané sans date';
    }
    if (provenance.isStale) {
      return 'Données périmées · dernière mise à jour ${_formatFrenchDate(provenance.generatedAt!.toLocal())}';
    }
    return 'Analyse hors ligne · instantané du ${_formatFrenchDate(provenance.generatedAt!.toLocal())}';
  }
  return 'Source des données non confirmée';
}

String _marketPriceLabel(MarketPriceRead? market, [LivePriceTick? live]) {
  if (live != null) {
    final digits = live.priceEur >= 1000 ? 0 : 2;
    return '€${_numberFr(live.priceEur, digits: digits)}';
  }
  if (market == null || !market.available || market.displayPrice == null) {
    return 'INDISPONIBLE';
  }
  // Un prix périmé reste affiché: cacher le chiffre derrière le mot
  // « PÉRIMÉ » rendait la page vide dès que l'instantané dépassait 24 h, ce
  // qui est l'état normal d'un déploiement sans backend. La valeur est
  // conservée à titre informatif et c'est l'étiquette de fraîcheur, juste
  // en dessous, qui dit son âge.
  final value = market.displayPrice!;
  final symbol = market.displayUnit == 'EUR' ? '€' : r'$';
  final digits = value >= 1000 ? 0 : 2;
  return '$symbol${_numberFr(value, digits: digits)}';
}

String _marketChangeLabel(MarketPriceRead? market, [LivePriceTick? live]) {
  final value = live?.change24hPct ?? market?.change24hPct;
  if (value == null || value.isNaN) return '24h N/A';
  final sign = value > 0 ? '+' : '';
  return '$sign${_numberFr(value, digits: 1)} %';
}

String _liveFreshnessShort(LivePriceConnection connection) =>
    connection == LivePriceConnection.live
        ? 'LIVE · Kraken · flux 0,5 s'
        : 'RECONNEXION · dernier prix Kraken';

String _liveFreshnessLabel(
  LivePriceTick live,
  LivePriceConnection connection,
) {
  final elapsed = DateTime.now().toUtc().difference(live.receivedAt);
  final seconds = elapsed.isNegative ? 0 : elapsed.inSeconds;
  final prefix = connection == LivePriceConnection.live
      ? 'LIVE · flux 0,5 s'
      : 'RECONNEXION · dernier prix reçu';
  return '$prefix · Kraken · ${seconds}s';
}

String _marketFreshnessShort(MarketPriceRead? market) {
  if (market == null) return 'marché indisponible';
  // Recalculé, jamais lu dans le payload: un instantané embarqué y déclare
  // « LIVE · 0 s » indéfiniment.
  final derived = market.derived();
  final source = _marketPrimarySource(market);
  return source.isEmpty
      ? derived.description
      : '${derived.description} · $source';
}

String _marketFreshnessLabel(MarketPriceRead? market) {
  if (market == null) return 'INDISPONIBLE';
  final derived = market.derived();
  final asOf =
      market.asOf == null ? '' : ' · as_of ${_dateTimeLabel(market.asOf!)}';
  return '${derived.description}$asOf';
}

String _marketProvidersLabel(MarketPriceRead? market) {
  if (market == null || market.providers.isEmpty) return 'Aucun provider';
  final ok = market.providers
      .where((provider) => provider.status == 'OK' && provider.price != null)
      .map((provider) => _providerSourceLabel(provider))
      .toList();
  if (ok.isEmpty) {
    return market.providers
        .map((provider) => '${provider.provider}: ${provider.status}')
        .join(', ');
  }
  // Un provider peut repondre sur deux paires (USD et EUR): le dedoublonner,
  // sinon Coinbase apparaissait deux fois comme s'il y avait quatre sources.
  final uniques = <String>{...ok}.toList();
  // « FX » ne convient pas a une paire EUR directe: il n'y a pas de
  // conversion. On dit d'ou vient le prix EUR, sans pretendre a un change.
  final eur = market.priceEur != null && market.fxSource != null
      ? ' · Paire EUR: ${market.fxSource}'
      : '';
  return '${uniques.join(' · ')}$eur';
}

String _marketPrimarySource(MarketPriceRead? market) {
  if (market == null) return '';
  MarketProviderRead? provider;
  for (final candidate in market.providers) {
    if (candidate.status == 'OK' &&
        candidate.price != null &&
        candidate.unit == market.displayUnit) {
      provider = candidate;
      break;
    }
  }
  provider ??= () {
    for (final candidate in market.providers) {
      if (candidate.status == 'OK') return candidate;
    }
    return null;
  }();
  if (provider == null) return '';
  return _providerSourceLabel(provider);
}

String _providerSourceLabel(MarketProviderRead provider) {
  final raw = provider.source.isEmpty ? provider.provider : provider.source;
  if (provider.provider == 'fixtures' ||
      raw.toUpperCase().contains('MOCK FIXTURES')) {
    return 'fixtures hors ligne';
  }
  return raw;
}

String _dateTimeLabel(String raw) {
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) return raw;
  final local = parsed.toLocal();
  final minute = local.minute.toString().padLeft(2, '0');
  return '${_formatFrenchDate(local)} ${local.hour}:$minute';
}

String _numberFr(num value, {int digits = 2}) {
  final parts = value.toStringAsFixed(digits).replaceAll('.', ',').split(',');
  final whole = parts.first;
  final buffer = StringBuffer();
  for (var i = 0; i < whole.length; i += 1) {
    final remaining = whole.length - i;
    buffer.write(whole[i]);
    if (remaining > 1 && remaining % 3 == 1) buffer.write(' ');
  }
  if (digits == 0) return buffer.toString();
  return '${buffer.toString()},${parts.last}';
}

/// Fraîcheur, âge et utilisabilité en une ligne.
String _familySummary(FamilyState state) {
  if (!state.available) return 'Indisponible';
  if (!state.valid) return 'Données insuffisantes';
  // Recalculé: les champs de fraîcheur du payload sont figés à l'export et
  // rajeuniraient indéfiniment un instantané embarqué.
  final derived = state.derived();
  final age = derived.ageLabel == null ? '' : ' · ${derived.ageLabel}';
  final usable = state.usableNow() ? '' : ' · non utilisable';
  return '${derived.label}$age$usable';
}

/// Les enums et messages du backend restent anglais; l'UI francaise ne doit
/// jamais les laisser passer tels quels.
String _driverFr(String raw) => switch (raw.toLowerCase()) {
      'no measured edge' => 'Aucun avantage statistique mesurable',
      'edge untested' => 'Avantage non testé',
      'edge measured but modest' => 'Avantage mesuré mais modeste',
      'regime undetermined' => 'Régime indéterminé',
      'neutral regime' => 'Régime neutre',
      'unresolved contradictions' => 'Contradictions non résolues',
      'stale or missing data' => 'Données périmées ou manquantes',
      'crowded positioning' => 'Positionnement encombré',
      _ => _sentenceCase(raw.replaceAll('_', ' ')),
    };

String _driverDetailFr(String raw) {
  const map = {
    'no relationship survived the full filter chain':
        'aucune relation n’a franchi l’ensemble des filtres',
    'research output unavailable, so nothing has been verified':
        'aucun résultat de recherche disponible, donc rien n’est vérifié',
    'directional read is not established':
        'la lecture directionnelle n’est pas établie',
    'no clear directional bias': 'aucun biais directionnel net',
  };
  final hit = map[raw.toLowerCase()];
  if (hit != null) return hit;
  // « stale or missing data » liste ses familles: on traduit les noms.
  return raw
      .replaceAll('price', 'prix')
      .replaceAll('ohlcv_daily', 'bougies journalières')
      .replaceAll('open_interest', 'open interest')
      .replaceAll('dvol', 'volatilité implicite');
}

String _caveatFr(String raw) {
  if (raw.startsWith('Not actionable')) {
    return 'Aucune action: aucun avantage mesuré ne franchit la barre des '
        'preuves, donc toute position reposerait sur le récit et non sur une '
        'relation testée.';
  }
  if (raw.startsWith('Market direction and measured edge')) {
    return 'La direction du marché et l’avantage mesuré sont calculés '
        'séparément: un régime haussier n’est pas une preuve de capacité '
        'prédictive.';
  }
  return raw;
}

String _directionLabel(String raw) {
  final value = raw.toUpperCase();
  if (value.contains('BULLISH')) {
    return value.contains('STRONG') ? 'FORTEMENT HAUSSIER' : 'HAUSSIER';
  }
  if (value.contains('BEARISH')) {
    return value.contains('STRONG') ? 'FORTEMENT BAISSIER' : 'BAISSIER';
  }
  if (value.contains('NEUTRAL')) return 'NEUTRE';
  return 'DIRECTION INCONNUE';
}

Color _directionColor(String raw) {
  final value = raw.toUpperCase();
  if (value.contains('BULLISH')) return AppColors.measured;
  if (value.contains('BEARISH')) return AppColors.bad;
  return AppColors.textMuted;
}

/// Le régime, en français, à partir de l'état structuré et non d'un test
/// binaire. L'ancienne version faisait `contains('BEARISH') ? baissière :
/// haussière`, ce qui décrivait un marché NEUTRE comme haussier.
String? _regimePhrase(String rawDirection) =>
    switch (rawDirection.toUpperCase()) {
      'STRONGLY_BULLISH' => 'un régime fortement haussier',
      'BULLISH' => 'un régime haussier',
      'NEUTRAL' => 'un régime neutre',
      'BEARISH' => 'un régime baissier',
      'STRONGLY_BEARISH' => 'un régime fortement baissier',
      _ => null,
    };

/// La phrase du bandeau, dérivée des états structurés.
///
/// L'ancienne version disait « nous n'avons pas encore d'indicateur
/// directionnel robuste » alors que la direction était établie à 80 % de
/// persistance. Elle confondait deux choses que le reste du système sépare
/// soigneusement : avoir une lecture directionnelle, et avoir un edge
/// statistiquement validé. On peut tenir la première sans la seconde — c'est
/// même le cas le plus fréquent.
String _verdictBody(TodayRead read, {DerivedFreshness? freshness}) {
  final ticker = read.asset;

  if (freshness != null && freshness.blocksAnalysis) {
    final quand = freshness.ageLabel ?? 'à une date inconnue';
    return 'Lecture figée: cette analyse du $ticker a été calculée $quand et '
        'n’a pas été rafraîchie. Les chiffres ci-dessous décrivent ce moment-là, '
        'pas le marché actuel.';
  }

  final regime = _regimePhrase(read.summary.marketDirection);
  if (regime == null) {
    return 'Les données disponibles ne permettent pas d’établir une lecture '
        'directionnelle fiable du $ticker.';
  }

  return switch (read.edgeState) {
    EdgeState.positiveEdge =>
      'Le $ticker évolue dans $regime, et un edge mesurable est actuellement '
          'actif — à surveiller, pas à exécuter automatiquement.',
    EdgeState.negativeEdge =>
      'Le $ticker évolue dans $regime, mais la relation testée joue '
          'défavorablement : aucun setup n’est retenu.',
    EdgeState.insufficientData =>
      'Le $ticker évolue dans $regime. L’historique disponible ne suffit pas à '
          'conclure sur l’existence d’un edge, ce qui n’est pas la même chose '
          'qu’une absence d’edge.',
    EdgeState.notYetTested =>
      'Le $ticker évolue dans $regime. Aucune recherche n’a encore été '
          'exécutée pour ce cas.',
    EdgeState.unstable =>
      'Le $ticker évolue dans $regime, mais l’edge mesuré n’est pas stable '
          'dans le temps : il n’est pas retenu.',
    EdgeState.noMeasurableEdge =>
      'Le $ticker évolue dans $regime, mais aucun setup statistiquement '
          'validé n’est actuellement actif.',
    EdgeState.unknown =>
      'Le $ticker évolue dans $regime. L’état de l’edge n’a pas pu être '
          'déterminé.',
  };
}

String _edgeLabel(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => 'AVANTAGE MESURABLE',
      EdgeState.negativeEdge => 'AVANTAGE DÉFAVORABLE',
      EdgeState.noMeasurableEdge => 'AUCUN AVANTAGE MESURABLE',
      EdgeState.unstable => 'INSTABLE',
      EdgeState.insufficientData => 'DONNÉES INSUFFISANTES',
      EdgeState.notYetTested => 'PAS ENCORE TESTÉ',
      EdgeState.unknown => 'INCONNU',
    };

Color _edgeColor(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => AppColors.measured,
      EdgeState.negativeEdge => AppColors.bad,
      EdgeState.noMeasurableEdge || EdgeState.unstable => AppColors.warn,
      _ => AppColors.textMuted,
    };

String _crowdingLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'NORMAL' => 'NORMAL',
      'HIGH' => 'ÉLEVÉ',
      'EXTREME' => 'EXTRÊME',
      _ => raw.replaceAll('_', ' '),
    };

String _crowdingDirectionTitle(String raw) {
  final value = raw.toUpperCase();
  if (value.contains('LONG')) return 'Biais longs';
  if (value.contains('SHORT')) return 'Biais shorts';
  if (value.contains('BALANCED')) return 'Équilibre';
  return 'Direction inconnue';
}

/// Tous les états de LeverageState, y compris ceux qui manquaient et
/// s'affichaient bruts: QUIET apparaissait tel quel à l'écran.
String _leverageLabel(String raw) => switch (raw.toUpperCase()) {
      'NEW_LONGS' => 'NOUVEAUX LONGS',
      'NEW_SHORTS' => 'NOUVEAUX SHORTS',
      'SHORT_COVERING' => 'RACHAT DE SHORTS',
      'LONG_LIQUIDATION' => 'LIQUIDATION DE LONGS',
      'DELEVERAGING' => 'RÉDUCTION DU LEVIER',
      'CROWDED_LONGS' => 'LONGS SURCHARGÉS',
      'CROWDED_SHORTS' => 'SHORTS SURCHARGÉS',
      'BALANCED' => 'ÉQUILIBRÉ',
      'QUIET' => 'CALME',
      'UNDETERMINED' || 'UNKNOWN' => 'INDÉTERMINÉ',
      'INSUFFICIENT_DATA' => 'DONNÉES INSUFFISANTES',
      _ => raw.replaceAll('_', ' '),
    };

String _fundingLabel(TodayRead read) {
  final band = switch (read.fundingBand.toUpperCase()) {
    'NEUTRAL' => 'NEUTRE',
    'LOW' => 'FAIBLE',
    'HIGH' => 'ÉLEVÉ',
    'NEGATIVE' => 'NÉGATIF',
    'POSITIVE' => 'POSITIF',
    _ => read.fundingBand.replaceAll('_', ' '),
  };
  final percentile = read.fundingPercentile;
  if (percentile == null) return band;
  return '$band (p${percentile.toStringAsFixed(0)})';
}

String _volatilityLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'NORMAL' => 'NORMALE',
      'MODERATE' => 'MODÉRÉE',
      'HIGH' => 'ÉLEVÉE',
      'EXTREME' => 'EXTRÊME',
      _ => raw.replaceAll('_', ' '),
    };

String _entryTimingLabel(String raw) => switch (raw.toUpperCase()) {
      'VERY_UNFAVORABLE' => 'TRÈS DÉFAVORABLE',
      'UNFAVORABLE' => 'DÉFAVORABLE',
      'NEUTRAL' => 'NEUTRE',
      'FAVORABLE' => 'FAVORABLE',
      'VERY_FAVORABLE' => 'TRÈS FAVORABLE',
      'INSUFFICIENT_DATA' => 'DONNÉES INSUFFISANTES',
      // UNDETERMINED est un résultat, pas une absence: le moteur a tourné et
      // n'a pas pu trancher. Le rendre par « INDISPONIBLE » confondait les
      // deux, alors que la distinction est celle que tout le reste du système
      // défend — DONNÉES INSUFFISANTES reste juste au-dessus.
      'WAIT' => 'ATTENDRE',
      'UNDETERMINED' => 'INDÉTERMINÉ',
      _ => raw.replaceAll('_', ' '),
    };

/// Le libellé, plus le score quand le moteur a pu le calculer.
String _timingValue(TodayRead read) {
  final label = _entryTimingLabel(read.summary.entryTiming);
  final score = read.timingScore;
  if (score == null) return label;
  return '$label · ${score >= 0 ? '+' : ''}${score.toStringAsFixed(0)}/100';
}

/// L'incertitude a besoin d'être lue, pas seulement affichée: 40/100 ne dit
/// rien à qui ne connaît pas l'échelle.
String _uncertaintyReading(double score) {
  final lecture = score <= 25
      ? 'lecture fiable'
      : score <= 45
          ? 'lecture exploitable'
          : score <= 70
              ? 'prudence, plusieurs éléments manquent ou se contredisent'
              : 'lecture peu fiable';
  return '0 = tout concorde, 100 = rien n’est fiable. À '
      '${score.toStringAsFixed(0)}: $lecture.';
}

String _uncertaintyLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'MODERATE' => 'MODÉRÉE',
      'HIGH' => 'ÉLEVÉE',
      'EXTREME' => 'EXTRÊME',
      _ => raw.replaceAll('_', ' '),
    };

Color _uncertaintyColor(String raw) => switch (raw.toUpperCase()) {
      'LOW' => AppColors.measured,
      'MODERATE' => AppColors.accent,
      _ => AppColors.warn,
    };

/// La phrase du moteur arrive en anglais: elle est reformulée ici plutôt que
/// recopiée. Les chiffres viennent du payload, jamais du texte.
String _edgeExplanation(TodayRead read) {
  final teste = read.admittedCount + read.rejectedCount;
  if (teste == 0) {
    return 'Aucune relation candidate n’a encore été testée pour le '
        '${read.asset}. Sans test, rien ne peut être affirmé dans un sens ou '
        'dans l’autre.';
  }
  if (read.admittedCount == 0) {
    return '$teste relation${teste > 1 ? 's' : ''} candidate'
        '${teste > 1 ? 's ont' : ' a'} été testée${teste > 1 ? 's' : ''} pour '
        'le ${read.asset}, et aucune n’a survécu à la correction pour tests '
        'multiples, à la taille d’échantillon minimale, au seuil de taille '
        'd’effet et au contrôle de stabilité. Il n’existe donc aucune capacité '
        'démontrée à prévoir les rendements futurs. Cela ne dit rien de la '
        'direction que prendra le marché — seulement que nous ne pouvons pas '
        'prétendre la connaître.';
  }
  return '${read.admittedCount} relation${read.admittedCount > 1 ? 's' : ''} '
      'sur $teste testée${teste > 1 ? 's' : ''} a survécu à l’ensemble des '
      'filtres. Un avantage mesuré reste une propriété historique: il ne '
      'garantit pas le prochain mouvement.';
}

String _sentenceCase(String value) {
  if (value.isEmpty) return value;
  final lower = value.toLowerCase();
  return '${lower[0].toUpperCase()}${lower.substring(1)}';
}

/// Le geste qui développe ou replie une carte.
///
/// Sans lui, les trois actifs développés donnaient une page de plusieurs
/// écrans: la comparaison BTC / ETH / SOL, qui est la raison d'être de cette
/// liste, devenait impossible.
class _ExpandToggle extends StatelessWidget {
  final bool expanded;
  final VoidCallback onTap;

  const _ExpandToggle({required this.expanded, required this.onTap});

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(11),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 9, horizontal: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Flexible(
                  child: Text(
                    expanded ? 'Réduire' : 'Plus de détail',
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.accent,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Icon(
                  expanded
                      ? Icons.keyboard_arrow_up_rounded
                      : Icons.keyboard_arrow_down_rounded,
                  color: AppColors.accent,
                  size: 21,
                ),
              ],
            ),
          ),
        ),
      );
}

/// Une feuille de détail au dessin commun à toute la page.
void _showTodaySheet(
  BuildContext context, {
  required String title,
  required List<Widget> children,
  double initialSize = .6,
}) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: mobilePanel,
    builder: (context) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: initialSize,
      minChildSize: .35,
      maxChildSize: .94,
      builder: (context, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(22, 20, 22, 34),
        children: [
          Text(
            title,
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 20,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 14),
          ...children,
        ],
      ),
    ),
  );
}

class _SheetSection extends StatelessWidget {
  final String title;
  final List<Widget> children;

  const _SheetSection({required this.title, required this.children});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: const TextStyle(
                color: mobileMuted,
                fontSize: 13,
                fontWeight: FontWeight.w800,
                letterSpacing: .5,
              ),
            ),
            const SizedBox(height: 8),
            ...children,
          ],
        ),
      );
}

class _SheetNote extends StatelessWidget {
  final String text;

  const _SheetNote(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Text(
          text,
          style: const TextStyle(
            color: mobileMuted,
            fontSize: 13,
            height: 1.36,
            fontStyle: FontStyle.italic,
          ),
        ),
      );
}

/// Ce que direction, timing et avantage veulent dire, séparément.
void _showReadingsDetail(BuildContext context, TodayPage page) {
  Widget block(String label, ReadingLine line) => _SheetSection(
        title: label,
        children: [
          Text(
            line.value,
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 17,
              fontWeight: FontWeight.w800,
            ),
          ),
          if (line.question.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(
              line.question,
              style: const TextStyle(color: mobileMuted, fontSize: 13),
            ),
          ],
          if (line.detail.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              line.detail,
              style: const TextStyle(
                  color: mobileMuted, fontSize: 14, height: 1.36),
            ),
          ],
        ],
      );

  _showTodaySheet(
    context,
    title: 'Direction, timing, avantage',
    children: [
      block('DIRECTION', page.readings.direction),
      block('TIMING', page.readings.timing),
      block('AVANTAGE DÉMONTRÉ', page.readings.edge),
      if (page.readings.note.isNotEmpty) _SheetNote(page.readings.note),
    ],
  );
}

/// La position dans le range, et ce qui l'invaliderait.
void _showPositionDetail(BuildContext context, TodayPage page) {
  final position = page.position;
  final levels = page.levels;
  String money(double? value) =>
      value == null ? '—' : _numberFr(value, digits: 0);

  _showTodaySheet(
    context,
    title: 'Position ${position.timeframe}',
    initialSize: .55,
    children: [
      _SheetSection(
        title: 'LECTURE',
        children: [
          Text(
            position.headline,
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 17,
              fontWeight: FontWeight.w800,
            ),
          ),
          if (position.detail.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(position.detail,
                style: const TextStyle(color: mobileMuted, fontSize: 14)),
          ],
        ],
      ),
      if (position.hasRange)
        _SheetSection(
          title: 'BORNES DU RANGE',
          children: [
            _TodaySheetLine(
                label: position.bottomLabel,
                value: money(position.rangeBottom)),
            _TodaySheetLine(
                label: 'Milieu', value: money(position.rangeMidpoint)),
            _TodaySheetLine(
                label: position.topLabel, value: money(position.rangeTop)),
          ],
        ),
      if (levels.available)
        _SheetSection(
          title: 'NIVEAUX LES PLUS PROCHES',
          children: [
            if (levels.support != null)
              _TodaySheetLine(
                label: 'Support',
                value: '${money(levels.support!.price)} · '
                    '${levels.support!.distancePct.toStringAsFixed(1)} %',
              ),
            if (levels.resistance != null)
              _TodaySheetLine(
                label: 'Résistance',
                value: '${money(levels.resistance!.price)} · '
                    '+${levels.resistance!.distancePct.toStringAsFixed(1)} %',
              ),
            if (levels.source.isNotEmpty) _SheetNote(levels.source),
          ],
        ),
      if (position.invalidation.isNotEmpty)
        _SheetSection(
          title: 'CE QUI INVALIDERAIT CETTE LECTURE',
          children: [
            Text(
              position.invalidation,
              style: const TextStyle(
                  color: mobileMuted, fontSize: 14, height: 1.36),
            ),
          ],
        ),
      if (position.note.isNotEmpty) _SheetNote(position.note),
    ],
  );
}

/// Les quatre unités de temps, nommées, et leurs désaccords.
void _showTimeframeDetail(BuildContext context, TodayPage page) {
  _showTodaySheet(
    context,
    title: 'Structure par unité de temps',
    initialSize: .55,
    children: [
      _SheetSection(
        title: 'LECTURES',
        children: [
          for (final row in page.timeframes.rows)
            _TodaySheetLine(label: row.timeframe, value: row.label),
          _TodaySheetLine(
              label: 'Alignement', value: page.timeframes.alignmentLabel),
        ],
      ),
      if (page.contradictions.items.isNotEmpty)
        _SheetSection(
          title: page.contradictions.badge,
          children: [
            for (final item in page.contradictions.items)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.title,
                      style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 14.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      item.text,
                      style: const TextStyle(
                          color: mobileMuted, fontSize: 13.5, height: 1.36),
                    ),
                  ],
                ),
              ),
          ],
        ),
      if (page.timeframes.note.isNotEmpty) _SheetNote(page.timeframes.note),
    ],
  );
}

/// Ce que nous avons pu observer, et ce que nous n'avons pas.
void _showCoverageDetail(BuildContext context, TodayPage page) {
  final coverage = page.coverage;
  Widget group(String title, List<CoverageFamily> families) {
    if (families.isEmpty) return const SizedBox.shrink();
    return _SheetSection(
      title: title,
      children: [
        for (final family in families)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        family.label,
                        style: const TextStyle(
                            color: AppColors.text, fontSize: 14.5),
                      ),
                    ),
                    if (family.stale)
                      const Text(
                        'périmée',
                        style: TextStyle(color: AppColors.warn, fontSize: 12.5),
                      ),
                  ],
                ),
                if (family.reason.isNotEmpty && !family.fresh)
                  Text(
                    family.reason,
                    style: const TextStyle(
                        color: mobileMuted, fontSize: 12.5, height: 1.3),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  _showTodaySheet(
    context,
    title: 'Couverture des données',
    initialSize: .7,
    children: [
      _SheetSection(
        title: 'RÉSUMÉ',
        children: [
          _TodaySheetLine(
            label: 'Disponibles',
            value: '${coverage.available} / ${coverage.expected}',
          ),
          _TodaySheetLine(label: 'Récentes', value: '${coverage.fresh}'),
          if (coverage.stale > 0)
            _TodaySheetLine(label: 'Périmées', value: '${coverage.stale}'),
          if (coverage.missing > 0)
            _TodaySheetLine(label: 'Manquantes', value: '${coverage.missing}'),
          if (coverage.uncertaintyScore != null)
            _TodaySheetLine(
              label: 'Incertitude',
              value: '${coverage.uncertaintyScore!.toStringAsFixed(0)}/100',
            ),
        ],
      ),
      if (coverage.uncertaintyNote.isNotEmpty)
        _SheetNote(coverage.uncertaintyNote),
      const SizedBox(height: 10),
      group(coverage.titles['available'] ?? 'DONNÉES DISPONIBLES',
          coverage.availableFamilies),
      group(coverage.titles['missing'] ?? 'DONNÉES MANQUANTES',
          coverage.missingFamilies),
      group(coverage.titles['not_applicable'] ?? 'NON APPLICABLE',
          coverage.notApplicableFamilies),
      group(coverage.titles['by_design'] ?? 'NON COLLECTÉ PAR CONCEPTION',
          coverage.byDesignFamilies),
    ],
  );
}

/// Qui achète, qui vend, famille par famille, avec l'arithmétique visible.
///
/// Une source absente n'apparaît ni comme neutre ni comme zéro: elle est
/// listée avec la raison de son absence, et retirée du calcul.
void _showPressureBreakdown(BuildContext context, PressureBreakdown breakdown) {
  String signed(double? value) => value == null
      ? '—'
      : '${value >= 0 ? '+' : ''}${value.toStringAsFixed(0)}';

  Widget contributions(
    String title,
    List<PressureContribution> items,
    Color tone,
  ) {
    if (items.isEmpty) return const SizedBox.shrink();
    return _SheetSection(
      title: title,
      children: [
        for (final item in items)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        item.label,
                        style: const TextStyle(
                          color: AppColors.text,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    Text(
                      item.available ? signed(item.normalizedScore) : '—',
                      style: TextStyle(
                        color: item.available ? tone : mobileMuted,
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
                if (item.explanation.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    item.explanation,
                    style: const TextStyle(
                        color: mobileMuted, fontSize: 13, height: 1.34),
                  ),
                ],
                if (item.available && item.contributionPoints != null)
                  Text(
                    'Apport au total : '
                    '${signed(item.contributionPoints)} · poids '
                    '${(item.weight * 100).toStringAsFixed(0)} %',
                    style: const TextStyle(color: mobileMuted, fontSize: 12),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  _showTodaySheet(
    context,
    title: 'Qui achète, qui vend ?',
    initialSize: .78,
    children: [
      Text(
        breakdown.headline,
        style: const TextStyle(
          color: AppColors.text,
          fontSize: 18,
          fontWeight: FontWeight.w800,
        ),
      ),
      const SizedBox(height: 3),
      Text(
        breakdown.familiesLine,
        style: const TextStyle(color: mobileMuted, fontSize: 14),
      ),
      const SizedBox(height: 18),
      contributions(
          breakdown.buyersTitle, breakdown.buyers, AppColors.measured),
      contributions(breakdown.sellersTitle, breakdown.sellers, AppColors.bad),
      contributions('SANS DIRECTION NETTE', breakdown.neutral, mobileMuted),
      contributions(
          breakdown.unavailableTitle, breakdown.unavailable, mobileMuted),
      if (breakdown.contradictions.isNotEmpty)
        _SheetSection(
          title: 'SOURCES EN DÉSACCORD',
          children: [
            for (final line in breakdown.contradictions)
              Text(
                line,
                style: const TextStyle(
                    color: mobileMuted, fontSize: 13.5, height: 1.36),
              ),
          ],
        ),
      if (breakdown.missingNote.isNotEmpty) _SheetNote(breakdown.missingNote),
      if (breakdown.tooltip.isNotEmpty) _SheetNote(breakdown.tooltip),
    ],
  );
}
