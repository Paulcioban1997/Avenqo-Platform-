import json
import sys
sys.path.insert(0, 'scripts')
from i18n_data_asia1 import MODULES_HEADER, MODULE_NAMES, MODULE_DESCRIPTIONS, PRICING, COMMON_OVERRIDES, FINALCTA_TRYFREE, ASSISTANT_SUGGESTIONS
from i18n_onboarding_asia1 import ONBOARDING
from i18n_company_asia1a import COMPANY as COMPANY_A
from i18n_company_asia1b import COMPANY_B
from i18n_dashboardhome_extra_asia1 import DASHBOARD_HOME_EXTRA

COMPANY = {**COMPANY_A, **COMPANY_B}

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

    d.setdefault('assistant', {})['suggestions'] = ASSISTANT_SUGGESTIONS[code]

    d['onboarding'] = ONBOARDING[code]
    d['company'] = COMPANY[code]
    d['dashboardHome'].update(DASHBOARD_HOME_EXTRA[code])

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'patched {code}.json')

for code in MODULES_HEADER:
    apply_locale(code)
