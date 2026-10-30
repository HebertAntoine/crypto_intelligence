/// Historique traçable des alertes privées Lexa.
///
/// Une ligne n'est marquée « remise » que lorsque le sink in-app l'a
/// effectivement persistée. Aucun canal push externe n'est prétendu ici.
library;

import 'package:flutter/material.dart';

import '../widgets/common.dart';
import '../widgets/mobile_kit.dart';
import 'lexa_client.dart';
import 'lexa_ui.dart';

class LexaNotificationsScreen extends StatefulWidget {
  final LexaClient client;

  const LexaNotificationsScreen({super.key, required this.client});

  @override
  State<LexaNotificationsScreen> createState() =>
      _LexaNotificationsScreenState();
}

class _LexaNotificationsScreenState extends State<LexaNotificationsScreen> {
  late Future<Map<String, dynamic>> _data = widget.client.notifications();
  bool _marking = false;

  void _reload() => setState(() => _data = widget.client.notifications());

  Future<void> _markRead() async {
    setState(() => _marking = true);
    try {
      await widget.client.markNotificationsRead();
      _reload();
    } finally {
      if (mounted) setState(() => _marking = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: const Color(0xFF061525),
        appBar: AppBar(
          backgroundColor: const Color(0xFF061525),
          title: const Text('Alertes Lexa'),
        ),
        body: FutureBuilder<Map<String, dynamic>>(
          future: _data,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return Center(
                child: ErrorView(
                  error: 'Lecture impossible : ${snapshot.error}',
                  onRetry: _reload,
                ),
              );
            }
            return _body(snapshot.data ?? const {});
          },
        ),
      );

  Widget _body(Map<String, dynamic> data) {
    final rows = (data['notifications'] as List? ?? const [])
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
    final unread = (data['unread'] as num?)?.toInt() ?? 0;
    return RefreshIndicator(
      onRefresh: () async => _reload(),
      child: MobileScrollView(
        key: const ValueKey('lexa-notifications'),
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 50),
        children: [
          Row(children: [
            Expanded(
              child: Text(
                '$unread non lue${unread > 1 ? 's' : ''}',
                style: const TextStyle(color: lexaMuted, fontSize: 13),
              ),
            ),
            TextButton(
              key: const ValueKey('lexa-notifications-read-all'),
              onPressed: unread == 0 || _marking ? null : _markRead,
              child: Text(_marking ? 'Mise à jour…' : 'Tout marquer comme lu'),
            ),
          ]),
          const SizedBox(height: 8),
          if (rows.isEmpty)
            lexaNote('Aucune alerte enregistrée.')
          else
            for (final row in rows) _notification(row),
        ],
      ),
    );
  }

  Widget _notification(Map<String, dynamic> row) {
    final delivered = row['delivery_status'] == 'DELIVERED';
    final created = parseIso(row['created_at']);
    final when = created == null
        ? 'date inconnue'
        : '${created.day.toString().padLeft(2, '0')}/'
            '${created.month.toString().padLeft(2, '0')}/${created.year} '
            '${created.hour.toString().padLeft(2, '0')}:'
            '${created.minute.toString().padLeft(2, '0')}';
    return GlassPanel(
      key: ValueKey('lexa-notification-${row['notification_id']}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(
                '${row['asset_id'] ?? 'MARCHÉ'} · ${row['kind'] ?? 'ALERTE'}',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w800),
              ),
            ),
            Text(
              delivered
                  ? 'Remise dans l’app'
                  : '${row['delivery_status'] ?? 'Inconnue'}',
              style: TextStyle(
                color: delivered ? lexaGreen : lexaOrange,
                fontSize: 11.5,
                fontWeight: FontWeight.w700,
              ),
            ),
          ]),
          const SizedBox(height: 6),
          Text('${row['message'] ?? ''}',
              style: const TextStyle(
                  color: lexaWhite, fontSize: 13.5, height: 1.4)),
          const SizedBox(height: 6),
          Text('$when · déclencheur ${row['trigger_id'] ?? '—'}',
              style: const TextStyle(color: lexaMuted, fontSize: 11)),
          if ('${row['reason'] ?? ''}'.isNotEmpty)
            Text('${row['reason']}',
                style: const TextStyle(color: lexaMuted, fontSize: 11)),
        ],
      ),
    );
  }
}
