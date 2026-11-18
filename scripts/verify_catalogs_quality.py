import json

with open("web/src/lib/i18n/voice-industry-catalogs.generated.json", "r", encoding="utf-8") as f:
    catalogs = json.load(f)

print(f"Total locales in generated JSON: {len(catalogs)}")

en_caps_by_ind = {}
fr_caps_by_ind = {}
for ind_id, ind_data in catalogs["en"]["industries"].items():
    en_caps_by_ind[ind_id] = set(ind_data["suggestedCapabilities"])

for ind_id, ind_data in catalogs["fr"]["industries"].items():
    fr_caps_by_ind[ind_id] = set(ind_data["suggestedCapabilities"])

leaks = []
for loc, loc_data in catalogs.items():
    if loc in ("en", "en-GB", "fr", "fr-FR"):
        continue
    for ind_id, ind_data in loc_data["industries"].items():
        caps = ind_data["suggestedCapabilities"]
        if not caps:
            leaks.append((loc, ind_id, "EMPTY"))
            continue
        # Check if caps match English or French exactly
        en_matches = set(caps) & en_caps_by_ind[ind_id]
        if en_matches:
            leaks.append((loc, ind_id, f"EN_LEAK: {en_matches}"))
        fr_matches = set(caps) & fr_caps_by_ind[ind_id]
        if fr_matches:
            leaks.append((loc, ind_id, f"FR_LEAK: {fr_matches}"))

if leaks:
    print(f"FAILED: Found {len(leaks)} capability leaks:")
    for leak in leaks[:20]:
        print(" ", leak)
else:
    print("SUCCESS: Zero English or French capability leaks across all 40 non-EN/FR locales and 30 industries!")
