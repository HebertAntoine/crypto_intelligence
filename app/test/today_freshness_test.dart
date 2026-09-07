/// La page « Aujourd'hui » ne doit jamais présenter du vieux comme de l'actuel.
///
/// Le défaut que ces tests verrouillent : un instantané embarqué transporte
/// `freshness: LIVE` et `age_seconds: 0.0002` figés au moment de la capture,
/// et les rejoue à l'identique des mois plus tard. Le prix affiché était vrai
/// le jour de la capture ; l'étiquette « temps réel » posée au-dessus ne l'est
/// plus.
library;

import 'package:crypto_intelligence_app/api/freshness.dart';
import 'package:crypto_intelligence_app/api/models.dart';
import 'package:flutter_test/flutter_test.dart';

MarketPriceRead _market({
  String? asOf,
  String status = 'LIVE',
  String freshness = 'LIVE',
  double? ageSeconds = 0.0002,
  double? priceEur = 67998.335,
  double? priceUsd = 79075.5,
  double? change24h = -0.65,
}) =>
    MarketPriceRead(
      asset: 'BTC',
      status: status,
      priceUsd: priceUsd,
      priceEur: priceEur,
      change24hPct: change24h,
      timestamp: asOf,
      asOf: asOf,
      fetchedAt: asOf,
      ageSeconds: ageSeconds,
      providers: const [],
      providerCount: 3,
      dispersionPct: 0.0225,
      quality: 'OK',
      freshness: freshness,
      fxRate: 0.8599166,
      fxTimestamp: asOf,
      fxSource: 'Coinbase direct EUR spot pair',
      method: 'median of 3 providers',
    );

void main() {
  final now = DateTime.utc(2026, 9, 7, 14, 40);

  group('Fraîcheur dérivée', () {
    test('une observation de quelques secondes est temps réel', () {
      final derived = deriveFreshness(
        now.subtract(const Duration(seconds: 20)).toIso8601String(),
        now: now,
      );
      expect(derived.state, FreshnessState.live);
      expect(derived.isTrustworthy, isTrue);
      expect(derived.blocksAnalysis, isFalse);
    });

    test('un prix de dix minutes est récent, pas temps réel', () {
      final derived = deriveFreshness(
        now.subtract(const Duration(minutes: 10)).toIso8601String(),
        now: now,
      );
      expect(derived.state, FreshnessState.recent);
      expect(derived.isTrustworthy, isTrue);
    });

    test('un prix de trente minutes est différé et n’est plus exploitable', () {
      final derived = deriveFreshness(
        now.subtract(const Duration(minutes: 30)).toIso8601String(),
        now: now,
      );
      expect(derived.state, FreshnessState.delayed);
      expect(derived.isTrustworthy, isFalse);
    });

    test('un prix de six heures est périmé', () {
      final derived = deriveFreshness(
        now.subtract(const Duration(hours: 6)).toIso8601String(),
        now: now,
      );
      expect(derived.state, FreshnessState.stale);
      expect(derived.isTrustworthy, isFalse);
    });

    test('un prix de deux jours bloque l’analyse', () {
      final derived = deriveFreshness(
        now.subtract(const Duration(days: 2)).toIso8601String(),
        now: now,
      );
      expect(derived.state, FreshnessState.stale);
      expect(derived.blocksAnalysis, isTrue);
    });

    test('un horodatage absent ne donne jamais « frais »', () {
      expect(deriveFreshness(null, now: now).state, FreshnessState.unavailable);
      expect(deriveFreshness('', now: now).state, FreshnessState.unavailable);
      expect(
        deriveFreshness('pas une date', now: now).state,
        FreshnessState.unavailable,
      );
    });

    test('un horodatage dans le futur avoue l’ignorance plutôt que la fraîcheur',
        () {
      final derived = deriveFreshness(
        now.add(const Duration(days: 3)).toIso8601String(),
        now: now,
      );
      expect(derived.state, FreshnessState.unavailable);
    });

    test('chaque famille a sa propre cadence', () {
      final sixHours = now.subtract(const Duration(hours: 6)).toIso8601String();
      // Six heures: vieux pour un prix, normal pour un flux ETF publié une
      // fois par séance.
      expect(
        deriveFreshness(sixHours, family: DataFamily.price, now: now).state,
        FreshnessState.stale,
      );
      expect(
        deriveFreshness(sixHours, family: DataFamily.etf, now: now).state,
        FreshnessState.recent,
      );
    });
  });

  group('Le champ figé du payload n’est jamais cru', () {
    test('un instantané qui se déclare LIVE est requalifié par son horodatage',
        () {
      // Exactement la forme du snapshot embarqué: status LIVE, freshness LIVE,
      // age_seconds 0.0002 — capturés il y a six mois.
      final market = _market(
        asOf: now.subtract(const Duration(days: 180)).toIso8601String(),
      );

      expect(market.status, 'LIVE', reason: 'le payload prétend toujours LIVE');
      expect(market.ageSeconds, 0.0002, reason: 'et un âge nul');

      final derived = market.derived(now: now);
      expect(derived.state, FreshnessState.stale);
      expect(derived.blocksAnalysis, isTrue);
      expect(market.trustworthyAt(now: now), isFalse);
    });

    test('un instantané récent reste exploitable', () {
      final market = _market(
        asOf: now.subtract(const Duration(seconds: 30)).toIso8601String(),
      );
      expect(market.trustworthyAt(now: now), isTrue);
      expect(market.derived(now: now).state, FreshnessState.live);
    });

    test('un instantané sans horodatage n’est jamais exploitable', () {
      final market = _market(asOf: null);
      expect(market.trustworthyAt(now: now), isFalse);
      expect(market.derived(now: now).blocksAnalysis, isTrue);
    });
  });

  group('Prix et variation', () {
    test('EUR est préféré quand il existe, sans conversion inventée', () {
      final market = _market(asOf: now.toIso8601String());
      expect(market.displayUnit, 'EUR');
      expect(market.displayPrice, 67998.335);
      expect(market.fxSource, isNotNull,
          reason: 'la source du taux doit être traçable');
    });

    test('sans EUR, USD est affiché plutôt qu’un EUR fabriqué', () {
      final market = _market(asOf: now.toIso8601String(), priceEur: null);
      expect(market.displayUnit, 'USD');
      expect(market.displayPrice, 79075.5);
    });

    test('un prix absent rend la lecture indisponible, pas nulle', () {
      final market = _market(
        asOf: now.toIso8601String(),
        priceEur: null,
        priceUsd: null,
        status: 'UNAVAILABLE',
      );
      expect(market.available, isFalse);
      expect(market.displayPrice, isNull);
    });

    test('une variation 24 h absente reste absente', () {
      final market = _market(asOf: now.toIso8601String(), change24h: null);
      expect(market.change24hPct, isNull);
    });

    test('une variation de zéro est une valeur, pas une absence', () {
      final market = _market(asOf: now.toIso8601String(), change24h: 0);
      expect(market.change24hPct, 0);
    });
  });

  group('Un instantané ne rajeunit jamais une donnée', () {
    // Le défaut exact rapporté: la page affichait « instantané embarqué,
    // backend injoignable, as_of il y a 5 min » et, juste en dessous,
    // « Prix : À JOUR · il y a 1 s ». Les deux venaient du même payload.
    FamilyState frozen({
      required String observedAt,
      String freshness = 'LIVE',
      double ageSeconds = 1.0,
      bool usable = true,
    }) =>
        FamilyState(
          family: 'price',
          available: true,
          valid: true,
          freshness: freshness,
          usable: usable,
          observedAt: observedAt,
          ageSeconds: ageSeconds,
          source: 'median of 3 providers',
          points: 3,
          reason: 'présente, valide et dans sa cadence',
        );

    test('un âge exporté à 1 s devient 30 min une demi-heure plus tard', () {
      final t0 = DateTime.utc(2026, 9, 7, 16, 30, 37);
      final state = frozen(observedAt: t0.toIso8601String());

      // Ce que le payload transporte, figé à l'export.
      expect(state.ageSeconds, 1.0);
      expect(state.freshness, 'LIVE');
      expect(state.usable, isTrue);

      final later = t0.add(const Duration(minutes: 30));
      final derived = state.derived(now: later);

      expect(derived.age!.inMinutes, 30);
      expect(derived.state, isNot(FreshnessState.live));
      expect(state.usableNow(now: later), isFalse,
          reason: 'un prix de 30 min n’alimente pas une analyse actuelle');
    });

    test('l’âge suit l’horloge, jamais le champ exporté', () {
      final t0 = DateTime.utc(2026, 9, 7, 12);
      final state = frozen(observedAt: t0.toIso8601String());
      for (final elapsed in [
        const Duration(seconds: 30),
        const Duration(minutes: 10),
        const Duration(hours: 3),
      ]) {
        final derived = state.derived(now: t0.add(elapsed));
        expect(derived.age!.inSeconds, closeTo(elapsed.inSeconds, 1));
      }
    });

    test('un prix récent reste exploitable', () {
      final t0 = DateTime.utc(2026, 9, 7, 12);
      final state = frozen(observedAt: t0.toIso8601String());
      expect(
        state.usableNow(now: t0.add(const Duration(seconds: 45))),
        isTrue,
      );
    });

    test('un usable figé à true ne survit pas à un horodatage ancien', () {
      final observed = DateTime.utc(2026, 9, 1);
      final state = frozen(observedAt: observed.toIso8601String());
      expect(state.usable, isTrue, reason: 'le payload l’affirme');
      expect(
        state.usableNow(now: DateTime.utc(2026, 9, 7)),
        isFalse,
        reason: 'six jours plus tard, non',
      );
    });

    test('chaque famille est jugée à sa propre cadence', () {
      final now = DateTime.utc(2026, 9, 7, 16);
      final observed = now.subtract(const Duration(hours: 20));

      FamilyState build(String family) => FamilyState(
            family: family, available: true, valid: true, freshness: 'LIVE',
            usable: true, observedAt: observed.toIso8601String(),
            ageSeconds: 1.0, source: family, points: 100, reason: '',
          );

      // Vingt heures: périmé pour un prix, encore dans la cadence pour des
      // bougies journalières qui ne closent qu'une fois par jour.
      expect(build('price').usableNow(now: now), isFalse);
      expect(build('ohlcv_daily').usableNow(now: now), isTrue);
    });
  });
}
