{{flutter_js}}
{{flutter_build_config}}

// Colour emoji. Flutter web draws text itself and cannot reach the system's
// Apple Color Emoji font; by default it falls back to a monochrome emoji font
// to save a download, which is why every 🛒 ⏳ 🏦 on the home rendered as a
// tinted outline on iPhone. The icons on this app are emoji by design, so the
// colour font is worth its weight.
_flutter.loader.load({
  config: {
    useColorEmoji: true,
  },
});
