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

  /// Le mot que l'écran affiche en grand.
  final String headline;

  /// Pourquoi, en une phrase, sans jargon.
  final String reason;

  const EntryVerdict({
    required this.answer,
    required this.headline,
    required this.reason,
  });

  bool get isNo => answer == EntryAnswer.no;
}

/// Décide à partir des états structurés, jamais d'un texte.
EntryVerdict entryVerdict(TodayRead read) {
  final tested = read.admittedCount + read.rejectedCount;

  // 1. Rien ne peut être conclu si les données ne portent plus le présent.
  if (!read.allowsAction) {
    return EntryVerdict(
      answer: EntryAnswer.impossible,
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
    return EntryVerdict(
      answer: EntryAnswer.no,
      headline: 'NON',
      reason: '$tested relation${tested > 1 ? 's' : ''} testée'
          '${tested > 1 ? 's' : ''}, $detail. La tendance du marché n’est pas '
          'un signal d’achat: une hausse peut continuer sans qu’il existe le '
          'moindre avantage mesurable à entrer maintenant.',
    );
  }

  // 4. Un signal existe mais l'incertitude est trop haute pour s'y fier.
  if (read.uncertaintyScore >= 60) {
    return EntryVerdict(
      answer: EntryAnswer.watch,
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
      headline: 'PAS MAINTENANT',
      reason: '${read.admittedCount} relation validée, mais les conditions '
          'd’entrée ne sont pas réunies aujourd’hui.',
    );
  }

  return EntryVerdict(
    answer: EntryAnswer.active,
    headline: 'SIGNAL VALIDÉ',
    reason: '${read.admittedCount} relation validée est active et les données '
        'sont à jour. Ce constat n’est pas un conseil: l’application ne passe '
        'jamais d’ordre et ne dit pas quoi faire.',
  );
}
