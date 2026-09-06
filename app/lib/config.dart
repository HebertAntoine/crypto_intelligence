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

  /// Embedded snapshots let the Vercel build work without a public API.
  ///
  /// When API_BASE_URL is provided the live backend remains the source of
  /// truth. When it is empty, the client first tries same-origin `/api`, then
  /// falls back to the bundled JSON snapshots if Vercel serves index.html.
  static const bool staticApiFallbackEnabled = bool.fromEnvironment(
    'STATIC_API_FALLBACK',
    defaultValue: true,
  );
}
