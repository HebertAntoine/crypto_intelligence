/// « Peut-on acheter ? » — la réponse doit être nette, et jamais un conseil.
library;

import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/diagnostics/entry_verdict.dart';
import 'package:flutter_test/flutter_test.dart';

TodayRead _read({
  EdgeState edge = EdgeState.noMeasurableEdge,
  int admitted = 0,
  int rejected = 3,
  double uncertainty = 40,
  bool actionable = false,
  bool allowsAction = true,
}) =>
    TodayRead(
      asset: 'BTC',
      marketData: null,
      summary: DecisionSummary(
        asset: 'BTC',
        marketDirection: 'STRONGLY_BULLISH',
        directionConfidence: '80.0',
        entryTiming: 'UNDETERMINED',
        edgeState: edge,
        crowding: 'NORMAL',
        volatilityRegime: 'LOW',
        uncertainty: uncertainty,
        actionable: actionable,
        statement: '',
        caveats: const [],
      ),
      directionSource: '',
      edgeState: edge,
      admittedCount: admitted,
      rejectedCount: rejected,
      edgeStatement: '',
      uncertaintyLevel: 'MODERATE',
      uncertaintyScore: uncertainty,
      uncertaintyDrivers: const [],
      crowdingLevel: 'NORMAL',
      crowdingScore: 56,
      crowdingDirection: 'UNKNOWN',
      leverageState: 'QUIET',
      fundingBand: 'NEUTRAL',
      fundingPercentile: 25,
      volatilityRegime: 'LOW',
      allowsAction: allowsAction,
    );

void main() {
  group('La réponse est un non, pas un haussement d’épaules', () {
    test('trois relations testées, zéro validée: NON', () {
      final verdict = entryVerdict(_read());
      expect(verdict.answer, EntryAnswer.no);
      expect(verdict.headline, 'NON');
      expect(verdict.reason, contains('3 relations testées'));
    });

    test('la hausse du marché ne suffit jamais à dire oui', () {
      // Régime fortement haussier, mais aucun avantage mesuré.
      final verdict = entryVerdict(_read());
      expect(verdict.isNo, isTrue);
      expect(verdict.reason, contains('n’est pas un signal d’achat'));
    });

    test('rien testé n’est pas la même chose que testé et rejeté', () {
      final verdict = entryVerdict(
        _read(edge: EdgeState.notYetTested, rejected: 0),
      );
      expect(verdict.answer, EntryAnswer.no);
      expect(verdict.reason, contains('n’a encore été testée'));
    });

    test('historique insuffisant: absence de preuve, pas de signal', () {
      final verdict = entryVerdict(_read(edge: EdgeState.insufficientData));
      expect(verdict.answer, EntryAnswer.no);
      expect(verdict.reason, contains('absence de preuve'));
    });
  });

  group('Les données commandent', () {
    test('des données périmées rendent la question sans réponse', () {
      final verdict = entryVerdict(_read(allowsAction: false));
      expect(verdict.answer, EntryAnswer.impossible);
      expect(verdict.headline, 'ANALYSE IMPOSSIBLE');
    });

    test('des données périmées passent avant tout le reste', () {
      // Même avec un avantage validé et actionnable.
      final verdict = entryVerdict(_read(
        edge: EdgeState.positiveEdge, admitted: 2, rejected: 1,
        actionable: true, uncertainty: 20, allowsAction: false,
      ));
      expect(verdict.answer, EntryAnswer.impossible);
    });
  });

  group('Un avantage validé ne devient pas un ordre', () {
    test('avantage validé mais incertitude haute: pas maintenant', () {
      final verdict = entryVerdict(_read(
        edge: EdgeState.positiveEdge, admitted: 1, rejected: 2,
        uncertainty: 75, actionable: true,
      ));
      expect(verdict.answer, EntryAnswer.watch);
      expect(verdict.headline, 'PAS MAINTENANT');
    });

    test('avantage validé mais conditions non réunies: pas maintenant', () {
      final verdict = entryVerdict(_read(
        edge: EdgeState.positiveEdge, admitted: 1, rejected: 2,
        uncertainty: 30, actionable: false,
      ));
      expect(verdict.answer, EntryAnswer.watch);
    });

    test('même au mieux, l’app ne dit jamais d’acheter', () {
      final verdict = entryVerdict(_read(
        edge: EdgeState.positiveEdge, admitted: 1, rejected: 2,
        uncertainty: 20, actionable: true,
      ));
      expect(verdict.answer, EntryAnswer.active);
      expect(verdict.headline, 'SIGNAL VALIDÉ');
      expect(verdict.headline, isNot(contains('ACHET')));
      expect(verdict.reason, contains('n’est pas un conseil'));
    });

    test('un avantage défavorable reste un non', () {
      final verdict = entryVerdict(_read(edge: EdgeState.negativeEdge));
      expect(verdict.answer, EntryAnswer.no);
      expect(verdict.reason, contains('défavorablement'));
    });

    test('un avantage instable reste un non', () {
      final verdict = entryVerdict(_read(edge: EdgeState.unstable));
      expect(verdict.answer, EntryAnswer.no);
      expect(verdict.reason, contains('pas stable'));
    });
  });

  test('aucun verdict ne contient d’impératif d’achat ou de vente', () {
    for (final verdict in [
      entryVerdict(_read()),
      entryVerdict(_read(allowsAction: false)),
      entryVerdict(_read(edge: EdgeState.notYetTested, rejected: 0)),
      entryVerdict(_read(
        edge: EdgeState.positiveEdge, admitted: 1, uncertainty: 20,
        actionable: true,
      )),
    ]) {
      final texte = '${verdict.headline} ${verdict.reason}'.toUpperCase();
      for (final interdit in ['ACHÈTE', 'ACHETEZ', 'VENDS', 'VENDEZ']) {
        expect(texte.contains(interdit), isFalse, reason: interdit);
      }
    }
  });
}
