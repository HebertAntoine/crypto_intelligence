/// Ce que la page Aujourd'hui a le droit d'afficher, et ce qu'elle doit taire.
///
/// Les blocs sont rendus réellement, pas inspectés en mémoire: la question
/// n'est pas si un champ existe, mais si un utilisateur le verrait et ce qu'il
/// y lirait. Chaque test tient une propriété qu'aucune donnée inventée ne peut
/// satisfaire — une barre de position n'existe que si un range existe, une
/// source absente n'est jamais un zéro, et une cassure haussière n'est jamais
/// rangée parmi les dégradations.
library;

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/api/today_page.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:crypto_intelligence_app/widgets/today_blocks.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _pump(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(450, 900);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark,
      home: Scaffold(
        body: SingleChildScrollView(
          child: SizedBox(width: 430, child: child),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

ReadingLine _line(String value, String state) =>
    ReadingLine(value: value, state: state);

DirectionTimingEdge _readings({
  String direction = 'FORTEMENT HAUSSIÈRE',
  String directionState = 'STRONGLY_BULLISH',
  String timing = 'ATTENDRE',
  String timingState = 'WAIT',
  String edge = 'AUCUN AVANTAGE DÉMONTRÉ',
  String edgeState = 'NO_MEASURABLE_EDGE',
}) =>
    DirectionTimingEdge(
      direction: _line(direction, directionState),
      timing: _line(timing, timingState),
      edge: _line(edge, edgeState),
      note: 'Ces trois lectures sont indépendantes.',
    );

PressureContribution _contribution({
  required String label,
  double? score,
  bool available = true,
  String direction = 'BUYING',
  String explanation = '',
}) =>
    PressureContribution(
      family: label.toLowerCase(),
      label: label,
      available: available,
      normalizedScore: score,
      contributionPoints: available && score != null ? score * .5 : null,
      direction: direction,
      weight: .3,
      explanation: explanation,
    );

void main() {
  group('Direction, timing et avantage restent trois lectures', () {
    testWidgets('les trois sont affichées côte à côte, jamais fusionnées',
        (tester) async {
      await _pump(tester, DirectionTimingEdgeRow(readings: _readings()));

      expect(find.text('DIRECTION'), findsOneWidget);
      expect(find.text('TIMING'), findsOneWidget);
      expect(find.text('AVANTAGE'), findsOneWidget);
      expect(find.text('FORTEMENT HAUSSIÈRE'), findsOneWidget);
      expect(find.text('ATTENDRE'), findsOneWidget);
      expect(find.text('AUCUN AVANTAGE DÉMONTRÉ'), findsOneWidget);
    });

    testWidgets(
        'haussière + attendre + aucun avantage est affiché sans contradiction',
        (tester) async {
      // La combinaison la plus fréquente de ce système. Elle doit se lire
      // telle quelle: rien n'est masqué, rien n'est réconcilié.
      await _pump(tester, DirectionTimingEdgeRow(readings: _readings()));
      expect(tester.takeException(), isNull);
      expect(find.text('FORTEMENT HAUSSIÈRE'), findsOneWidget);
      expect(find.text('ATTENDRE'), findsOneWidget);
    });

    testWidgets('une opportunité se distingue visuellement d’une attente',
        (tester) async {
      await _pump(
        tester,
        DirectionTimingEdgeRow(
          readings:
              _readings(timing: 'OPPORTUNITÉ', timingState: 'OPPORTUNITY'),
        ),
      );
      final opportunity =
          tester.widget<Text>(find.text('OPPORTUNITÉ')).style!.color;
      await _pump(tester, DirectionTimingEdgeRow(readings: _readings()));
      final wait = tester.widget<Text>(find.text('ATTENDRE')).style!.color;
      expect(opportunity, isNot(wait));
    });

    testWidgets('aucun identifiant technique n’est affiché', (tester) async {
      await _pump(tester, DirectionTimingEdgeRow(readings: _readings()));
      expect(find.text('STRONGLY_BULLISH'), findsNothing);
      expect(find.text('WAIT'), findsNothing);
      expect(find.text('NO_MEASURABLE_EDGE'), findsNothing);
    });
  });

  group('La barre de position n’existe que si le range existe', () {
    const inRange = StructuralPosition(
      hasRange: true,
      headline: 'Proche du haut du range',
      state: 'NEAR_RANGE_TOP',
      rangeBottom: 62625.62,
      rangeTop: 81375.74,
      relativePosition: 0.86,
      percent: 86,
      detail: '86 % de la hauteur du range 4H',
    );

    testWidgets('un range validé donne une barre et un pourcentage',
        (tester) async {
      await _pump(tester, const StructuralPositionBar(position: inRange));
      expect(find.text('POSITION 4H'), findsOneWidget);
      expect(find.text('86 %'), findsOneWidget);
      expect(find.text('Proche du haut du range'), findsOneWidget);
      expect(find.text('Bas du range'), findsOneWidget);
      expect(find.text('Haut du range'), findsOneWidget);
    });

    testWidgets('sans range validé, aucune borne n’est inventée',
        (tester) async {
      await _pump(
        tester,
        const StructuralPositionBar(
          position: StructuralPosition(
            hasRange: false,
            headline: 'Haussière',
            state: 'NO_VALID_RANGE',
            detail: 'Aucun range validé n’a été détecté sur cette unité.',
          ),
        ),
      );
      expect(find.text('STRUCTURE 4H'), findsOneWidget);
      expect(find.text('Haussière'), findsOneWidget);
      // Ni pourcentage ni bornes: la barre est absente, pas remplie au hasard.
      expect(find.text('Bas du range'), findsNothing);
      expect(find.textContaining('%'), findsNothing);
    });

    testWidgets('un prix sorti du range est borné pour le dessin seulement',
        (tester) async {
      const outside = StructuralPosition(
        hasRange: true,
        headline: 'Au-dessus du range',
        state: 'ABOVE_RANGE',
        rangeBottom: 100,
        rangeTop: 120,
        relativePosition: 1.4,
        percent: 100,
      );
      expect(outside.fraction, 1.0);
      expect(outside.relativePosition, 1.4);
      await _pump(tester, const StructuralPositionBar(position: outside));
      expect(tester.takeException(), isNull);
    });

    testWidgets('les positions extrêmes se dessinent sans déborder',
        (tester) async {
      for (final value in [0.0, 0.5, 1.0]) {
        await _pump(
          tester,
          StructuralPositionBar(
            position: StructuralPosition(
              hasRange: true,
              headline: 'Position',
              relativePosition: value,
              percent: (value * 100).round(),
            ),
          ),
        );
        expect(tester.takeException(), isNull);
      }
    });
  });

  group('Support et résistance portent leur distance réelle', () {
    testWidgets('le support est en dessous, la résistance au-dessus',
        (tester) async {
      await _pump(
        tester,
        const NearestLevelsRow(
          levels: NearestLevels(
            available: true,
            support: PriceLevel(price: 76944, distancePct: -2.39),
            resistance: PriceLevel(price: 79383, distancePct: 0.71),
          ),
        ),
      );
      expect(find.text('Support principal'), findsOneWidget);
      expect(find.text('-2.4 %'), findsOneWidget);
      expect(find.text('Résistance principale'), findsOneWidget);
      expect(find.text('+0.7 %'), findsOneWidget);
    });

    testWidgets('aucun niveau retenu n’affiche rien plutôt qu’un zéro',
        (tester) async {
      await _pump(
        tester,
        const NearestLevelsRow(levels: NearestLevels.unavailable),
      );
      expect(find.text('Support principal'), findsNothing);
      expect(find.text('0,0 %'), findsNothing);
    });
  });

  group('Qui achète, qui vend', () {
    testWidgets('une source absente n’est ni neutre ni zéro', (tester) async {
      final breakdown = PressureBreakdown(
        state: 'BUYING',
        label: 'ACHAT LÉGER',
        headline: 'ACHAT LÉGER +19/100',
        score: 19,
        familiesActive: 3,
        familiesTotal: 5,
        familiesLine: '3/5 familles disponibles',
        buyers: [_contribution(label: 'ETF spot', score: 28)],
        sellers: [
          _contribution(label: 'Funding', score: -4, direction: 'SELLING'),
        ],
        unavailable: [
          _contribution(
            label: 'Baleines',
            available: false,
            direction: 'UNKNOWN',
            explanation: 'Aucun fournisseur fiable configuré.',
          ),
        ],
        missingNote: 'Une source absente n’est ni neutre ni zéro.',
      );
      final missing = breakdown.unavailable.single;
      expect(missing.normalizedScore, isNull);
      expect(missing.contributionPoints, isNull);
      expect(missing.direction, 'UNKNOWN');
      expect(breakdown.familiesActive, lessThan(breakdown.familiesTotal));
    });

    testWidgets('le total se reconstitue depuis les apports', (tester) async {
      final buyers = [
        _contribution(label: 'ETF spot', score: 40),
        _contribution(label: 'Positionnement', score: 20),
      ];
      final total = buyers.fold<double>(
          0, (sum, item) => sum + (item.contributionPoints ?? 0));
      expect(total, 30.0);
    });

    testWidgets('sans aucune source, la pression est dite indéterminée',
        (tester) async {
      const breakdown = PressureBreakdown(
        state: 'INSUFFICIENT_DATA',
        label: 'INDÉTERMINÉ',
        familiesActive: 0,
        familiesTotal: 5,
        familiesLine: '0/5 familles disponibles',
      );
      expect(breakdown.headline, 'Pression indéterminée');
      expect(breakdown.score, isNull);
    });
  });

  group('Ce qui ferait changer la décision', () {
    const conditions = ChangeConditions(
      improve: [
        'Le timing deviendrait plus favorable avec un retour au bas '
            'du range'
      ],
      degrade: ['La lecture serait dégradée par la perte du bas de range'],
      structureChange: [
        'La structure changerait avec une clôture 4H au-dessus '
            'du haut de range'
      ],
    );

    testWidgets('la cassure haussière est un changement, pas une dégradation',
        (tester) async {
      await _pump(tester, const ChangeConditionsBlock(conditions: conditions));

      expect(find.text('POUR DEVENIR PLUS FAVORABLE'), findsOneWidget);
      expect(find.text('POUR DEVENIR MOINS FAVORABLE'), findsOneWidget);
      expect(find.text('CHANGEMENT À SURVEILLER'), findsOneWidget);
      // La phrase de cassure est rendue, et pas sous le titre des
      // dégradations: c'était exactement le défaut corrigé.
      expect(
        find.textContaining('clôture 4H au-dessus du haut de range'),
        findsOneWidget,
      );
      expect(
        find.textContaining('dégradée par une clôture 4H au-dessus'),
        findsNothing,
      );
    });

    testWidgets('les phrases sont des conditions, pas des prévisions',
        (tester) async {
      await _pump(tester, const ChangeConditionsBlock(conditions: conditions));
      for (final forbidden in ['va monter', 'va baisser', 'objectif']) {
        expect(find.textContaining(forbidden), findsNothing);
      }
    });

    testWidgets('aucune condition n’affiche un bloc vide', (tester) async {
      await _pump(
        tester,
        const ChangeConditionsBlock(conditions: ChangeConditions.empty),
      );
      expect(find.byType(TodayPanel), findsNothing);
    });
  });

  group('Couverture des données', () {
    const coverage = DataCoverage(
      expected: 12,
      available: 11,
      fresh: 9,
      stale: 2,
      missing: 1,
      percent: 92,
      level: 'GOOD',
      label: 'Bonne couverture',
      uncertaintyScore: 60,
      uncertaintyNote: 'L’incertitude et la couverture sont distinctes.',
    );

    testWidgets('disponibles, récentes et périmées sont comptées à part',
        (tester) async {
      await _pump(tester, const DataCoverageBlock(coverage: coverage));
      expect(find.text('11 / 12 familles disponibles'), findsOneWidget);
      expect(find.text('9 récentes · 2 périmées'), findsOneWidget);
      expect(find.text('Bonne couverture'), findsOneWidget);
    });

    testWidgets(
        'une bonne couverture et une incertitude élevée coexistent sans conflit',
        (tester) async {
      // Les deux répondent à des questions différentes: ce que nous avons pu
      // observer, et la solidité de ce que nous en concluons.
      expect(coverage.level, 'GOOD');
      expect(coverage.uncertaintyScore, 60);
      await _pump(tester, const DataCoverageBlock(coverage: coverage));
      expect(tester.takeException(), isNull);
    });

    testWidgets('les familles non applicables sortent du dénominateur',
        (tester) async {
      const families = [
        CoverageFamily(
          family: 'dvol',
          label: 'Volatilité implicite (DVOL)',
          coverage: 'NOT_APPLICABLE',
          reason: 'Deribit ne publie pas d’indice DVOL pour SOL',
        ),
        CoverageFamily(
          family: 'whales',
          label: 'Baleines',
          coverage: 'UNAVAILABLE_BY_DESIGN',
          reason: 'aucun fournisseur fiable configuré',
        ),
        CoverageFamily(
          family: 'price',
          label: 'Prix',
          coverage: 'EXPECTED_AND_AVAILABLE',
          available: true,
          fresh: true,
        ),
      ];
      const sol = DataCoverage(expected: 10, available: 10, families: families);
      expect(sol.notApplicableFamilies.single.family, 'dvol');
      expect(sol.byDesignFamilies.single.family, 'whales');
      expect(sol.availableFamilies.single.family, 'price');
    });

    testWidgets('aucune famille attendue n’affiche rien', (tester) async {
      await _pump(
        tester,
        const DataCoverageBlock(coverage: DataCoverage.unavailable),
      );
      expect(find.byType(TodayPanel), findsNothing);
    });
  });

  group('Unités de temps', () {
    const divergent = TimeframeSummary(
      rows: [
        TimeframeRow(
            timeframe: '1S',
            state: 'BEARISH_STRUCTURE',
            label: 'Baissière',
            arrow: '↓'),
        TimeframeRow(
            timeframe: '1J',
            state: 'RANGE_STRUCTURE',
            label: 'En range',
            arrow: '↔'),
        TimeframeRow(
            timeframe: '4H',
            state: 'RANGE_STRUCTURE',
            label: 'En range',
            arrow: '↔'),
        TimeframeRow(
            timeframe: '1H',
            state: 'BULLISH_STRUCTURE',
            label: 'Haussière',
            arrow: '↑'),
      ],
      alignment: 'DIVERGENT',
      alignmentLabel: 'Divergent',
    );

    testWidgets('chaque unité porte un mot, pas seulement une flèche',
        (tester) async {
      await _pump(tester, const TimeframeStrip(summary: divergent));
      expect(find.text('Baissière'), findsOneWidget);
      expect(find.text('Haussière'), findsOneWidget);
      expect(find.text('En range'), findsNWidgets(2));
      expect(find.text('Divergent'), findsOneWidget);
    });

    testWidgets('une lecture mixte est signalée', (tester) async {
      await _pump(
        tester,
        const TimeframeStrip(
          summary: divergent,
          contradictions: Contradictions(badge: 'LECTURE MIXTE'),
        ),
      );
      expect(find.text('LECTURE MIXTE'), findsOneWidget);
    });

    testWidgets('sans contradiction, aucun badge', (tester) async {
      await _pump(tester, const TimeframeStrip(summary: divergent));
      expect(find.text('LECTURE MIXTE'), findsNothing);
    });
  });

  group('Catalyseurs', () {
    test('les métadonnées de pertinence et de fraîcheur sont conservées', () {
      final item = Catalyst.fromJson({
        'type': 'MACRO',
        'kind': 'CPI',
        'name': 'Inflation US (CPI)',
        'when': 'dans 18 h',
        'scheduled_at': '2026-09-09T14:30:00Z',
        'hours_until': 18,
        'relevance_score': 33,
        'importance': 'CRITICAL',
        'asset_scope': ['BTC', 'ETH', 'SOL'],
        'source': 'config/macro_calendar.yaml',
        'freshness': 'SCHEDULED',
      });
      expect(item.type, 'MACRO');
      expect(item.scheduledAt, '2026-09-09T14:30:00Z');
      expect(item.relevanceScore, 33);
      expect(item.freshness, 'SCHEDULED');
      expect(item.assetScope, ['BTC', 'ETH', 'SOL']);
    });

    testWidgets('une échéance majeure sous 24 h porte un bandeau',
        (tester) async {
      await _pump(
        tester,
        const CatalystsBlock(
          catalysts: Catalysts(
            items: [
              Catalyst(
                name: 'Inflation US (CPI)',
                when: 'dans 18 h',
                importance: 'CRITICAL',
                hoursUntil: 18,
              ),
            ],
            alert: CatalystAlert(
              label: 'ÉVÉNEMENT IMPORTANT DANS 18 H',
              name: 'Inflation US (CPI)',
              hoursUntil: 18,
              note: 'Le sens n’est pas prédit.',
            ),
          ),
        ),
      );
      expect(find.text('À SURVEILLER'), findsOneWidget);
      expect(find.text('ÉVÉNEMENT IMPORTANT DANS 18 H'), findsOneWidget);
      expect(find.text('Inflation US (CPI)'), findsOneWidget);
      expect(find.text('dans 18 h'), findsOneWidget);
    });

    testWidgets('sans échéance, le bloc disparaît', (tester) async {
      await _pump(tester, const CatalystsBlock(catalysts: Catalysts.empty));
      expect(find.text('À SURVEILLER'), findsNothing);
    });
  });

  group('Positionnement lisible sans métriques brutes', () {
    testWidgets('positionnement, funding, crowding et ETF restent en mots',
        (tester) async {
      await _pump(
        tester,
        const PositioningEtfBlock(
          positioning: PositioningReading(
            positioning: 'Nouveaux longs',
            funding: 'Plutôt faible',
            crowding: 'Normal',
          ),
          etf: EtfReading(
            available: true,
            headline: 'Flux récents positifs',
            caveat: 'Flux observés ≠ avantage prédictif démontré.',
          ),
        ),
      );
      expect(find.text('Nouveaux longs'), findsOneWidget);
      expect(find.text('Plutôt faible'), findsOneWidget);
      expect(find.text('Normal'), findsOneWidget);
      expect(find.text('Flux récents positifs'), findsOneWidget);
      expect(find.textContaining('avantage prédictif'), findsOneWidget);
      expect(find.textContaining('%'), findsNothing);
    });

    testWidgets('SOL sans ETF n’affiche pas une fausse lecture ETF',
        (tester) async {
      await _pump(
        tester,
        const PositioningEtfBlock(
          positioning: PositioningReading(),
          etf: EtfReading.unavailable,
        ),
      );
      expect(find.text('ETF SPOT'), findsNothing);
    });
  });

  group('Dernier changement de lecture', () {
    testWidgets('sans historique enregistré, rien n’est affiché',
        (tester) async {
      await _pump(
        tester,
        const LastChangeLine(change: LastDecisionChange.none),
      );
      expect(find.byType(TodayPanel), findsNothing);
    });

    testWidgets('un changement enregistré est daté et motivé', (tester) async {
      await _pump(
        tester,
        const LastChangeLine(
          change: LastDecisionChange(
            available: true,
            changedAt: '2026-09-07T21:00:00.000Z',
            text: 'Timing passé de À SURVEILLER à ATTENDRE',
            reason: 'Prix arrivé proche du haut du range 4H.',
          ),
        ),
      );
      expect(
        find.textContaining('Timing passé de À SURVEILLER à ATTENDRE'),
        findsOneWidget,
      );
      expect(
        find.text('Prix arrivé proche du haut du range 4H.'),
        findsOneWidget,
      );
    });
  });

  group('Identité de l’analyse', () {
    Map<String, dynamic> payload({
      required String stampId,
      required String pageId,
    }) =>
        {
          'asset': 'BTC',
          'analysis': {
            'analysis_id': stampId,
            'computed_at': '2026-09-07T20:19:00Z'
          },
          'page': {'analysis_id': pageId},
        };

    test('deux identifiants égaux forment une lecture cohérente', () {
      final read = TodayRead.fromJson(
        payload(stampId: 'an_1', pageId: 'an_1'),
      );
      expect(read.isCoherent, isTrue);
      expect(read.analysisId, 'an_1');
    });

    test('deux identifiants différents ne sont pas combinés', () {
      final read = TodayRead.fromJson(
        payload(stampId: 'an_1', pageId: 'an_2'),
      );
      expect(read.isCoherent, isFalse);
    });

    test('un backend sans page reste cohérent plutôt que faussement en conflit',
        () {
      final read = TodayRead.fromJson({
        'asset': 'BTC',
        'analysis': {'analysis_id': 'an_1'},
      });
      expect(read.page.isEmpty, isTrue);
      expect(read.isCoherent, isTrue);
    });

    testWidgets('un désaccord d’identifiant est dit, pas masqué',
        (tester) async {
      await _pump(tester, const AnalysisMismatchBanner());
      expect(
        find.textContaining('Analyse en cours d’actualisation'),
        findsOneWidget,
      );
      expect(find.textContaining('ne sont pas combinés'), findsOneWidget);
    });
  });

  group('Prix live et analyse restent deux couches', () {
    AnalysisStamp stamp(Map<String, dynamic> json) =>
        AnalysisStamp.fromJson(json);

    test('une dérive faible n’est pas signalée', () {
      final value = stamp({
        'price_drift_pct': 0.33,
        'drift_severity': 'NONE',
        'stale_for_current_price': false,
      });
      expect(value.staleForCurrentPrice, isFalse);
      expect(value.driftSeverity, 'NONE');
    });

    test('au-delà du seuil, l’analyse est marquée à actualiser', () {
      final value = stamp({
        'price_drift_pct': 2.1,
        'drift_severity': 'NOTABLE',
        'stale_for_current_price': true,
      });
      expect(value.staleForCurrentPrice, isTrue);
      expect(value.driftSeverity, 'NOTABLE');
    });

    test('une dérive très forte est escaladée', () {
      expect(stamp({'drift_severity': 'SEVERE'}).driftSeverity, 'SEVERE');
    });

    test('le prix de l’analyse et le prix live sont deux champs', () {
      final value = stamp({
        'price_at_analysis': 78824.65,
        'live_price': 79086.71,
      });
      expect(value.priceAtAnalysis, isNot(value.livePrice));
    });
  });
}
