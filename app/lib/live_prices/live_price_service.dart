/// Direct market-price stream owned by the Flutter app.
///
/// Analytical reads still come from Crypto Intelligence's backend. Prices are
/// deliberately separate: one public Kraken WebSocket supplies BTC, ETH and
/// SOL in EUR without polling our HTTP API every half-second.
library;

import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

const _krakenEndpoint = 'wss://ws.kraken.com/v2';
const _trackedPairs = ['BTC/EUR', 'ETH/EUR', 'SOL/EUR'];

enum LivePriceConnection { connecting, live, reconnecting, stopped }

class LivePriceTick {
  final String asset;
  final double priceEur;
  final double change24hPct;
  final DateTime marketTimestamp;
  final DateTime receivedAt;

  const LivePriceTick({
    required this.asset,
    required this.priceEur,
    required this.change24hPct,
    required this.marketTimestamp,
    required this.receivedAt,
  });
}

class LivePriceState {
  final LivePriceConnection connection;
  final Map<String, LivePriceTick> prices;
  final String? message;

  LivePriceState({
    required this.connection,
    Map<String, LivePriceTick> prices = const {},
    this.message,
  }) : prices = UnmodifiableMapView(Map.of(prices));

  LivePriceTick? priceFor(String asset) => prices[asset.toUpperCase()];
}

/// Minimal interface used by widgets, so tests can inject a local stream and
/// never open a real network connection.
abstract interface class LivePriceSource {
  LivePriceState get current;
  Stream<LivePriceState> get updates;
}

typedef WebSocketConnector = WebSocketChannel Function(Uri uri);

class LivePriceService implements LivePriceSource {
  final Uri endpoint;
  final Duration displayInterval;
  final WebSocketConnector _connectSocket;
  final StreamController<LivePriceState> _updates =
      StreamController<LivePriceState>.broadcast();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _socketSubscription;
  Timer? _displayTimer;
  Timer? _reconnectTimer;
  var _reconnectAttempt = 0;
  var _disposed = false;
  var _connecting = false;
  LivePriceState _current = LivePriceState(
    connection: LivePriceConnection.connecting,
  );

  LivePriceService({
    Uri? endpoint,
    this.displayInterval = const Duration(milliseconds: 500),
    WebSocketConnector? connectSocket,
  })  : endpoint = endpoint ?? Uri.parse(_krakenEndpoint),
        _connectSocket = connectSocket ?? WebSocketChannel.connect;

  @override
  LivePriceState get current => _current;

  @override
  Stream<LivePriceState> get updates => _updates.stream;

  /// Opens one socket for all three pairs and starts the 500 ms UI cadence.
  void start() {
    if (_disposed || _displayTimer != null) return;
    _displayTimer = Timer.periodic(displayInterval, (_) => _publish());
    unawaited(_connect());
  }

  Future<void> _connect() async {
    if (_disposed || _connecting || _channel != null) return;
    _connecting = true;
    _setConnection(
      _reconnectAttempt == 0
          ? LivePriceConnection.connecting
          : LivePriceConnection.reconnecting,
    );

    WebSocketChannel? socket;
    try {
      final connectedSocket = _connectSocket(endpoint);
      socket = connectedSocket;
      _channel = connectedSocket;
      _socketSubscription = connectedSocket.stream.listen(
        _handleMessage,
        onError: (Object error, StackTrace stackTrace) =>
            _handleSocketEnd(connectedSocket, error),
        onDone: () => _handleSocketEnd(connectedSocket),
        cancelOnError: true,
      );
      await connectedSocket.ready;
      if (_disposed || !identical(_channel, connectedSocket)) return;

      connectedSocket.sink.add(jsonEncode({
        'method': 'subscribe',
        'params': {
          'channel': 'ticker',
          'symbol': _trackedPairs,
          'event_trigger': 'trades',
          'snapshot': true,
        },
        'req_id': 1,
      }));
      _connecting = false;
      _reconnectAttempt = 0;
      _setConnection(LivePriceConnection.live);
    } catch (error) {
      _connecting = false;
      if (socket != null && identical(_channel, socket)) {
        _channel = null;
      }
      final failedSubscription = _socketSubscription;
      _socketSubscription = null;
      try {
        await failedSubscription?.cancel();
      } catch (_) {
        // The original connection error is the useful one.
      }
      try {
        await socket?.sink.close();
      } catch (_) {
        // The socket may never have completed its handshake.
      }
      _scheduleReconnect(error);
    }
  }

  void _handleMessage(dynamic payload) {
    final ticks = parseKrakenTickerMessage(payload);
    if (ticks.isEmpty) return;

    final prices = Map<String, LivePriceTick>.of(_current.prices);
    for (final tick in ticks) {
      prices[tick.asset] = tick;
    }
    _current = LivePriceState(
      connection: LivePriceConnection.live,
      prices: prices,
    );
    // Do not publish here. Kraken can send several trades per millisecond;
    // the periodic publisher keeps rendering predictably at 500 ms.
  }

  void _handleSocketEnd(WebSocketChannel socket, [Object? error]) {
    if (_disposed || !identical(_channel, socket)) return;
    _channel = null;
    _socketSubscription = null;
    _connecting = false;
    _scheduleReconnect(error);
  }

  void _scheduleReconnect([Object? error]) {
    if (_disposed || _reconnectTimer?.isActive == true) return;
    _setConnection(
      LivePriceConnection.reconnecting,
      message: error?.toString(),
    );
    const seconds = [1, 2, 4, 8, 16, 30];
    final delay = Duration(
      seconds: seconds[_reconnectAttempt.clamp(0, seconds.length - 1)],
    );
    if (_reconnectAttempt < seconds.length - 1) _reconnectAttempt++;
    _reconnectTimer = Timer(delay, () {
      _reconnectTimer = null;
      unawaited(_connect());
    });
  }

  void _setConnection(LivePriceConnection connection, {String? message}) {
    _current = LivePriceState(
      connection: connection,
      prices: _current.prices,
      message: message,
    );
    _publish();
  }

  void _publish() {
    if (!_disposed && !_updates.isClosed) _updates.add(_current);
  }

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _displayTimer?.cancel();
    _reconnectTimer?.cancel();
    unawaited(_socketSubscription?.cancel());
    unawaited(_channel?.sink.close());
    _channel = null;
    _current = LivePriceState(
      connection: LivePriceConnection.stopped,
      prices: _current.prices,
    );
    unawaited(_updates.close());
  }
}

/// Parses only Kraken ticker events. Acknowledgements, status messages and
/// heartbeats intentionally produce an empty list.
List<LivePriceTick> parseKrakenTickerMessage(
  dynamic payload, {
  DateTime? receivedAt,
}) {
  dynamic decoded = payload;
  if (decoded is String) {
    try {
      decoded = jsonDecode(decoded);
    } catch (_) {
      return const [];
    }
  }
  if (decoded is! Map || decoded['channel'] != 'ticker') return const [];
  final data = decoded['data'];
  if (data is! List) return const [];

  final received = (receivedAt ?? DateTime.now()).toUtc();
  final ticks = <LivePriceTick>[];
  for (final raw in data) {
    if (raw is! Map) continue;
    final symbol = raw['symbol']?.toString();
    final price = _asDouble(raw['last']);
    final change = _asDouble(raw['change_pct']);
    final timestamp = DateTime.tryParse(raw['timestamp']?.toString() ?? '');
    if (symbol == null ||
        !symbol.endsWith('/EUR') ||
        price == null ||
        change == null ||
        timestamp == null) {
      continue;
    }
    final asset = symbol.substring(0, symbol.indexOf('/')).toUpperCase();
    if (!_trackedPairs.contains('$asset/EUR')) continue;
    ticks.add(LivePriceTick(
      asset: asset,
      priceEur: price,
      change24hPct: change,
      marketTimestamp: timestamp.toUtc(),
      receivedAt: received,
    ));
  }
  return ticks;
}

double? _asDouble(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}
