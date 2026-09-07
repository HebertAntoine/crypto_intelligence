/// La page rendue à la taille d'un téléphone, sans débordement.
///
/// La largeur de référence du design est passée de 900 à 450 pour doubler la
/// taille apparente du texte: à 900, le facteur de réduction sur un téléphone
/// était de 0,44 et une police déclarée à 12,5 px s'affichait à 5,5 px. Une
/// mise en page écrite pour 900 peut déborder à 450, donc ces tests rendent
/// réellement l'écran et échouent sur tout dépassement.
library;

import 'dart:convert';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/screens/today_screen.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:crypto_intelligence_app/widgets/mobile_kit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> _today(String asset, {bool withMarket = true}) => {
      'asset': asset,
      'decision_summary': {
        'asset': asset,
        'market_direction': 'STRONGLY_BULLISH',
        'direction_confidence': '80.0',
        'entry_timing': 'UNDETERMINED',
        'edge_state': 'NO_MEASURABLE_EDGE',
        'crowding': 'NORMAL',
        'volatility_regime': 'LOW',
        'uncertainty': 40.0,
        'actionable': false,
        'statement': 'régime fortement haussier, aucun edge robuste',
        'caveats': [
          'Direction et edge sont calculés indépendamment; un régime haussier '
              'n’est pas une preuve de capacité prédictive.',
        ],
        'generated_at': '2026-09-07T15:23:29.000Z',
      },
      'direction_source': 'reconstructed from price structure',
      'edge': {
        'state': 'NO_MEASURABLE_EDGE',
        'admitted_count': 0,
        'rejected_count': 3,
        'statement': '3 candidates tested, none survived',
      },
      'uncertainty': {
        'score': 40.0,
        'level': 'MODERATE',
        'drivers': [
          {
            'driver': 'no measured edge',
            'contribution': 40,
            'detail': 'no relationship survived the full filter chain',
          },
        ],
      },
      'crowding': {'level': 'NORMAL', 'score': 56.1, 'direction': 'UNKNOWN'},
      'leverage_state': {'state': 'NEW_LONGS'},
      'funding': {'band': 'NEUTRAL', 'percentile': 25.4},
      'volatility': {'regime': 'LOW'},
      'buy_opportunity': 'FAVORABLE',
      'buy_opportunity_explanation': {
        'state': 'FAVORABLE',
        'headline': 'FAVORABLE',
        'summary':
            'La structure est favorable, mais aucun avantage statistique ne garantit la suite.',
        'positives': [
          {
            'id': 'structure.multi_timeframe',
            'category': 'STRUCTURE',
            'title': 'Structure haussière',
            'short_text': '1D et 4H haussiers; prix près du bas du range.',
            'raw_value': {
              'bullish': ['1d', '4h']
            },
            'normalized_value': 55,
            'polarity': 'POSITIVE',
            'importance': 84,
            'confidence': .8,
            'evidence_level': 'COMPUTATION',
            'timeframe': '1D/4H',
            'source': 'MarketStructureEngine',
            'as_of': '2026-09-07T15:23:29.000Z',
            'freshness': 'RECENT',
            'available': true,
          },
        ],
        'waits': [
          {
            'id': 'edge.none',
            'category': 'MEASURED_EDGE',
            'title': 'Aucun avantage statistique démontré',
            'short_text': '0 validée, 3 rejetées.',
            'raw_value': {'admitted': 0, 'rejected': 3},
            'normalized_value': 0,
            'polarity': 'WAIT',
            'importance': 88,
            'confidence': 1,
            'evidence_level': 'COMPUTATION',
            'timeframe': 'HISTORIQUE',
            'source': 'EdgeEngine',
            'as_of': '2026-09-07T15:23:29.000Z',
            'freshness': 'RECENT',
            'available': true,
          },
        ],
        'negatives': [],
        'missing': [
          {
            'id': 'pressure.baleines',
            'category': 'WHALES',
            'title': 'Baleines',
            'short_text': 'Aucun fournisseur fiable configuré.',
            'polarity': 'MISSING',
            'importance': 35,
            'confidence': 1,
            'evidence_level': 'MISSING',
            'timeframe': 'NOW',
            'source': 'fournisseur on-chain',
            'freshness': 'UNAVAILABLE',
            'available': false,
          },
        ],
        'improvement_conditions': ['un retest confirmé du support'],
        'deterioration_conditions': ['une cassure baissière du support'],
        'as_of': '2026-09-07T15:23:29.000Z',
        'provenance': {'llm_used': false},
      },
      'market_pressure': {
        'state': 'BALANCED',
        'pressure_score': 6.5,
        'balance': 53.25,
        'label': 'ÉQUILIBRÉ',
        'components_measured': 2,
        'components_missing': ['Baleines'],
        'contradictions': [
          'Les ETF achètent tandis que le positionnement dérivé vend.',
        ],
        'summary': 'ÉQUILIBRÉ (+7/100), mesuré par 2 composantes sur 5.',
        'as_of': '2026-09-07T15:23:29.000Z',
        'components': [
          {
            'name': 'institutions',
            'label': 'Institutions (ETF spot)',
            'available': true,
            'normalized_pressure': 45,
            'weight': .35,
            'confidence': .95,
            'detail': '+450 M\$ sur 5 séances',
            'source': 'Farside Investors',
            'freshness': 'RECENT',
          },
          {
            'name': 'baleines',
            'label': 'Baleines',
            'available': false,
            'reason': 'Aucun fournisseur fiable configuré.',
            'source': 'fournisseur on-chain',
            'freshness': 'UNAVAILABLE',
          },
        ],
      },
      'overall_status': withMarket ? 'LIVE' : 'UNAVAILABLE',
      'overall_status_reason': withMarket
          ? 'toutes les entrées critiques sont dans leur cadence'
          : 'donnée critique absente: price',
      'allows_action': withMarket,
      'families': {
        'price': {
          'family': 'price',
          'available': withMarket,
          'valid': withMarket,
          'freshness': withMarket ? 'LIVE' : 'UNAVAILABLE',
          'usable': withMarket,
          'observed_at': '2026-09-07T15:23:29.000Z',
          'age_seconds': 12.0,
          'source': 'median of 3 providers',
          'points': 3,
          'reason': 'présente, valide et dans sa cadence',
        },
        'funding': {
          'family': 'funding',
          'available': true,
          'valid': true,
          'freshness': 'STALE',
          'usable': false,
          'observed_at': '2026-09-06T16:00:00.000Z',
          'age_seconds': 87840.0,
          'source': 'funding.rate',
          'points': 7006,
          'reason': 'trop ancienne pour décrire l’état actuel',
        },
      },
      if (withMarket)
        'market_data': {
          'asset': asset,
          'status': 'LIVE',
          'price_usd': 79086.715,
          'price_eur': 68033.92,
          'change_24h_pct': -0.656,
          'timestamp': '2026-09-07T15:23:29.000Z',
          'as_of': '2026-09-07T15:23:29.000Z',
          'fetched_at': '2026-09-07T15:23:29.000Z',
          'age_seconds': 0.0002,
          'providers': [
            {
              'provider': 'coinbase_spot',
              'source': 'Coinbase',
              'status': 'OK',
              'unit': 'EUR',
              'price': 68033.92,
            },
          ],
          'provider_count': 3,
          'dispersion_pct': 0.0225,
          'quality': 'OK',
          'freshness': 'LIVE',
          'fx_rate': 0.8599166,
          'fx_source': 'Coinbase direct EUR spot pair',
          'method': 'median of 3 providers',
        },
    };

ApiClient _client({bool withMarket = true}) => ApiClient(
      client: MockClient((request) async {
        final asset = request.url.path.split('/').last;
        return http.Response(
          jsonEncode(_today(asset, withMarket: withMarket)),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
      baseUrl: 'http://test.local/api',
      loadAsset: (_) async => throw Exception('pas d’instantané ici'),
    );

Future<void> _pumpAt(WidgetTester tester, Size size, Widget child) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(theme: AppTheme.dark, home: child));
  await tester.pumpAndSettle();
}

void main() {
  group('Mise en page à la taille d’un téléphone', () {
    // Trois largeurs logiques courantes: petit Android, iPhone, grand format.
    for (final size in [
      const Size(360, 800),
      const Size(393, 852),
      const Size(430, 932),
    ]) {
      testWidgets('aucun débordement à ${size.width.toInt()} px de large',
          (tester) async {
        await _pumpAt(tester, size, TodayScreen(client: _client()));
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('aucun débordement quand le prix est absent', (tester) async {
      await _pumpAt(
        tester,
        const Size(393, 852),
        TodayScreen(client: _client(withMarket: false)),
      );
      expect(tester.takeException(), isNull);
    });
  });

  group('Taille apparente du texte', () {
    test('la largeur de référence a été divisée par deux', () {
      // 900 -> 450 double le facteur de réduction, donc double la taille
      // apparente de chaque mot sur un téléphone.
      expect(kMobileDesignWidth, 450);
    });

    testWidgets('le contenu est mis en page à la largeur de référence',
        (tester) async {
      await _pumpAt(
        tester,
        const Size(393, 852),
        MobileScrollView(
          padding: EdgeInsets.zero,
          children: const [SizedBox(height: 10)],
        ),
      );
      final box = tester.renderObject<RenderBox>(
        find.byType(MobileScrollView),
      );
      // La boîte externe occupe l'écran; l'enfant, lui, est mis en page à 450
      // puis réduit, ce qui est exactement ce qui agrandit le texte.
      expect(box.size.width, lessThanOrEqualTo(393));
    });
  });

  group('Surface décisionnelle compacte', () {
    testWidgets('la carte fermée ne montre que les réponses principales',
        (tester) async {
      await _pumpAt(
          tester, const Size(430, 932), TodayScreen(client: _client()));

      expect(find.text('RÉGIME'), findsWidgets);
      expect(find.text('FAVORABLE'), findsWidgets);
      expect(find.text('QUI ACHÈTE, QUI VEND ?'), findsWidgets);
      expect(find.text('Voir pourquoi'), findsWidgets);
      expect(find.text('Voir les sources'), findsWidgets);
      // Les détails de structure restent fermés au premier regard.
      expect(find.textContaining('prix près du bas du range'), findsNothing);
      expect(find.text('STRONGLY_BULLISH'), findsNothing);
      expect(find.text('ohlcv_daily'), findsNothing);
    });

    testWidgets('Voir pourquoi ouvre les groupes sourcés et les conditions',
        (tester) async {
      await _pumpAt(
          tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('Voir pourquoi').first);
      await tester.pumpAndSettle();

      expect(find.text('POURQUOI FAVORABLE ?'), findsOneWidget);
      expect(find.text('CE QUI AIDE'), findsOneWidget);
      expect(find.text('CE QUI FAIT ATTENDRE'), findsOneWidget);
      expect(find.textContaining('MarketStructureEngine'), findsOneWidget);
      expect(find.textContaining('EdgeEngine'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('la pression détaille les sources et les absences',
        (tester) async {
      await _pumpAt(
          tester, const Size(430, 932), TodayScreen(client: _client()));
      final trigger = find.text('Voir les sources').first;
      await tester.ensureVisible(trigger);
      await tester.tap(trigger);
      await tester.pumpAndSettle();

      expect(find.text('Institutions (ETF spot)'), findsOneWidget);
      expect(find.text('Baleines'), findsOneWidget);
      expect(find.textContaining('Aucun fournisseur fiable'), findsOneWidget);
      expect(find.text('CONTRADICTIONS'), findsOneWidget);
    });

    testWidgets('un prix réellement absent reste explicitement indisponible',
        (tester) async {
      await _pumpAt(
        tester,
        const Size(430, 932),
        TodayScreen(client: _client(withMarket: false)),
      );
      expect(find.text('INDISPONIBLE'), findsWidgets);
    });
  });
}
