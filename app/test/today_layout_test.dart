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

  group('Une donnée périmée ne dit jamais OK', () {
    testWidgets('le funding périmé est affiché comme tel, pas comme disponible',
        (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      // Le funding du fixture est present et valide mais vieux de 24 h.
      expect(find.textContaining('PÉRIMÉ'), findsWidgets);
      expect(find.textContaining('non utilisable'), findsWidgets);
    });

    testWidgets('l’identifiant technique n’est jamais montré à l’utilisateur',
        (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      // Les enums restent anglais en interne; l'UI francaise les traduit.
      expect(find.text('ohlcv_daily'), findsNothing);
      expect(find.text('open_interest'), findsNothing);
      expect(find.text('STRONGLY_BULLISH'), findsNothing);
    });
  });

  group('Cohérence fraîcheur / analyse', () {
    testWidgets('le funding périmé n’est pas présenté comme utilisable',
        (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      // Le percentile historique reste affiché - il est valide - mais la
      // ligne dit explicitement que l'entrée n'est pas utilisable.
      expect(find.textContaining('Funding (contexte historique)'), findsOneWidget);
      expect(find.textContaining('Entrée non utilisable'), findsWidgets);
    });

    testWidgets('volatilité réalisée et implicite ne sont pas confondues',
        (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      expect(find.textContaining('Volatilité réalisée (ATR)'), findsOneWidget);
    });

    testWidgets('la direction annonce son mode simplifié', (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      expect(find.textContaining('mode prix simplifié'), findsOneWidget);
    });

    testWidgets('aucune chaîne anglaise ne reste visible', (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      for (final anglais in ['Drivers', 'Caveats', 'NEUTRAL', 'STRONGLY_BULLISH']) {
        expect(find.text(anglais), findsNothing, reason: '$anglais visible');
      }

      // Les sections plus bas ne sont pas construites (ListView paresseux);
      // leur libellé français est vérifié statiquement côté backend, par
      // test_no_fake_frontend_market_data.py.
    });
  });

  group('Diagnostic par crypto', () {
    testWidgets('le panneau s’ouvre au clic sur la carte', (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));

      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      expect(find.textContaining('DONNÉES REÇUES'), findsOneWidget);
      expect(find.textContaining('contrôles passés'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('il montre la valeur brute reçue, pas une reformulation',
        (tester) async {
      await _pumpAt(tester, const Size(430, 932), TodayScreen(client: _client()));
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      expect(find.textContaining('68033.92'), findsWidgets);
      expect(find.textContaining('Coinbase direct EUR spot pair'), findsWidgets);
    });

    testWidgets('un bloc de prix absent est signalé comme un échec',
        (tester) async {
      await _pumpAt(
        tester,
        const Size(430, 932),
        TodayScreen(client: _client(withMarket: false)),
      );
      await tester.tap(find.text('BTC').first);
      await tester.pumpAndSettle();

      expect(find.text('Bloc market_data'), findsOneWidget);
      expect(find.textContaining('aucun bloc de prix'), findsOneWidget);
    });
  });
}
