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
}
