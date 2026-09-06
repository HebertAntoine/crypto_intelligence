/// Ecran "Aujourd’hui".
///
/// Le backend reste la source de verite pour les verdicts; cette page met ces
/// donnees dans une interface mobile proche de la maquette fournie.
library;

import 'package:flutter/material.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../theme/app_theme.dart';
import '../widgets/common.dart';

class TodayScreen extends StatefulWidget {
  final ApiClient client;

  const TodayScreen({super.key, required this.client});

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  late Future<List<TodayRead>> _future;

  static const _assets = ['BTC', 'ETH', 'SOL'];

  @override
  void initState() {
    super.initState();
    _future = widget.client.todayAll(_assets);
  }

  void _reload() {
    setState(() => _future = widget.client.todayAll(_assets));
  }

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF07111D),
            Color(0xFF0A1726),
            Color(0xFF0E1116),
          ],
        ),
      ),
      child: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<List<TodayRead>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const LoadingView(what: 'analyse du jour');
            }
            if (snapshot.hasError) {
              return ErrorView(error: snapshot.error!, onRetry: _reload);
            }

            final reads = snapshot.data ?? const [];
            if (reads.isEmpty) {
              return ErrorView(error: 'Aucune analyse disponible.', onRetry: _reload);
            }

            return SafeArea(
              bottom: false,
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 840),
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(26, 26, 26, 24),
                    children: [
                      const _TodayHeader(),
                      const SizedBox(height: 20),
                      for (final read in reads) ...[
                        _MarketCard(read: read),
                        const SizedBox(height: 22),
                      ],
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _TodayHeader extends StatelessWidget {
  const _TodayHeader();

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Aujourd’hui',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 40,
                  fontWeight: FontWeight.w800,
                  height: 0.98,
                ),
              ),
              SizedBox(height: 8),
              Text(
                'Analyse des marchés en temps réel',
                style: TextStyle(
                  color: Color(0xFFB6C1D2),
                  fontSize: 20,
                  height: 1.15,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 14),
        Wrap(
          spacing: 12,
          runSpacing: 10,
          alignment: WrapAlignment.end,
          children: [
            _HeaderButton(
              icon: Icons.calendar_today_rounded,
              label: _formatFrenchDate(DateTime.now()),
            ),
            const _SquareHeaderButton(icon: Icons.settings_outlined),
          ],
        ),
      ],
    );
  }
}

class _MarketCard extends StatelessWidget {
  final TodayRead read;

  const _MarketCard({required this.read});

  @override
  Widget build(BuildContext context) {
    final meta = _AssetMeta.forAsset(read.asset);
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF101927).withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(17),
        border: Border.all(color: const Color(0xFF1F4A7E), width: 1.4),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.34),
            blurRadius: 24,
            offset: const Offset(0, 15),
          ),
          BoxShadow(
            color: const Color(0xFF1A67B3).withValues(alpha: 0.12),
            blurRadius: 28,
            spreadRadius: -8,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _AssetHeader(read: read, meta: meta),
          const SizedBox(height: 22),
          _VerdictPanel(read: read),
          const SizedBox(height: 16),
          _MetricGrid(read: read),
          const SizedBox(height: 20),
          const Divider(height: 1, color: Color(0xFF2A3B51)),
          const SizedBox(height: 16),
          _DetailRows(read: read),
          const SizedBox(height: 22),
          _WhyPanel(read: read),
        ],
      ),
    );
  }
}

class _AssetHeader extends StatelessWidget {
  final TodayRead read;
  final _AssetMeta meta;

  const _AssetHeader({required this.read, required this.meta});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _CryptoLogo(meta: meta),
        const SizedBox(width: 22),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                read.asset,
                style: const TextStyle(
                  color: AppColors.text,
                  fontSize: 31,
                  fontWeight: FontWeight.w800,
                  height: 1,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                meta.name,
                style: const TextStyle(color: Color(0xFFB6C1D2), fontSize: 24, height: 1),
              ),
            ],
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              meta.price,
              style: const TextStyle(
                color: AppColors.text,
                fontSize: 28,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            _ChangePill(label: meta.change),
          ],
        ),
        const SizedBox(width: 16),
        const Icon(Icons.chevron_right_rounded, color: AppColors.text, size: 34),
      ],
    );
  }
}

class _VerdictPanel extends StatelessWidget {
  final TodayRead read;

  const _VerdictPanel({required this.read});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.measured.withValues(alpha: 0.25),
            const Color(0xFF12291E).withValues(alpha: 0.84),
            const Color(0xFF122328).withValues(alpha: 0.88),
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.measured, width: 1.5),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.measured.withValues(alpha: 0.28),
            ),
            child: const Icon(Icons.trending_up_rounded, color: Color(0xFF5CFF9F), size: 34),
          ),
          const SizedBox(width: 22),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _directionLabel(read.summary.marketDirection),
                  style: const TextStyle(
                    color: Color(0xFF61F29E),
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                    height: 1.05,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _verdictBody(read),
                  style: const TextStyle(color: AppColors.text, fontSize: 18, height: 1.36),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricGrid extends StatelessWidget {
  final TodayRead read;

  const _MetricGrid({required this.read});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 620;
        final children = [
          _MetricBox(
            icon: Icons.bar_chart_rounded,
            title: 'Direction du marché',
            pill: _directionLabel(read.summary.marketDirection),
            pillColor: _directionColor(read.summary.marketDirection),
            caption: 'présente sur ${read.summary.directionConfidence} % des 20 derniers jours',
          ),
          _MetricBox(
            icon: Icons.track_changes_rounded,
            title: 'Edge mesurable',
            pill: _edgeLabel(read.edgeState),
            pillColor: _edgeColor(read.edgeState),
            caption: '${read.admittedCount} validé, ${read.rejectedCount} rejeté',
          ),
        ];

        if (compact) {
          return Column(
            children: [
              children[0],
              const SizedBox(height: 12),
              children[1],
            ],
          );
        }

        return Row(
          children: [
            Expanded(child: children[0]),
            const SizedBox(width: 14),
            Expanded(child: children[1]),
          ],
        );
      },
    );
  }
}

class _MetricBox extends StatelessWidget {
  final IconData icon;
  final String title;
  final String pill;
  final Color pillColor;
  final String caption;

  const _MetricBox({
    required this.icon,
    required this.title,
    required this.pill,
    required this.pillColor,
    required this.caption,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 128),
      padding: const EdgeInsets.fromLTRB(18, 17, 18, 15),
      decoration: BoxDecoration(
        color: const Color(0xFF111D2B).withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF273B54), width: 1.25),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppColors.text, size: 30),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: AppColors.text, fontSize: 18)),
                const SizedBox(height: 10),
                _OutlinePill(label: pill, color: pillColor),
                const SizedBox(height: 10),
                Text(caption, style: const TextStyle(color: Color(0xFFB6C1D2), fontSize: 14)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DetailRows extends StatelessWidget {
  final TodayRead read;

  const _DetailRows({required this.read});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _InfoRow(
          icon: Icons.groups_rounded,
          label: 'Crowding',
          value: _crowdingLabel(read.crowdingLevel),
          valuePill: true,
          valueColor: AppColors.accent,
          sideTitle: _crowdingDirectionTitle(read.crowdingDirection),
          sideBody: "L’open interest présente deux scénarios possibles",
        ),
        _InfoRow(
          icon: Icons.bar_chart_rounded,
          label: 'Positionnement',
          value: _leverageLabel(read.leverageState),
        ),
        _InfoRow(
          icon: Icons.storage_rounded,
          label: 'Funding',
          value: _fundingLabel(read),
        ),
        _InfoRow(
          icon: Icons.show_chart_rounded,
          label: 'Volatilité',
          value: _volatilityLabel(read.volatilityRegime),
        ),
        _InfoRow(
          icon: Icons.help_rounded,
          label: 'Incertitude',
          value: '${_uncertaintyLabel(read.uncertaintyLevel)}  ${read.uncertaintyScore.toStringAsFixed(0)}/100',
          valuePill: true,
          valueColor: _uncertaintyColor(read.uncertaintyLevel),
        ),
        _InfoRow(
          icon: Icons.check_box_rounded,
          label: 'Action recommandée',
          value: read.summary.actionable ? 'A SURVEILLER' : 'AUCUNE',
        ),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final bool valuePill;
  final Color valueColor;
  final String? sideTitle;
  final String? sideBody;

  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.valuePill = false,
    this.valueColor = AppColors.text,
    this.sideTitle,
    this.sideBody,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 620;
        final leading = Row(
          children: [
            SizedBox(width: 54, child: Icon(icon, color: AppColors.text, size: 30)),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(color: Color(0xFFB6C1D2), fontSize: 20),
              ),
            ),
            if (compact)
              IconButton(
                tooltip: 'Détail',
                icon: const Icon(Icons.info_outline_rounded, color: AppColors.text, size: 22),
                onPressed: () => _showInfo(context),
              ),
          ],
        );

        final valueWidget = Align(
          alignment: compact ? Alignment.centerLeft : Alignment.centerRight,
          child: valuePill
              ? _OutlinePill(label: value, color: valueColor, dense: true)
              : Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textAlign: compact ? TextAlign.left : TextAlign.right,
                  style: const TextStyle(
                    color: AppColors.text,
                    fontSize: 17,
                    fontWeight: FontWeight.w500,
                  ),
                ),
        );

        if (compact) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 9),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                leading,
                Padding(
                  padding: const EdgeInsets.only(left: 54),
                  child: valueWidget,
                ),
                if (sideTitle != null || sideBody != null)
                  Padding(
                    padding: const EdgeInsets.only(left: 54, top: 8),
                    child: _SideNote(title: sideTitle, body: sideBody),
                  ),
              ],
            ),
          );
        }

        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 9),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              SizedBox(width: 54, child: Icon(icon, color: AppColors.text, size: 30)),
              SizedBox(
                width: 220,
                child: Text(
                  label,
                  style: const TextStyle(color: Color(0xFFB6C1D2), fontSize: 20),
                ),
              ),
              Expanded(child: valueWidget),
              if (sideTitle != null || sideBody != null) ...[
                const SizedBox(width: 24),
                SizedBox(width: 210, child: _SideNote(title: sideTitle, body: sideBody)),
              ],
              IconButton(
                tooltip: 'Détail',
                icon: const Icon(Icons.info_outline_rounded, color: AppColors.text, size: 22),
                onPressed: () => _showInfo(context),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showInfo(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text(label, style: const TextStyle(fontSize: 16)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(value, style: const TextStyle(fontSize: 14)),
            if (sideTitle != null || sideBody != null) ...[
              const SizedBox(height: 12),
              if (sideTitle != null)
                Text(
                  sideTitle!,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              if (sideBody != null) ...[
                const SizedBox(height: 4),
                Text(sideBody!, style: const TextStyle(color: AppColors.textMuted, height: 1.35)),
              ],
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Fermer'),
          ),
        ],
      ),
    );
  }
}

class _SideNote extends StatelessWidget {
  final String? title;
  final String? body;

  const _SideNote({this.title, this.body});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title != null)
          Text(
            title!,
            style: const TextStyle(color: AppColors.text, fontSize: 15),
          ),
        if (body != null) ...[
          const SizedBox(height: 2),
          Text(
            body!,
            style: const TextStyle(color: Color(0xFFB6C1D2), fontSize: 13, height: 1.2),
          ),
        ],
      ],
    );
  }
}

class _WhyPanel extends StatelessWidget {
  final TodayRead read;

  const _WhyPanel({required this.read});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF121D2A).withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF31465F), width: 1.25),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.fromLTRB(18, 8, 18, 8),
          childrenPadding: const EdgeInsets.fromLTRB(20, 0, 20, 18),
          leading: Container(
            width: 52,
            height: 52,
            decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFFF4B924)),
            child: const Icon(Icons.lightbulb_outline_rounded, color: Colors.white, size: 30),
          ),
          title: const Text(
            'Pourquoi cette analyse ?',
            style: TextStyle(color: AppColors.text, fontSize: 20, fontWeight: FontWeight.w800),
          ),
          subtitle: const Text(
            'Voir le détail des indicateurs et sources',
            style: TextStyle(color: Color(0xFFB6C1D2), fontSize: 17),
          ),
          iconColor: AppColors.text,
          collapsedIconColor: AppColors.text,
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                _edgeExplanation(read),
                style: const TextStyle(color: Color(0xFFB6C1D2), fontSize: 14.5, height: 1.35),
              ),
            ),
            const SizedBox(height: 12),
            for (final driver in read.uncertaintyDrivers.take(3))
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(
                    '+${driver.contribution}  ${_sentenceCase(driver.driver.replaceAll('_', ' '))} - ${driver.detail}',
                    style: const TextStyle(color: AppColors.text, fontSize: 13.5, height: 1.25),
                  ),
                ),
              ),
            if (read.summary.caveats.isNotEmpty) ...[
              const SizedBox(height: 6),
              for (final caveat in read.summary.caveats.take(3))
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 5),
                    child: Text(
                      '- $caveat',
                      style: const TextStyle(
                        color: Color(0xFFB6C1D2),
                        fontSize: 13.5,
                        fontStyle: FontStyle.italic,
                        height: 1.25,
                      ),
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _HeaderButton extends StatelessWidget {
  final IconData icon;
  final String label;

  const _HeaderButton({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 66,
      padding: const EdgeInsets.symmetric(horizontal: 22),
      decoration: BoxDecoration(
        color: const Color(0xFF121D2B).withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF34506F), width: 1.4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: AppColors.text, size: 26),
          const SizedBox(width: 16),
          Text(label, style: const TextStyle(color: AppColors.text, fontSize: 19)),
        ],
      ),
    );
  }
}

class _SquareHeaderButton extends StatelessWidget {
  final IconData icon;

  const _SquareHeaderButton({required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 66,
      height: 66,
      decoration: BoxDecoration(
        color: const Color(0xFF121D2B).withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF34506F), width: 1.4),
      ),
      child: Icon(icon, color: AppColors.text, size: 30),
    );
  }
}

class _ChangePill extends StatelessWidget {
  final String label;

  const _ChangePill({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF0D633F).withValues(alpha: 0.82),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Color(0xFF63F39F),
          fontSize: 18,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _OutlinePill extends StatelessWidget {
  final String label;
  final Color color;
  final bool dense;

  const _OutlinePill({
    required this.label,
    required this.color,
    this.dense = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 260),
      padding: EdgeInsets.symmetric(horizontal: dense ? 13 : 15, vertical: dense ? 6 : 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: dense ? 0.18 : 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color, width: 1.45),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: color,
          fontSize: dense ? 16 : 14.5,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _CryptoLogo extends StatelessWidget {
  final _AssetMeta meta;

  const _CryptoLogo({required this.meta});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 82,
      height: 82,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: meta.logoGradient,
        ),
        boxShadow: [
          BoxShadow(
            color: meta.logoGradient.last.withValues(alpha: 0.25),
            blurRadius: 18,
            spreadRadius: -2,
          ),
        ],
      ),
      child: Center(child: meta.logo),
    );
  }
}

class _EthMark extends StatelessWidget {
  const _EthMark();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(size: const Size(43, 58), painter: _EthPainter());
  }
}

class _EthPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final topPaint = Paint()..color = Colors.white.withValues(alpha: 0.94);
    final bottomPaint = Paint()..color = Colors.white.withValues(alpha: 0.72);
    final stroke = Paint()
      ..color = const Color(0xFFB9C9FF).withValues(alpha: 0.56)
      ..strokeWidth = 1.4
      ..style = PaintingStyle.stroke;

    final cx = size.width / 2;
    final top = Path()
      ..moveTo(cx, 0)
      ..lineTo(size.width, size.height * 0.52)
      ..lineTo(cx, size.height * 0.38)
      ..lineTo(0, size.height * 0.52)
      ..close();
    final bottom = Path()
      ..moveTo(0, size.height * 0.58)
      ..lineTo(cx, size.height)
      ..lineTo(size.width, size.height * 0.58)
      ..lineTo(cx, size.height * 0.72)
      ..close();

    canvas.drawPath(top, topPaint);
    canvas.drawPath(bottom, bottomPaint);
    canvas.drawLine(Offset(cx, 0), Offset(cx, size.height), stroke);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _SolMark extends StatelessWidget {
  const _SolMark();

  @override
  Widget build(BuildContext context) {
    return const Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _SolBar(colorA: Color(0xFF35E8AA), colorB: Color(0xFF8A6BFF)),
        SizedBox(height: 6),
        _SolBar(colorA: Color(0xFF8A6BFF), colorB: Color(0xFFE35EFF)),
        SizedBox(height: 6),
        _SolBar(colorA: Color(0xFFE35EFF), colorB: Color(0xFF35E8AA)),
      ],
    );
  }
}

class _SolBar extends StatelessWidget {
  final Color colorA;
  final Color colorB;

  const _SolBar({required this.colorA, required this.colorB});

  @override
  Widget build(BuildContext context) {
    return Transform(
      transform: Matrix4.skewX(-0.22),
      child: Container(
        width: 42,
        height: 9,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(2),
          gradient: LinearGradient(colors: [colorA, colorB]),
        ),
      ),
    );
  }
}

class _AssetMeta {
  final String name;
  final String price;
  final String change;
  final Widget logo;
  final List<Color> logoGradient;

  const _AssetMeta({
    required this.name,
    required this.price,
    required this.change,
    required this.logo,
    required this.logoGradient,
  });

  static _AssetMeta forAsset(String asset) => switch (asset) {
        'ETH' => const _AssetMeta(
            name: 'Ethereum',
            price: '€2 210',
            change: '+1,8 %',
            logo: _EthMark(),
            logoGradient: [Color(0xFF7A63F8), Color(0xFF5146E8)],
          ),
        'SOL' => const _AssetMeta(
            name: 'Solana',
            price: '€128',
            change: '+3,1 %',
            logo: _SolMark(),
            logoGradient: [Color(0xFF112F38), Color(0xFF151423)],
          ),
        _ => const _AssetMeta(
            name: 'Bitcoin',
            price: '€52 840',
            change: '+2,4 %',
            logo: Text(
              '₿',
              style: TextStyle(color: Colors.white, fontSize: 50, fontWeight: FontWeight.w800),
            ),
            logoGradient: [Color(0xFFFFA52C), Color(0xFFFF8B1F)],
          ),
      };
}

String _formatFrenchDate(DateTime date) {
  const months = [
    'janv.',
    'févr.',
    'mars',
    'avr.',
    'mai',
    'juin',
    'juil.',
    'août',
    'sept.',
    'oct.',
    'nov.',
    'déc.',
  ];
  return '${date.day} ${months[date.month - 1]} ${date.year}';
}

String _directionLabel(String raw) {
  final value = raw.toUpperCase();
  if (value.contains('BULLISH')) {
    return value.contains('STRONG') ? 'FORTEMENT HAUSSIER' : 'HAUSSIER';
  }
  if (value.contains('BEARISH')) {
    return value.contains('STRONG') ? 'FORTEMENT BAISSIER' : 'BAISSIER';
  }
  if (value.contains('NEUTRAL')) return 'NEUTRE';
  return 'DIRECTION INCONNUE';
}

Color _directionColor(String raw) {
  final value = raw.toUpperCase();
  if (value.contains('BULLISH')) return AppColors.measured;
  if (value.contains('BEARISH')) return AppColors.bad;
  return AppColors.textMuted;
}

String _verdictBody(TodayRead read) {
  final ticker = read.asset;
  final direction = read.summary.marketDirection.toUpperCase();
  final trend = direction.contains('BEARISH') ? 'baissiere' : 'haussiere';
  if (read.edgeState == EdgeState.positiveEdge) {
    return 'Le $ticker est en tendance $trend et dispose actuellement d’un edge mesurable à surveiller.';
  }
  return 'Le $ticker est en tendance $trend, mais nous n’avons pas encore d’indicateur directionnel robuste pour confirmer un point d’entrée optimal.';
}

String _edgeLabel(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => 'EDGE MESURABLE',
      EdgeState.negativeEdge => 'EDGE DÉFAVORABLE',
      EdgeState.noMeasurableEdge => 'AUCUN EDGE MESURABLE',
      EdgeState.unstable => 'INSTABLE',
      EdgeState.insufficientData => 'DONNÉES INSUFFISANTES',
      EdgeState.notYetTested => 'PAS ENCORE TESTÉ',
      EdgeState.unknown => 'INCONNU',
    };

Color _edgeColor(EdgeState state) => switch (state) {
      EdgeState.positiveEdge => AppColors.measured,
      EdgeState.negativeEdge => AppColors.bad,
      EdgeState.noMeasurableEdge || EdgeState.unstable => AppColors.warn,
      _ => AppColors.textMuted,
    };

String _crowdingLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'NORMAL' => 'NORMAL',
      'HIGH' => 'ÉLEVÉ',
      'EXTREME' => 'EXTRÊME',
      _ => raw.replaceAll('_', ' '),
    };

String _crowdingDirectionTitle(String raw) {
  final value = raw.toUpperCase();
  if (value.contains('LONG')) return 'Biais longs';
  if (value.contains('SHORT')) return 'Biais shorts';
  if (value.contains('BALANCED')) return 'Équilibre';
  return 'Direction inconnue';
}

String _leverageLabel(String raw) => switch (raw.toUpperCase()) {
      'NEW_LONGS' => 'NOUVEAUX LONGS',
      'NEW_SHORTS' => 'NOUVEAUX SHORTS',
      'CROWDED_LONGS' => 'LONGS SURCHARGÉS',
      'CROWDED_SHORTS' => 'SHORTS SURCHARGÉS',
      'BALANCED' => 'ÉQUILIBRE',
      _ => raw.replaceAll('_', ' '),
    };

String _fundingLabel(TodayRead read) {
  final band = switch (read.fundingBand.toUpperCase()) {
    'NEUTRAL' => 'NEUTRE',
    'LOW' => 'FAIBLE',
    'HIGH' => 'ÉLEVÉ',
    'NEGATIVE' => 'NÉGATIF',
    'POSITIVE' => 'POSITIF',
    _ => read.fundingBand.replaceAll('_', ' '),
  };
  final percentile = read.fundingPercentile;
  if (percentile == null) return band;
  return '$band (p${percentile.toStringAsFixed(0)})';
}

String _volatilityLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'NORMAL' => 'NORMALE',
      'MODERATE' => 'MODÉRÉE',
      'HIGH' => 'ÉLEVÉE',
      'EXTREME' => 'EXTRÊME',
      _ => raw.replaceAll('_', ' '),
    };

String _uncertaintyLabel(String raw) => switch (raw.toUpperCase()) {
      'LOW' => 'FAIBLE',
      'MODERATE' => 'MODÉRÉE',
      'HIGH' => 'ÉLEVÉE',
      'EXTREME' => 'EXTRÊME',
      _ => raw.replaceAll('_', ' '),
    };

Color _uncertaintyColor(String raw) => switch (raw.toUpperCase()) {
      'LOW' => AppColors.measured,
      'MODERATE' => AppColors.accent,
      _ => AppColors.warn,
    };

String _edgeExplanation(TodayRead read) {
  if (read.edgeStatement.isNotEmpty) return read.edgeStatement;
  return 'Le signal est affiché seulement si les données backend l’ont validé. Sans edge mesurable, l’application garde une recommandation prudente.';
}

String _sentenceCase(String value) {
  if (value.isEmpty) return value;
  final lower = value.toLowerCase();
  return '${lower[0].toUpperCase()}${lower.substring(1)}';
}
