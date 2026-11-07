"""SDK contract tests: no provider requests, no live payment credentials."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from backend.app.services.voice_billing_gateway import VoiceBillingGateway


def value(data):
    return SimpleNamespace(to_dict=lambda: data)


@pytest.fixture
def gateway():
    settings=SimpleNamespace(stripe_secret_key=None,stripe_automatic_tax_enabled=False)
    gateway=VoiceBillingGateway(settings)
    gateway.client=MagicMock()
    voice={'id':'price_voice','active':True,'currency':'cad','unit_amount':499,'tax_behavior':'exclusive',
           'recurring':{'interval':'month','interval_count':1},'metadata':{'avenqo_kind':'voice_number'}}
    base={'id':'price_base','currency':'cad','unit_amount':2999,'recurring':{'interval':'month'}}
    gateway.client.v1.prices.retrieve.return_value=value(voice)
    gateway.client.v1.subscriptions.retrieve.return_value=value({'id':'sub_fixture','customer':'cus_fixture','status':'active',
        'collection_method':'charge_automatically','metadata':{'tenant':'fixture'},'items':{'data':[{'id':'si_base','price':base,'quantity':1}]}})
    gateway.client.v1.invoices.create_preview.side_effect=[value({'total':499,'amount_due':499}),value({'total':3498})]
    return gateway


def test_preview_keeps_base_and_displays_full_monthly_total(gateway):
    q=gateway.preview('cus_fixture','sub_fixture','price_voice',1234)
    assert q['monthly_total_before_tax']==q['monthly_invoice_total']==3498
    assert q['initial_amount_due']==499 and q['number_monthly_amount']==499
    calls=gateway.client.v1.invoices.create_preview.call_args_list
    assert calls[0].kwargs['params']['subscription_details']['proration_date']==1234
    assert calls[1].kwargs['params']['preview_mode']=='recurring'
    assert not gateway.client.v1.subscriptions.update.called


def test_payment_appends_only_addon_and_is_idempotent(gateway):
    q=gateway.preview('cus_fixture','sub_fixture','price_voice',1234)
    order=SimpleNamespace(id=uuid4(),snapshot={'billing':q},stripe_subscription_id='sub_fixture')
    gateway.client.v1.subscriptions.update.return_value=value({'latest_invoice':{'id':'in_fixture'}})
    assert gateway.add_number(order)['id']=='in_fixture'
    call=gateway.client.v1.subscriptions.update.call_args
    assert call.kwargs['params']['items']==[{'price':'price_voice','quantity':1}]
    assert call.kwargs['params']['payment_behavior']=='pending_if_incomplete'
    assert call.kwargs['params']['metadata']['tenant']=='fixture'
    assert call.kwargs['options']['idempotency_key']==f'voice-bill:{order.id}'


def test_compensation_refunds_only_voice_line(gateway):
    order=SimpleNamespace(id=uuid4(),stripe_customer_id='cus_fixture',stripe_subscription_id='sub_fixture',stripe_invoice_id='in_fixture',
        snapshot={'billing':{'price_id':'price_voice','initial_amount_due':499}})
    gateway.client.v1.subscriptions.retrieve.return_value=value({'customer':'cus_fixture','metadata':{'avenqo_voice_order_id':str(order.id)},
        'items':{'data':[{'id':'si_base','price':{'id':'price_base'}},{'id':'si_voice','price':{'id':'price_voice'}}]}})
    gateway.client.v1.invoices.retrieve.return_value=value({'id':'in_fixture','status':'paid','lines':{'data':[
        {'id':'il_base','price':{'id':'price_base'}},{'id':'il_voice','price':{'id':'price_voice'}}]}})
    gateway.client.v1.credit_notes.preview.return_value=value({'amount':499})
    gateway.compensate(order)
    gateway.client.v1.subscription_items.delete.assert_called_once_with('si_voice',params={'proration_behavior':'none'})
    credit=gateway.client.v1.credit_notes.create.call_args.kwargs
    assert credit['params']['lines']==[{'type':'invoice_line_item','invoice_line_item':'il_voice','quantity':1}]
    assert credit['params']['refund_amount']==499


def test_unmarked_provider_price_cannot_charge(gateway):
    gateway.client.v1.prices.retrieve.return_value=value({'active':True,'unit_amount':499,'tax_behavior':'exclusive','recurring':{'interval':'month'}})
    with pytest.raises(ValueError):gateway.preview('cus_fixture','sub_fixture','price_voice',1234)
    assert not gateway.client.v1.subscriptions.update.called


def test_cancel_active_number_removes_addon_without_refunding_past_service(gateway):
    order=SimpleNamespace(id=uuid4(),stripe_customer_id='cus_fixture',stripe_subscription_id='sub_fixture',stripe_invoice_id='in_fixture',snapshot={'billing':{'price_id':'price_voice','initial_amount_due':499}})
    gateway.client.v1.subscriptions.retrieve.return_value=value({'customer':'cus_fixture','metadata':{'avenqo_voice_order_id':str(order.id)},'items':{'data':[{'id':'si_voice','price':{'id':'price_voice'}}]}})
    gateway.compensate(order,refund=False)
    gateway.client.v1.subscription_items.delete.assert_called_once()
    assert not gateway.client.v1.credit_notes.create.called
