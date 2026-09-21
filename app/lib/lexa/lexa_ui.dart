/// Shared pieces of the 🎬 Lexa tab, in the Home's visual language:
/// blue-black panels, blue borders, big white titles, colour emojis, and
/// every status written out next to its colour.
library;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../widgets/color_emoji.dart';
import '../widgets/mobile_kit.dart';
import 'lexa_models.dart';

const lexaGreen = Color(0xFF3FB950);
const lexaOrange = Color(0xFFF0A23B);
const lexaRed = Color(0xFFF85149);
const lexaBlue = Color(0xFF58A6FF);
const lexaWhite = Color(0xFFD3D9EF);
const lexaMuted = Color(0xFF9FB3CC);
const lexaDivider = Color(0xFF1D3853);

Color toneColor(String? tone) => switch (tone) {
      'GREEN' => lexaGreen,
      'ORANGE' => lexaOrange,
      'RED' => lexaRed,
      'BLUE' => lexaBlue,
      'BLACK' => const Color(0xFF8B949E),
      _ => lexaWhite,
    };

Color emojiColor(String emoji) => switch (emoji) {
      '🟢' => lexaGreen,
      '🟠' => lexaOrange,
      '🔴' => lexaRed,
      '🔵' => lexaBlue,
      _ => lexaWhite,
    };

const _months = [
  'JANV', 'FÉVR', 'MARS', 'AVR', 'MAI', 'JUIN', 'JUIL', 'AOÛT', 'SEPT', 'OCT',
  'NOV', 'DÉC' //
];

DateTime? parseIso(Object? value) {
  if (value is! String || value.isEmpty) return null;
  return DateTime.tryParse(value)?.toLocal();
}

String dayMonth(DateTime? d) =>
    d == null ? '—' : '${d.day} ${_months[d.month - 1]}';

String fmtDistance(num? pct) {
  if (pct == null) return '';
  final arrow = pct < 0 ? '↓' : '↑';
  return '$arrow ${pct.abs().toStringAsFixed(1).replaceAll('.', ',')} %';
}

/// « 🎬 Voir le passage 18:42 » — YouTube links jump to the second.
Uri? videoAt(String? url, int? seconds) {
  if (url == null || url.trim().isEmpty) return null;
  final uri = Uri.tryParse(url.trim());
  if (uri == null || seconds == null) return uri;
  final host = uri.host.toLowerCase();
  if (host.contains('youtube.com') || host.contains('youtu.be')) {
    return uri
        .replace(queryParameters: {...uri.queryParameters, 't': '${seconds}s'});
  }
  return uri;
}

String fmtTimestamp(int? seconds) {
  if (seconds == null) return '—';
  final h = seconds ~/ 3600, m = (seconds % 3600) ~/ 60, s = seconds % 60;
  String two(int v) => v.toString().padLeft(2, '0');
  return h > 0 ? '$h:${two(m)}:${two(s)}' : '${two(m)}:${two(s)}';
}

Future<void> openVideo(BuildContext context, String? url, int? seconds) async {
  final uri = videoAt(url, seconds);
  if (uri == null) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
            'Aucun lien vidéo enregistré. Ouvre la vidéo sur la plateforme Lexa.')));
    return;
  }
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}

/// Emojis inside Lexa sentences use the same colour fonts as [ColorEmoji]:
/// without this fallback a canvas renderer can draw them as white outlines.
class LexaEmojiFonts extends StatelessWidget {
  final Widget child;

  const LexaEmojiFonts({super.key, required this.child});

  @override
  Widget build(BuildContext context) => DefaultTextStyle.merge(
        style: const TextStyle(fontFamilyFallback: [
          'Apple Color Emoji',
          'Noto Color Emoji',
          'Segoe UI Emoji',
        ]),
        child: child,
      );
}

/// A button label whose emoji keeps its colour (buttons use their own font).
Widget lexaLabel(String text) {
  final m = RegExp(r'^(\S+)\s+(.*)$').firstMatch(text);
  final first = m?.group(1) ?? '';
  final isEmoji = first.runes.any((r) => r > 0x2300);
  if (m == null || !isEmoji) return Text(text);
  return Row(mainAxisSize: MainAxisSize.min, children: [
    ColorEmoji(emoji: first, size: 15),
    const SizedBox(width: 6),
    Flexible(child: Text(m.group(2)!)),
  ]);
}

class LexaSectionTitle extends StatelessWidget {
  final String emoji;
  final String text;
  final Widget? trailing;

  const LexaSectionTitle(
      {super.key, required this.emoji, required this.text, this.trailing});

  @override
  Widget build(BuildContext context) => Row(
        children: [
          ColorEmoji(emoji: emoji, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 19,
                    fontWeight: FontWeight.w800)),
          ),
          if (trailing != null) trailing!,
        ],
      );
}

/// The date column of « À surveiller »: day on top, month below.
class LexaDateBadge extends StatelessWidget {
  final DateTime? date;

  const LexaDateBadge({super.key, required this.date});

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 46,
        child: Column(
          children: [
            Text('${date?.day ?? '—'}',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 19,
                    height: 1,
                    fontWeight: FontWeight.w800)),
            const SizedBox(height: 3),
            Text(date == null ? '' : _months[date!.month - 1],
                style: const TextStyle(
                    color: lexaMuted,
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700)),
          ],
        ),
      );
}

/// A status is never a colour alone: emoji + words, in the colour.
class LexaStatusPill extends StatelessWidget {
  final String emoji;
  final String label;
  final bool big;

  const LexaStatusPill(
      {super.key, required this.emoji, required this.label, this.big = false});

  @override
  Widget build(BuildContext context) {
    final color = emojiColor(emoji);
    return Container(
      padding: EdgeInsets.symmetric(
          horizontal: big ? 14 : 10, vertical: big ? 8 : 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.85), width: 1.3),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          ColorEmoji(emoji: emoji, size: big ? 18 : 13),
          SizedBox(width: big ? 8 : 6),
          Flexible(
            child: Text(label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                    color: color,
                    fontSize: big ? 18 : 12.5,
                    fontWeight: FontWeight.w800)),
          ),
        ],
      ),
    );
  }
}

class LexaChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const LexaChip(
      {super.key,
      required this.label,
      required this.selected,
      required this.onTap});

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 7),
          decoration: BoxDecoration(
            color: selected
                ? mobileBlue.withValues(alpha: 0.20)
                : const Color(0xFF0E1A28),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
                color: selected ? mobileBlue : const Color(0xFF245386),
                width: 1.2),
          ),
          child: Text(label,
              style: TextStyle(
                  color: selected ? Colors.white : lexaWhite,
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w800 : FontWeight.w600)),
        ),
      );
}

class LexaLine extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;

  const LexaLine(this.label, this.value, {super.key, this.color});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
                child: Text(label,
                    style: const TextStyle(color: lexaMuted, fontSize: 13.5))),
            const SizedBox(width: 10),
            Flexible(
              child: Text(value,
                  textAlign: TextAlign.right,
                  style: TextStyle(
                      color: color ?? Colors.white,
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700)),
            ),
          ],
        ),
      );
}

Widget lexaNote(String text, {Color color = lexaMuted}) => Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(text,
          style: TextStyle(color: color, fontSize: 12.5, height: 1.35)),
    );

String priceOf(Object? v) => fmtPrice(v is num ? v.toDouble() : null);

String eurOf(Object? v) => fmtEur(v is num ? v.toDouble() : null);
