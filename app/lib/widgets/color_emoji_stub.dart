import 'package:flutter/material.dart';

/// Uses the operating system's native colour emoji font on mobile platforms.
class ColorEmoji extends StatelessWidget {
  final String emoji;
  final double size;

  const ColorEmoji({
    super.key,
    required this.emoji,
    this.size = 22,
  });

  @override
  Widget build(BuildContext context) => SizedBox.square(
        dimension: size * 1.22,
        child: Center(
          child: Text(
            emoji,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: size,
              height: 1,
              fontFamily: 'Apple Color Emoji',
              fontFamilyFallback: const [
                'Noto Color Emoji',
                'Segoe UI Emoji',
              ],
            ),
          ),
        ),
      );
}
