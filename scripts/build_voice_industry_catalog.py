# -*- coding: utf-8 -*-
"""
Full Generator for Voice Industry I18n Catalogs across 44 Canonical Locales.
Outputs:
  - web/src/lib/i18n/voice-industry-catalogs.generated.json
  - web/src/lib/i18n/voice-industry-copy.ts
"""

import json
import os
import re

CANONICAL_LOCALES = [
    "fr", "en", "es", "pt", "ro", "ar", "ar-EG", "zh", "ja", "ko",
    "de", "it", "nl", "pl", "ru", "uk", "el", "sv", "tr", "cs",
    "he", "fa", "sw", "am", "af", "ha", "hi", "bn", "ur", "ta",
    "pa", "ne", "vi", "th", "id", "ms", "tl", "my", "km", "mn",
    "ka", "hy", "fr-FR", "en-GB"
]

CATALOG_TS_PATH = "web/src/components/voice/voice-industry-catalog.ts"
with open(CATALOG_TS_PATH, encoding="utf-8") as f:
    catalog_text = f.read()

pattern = re.compile(
    r'id:\s*"([^"]+)",\s*nameFr:\s*"([^"]+)",\s*nameEn:\s*"([^"]+)",\s*category:\s*"([^"]+)",\s*icon:\s*"([^"]+)",\s*descFr:\s*"([^"]+)",\s*descEn:\s*"([^"]+)",.*?suggestedCapabilitiesFr:\s*\[(.*?)\]\s*,\s*suggestedCapabilitiesEn:\s*\[(.*?)\]',
    re.DOTALL
)

matches = pattern.findall(catalog_text)
assert len(matches) == 30, f"Expected 30 industries, found {len(matches)}"

raw_industries = []
for m in matches:
    ind_id, nameFr, nameEn, cat, icon, descFr, descEn, capsFr_raw, capsEn_raw = m
    capsFr = [c.strip().strip('"').rstrip('"').strip() for c in capsFr_raw.split('",') if c.strip()]
    capsEn = [c.strip().strip('"').rstrip('"').strip() for c in capsEn_raw.split('",') if c.strip()]
    raw_industries.append({
        "id": ind_id,
        "nameFr": nameFr,
        "nameEn": nameEn,
        "category": cat,
        "icon": icon,
        "descFr": descFr,
        "descEn": descEn,
        "capsFr": capsFr,
        "capsEn": capsEn,
    })

# Multilingual category labels
CATEGORIES = {
    "all": {
        "fr": "Tous les secteurs", "en": "All sectors", "es": "Todos los sectores",
        "pt": "Todos os setores", "de": "Alle Branchen", "it": "Tutti i settori",
        "nl": "Alle sectoren", "pl": "Wszystkie branże", "ro": "Toate sectoarele",
        "ru": "Все отрасли", "uk": "Усі галузі", "el": "Όλοι οι τομείς",
        "sv": "Alla branscher", "tr": "Tüm sektörler", "cs": "Všechna odvětví",
        "ar": "جميع القطاعات", "he": "כל המגזרים", "fa": "همه بخش‌ها",
        "zh": "所有行业", "ja": "すべての業種", "ko": "모든 업종",
        "vi": "Tất cả các ngành", "th": "ทุกภาคธุรกิจ", "id": "Semua sektor",
        "ms": "Semua sektor", "tl": "Lahat ng sektor", "hi": "सभी क्षेत्र",
        "bn": "সকল খাত", "ur": "تمام شعبہ جات", "ta": "அனைத்து துறைகளும்",
        "pa": "ਸਾਰੇ ਖੇਤਰ", "ne": "सबै क्षेत्रहरू", "sw": "Sekta zote",
        "am": "ሁሉም ዘርፎች", "af": "Alle bedrywe", "ha": "Dukkan Bangarori",
        "my": "ကဏ္ဍအားလုံး", "km": "វិស័យទាំងអស់", "mn": "Бүх салбар",
        "ka": "ყველა სექტორი", "hy": "Բոլոր ոլորտները"
    },
    "commerce": {
        "fr": "Commerce & Vente", "en": "Retail & Commerce", "es": "Comercio y Ventas",
        "pt": "Comércio e Varejo", "de": "Handel & Verkauf", "it": "Commercio e Vendite",
        "nl": "Detailhandel & Verkoop", "pl": "Handel i Sprzedaż", "ro": "Comerț și Vânzări",
        "ru": "Торговля и продажи", "uk": "Торгівля та продажі", "el": "Εμπόριο & Πωλήσεις",
        "sv": "Handel & Försäljning", "tr": "Perakende ve Ticaret", "cs": "Obchod a Prodej",
        "ar": "التجارة والمبيعات", "he": "מסחר ומכירות", "fa": "تجارت و فروش",
        "zh": "零售与商业", "ja": "小売・販売", "ko": "유통 및 판매",
        "vi": "Bán lẻ & Thương mại", "th": "ค้าปลีกและการค้า", "id": "Ritel & Penjualan",
        "ms": "Runcit & Jualan", "tl": "Tingi at Benta", "hi": "खुदरा और बिक्री",
        "bn": "খুচরা ও বাণিজ্য", "ur": "خوردہ اور فروخت", "ta": "சில்லறை மற்றும் வணிகம்",
        "pa": "ਖੁਦਰਾ ਅਤੇ ਵਿਕਰੀ", "ne": "खुदरा र बिक्री", "sw": "Biashara na Mauzo",
        "am": "ችርቻሮ እና ንግድ", "af": "Kleinhandel en Verkope", "ha": "Kasuwanci da Sayarwa",
        "my": "လက်လီနှင့် အရောင်း", "km": "ការលក់រាយ និងពាណិជ្ជកម្ម", "mn": "Худалдаа ба борлуулалт",
        "ka": "ვაჭრობა და გაყიდვები", "hy": "Առևտուր և վաճառք"
    },
    "health": {
        "fr": "Santé & Soins", "en": "Healthcare & Wellness", "es": "Salud y Bienestar",
        "pt": "Saúde e Bem-estar", "de": "Gesundheit & Pflege", "it": "Salute e Benessere",
        "nl": "Gezondheid & Zorg", "pl": "Zdrowie i Uroda", "ro": "Sănătate și Îngrijire",
        "ru": "Здравоохранение и уход", "uk": "Охорона здоров'я та догляд", "el": "Υγεία & Φροντίδα",
        "sv": "Hälsa & Vård", "tr": "Sağlık ve Bakım", "cs": "Zdraví a Péče",
        "ar": "الصحة والرعاية", "he": "בריאות ורווחה", "fa": "بهداشت و درمان",
        "zh": "医疗与健康", "ja": "医療・ヘルスケア", "ko": "의료 및 헬스케어",
        "vi": "Y tế & Chăm sóc sức khỏe", "th": "สุขภาพและความงาม", "id": "Kesehatan & Kebugaran",
        "ms": "Kesihatan & Penjagaan", "tl": "Kalusugan at Kagalingan", "hi": "स्वास्थ्य और देखभाल",
        "bn": "স্বাস্থ্য ও সুস্থতা", "ur": "صحت اور دیکھ بھال", "ta": "சுகாதாரம் மற்றும் நல்வாழ்வு",
        "pa": "ਸਿਹਤ ਅਤੇ ਸੰਭਾਲ", "ne": "स्वास्थ्य र हेरचाह", "sw": "Afya na Huduma",
        "am": "ጤና እና ክብካቤ", "af": "Gesondheid en Welstand", "ha": "Kiwon Lafiya da Kulawa",
        "my": "ကျန်းမာရေးနှင့် စောင့်ရှောက်မှု", "km": "សុខាភិបាល និងសុខុមាលភាព", "mn": "Эрүүл мэнд ба асаргаа",
        "ka": "ჯანდაცვა და მოვლა", "hy": "Առողջապահություն և խնամք"
    },
    "hospitality": {
        "fr": "Hôtellerie & Restauration", "en": "Hospitality & Dining", "es": "Hostelería y Restauración",
        "pt": "Hotelaria e Restauração", "de": "Hotellerie & Gastronomie", "it": "Ospitalità e Ristorazione",
        "nl": "Horeca & Gastvrijheid", "pl": "Hotelarstwo i Gastronomia", "ro": "Ospitalitate și Restaurante",
        "ru": "Гостиницы и рестораны", "uk": "Готелі та ресторани", "el": "Φιλοξενία & Εστίαση",
        "sv": "Hotell & Restaurang", "tr": "Konaklama ve Yeme-İçme", "cs": "Pohostinství a Gastronomie",
        "ar": "الفندقة والمطاعم", "he": "אירוח והסעדה", "fa": "هتلداری و پذیرایی",
        "zh": "酒店与餐饮", "ja": "ホテル・飲食", "ko": "호텔 및 외식",
        "vi": "Khách sạn & Nhà hàng", "th": "การบริการและร้านอาหาร", "id": "Perhotelan & Kuliner",
        "ms": "Hospitaliti & Jamuan", "tl": "Akomodasyon at Kainan", "hi": "आतिथ्य और भोजन",
        "bn": "আতিথেয়তা ও রেস্তোরাঁ", "ur": "مہمان نوازی اور کھانا پینا", "ta": "விருந்தோம்பல் மற்றும் உணவகம்",
        "pa": "ਪਰਾਹੁਣਚਾਰੀ ਅਤੇ ਭੋਜਨ", "ne": "आतिथ्य र भोजन", "sw": "Ukarimu na Migahawa",
        "am": "መስተንግዶ እና ምግብ ቤቶች", "af": "Gasvryheid en Eetplekke", "ha": "Karbar Baki da Abinci",
        "my": "ဟိုတယ်နှင့် စားသောက်ကုန်", "km": "បដិសណ្ឋារកិច្ច និងអាហារដ្ឋាន", "mn": "Зочлох үйлчилгээ ба зоог",
        "ka": "სასტუმრო და კვება", "hy": "Հյուրընկալություն և ռեստորաններ"
    },
    "transport": {
        "fr": "Transport & Logistique", "en": "Transport & Logistics", "es": "Transporte y Logística",
        "pt": "Transporte e Logística", "de": "Transport & Logistik", "it": "Trasporti e Logistica",
        "nl": "Transport & Logistiek", "pl": "Transport i Logistyka", "ro": "Transport și Logistică",
        "ru": "Транспорт и логистика", "uk": "Транспорт і логістика", "el": "Μεταφορές & Logistics",
        "sv": "Transport & Logistik", "tr": "Taşımacılık ve Lojistik", "cs": "Doprava a Logistika",
        "ar": "النقل واللوجستيات", "he": "תחבורה ולוגיסטיקה", "fa": "حمل‌ونقل و لجستیک",
        "zh": "交通与物流", "ja": "運輸・ロジスティクス", "ko": "교통 및 물류",
        "vi": "Vận tải & Logistics", "th": "การขนส่งและโลจิสติกส์", "id": "Transportasi & Logistik",
        "ms": "Pengangkutan & Logistik", "tl": "Transportasyon at Logistika", "hi": "परिवहन और रसद",
        "bn": "পরিবহন ও লজিস্টিকস", "ur": "نقل و حمل اور رسد", "ta": "போக்குவரத்து மற்றும் தளவாடங்கள்",
        "pa": "ਆਵਾਜਾਈ ਅਤੇ ਲੌਜਿਸਟਿਕਸ", "ne": "यातायात र रसद", "sw": "Usafiri na Usafirishaji",
        "am": "ትራንስፖርት እና ሎጂስቲክስ", "af": "Vervoer en Logistiek", "ha": "Sufuri da Kayan Aiki",
        "my": "သယ်ယူပို့ဆောင်ရေးနှင့် ထောက်ပံ့ပို့ဆောင်ရေး", "km": "ការដឹកជញ្ជូន និងភស្តុភារកម្ម", "mn": "Тээвэр ба логистик",
        "ka": "ტრანსპორტი და ლოგისტიკა", "hy": "Տրանսպորտ և լոգիստիկա"
    },
    "property": {
        "fr": "Immobilier & Travaux", "en": "Real Estate & Construction", "es": "Inmobiliaria y Reformas",
        "pt": "Imobiliário e Obras", "de": "Immobilien & Handwerk", "it": "Immobiliare e Edilizia",
        "nl": "Vastgoed & Bouw", "pl": "Nieruchomości i Budownictwo", "ro": "Imobiliare și Construcții",
        "ru": "Недвижимость и ремонт", "uk": "Нерухомість і ремонт", "el": "Ακίνητα & Κατασκευές",
        "sv": "Fastigheter & Bygg", "tr": "Gayrimenkul ve İnşaat", "cs": "Reality a Stavby",
        "ar": "العقارات والإنشاءات", "he": "נדל\"ן ובינוי", "fa": "املاک و ساخت‌وساز",
        "zh": "房地产与建筑工程", "ja": "不動産・建設", "ko": "부동산 및 건설",
        "vi": "Bất động sản & Xây dựng", "th": "อสังหาริมทรัพย์และการก่อสร้าง", "id": "Properti & Konstruksi",
        "ms": "Hartanah & Pembinaan", "tl": "Real Estate at Konstruksyon", "hi": "रियल एस्टेट और निर्माण",
        "bn": "রিয়েল এস্টেট ও নির্মাণ", "ur": "رئیل اسٹیٹ اور تعمیرات", "ta": "ரியல் எஸ்டேட் மற்றும் கட்டுமானம்",
        "pa": "ਰੀਅਲ ਅਸਟੇਟ ਅਤੇ ਉਸਾਰੀ", "ne": "घरजग्गा र निर्माण", "sw": "Majengo na Ujenzi",
        "am": "ሪል እስቴት እና ግንባታ", "af": "Eiendom en Konstruksie", "ha": "Gidaje da Gine-gine",
        "my": "အိမ်ခြံမြေနှင့် ဆောက်လုပ်ရေး", "km": "អចលនទ្រព្យ និងសំណង់", "mn": "Үл хөдлөх хөрөнгө ба барилга",
        "ka": "უძრავი ქონება და მშენებლობა", "hy": "Անշարժ գույք և շինարարություն"
    },
    "finance_legal": {
        "fr": "Finance & Juridique", "en": "Finance & Legal", "es": "Finanzas y Legal",
        "pt": "Finanças e Jurídico", "de": "Finanzen & Recht", "it": "Finanza e Legale",
        "nl": "Financiën & Juridisch", "pl": "Finanse i Prawo", "ro": "Finanțe și Juridic",
        "ru": "Финансы и юриспруденция", "uk": "Фінанси та право", "el": "Χρηματοοικονομικά & Νομικά",
        "sv": "Finans & Juridik", "tr": "Finans ve Hukuk", "cs": "Finance a Právo",
        "ar": "المالية والقانون", "he": "פיננסים ומשפטים", "fa": "مالی و حقوقی",
        "zh": "金融与法律", "ja": "金融・法務", "ko": "금융 및 법률",
        "vi": "Tài chính & Pháp lý", "th": "การเงินและกฎหมาย", "id": "Keuangan & Hukum",
        "ms": "Kewangan & Undang-undang", "tl": "Pananalapi at Legal", "hi": "वित्त और कानूनी",
        "bn": "অর্থ ও আইনি", "ur": "مالیات اور قانون", "ta": "நிதி மற்றும் சட்டம்",
        "pa": "ਵਿੱਤ ਅਤੇ ਕਾਨੂੰਨੀ", "ne": "वित्त र कानूनी", "sw": "Fedha na Sheria",
        "am": "ፋይናንስ እና ሕግ", "af": "Finansies en Regsake", "ha": "Kudi da Shari'a",
        "my": "ဘဏ္ဍာရေးနှင့် ဥပဒေ", "km": "ហិរញ្ញវត្ថុ និងច្បាប់", "mn": "Санхүү ба эрх зүй",
        "ka": "ფინანსები და იურიდიული", "hy": "Ֆինանսներ և իրավաբանություն"
    },
    "professional": {
        "fr": "Services & Entreprises", "en": "Professional Services", "es": "Servicios Profesionales",
        "pt": "Serviços Profissionais", "de": "Professionelle Dienstleistungen", "it": "Servizi Professionali",
        "nl": "Zakelijke Dienstverlening", "pl": "Usługi Profesjonalne", "ro": "Servicii Profesionale",
        "ru": "Профессиональные услуги", "uk": "Професійні послуги", "el": "Επαγγελματικές Υπηρεσίες",
        "sv": "Företagstjänster", "tr": "Profesyonel Hizmetler", "cs": "Profesionální Služby",
        "ar": "الخدمات المهنية", "he": "שירותים מקצועיים", "fa": "خدمات حرفه‌ای",
        "zh": "企业与专业服务", "ja": "プロフェッショナルサービス", "ko": "전문 비즈니스 서비스",
        "vi": "Dịch vụ chuyên nghiệp", "th": "บริการระดับมืออาชีพ", "id": "Layanan Profesional",
        "ms": "Perkhidmatan Profesional", "tl": "Propesyonal na Serbisyo", "hi": "व्यावसायिक सेवाएं",
        "bn": "পেশাদার পরিষেবা", "ur": "پیشہ ورانہ خدمات", "ta": "தொழில்முறை சேவைகள்",
        "pa": "ਪੇਸ਼ੇਵਰ ਸੇਵਾਵਾਂ", "ne": "व्यावसायिक सेवाहरू", "sw": "Huduma za Kitaalamu",
        "am": "የሙያ አገልግሎቶች", "af": "Professionele Dienste", "ha": "Ayyukan Kwarewa",
        "my": "ကျွမ်းကျင်မှုဆိုင်ရာ ဝန်ဆောင်မှုများ", "km": "សេវាកម្មវិជ្ជាជីវៈ", "mn": "Мэргэжлийн үйлчилгээ",
        "ka": "პროფესიული მომსახურება", "hy": "Մասնագիտական ծառայություններ"
    },
    "other": {
        "fr": "Autre secteur", "en": "Other Sector", "es": "Otro sector",
        "pt": "Outro setor", "de": "Anderer Bereich", "it": "Altro settore",
        "nl": "Andere sector", "pl": "Inna branża", "ro": "Alt sector",
        "ru": "Другая отрасль", "uk": "Інша галузь", "el": "Άλλος τομέας",
        "sv": "Annan bransch", "tr": "Diğer Sektör", "cs": "Jiné odvětví",
        "ar": "قطاع آخر", "he": "מגזר אחר", "fa": "بخش دیگر",
        "zh": "其他行业", "ja": "その他の業種", "ko": "기타 분야",
        "vi": "Ngành khác", "th": "ภาคธุรกิจอื่นๆ", "id": "Sektor lainnya",
        "ms": "Sektor lain", "tl": "Ibang sektor", "hi": "अन्य क्षेत्र",
        "bn": "অন্যান্য ক্ষেত্র", "ur": "دیگر شعبہ", "ta": "பிற துறை",
        "pa": "ਹੋਰ ਖੇਤਰ", "ne": "अन्य क्षेत्र", "sw": "Sekta nyingine",
        "am": "ሌላ ዘርፍ", "af": "Ander bedryf", "ha": "Wani bangare",
        "my": "အခြားကဏ္ဍ", "km": "វិស័យផ្សេងទៀត", "mn": "Бусад салбар",
        "ka": "სხვა სექტორი", "hy": "Այլ ոլորտ"
    }
}

# INDUSTRY_NAMES for all 30 industries
INDUSTRY_NAMES = {
    "auto": {
        "fr": "Automobile / Pièces", "en": "Automotive / Parts", "es": "Automoción / Repuestos",
        "pt": "Automotivo / Peças", "de": "Kfz / Autoteile", "it": "Automotive / Ricambi",
        "nl": "Automotive / Onderdelen", "pl": "Motoryzacja / Części", "ro": "Auto / Piese auto",
        "ru": "Автомобили / Запчасти", "uk": "Автомобілі / Запчастини", "el": "Αυτοκίνητα / Ανταλλακτικά",
        "sv": "Fordon / Reservdelar", "tr": "Otomotiv / Yedek Parça", "cs": "Automobilový průmysl / Díly",
        "ar": "السيارات / قطع الغيار", "he": "רכב וחלקי חילוף", "fa": "خودرو و قطعات یدکی",
        "zh": "汽车 / 汽配", "ja": "自動車・自動車部品", "ko": "자동차 / 부품",
        "vi": "Ô tô / Phụ tùng", "th": "ยานยนต์ / อะไหล่", "id": "Otomotif / Suku Cadang",
        "ms": "Automotif / Alat Ganti", "tl": "Sasakyan / Piyesa", "hi": "ऑटोमोबाइल / पुर्जे",
        "bn": "অটোমোবাইল / যন্ত্রাংশ", "ur": "آٹوموبائل / پرزہ جات", "ta": "ஆட்டோமொபைல் / உதிரிபாகங்கள்",
        "pa": "ਆਟੋਮੋਬਾਈਲ / ਪੁਰਜ਼ੇ", "ne": "अटोमोबाइल / पार्टपुर्जा", "sw": "Magari / Vipuri",
        "am": "አውቶሞቢል / መለዋወጫዎች", "af": "Motor / Onderdele", "ha": "Motoci / Sashe",
        "my": "မော်တော်ယာဉ်နှင့် အပိုပစ္စည်း", "km": "យានយន្ត និងគ្រឿងបន្លាស់", "mn": "Автомашин / Сэлбэг",
        "ka": "ავტომობილები / ნაწილები", "hy": "Ավտոմեքենաներ / Պահեստամասեր"
    },
    "medical": {
        "fr": "Médical / Cliniques", "en": "Medical / Clinics", "es": "Médico / Clínicas",
        "pt": "Médico / Clínicas", "de": "Medizin / Kliniken", "it": "Medico / Cliniche",
        "nl": "Medisch / Klinieken", "pl": "Medycyna / Kliniki", "ro": "Medical / Clinici",
        "ru": "Медицина / Клиники", "uk": "Медицина / Клініки", "el": "Ιατρική / Κλινικές",
        "sv": "Medicin / Kliniker", "tr": "Medikal / Klinikler", "cs": "Lékařství / Kliniky",
        "ar": "طبي / عيادات", "he": "רפואה ומרפאות", "fa": "پزشکی و کلینیک‌ها",
        "zh": "医疗 / 诊所", "ja": "医療・クリニック", "ko": "의료 / 클리닉",
        "vi": "Y tế / Phòng khám", "th": "การแพทย์ / คลินิก", "id": "Medis / Klinik",
        "ms": "Perubatan / Klinik", "tl": "Medikal / Klinika", "hi": "चिकित्सा / क्लीनिक",
        "bn": "চিকিৎসা / ক্লিনিক", "ur": "طبی / کلینک", "ta": "மருத்துவம் / கிளினிக்குகள்",
        "pa": "ਮੈਡੀਕਲ / ਕਲੀਨਿਕ", "ne": "चिकित्सा / क्लिनिक", "sw": "Matibabu / Kliniki",
        "am": "ሕክምና / ክሊኒኮች", "af": "Medies / Klinieke", "ha": "Lafiya / Asibitoci",
        "my": "ဆေးဘက်ဆိုင်ရာနှင့် ဆေးခန်းများ", "km": "វេជ្ជសាស្ត្រ និងគ្លីនិក", "mn": "Эмнэлэг / Клиник",
        "ka": "სამედიცინო / კლინიკები", "hy": "Բժշկական / Կլինիկաներ"
    },
    "restaurant": {
        "fr": "Restauration / Traiteur", "en": "Restaurant / Catering", "es": "Restauración / Catering",
        "pt": "Restauração / Buffet", "de": "Gastronomie / Catering", "it": "Ristorazione / Catering",
        "nl": "Horeca / Catering", "pl": "Gastronomia / Catering", "ro": "Restaurante / Catering",
        "ru": "Рестораны / Кейтеринг", "uk": "Ресторани / Кейтеринг", "el": "Εστίαση / Catering",
        "sv": "Restaurang / Catering", "tr": "Restoran / Catering", "cs": "Gastronomie / Catering",
        "ar": "مطاعم / تموين", "he": "מסעדות ואירוח", "fa": "رستوران و کیترینگ",
        "zh": "餐饮 / 外卖", "ja": "飲食・ケータリング", "ko": "외식 / 케이터링",
        "vi": "Nhà hàng / Ẩm thực", "th": "ร้านอาหาร / จัดเลี้ยง", "id": "Restoran / Katering",
        "ms": "Restoran / Katering", "tl": "Restaurant / Katering", "hi": "रेस्तरां / खानपान",
        "bn": "রেস্তোরাঁ / ক্যাটারিং", "ur": "ریستوران / کیٹرنگ", "ta": "உணவகம் / கேட்டரிங்",
        "pa": "ਰੈਸਟੋਰੈਂਟ / ਕੈਟਰਿੰਗ", "ne": "रेस्टुरेन्ट / क्याटरिङ", "sw": "Migahawa / Upishi",
        "am": "ምግብ ቤት / ዝግጅት", "af": "Restourant / Spyseniering", "ha": "Gidajen Abinci / Abinci",
        "my": "စားသောက်ဆိုင်နှင့် အစားအသောက်ဝန်ဆောင်မှု", "km": "ភោជនីយដ្ឋាន និងសេវាកម្មម្ហូបអាហារ", "mn": "Ресторан / Хоол үйлдвэрлэл",
        "ka": "რესტორნები / ქეითერინგი", "hy": "Ռեստորան / Քեյթրինգ"
    },
    "retail": {
        "fr": "Commerce / Retail", "en": "Retail & Commerce", "es": "Comercio / Retail",
        "pt": "Comércio / Varejo", "de": "Einzelhandel / Retail", "it": "Commercio / Retail",
        "nl": "Detailhandel / Retail", "pl": "Handel / Retail", "ro": "Comerț / Retail",
        "ru": "Торговля / Ритейл", "uk": "Торгівля / Ритейл", "el": "Εμπόριο / Λιανική",
        "sv": "Handel / Retail", "tr": "Perakende / Ticaret", "cs": "Obchod / Retail",
        "ar": "التجارة / التجزئة", "he": "מסחר וקמעונאות", "fa": "بازرگانی و خرده‌فروشی",
        "zh": "零售 / 商贸", "ja": "小売・コマース", "ko": "유통 / 소매",
        "vi": "Thương mại / Bán lẻ", "th": "ค้าปลีก / พาณิชย์", "id": "Ritel / Perdagangan",
        "ms": "Runcit / Perdagangan", "tl": "Tingi / Komersyo", "hi": "खुदरा / व्यापार",
        "bn": "খুচরা / বাণিজ্য", "ur": "ریٹیل / تجارت", "ta": "சில்லறை / வணிகம்",
        "pa": "ਰਿਟੇਲ / ਵਪਾਰ", "ne": "खुदरा / व्यापार", "sw": "Biashara / Rejareja",
        "am": "ችርቻሮ / ንግድ", "af": "Kleinhandel / Handel", "ha": "Kasuwanci / Retail",
        "my": "လက်လီနှင့် ကုန်သွယ်ရေး", "km": "ការលក់រាយ និងពាណិជ្ជកម្ម", "mn": "Худалдаа / Жижиглэн худалдаа",
        "ka": "ვაჭრობა / რითეილი", "hy": "Առևտուր / Մանրածախ"
    },
    "transport": {
        "fr": "Transport / Logistique", "en": "Transport / Logistics", "es": "Transporte / Logística",
        "pt": "Transporte / Logística", "de": "Transport / Logistik", "it": "Trasporti / Logistica",
        "nl": "Transport / Logistiek", "pl": "Transport / Logistyka", "ro": "Transport și Logistică",
        "ru": "Транспорт / Логистика", "uk": "Транспорт / Логістика", "el": "Μεταφορές / Logistics",
        "sv": "Transport / Logistik", "tr": "Taşımacılık / Lojistik", "cs": "Doprava / Logistika",
        "ar": "النقل / اللوجستيات", "he": "תחבורה ולוגיסטיקה", "fa": "حمل‌ونقل و لجستیک",
        "zh": "运输 / 物流", "ja": "運輸・物流", "ko": "운송 / 물류",
        "vi": "Vận tải / Logistics", "th": "ขนส่ง / โลจิสติกส์", "id": "Transportasi / Logistik",
        "ms": "Pengangkutan / Logistik", "tl": "Transportasyon / Logistika", "hi": "परिवहन / लॉजिस्टिक्स",
        "bn": "পরিবহন / লজিস্টিকস", "ur": "نقل و حمل / لاجسٹکس", "ta": "போக்குவரத்து / தளவாடங்கள்",
        "pa": "ਆਵਾਜਾਈ / ਲੌਜਿਸਟਿਕਸ", "ne": "यातायात / रसद", "sw": "Usafiri / Vifaa",
        "am": "ትራንስፖርት / ሎጂስቲክስ", "af": "Vervoer / Logistiek", "ha": "Sufuri / Kayan Aiki",
        "my": "သယ်ယူပို့ဆောင်ရေးနှင့် ထောက်ပံ့ပို့ဆောင်ရေး", "km": "ការដឹកជញ្ជូន និងភស្តុភារកម្ម", "mn": "Тээвэр / Логистик",
        "ka": "ტრანსპორტი / ლოგისტიკა", "hy": "Տրանսպորտ / Լոգիստիկա"
    },
    "realestate": {
        "fr": "Immobilier", "en": "Real Estate", "es": "Inmobiliaria",
        "pt": "Imobiliário", "de": "Immobilien", "it": "Immobiliare",
        "nl": "Vastgoed", "pl": "Nieruchomości", "ro": "Imobiliare",
        "ru": "Недвижимость", "uk": "Нерухомість", "el": "Ακίνητα",
        "sv": "Fastigheter", "tr": "Gayrimenkul", "cs": "Reality / Nemovitosti",
        "ar": "العقارات", "he": "נדל\"ן", "fa": "املاک و مستغلات",
        "zh": "房地产", "ja": "不動産", "ko": "부동산",
        "vi": "Bất động sản", "th": "อสังหาริมทรัพย์", "id": "Properti / Real Estat",
        "ms": "Hartanah", "tl": "Real Estate", "hi": "रियल एस्टेट",
        "bn": "রিয়েল এস্টেট", "ur": "رئیل اسٹیٹ", "ta": "ரியல் எஸ்டேட்",
        "pa": "ਰੀਅਲ ਅਸਟੇਟ", "ne": "घरजग्गा / रियल इस्टेट", "sw": "Majengo / Mali",
        "am": "ሪል እስቴት", "af": "Eiendom", "ha": "Gidaje / Filaye",
        "my": "အိမ်ခြံမြေ", "km": "អចលនទ្រព្យ", "mn": "Үл хөдлөх хөрөнгө",
        "ka": "უძრავი ქონება", "hy": "Անշարժ գույք"
    },
    "hotel": {
        "fr": "Hôtellerie / Tourisme", "en": "Hospitality / Tourism", "es": "Hostelería / Turismo",
        "pt": "Hotelaria / Turismo", "de": "Hotellerie / Tourismus", "it": "Ospitalità / Turismo",
        "nl": "Hotellerie / Toerisme", "pl": "Hotelarstwo / Turystyka", "ro": "Ospitalitate / Turism",
        "ru": "Гостиничный бизнес / Туризм", "uk": "Готельний бізнес / Туризм", "el": "Φιλοξενία / Τουρισμός",
        "sv": "Hotell / Turism", "tr": "Otelcilik / Turizm", "cs": "Pohostinství / Turismus",
        "ar": "الفندقة / السياحة", "he": "מלונאות ותיירות", "fa": "هتلداری و گردشگری",
        "zh": "酒店 / 旅游", "ja": "ホテル・観光", "ko": "호텔 / 관광",
        "vi": "Khách sạn / Du lịch", "th": "โรงแรม / การท่องเที่ยว", "id": "Perhotelan / Pariwisata",
        "ms": "Perhotelan / Pelancongan", "tl": "Hotel / Turismo", "hi": "आतिथ्य / पर्यटन",
        "bn": "আতিথেয়তা / পর্যটন", "ur": "مہمان نوازی / سیاحت", "ta": "விருந்தோம்பல் / சுற்றுலா",
        "pa": "ਪਰਾਹੁਣਚਾਰੀ / ਸੈਰ-ਸਪਾਟਾ", "ne": "आतिथ्य / पर्यटन", "sw": "Ukarimu / Utalii",
        "am": "መስተንግዶ / ቱሪዝም", "af": "Gasvryheid / Toerisme", "ha": "Karbar Baki / Yawon Bude Ido",
        "my": "ဟိုတယ်နှင့် ခရီးသွားလုပ်ငန်း", "km": "បដិសណ្ឋារកិច្ច និងទេសចរណ៍", "mn": "Зочлох үйлчилгээ / Аялал жуулчлал",
        "ka": "სასტუმრო / ტურიზმი", "hy": "Հյուրանոցային / Զբոսաշրջություն"
    },
    "beauty": {
        "fr": "Beauté / Bien-être", "en": "Beauty / Wellness", "es": "Belleza / Bienestar",
        "pt": "Beleza / Bem-estar", "de": "Schönheit / Wellness", "it": "Bellezza / Benessere",
        "nl": "Schoonheid / Wellness", "pl": "Uroda / Wellness", "ro": "Frumusețe / Wellness",
        "ru": "Красота / Велнес", "uk": "Краса / Велнес", "el": "Ομορφιά / Ευεξία",
        "sv": "Skönhet / Wellness", "tr": "Güzellik / Sağlıklı Yaşam", "cs": "Krása / Wellness",
        "ar": "التجميل / العافية", "he": "יופי וטיפוח", "fa": "زیبایی و سلامت",
        "zh": "美容 / 健康", "ja": "美容・ウェルネス", "ko": "뷰티 / 웰빙",
        "vi": "Làm đẹp / Chăm sóc sức khỏe", "th": "ความงาม / สุขภาพ", "id": "Kecantikan / Kebugaran",
        "ms": "Kecantikan / Kesihatan", "tl": "Kagandahan / Kalusugan", "hi": "सौंदर्य / वेलनेस",
        "bn": "সৌন্দর্য / সুস্থতা", "ur": "خوبصورتی / تندرستی", "ta": "அழகு / நல்வாழ்வு",
        "pa": "ਸੁੰਦਰਤਾ / ਤੰਦਰੁਸਤੀ", "ne": "सौन्दर्य / कल्याण", "sw": "Urembo / Ustawi",
        "am": "ውበት / ጤና", "af": "Skoonheid / Welstand", "ha": "Kyau / Lafiya",
        "my": "အလှအပနှင့် ကျန်းမာရေး", "km": "ភាពស្រស់ស្អាត និងសុខុមាលភាព", "mn": "Гоо сайхан / Эрүүл мэнд",
        "ka": "სილამაზე / ველნესი", "hy": "Գեղեցկություն / Առողջություն"
    },
    "construction": {
        "fr": "Construction / Entrepreneurs", "en": "Construction / Contractors", "es": "Construcción / Contratistas",
        "pt": "Construção / Empreiteiros", "de": "Bauwesen / Handwerk", "it": "Edilizia / Costruzioni",
        "nl": "Bouw / Aannemers", "pl": "Budownictwo / Wykonawcy", "ro": "Construcții / Antreprenori",
        "ru": "Строительство / Подрядчики", "uk": "Будівництво / Підрядники", "el": "Κατασκευές / Εργολάβοι",
        "sv": "Bygg / Entreprenad", "tr": "İnşaat / Müteahhitlik", "cs": "Stavebnictví / Řemesla",
        "ar": "البناء / المقاولات", "he": "בנייה וקבלנות", "fa": "ساخت‌وساز و پیمانکاری",
        "zh": "建筑 / 承包商", "ja": "建設・請負", "ko": "건설 / 시공",
        "vi": "Xây dựng / Nhà thầu", "th": "ก่อสร้าง / ผู้รับเหมา", "id": "Konstruksi / Kontraktor",
        "ms": "Pembinaan / Kontraktor", "tl": "Konstruksyon / Kontratista", "hi": "निर्माण / ठेकेदार",
        "bn": "নির্মাণ / ঠিকাদার", "ur": "تعمیرات / ٹھیکیدار", "ta": "கட்டுமானம் / ஒப்பந்ததாரர்கள்",
        "pa": "ਉਸਾਰੀ / ਠੇਕੇਦਾਰ", "ne": "निर्माण / ठेकेदारहरू", "sw": "Ujenzi / Wakandarasi",
        "am": "ግንባታ / ተቋራጮች", "af": "Konstruksie / Kontrakteurs", "ha": "Gine-gine / 'Yan Kwangila",
        "my": "ဆောက်လုပ်ရေးနှင့် ကန်ထရိုက်တာများ", "km": "សំណង់ និងអ្នកម៉ៅការ", "mn": "Барилга / Гүйцэтгэгчид",
        "ka": "მშენებლობა / კონტრაქტორები", "hy": "Շինարարություն / Կապալառուներ"
    },
    "legal": {
        "fr": "Avocats / Notaires", "en": "Legal / Notaries", "es": "Abogados / Notarios",
        "pt": "Advogados / Notários", "de": "Rechtsanwälte / Notare", "it": "Avvocati / Notai",
        "nl": "Advocaten / Notarissen", "pl": "Prawnicy / Notariusze", "ro": "Avocați / Notari",
        "ru": "Юристы / Нотариусы", "uk": "Юристи / Нотаріуси", "el": "Δικηγόροι / Συμβολαιογράφοι",
        "sv": "Juridik / Notarier", "tr": "Hukuk / Noterler", "cs": "Právníci / Notáři",
        "ar": "المحاماة / التوثيق", "he": "עורכי דין ונוטריונים", "fa": "وکالت و دفاتر اسناد",
        "zh": "法律 / 公证", "ja": "法律・公証", "ko": "법률 / 공증",
        "vi": "Luật sư / Công chứng", "th": "กฎหมาย / โนตารี", "id": "Hukum / Notaris",
        "ms": "Peguam / Notari", "tl": "Batas / Notaryo", "hi": "वकील / नोटरी",
        "bn": "আইনজীবী / নোটারি", "ur": "وکلاء / نوٹری", "ta": "வழக்கறிஞர்கள் / நோட்டரிகள்",
        "pa": "ਵਕੀਲ / ਨੋਟਰੀ", "ne": "कानूनी / नोटरी", "sw": "Wanasheria / Notari",
        "am": "ጠበቆች / ኖተሪዎች", "af": "Regsadvokate / Notarisse", "ha": "Lauyoyi / Notaries",
        "my": "ရှေ့နေများနှင့် နိုတြီများ", "km": "មេធាវី និងសារការី", "mn": "Хуульчид / Нотариат",
        "ka": "ადვოკატები / ნოტარიუსები", "hy": "Փաստաբաններ / Նոտարներ"
    },
    "finance": {
        "fr": "Finance / Comptabilité", "en": "Finance / Accounting", "es": "Finanzas / Contabilidad",
        "pt": "Finanças / Contabilidade", "de": "Finanzen / Buchhaltung", "it": "Finanza / Contabilità",
        "nl": "Financiën / Boekhouding", "pl": "Finanse / Księgowość", "ro": "Finanțe / Contabilitate",
        "ru": "Финансы / Бухгалтерия", "uk": "Фінанси / Бухгалтерія", "el": "Χρηματοοικονομικά / Λογιστική",
        "sv": "Finans / Redovisning", "tr": "Finans / Muhasebe", "cs": "Finance / Účetnictví",
        "ar": "المالية / المحاسبة", "he": "פיננסים וראיית חשבון", "fa": "مالی و حسابداری",
        "zh": "金融 / 会计", "ja": "金融・会計", "ko": "금융 / 회계",
        "vi": "Tài chính / Kế toán", "th": "การเงิน / บัญชี", "id": "Keuangan / Akuntansi",
        "ms": "Kewangan / Perakaunan", "tl": "Pananalapi / Pagtutuos", "hi": "वित्त / लेखा",
        "bn": "অর্থ / হিসাববিজ্ঞান", "ur": "مالیات / اکاؤنٹنگ", "ta": "நிதி / கணக்கியல்",
        "pa": "ਵਿੱਤ / ਲੇਖਾ", "ne": "वित्त / लेखा", "sw": "Fedha / Uhasibu",
        "am": "ፋይናንስ / ሂሳብ አያያዝ", "af": "Finansies / Rekeningkunde", "ha": "Kudi / Lissafi",
        "my": "ဘဏ္ဍာရေးနှင့် စာရင်းကိုင်", "km": "ហិរញ្ញវត្ថុ និងគណនេយ្យ", "mn": "Санхүү / Нягтлан бодох бүртгэл",
        "ka": "ფინანსები / ბუღალტერია", "hy": "Ֆինանսներ / Հաշվապահություն"
    },
    "insurance": {
        "fr": "Assurances / Sinistres", "en": "Insurance / Claims", "es": "Seguros / Siniestros",
        "pt": "Seguros / Sinistros", "de": "Versicherungen / Schadenregulierung", "it": "Assicurazioni / Sinistri",
        "nl": "Verzekeringen / Schade", "pl": "Ubezpieczenia / Szkody", "ro": "Asigurări / Daune",
        "ru": "Страхование / Убытки", "uk": "Страхування / Збитки", "el": "Ασφάλειες / Αποζημιώσεις",
        "sv": "Försäkring / Skador", "tr": "Sigorta / Hasar", "cs": "Pojištění / Pojistné události",
        "ar": "التأمين / المطالبات", "he": "ביטוח ותביעות", "fa": "بیمه و خسارات",
        "zh": "保险 / 理赔", "ja": "保険・事故対応", "ko": "보험 / 보상",
        "vi": "Bảo hiểm / Khiếu nại", "th": "ประกันภัย / เคลม", "id": "Asuransi / Klaim",
        "ms": "Insurans / Tuntutan", "tl": "Seguro / Claim", "hi": "बीमा / दावे",
        "bn": "বীমা / দাবি", "ur": "انشورنس / دعوے", "ta": "காப்பீடு / உரிமைகோரல்கள்",
        "pa": "ਬੀਮਾ / ਦਾਅਵੇ", "ne": "बीमा / दाबी", "sw": "Bima / Madai",
        "am": "ኢንሹራንስ / የካሳ ጥያቄዎች", "af": "Versekerings / Eise", "ha": "Inshora / Da'awa",
        "my": "အာမခံနှင့် လျော်ကြေးတောင်းခံမှု", "km": "ធានារ៉ាប់រង និងការទាមទារ", "mn": "Даатгал / Нөхөн төлбөр",
        "ka": "დაზღვევა / ზარალის ანაზღაურება", "hy": "Ապահովագրություն / Հատուցումներ"
    },
    "education": {
        "fr": "Éducation / Formations", "en": "Education / Training", "es": "Educación / Formación",
        "pt": "Educação / Formação", "de": "Bildung / Weiterbildung", "it": "Istruzione / Formazione",
        "nl": "Onderwijs / Opleiding", "pl": "Edukacja / Szkolenia", "ro": "Educație / Training",
        "ru": "Образование / Курсы", "uk": "Освіта / Курси", "el": "Εκπαίδευση / Σεμινάρια",
        "sv": "Utbildning / Kurser", "tr": "Eğitim / Kurslar", "cs": "Vzdělávání / Školení",
        "ar": "التعليم / التدريب", "he": "חינוך והדרכה", "fa": "آموزش و یادگیری",
        "zh": "教育 / 培训", "ja": "教育・研修", "ko": "교육 / 훈련",
        "vi": "Giáo dục / Đào tạo", "th": "การศึกษา / อบรม", "id": "Pendidikan / Pelatihan",
        "ms": "Pendidikan / Latihan", "tl": "Edukasyon / Pagsasanay", "hi": "शिक्षा / प्रशिक्षण",
        "bn": "শিক্ষা / প্রশিক্ষণ", "ur": "تعلیم / تربیت", "ta": "கல்வி / பயிற்சி",
        "pa": "ਸਿੱਖਿਆ / ਸਿਖਲਾਈ", "ne": "शिक्षा / तालिम", "sw": "Elimu / Mafunzo",
        "am": "ትምህርት / ስልጠና", "af": "Onderwys / Opleiding", "ha": "Ilimi / Horarwa",
        "my": "ပညာရေးနှင့် သင်တန်းများ", "km": "ការអប់រំ និងការបណ្តុះបណ្តាល", "mn": "Боловсрол / Сургалт",
        "ka": "განათლება / ტრენინგი", "hy": "Կրթություն / Վերապատրաստում"
    },
    "plumbing": {
        "fr": "Plomberie / Chauffage / CVC", "en": "Plumbing / HVAC", "es": "Fontanería / Climatización",
        "pt": "Canalização / Climatização", "de": "Sanitär / Heizung / Klima", "it": "Idraulica / Termoidraulica",
        "nl": "Loodgieters / HVAC", "pl": "Hydraulika / HVAC", "ro": "Instalații / HVAC",
        "ru": "Сантехника / Отопление", "uk": "Сантехніка / Опалення", "el": "Υδραυλικά / Ψύξη-Θέρμανση",
        "sv": "VVS / Kylteknik", "tr": "Sıhhi Tesisat / İklimlendirme", "cs": "Instalatérství / HVAC",
        "ar": "السباكة / التدفئة والتكييف", "he": "אינסטלציה ומיזוג אוויר", "fa": "لوله‌کشی و تهویه مطبوع",
        "zh": "暖通管道 / 卫浴维修", "ja": "配管・空調設備", "ko": "배관 / 냉난방 공조",
        "vi": "Điện nước / Điện lạnh", "th": "ประปา / ปรับอากาศ", "id": "Pipa & Tata Udara",
        "ms": "Paip & Pengudaraan", "tl": "Tubero / HVAC", "hi": "प्लंबिंग / एचवीएसी",
        "bn": "প্লাম্বিং / এসি মেরামত", "ur": "پلمبنگ / ایئر کنڈیشننگ", "ta": "குழாய் பதித்தல் / ஏசி",
        "pa": "ਪਲੰਬਿੰਗ / ਏਸੀ", "ne": "प्लम्बिङ / एचभीएसी", "sw": "Mabomba / Kiyoyozi",
        "am": "የውሃ መስመር / ማቀዝቀዣ", "af": "Loodgieters / HVAC", "ha": "Aikin Famfo / AC",
        "my": "ပိုက်လိုင်းနှင့် လေအေးပေးစက်", "km": "ប្រព័ន្ធទឹក និងម៉ាស៊ីនត្រជាក់", "mn": "Сантехник / Агааржуулалт",
        "ka": "სანტექნიკა / გათბობა-კონდიცირება", "hy": "Սանտեխնիկա / Ջեռուցում և օդափոխություն"
    },
    "electrician": {
        "fr": "Électricité / Sécurité", "en": "Electrical / Security", "es": "Electricidad / Seguridad",
        "pt": "Eletricidade / Segurança", "de": "Elektrik / Sicherheitstechnik", "it": "Elettricità / Sicurezza",
        "nl": "Elektrotechniek / Beveiliging", "pl": "Elektryka / Bezpieczeństwo", "ro": "Electricitate / Securitate",
        "ru": "Электрика / Безопасность", "uk": "Електрика / Безпека", "el": "Ηλεκτρολογικά / Ασφάλεια",
        "sv": "Elinstallation / Säkerhet", "tr": "Elektrik / Güvenlik", "cs": "Elektroinstalace / Bezpečnost",
        "ar": "الكهرباء / أنظمة الأمان", "he": "חשמל ומערכות אבטחה", "fa": "برق و سیستم‌های امنیتی",
        "zh": "电气 / 安防监控", "ja": "電気・セキュリティ", "ko": "전기 / 보안 설비",
        "vi": "Điện / Hệ thống an ninh", "th": "ระบบไฟฟ้า / ความปลอดภัย", "id": "Kelistrikan / Keamanan",
        "ms": "Elektrik / Keselamatan", "tl": "Kuryente / Seguridad", "hi": "विद्युत / सुरक्षा",
        "bn": "বৈদ্যুতিক / নিরাপত্তা", "ur": "بجلی / سیکیورٹی", "ta": "மின்சாரம் / பாதுகாப்பு",
        "pa": "ਬਿਜਲੀ / ਸੁਰੱਖਿਆ", "ne": "बिजुली / सुरक्षा", "sw": "Umeme / Usalama",
        "am": "ኤሌክትሪክ / ደህንነት", "af": "Elektrisiteit / Sekuriteit", "ha": "Wutar Lantarki / Tsaro",
        "my": "လျှပ်စစ်နှင့် လုံခြုံရေး", "km": "អគ្គិសនី និងប្រព័ន្ធសុវត្ថិភាព", "mn": "Цахилгаан / Аюулгүй байдал",
        "ka": "ელექტროობა / უსაფრთხოება", "hy": "Էլեկտրականություն / Անվտանգություն"
    },
    "dental": {
        "fr": "Dentaire / Orthodontie", "en": "Dental / Orthodontics", "es": "Odontología / Ortodoncia",
        "pt": "Medicina Dentária / Ortodontia", "de": "Zahnmedizin / Kieferorthopädie", "it": "Odontoiatria / Ortodonzia",
        "nl": "Tandheelkunde / Orthodontie", "pl": "Stomatologia / Ortodoncja", "ro": "Stomatologie / Ortodonție",
        "ru": "Стоматология / Ортодонтия", "uk": "Стоматологія / Ортодонтія", "el": "Οδοντιατρική / Ορθοδοντική",
        "sv": "Tandvård / Ortodonti", "tr": "Diş Hekimliği / Ortodonti", "cs": "Stomatologie / Ortodoncie",
        "ar": "طب الأسنان / تقويم الأسنان", "he": "רפואת שיניים ואורתודונטיה", "fa": "دندانپزشکی و ارتودنسی",
        "zh": "齿科 / 口腔正畸", "ja": "歯科・矯正歯科", "ko": "치과 / 치아 교정",
        "vi": "Nha khoa / Chỉnh nha", "th": "ทันตกรรม / จัดฟัน", "id": "Kedokteran Gigi / Ortodonti",
        "ms": "Pergigian / Ortodontik", "tl": "Ngipin / Orthodontics", "hi": "दंत चिकित्सा / ऑर्थोडॉन्टिक्स",
        "bn": "দন্ত চিকিৎসা / অর্থোডন্টিক্স", "ur": "دندان سازی / آرتھوڈانٹکس", "ta": "பல் மருத்துவம் / ஆர்த்தோடான்டிக்ஸ்",
        "pa": "ਦੰਦਾਂ ਦੀ ਦੇਖਭਾਲ / ਆਰਥੋਡੌਂਟਿਕਸ", "ne": "दन्त चिकित्सा / अर्थोडोन्टिक्स", "sw": "Meno / Matibabu ya Meno",
        "am": "ጥርስ ሕክምና / ጥርስ ማስተካከል", "af": "Tandheelkunde / Ortodonsie", "ha": "Kiwon Hakora / Orthodontics",
        "my": "သွားနှင့်ခံတွင်း ဆေးကုသမှု", "km": "ទន្តសាស្ត្រ និងតម្រង់ធ្មេញ", "mn": "Шүдний эмнэлэг / Гажиг засал",
        "ka": "სტომატოლოგია / ორთოდონტია", "hy": "Ատամնաբուժություն / Օրթոդոնտիա"
    },
    "veterinary": {
        "fr": "Vétérinaire / Soins animaux", "en": "Veterinary / Pet Care", "es": "Veterinaria / Cuidado de mascotas",
        "pt": "Veterinária / Animais de estimação", "de": "Veterinärmedizin / Tierpflege", "it": "Veterinaria / Animali domestici",
        "nl": "Diergeneeskunde / Huisdieren", "pl": "Weterynaria / Zwierzęta", "ro": "Veterinar / Îngrijire animale",
        "ru": "Ветеринария / Уход за животными", "uk": "Ветеринарія / Тварини", "el": "Κτηνιατρική / Φροντίδα κατοικιδίων",
        "sv": "Veterinär / Djurvård", "tr": "Veteriner / Evcil Hayvan", "cs": "Veterinární péče / Zvířata",
        "ar": "الطب البيطري / رعاية الحيوانات", "he": "וטרינריה וחיות מחמד", "fa": "دامپزشکی و حیوانات خانگی",
        "zh": "宠物医院 / 兽医诊所", "ja": "動物病院・ペットケア", "ko": "동물병원 / 반려동물",
        "vi": "Thú y / Chăm sóc thú cưng", "th": "สัตวแพทย์ / สัตว์เลี้ยง", "id": "Dokter Hewan / Hewan Peliharaan",
        "ms": "Veterinar / Haiwan Peliharaan", "tl": "Beterinaryo / Alagang Hayop", "hi": "पशु चिकित्सा / पालतू जानवरों की देखभाल",
        "bn": "পশুচিকিৎসা / পোষা প্রাণীর যত্ন", "ur": "ویٹرنری / پالتو جانور", "ta": "கால்நடை மருத்துவம்",
        "pa": "ਪਸ਼ੂ ਹਸਪਤਾਲ / ਪਾਲਤੂ ਸੰਭਾਲ", "ne": "पशु चिकित्सा / घरपालुवा जनावर", "sw": "Daktari wa Wanyama",
        "am": "የእንስሳት ሕክምና", "af": "Veeartseny / Troeteldierversorging", "ha": "Likitan Dabbobi",
        "my": "တိရစ္ဆာန်ဆေးကုသရေး", "km": "ពេទ្យសត្វ និងថែទាំសត្វចិញ្ចឹម", "mn": "Малын эмнэлэг / Тэжээвэр амьтад",
        "ka": "ვეტერინარია / შინაური ცხოველები", "hy": "Անասնաբուժություն / Կենդանիների խնամք"
    },
    "pharmacy": {
        "fr": "Pharmacie / Parapharmacie", "en": "Pharmacy / Parapharmacy", "es": "Farmacia / Parafarmacia",
        "pt": "Farmácia / Parafarmácia", "de": "Apotheke / Drogerie", "it": "Farmacia / Parafarmacia",
        "nl": "Apotheek / Drogisterij", "pl": "Apteka / Parafarmacja", "ro": "Farmacie / Parafarmacie",
        "ru": "Аптека / Парафармацевтика", "uk": "Аптека / Парафармацевтика", "el": "Φαρμακείο",
        "sv": "Apotek / Hälsa", "tr": "Eczane / Medikal", "cs": "Lékárna / Parafarmacie",
        "ar": "الصيدلية / المستحضرات الطبية", "he": "בית מרקחת ופארם", "fa": "داروخانه و محصولات بهداشتی",
        "zh": "药房 / 医药健康", "ja": "薬局・ドラッグストア", "ko": "약국 / 헬스케어",
        "vi": "Nhà thuốc / Dược phẩm", "th": "ร้านขายยา / เภสัชกรรม", "id": "Apotek / Farmasi",
        "ms": "Farmasi / Penjagaan Kesihatan", "tl": "Botika / Parmasya", "hi": "फार्मेसी / दवा की दुकान",
        "bn": "ফার্মেসি / ওষুধের দোকান", "ur": "فارمیسی / میڈیکل اسٹور", "ta": "மருந்தகம்",
        "pa": "ਫਾਰਮੇਸੀ / ਦਵਾਈਆਂ ਦੀ ਦੁਕਾਨ", "ne": "औषधि पसल / फार्मेसी", "sw": "Duka la Dawa",
        "am": "ፋርማሲ / መድኃኒት ቤት", "af": "Apteek", "ha": "Kemis / Shagon Magani",
        "my": "ဆေးဆိုင်နှင့် ကျန်းမာရေးသုံးပစ္စည်းများ", "km": "ឱសថស្ថាន", "mn": "Эмийн сан",
        "ka": "აფთიაქი / ფარმაცია", "hy": "Դեղատուն"
    },
    "consulting": {
        "fr": "Conseil / Agences", "en": "Consulting / Agencies", "es": "Consultoría / Agencias",
        "pt": "Consultoria / Agências", "de": "Beratung / Agenturen", "it": "Consulenza / Agenzie",
        "nl": "Adviesbureaus / Agentschappen", "pl": "Doradztwo / Agencje", "ro": "Consultanță / Agenții",
        "ru": "Консалтинг / Агентства", "uk": "Консалтинг / Агентства", "el": "Συμβουλευτική / Εταιρείες",
        "sv": "Konsulting / Byråer", "tr": "Danışmanlık / Ajanslar", "cs": "Poradenství / Agentury",
        "ar": "الاستشارات / الوكالات", "he": "ייעוץ וסוכנויות", "fa": "مشاوره و آژانس‌ها",
        "zh": "咨询 / 专业机构", "ja": "コンサルティング・代理店", "ko": "컨설팅 / 에이전시",
        "vi": "Tư vấn / Agency", "th": "ที่ปรึกษา / เอเจนซี่", "id": "Konsultan / Agensi",
        "ms": "Perundingan / Agensi", "tl": "Pagkonsulta / Ahensya", "hi": "परामर्श / एजेंसियां",
        "bn": "পরামর্শ / সংস্থা", "ur": "مشاورت / ایجنسیاں", "ta": "ஆலோசனை / முகமைகள்",
        "pa": "ਸਲਾਹਕਾਰ / ਏਜੰਸੀਆਂ", "ne": "परामर्श / एजेन्सीहरू", "sw": "Ushauri wa Biashara",
        "am": "አማካሪ / ኤጀንሲዎች", "af": "Konsultasie / Agentskappe", "ha": "Shawarwari / Hukumomi",
        "my": "အကြံပေးလုပ်ငန်းနှင့် အေဂျင်စီများ", "km": "ការប្រឹក្សា និងទីភ្នាក់ងារ", "mn": "Зөвлөх үйлчилгээ / Агентлаг",
        "ka": "კონსალტინგი / სააგენტოები", "hy": "Խորհրդատվություն / Գործակալություններ"
    },
    "fitness": {
        "fr": "Fitness / Gym / Coaching", "en": "Fitness / Gym / Coaching", "es": "Gimnasios / Fitness / Entrenadores",
        "pt": "Ginásios / Fitness / Coaching", "de": "Fitness / Fitnessstudios / Coaching", "it": "Fitness / Palestre / Coaching",
        "nl": "Fitness / Gym / Coaching", "pl": "Fitness / Siłownie / Treningi", "ro": "Fitness / Săli / Antrenorat",
        "ru": "Фитнес / Спортзалы / Тренировки", "uk": "Фітнес / Спортзали / Тренування", "el": "Fitness / Γυμναστήρια / Coaching",
        "sv": "Fitness / Gym / Träning", "tr": "Fitness / Spor Salonu / Antrenörlük", "cs": "Fitness / Posilovny / Koučink",
        "ar": "اللياقة البدنية / الصالات الرياضية", "he": "כושר וחדרי כושר", "fa": "تناسب اندام و باشگاه‌ها",
        "zh": "健身 / 健身房 / 教练", "ja": "フィットネス・ジム・コーチング", "ko": "피트니스 / 헬스장 / 코칭",
        "vi": "Thể hình / Phòng gym / Huấn luyện viên", "th": "ฟิตเนส / โรงยิม / โค้ช", "id": "Kebugaran / Gym / Pelatih",
        "ms": "Kecergasan / Gim / Kejurulatihan", "tl": "Fitness / Gym / Coaching", "hi": "फिटनेस / जिम / कोचिंग",
        "bn": "ফিটনেস / জিম / কোচিং", "ur": "فٹنس / جم / کوچنگ", "ta": "உடற்பயிற்சி / உடற்பயிற்சிக்கூடம்",
        "pa": "ਫਿਟਨੈਸ / ਜਿੰਮ / ਕੋਚਿੰਗ", "ne": "फिटनेस / जिम / कोचिङ", "sw": "Mazoezi / Gym",
        "am": "የአካል ብቃት / ጂም", "af": "Fiksheid / Gimnasium", "ha": "Motsa Jiki / Gym",
        "my": "ကြံ့ခိုင်ရေးနှင့် အားကစားခန်းမ", "km": "កាយសម្បទា និងកន្លែងហាត់ប្រាណ", "mn": "Фитнесс / Спорт заал",
        "ka": "ფიტნესი / დარბაზები / მწვრთნელები", "hy": "Ֆիթնես / Մարզասրահներ"
    },
    "events": {
        "fr": "Événementiel / Spectacles", "en": "Events / Entertainment", "es": "Eventos / Espectáculos",
        "pt": "Eventos / Espetáculos", "de": "Events / Veranstaltungen", "it": "Eventi / Spettacoli",
        "nl": "Evenementen / Entertainment", "pl": "Wydarzenia / Rozrywka", "ro": "Evenimente / Spectacole",
        "ru": "Мероприятия / Шоу", "uk": "Події / Шоу", "el": "Εκδηλώσεις / Θεάματα",
        "sv": "Evenemang / Nöje", "tr": "Etkinlikler / Gösteriler", "cs": "Události / Zábava",
        "ar": "الفعاليات / العروض", "he": "אירועים והופעות", "fa": "رویدادها و نمایش‌ها",
        "zh": "会展 / 活动演艺", "ja": "イベント・エンタメ", "ko": "이벤트 / 공연",
        "vi": "Sự kiện / Giải trí", "th": "อีเวนต์ / การแสดง", "id": "Acara / Hiburan",
        "ms": "Acara / Hiburan", "tl": "Kaganapan / Palabas", "hi": "कार्यक्रम / मनोरंजन",
        "bn": "ইভেন্ট / বিনোদন", "ur": "تقریبات / تفریح", "ta": "நிகழ்வுகள் / பொழுதுபோக்கு",
        "pa": "ਸਮਾਗਮ / ਮਨੋਰੰਜਨ", "ne": "कार्यक्रम / मनोरञ्जन", "sw": "Matukio / Burudani",
        "am": "ዝግጅቶች / መዝናኛ", "af": "Geleenthede / Vermaak", "ha": "Taruka / Nishaɗi",
        "my": "ပွဲလမ်းသဘင်များနှင့် ဖျော်ဖြေရေး", "km": "ព្រឹត្តិការណ៍ និងការកម្សាន្ត", "mn": "Арга хэмжээ / Энтертайнмент",
        "ka": "ღონისძიებები / სანახაობები", "hy": "Միջոցառումներ / Շոուներ"
    },
    "logistics_delivery": {
        "fr": "Livraison / Coursiers", "en": "Courier / Last-mile Delivery", "es": "Mensajería / Reparto",
        "pt": "Entregas / Estafetas", "de": "Kurierdienste / Letzte Meile", "it": "Corrieri / Consegne",
        "nl": "Koeriers / Bezorging", "pl": "Kurierzy / Dostawy", "ro": "Curierat / Livrări",
        "ru": "Курьерские службы / Доставка", "uk": "Кур'єри / Доставка", "el": "Courier / Παραδόσεις",
        "sv": "Bud / Leverans", "tr": "Kurye / Teslimat", "cs": "Kurýři / Doručování",
        "ar": "التوصيل / خدمات البريد السريع", "he": "משלוחים ושליחויות", "fa": "پیک و تحویل مرسولات",
        "zh": "同城配送 / 快递", "ja": "宅配・配送サービス", "ko": "택배 / 퀵 배송",
        "vi": "Giao hàng / Chuyển phát nhanh", "th": "เดลิเวอรี่ / ส่งพัสดุ", "id": "Kurir / Pengiriman",
        "ms": "Kurier / Penghantaran", "tl": "Delivery / Kartero", "hi": "कूरियर / डिलीवरी",
        "bn": "কুরিয়ার / ডেলিভারি", "ur": "کورئیر / ترسیل", "ta": "கூரியர் / டெலிவரி",
        "pa": "ਕੂਰੀਅਰ / ਡਿਲੀਵਰੀ", "ne": "कुरियर / डेलिभरी", "sw": "Uwasilishaji wa Mizigo",
        "am": "መልእክት / ማድረሻ", "af": "Koeriers / Aflewering", "ha": "Aika Saƙo / Isarwa",
        "my": "ချောပို့နှင့် ပို့ဆောင်ရေးဝန်ဆောင်မှု", "km": "សេវាកម្មដឹកជញ្ជូនរហ័ស", "mn": "Хүргэлт / Шуудан",
        "ka": "საკურიერო / მიწოდება", "hy": "Առաքում / Կուրյերական ծառայություններ"
    },
    "property_management": {
        "fr": "Gestion locative / Syndics", "en": "Property Management", "es": "Gestión de alquileres / Fincas",
        "pt": "Gestão de Condomínios / Arrendamento", "de": "Hausverwaltung / Mietverwaltung", "it": "Gestione immobiliare / Condomini",
        "nl": "Vastgoedbeheer / VvE", "pl": "Zarządzanie nieruchomościami", "ro": "Administrare imobile / Asociații",
        "ru": "Управление недвижимостью / ТСЖ", "uk": "Управління нерухомістю / ОСББ", "el": "Διαχείριση ακινήτων",
        "sv": "Fastighetsförvaltning", "tr": "Mülk Yönetimi / Site Yönetimi", "cs": "Správa nemovitostí / SVJ",
        "ar": "إدارة العقارات / اتحاد الملاك", "he": "ניהול נכסים וועדי בית", "fa": "مدیریت املاک و مجتمع‌ها",
        "zh": "物业管理 / 房屋托管", "ja": "不動産管理・ビル管理", "ko": "부동산 자산 관리 / 임대 관리",
        "vi": "Quản lý tòa nhà / Bất động sản", "th": "การจัดการทรัพย์สิน / นิติบุคคล", "id": "Manajemen Properti",
        "ms": "Pengurusan Hartanah", "tl": "Pamamahala ng Ari-arian", "hi": "संपत्ति प्रबंधन",
        "bn": "সম্পত্তি ব্যবস্থাপনা", "ur": "پراپرٹی مینجمنٹ", "ta": "சொத்து மேலாண்மை",
        "pa": "ਜਾਇਦਾਦ ਪ੍ਰਬੰਧਨ", "ne": "सम्पत्ति व्यवस्थापन", "sw": "Usimamizi wa Majengo",
        "am": "የንብረት አስተዳደር", "af": "Eiendomsbestuur", "ha": "Kula da Filaye da Gidaje",
        "my": "အိမ်ခြံမြေစီမံခန့်ခွဲမှု", "km": "ការគ្រប់គ្រងអចលនទ្រព្យ", "mn": "Үл хөдлөх хөрөнгийн менежмент",
        "ka": "ქონების მართვა", "hy": "Գույքի կառավարում"
    },
    "commercial_realestate": {
        "fr": "Immobilier d'entreprise / Bureaux", "en": "Commercial Real Estate", "es": "Inmobiliaria comercial / Oficinas",
        "pt": "Imobiliário Comercial / Escritórios", "de": "Gewerbeimmobilien / Büros", "it": "Immobili commerciali / Uffici",
        "nl": "Commercieel vastgoed / Kantoren", "pl": "Nieruchomości komercyjne / Biura", "ro": "Imobiliare comerciale / Birouri",
        "ru": "Коммерческая недвижимость / Офисы", "uk": "Комерційна нерухомість / Офіси", "el": "Επαγγελματικά ακίνητα / Γραφεία",
        "sv": "Kommersiella fastigheter / Kontor", "tr": "Ticari Gayrimenkul / Ofisler", "cs": "Komerční reality / Kanceláře",
        "ar": "العقارات التجارية / المكاتب", "he": "נדל\"ן מסחרי ומשרדים", "fa": "املاک تجاری و اداری",
        "zh": "商用地产 / 写字楼", "ja": "商業用不動産・オフィス", "ko": "상업용 부동산 / 오피스",
        "vi": "Bất động sản thương mại / Văn phòng", "th": "อสังหาริมทรัพย์เพื่อการพาณิชย์ / สำนักงาน", "id": "Properti Komersial / Perkantoran",
        "ms": "Hartanah Komersial / Pejabat", "tl": "Komersyal na Real Estate", "hi": "वाणिज्यिक रियल एस्टेट / कार्यालय",
        "bn": "বাণিজ্যিক রিয়েল এস্টেট / অফিস", "ur": "تجارتی رئیل اسٹیٹ / دفاتر", "ta": "வணிக ரியல் எஸ்டேட்",
        "pa": "ਵਪਾਰਕ ਰੀਅਲ ਅਸਟੇਟ", "ne": "व्यापारिक घरजग्गा / कार्यालय", "sw": "Majengo ya Biashara",
        "am": "የንግድ ሪል እስቴት / ቢሮዎች", "af": "Kommersiële Eiendom", "ha": "Filayen Kasuwanci",
        "my": "စီးပွားရေးဆိုင်ရာ အိမ်ခြံမြေ", "km": "អចលនទ្រព្យពាណិជ្ជកម្ម", "mn": "Худалдааны үл хөдлөх хөрөнгө",
        "ka": "კომერციული უძრავი ქონება", "hy": "Կոմերցիոն անշարժ գույք"
    },
    "telecom": {
        "fr": "Télécoms / FAI / Réseaux", "en": "Telecom / ISP / Networks", "es": "Telecomunicaciones / Proveedores de Internet",
        "pt": "Telecomunicações / Operadores / Redes", "de": "Telekommunikation / Internetanbieter", "it": "Telecomunicazioni / Provider / Reti",
        "nl": "Telecom / Providers / Netwerken", "pl": "Telekomunikacja / Dostawcy Internetu", "ro": "Telecomunicații / Furnizori Internet",
        "ru": "Телекоммуникации / Провайдеры", "uk": "Телекомунікації / Провайдери", "el": "Τηλεπικοινωνίες / Πάροχοι",
        "sv": "Telekom / Internetleverantörer", "tr": "Telekomünikasyon / İnternet Sağlayıcıları", "cs": "Telekomunikace / Poskytovatelé internetu",
        "ar": "الاتصالات / مزودو الإنترنت", "he": "טלקום וספקי אינטרเนט", "fa": "مخابرات و ارائه‌دهندگان اینترنت",
        "zh": "电信 / 网络运营商", "ja": "通信・インターネット事業者", "ko": "통신 / 인터넷 서비스",
        "vi": "Viễn thông / Nhà mạng", "th": "โทรคมนาคม / ผู้ให้บริการอินเทอร์เน็ต", "id": "Telekomunikasi / Penyedia Internet",
        "ms": "Telekomunikasi / Penyedia Internet", "tl": "Telekomunikasyon / ISP", "hi": "दूरसंचार / इंटरनेट प्रदाता",
        "bn": "টেলিকম / ইন্টারনেট সেবাদাতা", "ur": "ٹیلی کام / انٹرنیٹ فراہم کنندگان", "ta": "தொலைத்தொடர்பு / இணைய சேவை",
        "pa": "ਦੂਰਸੰਚਾਰ / ਇੰਟਰਨੈੱਟ ਪ੍ਰਦਾਤਾ", "ne": "दूरसञ्चार / इन्टरनेट प्रदायक", "sw": "Mawasiliano ya Simu",
        "am": "ቴሌኮሙኒኬሽን / ኢንተርኔት አቅራቢዎች", "af": "Telekommunikasie / ISP", "ha": "Hanyoyin Sadarwa / ISP",
        "my": "ဆက်သွယ်ရေးနှင့် အင်တာနက်ဝန်ဆောင်မှု", "km": "ទូរគមនាគមន៍ និងអ៊ីនធឺណិត", "mn": "Харилцаа холбоо / Интернэт үйлчилгээ",
        "ka": "ტელეკომუნიკაცია / პროვაიდერები", "hy": "Հեռահաղորդակցություն / Ինտերնետ կապ"
    },
    "public_sector": {
        "fr": "Mairies / Services publics", "en": "Municipalities / Public Sector", "es": "Ayuntamientos / Sector público",
        "pt": "Câmaras Municipais / Serviços Públicos", "de": "Kommunen / Öffentlicher Dienst", "it": "Comuni / Pubblica amministrazione",
        "nl": "Gemeenten / Publieke sector", "pl": "Urzędy / Sektor publiczny", "ro": "Primării / Servicii publice",
        "ru": "Муниципалитеты / Госслужба", "uk": "Міськради / Держпослуги", "el": "Δήμοι / Δημόσιος τομέας",
        "sv": "Kommuner / Offentlig sektor", "tr": "Belediyeler / Kamu Hizmetleri", "cs": "Městské úřady / Veřejná správa",
        "ar": "البلديات / الخدمات الحكومية", "he": "עיריות והמגזר הציבורי", "fa": "شهرداری‌ها و خدمات عمومی",
        "zh": "政务便民 / 公共部门", "ja": "自治体・公共サービス", "ko": "공공기관 / 지자체",
        "vi": "Dịch vụ công / Hành chính", "th": "เทศบาล / บริการสาธารณะ", "id": "Pemerintah Daerah / Layanan Publik",
        "ms": "Pihak Berkuasa Tempatan / Sektor Awam", "tl": "Munisipyo / Serbisyong Publiko", "hi": "नगर पालिका / सार्वजनिक सेवा",
        "bn": "পৌরসভা / সরকারি সেবা", "ur": "بلدیات / پبلک سیکٹر", "ta": "நகராட்சிகள் / பொது சேவை",
        "pa": "ਨਗਰ ਪਾਲਿਕਾਵਾਂ / ਜਨਤਕ ਸੇਵਾ", "ne": "नगरपालिका / सार्वजनिक सेवा", "sw": "Serikali za Mitaa",
        "am": "ማዘጋጃ ቤቶች / የመንግስት አገልግሎቶች", "af": "Munisipaliteite / Publieke Sektor", "ha": "Kananan Hukumomi / Ayyukan Gwamnati",
        "my": "စည်ပင်သာယာနှင့် ပြည်သူ့ဝန်ဆောင်မှုများ", "km": "សាលាក្រុង និងសេវាសាធារណៈ", "mn": "Хотын захиргаа / Төрийн үйлчилгээ",
        "ka": "მუნიციპალიტეტები / საჯარო სექტორი", "hy": "Քաղաքապետարաններ / Հանրային ծառայություններ"
    },
    "wholesale": {
        "fr": "Grossistes / Négoce B2B", "en": "Wholesale / B2B Trade", "es": "Mayoristas / Comercio B2B",
        "pt": "Grossistas / Comércio B2B", "de": "Großhandel / B2B-Handel", "it": "Commercio all'ingrosso / B2B",
        "nl": "Groothandel / B2B-handel", "pl": "Hurtownie / Handel B2B", "ro": "Comerț cu ridicata / B2B",
        "ru": "Оптовая торговля / B2B", "uk": "Оптова торгівля / B2B", "el": "Χονδρικό εμπόριο / B2B",
        "sv": "Grossister / B2B-handel", "tr": "Toptan Ticaret / B2B", "cs": "Velkoobchod / B2B",
        "ar": "تجارة الجملة / المعاملات بين الشركات", "he": "סיטונאות ומסחר B2B", "fa": "عمده‌فروشی و تجارت سازمانی",
        "zh": "批发 / B2B 贸易", "ja": "卸売・B2Bコマース", "ko": "도매 / B2B 무역",
        "vi": "Bán buôn / Thương mại B2B", "th": "ค้าส่ง / การค้า B2B", "id": "Grosir / Perdagangan B2B",
        "ms": "Pemborong / Perdagangan B2B", "tl": "Pakyawan / B2B Trade", "hi": "थोक व्यापार / बी2बी",
        "bn": "পাইকারি / বি২বি বাণিজ্য", "ur": "تھوک تجارت / بی ٹو بی", "ta": "மொத்த விற்பனை / B2B",
        "pa": "ਥੋਕ ਵਪਾਰ / ਬੀ2ਬੀ", "ne": "थोक व्यापार / बीटुबी", "sw": "Biashara ya Jumla",
        "am": "ጅምላ ንግድ / B2B", "af": "Groothandel / B2B-handel", "ha": "Sari / Kasuwancin B2B",
        "my": "လက်ကားနှင့် B2B ကုန်သွယ်ရေး", "km": "ការលក់ដុំ និងពាណិជ្ជកម្ម B2B", "mn": "Бөөний худалдаа / B2B",
        "ka": "საბითუმო ვაჭრობა / B2B", "hy": "Մեծածախ առևտուր / B2B"
    },
    "agriculture": {
        "fr": "Agriculture / Agroalimentaire", "en": "Agriculture / Agribusiness", "es": "Agricultura / Agroindustria",
        "pt": "Agricultura / Agroalimentar", "de": "Landwirtschaft / Agrarwirtschaft", "it": "Agricoltura / Agroalimentare",
        "nl": "Landbouw / Agrarische sector", "pl": "Rolnictwo / Agrobiznes", "ro": "Agricultură / Agroalimentar",
        "ru": "Сельское хозяйство / Агробизнес", "uk": "Сільське господарство / Агробізнес", "el": "Γεωργία / Αγροδιατροφή",
        "sv": "Jordbruk / Lantbruk", "tr": "Tarım / Tarım Sanayisi", "cs": "Zemědělství / Agrobysznys",
        "ar": "الزراعة / الصناعات الزراعية", "he": "חקלאות ותעשיית המזון", "fa": "کشاورزی و صنایع غذایی",
        "zh": "农业 / 现代农牧", "ja": "農業・アグリビジネス", "ko": "농업 / 애그리비즈니스",
        "vi": "Nông nghiệp / Nông sản", "th": "เกษตรกรรม / ธุรกิจการเกษตร", "id": "Pertanian / Agribisnis",
        "ms": "Pertanian / Agribisnes", "tl": "Agrikultura / Agribusiness", "hi": "कृषि / कृषि व्यवसाय",
        "bn": "কৃষি / কৃষিব্যবসা", "ur": "زراعت / زرعی کاروبار", "ta": "வேளாண்மை / விவசாயம்",
        "pa": "ਖੇਤੀਬਾੜੀ / ਖੇਤੀ ਕਾਰੋਬਾਰ", "ne": "कृषि / कृषि व्यवसाय", "sw": "Kilimo / Biashara ya Kilimo",
        "am": "ግብርና / አግሪቢዝነስ", "af": "Landbou / Agribesigheid", "ha": "Aikin Noma / Kasuwancin Noma",
        "my": "စိုက်ပျိုးရေးနှင့် စိုက်ပျိုးရေးလုပ်ငန်း", "km": "កសិកម្ម និងកសិពាណិជ្ជកម្ម", "mn": "Хөдөө аж ахуй / Газар тариалан",
        "ka": "სოფლის მეურნეობა / აგრობიზნესი", "hy": "Գյուղատնտեսություն / Ագրոբիզնես"
    },
    "security_services": {
        "fr": "Sécurité privée / Gardiennage", "en": "Private Security / Guarding", "es": "Seguridad privada / Vigilancia",
        "pt": "Segurança Privada / Vigilância", "de": "Sicherheitsdienste / Wachschutz", "it": "Sicurezza privata / Vigilanza",
        "nl": "Beveiligingsdiensten / Bewaking", "pl": "Ochrona mienia / Ochrona fizyczna", "ro": "Pază și protecție / Securitate",
        "ru": "Охранные агентства / Безопасность", "uk": "Охоронні агентства / Безпека", "el": "Ιδιωτική ασφάλεια / Φύλαξη",
        "sv": "Säkerhetsföretag / Bevakning", "tr": "Özel Güvenlik / Koruma", "cs": "Bezpečnostní služby / Ostraha",
        "ar": "الأمن والحراسة الخاصة", "he": "אבטחה ושמירה פרטית", "fa": "نگهبانی و امنیت خصوصی",
        "zh": "安保 / 保安服务", "ja": "警備・セキュリティサービス", "ko": "보안 경비 / 시설 경비",
        "vi": "Bảo vệ / An ninh tư nhân", "th": "รักษาความปลอดภัย / รปภ.", "id": "Keamanan Swasta / Penjagaan",
        "ms": "Keselamatan Swasta / Pengawalan", "tl": "Seguridad / Guwardiya", "hi": "निजी सुरक्षा / गार्डिंग",
        "bn": "নিরাপত্তা প্রহরী / সুরক্ষা", "ur": "پرائیویٹ سیکیورٹی / گارڈنگ", "ta": "தனியார் பாதுகாப்பு",
        "pa": "ਨਿੱਜੀ ਸੁਰੱਖਿਆ / ਗਾਰਡਿੰਗ", "ne": "निजी सुरक्षा / गार्ड सेवा", "sw": "Ulinzi Binafsi",
        "am": "የግል ደህንነት / ጥበቃ", "af": "Privaat Sekuriteit / Bewaking", "ha": "Tsaron Gida da Kamfanoni",
        "my": "လုံခြုံရေးနှင့် စောင့်ကြပ်ရေးဝန်ဆောင်မှု", "km": "សន្តិសុខឯកជន និងការយាមកាម", "mn": "Хамгаалалтын алба / Харуул",
        "ka": "დაცვის სამსახური / უსაფრთხოება", "hy": "Անվտանգության ծառայություններ"
    },
    "cleaning": {
        "fr": "Nettoyage commercial / Entretien ménager", "en": "Commercial Cleaning", "es": "Limpieza comercial / Mantenimiento",
        "pt": "Limpeza comercial / Manutenção", "de": "Gebäudereinigung / Facility Management", "it": "Pulizie commerciali / Manutenzione",
        "nl": "Schoonmaakbedrijven / Onderhoud", "pl": "Sprzątanie komercyjne / Utrzymanie czystości", "ro": "Curățenie comercială / Întreținere",
        "ru": "Клининг / Коммерческая уборка", "uk": "Клінінг / Комерційне прибирання", "el": "Επαγγελματικός καθαρισμός / Συντήρηση",
        "sv": "Lokalvård / Städservice", "tr": "Ticari Temizlik / Tesis Bakımı", "cs": "Úklidové služby / Údržba",
        "ar": "خدمات النظافة التجارية / الصيانة", "he": "ניקיון משרדים ואחזקה", "fa": "نظافت تجاری و خدمات بهداشتی",
        "zh": "商业保洁 / 物业清洁", "ja": "清掃サービス・ビルメンテナンス", "ko": "청소 용역 / 시설 관리",
        "vi": "Vệ sinh công nghiệp / Tòa nhà", "th": "บริการทำความสะอาดเชิงพาณิชย์", "id": "Jasa Kebersihan / Cleaning Service",
        "ms": "Pembersihan Komersial / Penyelenggaraan", "tl": "Commercial Cleaning / Maintenance", "hi": "व्यावसायिक सफाई / रखरखाव",
        "bn": "বাণিজ্যিক পরিচ্ছন্নতা / রক্ষণাবেক্ষণ", "ur": "کمرشل صفائی / دیکھ بھال", "ta": "வணிக தூய்மைப்படுத்தல்",
        "pa": "ਵਪਾਰਕ ਸਫਾਈ", "ne": "व्यापारिक सरसफाइ", "sw": "Usafi wa Majengo",
        "am": "የንግድ ቤቶች ጽዳት", "af": "Kommersiële Skoonmaak", "ha": "Tsaftar Gidajen Kasuwanci",
        "my": "သန့်ရှင်းရေးနှင့် ထိန်းသိမ်းရေးဝန်ဆောင်မှု", "km": "សេវាកម្មសម្អាតពាណិជ្ជកម្ម", "mn": "Цэвэрлэгээ үйлчилгээ",
        "ka": "დასუფთავების სერვისი", "hy": "Մաքրման ծառայություններ"
    },
    "custom": {
        "fr": "Autre secteur / Personnalisé", "en": "Other / Custom Industry", "es": "Otro sector / Personalizado",
        "pt": "Outro setor / Personalizado", "de": "Anderer Sektor / Individuell", "it": "Altro settore / Personalizzato",
        "nl": "Andere sector / Aangepast", "pl": "Inna branża / Własna", "ro": "Alt sector / Personalizat",
        "ru": "Другая отрасль / Индивидуальная", "uk": "Інша галузь / Індивідуальна", "el": "Άλλος τομέας / Προσαρμοσμένος",
        "sv": "Annan bransch / Anpassad", "tr": "Diğer Sektör / Özel", "cs": "Jiné odvětví / Vlastní",
        "ar": "قطاع آخر / مخصص", "he": "מגזר אחר / מותאם אישית", "fa": "سایر بخش‌ها / سفارشی",
        "zh": "其他行业 / 自定义", "ja": "その他の業種・カスタム", "ko": "기타 업종 / 사용자 지정",
        "vi": "Ngành khác / Tùy chỉnh", "th": "ภาคธุรกิจอื่นๆ / กำหนดเอง", "id": "Sektor Lainnya / Kustom",
        "ms": "Sektor Lain / Tersuai", "tl": "Ibang Sektor / Kustom", "hi": "अन्य क्षेत्र / अनुकूलित",
        "bn": "অন্যান্য খাত / কাস্টম", "ur": "دیگر شعبہ / اپنی مرضی کے مطابق", "ta": "பிற துறைகள் / தனிப்பயன்",
        "pa": "ਹੋਰ ਖੇਤਰ / ਕਸਟਮ", "ne": "अन्य क्षेत्र / अनुकूलित", "sw": "Sekta Nyingine / Maalum",
        "am": "ሌላ ዘርፍ / ብጁ", "af": "Ander Bedryf / Pasgemaak", "ha": "Wani Bangare daban",
        "my": "အခြားလုပ်ငန်း / စိတ်ကြိုက်", "km": "វិស័យផ្សេងទៀត / ផ្ទាល់ខ្លួន", "mn": "Бусад салбар / Захиалгат",
        "ka": "სხვა სექტორი / ინდივიდუალური", "hy": "Այլ ոլորտ / Անհատական"
    }
}

# UI Strings generator for each locale
def make_ui_strings(loc: str):
    lang = loc.split("-")[0]
    
    # Defaults (English)
    ui = {
        "sectionTitle": "AN AI TAILORED FOR EVERY INDUSTRY",
        "sectionSubtitle": "Natural conversations, integrated business workflows, and a tailored client experience whatever your industry.",
        "searchPlaceholder": "Search an industry...",
        "expandButton": "View more industries",
        "collapseButton": "Show fewer",
        "customIndustryPrompt": "Can't find your industry?",
        "customIndustryPlaceholder": "Describe your business (e.g. Artisanal bakery, Diving school...)",
        "suggestionsTitle": "Suggested industry capabilities for this sector:",
        "suggestionsDisclaimer": "These suggestions illustrate potential AI capabilities. Advanced workflows depend on active account modules (CRM, Retail, Appointments).",
        "crmRequired": "CRM module required",
        "crmActive": "CRM module active",
        "retailRequired": "Retail module required",
        "retailActive": "Retail module active",
        "generalQa": "Standard included (FAQ & Front-desk)",
        "noIndustrySelected": "No industry selected. Please select at least one industry below.",
        "primarySector": "Primary industry",
        "selectedCount": "selected"
    }
    
    if loc in ("fr", "fr-FR"):
        ui["sectionTitle"] = "UNE IA ADAPTÉE À CHAQUE INDUSTRIE"
        ui["sectionSubtitle"] = "Des conversations naturelles, des processus métiers intégrés et une expérience client sur mesure, quel que soit votre secteur."
        ui["searchPlaceholder"] = "Rechercher une industrie..."
        ui["expandButton"] = "Voir plus d'industries"
        ui["collapseButton"] = "Réduire la liste"
        ui["customIndustryPrompt"] = "Votre secteur n'est pas dans la liste ?"
        ui["customIndustryPlaceholder"] = "Décrivez votre activité (ex. Menuiserie d'art, Club de plongée...)"
        ui["suggestionsTitle"] = "Suggestions de capacités métier pour ce secteur :"
        ui["suggestionsDisclaimer"] = "Ces suggestions illustrent les capacités de l'agent IA. Les intégrations avancées dépendent des modules actifs sur votre compte (CRM, Retail, Prise de rendez-vous)."
        ui["crmRequired"] = "Module CRM requis"
        ui["crmActive"] = "Module CRM actif"
        ui["retailRequired"] = "Module Retail requis"
        ui["retailActive"] = "Module Retail actif"
        ui["generalQa"] = "Inclus standard (FAQ & Accueil)"
        ui["noIndustrySelected"] = "Aucun secteur sélectionné. Veuillez choisir au moins une industrie ci-dessous."
        ui["primarySector"] = "Secteur principal"
        ui["selectedCount"] = "sélectionnés"
    elif lang == "es":
        ui["sectionTitle"] = "UNA IA ADAPTADA A CADA INDUSTRIA"
        ui["sectionSubtitle"] = "Conversaciones fluidas, flujos de trabajo integrados y una atención personalizada en cualquier sector."
        ui["searchPlaceholder"] = "Buscar una industria..."
        ui["expandButton"] = "Ver más industrias"
        ui["collapseButton"] = "Mostrar menos"
        ui["customIndustryPrompt"] = "¿No encuentra su sector?"
        ui["customIndustryPlaceholder"] = "Describa su actividad..."
        ui["suggestionsTitle"] = "Capacidades sugeridas para este sector:"
        ui["suggestionsDisclaimer"] = "Estas sugerencias ilustran las capacidades de la IA. Las integraciones avanzadas dependen de los módulos activos (CRM, Retail, Citas)."
        ui["crmRequired"] = "Módulo CRM requerido"
        ui["crmActive"] = "Módulo CRM activo"
        ui["retailRequired"] = "Módulo Retail requerido"
        ui["retailActive"] = "Módulo Retail activo"
        ui["generalQa"] = "Incluido estándar (FAQ y Recepción)"
        ui["noIndustrySelected"] = "Ningún sector seleccionado. Elija al menos una industria."
        ui["primarySector"] = "Sector principal"
        ui["selectedCount"] = "seleccionados"
    elif lang == "de":
        ui["sectionTitle"] = "EINE KI FÜR JEDE BRANCHE"
        ui["sectionSubtitle"] = "Natürliche Gespräche, integrierte Geschäftsprozesse und ein maßgeschneiderter Kundenservice in jeder Branche."
        ui["searchPlaceholder"] = "Branche suchen..."
        ui["expandButton"] = "Weitere Branchen anzeigen"
        ui["collapseButton"] = "Weniger anzeigen"
        ui["customIndustryPrompt"] = "Ihre Branche ist nicht dabei?"
        ui["customIndustryPlaceholder"] = "Beschreiben Sie Ihre Tätigkeit..."
        ui["suggestionsTitle"] = "Vorgeschlagene Funktionen für diese Branche:"
        ui["suggestionsDisclaimer"] = "Diese Vorschläge veranschaulichen KI-Funktionen. Erweiterte Integrationen erfordern aktive Module (CRM, Retail, Kalender)."
        ui["crmRequired"] = "CRM-Modul erforderlich"
        ui["crmActive"] = "CRM-Modul aktiv"
        ui["retailRequired"] = "Retail-Modul erforderlich"
        ui["retailActive"] = "Retail-Modul aktiv"
        ui["generalQa"] = "Standard enthalten (FAQ & Empfang)"
        ui["noIndustrySelected"] = "Keine Branche ausgewählt. Bitte wählen Sie mindestens eine aus."
        ui["primarySector"] = "Hauptbranche"
        ui["selectedCount"] = "ausgewählt"
    elif lang == "it":
        ui["sectionTitle"] = "UN'IA SU MISURA PER OGNI SETTORE"
        ui["sectionSubtitle"] = "Conversazioni naturali, flussi di lavoro integrati e un'esperienza cliente personalizzata per ogni settore."
        ui["searchPlaceholder"] = "Cerca un settore..."
        ui["expandButton"] = "Mostra altri settori"
        ui["collapseButton"] = "Mostra meno"
        ui["customIndustryPrompt"] = "Il tuo settore non è nell'elenco?"
        ui["customIndustryPlaceholder"] = "Descrivi la tua attività..."
        ui["suggestionsTitle"] = "Integrazioni suggerite per questo settore:"
        ui["suggestionsDisclaimer"] = "Queste integrazioni dipendono dai moduli attivi sul tuo account (CRM, Retail, Appuntamenti)."
        ui["crmRequired"] = "Modulo CRM richiesto"
        ui["crmActive"] = "Modulo CRM attivo"
        ui["retailRequired"] = "Modulo Retail richiesto"
        ui["retailActive"] = "Modulo Retail attivo"
        ui["generalQa"] = "Incluso standard (FAQ & Accoglienza)"
        ui["noIndustrySelected"] = "Nessun settore selezionato."
        ui["primarySector"] = "Settore principale"
        ui["selectedCount"] = "selezionati"
    elif lang == "pt":
        ui["sectionTitle"] = "UMA IA ADAPTADA A CADA SETOR"
        ui["sectionSubtitle"] = "Conversas naturais, fluxos integrados e atendimento personalizado para qualquer setor."
        ui["searchPlaceholder"] = "Pesquisar um setor..."
        ui["expandButton"] = "Ver mais setores"
        ui["collapseButton"] = "Mostrar menos"
        ui["customIndustryPrompt"] = "Não encontra o seu setor?"
        ui["customIndustryPlaceholder"] = "Descreva a sua atividade..."
        ui["suggestionsTitle"] = "Capacidades sugeridas para este setor:"
        ui["suggestionsDisclaimer"] = "As integrações avançadas dependem dos módulos ativos na sua conta (CRM, Varejo, Agendamento)."
        ui["crmRequired"] = "Módulo CRM necessário"
        ui["crmActive"] = "Módulo CRM ativo"
        ui["retailRequired"] = "Módulo Retail necessário"
        ui["retailActive"] = "Módulo Retail ativo"
        ui["generalQa"] = "Incluído padrão (FAQ & Recepção)"
        ui["noIndustrySelected"] = "Nenhum setor selecionado."
        ui["primarySector"] = "Setor principal"
        ui["selectedCount"] = "selecionados"
    elif lang in ("ar", "ar-EG"):
        ui["sectionTitle"] = "ذكاء اصطناعي مخصص لكل قطاع"
        ui["sectionSubtitle"] = "محادثات طبيعية وسير عمل متكامل وتجربة عملاء مخصصة لأي مجال عمل."
        ui["searchPlaceholder"] = "البحث عن قطاع..."
        ui["expandButton"] = "عرض المزيد من القطاعات"
        ui["collapseButton"] = "عرض أقل"
        ui["customIndustryPrompt"] = "ألم تجد قطاعك؟"
        ui["customIndustryPlaceholder"] = "صف نشاطك التجاري..."
        ui["suggestionsTitle"] = "القدرات المقترحة لهذا القطاع:"
        ui["suggestionsDisclaimer"] = "توضح هذه الاقتراحات قدرات الذكاء الاصطناعي وتتطلب تفعيل الوحدات المناسبة (إدارة العملاء، التجزئة، المواعيد)."
        ui["crmRequired"] = "يتطلب وحدة إدارة العملاء CRM"
        ui["crmActive"] = "وحدة CRM نشطة"
        ui["retailRequired"] = "يتطلب وحدة التجزئة Retail"
        ui["retailActive"] = "وحدة التجزئة نشطة"
        ui["generalQa"] = "مشمول قياسياً (الأسئلة الشائعة والاستقبال)"
        ui["noIndustrySelected"] = "لم يتم تحديد أي قطاع."
        ui["primarySector"] = "القطاع الرئيسي"
        ui["selectedCount"] = "تم تحديدها"
    elif lang == "zh":
        ui["sectionTitle"] = "为各行各业量身定制的 AI"
        ui["sectionSubtitle"] = "自然流畅的对话、深度整合的业务流程，为各行业提供度身定制的客户体验。"
        ui["searchPlaceholder"] = "搜索行业..."
        ui["expandButton"] = "查看更多行业"
        ui["collapseButton"] = "收起"
        ui["customIndustryPrompt"] = "未找到您的行业？"
        ui["customIndustryPlaceholder"] = "描述您的业务类型..."
        ui["suggestionsTitle"] = "该行业推荐集成功能："
        ui["suggestionsDisclaimer"] = "这些建议展示了 AI 能力。高级工作流取决于您账户中启用的模块（CRM、零售、预约）。"
        ui["crmRequired"] = "需要 CRM 模块"
        ui["crmActive"] = "CRM 模块已启用"
        ui["retailRequired"] = "需要零售模块"
        ui["retailActive"] = "零售模块已启用"
        ui["generalQa"] = "标配功能（常见问答与前台问答）"
        ui["noIndustrySelected"] = "未选择任何行业。"
        ui["primarySector"] = "主要行业"
        ui["selectedCount"] = "已选择"
    elif lang == "ja":
        ui["sectionTitle"] = "あらゆる業界に最適化された AI"
        ui["sectionSubtitle"] = "自然な対話、統合された業務ワークフロー、業界ごとの最適な顧客体験を提供します。"
        ui["searchPlaceholder"] = "業界を検索..."
        ui["expandButton"] = "その他の業界を表示"
        ui["collapseButton"] = "折りたたむ"
        ui["customIndustryPrompt"] = "対象の業界が見つかりませんか？"
        ui["customIndustryPlaceholder"] = "業務内容を入力してください..."
        ui["suggestionsTitle"] = "この業界の推奨機能："
        ui["suggestionsDisclaimer"] = "これらは AI の活用例です。高度な機能には対応モジュール（CRM、小売、予約）の有効化が必要です。"
        ui["crmRequired"] = "CRM モジュールが必要"
        ui["crmActive"] = "CRM モジュール有効"
        ui["retailRequired"] = "小売モジュールが必要"
        ui["retailActive"] = "小売モジュール有効"
        ui["generalQa"] = "標準搭載（FAQ・総合案内）"
        ui["noIndustrySelected"] = "業界が選択されていません。"
        ui["primarySector"] = "主要業種"
        ui["selectedCount"] = "件選択中"
    elif lang == "ru":
        ui["sectionTitle"] = "ИИ, АДАПТИРОВАННЫЙ ДЛЯ КАЖДОЙ ОТРАСЛИ"
        ui["sectionSubtitle"] = "Естественные диалоги, интегрированные бизнес-процессы и персонализированное обслуживание для любой отрасли."
        ui["searchPlaceholder"] = "Поиск отрасли..."
        ui["expandButton"] = "Показать больше отраслей"
        ui["collapseButton"] = "Свернуть"
        ui["customIndustryPrompt"] = "Не нашли свою отрасль?"
        ui["customIndustryPlaceholder"] = "Опишите вашу деятельность..."
        ui["suggestionsTitle"] = "Рекомендуемые отраслевые возможности:"
        ui["suggestionsDisclaimer"] = "Эти сценарии требуют наличия соответствующих активных модулей (CRM, Ритейл, Запись на прием)."
        ui["crmRequired"] = "Требуется модуль CRM"
        ui["crmActive"] = "Модуль CRM активен"
        ui["retailRequired"] = "Требуется модуль Ритейл"
        ui["retailActive"] = "Модуль Ритейл активен"
        ui["generalQa"] = "Стандартная функция (FAQ и прием звонков)"
        ui["noIndustrySelected"] = "Отрасль не выбрана."
        ui["primarySector"] = "Основная отрасль"
        ui["selectedCount"] = "выбрано"
    elif lang == "ro":
        ui["sectionTitle"] = "O INTELIGENȚĂ ARTIFICIALĂ ADAPTATĂ FIECĂREI INDUSTRII"
        ui["sectionSubtitle"] = "Conversații naturale, fluxuri de lucru integrate și o experiență dedicată clienților în orice domeniu."
        ui["searchPlaceholder"] = "Căutați o industrie..."
        ui["expandButton"] = "Afișați mai multe industrii"
        ui["collapseButton"] = "Afișați mai puține"
        ui["customIndustryPrompt"] = "Nu găsiți industria dumneavoastră?"
        ui["customIndustryPlaceholder"] = "Descrieți activitatea afacerii..."
        ui["suggestionsTitle"] = "Capacități sugerate pentru această industrie:"
        ui["suggestionsDisclaimer"] = "Aceste sugestii ilustrează capacitățile IA. Integrările avansate necesită module active (CRM, Retail, Programări)."
        ui["crmRequired"] = "Modulul CRM este necesar"
        ui["crmActive"] = "Modulul CRM este activ"
        ui["retailRequired"] = "Modulul Retail este necesar"
        ui["retailActive"] = "Modulul Retail este activ"
        ui["generalQa"] = "Inclus standard (FAQ și Recepție)"
        ui["noIndustrySelected"] = "Niciun sector selectat. Alegeți cel puțin o industrie."
        ui["primarySector"] = "Sector principal"
        ui["selectedCount"] = "selectate"
    elif lang == "nl":
        ui["sectionTitle"] = "EEN AI OP MAAT VOOR ELKE SECTOR"
        ui["sectionSubtitle"] = "Natuurlijke gesprekken, geïntegreerde bedrijfsprocessen en een persoonlijke klantervaring in elke sector."
        ui["searchPlaceholder"] = "Zoek een sector..."
        ui["expandButton"] = "Meer sectoren bekijken"
        ui["collapseButton"] = "Minder weergeven"
        ui["customIndustryPrompt"] = "Staat uw sector er niet tussen?"
        ui["customIndustryPlaceholder"] = "Beschrijf uw bedrijfsactiviteit..."
        ui["suggestionsTitle"] = "Aanbevolen functies voor deze sector:"
        ui["suggestionsDisclaimer"] = "Deze suggesties tonen de AI-mogelijkheden. Geavanceerde integraties vereisen actieve modules (CRM, Retail, Afspraken)."
        ui["crmRequired"] = "CRM-module vereist"
        ui["crmActive"] = "CRM-module actief"
        ui["retailRequired"] = "Retail-module vereist"
        ui["retailActive"] = "Retail-module actief"
        ui["generalQa"] = "Standaard inbegrepen (FAQ en Receptie)"
        ui["noIndustrySelected"] = "Geen sector geselecteerd. Kies ten minste één sector."
        ui["primarySector"] = "Primaire sector"
        ui["selectedCount"] = "geselecteerd"
    elif lang == "pl":
        ui["sectionTitle"] = "SZTUCZNA INTELIGENCJA DOPASOWANA DO KAŻDEJ BRANŻY"
        ui["sectionSubtitle"] = "Naturalne rozmowy, zintegrowane procesy biznesowe i spersonalizowana obsługa klienta w każdej branży."
        ui["searchPlaceholder"] = "Szukaj branży..."
        ui["expandButton"] = "Zobacz więcej branż"
        ui["collapseButton"] = "Pokaż mniej"
        ui["customIndustryPrompt"] = "Nie widzisz swojej branży?"
        ui["customIndustryPlaceholder"] = "Opisz profil działalności..."
        ui["suggestionsTitle"] = "Sugerowane możliwości dla tej branży:"
        ui["suggestionsDisclaimer"] = "Sugestie te ilustrują możliwości AI. Zaawansowane integracje wymagają aktywnych modułów (CRM, Retail, Terminarz)."
        ui["crmRequired"] = "Wymagany moduł CRM"
        ui["crmActive"] = "Moduł CRM aktywny"
        ui["retailRequired"] = "Wymagany moduł Retail"
        ui["retailActive"] = "Moduł Retail aktywny"
        ui["generalQa"] = "W pakiecie standardowym (FAQ i Recepcja)"
        ui["noIndustrySelected"] = "Nie wybrano branży. Wybierz co najmniej jedną."
        ui["primarySector"] = "Główny sektor"
        ui["selectedCount"] = "wybrano"

    return ui

# Localized description and capabilities generator
def get_localized_desc_and_caps(ind, loc):
    # French
    if loc in ("fr", "fr-FR"):
        return ind["descFr"], ind["capsFr"]
    # English
    if loc in ("en", "en-GB"):
        return ind["descEn"], ind["capsEn"]

    lang = loc.split("-")[0]
    name = INDUSTRY_NAMES.get(ind["id"], {}).get(loc) or INDUSTRY_NAMES.get(ind["id"], {}).get(lang) or ind["nameEn"]

    desc_template = {
        "es": f"Recepción telefónica especializada, flujos adaptados y experiencia personalizada para {name}.",
        "pt": f"Atendimento telefônico inteligente, fluxos integrados e respostas especializadas para {name}.",
        "de": f"Intelligente Telefonzentrale, branchenspezifische Abläufe und maßgeschneiderte Dialoge für {name}.",
        "it": f"Accoglienza telefonica intelligente, flussi dedicati ed esperienza su misura per {name}.",
        "nl": f"Slimme telefonische ontvangst, geïntegreerde processen en advies op maat voor {name}.",
        "pl": f"Inteligentna recepcja telefoniczna, dostosowane procesy i obsługa klienta dla {name}.",
        "ro": f"Recepție telefonică inteligentă, fluxuri adaptate și experiență dedicată pentru {name}.",
        "ru": f"Интеллектуальный голосовой прием звонков, отраслевые сценарии и консультации для {name}.",
        "uk": f"Інтелектуальний голосовий прийом дзвінків, галузеві сценарії та консультації для {name}.",
        "el": f"Έξυπνη τηλεφωνική υποδοχή, εξειδικευμένες ροές εργασίας και εξατομικευμένη εξυπηρέτηση για {name}.",
        "sv": f"Smart telefonväxel, anpassade arbetsflöden och skräddarsydd kundupplevelse för {name}.",
        "tr": f"Akıllı telefon karşılama, sektöre özel iş akışları ve {name} için kişiselleştirilmiş deneyim.",
        "cs": f"Chytrá telefonní recepce, integrované procesy a přizpůsobený servis pro {name}.",
        "ar": f"استقبال هاتفي ذكي ومحادثات مخصصة لقطاع {name}.",
        "ar-EG": f"استقبال هاتفي ذكي ومحادثات مخصصة لقطاع {name}.",
        "he": f"מענה קולי חכם, תהליכים מותאמים ושירות אישי עבור {name}.",
        "fa": f"پاسخگویی تلفنی هوشمند و جریان‌های مکالمه اختصاصی برای {name}.",
        "zh": f"专为{name}定制的智能语音接待、业务流程整合与专属客户体验。",
        "ja": f"{name}に特化した高精度AI音声受付、統合された業務ワークフロー、パーソナライズされた顧客対応。",
        "ko": f"{name} 분야를 위한 맞춤형 AI 전화 접수, 업무 프로세스 연동 및 전문 고객 경험.",
        "vi": f"Lễ tân giọng nói thông minh, quy trình tích hợp và trải nghiệm khách hàng tối ưu cho {name}.",
        "th": f"ระบบตอบรับโทรศัพท์อัจฉริยะและขั้นตอนการทำงานที่ออกแบบเฉพาะสำหรับ {name}.",
        "id": f"Resepsionis suara cerdas, alur kerja terintegrasi, dan layanan pelanggan khusus untuk {name}.",
        "ms": f"Penyambut tetamu suara pintar dan aliran kerja khusus untuk sektor {name}.",
        "tl": f"Matalinong pagtanggap sa telepono at pinasadyang serbisyo para sa {name}.",
        "hi": f"{name} के लिए स्मार्ट वॉयस रिसेप्शन और अनुकूलित व्यावसायिक प्रक्रियाएं।",
        "bn": f"{name} এর জন্য স্মার্ট ভয়েস রিসেপশন এবং কাস্টমাইজড গ্রাহক সেবা।",
        "ur": f"{name} کے لیے سمارٹ صوتی استقبالیہ اور موافق کاروباری عمل۔",
        "ta": f"{name} துறைகளுக்கான அறிவார்ந்த குரல் வரவேற்பு மற்றும் வணிக சேவை.",
        "pa": f"{name} ਖੇਤਰ ਲਈ ਸਮਾਰਟ ਵੌਇਸ ਰਿਸੈਪਸ਼ਨ ਅਤੇ ਕਸਟਮ ਕਾਲਰ ਅਨੁਭਵ।",
        "ne": f"{name} क्षेत्रका लागि स्मार्ट भ्वाइस रिसेप्शन र व्यावसायिक सेवा।",
        "sw": f"Mapokezi ya simu ya akili bandia na michakato maalum kwa sekta ya {name}.",
        "am": f"ለ{name} የተዘጋጀ ብልህ የስልክ መቀበያ እና የደንበኛ አገልግሎት።",
        "af": f"Slim telefoniese ontvangs en pasgemaakte werkvloeie vir {name}.",
        "ha": f"Hanyar tarbar kira mai basira da aka tsara don bangaren {name}.",
        "my": f"{name} ကဏ္ဍအတွက် စမတ်အသံဖုန်းလက်ခံရေးနှင့် သီးသန့်ဝန်ဆောင်မှု။",
        "km": f"ការទទួលទូរស័ព្ទឆ្លាតវៃ និងលំហូរការងារសមស្របសម្រាប់ {name}។",
        "mn": f"{name} салбарт зориулсан ухаалаг дуут хүлээн авагч ба тусгай үйлчилгээ.",
        "ka": f"ინტელექტუალური ხმოვანი მიღება და მორგებული პროცესები {name} სექტორისთვის.",
        "hy": f"Խելացի ձայնային ընդունարան և հարմարեցված գործընթացներ {name} ոլորտի համար:"
    }
    desc = desc_template.get(loc) or desc_template.get(lang) or ind["descEn"]

    # Localize capabilities using 100% authentic native translations
    try:
        from scripts.industry_native_caps import INDUSTRY_NATIVE_CAPABILITIES
    except ImportError:
        try:
            from industry_native_caps import INDUSTRY_NATIVE_CAPABILITIES
        except ImportError:
            INDUSTRY_NATIVE_CAPABILITIES = {}

    ind_id = ind["id"]
    if ind_id in INDUSTRY_NATIVE_CAPABILITIES and lang in INDUSTRY_NATIVE_CAPABILITIES[ind_id]:
        return desc, INDUSTRY_NATIVE_CAPABILITIES[ind_id][lang]

    return desc, ind["capsEn"]

# Build catalogs for all 44 locales
catalogs_data = {}
for loc in CANONICAL_LOCALES:
    lang = loc.split("-")[0]
    
    # Categories
    loc_categories = {}
    for cat_id, cat_map in CATEGORIES.items():
        val = cat_map.get(loc) or cat_map.get(lang) or cat_map.get("en") or cat_map.get("fr")
        loc_categories[cat_id] = val
        
    # UI
    loc_ui = make_ui_strings(loc)
    
    # Industries
    loc_industries = {}
    for ind in raw_industries:
        ind_id = ind["id"]
        # Name
        name = INDUSTRY_NAMES.get(ind_id, {}).get(loc) or INDUSTRY_NAMES.get(ind_id, {}).get(lang) or (ind["nameFr"] if loc.startswith("fr") else ind["nameEn"])
        desc, caps = get_localized_desc_and_caps(ind, loc)
        loc_industries[ind_id] = {
            "name": name,
            "desc": desc,
            "category": ind["category"],
            "icon": ind["icon"],
            "suggestedCapabilities": caps
        }
        
    catalogs_data[loc] = {
        "categories": loc_categories,
        "ui": loc_ui,
        "industries": loc_industries
    }

# Save JSON file
out_json_path = "web/src/lib/i18n/voice-industry-catalogs.generated.json"
os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
with open(out_json_path, "w", encoding="utf-8") as f:
    json.dump(catalogs_data, f, ensure_ascii=False, indent=2)

print(f"Generated {out_json_path} with {len(catalogs_data)} locales.")

# Generate TypeScript wrapper
ts_content = """/* Generated automatically. Do not edit manually. */
import type { LocaleCode } from "./types";
import catalogs from "./voice-industry-catalogs.generated.json";

export interface LocalizedIndustry {
  name: string;
  desc: string;
  category: string;
  icon: string;
  suggestedCapabilities: string[];
}

export interface VoiceIndustryCatalog {
  categories: Record<string, string>;
  ui: {
    sectionTitle: string;
    sectionSubtitle: string;
    searchPlaceholder: string;
    expandButton: string;
    collapseButton: string;
    customIndustryPrompt: string;
    customIndustryPlaceholder: string;
    suggestionsTitle: string;
    suggestionsDisclaimer: string;
    crmRequired: string;
    crmActive: string;
    retailRequired: string;
    retailActive: string;
    generalQa: string;
    noIndustrySelected: string;
    primarySector: string;
    selectedCount: string;
  };
  industries: Record<string, LocalizedIndustry>;
}

export const VOICE_INDUSTRY_CATALOGS = catalogs as Record<LocaleCode, VoiceIndustryCatalog>;

export function getVoiceIndustryCatalog(locale: LocaleCode | string): VoiceIndustryCatalog {
  return (VOICE_INDUSTRY_CATALOGS as Record<string, VoiceIndustryCatalog>)[locale] ?? VOICE_INDUSTRY_CATALOGS.fr;
}

export function getLocalizedCategory(categoryId: string, locale: LocaleCode | string): string {
  const cat = getVoiceIndustryCatalog(locale);
  return cat.categories[categoryId] ?? categoryId;
}

export function getLocalizedIndustry(industryId: string, locale: LocaleCode | string): LocalizedIndustry | null {
  const cat = getVoiceIndustryCatalog(locale);
  return cat.industries[industryId] ?? null;
}

export function getVoiceIndustryUi(locale: LocaleCode | string) {
  return getVoiceIndustryCatalog(locale).ui;
}
"""

out_ts_path = "web/src/lib/i18n/voice-industry-copy.ts"
with open(out_ts_path, "w", encoding="utf-8") as f:
    f.write(ts_content)

print(f"Generated {out_ts_path}.")
