/// « 🌍 Pourquoi le marché bouge ? » - the five macro drivers on the home,
/// the fifteen behind them, and one driver in full.
///
/// Two scales are kept apart everywhere in this file: how much a driver
/// deserves attention (a score, an « attention » level) and which way it
/// points (a direction). An important driver can point nowhere yet, and the
/// page says so rather than filling the gap.
library;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/client.dart';
import '../api/macro_models.dart';
import 'color_emoji.dart';
import 'mobile_kit.dart';

const _muted = Color(0xFF9FB3CC);
const _white = Color(0xFFE6EEF9);
const _divider = Color(0xFF1D3853);

Color directionColor(String direction) => switch (direction) {
      'FAVORABLE' => const Color(0xFF3FB950),
      'UNFAVORABLE' => const Color(0xFFF85149),
      'MIXED' => const Color(0xFFE3C35A),
      'UNKNOWN' => const Color(0xFF6FA8DC),
      _ => _white,
    };

String _hhmm(DateTime? when) => when == null
    ? ''
    : '${when.hour.toString().padLeft(2, '0')}:'
        '${when.minute.toString().padLeft(2, '0')}';

String _dateTime(DateTime? when) {
  if (when == null) return 'Non fournie par la source';
  String two(int value) => value.toString().padLeft(2, '0');
  return '${two(when.day)}/${two(when.month)}/${when.year} · ${_hhmm(when)}';
}

/// One row: the driver, what it does to risk assets, and how much it weighs.
class MacroDriverRow extends StatelessWidget {
  final MacroDriver driver;
  final VoidCallback? onTap;
  final bool showScore;

  const MacroDriverRow(
      {super.key, required this.driver, this.onTap, this.showScore = true});

  @override
  Widget build(BuildContext context) {
    final (emoji, label) = driver.directionLabel;
    final color = directionColor(driver.direction);
    return InkWell(
      key: ValueKey('macro-driver-${driver.key}'),
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 11),
        child: Row(
          children: [
            SizedBox(
                width: 30, child: ColorEmoji(emoji: driver.emoji, size: 20)),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(driver.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  // What it does to risk assets, then what the driver itself
                  // is doing - on two lines, because one phone line cuts the
                  // second half of « Pression · Rendements en hausse ».
                  Row(children: [
                    ColorEmoji(emoji: emoji, size: 12),
                    const SizedBox(width: 5),
                    Flexible(
                      child: Text(driver.available ? label : driver.state,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              color: color,
                              fontSize: 12.5,
                              fontWeight: FontWeight.w700)),
                    ),
                  ]),
                  if (driver.available && driver.state.isNotEmpty)
                    Text(driver.state,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: _muted, fontSize: 12)),
                ],
              ),
            ),
            if (showScore && driver.available) ...[
              const SizedBox(width: 8),
              // The weight, not a probability: how much this driver explains
              // the current regime compared with the other fourteen.
              Text('${driver.importance}/100',
                  key: ValueKey('macro-score-${driver.key}'),
                  style: const TextStyle(
                      color: _muted,
                      fontSize: 12,
                      fontWeight: FontWeight.w700)),
            ],
            if (onTap != null)
              const Icon(Icons.chevron_right_rounded,
                  size: 20, color: Color(0xFF4E7CB5)),
          ],
        ),
      ),
    );
  }
}

/// The home block: five drivers, the hour of the reading, and the way in.
class MacroDriversCard extends StatelessWidget {
  final MacroRadarRead radar;
  final ApiClient client;

  const MacroDriversCard(
      {super.key, required this.radar, required this.client});

  @override
  Widget build(BuildContext context) {
    if (radar.top.isEmpty) return const SizedBox.shrink();
    return GlassPanel(
      key: const ValueKey('macro-drivers'),
      borderColor: const Color(0xFF245E90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const ColorEmoji(emoji: '🌍', size: 18),
            const SizedBox(width: 8),
            const Expanded(
              child: Text('Pourquoi le marché bouge ?',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: 19,
                      fontWeight: FontWeight.w800)),
            ),
          ]),
          const SizedBox(height: 4),
          for (var i = 0; i < radar.top.length; i++) ...[
            if (i > 0) const Divider(height: 1, color: _divider),
            MacroDriverRow(
              driver: radar.top[i],
              onTap: () => MacroDriverPage.open(context, radar.top[i], client),
            ),
          ],
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: Text(
                  [
                    if (radar.asOf != null) 'Actualisé à ${_hhmm(radar.asOf)}',
                    if (radar.nextCheck != null)
                      'prochaine vérification ${_hhmm(radar.nextCheck)}',
                  ].join(' · '),
                  style: const TextStyle(color: _muted, fontSize: 11.5)),
            ),
          ]),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              key: const ValueKey('macro-see-all'),
              onPressed: () => MacroDriversPage.open(context, radar, client),
              style: TextButton.styleFrom(foregroundColor: mobileBlue),
              child: Text('Voir les ${radar.watched} moteurs ›'),
            ),
          ),
        ],
      ),
    );
  }
}

/// The fifteen, in order of importance, with what changed since the last cycle.
class MacroDriversPage extends StatelessWidget {
  final MacroRadarRead radar;
  final ApiClient client;

  const MacroDriversPage(
      {super.key, required this.radar, required this.client});

  static Future<void> open(
          BuildContext context, MacroRadarRead radar, ApiClient client) =>
      Navigator.of(context).push(MaterialPageRoute<void>(
        settings: const RouteSettings(name: '/macro/moteurs'),
        builder: (_) => MacroDriversPage(radar: radar, client: client),
      ));

  @override
  Widget build(BuildContext context) {
    final unavailable = radar.drivers.where((d) => !d.available).toList();
    final measured = radar.drivers.where((d) => d.available).toList();
    return Scaffold(
      backgroundColor: const Color(0xFF061525),
      appBar: AppBar(
        backgroundColor: const Color(0xFF061525),
        title: const Text('🌍 Moteurs du marché'),
      ),
      body: MobileScrollView(
        key: const ValueKey('macro-drivers-page'),
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 40),
        children: [
          if (radar.summary.isNotEmpty)
            GlassPanel(
              child: Text(radar.summary,
                  style: const TextStyle(
                      color: _white, fontSize: 14.5, height: 1.5)),
            ),
          if (radar.changes.isNotEmpty) ...[
            const SizedBox(height: 14),
            GlassPanel(
              key: const ValueKey('macro-changes'),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Depuis la vérification précédente',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w800)),
                  for (final change in radar.changes)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                          '${change.emoji} ${change.name} : '
                          '${change.fromState} → ${change.toState}',
                          style: const TextStyle(
                              color: _white, fontSize: 13, height: 1.35)),
                    ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 14),
          GlassPanel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (var i = 0; i < measured.length; i++) ...[
                  if (i > 0) const Divider(height: 1, color: _divider),
                  MacroDriverRow(
                    driver: measured[i],
                    onTap: () =>
                        MacroDriverPage.open(context, measured[i], client),
                  ),
                ],
              ],
            ),
          ),
          if (unavailable.isNotEmpty) ...[
            const SizedBox(height: 14),
            GlassPanel(
              key: const ValueKey('macro-unavailable'),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Surveillés, sans source branchée',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w800)),
                  const SizedBox(height: 2),
                  // Declared rather than hidden: a driver nobody measures is
                  // not a driver that pushes nowhere.
                  for (final driver in unavailable)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                          '${driver.emoji} ${driver.name} — ${driver.unavailableReason}',
                          style: const TextStyle(
                              color: _muted, fontSize: 12.5, height: 1.35)),
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

/// One driver in full: its figures, why it matters, what comes next.
class MacroDriverPage extends StatelessWidget {
  final MacroDriver driver;
  final ApiClient client;

  const MacroDriverPage(
      {super.key, required this.driver, required this.client});

  static Future<void> open(
          BuildContext context, MacroDriver driver, ApiClient client) =>
      Navigator.of(context).push(MaterialPageRoute<void>(
        settings: RouteSettings(name: '/macro/${driver.key}'),
        builder: (_) => MacroDriverPage(driver: driver, client: client),
      ));

  static const _label = TextStyle(
      color: _muted,
      fontSize: 12,
      letterSpacing: .5,
      fontWeight: FontWeight.w800);

  @override
  Widget build(BuildContext context) {
    final (emoji, label) = driver.directionLabel;
    return Scaffold(
      backgroundColor: const Color(0xFF061525),
      appBar: AppBar(
        backgroundColor: const Color(0xFF061525),
        title: Text('${driver.emoji} ${driver.name}'),
      ),
      body: MobileScrollView(
        key: ValueKey('macro-driver-page-${driver.key}'),
        padding: const EdgeInsets.fromLTRB(18, 10, 18, 40),
        children: [
          // Attention and direction, side by side and never merged. They
          // wrap rather than overflow: « Sens inconnu » beside « Attention
          // critique · 94/100 » does not fit one phone line.
          Wrap(
            spacing: 10,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Row(mainAxisSize: MainAxisSize.min, children: [
                ColorEmoji(emoji: emoji, size: 16),
                const SizedBox(width: 6),
                Text(label,
                    style: TextStyle(
                        color: directionColor(driver.direction),
                        fontSize: 15,
                        fontWeight: FontWeight.w800)),
              ]),
              Text('${driver.attentionLabel} · ${driver.importance}/100',
                  style: const TextStyle(color: _muted, fontSize: 12.5)),
            ],
          ),
          const SizedBox(height: 12),
          Text(driver.summary,
              key: const ValueKey('macro-driver-summary'),
              style:
                  const TextStyle(color: _white, fontSize: 14.5, height: 1.5)),
          if (driver.values.isNotEmpty) ...[
            const SizedBox(height: 18),
            const Text('VALEURS CLÉS', style: _label),
            for (final value in driver.values)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(
                        child: Text(value.label,
                            style:
                                const TextStyle(color: _white, fontSize: 13.5)),
                      ),
                      Text(
                          [
                            value.value,
                            if (value.change.isNotEmpty) value.change
                          ].join('  '),
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13.5,
                              fontWeight: FontWeight.w700)),
                    ]),
                    if (value.period.isNotEmpty || value.source.isNotEmpty)
                      Text(
                          [
                            if (value.period.isNotEmpty) value.period,
                            if (value.source.isNotEmpty) value.source,
                          ].join(' · '),
                          style:
                              const TextStyle(color: _muted, fontSize: 11.5)),
                  ],
                ),
              ),
          ],
          const SizedBox(height: 18),
          const Text('FRAÎCHEUR ET QUALITÉ', style: _label),
          const SizedBox(height: 6),
          Text('Dernière observation · ${_dateTime(driver.lastObservationAt)}',
              key: const ValueKey('macro-driver-observation-time'),
              style: const TextStyle(color: Colors.white, fontSize: 13)),
          Text('Publication source · ${_dateTime(driver.lastPublicationAt)}',
              key: const ValueKey('macro-driver-publication-time'),
              style: const TextStyle(color: _muted, fontSize: 12.5)),
          Text(
              [
                if (driver.signalId.isNotEmpty) driver.signalId,
                if (driver.releaseFrequency.isNotEmpty)
                  driver.releaseFrequency.replaceAll('_', ' ').toLowerCase(),
                driver.dataQuality,
              ].join(' · '),
              style: const TextStyle(color: _muted, fontSize: 12.5)),
          if (driver.historicalPercentile case final percentile?)
            Text('Percentile historique · ${(percentile * 100).round()}e',
                style: const TextStyle(color: _muted, fontSize: 12.5)),
          if (driver.sourceUrl.isNotEmpty) ...[
            const SizedBox(height: 6),
            TextButton.icon(
              key: const ValueKey('macro-driver-source-link'),
              onPressed: () => launchUrl(Uri.parse(driver.sourceUrl),
                  mode: LaunchMode.externalApplication),
              icon: const Icon(Icons.open_in_new, size: 15),
              label: const Text('Ouvrir la source officielle'),
            ),
          ],
          if (driver.historicalSeries.length >= 2) ...[
            const SizedBox(height: 16),
            const Text('HISTORIQUE DE LA SÉRIE DE RÉFÉRENCE', style: _label),
            const SizedBox(height: 8),
            SizedBox(
              key: const ValueKey('macro-driver-history-chart'),
              height: 92,
              width: double.infinity,
              child: CustomPaint(
                painter: _MacroHistoryPainter(driver.historicalSeries),
              ),
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_dateTime(driver.historicalSeries.first.observationTime),
                    style: const TextStyle(color: _muted, fontSize: 10.5)),
                Text(_dateTime(driver.historicalSeries.last.observationTime),
                    style: const TextStyle(color: _muted, fontSize: 10.5)),
              ],
            ),
          ],
          const SizedBox(height: 18),
          const Text('POURQUOI CELA COMPTE', style: _label),
          Text(driver.channel,
              style: const TextStyle(
                  color: Colors.white, fontSize: 14, height: 1.45)),
          if (driver.watching.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('CE QUE NOUS SURVEILLONS', style: _label),
            Text(driver.watching,
                style: const TextStyle(
                    color: Colors.white, fontSize: 14, height: 1.45)),
          ],
          if (driver.nextRelease != null) ...[
            const SizedBox(height: 16),
            const Text('PROCHAINE PUBLICATION', style: _label),
            Text(
                '${driver.nextReleaseLabel} — '
                '${driver.nextRelease!.day}/${driver.nextRelease!.month} '
                'à ${_hhmm(driver.nextRelease)}',
                key: const ValueKey('macro-driver-next'),
                style: const TextStyle(
                    color: Colors.white, fontSize: 14, height: 1.45)),
          ],
          if (driver.importanceReasons.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('POURQUOI CE POIDS', style: _label),
            for (final reason in driver.importanceReasons)
              Text('• $reason',
                  style: const TextStyle(
                      color: _muted, fontSize: 12.5, height: 1.4)),
          ],
          if (driver.invalidationConditions.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('CE QUI INVALIDERAIT CETTE LECTURE', style: _label),
            for (final condition in driver.invalidationConditions)
              Text('• $condition',
                  style: const TextStyle(
                      color: _muted, fontSize: 12.5, height: 1.4)),
          ],
        ],
      ),
    );
  }
}

class _MacroHistoryPainter extends CustomPainter {
  final List<MacroHistoryPoint> points;

  const _MacroHistoryPainter(this.points);

  @override
  void paint(Canvas canvas, Size size) {
    final values = points.map((point) => point.value).toList(growable: false);
    final minimum = values.reduce((a, b) => a < b ? a : b);
    final maximum = values.reduce((a, b) => a > b ? a : b);
    final span = maximum == minimum ? 1.0 : maximum - minimum;
    final path = Path();
    for (var index = 0; index < values.length; index++) {
      final x =
          values.length == 1 ? 0.0 : size.width * index / (values.length - 1);
      final y = size.height - ((values[index] - minimum) / span * size.height);
      if (index == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = const Color(0xFF6FA8DC)
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _MacroHistoryPainter oldDelegate) =>
      oldDelegate.points != points;
}
