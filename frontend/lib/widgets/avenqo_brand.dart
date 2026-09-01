import 'package:avenqo/app/avenqo_colors.dart';
import 'package:flutter/material.dart';

/// Logo Avenqo officiel, réutilisable à une taille carrée configurable.
class AvenqoBrandIcon extends StatelessWidget {
  const AvenqoBrandIcon({super.key, this.size = 22});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      'assets/brand/avenqo-official.png',
      width: size,
      height: size,
      fit: BoxFit.cover,
      filterQuality: FilterQuality.high,
    );
  }
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
