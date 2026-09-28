import 'package:avenqo/agents/agent_registry.dart';
import 'package:avenqo/app/destinations.dart';
import 'package:avenqo/features/admin/admin_destinations.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('registry has stable unique identities and current operational agents', () {
    expect(avenqoAgentRegistry, hasLength(11));
    expect(avenqoAgentRegistry.map((agent) => agent.id).toSet(), hasLength(11));

    final retail = agentById('retail');
    expect(retail.isAvailable, isTrue);
    expect(retail.route, '/retail');
    expect(retail.nameKey, 'retailName');

    final availableAgents = avenqoAgentRegistry.where((agent) => agent.isAvailable);
    expect(availableAgents.map((agent) => agent.id), containsAll(<String>['retail', 'crm', 'accounting']));
    final futureAgents = avenqoAgentRegistry.where((agent) => !agent.isAvailable);
    expect(futureAgents, hasLength(8));
    expect(futureAgents.every((agent) => !agent.isAvailable), isTrue);
    expect(futureAgents.every((agent) => agent.route == null), isTrue);
  });

  test('Appointments identity remains industry-neutral', () {
    final appointments = agentById('appointments');
    expect(appointments.nameKey, 'appointmentsName');
    expect(appointments.descriptionKey, 'appointmentsDescription');
    expect(appointments.requiredPlan, isNull);
  });

  test('global navigation exposes Agents without standalone Retail functions', () {
    expect(appDestinations.map((item) => item.path), contains('/agents'));
    expect(adminDestinations.map((item) => item.path), contains('/admin/agents'));
    expect(
      appDestinations.map((item) => item.path),
      contains('/dashboard'),
    );
    expect(
      appDestinations.map((item) => item.path),
      isNot(contains(anyOf('/sales', '/customers', '/products', '/recommendations'))),
    );
  });
}