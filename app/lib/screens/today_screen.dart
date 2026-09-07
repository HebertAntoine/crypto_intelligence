/// Ecran "Aujourd’hui".
///
/// Le backend reste la source de verite pour les verdicts; cette page met ces
/// donnees dans une interface mobile proche de la maquette fournie.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/freshness.dart';
import '../diagnostics/today_diagnostics.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';

class TodayScreen extends StatefulWidget {
  final ApiClient client;

  const TodayScreen({super.key, required this.client});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  late Future<List<TodayRead>> _future;
  Timer? _refreshTimer;

  static const _assets = ['BTC', 'ETH', 'SOL'];

  @override
  void initState() {
    super.initState();
    _future = _load();
    _refreshTimer = Timer.periodic(const Duration(seconds: 45), (_) {
      if (mounted) _reload();
    });
  }

  Future<List<TodayRead>> _load() => widget.client.todayAll(_assets);

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
    _refreshTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MobileGradientFrame(
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
              padding: const EdgeInsets.fromLTRB(26, 26, 26, 260),
              children: [
                _TodayHeader(
                  provenance: provenance,
                  onRefresh: _reload,
                ),
                const SizedBox(height: 20),
                // The app bundles snapshots so it can render without a
                // backend. A snapshot is a photograph of a past moment;
                // showing it as "today" without saying so would be the
                // one thing this project exists not to do.
                _ProvenanceBanner(provenance: provenance),
                for (final read in reads) ...[
                  _MarketCard(read: read, provenance: provenance),
                  const SizedBox(height: 22),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}

/// Says plainly where the numbers came from and how old they are.
class _ProvenanceBanner extends StatelessWidget {
  final DataProvenance provenance;

  const _ProvenanceBanner({required this.provenance});

  @override
  Widget build(BuildContext context) {
    if (!provenance.isSnapshot) return const SizedBox.shrink();

    final stale = provenance.isStale;
    final colour = stale ? AppColors.warn : mobileMuted;

    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: colour.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: colour.withValues(alpha: 0.55), width: 1.2),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              stale ? Icons.history_toggle_off : Icons.snippet_folder_outlined,
              color: colour,
              size: 20,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    provenance.describe(),
                    style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                      color: colour,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    stale
                        ? "Ces chiffres ne décrivent pas le marché actuel. Aucun "
                            "backend n'est joignable depuis cette page."
                        : "Aucun backend joignable: lecture issue de l'instantané "
                            'intégré à la version publiée.',
                    style: const TextStyle(
                      fontSize: 12,
                      color: mobileMuted,
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TodayHeader extends StatelessWidget {
  final DataProvenance provenance;
  final VoidCallback onRefresh;

  const _TodayHeader({
    required this.provenance,
    required this.onRefresh,
  });

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
                _subtitleForProvenance(provenance),
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
        // Flexible: un Wrap prend sa largeur naturelle et ne descend jamais
        // sous celle de son plus grand enfant, donc il poussait le titre hors
        // de l'ecran au lieu de se replier.
        Flexible(
          child: Wrap(
            spacing: 10,
            runSpacing: 10,
            alignment: WrapAlignment.end,
            children: [
              _HeaderButton(
                icon: Icons.calendar_today_rounded,
                label: _formatFrenchDate(DateTime.now()),
                onTap: () => _showDateInfo(context, provenance),
              ),
              _SquareHeaderButton(
                icon: Icons.settings_outlined,
                onTap: () => _showSettings(context, provenance, onRefresh),
              ),
            ],
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

  void _showSettings(
    BuildContext context,
    DataProvenance provenance,
    VoidCallback onRefresh,
  ) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: mobilePanel,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(22, 20, 22, 34),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Réglages de lecture',
              style: TextStyle(
                color: AppColors.text,
                fontSize: 24,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              provenance.describe(),
              style: const TextStyle(
                color: mobileMuted,
                fontSize: 15,
                height: 1.35,
              ),
            ),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {
                  Navigator.of(context).pop();
                  onRefresh();
                },
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Rafraîchir les données'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MarketCard extends StatelessWidget {
  final TodayRead read;

  /// D'ou vient ce payload: le diagnostic ouvert au clic en a besoin.
  final DataProvenance provenance;

  const _MarketCard({required this.read, required this.provenance});

  @override
  Widget build(BuildContext context) {
    final meta = _AssetMeta.forAsset(read.asset);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(17),
        onTap: () => _showDetails(context, read, meta, provenance),
        child: Ink(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: const Color(0xFF101927).withValues(alpha: 0.86),
            borderRadius: BorderRadius.circular(17),
            border: Border.all(color: const Color(0xFF1F4A7E), width: 1.4),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.34),
                blurRadius: 24,
                offset: const Offset(0, 15),
              ),
              BoxShadow(
                color: const Color(0xFF1A67B3).withValues(alpha: 0.12),
                blurRadius: 28,
                spreadRadius: -8,
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _AssetHeader(read: read, meta: meta),
              const SizedBox(height: 22),
              _VerdictPanel(read: read),
              const SizedBox(height: 16),
              _MetricGrid(read: read),
              const SizedBox(height: 20),
              const Divider(height: 1, color: Color(0xFF2A3B51)),
              const SizedBox(height: 16),
              _DetailRows(read: read),
              const SizedBox(height: 22),
              _WhyPanel(read: read),
            ],
          ),
        ),
      ),
    );
  }

  void _showDetails(
    BuildContext context,
    TodayRead read,
    _AssetMeta meta,
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
                _CryptoLogo(meta: meta),
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
            _TodaySheetLine(
              label: 'Prix',
              value: _marketPriceLabel(read.marketData),
            ),
            _TodaySheetLine(
              label: '24h',
              value: _marketChangeLabel(read.marketData),
            ),
            _TodaySheetLine(
              label: 'Fraîcheur',
              value: _marketFreshnessLabel(read.marketData),
            ),
            _TodaySheetLine(
              label: 'Providers',
              value: _marketProvidersLabel(read.marketData),
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
                  : read.directionSource,
            ),
            _TodaySheetLine(
              label: 'Edge',
              value:
                  '${_edgeLabel(read.edgeState)} · ${read.admittedCount} validé, ${read.rejectedCount} rejeté',
            ),
            _TodaySheetLine(
                label: 'Crowding', value: _crowdingLabel(read.crowdingLevel)),
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
                'Drivers',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              for (final driver in read.uncertaintyDrivers)
                Text(
                  '• ${_sentenceCase(driver.driver.replaceAll('_', ' '))}: ${driver.detail}',
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
                'Caveats',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              for (final caveat in read.summary.caveats)
                Text(
                  '• $caveat',
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
  final _AssetMeta meta;

  const _AssetHeader({required this.read, required this.meta});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _CryptoLogo(meta: meta),
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
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerRight,
                child: Text(
                  _marketPriceLabel(read.marketData),
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
                label: _marketChangeLabel(read.marketData),
                positive: (read.marketData?.change24hPct ?? 0) >= 0,
                // La variation reste lisible, mais perd sa couleur dès que
                // l'horodatage n'est plus fiable: en vert ou en rouge elle se
                // lirait comme un mouvement en cours.
                available: read.marketData?.change24hPct != null &&
                    (read.marketData?.derived().isTrustworthy ?? false),
              ),
              const SizedBox(height: 6),
              Text(
                _marketFreshnessShort(read.marketData),
                textAlign: TextAlign.right,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: mobileMuted, fontSize: 12),
              ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        const Icon(Icons.chevron_right_rounded,
            color: AppColors.text, size: 30),
      ],
    );
  }
}

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
            title: 'Edge mesurable',
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

class _DetailRows extends StatelessWidget {
  final TodayRead read;

  const _DetailRows({required this.read});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _InfoRow(
          icon: Icons.groups_rounded,
          label: 'Crowding',
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
        ),
        _InfoRow(
          icon: Icons.check_box_rounded,
          label: 'Opportunité d’entrée',
          value: _entryTimingLabel(read.summary.entryTiming),
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
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 620;
        final leading = Row(
          children: [
            SizedBox(
                width: 54, child: Icon(icon, color: AppColors.text, size: 30)),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(color: Color(0xFFB6C1D2), fontSize: 20),
              ),
            ),
            if (compact)
              IconButton(
                tooltip: 'Détail',
                icon: const Icon(Icons.info_outline_rounded,
                    color: AppColors.text, size: 22),
                onPressed: () => _showInfo(context),
              ),
          ],
        );

        final valueWidget = Align(
          alignment: compact ? Alignment.centerLeft : Alignment.centerRight,
          child: valuePill
              ? _OutlinePill(label: value, color: valueColor, dense: true)
              : Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textAlign: compact ? TextAlign.left : TextAlign.right,
                  style: const TextStyle(
                    color: AppColors.text,
                    fontSize: 17,
                    fontWeight: FontWeight.w500,
                  ),
                ),
        );

        if (compact) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 9),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                leading,
                Padding(
                  padding: const EdgeInsets.only(left: 54),
                  child: valueWidget,
                ),
                if (sideTitle != null || sideBody != null)
                  Padding(
                    padding: const EdgeInsets.only(left: 54, top: 8),
                    child: _SideNote(title: sideTitle, body: sideBody),
                  ),
              ],
            ),
          );
        }

        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 9),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              SizedBox(
                  width: 54,
                  child: Icon(icon, color: AppColors.text, size: 30)),
              SizedBox(
                width: 220,
                child: Text(
                  label,
                  style:
                      const TextStyle(color: Color(0xFFB6C1D2), fontSize: 20),
                ),
              ),
              Expanded(child: valueWidget),
              if (sideTitle != null || sideBody != null) ...[
                const SizedBox(width: 24),
                SizedBox(
                    width: 210,
                    child: _SideNote(title: sideTitle, body: sideBody)),
              ],
              IconButton(
                tooltip: 'Détail',
                icon: const Icon(Icons.info_outline_rounded,
                    color: AppColors.text, size: 22),
                onPressed: () => _showInfo(context),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showInfo(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text(label, style: const TextStyle(fontSize: 16)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(value, style: const TextStyle(fontSize: 14)),
            if (sideTitle != null || sideBody != null) ...[
              const SizedBox(height: 12),
              if (sideTitle != null)
                Text(
                  sideTitle!,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              if (sideBody != null) ...[
                const SizedBox(height: 4),
                Text(sideBody!,
                    style: const TextStyle(
                        color: AppColors.textMuted, height: 1.35)),
              ],
            ],
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

class _SquareHeaderButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _SquareHeaderButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Ink(
          width: 66,
          height: 66,
          decoration: BoxDecoration(
            color: const Color(0xFF121D2B).withValues(alpha: 0.82),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF34506F), width: 1.4),
          ),
          child: Icon(icon, color: AppColors.text, size: 30),
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

class _CryptoLogo extends StatelessWidget {
  final _AssetMeta meta;

  const _CryptoLogo({required this.meta});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 82,
      height: 82,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: meta.logoGradient,
        ),
        boxShadow: [
          BoxShadow(
            color: meta.logoGradient.last.withValues(alpha: 0.25),
            blurRadius: 18,
            spreadRadius: -2,
          ),
        ],
      ),
      child: Center(child: meta.logo),
    );
  }
}

class _EthMark extends StatelessWidget {
  const _EthMark();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(size: const Size(43, 58), painter: _EthPainter());
  }
}

class _EthPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final topPaint = Paint()..color = Colors.white.withValues(alpha: 0.94);
    final bottomPaint = Paint()..color = Colors.white.withValues(alpha: 0.72);
    final stroke = Paint()
      ..color = const Color(0xFFB9C9FF).withValues(alpha: 0.56)
      ..strokeWidth = 1.4
      ..style = PaintingStyle.stroke;

    final cx = size.width / 2;
    final top = Path()
      ..moveTo(cx, 0)
      ..lineTo(size.width, size.height * 0.52)
      ..lineTo(cx, size.height * 0.38)
      ..lineTo(0, size.height * 0.52)
      ..close();
    final bottom = Path()
      ..moveTo(0, size.height * 0.58)
      ..lineTo(cx, size.height)
      ..lineTo(size.width, size.height * 0.58)
      ..lineTo(cx, size.height * 0.72)
      ..close();

    canvas.drawPath(top, topPaint);
    canvas.drawPath(bottom, bottomPaint);
    canvas.drawLine(Offset(cx, 0), Offset(cx, size.height), stroke);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _SolMark extends StatelessWidget {
  const _SolMark();

  @override
  Widget build(BuildContext context) {
    return const Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _SolBar(colorA: Color(0xFF35E8AA), colorB: Color(0xFF8A6BFF)),
        SizedBox(height: 6),
        _SolBar(colorA: Color(0xFF8A6BFF), colorB: Color(0xFFE35EFF)),
        SizedBox(height: 6),
        _SolBar(colorA: Color(0xFFE35EFF), colorB: Color(0xFF35E8AA)),
      ],
    );
  }
}

class _SolBar extends StatelessWidget {
  final Color colorA;
  final Color colorB;

  const _SolBar({required this.colorA, required this.colorB});

  @override
  Widget build(BuildContext context) {
    return Transform(
      transform: Matrix4.skewX(-0.22),
      child: Container(
        width: 42,
        height: 9,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(2),
          gradient: LinearGradient(colors: [colorA, colorB]),
        ),
      ),
    );
  }
}

class _AssetMeta {
  final String name;
  final Widget logo;
  final List<Color> logoGradient;

  const _AssetMeta({
    required this.name,
    required this.logo,
    required this.logoGradient,
  });

  static _AssetMeta forAsset(String asset) => switch (asset) {
        'ETH' => const _AssetMeta(
            name: 'Ethereum',
            logo: _EthMark(),
            logoGradient: [Color(0xFF7A63F8), Color(0xFF5146E8)],
          ),
        'SOL' => const _AssetMeta(
            name: 'Solana',
            logo: _SolMark(),
            logoGradient: [Color(0xFF112F38), Color(0xFF151423)],
          ),
        _ => const _AssetMeta(
            name: 'Bitcoin',
            logo: Text(
              '₿',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 50,
                  fontWeight: FontWeight.w800),
            ),
            logoGradient: [Color(0xFFFFA52C), Color(0xFFFF8B1F)],
          ),
      };
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

String _marketPriceLabel(MarketPriceRead? market) {
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

String _marketChangeLabel(MarketPriceRead? market) {
  final value = market?.change24hPct;
  if (value == null || value.isNaN) return '24h N/A';
  final sign = value > 0 ? '+' : '';
  return '$sign${_numberFr(value, digits: 1)} %';
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
  final fx = market.fxSource == null ? '' : ' · FX: ${market.fxSource}';
  return '${ok.join(', ')}$fx';
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
  final age = state.ageSeconds == null ? '' : ' · ${ageLabel(state.ageSeconds!)}';
  final usable = state.usable ? '' : ' · non utilisable';
  return '${freshnessLabel(state.freshness)}$age$usable';
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
      EdgeState.positiveEdge => 'EDGE MESURABLE',
      EdgeState.negativeEdge => 'EDGE DÉFAVORABLE',
      EdgeState.noMeasurableEdge => 'AUCUN EDGE MESURABLE',
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

String _leverageLabel(String raw) => switch (raw.toUpperCase()) {
      'NEW_LONGS' => 'NOUVEAUX LONGS',
      'NEW_SHORTS' => 'NOUVEAUX SHORTS',
      'CROWDED_LONGS' => 'LONGS SURCHARGÉS',
      'CROWDED_SHORTS' => 'SHORTS SURCHARGÉS',
      'BALANCED' => 'ÉQUILIBRE',
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
      'UNDETERMINED' => 'INDÉTERMINÉ',
      _ => raw.replaceAll('_', ' '),
    };

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

String _edgeExplanation(TodayRead read) {
  if (read.edgeStatement.isNotEmpty) return read.edgeStatement;
  return 'Le signal est affiché seulement si les données backend l’ont validé. Sans edge mesurable, l’application garde une recommandation prudente.';
}

String _sentenceCase(String value) {
  if (value.isEmpty) return value;
  final lower = value.toLowerCase();
  return '${lower[0].toUpperCase()}${lower.substring(1)}';
}
