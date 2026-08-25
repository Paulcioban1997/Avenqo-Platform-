import json
import sys
sys.path.insert(0, 'scripts')
from i18n_data_kovi import MODULES_HEADER, MODULE_NAMES, MODULE_DESCRIPTIONS, PRICING, COMMON_OVERRIDES, FINALCTA_TRYFREE
from i18n_assistant_auth_kovi import ASSISTANT, AUTH
from i18n_dashboardhome_full_kovi import DASHBOARD_HOME
from i18n_admin_full_kovi import ADMIN
from i18n_onboarding_kovi import ONBOARDING
from i18n_company_kovi import COMPANY

AVAILABLE = [True, False, False, False, False, False, False]

def apply_locale(code):
    path = f'assets/i18n/{code}.json'
    with open(path, encoding='utf-8') as f:
        d = json.load(f)

    items = []
    for i, name in enumerate(MODULE_NAMES):
        items.append({"name": name, "description": MODULE_DESCRIPTIONS[code][i], "available": AVAILABLE[i]})
    d['modulesSection'] = {**MODULES_HEADER[code], "items": items}

    d['pricing'] = PRICING[code]
    d['common']['tryFree'] = COMMON_OVERRIDES[code]['tryFree']
    d['common']['noCreditCard'] = COMMON_OVERRIDES[code]['noCreditCard']
    d['finalCta']['tryFree'] = FINALCTA_TRYFREE[code]

    # These 4 sections were entirely missing for ko/vi - set in full.
    d['assistant'] = ASSISTANT[code]
    d['auth'] = AUTH[code]
    d['dashboardHome'] = DASHBOARD_HOME[code]
    d['admin'] = ADMIN[code]

    d['onboarding'] = ONBOARDING[code]
    d['company'] = COMPANY[code]

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'patched {code}.json (full rebuild)')

for code in MODULES_HEADER:
    apply_locale(code)
