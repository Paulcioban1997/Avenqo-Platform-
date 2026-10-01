"""Exact, locale-scoped natural confirmation phrases.

Matching is whole-message equality after Unicode whitespace/case normalization;
there is no substring authorization.
"""

from __future__ import annotations

import re
import unicodedata

_PHRASES: dict[str, tuple[str, ...]] = {
    "fr": ("oui confirme", "oui je confirme", "confirme"),
    "en": ("yes confirm", "yes confirm it", "i confirm"),
    "es": ("si confirmalo", "sí confírmalo", "si confirmo"),
    "pt": ("sim confirme", "sim confirmo", "confirmo"),
    "fr-FR": ("oui confirme", "oui je confirme", "confirme"),
    "en-GB": ("yes confirm", "yes confirm it", "i confirm"),
    "ro": ("da confirmă", "da confirm", "confirm"),
    "de": ("ja bestätigen", "ja ich bestätige", "bestätigen"),
    "it": ("sì conferma", "si confermo", "conferma"),
    "nl": ("ja bevestig", "ja ik bevestig", "bevestig"),
    "pl": ("tak potwierdź", "tak potwierdzam", "potwierdź"),
    "ru": ("да подтверждаю", "да подтвердить", "подтверждаю"),
    "uk": ("так підтверджую", "так підтвердити", "підтверджую"),
    "el": ("ναι επιβεβαιώνω", "ναι επιβεβαίωσε", "επιβεβαιώνω"),
    "sv": ("ja bekräfta", "ja jag bekräftar", "bekräfta"),
    "tr": ("evet onayla", "evet onaylıyorum", "onayla"),
    "cs": ("ano potvrzuji", "ano potvrď", "potvrzuji"),
    "ka": ("დიახ დაადასტურე", "დიახ ვადასტურებ", "დაადასტურე"),
    "hy": ("այո հաստատում եմ", "այո հաստատիր", "հաստատում եմ"),
    "ar": ("نعم أؤكد", "نعم أكد", "أؤكد"),
    "ar-EG": ("نعم أؤكد", "نعم أكد", "أؤكد"),
    "he": ("כן אשר", "כן אני מאשר", "אשר"),
    "fa": ("بله تایید", "بله تأیید می‌کنم", "تایید"),
    "sw": ("ndiyo thibitisha", "ndiyo ninathibitisha", "thibitisha"),
    "am": ("አዎ አረጋግጥ", "አዎ አረጋግጣለሁ", "አረጋግጥ"),
    "af": ("ja bevestig", "ja ek bevestig", "bevestig"),
    "ha": ("eh tabbatar", "eh na tabbatar", "tabbatar"),
    "zh": ("是的确认", "是我确认", "确认"),
    "ja": ("はい確認", "はい確認します", "確認"),
    "ko": ("네 확인", "네 확인합니다", "확인"),
    "hi": ("हाँ पुष्टि", "हाँ मैं पुष्टि करता हूँ", "पुष्टि"),
    "bn": ("হ্যাঁ নিশ্চিত", "হ্যাঁ আমি নিশ্চিত করছি", "নিশ্চিত"),
    "ur": ("ہاں تصدیق", "ہاں میں تصدیق کرتا ہوں", "تصدیق"),
    "ta": ("ஆம் உறுதிப்படுத்து", "ஆம் உறுதிசெய்கிறேன்", "உறுதிப்படுத்து"),
    "pa": ("ਹਾਂ ਪੁਸ਼ਟੀ", "ਹਾਂ ਮੈਂ ਪੁਸ਼ਟੀ ਕਰਦਾ ਹਾਂ", "ਪੁਸ਼ਟੀ"),
    "ne": ("हो पुष्टि", "हो म पुष्टि गर्छु", "पुष्टि"),
    "vi": ("có xác nhận", "có tôi xác nhận", "xác nhận"),
    "th": ("ใช่ ยืนยัน", "ใช่ฉันยืนยัน", "ยืนยัน"),
    "id": ("ya konfirmasi", "ya saya konfirmasi", "konfirmasi"),
    "ms": ("ya sahkan", "ya saya sahkan", "sahkan"),
    "tl": ("oo kumpirmahin", "oo kinukumpirma ko", "kumpirmahin"),
    "my": ("အတည်ပြုပါ", "ဟုတ်ကဲ့ အတည်ပြုပါ", "အတည်ပြု"),
    "km": ("បាទ បញ្ជាក់", "បាទ ខ្ញុំបញ្ជាក់", "បញ្ជាក់"),
    "mn": ("тийм баталгаажуул", "тийм баталгаажуулна", "баталгаажуул"),
}

_REQUIRED: dict[str, str] = {
    "fr": "Une confirmation explicite est requise pour cette action.", "en": "Explicit confirmation is required for this action.",
    "es": "Se requiere una confirmación explícita para esta acción.", "pt": "É necessária uma confirmação explícita para esta ação.",
    "fr-FR": "Une confirmation explicite est requise pour cette action.", "en-GB": "Explicit confirmation is required for this action.",
    "ro": "Este necesară confirmarea explicită pentru această acțiune.", "de": "Für diese Aktion ist eine ausdrückliche Bestätigung erforderlich.",
    "it": "È necessaria una conferma esplicita per questa azione.", "nl": "Voor deze actie is expliciete bevestiging vereist.",
    "pl": "Ta czynność wymaga wyraźnego potwierdzenia.", "ru": "Для этого действия требуется явное подтверждение.",
    "uk": "Для цієї дії потрібне явне підтвердження.", "el": "Απαιτείται ρητή επιβεβαίωση για αυτήν την ενέργεια.",
    "sv": "Den här åtgärden kräver en uttrycklig bekräftelse.", "tr": "Bu işlem için açık onay gerekiyor.",
    "cs": "Tato akce vyžaduje výslovné potvrzení.", "ka": "ამ მოქმედებისთვის საჭიროა მკაფიო დადასტურება.",
    "hy": "Այս գործողության համար անհրաժեշտ է հստակ հաստատում։", "ar": "يلزم تأكيد صريح لهذا الإجراء.",
    "ar-EG": "يلزم تأكيد صريح لهذا الإجراء.", "he": "נדרש אישור מפורש לפעולה הזו.",
    "fa": "برای این اقدام تأیید صریح لازم است.", "sw": "Uthibitisho wa wazi unahitajika kwa hatua hii.",
    "am": "ለዚህ ተግባር ግልጽ ማረጋገጫ ያስፈልጋል።", "af": "Eksplisiete bevestiging is vir hierdie aksie nodig.",
    "ha": "Ana buƙatar tabbatarwa bayyananniya don wannan aiki.", "zh": "此操作需要明确确认。", "ja": "この操作には明示的な確認が必要です。",
    "ko": "이 작업에는 명시적인 확인이 필요합니다.", "hi": "इस कार्रवाई के लिए स्पष्ट पुष्टि आवश्यक है।", "bn": "এই কাজের জন্য স্পষ্ট নিশ্চিতকরণ প্রয়োজন।",
    "ur": "اس کارروائی کے لیے واضح تصدیق ضروری ہے۔", "ta": "இந்தச் செயலுக்கு வெளிப்படையான உறுதிப்படுத்தல் தேவை.",
    "pa": "ਇਸ ਕਾਰਵਾਈ ਲਈ ਸਪਸ਼ਟ ਪੁਸ਼ਟੀ ਲੋੜੀਂਦੀ ਹੈ।", "ne": "यो कार्यका लागि स्पष्ट पुष्टि आवश्यक छ।", "vi": "Hành động này cần xác nhận rõ ràng.",
    "th": "การดำเนินการนี้ต้องมีการยืนยันอย่างชัดเจน", "id": "Tindakan ini memerlukan konfirmasi eksplisit.", "ms": "Tindakan ini memerlukan pengesahan jelas.",
    "tl": "Kailangan ng malinaw na kumpirmasyon para sa pagkilos na ito.", "my": "ဤလုပ်ဆောင်ချက်အတွက် ပြတ်သားသောအတည်ပြုချက် လိုအပ်သည်။",
    "km": "សកម្មភាពនេះត្រូវការការបញ្ជាក់ច្បាស់លាស់។", "mn": "Энэ үйлдэлд тодорхой баталгаажуулалт шаардлагатай.",
}


def normalize_confirmation(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().strip()
    text = "".join(char if not unicodedata.category(char).startswith("P") else " " for char in text)
    return re.sub(r"\s+", " ", text).strip()


def is_natural_confirmation(locale: str, text: str) -> bool:
    return normalize_confirmation(text) in {
        normalize_confirmation(phrase) for phrase in _PHRASES.get(locale, ())
    }


def confirmation_required_message(locale: str) -> str:
    return _REQUIRED.get(locale, _REQUIRED["en"])


SUPPORTED_CONFIRMATION_LOCALES = frozenset(_PHRASES)
