from functools import lru_cache
import json
from pathlib import Path

from backend.app.core.locale_catalog import resolve_locale


@lru_cache(maxsize=1)
def voice_messages():
    return json.loads((Path(__file__).resolve().parents[3] / "shared/locales/voice_auth_messages.json").read_text(encoding="utf-8"))


def voice_auth_message(locale, index):
    return voice_messages()[resolve_locale(locale)][index]


_VOICE_GREETINGS = {
    "af": "Hallo, {name}. Ek is die virtuele assistent. Hierdie oproep kan opgeneem word.",
    "am": "ሰላም፣ {name}። እኔ ምናባዊ ረዳት ነኝ። ይህ ጥሪ ሊቀረጽ ይችላል።",
    "ar": "مرحبًا، {name}. أنا المساعد الافتراضي. قد يتم تسجيل هذه المكالمة.",
    "bn": "হ্যালো, {name}। আমি ভার্চুয়াল সহকারী। এই কলটি রেকর্ড করা হতে পারে।",
    "cs": "Dobrý den, {name}. Jsem virtuální asistent. Tento hovor může být nahráván.",
    "de": "Guten Tag, {name}. Ich bin der virtuelle Assistent. Dieses Gespräch kann aufgezeichnet werden.",
    "el": "Γεια σας, {name}. Είμαι ο εικονικός βοηθός. Αυτή η κλήση μπορεί να καταγραφεί.",
    "en": "Hello, {name}. I am the virtual assistant. This call may be recorded.",
    "es": "Hola, {name}. Soy el asistente virtual. Esta llamada puede ser grabada.",
    "fa": "سلام، {name}. من دستیار مجازی هستم. ممکن است این تماس ضبط شود.",
    "fr": "Bonjour, {name}. Je suis l’assistant virtuel. Cet appel peut être enregistré.",
    "ha": "Sannu, {name}. Ni mataimakin kama-da-wane ne. Ana iya yin rikodin wannan kira.",
    "he": "שלום, {name}. אני העוזר הווירטואלי. ייתכן שהשיחה מוקלטת.",
    "hi": "नमस्ते, {name}। मैं वर्चुअल सहायक हूँ। यह कॉल रिकॉर्ड की जा सकती है।",
    "hy": "Բարև, {name}։ Ես վիրտուալ օգնականն եմ։ Այս զանգը կարող է ձայնագրվել։",
    "id": "Halo, {name}. Saya asisten virtual. Panggilan ini mungkin direkam.",
    "it": "Buongiorno, {name}. Sono l’assistente virtuale. Questa chiamata potrebbe essere registrata.",
    "ja": "こんにちは、{name}。バーチャルアシスタントです。この通話は録音される場合があります。",
    "ka": "გამარჯობა, {name}. მე ვირტუალური ასისტენტი ვარ. ეს ზარი შეიძლება ჩაიწეროს.",
    "km": "សួស្តី {name}។ ខ្ញុំជាជំនួយការនិម្មិត។ ការហៅនេះអាចត្រូវបានថតទុក។",
    "ko": "안녕하세요, {name}. 가상 비서입니다. 이 통화는 녹음될 수 있습니다.",
    "ms": "Helo, {name}. Saya pembantu maya. Panggilan ini mungkin dirakam.",
    "my": "မင်္ဂလာပါ၊ {name}။ ကျွန်ုပ်သည် အတုအယောင်အကူအညီပေးသူဖြစ်သည်။ ဤခေါ်ဆိုမှုကို မှတ်တမ်းတင်နိုင်ပါသည်။",
    "ne": "नमस्कार, {name}। म भर्चुअल सहायक हुँ। यो कल रेकर्ड हुन सक्छ।",
    "nl": "Hallo, {name}. Ik ben de virtuele assistent. Dit gesprek kan worden opgenomen.",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, {name}। ਮੈਂ ਵਰਚੁਅਲ ਸਹਾਇਕ ਹਾਂ। ਇਹ ਕਾਲ ਰਿਕਾਰਡ ਕੀਤੀ ਜਾ ਸਕਦੀ ਹੈ।",
    "pl": "Dzień dobry, {name}. Jestem wirtualnym asystentem. Ta rozmowa może być nagrywana.",
    "pt": "Olá, {name}. Sou o assistente virtual. Esta chamada pode ser gravada.",
    "ro": "Bună ziua, {name}. Sunt asistentul virtual. Acest apel poate fi înregistrat.",
    "ru": "Здравствуйте, {name}. Я виртуальный помощник. Этот звонок может записываться.",
    "sv": "Hej, {name}. Jag är den virtuella assistenten. Det här samtalet kan spelas in.",
    "sw": "Habari, {name}. Mimi ni msaidizi pepe. Simu hii inaweza kurekodiwa.",
    "ta": "வணக்கம், {name}. நான் மெய்நிகர் உதவியாளர். இந்த அழைப்பு பதிவு செய்யப்படலாம்.",
    "th": "สวัสดี {name} ฉันเป็นผู้ช่วยเสมือน สายนี้อาจมีการบันทึกเสียง",
    "tl": "Kamusta, {name}. Ako ang virtual assistant. Maaaring i-record ang tawag na ito.",
    "tr": "Merhaba, {name}. Ben sanal asistanım. Bu görüşme kaydedilebilir.",
    "uk": "Вітаю, {name}. Я віртуальний помічник. Цей дзвінок може записуватися.",
    "ur": "السلام علیکم، {name}۔ میں ورچوئل معاون ہوں۔ یہ کال ریکارڈ کی جا سکتی ہے۔",
    "vi": "Xin chào, {name}. Tôi là trợ lý ảo. Cuộc gọi này có thể được ghi âm.",
    "zh": "您好，{name}。我是虚拟助理。本次通话可能会被录音。",
}



_VOICE_NATURAL_GREETINGS = {
    "af": "Goeiedag, welkom by {name}. Hoe kan ek jou vandag help?",
    "am": "ሰላም፣ እንኳን ወደ {name} በደህና መጡ። ዛሬ በምን ልርዳዎ?",
    "ar": "مرحباً بكم في {name}. كيف يمكنني مساعدتكم اليوم؟",
    "bn": "নমস্কার, {name}-এ আপনাকে স্বাগত। আজ কীভাবে সাহায্য করতে পারি?",
    "cs": "Dobrý den, vítejte v {name}. Jak vám mohu dnes pomoci?",
    "de": "Guten Tag, herzlich willkommen bei {name}. Wie kann ich Ihnen heute helfen?",
    "el": "Γεια σας, καλώς ορίσατε στην {name}. Πώς μπορώ να σας βοηθήσω σήμερα;",
    "en": "Hello, thank you for calling {name}. How can I help you today?",
    "es": "Hola, le damos la bienvenida a {name}. ¿Cómo puedo ayudarle hoy?",
    "fa": "سلام، به {name} خوش آمدید. امروز چطور می‌توانم به شما کمک کنم؟",
    "fr": "Bonjour, bienvenue chez {name}. Comment puis-je vous aider aujourd'hui ?",
    "ha": "Barka, barka da zuwa {name}. Ta yaya zan iya taimaka muku yau?",
    "he": "שלום, ברוכים הבאים ל-{name}. כיצד אוכל לעזור לך היום?",
    "hi": "नमस्ते, {name} में आपका स्वागत है। आज मैं आपकी क्या मदद कर सकता हूँ?",
    "hy": "Բարև ձեզ, բարի գալուստ {name}։ Ինչո՞վ կարող եմ օգնել ձեզ այսօր։",
    "id": "Halo, selamat datang di {name}. Ada yang bisa saya bantu hari ini?",
    "it": "Buongiorno, benvenuto da {name}. Come posso aiutarla oggi?",
    "ja": "お電話ありがとうございます、{name}でございます。本日はどのようなご用件でしょうか？",
    "ka": "გამარჯობა, კეთილი იყოს თქვენი მობრძანება {name}-ში. რით შემიძლია დაგეხმაროთ დღეს?",
    "km": "ជំរាបសួរ សូមស្វាគមន៍មកកាន់ {name}។ តើខ្ញុំអាចជួយអ្វីបានខ្លះនៅថ្ងៃនេះ?",
    "ko": "안녕하세요, {name}에 오신 것을 환영합니다. 오늘 무엇을 도와드릴까요?",
    "mn": "Сайн байна уу, {name}-д тавтай морилно уу. Өнөөдөр танд юугаар туслах вэ?",
    "ms": "Halo, selamat datang ke {name}. Bagaimana saya boleh membantu anda hari ini?",
    "my": "မင်္ဂလာပါ {name} မှ ကြိုဆိုပါတယ်။ ဒီနေ့ ဘာကူညီပေးရမလဲခင်ဗျာ။",
    "ne": "नमस्ते, {name} मा स्वागत छ। आज म तपाईंलाई कसरी मद्दत गर्न सक्छु?",
    "nl": "Goedendag, welkom bij {name}. Hoe kan ik u vandaag helpen?",
    "pa": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ, {name} ਵਿੱਚ ਤੁਹਾਡਾ ਸਵਾਗਤ ਹੈ। ਅੱਜ ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    "pl": "Dzień dobry, witamy w {name}. W czym mogę dziś pomóc?",
    "pt": "Olá, seja bem-vindo à {name}. Como posso ajudar você hoje?",
    "ro": "Bună ziua, bine ați venit la {name}. Cu ce vă pot ajuta astăzi?",
    "ru": "Здравствуйте, добро пожаловать в {name}. Чем могу вам помочь?",
    "sv": "Hej, välkommen till {name}. Hur kan jag hjälpa dig idag?",
    "sw": "Habari, karibu {name}. Ninawezaje kukusaidia leo?",
    "ta": "வணக்கம், {name}-க்கு வரவேற்கிறோம். இன்று நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?",
    "th": "สวัสดีครับ ยินดีต้อนรับสู่ {name} วันนี้มีอะไรให้ช่วยไหมครับ",
    "tl": "Kumusta, maligayang pagdating sa {name}. Paano kita matutulungan ngayon?",
    "tr": "Merhaba, {name}'e hoş geldiniz. Bugün size nasıl yardımcı olabilirim?",
    "uk": "Доброго дня, вітаємо у {name}. Чим можу вам допомогти?",
    "ur": "السلام علیکم، {name} میں خوش آمدید۔ آج میں آپ کی کیا مدد کر سکتا ہوں؟",
    "vi": "Xin chào, chào mừng đến với {name}. Tôi có thể giúp gì cho bạn hôm nay?",
    "zh": "您好，欢迎致电{name}。请问今天有什么可以帮您？",
}


def voice_greeting(locale, business_name):
    language = resolve_locale(locale).split("-", 1)[0]
    template = _VOICE_GREETINGS.get(language, _VOICE_GREETINGS["en"])
    return template.format(name=business_name.strip())


def voice_natural_greeting(locale: str, business_name: str) -> str:
    lang = resolve_locale(locale).split("-", 1)[0]
    template = _VOICE_NATURAL_GREETINGS.get(lang) or _VOICE_NATURAL_GREETINGS.get(resolve_locale(locale), _VOICE_NATURAL_GREETINGS["en"])
    return template.format(name=business_name.strip())