import os

for root, dirs, files in os.walk(r'frontend\assets\i18n'):
    for f in files:
        if f.endswith('.json'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8') as fp:
                c = fp.read()
            if 'bonjour@avenqo.ca' in c:
                c = c.replace('bonjour@avenqo.ca', 'info@avenqo.ca')
                with open(p, 'w', encoding='utf-8') as fp:
                    fp.write(c)

print("Updated frontend assets i18n json files.")
