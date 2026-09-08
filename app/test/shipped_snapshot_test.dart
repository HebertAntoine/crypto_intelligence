/// Ce qui est réellement livré, rendu réellement.
///
/// Les autres tests utilisent des fixtures écrites à la main : ils prouvent que
/// l'écran sait rendre une forme, pas que le fichier embarqué dans l'app a
/// cette forme. C'est exactement l'écart qui a laissé « ACHAT DOMINANT » dans
/// `assets/api_snapshots/today__BTC.json` alors que le moteur ne produisait
/// plus ce mot : personne ne lisait le fichier livré.
///
/// Ce test lit les trois instantanés du dossier d'assets, tels qu'ils seront
/// empaquetés, et les fait traverser le modèle puis l'écran.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto_intelligence_app/api/client.dart';
import 'package:crypto_intelligence_app/api/models.dart';
import 'package:crypto_intelligence_app/screens/today_screen.dart';
import 'package:crypto_intelligence_app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _assets = ['BTC', 'ETH', 'SOL'];

Map<String, dynamic> _shipped(String asset) {
  final file = File('assets/api_snapshots/today__$asset.json');
  expect(file.existsSync(), isTrue,
      reason: 'l’instantané livré pour $asset est absent du bundle');
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

ApiClient _clientFromShipped() => ApiClient(
      baseUrl: '',
      loadAsset: (path) async {
        final file = File(path);
        if (!file.existsSync()) throw Exception('asset absent: $path');
        return file.readAsStringSync();
      },
    );

void main() {
  group('Les instantanés livrés portent la lecture actuelle', () {
    for (final asset in _assets) {
      test('$asset : la pression est nommée sous contrainte de couverture', () {
        final read = TodayRead.fromJson(_shipped(asset));
        final pressure = read.page.pressure;

        expect(read.page.isEmpty, isFalse,
            reason: 'l’instantané livré ne contient pas la page compacte');
        expect(pressure.familiesTotal, greaterThan(0));

        // Le mot « dominant » exige une couverture forte ET un déséquilibre
        // franc. C'est le défaut qui a motivé tout ce travail.
        if (pressure.label.contains('DOMINANT')) {
          expect(pressure.coverageLevel, 'STRONG',
              reason: '« dominant » annoncé sur une couverture '
                  '${pressure.coverageLevel}');
          expect((pressure.score ?? 0).abs(), greaterThanOrEqualTo(45));
        }

        // Une famille absente ne porte aucun chiffre.
        for (final family in pressure.unavailable) {
          expect(family.normalizedScore, isNull);
          expect(family.weightedContribution, isNull);
          expect(family.reason, isNotEmpty,
              reason: '${family.family} est absente sans dire pourquoi');
        }
        // Une famille sans objet ne compte pas dans la couverture.
        expect(
          pressure.familiesTotal,
          pressure.familiesActive + pressure.unavailable.length,
        );
      });

      test('$asset : la page ne se répète pas', () {
        final read = TodayRead.fromJson(_shipped(asset));
        final page = read.page;

        // La position est portée par la barre structurelle, pas aussi par le
        // contexte immédiat.
        expect(
          page.immediateContext.map((item) => item.label),
          isNot(contains('Position')),
        );
        // Une échéance unique et lointaine reste dans le contexte et ne
        // reprend pas un bloc à elle.
        if (!page.catalysts.addsInformation) {
          expect(page.catalysts.items.length, lessThanOrEqualTo(1));
        }
      });

      test('$asset : les textes tiennent les règles de longueur', () {
        final page = TodayRead.fromJson(_shipped(asset)).page;

        expect(page.decision.sentence.split(' ').length, lessThanOrEqualTo(30),
            reason: page.decision.sentence);
        for (final group in [
          page.changeConditions.improve,
          page.changeConditions.degrade,
          page.changeConditions.structureChange,
        ]) {
          for (final condition in group) {
            expect(condition.title.split(' ').length, lessThanOrEqualTo(6),
                reason: condition.title);
            expect(condition.detail, isNotEmpty);
          }
        }
      });

      test('$asset : aucun objet brut ne traverse jusqu’au texte', () {
        // « {detail: ..., title: ...} » s'affichait littéralement: le backend
        // avait structuré les conditions et le lecteur les interpolait encore
        // comme des chaînes. Interpoler un objet est toujours un défaut
        // d'affichage, jamais un texte.
        final read = TodayRead.fromJson(_shipped(asset));
        final texts = <String>[
          read.opportunity.summary,
          read.opportunity.headline,
          ...read.opportunity.whatWouldImprove,
          ...read.opportunity.whatWouldDeteriorate,
          ...read.opportunity.whatWouldChangeStructure,
          ...read.page.changeConditions.improve.map((c) => c.title + c.detail),
          ...read.page.changeConditions.degrade.map((c) => c.title + c.detail),
          ...read.page.changeConditions.structureChange
              .map((c) => c.title + c.detail),
          ...read.page.immediateContext.map((i) => '${i.label} ${i.value}'),
          ...read.page.pressure.applicableFamilies.map((f) => f.sentence),
        ];
        for (final text in texts) {
          expect(text, isNot(startsWith('{')), reason: text);
          expect(text.contains('title:'), isFalse, reason: text);
          expect(text.contains('detail:'), isFalse, reason: text);
          expect(text.contains('Instance of'), isFalse, reason: text);
        }
        // Et la forme structurée est bien lue, pas seulement contournée.
        expect(read.opportunity.whatWouldImprove, isNotEmpty);
        expect(read.opportunity.whatWouldImprove.first, contains('—'));
      });

      test('$asset : aucun chiffre de recherche sur la lecture principale', () {
        final page = TodayRead.fromJson(_shipped(asset)).page;
        final surface = [
          page.decision.sentence,
          page.readings.direction.value,
          page.readings.timing.value,
          page.readings.edge.value,
          page.position.headline,
          ...page.immediateContext.map((item) => '${item.label} ${item.value}'),
        ].join(' ').toLowerCase();

        for (final forbidden in [
          'p_value', 'p-value', 'fdr', 'effective_n', 'mfe', 'mae', 'r²'
        ]) {
          expect(surface.contains(forbidden), isFalse, reason: forbidden);
        }
      });
    }

    testWidgets('l’écran rend les trois instantanés livrés sans exception',
        (tester) async {
      tester.view.physicalSize = const Size(430, 932);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.dark,
        home: TodayScreen(client: _clientFromShipped()),
      ));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // La lecture principale est là, pas un écran d'erreur.
      expect(find.text('DIRECTION'), findsWidgets);
      expect(find.text('TIMING'), findsWidgets);
      expect(find.text('QUI ACHÈTE, QUI VEND ?'), findsWidgets);
      // Et le mot interdit sur une couverture faible n'y est pas.
      expect(find.textContaining('ACHAT DOMINANT'), findsNothing);
    });
  });

  // --- les figures réellement livrées ------------------------------------
  //
  // Même écart que pour « ACHAT DOMINANT » : l'app savait dessiner une
  // géométrie, mais les fichiers embarqués dataient d'avant l'endpoint et ne
  // contenaient pas la clé. Hors ligne, le graphique restait donc vide sans
  // que rien ne le signale.
  group('Les instantanés /chart livrés portent la géométrie', () {
    final files = Directory('assets/api_snapshots')
        .listSync()
        .whereType<File>()
        .where((file) => file.uri.pathSegments.last.startsWith('chart__'))
        .toList()
      ..sort((a, b) => a.path.compareTo(b.path));

    test('il y a bien quinze vues livrées', () {
      expect(files, hasLength(15));
    });

    for (final file in files) {
      final name = file.uri.pathSegments.last;
      test('$name : la clé structural_patterns est présente', () {
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        expect(json.containsKey('structural_patterns'), isTrue,
            reason: '$name a été exporté par un backend trop ancien');
      });

      test('$name : toute figure traçable tombe dans la fenêtre', () {
        final read =
            ChartRead.fromJson(jsonDecode(file.readAsStringSync()) as Map<String, dynamic>);
        if (read.candles.isEmpty) return;
        final times = read.candles
            .map((candle) => candle.time)
            .whereType<DateTime>()
            .map((time) => time.toUtc())
            .toList();
        final first = times.first, last = times.last;

        for (final pattern in read.structuralPatterns) {
          if (!pattern.isDrawable) continue;
          for (final point in pattern.geometry.points) {
            expect(point.price.isFinite && point.price > 0, isTrue,
                reason: '${pattern.name}: prix invalide sur ${point.role}');
            // Une marge d'une barre suffit: `extend` prolonge volontairement
            // certaines droites au-delà de la dernière bougie, mais un point
            // nommé hors fenêtre serait dessiné dans le vide.
            expect(point.time.isBefore(first), isFalse,
                reason: '${pattern.name}: ${point.role} précède la fenêtre');
            expect(point.time.isAfter(last), isFalse,
                reason: '${pattern.name}: ${point.role} dépasse la fenêtre');
          }
        }
      });
    }
  });
}
