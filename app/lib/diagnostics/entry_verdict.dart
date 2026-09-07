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

  // Le backend décide. Le frontend n'a le droit de trancher que si le backend
  // n'a rien renvoyé - une version antérieure, par exemple. Recalculer ici en
  // parallèle créerait deux vérités qui finiraient par diverger.
  final decision = read.opportunity;
  if (!decision.isEmpty) {
    return EntryVerdict(
      answer: switch (decision.state) {
        'STRONG_OPPORTUNITY' || 'OPPORTUNITY' => EntryAnswer.active,
        'WATCH' || 'WAIT' => EntryAnswer.watch,
        'UNFAVORABLE' => EntryAnswer.no,
        _ => EntryAnswer.impossible,
      },
      side: side,
      headline: decision.headline,
      reason: decision.summary,
    );
  }

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

/// Le sens d'un point de justification.
enum PointSign { favourable, against, neutral, missing }

class VerdictPoint {
  final PointSign sign;
  final String title;
  final String detail;

  const VerdictPoint({
    required this.sign,
    required this.title,
    required this.detail,
  });
}

/// Les points qui justifient le verdict, dans l'ordre où ils pèsent.
///
/// Chacun vient d'une mesure du payload. Un point « manquant » est affiché
/// comme manquant plutôt que passé sous silence: ne pas savoir est aussi une
/// raison de ne pas agir.
List<VerdictPoint> verdictPoints(TodayRead read) {
  final decision = read.opportunity;
  if (!decision.isEmpty) {
    // Les facteurs viennent du backend, déjà classés par polarité et triés
    // par importance. On les rend tels quels.
    return [
      for (final f in decision.positives)
        VerdictPoint(
            sign: PointSign.favourable, title: f.title, detail: f.explanation),
      for (final f in decision.waits)
        VerdictPoint(
            sign: PointSign.neutral, title: f.title, detail: f.explanation),
      for (final f in decision.negatives)
        VerdictPoint(
            sign: PointSign.against, title: f.title, detail: f.explanation),
      for (final f in decision.missing)
        VerdictPoint(
            sign: PointSign.missing, title: f.title, detail: f.explanation),
    ];
  }

  final points = <VerdictPoint>[];
  final teste = read.admittedCount + read.rejectedCount;

  // 1. L'avantage statistique décide du verdict, il vient donc en premier.
  if (teste == 0) {
    points.add(const VerdictPoint(
      sign: PointSign.missing,
      title: 'Aucune relation testée',
      detail: 'Rien n’a encore été mesuré sur cet actif.',
    ));
  } else if (read.admittedCount == 0) {
    points.add(VerdictPoint(
      sign: PointSign.against,
      title: 'Aucun avantage statistique',
      detail: '$teste relation${teste > 1 ? 's' : ''} testée'
          '${teste > 1 ? 's' : ''}, aucune n’a franchi les filtres.',
    ));
  } else {
    points.add(VerdictPoint(
      sign: PointSign.favourable,
      title: '${read.admittedCount} relation validée',
      detail: 'sur $teste testées.',
    ));
  }

  // 2. Le moment d'entrée, avec son score.
  final timing = read.timingScore;
  if (timing != null) {
    points.add(VerdictPoint(
      sign: timing >= 25
          ? PointSign.favourable
          : timing <= -25
              ? PointSign.against
              : PointSign.neutral,
      title: 'Moment d’entrée ${timing >= 0 ? '+' : ''}'
          '${timing.toStringAsFixed(0)}/100',
      detail: timing.abs() < 25
          ? 'Ni favorable ni défavorable: rien n’appelle à agir maintenant.'
          : timing > 0
              ? 'Conditions techniques plutôt favorables.'
              : 'Conditions techniques défavorables.',
    ));
  }

  // 3. Qui achète et qui vend, composante par composante.
  for (final component in read.pressure.components) {
    if (!component.available) {
      points.add(VerdictPoint(
        sign: PointSign.missing,
        title: component.label,
        detail: component.reason,
      ));
      continue;
    }
    final score = component.score ?? 0;
    points.add(VerdictPoint(
      sign: score > 15
          ? PointSign.favourable
          : score < -15
              ? PointSign.against
              : PointSign.neutral,
      title: component.label,
      detail: component.detail,
    ));
  }

  // 4. Les échéances macro proches: elles ne prédisent rien, mais attendre
  //    une publication programmée est une raison défendable de ne pas entrer.
  for (final event in read.upcomingMacro) {
    if (event.daysUntil > 7 && !event.isCritical) continue;
    points.add(VerdictPoint(
      sign: event.daysUntil <= 3 && event.isCritical
          ? PointSign.against
          : PointSign.neutral,
      title: '${event.name} dans ${event.daysUntil.toStringAsFixed(0)} j',
      detail: event.isCritical
          ? 'Échéance majeure: la volatilité augmente souvent autour.'
          : 'Échéance programmée à connaître.',
    ));
  }

  // 5. L'incertitude, et ce qu'elle veut dire.
  final incertitude = read.uncertaintyScore;
  points.add(VerdictPoint(
    sign: incertitude <= 25
        ? PointSign.favourable
        : incertitude >= 60
            ? PointSign.against
            : PointSign.neutral,
    title: 'Incertitude ${incertitude.toStringAsFixed(0)}/100',
    detail: incertitude <= 25
        ? 'Les signaux concordent.'
        : incertitude >= 60
            ? 'Plusieurs éléments manquent ou se contredisent.'
            : 'Lecture exploitable, sans être nette.',
  ));

  // 6. Les entrées trop anciennes pour servir.
  final perimees = read.families.entries
      .where((entry) => !entry.value.usableNow())
      .map((entry) => entry.key)
      .toList();
  if (perimees.isNotEmpty) {
    points.add(VerdictPoint(
      sign: PointSign.against,
      title: '${perimees.length} donnée(s) trop ancienne(s)',
      detail: 'Elles ne décrivent plus le marché actuel.',
    ));
  }

  return points;
}
