enum AvenqoAgentAvailability { available, comingSoon }

class AvenqoAgentDefinition {
  const AvenqoAgentDefinition({
    required this.id,
    required this.nameKey,
    required this.descriptionKey,
    required this.iconIdentifier,
    required this.availability,
    this.route,
    this.requiredPlan,
  });

  final String id;
  final String nameKey;
  final String descriptionKey;
  final String iconIdentifier;
  final AvenqoAgentAvailability availability;
  final String? route;
  final String? requiredPlan;

  bool get isAvailable => availability == AvenqoAgentAvailability.available;
}

const avenqoAgentRegistry = <AvenqoAgentDefinition>[
  AvenqoAgentDefinition(
    id: 'retail',
    nameKey: 'retailName',
    descriptionKey: 'retailDescription',
    iconIdentifier: 'storefront',
    availability: AvenqoAgentAvailability.available,
    route: '/dashboard',
  ),
  AvenqoAgentDefinition(
    id: 'marketing',
    nameKey: 'marketingName',
    descriptionKey: 'marketingDescription',
    iconIdentifier: 'campaign',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'crm',
    nameKey: 'crmName',
    descriptionKey: 'crmDescription',
    iconIdentifier: 'contacts',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'hr',
    nameKey: 'hrName',
    descriptionKey: 'hrDescription',
    iconIdentifier: 'groups',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'accounting',
    nameKey: 'accountingName',
    descriptionKey: 'accountingDescription',
    iconIdentifier: 'account_balance',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'ocr',
    nameKey: 'ocrName',
    descriptionKey: 'ocrDescription',
    iconIdentifier: 'document_scanner',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'voice',
    nameKey: 'voiceName',
    descriptionKey: 'voiceDescription',
    iconIdentifier: 'mic',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'media',
    nameKey: 'mediaName',
    descriptionKey: 'mediaDescription',
    iconIdentifier: 'perm_media',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'legal',
    nameKey: 'legalName',
    descriptionKey: 'legalDescription',
    iconIdentifier: 'gavel',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'appointments',
    nameKey: 'appointmentsName',
    descriptionKey: 'appointmentsDescription',
    iconIdentifier: 'calendar_month',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
  AvenqoAgentDefinition(
    id: 'workflow',
    nameKey: 'workflowName',
    descriptionKey: 'workflowDescription',
    iconIdentifier: 'account_tree',
    availability: AvenqoAgentAvailability.comingSoon,
  ),
];

AvenqoAgentDefinition agentById(String id) =>
    avenqoAgentRegistry.firstWhere((agent) => agent.id == id);