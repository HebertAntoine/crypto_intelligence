/// La réponse à « est-ce que je peux acheter ? », en une ligne.
///
/// L'écran disait « Opportunité d'entrée : INDÉTERMINÉ », ce qui se lit comme
/// « on ne sait pas ». Ce n'est pas ce que le système dit. Il dit : trois
/// relations ont été testées, zéro n'a survécu, donc il n'y a aucun signal
/// validé aujourd'hui. C'est un non, et un non se dit.
///
/// Ce fichier ne donne jamais de conseil. Il ne produit pas « achète ». Au
/// mieux il constate qu'un setup statistiquement validé est actif, et laisse
/// la décision à la personne qui lit.
library;

import '../api/models.dart';

/// Le sens du verdict, quand il y en a un.
enum VerdictSide { buy, sell, none }

enum EntryAnswer {
  /// Les données ne permettent pas de répondre.
  impossible,

  /// Non: aucune relation validée, ou rien n'a encore été testé.
  no,

  /// Un signal existe mais les conditions ne sont pas réunies.
  watch,

  /// Un setup validé est actif. À évaluer, jamais à exécuter automatiquement.
  active;
}

class EntryVerdict {
  final EntryAnswer answer;

  /// Acheter, vendre, ou ni l'un ni l'autre. Un régime baissier sans avantage
  /// mesuré n'est pas davantage un signal de vente qu'un régime haussier n'est
  /// un signal d'achat.
  final VerdictSide side;

  /// Le mot que l'écran affiche en grand.
  final String headline;

  /// Pourquoi, en une phrase, sans jargon.
  final String reason;

  const EntryVerdict({
    required this.answer,
    required this.headline,
    required this.reason,
    this.side = VerdictSide.none,
  });

  bool get isNo => answer == EntryAnswer.no;
}

/// Décide à partir des états structurés, jamais d'un texte.
/// La question que la page pose, selon le régime.
///
/// En tendance baissière, « est-ce une opportunité d'achat ? » est la mauvaise
/// question: ce qu'on veut savoir, c'est s'il faut sortir. Le verdict est le
/// même - il dépend de l'avantage mesuré, pas du régime - mais l'intitulé
/// s'adapte.
String verdictQuestion(TodayRead read) {
  final direction = read.summary.marketDirection.toUpperCase();
  if (direction.contains('BEARISH')) return 'FAUT-IL VENDRE ?';
  if (direction.contains('BULLISH')) return 'EST-CE UNE OPPORTUNITÉ D’ACHAT ?';
  return 'FAUT-IL AGIR ?';
}

VerdictSide _sideFor(TodayRead read) {
  final direction = read.summary.marketDirection.toUpperCase();
  if (direction.contains('BEARISH')) return VerdictSide.sell;
  if (direction.contains('BULLISH')) return VerdictSide.buy;
  return VerdictSide.none;
}

EntryVerdict entryVerdict(TodayRead read) {
  final tested = read.admittedCount + read.rejectedCount;
  final side = _sideFor(read);

  // 1. Rien ne peut être conclu si les données ne portent plus le présent.
  if (!read.allowsAction) {
    return EntryVerdict(
      answer: EntryAnswer.impossible,
      side: VerdictSide.none,
      headline: 'ANALYSE IMPOSSIBLE',
      reason: 'Les données disponibles sont trop anciennes pour dire quoi que '
          'ce soit du marché actuel.',
    );
  }

  // 2. Rien testé n'est pas la même chose que testé et rejeté.
  if (read.edgeState == EdgeState.notYetTested || tested == 0) {
    return const EntryVerdict(
      answer: EntryAnswer.no,
      headline: 'NON',
      reason: 'Aucune relation n’a encore été testée pour cet actif. En '
          'l’absence de test, il n’y a rien à suivre.',
    );
  }

  if (read.edgeState == EdgeState.insufficientData) {
    return const EntryVerdict(
      answer: EntryAnswer.no,
      headline: 'NON',
      reason: 'L’historique disponible ne suffit pas à conclure. Ce n’est pas '
          'une absence de signal, c’est une absence de preuve.',
    );
  }

  // 3. Le cas courant, et de loin: testé, rien ne survit.
  if (read.edgeState == EdgeState.noMeasurableEdge ||
      read.edgeState == EdgeState.negativeEdge ||
      read.edgeState == EdgeState.unstable ||
      read.edgeState == EdgeState.unknown ||
      read.admittedCount == 0) {
    final detail = switch (read.edgeState) {
      EdgeState.negativeEdge =>
        'la relation testée joue défavorablement',
      EdgeState.unstable => 'le signal mesuré n’est pas stable dans le temps',
      _ => 'aucune n’a franchi l’ensemble des filtres',
    };
    // Le même raisonnement vaut dans les deux sens: un régime ne fabrique pas
    // un signal, quelle que soit sa couleur.
    final mise = switch (side) {
      VerdictSide.sell =>
        'La baisse du marché n’est pas un signal de vente: elle peut se '
            'poursuivre sans qu’il existe le moindre avantage mesurable à '
            'sortir maintenant.',
      VerdictSide.buy =>
        'La hausse du marché n’est pas un signal d’achat: elle peut se '
            'poursuivre sans qu’il existe le moindre avantage mesurable à '
            'entrer maintenant.',
      VerdictSide.none =>
        'Le régime du marché, quel qu’il soit, ne constitue pas un signal.',
    };
    return EntryVerdict(
      answer: EntryAnswer.no,
      side: side,
      headline: side == VerdictSide.sell ? 'NON, RIEN NE L’IMPOSE' : 'NON',
      reason: '$tested relation${tested > 1 ? 's' : ''} testée'
          '${tested > 1 ? 's' : ''}, $detail. $mise',
    );
  }

  // 4. Un signal existe mais l'incertitude est trop haute pour s'y fier.
  if (read.uncertaintyScore >= 60) {
    return EntryVerdict(
      answer: EntryAnswer.watch,
      side: side,
      headline: 'PAS MAINTENANT',
      reason: '${read.admittedCount} relation validée, mais l’incertitude est '
          'de ${read.uncertaintyScore.toStringAsFixed(0)}/100. À surveiller, '
          'pas à suivre en l’état.',
    );
  }

  // 5. Le moteur lui-même refuse de qualifier l'entrée.
  if (!read.summary.actionable) {
    return EntryVerdict(
      answer: EntryAnswer.watch,
      side: side,
      headline: 'PAS MAINTENANT',
      reason: '${read.admittedCount} relation validée, mais les conditions '
          'd’entrée ne sont pas réunies aujourd’hui.',
    );
  }

  return EntryVerdict(
    answer: EntryAnswer.active,
    side: side,
    headline: side == VerdictSide.sell
        ? 'SIGNAL DE SORTIE VALIDÉ'
        : 'SIGNAL VALIDÉ',
    reason: '${read.admittedCount} relation validée est active et les données '
        'sont à jour. Ce constat n’est pas un conseil: l’application ne passe '
        'jamais d’ordre et ne dit pas quoi faire.',
  );
}
