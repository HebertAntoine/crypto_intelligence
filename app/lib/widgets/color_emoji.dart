import 'package:flutter/material.dart';

/// Lightweight emoji renderer safe for long, scrolling Flutter web pages.
///
/// Apple platforms use their native colour glyph whenever Flutter exposes the
/// system font. Canvas renderers that only expose a monochrome glyph receive a
/// semantic colour, so no icon falls back to the previous white outline.
class ColorEmoji extends StatelessWidget {
  final String emoji;
  final double size;
  final Color? color;

  const ColorEmoji({
    super.key,
    required this.emoji,
    this.size = 22,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final tone = color ?? _emojiTone(emoji);
    return SizedBox.square(
      dimension: size * 1.22,
      child: Center(
        child: Text(
          emoji,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: tone,
            fontSize: size,
            height: 1,
            fontFamily: 'Apple Color Emoji',
            fontFamilyFallback: const [
              'Noto Color Emoji',
              'Segoe UI Emoji',
            ],
            shadows: [
              Shadow(
                color: tone.withValues(alpha: .22),
                blurRadius: 5,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Color _emojiTone(String emoji) => switch (emoji) {
      '🏦' => const Color(0xFFFF6676),
      '📉' || '🔴' => const Color(0xFFFF5B68),
      '👥' || '🐋' || '🔍' || '🔎' || '🔄' => const Color(0xFF55A7FF),
      '🛢️' => const Color(0xFFFF813D),
      '📈' || '🟢' || '⬆️' => const Color(0xFF51E58C),
      '🪙' || '💡' || '⚖️' => const Color(0xFFFFC342),
      '📊' || '🎯' => const Color(0xFF8C7CFF),
      '⚠️' => const Color(0xFFFF6676),
      '🗓️' || '📅' => const Color(0xFF61A8FF),
      _ => const Color(0xFF61A8FF),
    };
