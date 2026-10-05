import type { LocaleCode } from "./types";

export interface VoiceNumberCopy {
  country: string;
  region: string;
  locality: string;
  search: string;
  purchase: string;
  monthlyPrice: string;
  regulatoryRequirements: string;
}

export const VOICE_NUMBER_COPY: Record<LocaleCode, VoiceNumberCopy> = {
  en: { country: "Country code", region: "Region", locality: "City", search: "Search numbers", purchase: "Purchase number", monthlyPrice: "Monthly price", regulatoryRequirements: "Regulatory requirements" },
  "en-GB": { country: "Country code", region: "Region", locality: "City", search: "Search numbers", purchase: "Purchase number", monthlyPrice: "Monthly price", regulatoryRequirements: "Regulatory requirements" },
  fr: { country: "Code pays", region: "Région", locality: "Ville", search: "Rechercher des numéros", purchase: "Acheter le numéro", monthlyPrice: "Prix mensuel", regulatoryRequirements: "Exigences réglementaires" },
  "fr-FR": { country: "Code pays", region: "Région", locality: "Ville", search: "Rechercher des numéros", purchase: "Acheter le numéro", monthlyPrice: "Prix mensuel", regulatoryRequirements: "Exigences réglementaires" },
  es: { country: "Código de país", region: "Región", locality: "Ciudad", search: "Buscar números", purchase: "Comprar número", monthlyPrice: "Precio mensual", regulatoryRequirements: "Requisitos reglamentarios" },
  pt: { country: "Código do país", region: "Região", locality: "Cidade", search: "Pesquisar números", purchase: "Comprar número", monthlyPrice: "Preço mensal", regulatoryRequirements: "Requisitos regulamentares" },
  ro: { country: "Cod de țară", region: "Regiune", locality: "Oraș", search: "Caută numere", purchase: "Cumpără numărul", monthlyPrice: "Preț lunar", regulatoryRequirements: "Cerințe de reglementare" },
  de: { country: "Ländercode", region: "Region", locality: "Stadt", search: "Nummern suchen", purchase: "Nummer kaufen", monthlyPrice: "Monatlicher Preis", regulatoryRequirements: "Regulatorische Anforderungen" },
  it: { country: "Codice paese", region: "Regione", locality: "Città", search: "Cerca numeri", purchase: "Acquista numero", monthlyPrice: "Prezzo mensile", regulatoryRequirements: "Requisiti normativi" },
  nl: { country: "Landcode", region: "Regio", locality: "Stad", search: "Nummers zoeken", purchase: "Nummer kopen", monthlyPrice: "Maandprijs", regulatoryRequirements: "Wettelijke vereisten" },
  pl: { country: "Kod kraju", region: "Region", locality: "Miasto", search: "Szukaj numerów", purchase: "Kup numer", monthlyPrice: "Cena miesięczna", regulatoryRequirements: "Wymogi prawne" },
  ru: { country: "Код страны", region: "Регион", locality: "Город", search: "Найти номера", purchase: "Купить номер", monthlyPrice: "Цена в месяц", regulatoryRequirements: "Требования законодательства" },
  uk: { country: "Код країни", region: "Регіон", locality: "Місто", search: "Знайти номери", purchase: "Придбати номер", monthlyPrice: "Ціна на місяць", regulatoryRequirements: "Регуляторні вимоги" },
  el: { country: "Κωδικός χώρας", region: "Περιοχή", locality: "Πόλη", search: "Αναζήτηση αριθμών", purchase: "Αγορά αριθμού", monthlyPrice: "Μηνιαία τιμή", regulatoryRequirements: "Κανονιστικές απαιτήσεις" },
  sv: { country: "Landskod", region: "Region", locality: "Stad", search: "Sök nummer", purchase: "Köp nummer", monthlyPrice: "Månadspris", regulatoryRequirements: "Regulatoriska krav" },
  tr: { country: "Ülke kodu", region: "Bölge", locality: "Şehir", search: "Numara ara", purchase: "Numara satın al", monthlyPrice: "Aylık fiyat", regulatoryRequirements: "Düzenleyici gereklilikler" },
  cs: { country: "Kód země", region: "Region", locality: "Město", search: "Vyhledat čísla", purchase: "Koupit číslo", monthlyPrice: "Měsíční cena", regulatoryRequirements: "Regulační požadavky" },
  ar: { country: "رمز الدولة", region: "المنطقة", locality: "المدينة", search: "البحث عن أرقام", purchase: "شراء الرقم", monthlyPrice: "السعر الشهري", regulatoryRequirements: "المتطلبات التنظيمية" },
  "ar-EG": { country: "رمز الدولة", region: "المنطقة", locality: "المدينة", search: "البحث عن أرقام", purchase: "شراء الرقم", monthlyPrice: "السعر الشهري", regulatoryRequirements: "المتطلبات التنظيمية" },
  he: { country: "קידומת מדינה", region: "אזור", locality: "עיר", search: "חיפוש מספרים", purchase: "רכישת מספר", monthlyPrice: "מחיר חודשי", regulatoryRequirements: "דרישות רגולטוריות" },
  fa: { country: "کد کشور", region: "منطقه", locality: "شهر", search: "جستجوی شماره‌ها", purchase: "خرید شماره", monthlyPrice: "قیمت ماهانه", regulatoryRequirements: "الزامات قانونی" },
  ja: { country: "国コード", region: "地域", locality: "市区町村", search: "番号を検索", purchase: "番号を購入", monthlyPrice: "月額料金", regulatoryRequirements: "規制要件" },
  ko: { country: "국가 코드", region: "지역", locality: "도시", search: "번호 검색", purchase: "번호 구매", monthlyPrice: "월 요금", regulatoryRequirements: "규제 요건" },
  zh: { country: "国家代码", region: "地区", locality: "城市", search: "搜索号码", purchase: "购买号码", monthlyPrice: "月费", regulatoryRequirements: "监管要求" },
  ka: { country: "ქვეყნის კოდი", region: "რეგიონი", locality: "ქალაქი", search: "ნომრების ძიება", purchase: "ნომრის შეძენა", monthlyPrice: "თვიური ფასი", regulatoryRequirements: "მარეგულირებელი მოთხოვნები" },
  hy: { country: "Երկրի կոդ", region: "Մարզ", locality: "Քաղաք", search: "Որոնել համարներ", purchase: "Գնել համար", monthlyPrice: "Ամսական գին", regulatoryRequirements: "Կարգավորող պահանջներ" },
  sw: { country: "Msimbo wa nchi", region: "Eneo", locality: "Jiji", search: "Tafuta nambari", purchase: "Nunua nambari", monthlyPrice: "Bei ya kila mwezi", regulatoryRequirements: "Mahitaji ya udhibiti" },
  am: { country: "የአገር ኮድ", region: "ክልል", locality: "ከተማ", search: "ቁጥሮችን ፈልግ", purchase: "ቁጥር ግዛ", monthlyPrice: "ወርሃዊ ዋጋ", regulatoryRequirements: "የቁጥጥር መስፈርቶች" },
  af: { country: "Landkode", region: "Streek", locality: "Stad", search: "Soek nommers", purchase: "Koop nommer", monthlyPrice: "Maandelikse prys", regulatoryRequirements: "Regulatoriese vereistes" },
  ha: { country: "Lambar ƙasa", region: "Yanki", locality: "Birni", search: "Nemo lambobi", purchase: "Sayi lamba", monthlyPrice: "Farashin wata-wata", regulatoryRequirements: "Bukatun ƙa'ida" },
  hi: { country: "देश कोड", region: "क्षेत्र", locality: "शहर", search: "नंबर खोजें", purchase: "नंबर खरीदें", monthlyPrice: "मासिक मूल्य", regulatoryRequirements: "नियामक आवश्यकताएँ" },
  bn: { country: "দেশের কোড", region: "অঞ্চল", locality: "শহর", search: "নম্বর খুঁজুন", purchase: "নম্বর কিনুন", monthlyPrice: "মাসিক মূল্য", regulatoryRequirements: "নিয়ন্ত্রক শর্ত" },
  ur: { country: "ملک کا کوڈ", region: "علاقہ", locality: "شہر", search: "نمبر تلاش کریں", purchase: "نمبر خریدیں", monthlyPrice: "ماہانہ قیمت", regulatoryRequirements: "قانونی تقاضے" },
  ta: { country: "நாட்டு குறியீடு", region: "பகுதி", locality: "நகரம்", search: "எண்களைத் தேடு", purchase: "எண்ணை வாங்கு", monthlyPrice: "மாத விலை", regulatoryRequirements: "ஒழுங்குமுறைத் தேவைகள்" },
  pa: { country: "ਦੇਸ਼ ਕੋਡ", region: "ਖੇਤਰ", locality: "ਸ਼ਹਿਰ", search: "ਨੰਬਰ ਖੋਜੋ", purchase: "ਨੰਬਰ ਖਰੀਦੋ", monthlyPrice: "ਮਹੀਨਾਵਾਰ ਕੀਮਤ", regulatoryRequirements: "ਨਿਯਮਕ ਲੋੜਾਂ" },
  ne: { country: "देशको कोड", region: "क्षेत्र", locality: "सहर", search: "नम्बर खोज्नुहोस्", purchase: "नम्बर किन्नुहोस्", monthlyPrice: "मासिक मूल्य", regulatoryRequirements: "नियामकीय आवश्यकताहरू" },
  vi: { country: "Mã quốc gia", region: "Khu vực", locality: "Thành phố", search: "Tìm số", purchase: "Mua số", monthlyPrice: "Giá hàng tháng", regulatoryRequirements: "Yêu cầu pháp lý" },
  th: { country: "รหัสประเทศ", region: "ภูมิภาค", locality: "เมือง", search: "ค้นหาหมายเลข", purchase: "ซื้อหมายเลข", monthlyPrice: "ราคารายเดือน", regulatoryRequirements: "ข้อกำหนดด้านกฎระเบียบ" },
  id: { country: "Kode negara", region: "Wilayah", locality: "Kota", search: "Cari nomor", purchase: "Beli nomor", monthlyPrice: "Harga bulanan", regulatoryRequirements: "Persyaratan regulasi" },
  ms: { country: "Kod negara", region: "Wilayah", locality: "Bandar", search: "Cari nombor", purchase: "Beli nombor", monthlyPrice: "Harga bulanan", regulatoryRequirements: "Keperluan peraturan" },
  tl: { country: "Code ng bansa", region: "Rehiyon", locality: "Lungsod", search: "Maghanap ng numero", purchase: "Bumili ng numero", monthlyPrice: "Buwanang presyo", regulatoryRequirements: "Mga kinakailangan sa regulasyon" },
  my: { country: "နိုင်ငံကုဒ်", region: "ဒေသ", locality: "မြို့", search: "နံပါတ်များရှာရန်", purchase: "နံပါတ်ဝယ်ရန်", monthlyPrice: "လစဉ်ဈေးနှုန်း", regulatoryRequirements: "စည်းမျဉ်းလိုအပ်ချက်များ" },
  km: { country: "កូដប្រទេស", region: "តំបន់", locality: "ទីក្រុង", search: "ស្វែងរកលេខ", purchase: "ទិញលេខ", monthlyPrice: "តម្លៃប្រចាំខែ", regulatoryRequirements: "តម្រូវការបទប្បញ្ញត្តិ" },
  mn: { country: "Улсын код", region: "Бүс нутаг", locality: "Хот", search: "Дугаар хайх", purchase: "Дугаар худалдаж авах", monthlyPrice: "Сарын үнэ", regulatoryRequirements: "Зохицуулалтын шаардлага" },
};