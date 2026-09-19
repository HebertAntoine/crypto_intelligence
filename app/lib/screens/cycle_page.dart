/// "🔄 Cycle": where Bitcoin stands, drawn from the data and nothing else.
///
/// The page reads top to bottom: the phase, the chart that shows how the
/// market got here, why the engine reads it that way, what would move it on,
/// the monthly archive of the analysis, and the previous cycles as history.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/cycle_models.dart';
import '../widgets/mobile_kit.dart';

const _phaseBlue = Color(0xFF4FA8FF);
const _phaseGreen = Color(0xFF55DD8B);
const _phaseFire = Color(0xFFFF8A3D);
const _phaseOrange = Color(0xFFFF9A4D);
const _phaseRed = Color(0xFFFF6676);

/// One colour per concept, the same as everywhere else in the application.
Color phaseColor(String tone) => switch (tone) {
      'BLUE' => _phaseBlue,
      'GREEN' => _phaseGreen,
      'FIRE' => _phaseFire,
      'ORANGE' => _phaseOrange,
      'RED' => _phaseRed,
      _ => mobileMuted,
    };

String _fr(double value, [int decimals = 0]) {
  final text = value.toStringAsFixed(decimals);
  final parts = text.split('.');
  final digits = parts.first.replaceAll('-', '');
  final buffer = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buffer.write(' ');
    buffer.write(digits[i]);
  }
  final sign = value < 0 ? '-' : '';
  return parts.length > 1 ? '$sign$buffer,${parts[1]}' : '$sign$buffer';
}

String _usd(double value) => '${_fr(value)} \$';

String _signed(double value) => '${value >= 0 ? '+' : ''}${_fr(value)} %';

class CyclePage extends StatefulWidget {
  final ApiClient client;
  final String asset;

  const CyclePage({super.key, required this.client, required this.asset});

  @override
  State<CyclePage> createState() => _CyclePageState();
}

class _CyclePageState extends State<CyclePage> {
  late final Future<CycleRead> _future = widget.client.cycle(widget.asset);

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFF040C18),
        body: SafeArea(
          bottom: false,
          child: FutureBuilder<CycleRead>(
            future: _future,
            builder: (context, snapshot) {
              final cycle = snapshot.data;
              return Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(8, 4, 18, 0),
                    child: Row(
                      children: [
                        IconButton(
                          key: const ValueKey('cycle-back'),
                          tooltip: 'Retour',
                          onPressed: () => Navigator.of(context).maybePop(),
                          icon: const Icon(Icons.arrow_back_ios_new_rounded,
                              color: Colors.white),
                        ),
                        Expanded(
                          child: Text(
                            cycle?.title ?? '🔄 Cycle',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 19,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: snapshot.connectionState != ConnectionState.done
                        ? const Center(child: CircularProgressIndicator())
                        : cycle == null
                            ? const Center(
                                child: Padding(
                                  padding: EdgeInsets.all(24),
                                  child: Text(
                                    'Lecture du cycle indisponible : historique insuffisant.',
                                    style: TextStyle(color: mobileMuted),
                                  ),
                                ),
                              )
                            : ListView(
                                key: const ValueKey('cycle-page'),
                                padding: const EdgeInsets.fromLTRB(18, 8, 18, 120),
                                children: [
                                  _PhaseCard(cycle: cycle),
                                  const SizedBox(height: 14),
                                  _ChartCard(cycle: cycle),
                                  const SizedBox(height: 14),
                                  _WhyCard(cycle: cycle),
                                  const SizedBox(height: 14),
                                  _NextStepCard(cycle: cycle),
                                  const SizedBox(height: 14),
                                  _SnapshotsCard(snapshots: cycle.snapshots),
                                  const SizedBox(height: 14),
                                  _PreviousCyclesCard(cycle: cycle),
                                ],
                              ),
                  ),
                ],
              );
            },
          ),
        ),
      );
}

/// The phase, its direction, and three figures. Nothing else.
class _PhaseCard extends StatelessWidget {
  final CycleRead cycle;

  const _PhaseCard({required this.cycle});

  @override
  Widget build(BuildContext context) {
    final color = phaseColor(cycle.tone);
    final relative = cycle.relativeStrength;
    return GlassPanel(
      key: const ValueKey('cycle-phase'),
      borderColor: color.withValues(alpha: .6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'PHASE ACTUELLE',
            style: TextStyle(
              color: Color(0xFF8FA8C4),
              fontSize: 11.5,
              letterSpacing: .8,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            '${cycle.phaseEmoji} ${cycle.phaseLabel}',
            style: TextStyle(color: color, fontSize: 26, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 2),
          Text(
            '${cycle.directionEmoji} ${cycle.directionLabel}',
            key: const ValueKey('cycle-direction'),
            style: const TextStyle(
                color: Colors.white, fontSize: 15, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Text(
            cycle.summary,
            style: const TextStyle(
                color: Color(0xFFD5E1F2), fontSize: 13.5, height: 1.35),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              if (cycle.isBtc && cycle.daysSinceHalving != null)
                Expanded(
                  child: _Figure(
                    emoji: '⚡',
                    label: 'Depuis le halving',
                    value: '${cycle.daysSinceHalving} j',
                  ),
                ),
              Expanded(
                child: _Figure(
                  emoji: '🏆',
                  label: cycle.isBtc ? 'Distance de l’ATH' : 'BTC sous son record',
                  value: _signed(cycle.drawdownPct),
                ),
              ),
              Expanded(
                child: _Figure(
                  emoji: '📅',
                  label: 'Phase depuis',
                  value: '${cycle.daysInPhase} j',
                ),
              ),
            ],
          ),
          if (!cycle.isBtc && relative.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              '📊 ${relative['label']} ${relative['emoji']} '
              '(${_signed((relative['change_pct'] as num?)?.toDouble() ?? 0)} sur '
              '${relative['window_days']} j)',
              key: const ValueKey('cycle-relative'),
              style: const TextStyle(color: Colors.white, fontSize: 13),
            ),
            const SizedBox(height: 4),
            Text(
              relative['note']?.toString() ?? '',
              style: const TextStyle(color: mobileMuted, fontSize: 11.5, height: 1.3),
            ),
          ],
        ],
      ),
    );
  }
}

class _Figure extends StatelessWidget {
  final String emoji;
  final String label;
  final String value;

  const _Figure({required this.emoji, required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$emoji $label',
              maxLines: 2,
              style: const TextStyle(color: mobileMuted, fontSize: 11, height: 1.2)),
          const SizedBox(height: 3),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: const TextStyle(
                  color: Colors.white, fontSize: 18, fontWeight: FontWeight.w900),
            ),
          ),
        ],
      );
}

/// The big picture: the whole history, its phases, the halvings, and today.
class _ChartCard extends StatelessWidget {
  final CycleRead cycle;

  const _ChartCard({required this.cycle});

  @override
  Widget build(BuildContext context) {
    final used = <String>{for (final run in cycle.chart.phases) run.tone};
    return GlassPanel(
      key: const ValueKey('cycle-chart'),
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  '📈 Historique du cycle',
                  style: TextStyle(
                      color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800),
                ),
              ),
              Text('échelle log',
                  style: TextStyle(color: mobileMuted.withValues(alpha: .8), fontSize: 11)),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            height: 260,
            child: CustomPaint(
              size: Size.infinite,
              painter: CycleChartPainter(chart: cycle.chart),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            '📍 Aujourd’hui · ${_dateFr(cycle.chart.todayDate)} · BTC ${_usd(cycle.chart.todayPrice)}',
            key: const ValueKey('cycle-today'),
            style: const TextStyle(
                color: Colors.white, fontSize: 13, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            runSpacing: 6,
            children: [
              for (final tone in ['GREEN', 'FIRE', 'ORANGE', 'BLUE', 'RED'])
                if (used.contains(tone))
                  _LegendChip(tone: tone, label: _toneLabel(tone)),
            ],
          ),
          for (final halving in cycle.chart.halvings.where((h) => h.estimated)) ...[
            const SizedBox(height: 8),
            Text('📅 ${halving.label}',
                style: const TextStyle(color: mobileMuted, fontSize: 11.5)),
          ],
          if (cycle.chart.localLow.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '🔻 ${cycle.chart.localLow['label']} : '
              '${_usd((cycle.chart.localLow['price'] as num?)?.toDouble() ?? 0)} '
              '(${cycle.chart.localLow['date']})',
              style: const TextStyle(color: mobileMuted, fontSize: 11.5),
            ),
          ],
        ],
      ),
    );
  }
}

String _toneLabel(String tone) => switch (tone) {
      'GREEN' => 'Expansion / récupération haussière',
      'FIRE' => 'Découverte de prix',
      'ORANGE' => 'Transition / distribution possible',
      'BLUE' => 'Accumulation / récupération',
      'RED' => 'Bear / drawdown',
      _ => 'Indéterminé',
    };

String _dateFr(DateTime when) =>
    '${when.day.toString().padLeft(2, '0')}/${when.month.toString().padLeft(2, '0')}/${when.year}';

class _LegendChip extends StatelessWidget {
  final String tone;
  final String label;

  const _LegendChip({required this.tone, required this.label});

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              color: phaseColor(tone).withValues(alpha: .55),
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          const SizedBox(width: 5),
          Text(label, style: const TextStyle(color: mobileMuted, fontSize: 11)),
        ],
      );
}

/// A stretch of chart painted in one colour.
typedef PhaseBand = ({String tone, DateTime start, DateTime end});

/// Joins neighbouring runs of the same colour, and absorbs runs shorter than
/// three weeks into the band before them.
List<PhaseBand> mergedBands(List<CyclePhaseRun> runs, {int minDays = 21}) {
  final bands = <PhaseBand>[];
  for (final run in runs) {
    if (bands.isNotEmpty && bands.last.tone == run.tone) {
      bands[bands.length - 1] = (
        tone: bands.last.tone,
        start: bands.last.start,
        end: run.end,
      );
      continue;
    }
    if (bands.isNotEmpty && run.days < minDays) {
      bands[bands.length - 1] = (
        tone: bands.last.tone,
        start: bands.last.start,
        end: run.end,
      );
      continue;
    }
    bands.add((tone: run.tone, start: run.start, end: run.end));
  }
  return bands;
}

/// Draws the price on a log scale, with the phases as background bands,
/// the halvings as vertical marks and today as a labelled point.
class CycleChartPainter extends CustomPainter {
  final CycleChart chart;

  CycleChartPainter({required this.chart});

  @override
  void paint(Canvas canvas, Size size) {
    final points = chart.points;
    if (points.length < 2) return;
    const leftPad = 38.0;
    const bottomPad = 18.0;
    const topPad = 8.0;
    final plotWidth = size.width - leftPad - 6;
    final plotHeight = size.height - bottomPad - topPad;
    final first = points.first.date.millisecondsSinceEpoch.toDouble();
    final last = points.last.date.millisecondsSinceEpoch.toDouble();
    final span = math.max(1.0, last - first);
    final prices = points.map((p) => p.price).where((p) => p > 0).toList();
    final minLog = math.log(prices.reduce(math.min)) / math.ln10;
    final maxLog = math.log(prices.reduce(math.max)) / math.ln10;
    final logSpan = math.max(0.3, maxLog - minLog);

    double dx(DateTime when) =>
        leftPad + ((when.millisecondsSinceEpoch - first) / span).clamp(0.0, 1.0) * plotWidth;
    double dy(double price) {
      final value = math.log(math.max(price, 0.01)) / math.ln10;
      return topPad + (1 - (value - minLog) / logSpan).clamp(0.0, 1.0) * plotHeight;
    }

    // Phase bands: the whole history, coloured by what the engine measured.
    // Neighbouring stretches of the same colour are drawn as one band, and a
    // very short stretch joins the one before it: the chart shows the shape of
    // the cycles, not every hesitation of the classifier.
    for (final band in mergedBands(chart.phases)) {
      final left = dx(band.start);
      final right = dx(band.end);
      if (right <= left) continue;
      canvas.drawRect(
        Rect.fromLTRB(left, topPad, right, topPad + plotHeight),
        Paint()..color = phaseColor(band.tone).withValues(alpha: .18),
      );
    }

    // Decade grid lines, labelled in dollars.
    final gridPaint = Paint()
      ..color = const Color(0xFF1D3853)
      ..strokeWidth = 0.6;
    for (var power = minLog.floor(); power <= maxLog.ceil(); power++) {
      final y = dy(math.pow(10, power).toDouble());
      if (y < topPad || y > topPad + plotHeight) continue;
      canvas.drawLine(Offset(leftPad, y), Offset(size.width - 6, y), gridPaint);
      _label(canvas, _shortPrice(math.pow(10, power).toDouble()), Offset(2, y - 6),
          const Color(0xFF6F86A6), 9);
    }

    // Halvings, as vertical marks with their own symbol.
    for (final halving in chart.halvings) {
      if (halving.estimated) continue;
      final x = dx(halving.date);
      final paint = Paint()
        ..color = Colors.white.withValues(alpha: .35)
        ..strokeWidth = 1;
      for (double y = topPad; y < topPad + plotHeight; y += 6) {
        canvas.drawLine(Offset(x, y), Offset(x, y + 3), paint);
      }
      _label(canvas, '⚡', Offset(x - 5, topPad - 2), Colors.white, 10);
    }

    // The price itself.
    final path = Path();
    for (var i = 0; i < points.length; i++) {
      final offset = Offset(dx(points[i].date), dy(points[i].price));
      i == 0 ? path.moveTo(offset.dx, offset.dy) : path.lineTo(offset.dx, offset.dy);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4,
    );

    // Records and confirmed bottoms: a few marks, never a wall of labels.
    for (final marker in chart.annotations) {
      if (marker.kind != 'ATH' && marker.kind != 'BOTTOM') continue;
      if (marker.price == null) continue;
      final centre = Offset(dx(marker.date), dy(marker.price!));
      canvas.drawCircle(
        centre,
        2.6,
        Paint()..color = marker.kind == 'ATH' ? _phaseGreen : _phaseRed,
      );
      _label(canvas, marker.kind == 'ATH' ? '🏆' : '🔻',
          centre.translate(-5, marker.kind == 'ATH' ? -16 : 4), Colors.white, 10);
    }

    // Today: the line continues to the live price and says so.
    final todayX = dx(chart.todayDate);
    final todayY = dy(chart.todayPrice);
    canvas.drawLine(
      Offset(todayX, topPad),
      Offset(todayX, topPad + plotHeight),
      Paint()
        ..color = mobileBlue.withValues(alpha: .8)
        ..strokeWidth = 1.2,
    );
    canvas.drawCircle(Offset(todayX, todayY), 4, Paint()..color = mobileBlue);
    canvas.drawCircle(
      Offset(todayX, todayY),
      4,
      Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2,
    );
    _label(canvas, '📍', Offset(todayX - 6, topPad + plotHeight + 2), Colors.white, 11);

    // Years along the bottom, sparsely.
    final firstYear = points.first.date.year;
    final lastYear = points.last.date.year;
    final stepYears = (lastYear - firstYear) > 10 ? 3 : 2;
    for (var year = firstYear + 1; year <= lastYear; year += stepYears) {
      final x = dx(DateTime(year));
      _label(canvas, '$year', Offset(x - 12, topPad + plotHeight + 3),
          const Color(0xFF6F86A6), 9);
    }
  }

  void _label(Canvas canvas, String text, Offset at, Color color, double size) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: TextStyle(color: color, fontSize: size)),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, at);
  }

  String _shortPrice(double value) {
    if (value >= 1000) return '${_fr(value / 1000)}k\$';
    return '${_fr(value)}\$';
  }

  @override
  bool shouldRepaint(covariant CycleChartPainter oldDelegate) => oldDelegate.chart != chart;
}

class _WhyCard extends StatelessWidget {
  final CycleRead cycle;

  const _WhyCard({required this.cycle});

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: const ValueKey('cycle-why'),
        borderColor: const Color(0xFF2B669B),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '🔎 Pourquoi ${cycle.phaseLabel.toLowerCase()} ?',
              style: const TextStyle(
                  color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            for (final reason in cycle.reasons.take(3))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Text(
                  reason,
                  style: const TextStyle(
                      color: Color(0xFFE6EEF9), fontSize: 13.5, height: 1.35),
                ),
              ),
          ],
        ),
      );
}

class _NextStepCard extends StatelessWidget {
  final CycleRead cycle;

  const _NextStepCard({required this.cycle});

  @override
  Widget build(BuildContext context) {
    final step = cycle.nextStep;
    return GlassPanel(
      key: const ValueKey('cycle-next-step'),
      borderColor: const Color(0xFF26405E),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '🎯 Prochaine étape',
            style: TextStyle(
                color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          Text(
            'Pour passer de ${cycle.phaseEmoji} ${cycle.phaseLabel} '
            'à ${step.toEmoji} ${step.toLabel} :',
            style: const TextStyle(color: mobileMuted, fontSize: 12.5),
          ),
          const SizedBox(height: 8),
          for (final condition in step.conditions)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text(condition,
                  style: const TextStyle(
                      color: Color(0xFFE6EEF9), fontSize: 13, height: 1.35)),
            ),
          if (step.candidateLabel != null) ...[
            const SizedBox(height: 8),
            Text(
              '⏳ Phase candidate : ${step.candidateLabel} '
              '(confirmation ${step.candidateProgress})',
              key: const ValueKey('cycle-candidate'),
              style: const TextStyle(color: Colors.white, fontSize: 12.5),
            ),
          ],
          const SizedBox(height: 10),
          const Divider(height: 1, color: Color(0xFF1D3853)),
          const SizedBox(height: 10),
          Text(
            '❌ Invalidation — ${step.invalidation} Le marché repasserait vers '
            '${step.invalidationEmoji} ${step.invalidationLabel}.',
            style: const TextStyle(
                color: Color(0xFFD5E1F2), fontSize: 12.5, height: 1.35),
          ),
        ],
      ),
    );
  }
}

/// The archive: what the analysis said each month, kept as it was said.
class _SnapshotsCard extends StatelessWidget {
  final List<CycleSnapshotRead> snapshots;

  const _SnapshotsCard({required this.snapshots});

  @override
  Widget build(BuildContext context) {
    if (snapshots.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('cycle-snapshots'),
      borderColor: const Color(0xFF26405E),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '📅 Historique mensuel',
            style: TextStyle(
                color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 4),
          const Text(
            'Chaque mois est conservé tel qu’il a été écrit.',
            style: TextStyle(color: mobileMuted, fontSize: 11.5),
          ),
          const SizedBox(height: 8),
          for (var i = 0; i < math.min(snapshots.length, 8); i++) ...[
            if (i > 0) const Divider(height: 1, color: Color(0xFF1D3853)),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 9),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          snapshots[i].monthLabel.toUpperCase(),
                          style: const TextStyle(
                            color: Color(0xFF8FA8C4),
                            fontSize: 11,
                            letterSpacing: .6,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                      Text(
                        '${snapshots[i].phaseEmoji} ${snapshots[i].phaseLabel}',
                        style: TextStyle(
                          color: phaseColor(_toneOf(snapshots[i].phase)),
                          fontSize: 13,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(snapshots[i].notes,
                      style: const TextStyle(
                          color: Color(0xFFD5E1F2), fontSize: 12.5, height: 1.3)),
                  if (snapshots[i].changes.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(snapshots[i].changes.join(' · '),
                        style: const TextStyle(color: mobileMuted, fontSize: 11.5)),
                  ],
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

String _toneOf(String phase) => switch (phase) {
      'EXPANSION' => 'GREEN',
      'PRICE_DISCOVERY' => 'FIRE',
      'RECOVERY' || 'ACCUMULATION' => 'BLUE',
      'TRANSITION' || 'DISTRIBUTION_POSSIBLE' => 'ORANGE',
      'BEAR_MARKET' || 'DEEP_DRAWDOWN' => 'RED',
      _ => 'WHITE',
    };

/// Previous cycles, measured on the same bars - and labelled as history.
class _PreviousCyclesCard extends StatelessWidget {
  final CycleRead cycle;

  const _PreviousCyclesCard({required this.cycle});

  @override
  Widget build(BuildContext context) => GlassPanel(
        key: const ValueKey('cycle-previous'),
        borderColor: const Color(0xFF26405E),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '📚 Cycles précédents',
              style: TextStyle(
                  color: Colors.white, fontSize: 17, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),
            for (final stats in cycle.cycles) ...[
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 7),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '⚡ ${stats.name}${stats.ongoing ? ' (en cours)' : ''}',
                            style: const TextStyle(
                                color: Colors.white,
                                fontSize: 14,
                                fontWeight: FontWeight.w800),
                          ),
                        ),
                        if (stats.daysToAth != null)
                          Text('sommet à +${stats.daysToAth} j',
                              style: const TextStyle(color: mobileMuted, fontSize: 11.5)),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      [
                        if (stats.gainPct != null) 'amplitude ${_signed(stats.gainPct!)}',
                        if (stats.drawdownPct != null)
                          'repli ${_signed(stats.drawdownPct!)}',
                        if (stats.bearDays != null) 'baisse ${stats.bearDays} j',
                        if (stats.recoveryDays != null)
                          'récupération ${stats.recoveryDays} j',
                      ].join(' · '),
                      style: const TextStyle(color: Color(0xFFD5E1F2), fontSize: 12.5),
                    ),
                    if (stats.ongoing)
                      const Text(
                        'Creux non confirmé : seul un sommet ultérieur le confirmerait.',
                        style: TextStyle(color: mobileMuted, fontSize: 11.5),
                      ),
                  ],
                ),
              ),
              const Divider(height: 1, color: Color(0xFF1D3853)),
            ],
            const SizedBox(height: 10),
            const Text(
              '📚 Comparaison normalisée — 100 au jour du halving',
              style: TextStyle(
                  color: Colors.white, fontSize: 13.5, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 150,
              child: CustomPaint(
                size: Size.infinite,
                painter: NormalisedCyclesPainter(cycles: cycle.normalised),
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 10,
              runSpacing: 4,
              children: [
                for (var i = 0; i < cycle.normalised.length; i++)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 10,
                        height: 3,
                        color: NormalisedCyclesPainter.colours[
                            i % NormalisedCyclesPainter.colours.length],
                      ),
                      const SizedBox(width: 5),
                      Text(
                        cycle.normalised[i].name +
                            (cycle.normalised[i].ongoing ? ' (en cours)' : ''),
                        style: const TextStyle(color: mobileMuted, fontSize: 11),
                      ),
                    ],
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              cycle.disclaimer,
              key: const ValueKey('cycle-disclaimer'),
              style: const TextStyle(color: mobileMuted, fontSize: 11.5, height: 1.3),
            ),
          ],
        ),
      );
}

class NormalisedCyclesPainter extends CustomPainter {
  static const colours = [
    Color(0xFF6F86A6),
    Color(0xFF9B8CFF),
    Color(0xFF4FA8FF),
    Color(0xFF55DD8B),
  ];

  final List<NormalisedCycle> cycles;

  NormalisedCyclesPainter({required this.cycles});

  @override
  void paint(Canvas canvas, Size size) {
    if (cycles.isEmpty) return;
    const leftPad = 30.0;
    const bottomPad = 14.0;
    final plotWidth = size.width - leftPad - 6;
    final plotHeight = size.height - bottomPad;
    final maxDay = cycles
        .expand((c) => c.points)
        .fold<int>(1, (value, point) => math.max(value, point.day));
    final maxIndex = cycles
        .expand((c) => c.points)
        .fold<double>(120, (value, point) => math.max(value, point.index));
    final maxLog = math.log(maxIndex) / math.ln10;
    const minLog = 1.4; // index 25: below that the comparison says little

    double dx(int day) => leftPad + (day / maxDay).clamp(0.0, 1.0) * plotWidth;
    double dy(double index) {
      final value = math.log(math.max(index, 1)) / math.ln10;
      return (1 - ((value - minLog) / (maxLog - minLog)).clamp(0.0, 1.0)) * plotHeight;
    }

    final gridPaint = Paint()
      ..color = const Color(0xFF1D3853)
      ..strokeWidth = 0.6;
    for (final level in [100.0, 1000.0, 10000.0]) {
      if (level > maxIndex * 1.2) continue;
      final y = dy(level);
      canvas.drawLine(Offset(leftPad, y), Offset(size.width - 6, y), gridPaint);
      final painter = TextPainter(
        text: TextSpan(
          text: level >= 1000 ? '×${(level / 100).round()}' : '100',
          style: const TextStyle(color: Color(0xFF6F86A6), fontSize: 9),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      painter.paint(canvas, Offset(2, y - 6));
    }

    for (var i = 0; i < cycles.length; i++) {
      final colour = colours[i % colours.length];
      final path = Path();
      var started = false;
      for (final point in cycles[i].points) {
        final offset = Offset(dx(point.day), dy(point.index));
        if (!started) {
          path.moveTo(offset.dx, offset.dy);
          started = true;
        } else {
          path.lineTo(offset.dx, offset.dy);
        }
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = cycles[i].ongoing ? colour : colour.withValues(alpha: .65)
          ..style = PaintingStyle.stroke
          ..strokeWidth = cycles[i].ongoing ? 2 : 1.2,
      );
    }
  }

  @override
  bool shouldRepaint(covariant NormalisedCyclesPainter oldDelegate) =>
      oldDelegate.cycles != cycles;
}
