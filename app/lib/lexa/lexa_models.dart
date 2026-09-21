/// Lexa labels and French formatting. Plans themselves are read as the
/// backend wrote them: nothing is computed here.
library;

/// Level types, in the order the entry form offers them.
const lexaKinds = <String, String>{
  'BUY_ZONE': '🟢 Zone d\'achat',
  'REINFORCEMENT': '🟢 Renforcement',
  'CONFIRMATION': '🚀 Confirmation',
  'BREAKOUT': '🚀 Cassure',
  'INVALIDATION': '❌ Invalidation',
  'TARGET': '🎯 Objectif',
  'TAKE_PROFIT': '🎯 Prise de profit',
  'SUPPORT': '🧱 Support',
  'RESISTANCE': '🧱 Résistance',
  'CURRENT_PRICE': '💲 Prix observé',
  'WARNING': '⚠️ Avertissement',
  'OTHER': '📝 Autre',
};

const lexaStances = <String, String>{
  'UNSPECIFIED': '⚪ Non précisé',
  'WAIT': '🟠 Attente',
  'BUY': '🟢 Achat',
  'SELL': '🔴 Vente',
  'NEUTRAL': '⚪ Neutre',
};

/// "2,4531" or "2.4531" or "70 000" -> 2.4531 / 70000. Null when unreadable.
double? parseFrNumber(String raw) {
  final cleaned = raw
      .trim()
      .replaceAll(RegExp(r'[\s\u00a0\u202f$€]'), '')
      .replaceAll(',', '.');
  if (cleaned.isEmpty) return null;
  return double.tryParse(cleaned);
}

/// A price with every decimal that was said, none added: 70 250 $ / 2,444175 $.
String fmtPrice(double? value) {
  if (value == null) return '—';
  var text = value.toStringAsFixed(value >= 1000 ? 2 : 8);
  if (text.contains('.')) {
    text = text.replaceAll(RegExp(r'0+$'), '');
    if (text.endsWith('.')) text = text.substring(0, text.length - 1);
  }
  final parts = text.split('.');
  final grouped = parts[0]
      .replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+$)'), (m) => '${m[1]} ');
  return parts.length > 1 ? '$grouped,${parts[1]} \$' : '$grouped \$';
}

String fmtEur(double? value) =>
    value == null ? '—' : '${value.toStringAsFixed(2).replaceAll('.', ',')} €';

String fmtDateFr(DateTime? d, {bool time = true}) {
  if (d == null) return '—';
  String two(int v) => v.toString().padLeft(2, '0');
  final day = '${two(d.day)}/${two(d.month)}/${d.year}';
  return time ? '$day à ${two(d.hour)}:${two(d.minute)}' : day;
}
