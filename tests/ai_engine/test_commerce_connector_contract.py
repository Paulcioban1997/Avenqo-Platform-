from uuid import uuid4

import pytest

from shared.ai_engine.connectors.commerce import (
    CommerceConnector,
    ConnectorAuthMethod,
    ConnectorCapability,
    ConnectorCapabilityError,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorImplementationStatus,
    ConnectorSyncContext,
)


class _OrdersOnlyConnector(CommerceConnector):
    definition = ConnectorDefinition(
        provider="orders-only",
        display_name="Orders Only",
        category=ConnectorCategory.ECOMMERCE,
        implementation_status=ConnectorImplementationStatus.AVAILABLE,
        auth_method=ConnectorAuthMethod.OAUTH2,
        capabilities=frozenset({ConnectorCapability.ORDERS}),
    )

    def authenticate(self, *, tenant_id, configuration):
        return "https://provider.example/authorize"

    async def handle_oauth_callback(self, *, tenant_id, callback_parameters):
        return {"access_token": "test-token"}

    async def test_connection(self, context):
        return True

    async def get_sync_status(self, *, tenant_id, connection_id):
        return "READY"

    async def disconnect(self, context):
        return None


@pytest.mark.asyncio
async def test_unsupported_connector_capability_fails_explicitly() -> None:
    connector = _OrdersOnlyConnector()
    context = ConnectorSyncContext(
        tenant_id=uuid4(),
        connection_id=uuid4(),
        access_token="backend-only-token",
        external_account_id="store.example",
    )

    with pytest.raises(ConnectorCapabilityError, match="inventory"):
        await connector.sync_inventory(context)


def test_available_definition_is_enabled() -> None:
    assert _OrdersOnlyConnector.definition.enabled is True