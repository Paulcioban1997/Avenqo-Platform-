# coding: utf-8
"""
Compiles all 44 canonical locales into web/src/lib/i18n/trading-chat-i18n.ts
Preserves authentic quantitative trading questions across every single language.
"""

import os
import sys
import json
import re

sys.path.insert(0, os.path.abspath("."))
from scripts.trading_chat_data.group_east_asia import DATA_EAST_ASIA
from scripts.trading_chat_data.group_europe_east import DATA_EUROPE_EAST
from scripts.trading_chat_data.group_europe_west_north import DATA_EUROPE_WEST_NORTH
from scripts.trading_chat_data.group_middle_east import DATA_MIDDLE_EAST
from scripts.trading_chat_data.group_south_asia import DATA_SOUTH_ASIA
from scripts.trading_chat_data.group_se_asia import DATA_SE_ASIA
from scripts.trading_chat_data.group_africa import DATA_AFRICA
from scripts.trading_chat_data.group_caucasus_mn import DATA_CAUCASUS_MN

ALL_NEW_DATA = {}
for g in [
    DATA_EAST_ASIA,
    DATA_EUROPE_EAST,
    DATA_EUROPE_WEST_NORTH,
    DATA_MIDDLE_EAST,
    DATA_SOUTH_ASIA,
    DATA_SE_ASIA,
    DATA_AFRICA,
    DATA_CAUCASUS_MN,
]:
    ALL_NEW_DATA.update(g)

print(f"Loaded {len(ALL_NEW_DATA)} new languages from data modules.")

# Read existing file to extract the original 9 implementations (fr, en, es, ro, de, ja, ar, it, pt)
ts_path = "web/src/lib/i18n/trading-chat-i18n.ts"
with open(ts_path, "r", encoding="utf-8") as f:
    orig_code = f.read()

# Extract original 9 language codes
orig_langs = ["fr", "en", "es", "ro", "de", "ja", "ar", "it", "pt"]
orig_blocks = {}

for lang in orig_langs:
    # Pattern to match: '  lang: {\n ... \n  },'
    pattern = rf'(  {lang}: \{{.*?\n  \}}),?\n'
    m = re.search(pattern, orig_code, re.DOTALL)
    if m:
        orig_blocks[lang] = m.group(1).rstrip(",")
    else:
        raise ValueError(f"Could not extract original block for {lang}")

print(f"Extracted {len(orig_blocks)} original language blocks.")

def escape_template_literal(s: str) -> str:
    # Replace single backticks if any
    s = s.replace("`", "\\`")
    # Replace {symbol} with ${symbol} and {interval} with ${interval}
    s = s.replace("{symbol}", "${symbol}").replace("{interval}", "${interval}")
    return s

def format_entry(lang_code: str, data: dict) -> str:
    welcome_str = escape_template_literal(data["welcome"])
    reset_str = escape_template_literal(data["reset"])
    loading_str = escape_template_literal(data["loading"])
    voice_str = escape_template_literal(data["voicePrompt"])
    
    questions_formatted = ",\n".join(f'      {json.dumps(q, ensure_ascii=False)}' for q in data["questions"])

    return f"""  {lang_code}: {{
    title: {json.dumps(data["title"], ensure_ascii=False)},
    badge: {json.dumps(data["badge"], ensure_ascii=False)},
    subtitle: {json.dumps(data["subtitle"], ensure_ascii=False)},
    welcome: (symbol, interval) =>
      `{welcome_str}`,
    reset: (symbol, interval) =>
      `{reset_str}`,
    loading: (symbol) => `{loading_str}`,
    error: {json.dumps(data["error"], ensure_ascii=False)},
    voicePrompt: (symbol, interval) =>
      `{voice_str}`,
    specializedQuestionsLabel: {json.dumps(data["specializedQuestionsLabel"], ensure_ascii=False)},
    shuffleQuestionsLabel: {json.dumps(data["shuffleQuestionsLabel"], ensure_ascii=False)},
    inputPlaceholder: {json.dumps(data["inputPlaceholder"], ensure_ascii=False)},
    clearChatTooltip: {json.dumps(data["clearChatTooltip"], ensure_ascii=False)},
    voiceTooltip: {json.dumps(data["voiceTooltip"], ensure_ascii=False)},
    questions: [
{questions_formatted},
    ],
  }}"""

# Combine all dictionaries
all_entries = []
# 1. Existing 9
for lang in orig_langs:
    all_entries.append(orig_blocks[lang])

# 2. 32 new languages
for lang, d in sorted(ALL_NEW_DATA.items()):
    all_entries.append(format_entry(lang, d))

# 3. Aliases for ar-EG, fr-FR, en-GB
all_entries.append('  "ar-EG": null as unknown as TradingChatStrings')
all_entries.append('  "fr-FR": null as unknown as TradingChatStrings')
all_entries.append('  "en-GB": null as unknown as TradingChatStrings')

entries_block = ",\n".join(all_entries)

final_ts = f"""import type {{ LocaleCode }} from "./types";

export interface TradingChatStrings {{
  title: string;
  badge: string;
  subtitle: string;
  welcome: (symbol: string, interval: string) => string;
  reset: (symbol: string, interval: string) => string;
  loading: (symbol: string) => string;
  error: string;
  voicePrompt: (symbol: string, interval: string) => string;
  specializedQuestionsLabel: string;
  shuffleQuestionsLabel: string;
  inputPlaceholder: string;
  clearChatTooltip: string;
  voiceTooltip: string;
  questions: string[];
}}

export const CHAT_DICTIONARY: Record<string, TradingChatStrings> = {{
{entries_block},
}};

// Set regional aliases
CHAT_DICTIONARY["ar-EG"] = CHAT_DICTIONARY.ar;
CHAT_DICTIONARY["fr-FR"] = CHAT_DICTIONARY.fr;
CHAT_DICTIONARY["en-GB"] = CHAT_DICTIONARY.en;

export function getTradingChatStrings(locale: LocaleCode | string): TradingChatStrings {{
  const code = (locale || "fr").toLowerCase();
  if (CHAT_DICTIONARY[code]) {{
    return CHAT_DICTIONARY[code];
  }}
  const prefix = code.split("-")[0];
  if (CHAT_DICTIONARY[prefix]) {{
    return CHAT_DICTIONARY[prefix];
  }}
  return CHAT_DICTIONARY.en || CHAT_DICTIONARY.fr;
}}

export function pickRandomTradingQuestions(locale: LocaleCode | string, count: number = 3): string[] {{
  const strings = getTradingChatStrings(locale);
  const pool = strings.questions && strings.questions.length > 0 ? strings.questions : CHAT_DICTIONARY.en.questions;
  const shuffled = [...pool].sort(() => 0.5 - Math.random());
  return shuffled.slice(0, count);
}}
"""

with open(ts_path, "w", encoding="utf-8") as f:
    f.write(final_ts)

print(f"Successfully generated {ts_path} with all 44 canonical locales!")
