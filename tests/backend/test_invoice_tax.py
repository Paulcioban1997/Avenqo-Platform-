from types import SimpleNamespace
import pytest
from backend.app.services.invoice_tax import invoice_tax_snapshot
from backend.app.services.stripe_gateway import StripeGateway, StripeTaxConfigurationError


def test_modern_tax_components_preserve_actual_amounts_and_rates():
    invoice = {"total_taxes": [
        {"amount":150, "taxable_amount":2999, "tax_behavior":"exclusive", "tax_rate_details":{"tax_rate":"txr_gst"},
         "_avenqo_tax_rate":{"tax_type":"gst", "percentage":5.0, "country":"CA"}, "taxability_reason":"standard_rated"},
        {"amount":299, "tax_rate_details":{"tax_rate":"txr_qst"}, "_avenqo_tax_rate":{"tax_type":"qst", "percentage":9.975, "state":"QC"}},
    ]}
    rows = invoice_tax_snapshot(invoice)
    assert sum(row['amount'] for row in rows)==449
    assert [row['name'] for row in rows]==['TPS','TVQ']
    assert rows[1]['percentage']==9.975
    assert rows[0]['taxable_amount']==2999


def test_missing_tax_components_do_not_invent_taxes():
    assert invoice_tax_snapshot({"total":2999, "customer_address":{"country":"CA","state":"QC"}})==[]
    assert invoice_tax_snapshot({"total_tax_amounts":[{"amount":0,"tax_rate":{"display_name":"Exonérée","percentage":0}}]})[0]['percentage']==0


@pytest.mark.parametrize('status,registered,code', [('pending',False,None),('active',False,'txcd_test'),('active',True,None)])
def test_automatic_tax_requires_ready_settings_registration_and_classification(monkeypatch,status,registered,code):
    settings=SimpleNamespace(to_dict=lambda:{'status':status,'defaults':{'tax_code':code}})
    client=SimpleNamespace(v1=SimpleNamespace(tax=SimpleNamespace(settings=SimpleNamespace(retrieve=lambda:settings),
        registrations=SimpleNamespace(list=lambda params:SimpleNamespace(data=[{'status':'active'}] if registered else [])))))
    monkeypatch.setattr('backend.app.services.stripe_gateway.stripe.StripeClient',lambda key:client)
    with pytest.raises(StripeTaxConfigurationError):
        StripeGateway('sk_test',automatic_tax_enabled=True)._tax_options()


def test_ready_tax_collects_address_and_enabled_options_without_changing_legacy(monkeypatch):
    settings=SimpleNamespace(to_dict=lambda:{'status':'active','defaults':{'tax_code':'txcd_test','tax_behavior':'exclusive'}})
    client=SimpleNamespace(v1=SimpleNamespace(tax=SimpleNamespace(settings=SimpleNamespace(retrieve=lambda:settings),
        registrations=SimpleNamespace(list=lambda params:SimpleNamespace(data=[{'status':'active'}])))))
    monkeypatch.setattr('backend.app.services.stripe_gateway.stripe.StripeClient',lambda key:client)
    assert StripeGateway('sk_test')._tax_options()=={}
    params=StripeGateway('sk_test',automatic_tax_enabled=True)._tax_options()
    assert params['automatic_tax']=={'enabled':True}
    assert params['billing_address_collection']=='required'
    assert params['customer_update']['address']=='auto'


@pytest.mark.parametrize('simulation',[False,True])
def test_pdf_details_actual_taxes_without_rewriting_paid_amount(monkeypatch,simulation):
    import io
    from datetime import datetime, timezone
    from uuid import uuid4
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from pypdf import PdfReader
    from backend.app.config.settings import get_settings
    from backend.app.models import Base, BillingInvoice
    from backend.app.services.invoice_fiscal_service import InvoiceFiscalService
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_fiscal_fixture')
    get_settings.cache_clear()
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine)
    invoice=BillingInvoice(id=uuid4(),company_id=uuid4(),stripe_invoice_id='in_fiscal_fixture',number='SIMULATION-QC-0001',
        plan_code='base',status='draft',currency='cad',subtotal=2999,discount_total=0,tax_total=449,total=3448,
        amount_due=3448,amount_paid=0,line_items=[{'description':'Abonnement Avenqo Base','quantity':1,'amount':2999}],
        billing_details={'name':'Client de test','tax_breakdown':[{'name':'TPS','percentage':5,'amount':150},{'name':'TVQ','percentage':9.975,'amount':299}]},
        issued_at=datetime.now(timezone.utc))
    with Session(engine) as db:
        pdf,_,_=InvoiceFiscalService(db).generate_invoice_pdf(invoice,simulation=simulation)
    text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert 'TPS (5 %)' in text and 'TVQ (9,975 %)' in text
    assert '1,50 CAD' in text and '2,99 CAD' in text and '34,48 CAD' in text
    assert 'ENVIRONNEMENT TEST' in text and '0,00 CAD' in text
    assert invoice.amount_paid==0 and invoice.tax_total==449
    assert ('SIMULATION FISCALE' in text)==simulation
    get_settings.cache_clear()
