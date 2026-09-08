/// Les calques du graphique, déclarés une fois.
///
/// Chaque élément dessiné appartient à un calque et un seul, et l'ordre de
/// l'énumération est l'ordre de peinture. Déclarer les calques maintenant,
/// même ceux qui restent vides dans ce lot, évite qu'un overlay ajouté plus
/// tard se retrouve peint par-dessus le crosshair ou sous les bougies.
library;

enum ChartLayer {
  grid,
  candles,
  volume,
  indicators,
  levels,
  range,
  patternGeometry,
  eventMarkers,
  labels,
  currentPrice,
  crosshair;

  /// Nom affiché dans la barre de calques.
  String get label => switch (this) {
        ChartLayer.grid => 'Grille',
        ChartLayer.candles => 'Bougies',
        ChartLayer.volume => 'Volume',
        ChartLayer.indicators => 'Indicateurs',
        ChartLayer.levels => 'Zones',
        ChartLayer.range => 'Range',
        ChartLayer.patternGeometry => 'Figures',
        ChartLayer.eventMarkers => 'Événements',
        ChartLayer.labels => 'Étiquettes',
        ChartLayer.currentPrice => 'Prix',
        ChartLayer.crosshair => 'Crosshair',
      };

  /// Un calque structurel, que l'utilisateur n'a pas à décocher.
  bool get isStructural => switch (this) {
        ChartLayer.grid ||
        ChartLayer.candles ||
        ChartLayer.labels ||
        ChartLayer.currentPrice ||
        ChartLayer.crosshair =>
          true,
        _ => false,
      };
}

/// Quels calques sont visibles.
///
/// Densité d'ouverture volontairement basse: un graphique qui affiche tout
/// dès la première seconde n'est pas lisible. L'utilisateur ajoute ce dont il
/// a besoin.
class ChartLayerSet {
  final Set<ChartLayer> _visible;

  const ChartLayerSet(this._visible);

  static const _defaults = {
    ChartLayer.grid,
    ChartLayer.candles,
    ChartLayer.volume,
    ChartLayer.levels,
    ChartLayer.range,
    ChartLayer.patternGeometry,
    ChartLayer.labels,
    ChartLayer.currentPrice,
    ChartLayer.crosshair,
  };

  factory ChartLayerSet.initial() => const ChartLayerSet(_defaults);

  bool isVisible(ChartLayer layer) => _visible.contains(layer);

  ChartLayerSet toggled(ChartLayer layer) {
    // Un calque structurel n'est pas négociable: sans bougies il n'y a plus
    // de graphique, seulement une grille.
    if (layer.isStructural) return this;
    final next = Set<ChartLayer>.of(_visible);
    if (!next.remove(layer)) next.add(layer);
    return ChartLayerSet(next);
  }

  /// Les calques optionnels, dans l'ordre de la barre.
  static List<ChartLayer> get toggleable =>
      ChartLayer.values.where((layer) => !layer.isStructural).toList();

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ChartLayerSet &&
          other._visible.length == _visible.length &&
          other._visible.containsAll(_visible);

  @override
  int get hashCode => Object.hashAllUnordered(_visible);
}
