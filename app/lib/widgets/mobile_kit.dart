/// Shared mobile presentation widgets for the dashboard screens.
library;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

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
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// Largeur de reference du design, avant reduction a la largeur de l'ecran.
///
/// Le contenu est mis en page a cette largeur puis reduit par
/// `availableWidth / designWidth`. Sur un telephone d'environ 400 px logiques,
/// une reference a 900 donnait un facteur de 0,44: un texte declare a 12,5 px
/// s'affichait a 5,5 px, illisible. A 450 le facteur passe a environ 0,9, soit
/// exactement le double, et les proportions du design sont conservees.
const double kMobileDesignWidth = 450;

class MobileScrollView extends StatelessWidget {
  final EdgeInsetsGeometry padding;
  final List<Widget> children;
  final double designWidth;

  const MobileScrollView({
    super.key,
    required this.padding,
    required this.children,
    this.designWidth = kMobileDesignWidth,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      child: Align(
        alignment: Alignment.topCenter,
        child: _ScaleDownToWidth(
          designWidth: designWidth,
          child: SizedBox(
            width: designWidth,
            child: Padding(
              padding: padding,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: children,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ScaleDownToWidth extends SingleChildRenderObjectWidget {
  final double designWidth;

  const _ScaleDownToWidth({
    required this.designWidth,
    required super.child,
  });

  @override
  RenderObject createRenderObject(BuildContext context) {
    return _RenderScaleDownToWidth(designWidth: designWidth);
  }

  @override
  void updateRenderObject(
    BuildContext context,
    covariant _RenderScaleDownToWidth renderObject,
  ) {
    renderObject.designWidth = designWidth;
  }
}

class _RenderScaleDownToWidth extends RenderProxyBox {
  double _designWidth;
  double _scale = 1;

  _RenderScaleDownToWidth({required double designWidth})
      : _designWidth = designWidth;

  double get designWidth => _designWidth;

  set designWidth(double value) {
    if (_designWidth == value) return;
    _designWidth = value;
    markNeedsLayout();
  }

  @override
  void performLayout() {
    if (child == null) {
      size = constraints.smallest;
      return;
    }

    final availableWidth =
        constraints.maxWidth.isFinite ? constraints.maxWidth : _designWidth;
    _scale = availableWidth < _designWidth ? availableWidth / _designWidth : 1;

    child!.layout(
      BoxConstraints(
        minWidth: _designWidth,
        maxWidth: _designWidth,
        minHeight: 0,
        maxHeight: double.infinity,
      ),
      parentUsesSize: true,
    );

    size = constraints.constrain(
      Size(child!.size.width * _scale, child!.size.height * _scale),
    );
  }

  @override
  void paint(PaintingContext context, Offset offset) {
    if (child == null) return;
    context.pushTransform(
      needsCompositing,
      offset,
      Matrix4.diagonal3Values(_scale, _scale, 1),
      super.paint,
    );
  }

  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) {
    if (child == null) return false;
    return child!.hitTest(
      result,
      position: Offset(position.dx / _scale, position.dy / _scale),
    );
  }

  @override
  void applyPaintTransform(RenderBox child, Matrix4 transform) {
    transform.scale(_scale, _scale);
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
      // Le logo officiel s'il est fourni, le tracé vectoriel sinon. Un
      // fichier manquant ne doit jamais laisser un rond vide: `errorBuilder`
      // ramène au dessin plutôt que d'afficher une icône cassée.
      //
      // L'image remplit le disque et y est découpée. Bitcoin et Solana sont
      // déjà des pastilles rondes: à 62 % elles flottaient dans un anneau de
      // dégradé qui n'a plus lieu d'être. Ethereum est une marque sur fond
      // transparent, et laisse le disque apparaître derrière elle.
      child: ClipOval(
        child: Image.asset(
          'assets/logos/${asset.toLowerCase()}.png',
          width: size,
          height: size,
          fit: BoxFit.cover,
          filterQuality: FilterQuality.high,
          errorBuilder: (context, error, stack) =>
              Center(child: meta.logoBuilder(size)),
        ),
      ),
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
            // Disque clair: la marque Ethereum est grise, elle disparaîtrait
            // sur le violet précédent. BTC garde son orange, SOL son noir.
            logoGradient: const [Color(0xFFF4F6FA), Color(0xFFDDE3ED)],
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
  // Six facettes, comme la marque officielle: l'octaèdre est coupé
  // verticalement en une moitié claire et une moitié sombre, avec une taille
  // marquée aux deux tiers de la hauteur. La version précédente n'en dessinait
  // que deux, ce qui donnait un losange plat sans relief.
  static const _light = Color(0xFF8C8C8C);
  static const _mid = Color(0xFF3C3C3B);
  static const _dark = Color(0xFF141414);
  static const _midLight = Color(0xFF393939);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final cx = w / 2;

    // Hauteurs des trois arêtes horizontales, en proportion de la marque.
    final waist = h * 0.505;      // pointe des faces supérieures
    final belt = h * 0.395;       // haut de la ceinture centrale
    final lower = h * 0.575;      // départ de la pointe inférieure

    void fill(Path path, Color colour) =>
        canvas.drawPath(path, Paint()..color = colour);

    // Faces supérieures: gauche claire, droite sombre.
    fill(
      Path()
        ..moveTo(cx, 0)
        ..lineTo(0, waist)
        ..lineTo(cx, belt)
        ..close(),
      _light,
    );
    fill(
      Path()
        ..moveTo(cx, 0)
        ..lineTo(w, waist)
        ..lineTo(cx, belt)
        ..close(),
      _mid,
    );

    // Ceinture centrale, plus sombre à droite.
    fill(
      Path()
        ..moveTo(0, waist)
        ..lineTo(cx, belt)
        ..lineTo(cx, h * 0.66)
        ..close(),
      _midLight,
    );
    fill(
      Path()
        ..moveTo(w, waist)
        ..lineTo(cx, belt)
        ..lineTo(cx, h * 0.66)
        ..close(),
      _dark,
    );

    // Pointe inférieure, séparée de la ceinture par un liseré vide.
    fill(
      Path()
        ..moveTo(0, lower)
        ..lineTo(cx, h)
        ..lineTo(cx, h * 0.735)
        ..close(),
      _light,
    );
    fill(
      Path()
        ..moveTo(w, lower)
        ..lineTo(cx, h)
        ..lineTo(cx, h * 0.735)
        ..close(),
      _mid,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class SolMark extends StatelessWidget {
  final double width;

  const SolMark({super.key, required this.width});

  @override
  Widget build(BuildContext context) {
    // Le dégradé traverse les trois barres au lieu de repartir de zéro sur
    // chacune: sur la marque officielle c'est une seule transition du
    // vert-bleu au violet, du bas à droite vers le haut à gauche.
    return SizedBox(
      width: width,
      height: width * 0.80,
      child: CustomPaint(painter: _SolPainter()),
    );
  }
}

class _SolPainter extends CustomPainter {
  static const _teal = Color(0xFF19FB9B);
  static const _blue = Color(0xFF41A5D4);
  static const _purple = Color(0xFF9945FF);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final barHeight = h * 0.215;
    final slant = w * 0.17;
    final gap = (h - barHeight * 3) / 2;

    final shader = const LinearGradient(
      begin: Alignment.bottomLeft,
      end: Alignment.topRight,
      colors: [_purple, _blue, _teal],
    ).createShader(Rect.fromLTWH(0, 0, w, h));
    final paint = Paint()..shader = shader;

    // Barre du haut et du bas penchées dans un sens, celle du milieu dans
    // l'autre: c'est ce contraste qui donne sa forme au logo.
    void bar(double top, {required bool leftLean}) {
      final path = Path();
      if (leftLean) {
        path
          ..moveTo(slant, top)
          ..lineTo(w, top)
          ..lineTo(w - slant, top + barHeight)
          ..lineTo(0, top + barHeight)
          ..close();
      } else {
        path
          ..moveTo(0, top)
          ..lineTo(w - slant, top)
          ..lineTo(w, top + barHeight)
          ..lineTo(slant, top + barHeight)
          ..close();
      }
      canvas.drawPath(path, paint);
    }

    bar(0, leftLean: true);
    bar(barHeight + gap, leftLean: false);
    bar((barHeight + gap) * 2, leftLean: true);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
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
