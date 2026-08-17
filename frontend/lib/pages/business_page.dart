import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/app/destinations.dart';

class BusinessPage extends StatelessWidget {
  const BusinessPage({super.key, required this.destination});
  final AppDestination destination;

  @override
  Widget build(BuildContext context) {
    final content = _content[destination.path] ?? const ('Votre espace est prêt', 'Connectez vos outils pour afficher ici des informations à jour.');
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1200),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(destination.label, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 6),
              Text(destination.description),
              const SizedBox(height: 28),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(28),
                decoration: BoxDecoration(color: Colors.white, border: Border.all(color: const Color(0xFFDDE5E8)), borderRadius: BorderRadius.circular(8)),
                child: Column(
                  children: [
                    Icon(destination.icon, size: 36, color: const Color(0xFF007C83)),
                    const SizedBox(height: 14),
                    Text(content.$1, style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 8),
                    Text(content.$2, textAlign: TextAlign.center),
                    const SizedBox(height: 20),
                    FilledButton.icon(onPressed: () => context.go('/connections'), icon: const Icon(Icons.add_link), label: const Text('Connecter mes outils')),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

const _content = <String, (String, String)>{
  '/sales': ('Suivez chaque évolution', 'Vos tendances, comparaisons et prévisions de ventes apparaîtront ici.'),
  '/customers': ('Fidélisez les bons clients', 'Vous retrouverez les clients à valoriser, à relancer ou à accompagner en priorité.'),
  '/products': ('Pilotez votre catalogue', 'Les produits performants, la demande attendue et les stocks à surveiller seront réunis ici.'),
  '/recommendations': ('Passez directement à l’action', 'Avenqo classera les opportunités selon leur impact potentiel sur votre activité.'),
  '/alerts': ('Restez informé sans bruit', 'Les variations importantes et les risques seront signalés avec une action recommandée.'),
  '/reports': ('Vos synthèses de direction', 'Créez et partagez des rapports clairs sur les résultats de votre entreprise.'),
  '/connections': ('Reliez vos outils métier', 'Ajoutez votre solution de caisse, votre boutique en ligne ou vos fichiers de ventes.'),
  '/settings': ('Préférences de l’entreprise', 'Personnalisez les informations et les notifications de votre organisation.'),
};