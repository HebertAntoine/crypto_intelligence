/// Runtime configuration.
///
/// The API base URL is injected at build time so the same source builds
/// against a local backend and a deployed one:
///
///   flutter build web --dart-define=API_BASE_URL=https://api.example.com
///
/// It has no default pointing at a real host on purpose. A build that forgets
/// the flag talks to its own origin, which fails loudly in the browser rather
/// than silently hitting someone else's server.
class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: '',
  );

  /// True when the app was built without an explicit backend.
  static bool get usesSameOrigin => apiBaseUrl.isEmpty;

  static const String appName = 'Crypto Intelligence';

  /// Shown wherever the app could be mistaken for a trading tool.
  static const String disclaimer =
      'Analysis only. This app never places orders and gives no financial advice.';
}
