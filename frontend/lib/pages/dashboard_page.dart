import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:avenqo/auth/auth_controller.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key, required this.auth});

  final AuthController auth;

  @override
  Widget build(BuildContext context) {
    final company = auth.company ?? const <String, dynamic>{};
    final user = auth.user ?? const <String, dynamic>{};
    final wide = MediaQuery.sizeOf(context).width >= 1080;
    return ListView(
      padding: EdgeInsets.all(wide ? 32 : 20),
      children: [
        Text(
          user['first_name'] == null ? 'Bonjour' : 'Bonjour ${user['first_name']}',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 6),
        Text('Voici ce qui mérite votre attention chez ${company['name'] ?? 'votre entreprise'}.'),
        const SizedBox(height: 24),
        Material(
          color: const Color(0xFF16324F),
          borderRadius: BorderRadius.circular(8),
          child: InkWell(
            onTap: () => context.go('/assistant'),
            borderRadius: BorderRadius.circular(8),
            child: const Padding(
              padding: EdgeInsets.all(22),
              child: Row(
                children: [
                  Icon(Icons.auto_awesome, color: Color(0xFF65D1C8)),
                  SizedBox(width: 16),
                  Expanded(
                    child: Text(
                      'Que souhaitez-vous comprendre aujourd’hui ?',
                      style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w700),
                    ),
                  ),
                  Icon(Icons.arrow_forward, color: Colors.white),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: const Color(0xFFFFF7E8),
            border: Border.all(color: const Color(0xFFE8C77B)),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Wrap(
            spacing: 14,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              const Icon(Icons.sync_alt, color: Color(0xFF8A5B00)),
              const Text('Connectez vos ventes pour obtenir vos premiers indicateurs et recommandations.'),
              OutlinedButton.icon(
                onPressed: () => context.go('/connections'),
                icon: const Icon(Icons.add_link),
                label: const Text('Connecter mes ventes'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 28),
        Text('Ce mois-ci', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        GridView.count(
          crossAxisCount: wide ? 4 : MediaQuery.sizeOf(context).width >= 620 ? 2 : 1,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          childAspectRatio: wide ? 1.65 : 2.2,
          children: const [
            _Metric(label: 'Chiffre d’affaires', value: '—'),
            _Metric(label: 'Commandes', value: '—'),
            _Metric(label: 'Clients actifs', value: '—'),
            _Metric(label: 'Panier moyen', value: '—'),
          ],
        ),
        const SizedBox(height: 28),
        Text('Priorités recommandées', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(22),
            child: Row(
              children: [
                Icon(Icons.lightbulb_outline, color: Theme.of(context).colorScheme.secondary),
                const SizedBox(width: 14),
                const Expanded(child: Text('Vos priorités apparaîtront ici dès que vos ventes seront connectées.')),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(label),
            const SizedBox(height: 4),
            Text(value, style: Theme.of(context).textTheme.titleLarge),
          ],
        ),
      ),
    );
  }
}
