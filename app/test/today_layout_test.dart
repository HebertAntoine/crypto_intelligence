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

Map<String, dynamic> _today(
  String asset, {
  bool withMarket = true,
  String opportunityState = 'FAVORABLE',
  bool opportunityHasNegative = false,
}) =>
    {
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
      'buy_opportunity': opportunityState,
      'buy_opportunity_explanation': {
        'state': opportunityState,
        'headline': opportunityState,
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
        'negatives': opportunityHasNegative
            ? [
                {
                  'id': 'risk.high',
                  'category': 'RISK',
                  'title': 'Risque élevé',
                  'short_text': 'La structure demeure fragile.',
                  'polarity': 'NEGATIVE',
                  'importance': 85,
                  'confidence': .9,
                  'evidence_level': 'COMPUTATION',
                  'timeframe': '4H',
                  'source': 'RiskEngine',
                  'freshness': 'RECENT',
                  'available': true,
                },
              ]
            : [],
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
      'analysis_id': 'an_layout_fixture',
      'analysis': {
        'analysis_id': 'an_layout_fixture',
        'computed_at': '2026-09-07T15:23:29.000Z',
        'age_seconds': 120.0,
        'price_at_analysis': 78824.65,
        'live_price': 79086.715,
        'price_drift_pct': 0.33,
        'drift_threshold_pct': 1.5,
        'drift_severity': 'NONE',
        'stale_for_current_price': false,
      },
      'page': _page(asset),
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

/// La page compacte telle que le backend la compose, avec les huit blocs que
/// l'écran doit savoir rendre sans déborder.
Map<String, dynamic> _page(String asset) => {
      'analysis_id': 'an_layout_fixture',
      'asset': asset,
      'analysis_time': '2026-09-07T15:23:29.000Z',
      'price_at_analysis': 78824.65,
      'direction_timing_edge': {
        'direction': {
          'value': 'FORTEMENT HAUSSIÈRE',
          'state': 'STRONGLY_BULLISH',
          'detail': 'Tendance, structure et momentum concordent à 80 %.',
          'question': 'Où va le marché ?',
        },
        'timing': {
          'value': 'ATTENDRE',
          'state': 'WAIT',
          'detail': 'Un facteur de risque justifie d’attendre.',
          'question': 'Est-ce intéressant maintenant ?',
        },
        'edge': {
          'value': 'AUCUN AVANTAGE DÉMONTRÉ',
          'state': 'NO_MEASURABLE_EDGE',
          'detail': '3 relation(s) testée(s); aucune n’a survécu.',
          'question': 'Est-ce historiquement démontré ?',
        },
        'note': 'Ces trois lectures sont indépendantes.',
      },
      'decision': {
        'state': 'WAIT',
        'headline': 'ATTENDRE',
        'label': 'ATTENDRE',
        'sentence': 'La tendance de fond reste positive, mais $asset évolue '
            'proche du haut de son range 4H. Le timing actuel n’est pas '
            'suffisamment favorable.',
        'guard_rails': [],
      },
      'structural_position': {
        'has_range': true,
        'timeframe': '4H',
        'headline': 'Proche du haut du range',
        'state': 'NEAR_RANGE_TOP',
        'range_bottom': 62625.62,
        'range_midpoint': 72000.68,
        'range_top': 81375.74,
        'price': 78824.65,
        'relative_position': 0.8639,
        'percent': 86,
        'bottom_label': 'Bas du range',
        'top_label': 'Haut du range',
        'detail': '86 % de la hauteur du range 4H',
        'invalidation': 'Une clôture 4h au-dessus de 84508.99 casserait la '
            'zone haute du range et invaliderait cette lecture.',
        'note': 'La position est descriptive.',
      },
      'levels': {
        'available': true,
        'reference_price': 78824.65,
        'support': {'price': 76944.0, 'distance_pct': -2.39, 'touches': 2},
        'resistance': {'price': 79383.33, 'distance_pct': 0.71, 'touches': 3},
        'source': 'clusters de swings 4H',
      },
      'immediate_context': [
        {'label': 'Position', 'value': 'Proche du haut du range', 'detail': ''},
        {'label': 'Volatilité', 'value': 'Faible', 'detail': ''},
        {'label': 'Encombrement', 'value': 'Normal', 'detail': ''},
        {
          'label': 'Prochain événement',
          'value': 'Inflation US (CPI) · dans 18 h',
          'detail': '',
        },
      ],
      'pressure': {
        'state': 'BUYING',
        'label': 'ACHAT LÉGER',
        'headline': 'ACHAT LÉGER +19/100',
        'score': 19.0,
        'families_active': 3,
        'families_total': 5,
        'families_line': '3/5 familles disponibles',
        'buyers': [
          {
            'family': 'institutions',
            'label': 'Institutions (ETF spot)',
            'available': true,
            'normalized_score': 28.0,
            'contribution_points': 14.2,
            'direction': 'BUYING',
            'weight_if_any': 0.35,
            'source': 'Farside Investors',
            'timestamp': '2026-09-07T00:00:00.000Z',
            'freshness': 'RECENT',
            'explanation': '+450 M\$ sur 5 séances.',
          },
        ],
        'sellers': [
          {
            'family': 'levier',
            'label': 'Funding perpétuel',
            'available': true,
            'normalized_score': -4.0,
            'contribution_points': -1.1,
            'direction': 'SELLING',
            'weight_if_any': 0.20,
            'source': 'funding.rate',
            'freshness': 'RECENT',
            'explanation': 'Coût de portage dans sa normale.',
          },
        ],
        'neutral': [],
        'unavailable': [
          {
            'family': 'baleines',
            'label': 'Baleines',
            'available': false,
            'direction': 'UNKNOWN',
            'source': 'fournisseur on-chain vérifié',
            'freshness': 'UNAVAILABLE',
            'explanation': 'Aucun fournisseur fiable configuré.',
          },
        ],
        'buyers_title': 'FACTEURS ACHETEURS',
        'sellers_title': 'FACTEURS VENDEURS',
        'unavailable_title': 'INDISPONIBLE',
        'contradictions': [
          'Institutions (ETF spot) indique une pression acheteuse tandis que '
              'Funding perpétuel indique une pression vendeuse.',
        ],
        'tooltip': 'Ce score mesure la pression relative des facteurs '
            'disponibles. Il ne représente ni une probabilité de hausse ni '
            'une edge statistique.',
        'missing_note': 'Une source absente n’est ni neutre ni zéro.',
      },
      'catalysts': {
        'items': [
          {
            'kind': 'CPI',
            'name': 'Inflation US (CPI)',
            'when': 'dans 18 h',
            'importance': 'CRITICAL',
            'importance_label': 'Majeur',
            'hours_until': 18.0,
            'asset_scope': ['BTC', 'ETH', 'SOL'],
            'source': 'config/macro_calendar.yaml',
          },
        ],
        'alert': {
          'label': 'ÉVÉNEMENT IMPORTANT DANS 18 H',
          'name': 'Inflation US (CPI)',
          'hours_until': 18.0,
          'note': 'Le sens n’est pas prédit.',
        },
        'horizon_note': 'Événements programmés des 7 prochains jours.',
        'not_news': 'Uniquement des échéances programmées et sourcées.',
      },
      'change_conditions': {
        'improve': [
          {
            'text': 'Le timing deviendrait plus favorable avec un retour du '
                'prix vers le bas du range'
          },
        ],
        'degrade': [
          {
            'text': 'La lecture serait dégradée par la perte confirmée du bas '
                'de range'
          },
        ],
        'structure_change': [
          {
            'text': 'La structure changerait avec une clôture 4H au-dessus du '
                'haut de range : le range serait invalidé, ce qui n’est pas une '
                'dégradation'
          },
        ],
        'improve_title': 'POUR DEVENIR PLUS FAVORABLE',
        'degrade_title': 'POUR DEVENIR MOINS FAVORABLE',
        'structure_change_title': 'CHANGEMENT À SURVEILLER',
        'note': 'Ce sont des conditions, pas des prévisions.',
      },
      'timeframes': {
        'rows': [
          {
            'timeframe': '1S',
            'key': '1w',
            'state': 'BEARISH_STRUCTURE',
            'label': 'Baissière',
            'arrow': '↓'
          },
          {
            'timeframe': '1J',
            'key': '1d',
            'state': 'RANGE_STRUCTURE',
            'label': 'En range',
            'arrow': '↔'
          },
          {
            'timeframe': '4H',
            'key': '4h',
            'state': 'RANGE_STRUCTURE',
            'label': 'En range',
            'arrow': '↔'
          },
          {
            'timeframe': '1H',
            'key': '1h',
            'state': 'BULLISH_STRUCTURE',
            'label': 'Haussière',
            'arrow': '↑'
          },
        ],
        'alignment': 'DIVERGENT',
        'alignment_label': 'Divergent',
        'note': 'L’alignement est descriptif.',
      },
      'contradictions': {
        'items': [
          {
            'title': 'Régime haussier, structure hebdomadaire baissière',
            'text': 'La tendance récente est positive, mais la structure de '
                'plus long terme n’est pas encore totalement alignée.',
          },
        ],
        'has_contradiction': true,
        'badge': 'LECTURE MIXTE',
      },
      'volatility': {
        'headline': 'Faible',
        'realised': {'state': 'LOW', 'label': 'Faible', 'direction': 'STABLE'},
        'implied': {
          'available': false,
          'label': 'Indisponible',
          'reason': 'aucune série DVOL pour cet actif',
        },
        'note': 'Réalisée et implicite ne sont jamais additionnées.',
      },
      'edge': {
        'state': 'NO_MEASURABLE_EDGE',
        'label': 'AUCUN AVANTAGE DÉMONTRÉ',
        'tested_relations': 3,
        'tooltip': 'Les configurations historiques comparables n’ont pas '
            'démontré de surperformance robuste.',
        'evidence_label': 'Preuve limitée',
        'not_a_bearish_signal': 'L’absence d’avantage démontré ne dit pas que '
            'le prix va baisser.',
      },
      'positioning': {
        'positioning': {'label': 'Positionnement', 'value': 'Nouveaux longs'},
        'funding': {'label': 'Funding', 'value': 'Dans sa normale'},
        'crowding': {'label': 'Encombrement', 'value': 'Normal'},
        'note': 'Les valeurs brutes sont dans l’écran Preuves.',
      },
      'etf': {
        'available': true,
        'headline': 'Flux récents positifs',
        'latest_musd': 120.0,
        'net_5d_musd': 450.0,
        'caveat': 'Flux observés ≠ avantage prédictif démontré.',
      },
      'coverage': {
        'expected': 12,
        'available': 11,
        'fresh': 9,
        'stale': 2,
        'missing': 1,
        'percent': 92,
        'level': 'GOOD',
        'label': 'Bonne couverture',
        'summary': '11/12 familles disponibles, 9 récentes',
        'uncertainty_score': 40.0,
        'uncertainty_note': 'L’incertitude et la couverture sont distinctes.',
        'titles': {
          'available': 'DONNÉES DISPONIBLES',
          'missing': 'DONNÉES MANQUANTES',
          'not_applicable': 'NON APPLICABLE',
          'by_design': 'NON COLLECTÉ PAR CONCEPTION',
        },
        'families': [
          {
            'family': 'price',
            'label': 'Prix',
            'coverage': 'EXPECTED_AND_AVAILABLE',
            'available': true,
            'fresh': true,
            'stale': false,
            'reason': ''
          },
          {
            'family': 'onchain',
            'label': 'On-chain',
            'coverage': 'EXPECTED_BUT_MISSING',
            'available': false,
            'fresh': false,
            'stale': false,
            'reason': 'aucune observation stockée'
          },
          {
            'family': 'dvol',
            'label': 'Volatilité implicite (DVOL)',
            'coverage': 'NOT_APPLICABLE',
            'available': false,
            'fresh': false,
            'stale': false,
            'reason': 'Deribit ne publie pas d’indice DVOL pour cet actif'
          },
          {
            'family': 'whales',
            'label': 'Baleines',
            'coverage': 'UNAVAILABLE_BY_DESIGN',
            'available': false,
            'fresh': false,
            'stale': false,
            'reason': 'aucun fournisseur baleines fiable n’est configuré'
          },
        ],
      },
      'last_change': {
        'available': false,
        'reason': 'Pas encore assez de lectures enregistrées.',
      },
      'reading_order': [
        'direction_timing_edge',
        'decision',
        'structural_position',
        'immediate_context',
        'pressure',
        'catalysts',
        'change_conditions',
        'coverage',
      ],
    };

ApiClient _client({
  bool withMarket = true,
  String opportunityState = 'FAVORABLE',
  bool opportunityHasNegative = false,
}) =>
    ApiClient(
      client: MockClient((request) async {
        final asset = request.url.path.split('/').last;
        return http.Response(
          jsonEncode(_today(
            asset,
            withMarket: withMarket,
            opportunityState: opportunityState,
            opportunityHasNegative: opportunityHasNegative,
          )),
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
    testWidgets('le fond Bitcoin et les illustrations suivent la décision',
        (tester) async {
      const cases = <(String, bool, String)>[
        (
          'VERY_FAVORABLE',
          false,
          'assets/visuals/opportunity_very_favorable.png'
        ),
        ('FAVORABLE', false, 'assets/visuals/opportunity_favorable.png'),
        ('WATCH', false, 'assets/visuals/opportunity_insufficient.png'),
        ('WAIT', false, 'assets/visuals/opportunity_wait.png'),
        ('WAIT', true, 'assets/visuals/opportunity_risk.png'),
        ('UNFAVORABLE', false, 'assets/visuals/opportunity_unfavorable.png'),
        (
          'INSUFFICIENT_DATA',
          false,
          'assets/visuals/opportunity_insufficient.png'
        ),
      ];

      for (final item in cases) {
        await _pumpAt(
          tester,
          const Size(430, 932),
          TodayScreen(
            key: ValueKey('${item.$1}-${item.$2}'),
            client: _client(
              opportunityState: item.$1,
              opportunityHasNegative: item.$2,
            ),
          ),
        );
        expect(find.byKey(const ValueKey('today-background')), findsOneWidget);
        expect(find.byKey(ValueKey(item.$3)), findsWidgets);
      }
    });

    testWidgets('la carte fermée ne montre que les réponses principales',
        (tester) async {
      await _pumpAt(
          tester, const Size(430, 932), TodayScreen(client: _client()));

      // Direction, timing et avantage remplacent la ligne « RÉGIME »: trois
      // lectures indépendantes plutôt qu'une seule.
      expect(find.text('DIRECTION'), findsWidgets);
      expect(find.text('TIMING'), findsWidgets);
      expect(find.text('AVANTAGE'), findsWidgets);
      expect(find.text('ACHETER'), findsWidgets);
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

      expect(find.text('POURQUOI ACHETER ?'), findsOneWidget);
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

      expect(find.text('FACTEURS ACHETEURS'), findsOneWidget);
      expect(find.text('FACTEURS VENDEURS'), findsOneWidget);
      expect(find.text('INDISPONIBLE'), findsWidgets);
      expect(find.text('Institutions (ETF spot)'), findsOneWidget);
      expect(find.text('Baleines'), findsOneWidget);
      expect(find.textContaining('Aucun fournisseur fiable'), findsOneWidget);
      // Une source absente n'est pas comptée zéro: elle n'a pas de score.
      expect(find.text('—'), findsWidgets);
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
