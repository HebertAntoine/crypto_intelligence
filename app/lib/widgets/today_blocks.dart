/// Les blocs de la page « Aujourd'hui ».
///
/// Aucun de ces widgets ne décide quoi que ce soit. Ils reçoivent des phrases
/// et des nombres déjà arrêtés par le backend, sous un seul `analysisId`, et
/// les disposent. C'est la règle qui rend la page lisible en dix secondes:
/// tout ce qui est affiché ensemble décrit le même instant.
library;

import 'package:flutter/material.dart';

import '../api/today_page.dart';
import '../theme/app_theme.dart';
import 'mobile_kit.dart';

const _panel = Color(0xFF101927);
const _panelBorder = Color(0xFF23364C);

/// Un cartouche compact, du même dessin que le reste de la carte.
class TodayPanel extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final Color? tint;

  const TodayPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
    this.tint,
  });

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: padding,
        decoration: BoxDecoration(
          color: (tint ?? _panel).withValues(alpha: tint == null ? .55 : .10),
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: tint ?? _panelBorder),
        ),
        child: child,
      );
}

class _BlockTitle extends StatelessWidget {
  final String text;
  final Widget? trailing;

  const _BlockTitle(this.text, {this.trailing});

  @override
  Widget build(BuildContext context) => Row(
        children: [
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                color: mobileMuted,
                fontSize: 13.5,
                fontWeight: FontWeight.w800,
                letterSpacing: .6,
              ),
            ),
          ),
          if (trailing != null) trailing!,
        ],
      );
}

Color _directionTone(String state) {
  if (state.contains('BULL')) return AppColors.measured;
  if (state.contains('BEAR')) return AppColors.bad;
  return mobileMuted;
}

Color _timingTone(String state) => switch (state) {
      'STRONG_OPPORTUNITY' || 'OPPORTUNITY' => AppColors.measured,
      'WATCH' => AppColors.accent,
      'WAIT' => AppColors.warn,
      'UNFAVORABLE' => AppColors.bad,
      _ => mobileMuted,
    };

/// Direction, timing et avantage: trois lectures, trois colonnes.
///
/// Elles ne sont jamais fusionnées en un score unique parce qu'elles répondent
/// à trois questions différentes, et qu'une direction haussière accompagnée
/// d'un timing « attendre » et d'aucun avantage démontré est la lecture la
/// plus fréquente que ce système produise.
class DirectionTimingEdgeRow extends StatelessWidget {
  final DirectionTimingEdge readings;
  final VoidCallback? onTap;

  const DirectionTimingEdgeRow({
    super.key,
    required this.readings,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final columns = <(String, ReadingLine, Color)>[
      (
        'DIRECTION',
        readings.direction,
        _directionTone(readings.direction.state)
      ),
      ('TIMING', readings.timing, _timingTone(readings.timing.state)),
      ('AVANTAGE', readings.edge, mobileMuted),
    ];
    return Semantics(
      button: onTap != null,
      label: columns
          .map((column) => '${column.$1} : ${column.$2.value}')
          .join('. '),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(13),
          onTap: onTap,
          child: TodayPanel(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (var i = 0; i < columns.length; i++) ...[
                  if (i > 0)
                    Container(
                      width: 1,
                      height: 34,
                      margin: const EdgeInsets.symmetric(horizontal: 10),
                      color: _panelBorder,
                    ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          columns[i].$1,
                          style: const TextStyle(
                            color: mobileMuted,
                            fontSize: 11.5,
                            fontWeight: FontWeight.w800,
                            letterSpacing: .5,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          columns[i].$2.value,
                          style: TextStyle(
                            color: columns[i].$3,
                            fontSize: 13.5,
                            height: 1.15,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Où le prix se situe dans son range, dessiné à l'échelle.
///
/// La barre n'apparaît que lorsqu'un range validé existe. Fabriquer des bornes
/// pour la remplir donnerait une fausse précision, alors qu'une structure sans
/// range est une information exacte qu'il suffit de nommer.
class StructuralPositionBar extends StatelessWidget {
  final StructuralPosition position;
  final VoidCallback? onTap;

  const StructuralPositionBar({
    super.key,
    required this.position,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    if (!position.hasRange) {
      return TodayPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _BlockTitle('STRUCTURE ${position.timeframe}'),
            const SizedBox(height: 6),
            Text(
              position.headline,
              style: const TextStyle(
                color: AppColors.text,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (position.detail.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                position.detail,
                style: const TextStyle(
                    color: mobileMuted, fontSize: 13, height: 1.3),
              ),
            ],
          ],
        ),
      );
    }

    final percent = position.percent ?? (position.fraction * 100).round();
    return Semantics(
      label: '${position.headline}, $percent pour cent de la hauteur du '
          'range ${position.timeframe}',
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(13),
          onTap: onTap,
          child: TodayPanel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _BlockTitle(
                  'POSITION ${position.timeframe}',
                  trailing: Text(
                    '$percent %',
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  position.headline,
                  style: const TextStyle(
                    color: AppColors.text,
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 11),
                LayoutBuilder(
                  builder: (context, constraints) {
                    final width = constraints.maxWidth;
                    const marker = 11.0;
                    final x = (width - marker) * position.fraction;
                    return SizedBox(
                      height: marker,
                      child: Stack(
                        clipBehavior: Clip.none,
                        children: [
                          Positioned(
                            left: 0,
                            right: 0,
                            top: (marker - 4) / 2,
                            child: Container(
                              height: 4,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(2),
                                gradient: const LinearGradient(colors: [
                                  Color(0xFF2C4A63),
                                  Color(0xFF3E6488),
                                ]),
                              ),
                            ),
                          ),
                          // Le milieu du range, repère discret.
                          Positioned(
                            left: width / 2 - 0.5,
                            top: 0,
                            child: Container(
                                width: 1, height: marker, color: _panelBorder),
                          ),
                          Positioned(
                            left: x,
                            top: 0,
                            child: Container(
                              width: marker,
                              height: marker,
                              decoration: BoxDecoration(
                                color: AppColors.text,
                                shape: BoxShape.circle,
                                border:
                                    Border.all(color: mobilePanel, width: 2),
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
                const SizedBox(height: 7),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      position.bottomLabel,
                      style: const TextStyle(color: mobileMuted, fontSize: 12),
                    ),
                    Text(
                      position.topLabel,
                      style: const TextStyle(color: mobileMuted, fontSize: 12),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Support et résistance les plus proches, avec leur distance réelle.
class NearestLevelsRow extends StatelessWidget {
  final NearestLevels levels;

  const NearestLevelsRow({super.key, required this.levels});

  @override
  Widget build(BuildContext context) {
    if (!levels.available) return const SizedBox.shrink();
    String distance(PriceLevel level) => '${level.distancePct >= 0 ? '+' : ''}'
        '${level.distancePct.toStringAsFixed(1)} %';

    return Row(
      children: [
        if (levels.support != null)
          Expanded(
            child: _LevelChip(
              label: levels.supportLabel,
              value: distance(levels.support!),
              tone: AppColors.measured,
            ),
          ),
        if (levels.support != null && levels.resistance != null)
          const SizedBox(width: 8),
        if (levels.resistance != null)
          Expanded(
            child: _LevelChip(
              label: levels.resistanceLabel,
              value: distance(levels.resistance!),
              tone: AppColors.warn,
            ),
          ),
      ],
    );
  }
}

class _LevelChip extends StatelessWidget {
  final String label;
  final String value;
  final Color tone;

  const _LevelChip({
    required this.label,
    required this.value,
    required this.tone,
  });

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        decoration: BoxDecoration(
          color: _panel.withValues(alpha: .5),
          borderRadius: BorderRadius.circular(11),
          border: Border.all(color: _panelBorder),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: const TextStyle(color: mobileMuted, fontSize: 11.5)),
            const SizedBox(height: 2),
            Text(
              value,
              style: TextStyle(
                  color: tone, fontSize: 15, fontWeight: FontWeight.w800),
            ),
          ],
        ),
      );
}

/// Quatre lectures au plus: position, volatilité, encombrement, prochaine
/// échéance. Au-delà ce n'est plus un contexte, c'est un tableau de bord.
class ImmediateContextBlock extends StatelessWidget {
  final List<ContextItem> items;

  const ImmediateContextBlock({super.key, required this.items});

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    return TodayPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _BlockTitle('CONTEXTE IMMÉDIAT'),
          const SizedBox(height: 9),
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0) const SizedBox(height: 7),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 108,
                  child: Text(
                    items[i].label,
                    style: const TextStyle(color: mobileMuted, fontSize: 13),
                  ),
                ),
                Expanded(
                  child: Text(
                    items[i].value,
                    textAlign: TextAlign.right,
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 13.5,
                      height: 1.25,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// Positionnement dérivé en mots, sans exposer les valeurs brutes.
///
/// Ces lectures sont déjà produites par le backend. Le widget ne les fusionne
/// ni avec la pression ni avec l'edge; il les range simplement dans le cockpit.
class PositioningEtfBlock extends StatelessWidget {
  final PositioningReading positioning;
  final EtfReading etf;

  const PositioningEtfBlock({
    super.key,
    required this.positioning,
    required this.etf,
  });

  @override
  Widget build(BuildContext context) => TodayPanel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const _BlockTitle('POSITIONNEMENT'),
            const SizedBox(height: 9),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: _CompactReading(
                    label: 'POSITIONS',
                    value: positioning.positioning,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _CompactReading(
                    label: 'FUNDING',
                    value: positioning.funding,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _CompactReading(
                    label: 'CROWDING',
                    value: positioning.crowding,
                  ),
                ),
              ],
            ),
            if (etf.available) ...[
              const SizedBox(height: 10),
              Container(height: 1, color: _panelBorder),
              const SizedBox(height: 9),
              Row(
                children: [
                  const Text(
                    'ETF SPOT',
                    style: TextStyle(
                      color: mobileMuted,
                      fontSize: 11.5,
                      fontWeight: FontWeight.w800,
                      letterSpacing: .4,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      etf.headline,
                      textAlign: TextAlign.right,
                      style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 13.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
              if (etf.caveat.isNotEmpty) ...[
                const SizedBox(height: 5),
                Text(
                  etf.caveat,
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 11.5,
                    height: 1.25,
                  ),
                ),
              ],
            ],
          ],
        ),
      );
}

class _CompactReading extends StatelessWidget {
  final String label;
  final String value;

  const _CompactReading({required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: mobileMuted,
              fontSize: 10.5,
              fontWeight: FontWeight.w800,
              letterSpacing: .35,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 13,
              height: 1.18,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      );
}

/// Les échéances programmées à surveiller. Jamais un flux d'actualité: chaque
/// ligne a une date publiée à l'avance, une importance et une source.
class CatalystsBlock extends StatelessWidget {
  final Catalysts catalysts;

  const CatalystsBlock({super.key, required this.catalysts});

  @override
  Widget build(BuildContext context) {
    if (catalysts.items.isEmpty && catalysts.alert == null) {
      return const SizedBox.shrink();
    }
    return TodayPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _BlockTitle('À SURVEILLER'),
          if (catalysts.alert != null) ...[
            const SizedBox(height: 9),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
              decoration: BoxDecoration(
                color: AppColors.warn.withValues(alpha: .12),
                borderRadius: BorderRadius.circular(9),
                border:
                    Border.all(color: AppColors.warn.withValues(alpha: .45)),
              ),
              child: Text(
                catalysts.alert!.label,
                style: const TextStyle(
                  color: AppColors.warn,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: .3,
                ),
              ),
            ),
          ],
          const SizedBox(height: 9),
          for (var i = 0; i < catalysts.items.length; i++) ...[
            if (i > 0) const SizedBox(height: 7),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  margin: const EdgeInsets.only(top: 6),
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: catalysts.items[i].isMajor
                        ? AppColors.warn
                        : mobileMuted,
                  ),
                ),
                const SizedBox(width: 9),
                Expanded(
                  child: Text(
                    catalysts.items[i].name,
                    style: const TextStyle(
                      color: AppColors.text,
                      fontSize: 13.5,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                Text(
                  catalysts.items[i].when,
                  style: const TextStyle(color: mobileMuted, fontSize: 13),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// Ce qui ferait changer la décision, en trois catégories distinctes.
///
/// La troisième existe parce qu'un changement de structure n'a pas de signe:
/// une cassure du haut de range invalide le range sans dégrader la lecture, et
/// la ranger parmi les dégradations faisait lire une cassure haussière comme
/// une mauvaise nouvelle.
class ChangeConditionsBlock extends StatelessWidget {
  final ChangeConditions conditions;

  const ChangeConditionsBlock({super.key, required this.conditions});

  @override
  Widget build(BuildContext context) {
    if (conditions.isEmpty) return const SizedBox.shrink();
    return TodayPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (conditions.improve.isNotEmpty)
            _ConditionGroup(
              title: conditions.improveTitle,
              conditions: conditions.improve,
              tone: AppColors.measured,
              glyph: '✓',
            ),
          if (conditions.improve.isNotEmpty && conditions.degrade.isNotEmpty)
            const SizedBox(height: 11),
          if (conditions.degrade.isNotEmpty)
            _ConditionGroup(
              title: conditions.degradeTitle,
              conditions: conditions.degrade,
              tone: AppColors.bad,
              glyph: '✕',
            ),
          if (conditions.structureChange.isNotEmpty) ...[
            const SizedBox(height: 11),
            _ConditionGroup(
              title: conditions.structureChangeTitle,
              conditions: conditions.structureChange,
              tone: AppColors.accent,
              glyph: '↗',
            ),
          ],
        ],
      ),
    );
  }
}

String _conditionGlyph(ChangeCondition condition, String fallback) =>
    // Le sens appartient à la condition. Une flèche unique par groupe donnait
    // la même à « cassure du haut du range » et à « retour vers le bas ».
    switch (condition.direction) {
      'UP' => '↗',
      'DOWN' => '↘',
      _ => fallback,
    };

class _ConditionGroup extends StatelessWidget {
  final String title;
  final List<ChangeCondition> conditions;
  final Color tone;
  final String glyph;

  const _ConditionGroup({
    required this.title,
    required this.conditions,
    required this.tone,
    required this.glyph,
  });

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _BlockTitle(title),
          const SizedBox(height: 7),
          for (final condition in conditions)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _conditionGlyph(condition, glyph),
                    style: TextStyle(color: tone, fontSize: 13, height: 1.35),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Le titre se lit avant qu'on ait fini de lire; le
                        // détail répond ensuite à « pourquoi ça compterait ».
                        Text(
                          condition.title,
                          style: const TextStyle(
                            color: AppColors.text,
                            fontSize: 13.5,
                            height: 1.3,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        if (condition.detail.isNotEmpty)
                          Text(
                            condition.detail,
                            style: const TextStyle(
                                color: mobileMuted, fontSize: 12.5, height: 1.32),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      );
}

/// La couverture des données, à ne pas confondre avec l'incertitude.
///
/// L'une dit ce que nous avons pu observer, l'autre la solidité de la
/// conclusion. « Couverture 85 % » et « incertitude 60/100 » ensemble ne sont
/// pas contradictoires: nous avons vu la plupart des preuves, et elles ne
/// concordent pas.
class DataCoverageBlock extends StatelessWidget {
  final DataCoverage coverage;
  final VoidCallback? onTap;

  const DataCoverageBlock({super.key, required this.coverage, this.onTap});

  @override
  Widget build(BuildContext context) {
    if (coverage.expected == 0) return const SizedBox.shrink();
    final tone = switch (coverage.level) {
      'GOOD' => AppColors.measured,
      'PARTIAL' => AppColors.warn,
      'LOW' => AppColors.bad,
      _ => mobileMuted,
    };
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(13),
        onTap: onTap,
        child: TodayPanel(
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const _BlockTitle('COUVERTURE DES DONNÉES'),
                    const SizedBox(height: 5),
                    Text(
                      '${coverage.available} / ${coverage.expected} familles '
                      'disponibles',
                      style: const TextStyle(
                        color: AppColors.text,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      coverage.stale > 0
                          ? '${coverage.fresh} récentes · '
                              '${coverage.stale} périmées'
                          : '${coverage.fresh} récentes',
                      style:
                          const TextStyle(color: mobileMuted, fontSize: 12.5),
                    ),
                  ],
                ),
              ),
              Text(
                coverage.label,
                style: TextStyle(
                    color: tone, fontSize: 13, fontWeight: FontWeight.w800),
              ),
              if (onTap != null) ...[
                const SizedBox(width: 4),
                const Icon(Icons.chevron_right_rounded,
                    size: 19, color: mobileMuted),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// 1S / 1J / 4H / 1H, chaque unité nommée en toutes lettres.
///
/// La flèche seule n'est lisible ni par tout le monde ni par un lecteur
/// d'écran, donc chaque ligne porte aussi son mot.
class TimeframeStrip extends StatelessWidget {
  final TimeframeSummary summary;
  final Contradictions contradictions;
  final VoidCallback? onTap;

  const TimeframeStrip({
    super.key,
    required this.summary,
    this.contradictions = Contradictions.none,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    if (summary.rows.isEmpty) return const SizedBox.shrink();
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(13),
        onTap: onTap,
        child: TodayPanel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _BlockTitle(
                'STRUCTURE PAR UNITÉ',
                trailing: Text(
                  summary.alignmentLabel,
                  style: const TextStyle(
                    color: mobileMuted,
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(height: 9),
              Row(
                children: [
                  for (final row in summary.rows)
                    Expanded(
                      child: Semantics(
                        label: '${row.timeframe} ${row.label}',
                        child: Column(
                          children: [
                            Text(
                              row.timeframe,
                              style: const TextStyle(
                                  color: mobileMuted, fontSize: 12),
                            ),
                            const SizedBox(height: 3),
                            Text(
                              row.arrow,
                              style: TextStyle(
                                color: _directionTone(row.state),
                                fontSize: 17,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              row.label,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                  color: mobileMuted,
                                  fontSize: 10.5,
                                  height: 1.15),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
              if (summary.sentence.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  summary.sentence,
                  style: const TextStyle(
                      color: mobileMuted, fontSize: 12.5, height: 1.3),
                ),
              ],
              if (contradictions.has) ...[
                const SizedBox(height: 9),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
                  decoration: BoxDecoration(
                    color: AppColors.accent.withValues(alpha: .12),
                    borderRadius: BorderRadius.circular(7),
                  ),
                  child: Text(
                    contradictions.badge,
                    style: const TextStyle(
                      color: AppColors.accent,
                      fontSize: 11.5,
                      fontWeight: FontWeight.w800,
                      letterSpacing: .4,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Le dernier changement de verdict, s'il a été enregistré au moment où il
/// s'est produit. Sans historique, ce bloc ne s'affiche pas: une lecture
/// passée reconstruite depuis les bougies d'aujourd'hui répondrait à une autre
/// question que celle posée.
class LastChangeLine extends StatelessWidget {
  final LastDecisionChange change;

  const LastChangeLine({super.key, required this.change});

  @override
  Widget build(BuildContext context) {
    if (!change.available) return const SizedBox.shrink();
    final moment = change.changedAtLocal;
    final clock = moment == null
        ? ''
        : '${moment.hour.toString().padLeft(2, '0')}:'
            '${moment.minute.toString().padLeft(2, '0')} · ';
    return TodayPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _BlockTitle(change.title),
          const SizedBox(height: 6),
          Text(
            '$clock${change.text}',
            style: const TextStyle(
              color: AppColors.text,
              fontSize: 13.5,
              fontWeight: FontWeight.w600,
              height: 1.3,
            ),
          ),
          if (change.reason.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              change.reason,
              style: const TextStyle(
                  color: mobileMuted, fontSize: 12.5, height: 1.3),
            ),
          ],
        ],
      ),
    );
  }
}

/// Affiché lorsque deux parties du payload ne portent pas le même
/// `analysisId`. L'écran refuse alors de les combiner et le dit, au lieu de
/// les empiler comme si elles décrivaient le même instant.
class AnalysisMismatchBanner extends StatelessWidget {
  const AnalysisMismatchBanner({super.key});

  @override
  Widget build(BuildContext context) => TodayPanel(
        tint: AppColors.warn,
        child: Row(
          children: [
            const Icon(Icons.sync_rounded, size: 18, color: AppColors.warn),
            const SizedBox(width: 9),
            const Expanded(
              child: Text(
                'Analyse en cours d’actualisation. Les blocs reçus ne '
                'décrivent pas le même instant et ne sont pas combinés.',
                style:
                    TextStyle(color: AppColors.warn, fontSize: 13, height: 1.3),
              ),
            ),
          ],
        ),
      );
}

Color _pressureTone(String direction) => switch (direction) {
      'STRONG_BUY' || 'BUY' || 'SLIGHT_BUY' => AppColors.measured,
      'SLIGHT_SELL' => AppColors.warn,
      'SELL' || 'STRONG_SELL' => AppColors.bad,
      _ => mobileMuted,
    };

/// Les cinq familles, une ligne chacune: pastille, nom, état, une phrase.
///
/// C'est la lecture complète que demande un clic sur « qui achète, qui vend ».
/// Les valeurs brutes — funding, open interest, flux par émetteur — restent
/// dans Preuves: ici la question est qui pousse, pas comment le chiffre est
/// fabriqué.
class PressureFamilyList extends StatelessWidget {
  final PressureBreakdown pressure;

  /// Affiche l'apport de chaque famille au total. Réservé à la feuille de
  /// détail; la carte principale n'en a pas besoin.
  final bool showContributions;

  const PressureFamilyList({
    super.key,
    required this.pressure,
    this.showContributions = false,
  });

  @override
  Widget build(BuildContext context) {
    final families = [
      ...pressure.applicableFamilies,
      ...pressure.notApplicable,
    ];
    if (families.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final family in families)
          Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 22,
                  child: Text(
                    family.applicable ? family.dot : '·',
                    style: const TextStyle(fontSize: 13),
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              family.label,
                              style: const TextStyle(
                                color: AppColors.text,
                                fontSize: 14.5,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          Text(
                            family.applicable
                                ? family.directionLabel
                                : 'Sans objet',
                            style: TextStyle(
                              color: _pressureTone(family.direction),
                              fontSize: 13.5,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                      if (family.sentence.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          family.sentence,
                          style: const TextStyle(
                              color: mobileMuted, fontSize: 12.5, height: 1.32),
                        ),
                      ],
                      // « Apport +32,9 · poids 30 % » donnait deux
                      // arithmétiques: +32,9 contient déjà le poids. On nomme
                      // donc la contribution, et le poids réellement utilisé.
                      if (showContributions &&
                          family.weightedContribution != null)
                        Text(
                          'Contribution : '
                          '${family.weightedContribution! >= 0 ? '+' : ''}'
                          '${family.weightedContribution!.toStringAsFixed(1)}'
                          '${family.effectiveWeight == null ? '' : '  ·  '
                              'Poids effectif : '
                              '${(family.effectiveWeight! * 100).toStringAsFixed(0)} %'}',
                          style: const TextStyle(
                              color: mobileMuted, fontSize: 11.5),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
