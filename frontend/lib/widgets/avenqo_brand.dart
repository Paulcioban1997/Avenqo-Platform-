import 'package:flutter/material.dart';
import 'package:avenqo/app/avenqo_colors.dart';

/// Logo Avenqo réutilisable — même icône que l'app (sharp, pas de rectangle
/// noir), fonctionne en Light/Dark, taille configurable.
class AvenqoBrandIcon extends StatelessWidget {
  const AvenqoBrandIcon({super.key, this.size = 22});

  final double size;

  @override
  Widget build(BuildContext context) {
    // Icône Avenqo : forme "A" stylisée en bleu brand, nette à toute taille.
    // Pas d'asset image (évite le rectangle noir et les problèmes de résolution).
    return CustomPaint(
      size: Size.square(size),
      painter: _AvenqoIconPainter(),
    );
  }
}

class _AvenqoIconPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF087CF0)
      ..style = PaintingStyle.fill;

    final path = Path()
      // Barre verticale gauche du A
      ..moveTo(size.width * 0.35, size.height * 0.15)
      ..lineTo(size.width * 0.5, size.height * 0.15)
      ..lineTo(size.width * 0.5, size.height * 0.85)
      ..lineTo(size.width * 0.35, size.height * 0.85)
      ..close()
      // Barre verticale droite du A
      ..moveTo(size.width * 0.5, size.height * 0.15)
      ..lineTo(size.width * 0.65, size.height * 0.15)
      ..lineTo(size.width * 0.65, size.height * 0.85)
      ..lineTo(size.width * 0.5, size.height * 0.85)
      ..close()
      // Barre horizontale du A
      ..moveTo(size.width * 0.35, size.height * 0.45)
      ..lineTo(size.width * 0.65, size.height * 0.45)
      ..lineTo(size.width * 0.65, size.height * 0.55)
      ..lineTo(size.width * 0.35, size.height * 0.55)
      ..close();

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Logo + wordmark "Avenqo" — utilisé dans navbar, footer, cartes.
/// Couleur du texte s'adapte au thème (ink en light, surface en dark).
class AvenqoBrand extends StatelessWidget {
  const AvenqoBrand({
    super.key,
    this.iconSize = 22,
    this.textSize = 20,
    this.lightOnDark = false,
  });

  final double iconSize;
  final double textSize;
  final bool lightOnDark;

  @override
  Widget build(BuildContext context) {
    final colors = AvenqoColors.of(context);
    final textColor = lightOnDark ? colors.surface : colors.ink;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        AvenqoBrandIcon(size: iconSize),
        SizedBox(width: iconSize * 0.36),
        Text(
          'Avenqo',
          style: TextStyle(
            color: textColor,
            fontWeight: FontWeight.w800,
            fontSize: textSize,
          ),
        ),
      ],
    );
  }
}
