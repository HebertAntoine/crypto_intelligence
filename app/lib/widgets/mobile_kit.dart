/// Shared mobile presentation widgets for the dashboard screens.
library;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

const mobileBlue = Color(0xFF58A6FF);
const mobilePanel = Color(0xFF0E1A28);
const mobilePanelAlt = Color(0xFF101E2D);
const mobileBorder = Color(0xFF245386);
const mobileMuted = Color(0xFFB7C6DF);

class MobileGradientFrame extends StatelessWidget {
  final Widget child;

  const MobileGradientFrame({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF06101C),
            Color(0xFF07182A),
            Color(0xFF0E1116),
          ],
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            const designWidth = 900.0;
            final width = constraints.maxWidth;
            if (width >= 700) {
              return Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: designWidth),
                  child: child,
                ),
              );
            }

            final scale = width / designWidth;
            final scaledHeight = constraints.maxHeight / scale;
            return Align(
              alignment: Alignment.topCenter,
              child: Transform.scale(
                scale: scale,
                alignment: Alignment.topCenter,
                child: OverflowBox(
                  minWidth: designWidth,
                  maxWidth: designWidth,
                  minHeight: scaledHeight,
                  maxHeight: scaledHeight,
                  alignment: Alignment.topCenter,
                  child: SizedBox(
                    width: designWidth,
                    height: scaledHeight,
                    child: child,
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

class MobileHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final VoidCallback? onInfo;

  const MobileHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.onInfo,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: AppColors.text,
                  fontSize: 40,
                  fontWeight: FontWeight.w800,
                  height: 1.02,
                ),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 7),
                Text(
                  subtitle!,
                  style: const TextStyle(
                      color: mobileMuted, fontSize: 21, height: 1.18),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(width: 14),
        IconButton(
          tooltip: 'Information',
          icon: const Icon(Icons.info_outline_rounded,
              color: Color(0xFFC7D5F2), size: 36),
          onPressed: onInfo,
        ),
      ],
    );
  }
}

class GlassPanel extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color borderColor;

  const GlassPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(22),
    this.borderColor = mobileBorder,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: mobilePanel.withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(17),
        border: Border.all(color: borderColor, width: 1.35),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.34),
            blurRadius: 24,
            offset: const Offset(0, 14),
          ),
          BoxShadow(
            color: mobileBlue.withValues(alpha: 0.10),
            blurRadius: 28,
            spreadRadius: -8,
          ),
        ],
      ),
      child: child,
    );
  }
}

class IconTile extends StatelessWidget {
  final IconData icon;

  const IconTile({super.key, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 74,
      height: 74,
      decoration: BoxDecoration(
        color: const Color(0xFF143966).withValues(alpha: 0.84),
        borderRadius: BorderRadius.circular(17),
        border:
            Border.all(color: mobileBlue.withValues(alpha: 0.66), width: 1.4),
      ),
      child: Icon(icon, color: const Color(0xFF7CB7FF), size: 38),
    );
  }
}

class MobilePill extends StatelessWidget {
  final String label;
  final Color color;
  final bool filled;
  final bool dense;

  const MobilePill({
    super.key,
    required this.label,
    required this.color,
    this.filled = false,
    this.dense = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 560),
      padding: EdgeInsets.symmetric(
          horizontal: dense ? 12 : 16, vertical: dense ? 5 : 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: filled ? 0.22 : 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
            color: color.withValues(alpha: filled ? 0.95 : 0.78), width: 1.35),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: color,
          fontSize: dense ? 14 : 16,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class MobileNavDestination {
  final IconData icon;
  final String label;

  const MobileNavDestination({required this.icon, required this.label});
}

class MobileBottomNav extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onSelected;
  final List<MobileNavDestination> destinations;

  const MobileBottomNav({
    super.key,
    required this.selectedIndex,
    required this.onSelected,
    required this.destinations,
  });

  @override
  Widget build(BuildContext context) {
    Widget bar({bool compact = false}) => Container(
          decoration: BoxDecoration(
            color: const Color(0xFF07111D),
            border: const Border(
                top: BorderSide(color: Color(0xFF1A3149), width: 1)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.38),
                blurRadius: 24,
                offset: const Offset(0, -10),
              ),
            ],
          ),
          child: SafeArea(
            top: false,
            child: SizedBox(
              height: compact ? 88 : 134,
              child: Row(
                children: [
                  for (var i = 0; i < destinations.length; i += 1)
                    Expanded(
                      child: _MobileNavItem(
                        destination: destinations[i],
                        selected: i == selectedIndex,
                        compact: compact,
                        onTap: () => onSelected(i),
                      ),
                    ),
                ],
              ),
            ),
          ),
        );

    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        return bar(compact: width < 700);
      },
    );
  }
}

class _MobileNavItem extends StatelessWidget {
  final MobileNavDestination destination;
  final bool selected;
  final bool compact;
  final VoidCallback onTap;

  const _MobileNavItem({
    required this.destination,
    required this.selected,
    required this.compact,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = selected ? mobileBlue : const Color(0xFFD3D9EF);
    return Padding(
      padding: EdgeInsets.symmetric(
          horizontal: compact ? 2 : 6, vertical: compact ? 8 : 12),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(compact ? 18 : 28),
          onTap: onTap,
          child: Ink(
            decoration: BoxDecoration(
              color: selected
                  ? const Color(0xFF123E71).withValues(alpha: 0.86)
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(compact ? 18 : 28),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(destination.icon,
                    color: color,
                    size:
                        compact ? (selected ? 24 : 22) : (selected ? 34 : 31)),
                SizedBox(height: compact ? 4 : 8),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: compact ? 3 : 0),
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      destination.label,
                      maxLines: 1,
                      style: TextStyle(
                        color: color,
                        fontSize: compact ? 11 : (selected ? 18 : 17),
                        fontWeight:
                            selected ? FontWeight.w600 : FontWeight.w400,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class CryptoLogo extends StatelessWidget {
  final String asset;
  final double size;

  const CryptoLogo({super.key, required this.asset, this.size = 66});

  @override
  Widget build(BuildContext context) {
    final meta = AssetVisuals.forAsset(asset);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: meta.logoGradient,
        ),
        boxShadow: [
          BoxShadow(
            color: meta.logoGradient.last.withValues(alpha: 0.22),
            blurRadius: 16,
            spreadRadius: -2,
          ),
        ],
      ),
      child: Center(child: meta.logoBuilder(size)),
    );
  }
}

class AssetVisuals {
  final String name;
  final List<Color> logoGradient;
  final Widget Function(double size) logoBuilder;

  const AssetVisuals({
    required this.name,
    required this.logoGradient,
    required this.logoBuilder,
  });

  static AssetVisuals forAsset(String asset) => switch (asset) {
        'ETH' => AssetVisuals(
            name: 'Ethereum',
            logoGradient: const [Color(0xFF7A63F8), Color(0xFF5146E8)],
            logoBuilder: (size) => EthMark(size: size * 0.67),
          ),
        'SOL' => AssetVisuals(
            name: 'Solana',
            logoGradient: const [Color(0xFF080B13), Color(0xFF171B2C)],
            logoBuilder: (size) => SolMark(width: size * 0.54),
          ),
        _ => AssetVisuals(
            name: 'Bitcoin',
            logoGradient: const [Color(0xFFFFA52C), Color(0xFFFF8B1F)],
            logoBuilder: (size) => Text(
              '₿',
              style: TextStyle(
                color: Colors.white,
                fontSize: size * 0.62,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
      };
}

class EthMark extends StatelessWidget {
  final double size;

  const EthMark({super.key, required this.size});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(size: Size(size * 0.74, size), painter: _EthPainter());
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

class SolMark extends StatelessWidget {
  final double width;

  const SolMark({super.key, required this.width});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _SolBar(
            width: width,
            colorA: const Color(0xFF35E8AA),
            colorB: const Color(0xFF8A6BFF)),
        const SizedBox(height: 5),
        _SolBar(
            width: width,
            colorA: const Color(0xFF8A6BFF),
            colorB: const Color(0xFFE35EFF)),
        const SizedBox(height: 5),
        _SolBar(
            width: width,
            colorA: const Color(0xFFE35EFF),
            colorB: const Color(0xFF35E8AA)),
      ],
    );
  }
}

class _SolBar extends StatelessWidget {
  final double width;
  final Color colorA;
  final Color colorB;

  const _SolBar(
      {required this.width, required this.colorA, required this.colorB});

  @override
  Widget build(BuildContext context) {
    return Transform(
      transform: Matrix4.skewX(-0.22),
      child: Container(
        width: width,
        height: width * 0.21,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(2),
          gradient: LinearGradient(colors: [colorA, colorB]),
        ),
      ),
    );
  }
}

String fmtFr(num? value, {int digits = 2, String suffix = ''}) {
  if (value == null || value.isNaN) return '—';
  final formatted = value.toStringAsFixed(digits).replaceAll('.', ',');
  return suffix.isEmpty ? formatted : '$formatted$suffix';
}

String signedFr(num? value, {int digits = 2, String suffix = ''}) {
  if (value == null || value.isNaN) return '—';
  final sign = value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(digits).replaceAll('.', ',')}$suffix';
}

String readableLabel(String value) => value.replaceAll('_', ' ');
