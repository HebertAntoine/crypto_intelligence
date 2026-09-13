// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter

import 'dart:html' as html;
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';

/// Renders through the browser instead of CanvasKit so Safari can use the
/// native Apple colour glyphs installed on iPhone and iPad.
class ColorEmoji extends StatefulWidget {
  final String emoji;
  final double size;

  const ColorEmoji({
    super.key,
    required this.emoji,
    this.size = 22,
  });

  @override
  State<ColorEmoji> createState() => _ColorEmojiState();
}

class _ColorEmojiState extends State<ColorEmoji> {
  static var _nextView = 0;
  late String _viewType;

  @override
  void initState() {
    super.initState();
    _registerView();
  }

  @override
  void didUpdateWidget(covariant ColorEmoji oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.emoji != widget.emoji || oldWidget.size != widget.size) {
      _registerView();
    }
  }

  void _registerView() {
    _viewType = 'native-color-emoji-${_nextView++}';
    final emoji = widget.emoji;
    final size = widget.size;
    ui_web.platformViewRegistry.registerViewFactory(
      _viewType,
      (viewId) => html.DivElement()
        ..setAttribute('aria-label', emoji)
        ..text = emoji
        ..style.setProperty('display', 'flex')
        ..style.setProperty('align-items', 'center')
        ..style.setProperty('justify-content', 'center')
        ..style.setProperty('width', '100%')
        ..style.setProperty('height', '100%')
        ..style.setProperty('overflow', 'hidden')
        ..style.setProperty('font-size', '${size}px')
        ..style.setProperty('line-height', '1')
        ..style.setProperty('font-variant-emoji', 'emoji')
        ..style.setProperty(
          'font-family',
          '"Apple Color Emoji", "Noto Color Emoji", "Segoe UI Emoji", '
              'sans-serif',
        ),
    );
  }

  @override
  Widget build(BuildContext context) => SizedBox.square(
        dimension: widget.size * 1.22,
        child: HtmlElementView(
          key: ValueKey(_viewType),
          viewType: _viewType,
        ),
      );
}
