import 'package:flutter/widgets.dart';

import '../live_prices/live_price_service.dart';

typedef LivePriceWidgetBuilder = Widget Function(
  BuildContext context,
  LivePriceTick? price,
  LivePriceConnection connection,
);

/// Rebuilds only the small price area, not the analytical screen around it.
class LivePriceBuilder extends StatelessWidget {
  final LivePriceSource? source;
  final String asset;
  final LivePriceWidgetBuilder builder;

  const LivePriceBuilder({
    super.key,
    required this.source,
    required this.asset,
    required this.builder,
  });

  @override
  Widget build(BuildContext context) {
    final prices = source;
    if (prices == null) {
      return builder(context, null, LivePriceConnection.stopped);
    }
    return StreamBuilder<LivePriceState>(
      stream: prices.updates,
      initialData: prices.current,
      builder: (context, snapshot) {
        final state = snapshot.data ?? prices.current;
        return builder(context, state.priceFor(asset), state.connection);
      },
    );
  }
}
