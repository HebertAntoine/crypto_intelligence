/// Shared widgets.
///
/// `EdgeBadge` is the most important one: it is the only place that decides
/// how an edge verdict looks, so a measured edge and an unmeasured one can
/// never be styled alike by accident somewhere else in the app.
library;
import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme/app_theme.dart';

class EdgeBadge extends StatelessWidget {
  final EdgeState state;
  final bool compact;

  const EdgeBadge({super.key, required this.state, this.compact = false});

  Color get _color => switch (state) {
        EdgeState.positiveEdge => AppColors.measured,
        EdgeState.negativeEdge => AppColors.bad,
        EdgeState.noMeasurableEdge => AppColors.warn,
        EdgeState.unstable => AppColors.warn,
        _ => AppColors.textMuted,
      };

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 6 : 9, vertical: compact ? 2 : 4),
      decoration: BoxDecoration(
        color: _color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: _color.withValues(alpha: 0.55)),
      ),
      child: Text(
        state.label,
        style: TextStyle(
          color: _color,
          fontSize: compact ? 10.5 : 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class StatePill extends StatelessWidget {
  final String label;
  final Color? color;
  final bool compact;

  const StatePill({super.key, required this.label, this.color, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final tone = color ?? AppColors.accent;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 6 : 9, vertical: compact ? 2 : 4),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: tone.withValues(alpha: 0.45)),
      ),
      child: Text(
        label.replaceAll('_', ' '),
        style: TextStyle(
          color: tone,
          fontSize: compact ? 10.5 : 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class SectionCard extends StatelessWidget {
  final String title;
  final Widget child;
  final String? subtitle;
  final Widget? trailing;

  const SectionCard({
    super.key,
    required this.title,
    required this.child,
    this.subtitle,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.4,
                      color: AppColors.textMuted,
                    ),
                  ),
                ),
                if (trailing != null) trailing!,
              ],
            ),
            if (subtitle != null) ...[
              const SizedBox(height: 4),
              Text(
                subtitle!,
                style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
              ),
            ],
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }
}

class LabelledRow extends StatelessWidget {
  final String label;
  final Widget value;

  const LabelledRow({super.key, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 132,
            child: Text(
              label,
              style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
            ),
          ),
          Expanded(child: DefaultTextStyle.merge(style: const TextStyle(fontSize: 12.5), child: value)),
        ],
      ),
    );
  }
}

class LoadingView extends StatelessWidget {
  final String what;

  const LoadingView({super.key, required this.what});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          const SizedBox(height: 14),
          Text(
            'Chargement : $what...',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 12.5),
          ),
        ],
      ),
    );
  }
}

class ErrorView extends StatelessWidget {
  final Object error;
  final VoidCallback? onRetry;

  const ErrorView({super.key, required this.error, this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.cloud_off, color: AppColors.textMuted, size: 32),
            const SizedBox(height: 12),
            const Text(
              'Données indisponibles',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Text(
              '$error',
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
            const SizedBox(height: 8),
            const Text(
              'Rien n’est inventé : l’app affiche les données backend ou le snapshot intégré disponible.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textMuted, fontSize: 11, fontStyle: FontStyle.italic),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              OutlinedButton(onPressed: onRetry, child: const Text('Réessayer')),
            ],
          ],
        ),
      ),
    );
  }
}

/// Renders an absent value as an explicit state rather than a blank or a zero.
class UnavailableText extends StatelessWidget {
  final String reason;

  const UnavailableText({super.key, this.reason = 'INDISPONIBLE'});

  @override
  Widget build(BuildContext context) => Text(
        reason,
        style: const TextStyle(color: AppColors.textMuted, fontSize: 12, fontStyle: FontStyle.italic),
      );
}

String fmt(double? value, {int digits = 2, String suffix = ''}) {
  if (value == null || value.isNaN) return '—';
  return '${value.toStringAsFixed(digits)}$suffix';
}

String fmtSigned(double? value, {int digits = 2, String suffix = '%'}) {
  if (value == null || value.isNaN) return '—';
  final sign = value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(digits)}$suffix';
}
