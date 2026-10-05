import type { LocaleCode } from "./types";

export interface RetailAnomalyCopy {
  none: string;
  explanation: string;
  expectedRange: string;
  observed: string;
  difference: string;
}

export const RETAIL_ANOMALY_COPY: Record<LocaleCode, RetailAnomalyCopy> = {
  en: { none: "No anomalies were detected for this period.", explanation: "Observed stock is outside the expected range for the selected source.", expectedRange: "Expected range", observed: "Observed", difference: "Difference" },
  "en-GB": { none: "No anomalies were detected for this period.", explanation: "Observed stock is outside the expected range for the selected source.", expectedRange: "Expected range", observed: "Observed", difference: "Difference" },
  fr: { none: "Aucune anomalie détectée pour cette période.", explanation: "Le stock observé sort de la plage attendue pour la source sélectionnée.", expectedRange: "Plage attendue", observed: "Valeur observée", difference: "Écart" },
  "fr-FR": { none: "Aucune anomalie détectée pour cette période.", explanation: "Le stock observé sort de la plage attendue pour la source sélectionnée.", expectedRange: "Plage attendue", observed: "Valeur observée", difference: "Écart" },
  es: { none: "No se detectaron anomalías en este período.", explanation: "El stock observado está fuera del rango esperado para la fuente seleccionada.", expectedRange: "Rango esperado", observed: "Valor observado", difference: "Diferencia" },
  pt: { none: "Nenhuma anomalia foi detectada neste período.", explanation: "O estoque observado está fora do intervalo esperado para a fonte selecionada.", expectedRange: "Intervalo esperado", observed: "Valor observado", difference: "Diferença" },
  ro: { none: "Nu au fost detectate anomalii în această perioadă.", explanation: "Stocul observat este în afara intervalului așteptat pentru sursa selectată.", expectedRange: "Interval așteptat", observed: "Valoare observată", difference: "Diferență" },
  de: { none: "Für diesen Zeitraum wurden keine Anomalien erkannt.", explanation: "Der beobachtete Bestand liegt außerhalb des erwarteten Bereichs der ausgewählten Quelle.", expectedRange: "Erwarteter Bereich", observed: "Beobachtet", difference: "Abweichung" },
  it: { none: "Nessuna anomalia rilevata per questo periodo.", explanation: "La scorta osservata è fuori dall'intervallo atteso per la fonte selezionata.", expectedRange: "Intervallo atteso", observed: "Valore osservato", difference: "Differenza" },
  nl: { none: "Geen afwijkingen gedetecteerd voor deze periode.", explanation: "De waargenomen voorraad valt buiten het verwachte bereik van de geselecteerde bron.", expectedRange: "Verwacht bereik", observed: "Waargenomen", difference: "Verschil" },
  pl: { none: "Nie wykryto anomalii w tym okresie.", explanation: "Zaobserwowany stan magazynowy wykracza poza oczekiwany zakres wybranego źródła.", expectedRange: "Oczekiwany zakres", observed: "Zaobserwowano", difference: "Różnica" },
  ru: { none: "За этот период аномалий не обнаружено.", explanation: "Наблюдаемый запас выходит за ожидаемый диапазон выбранного источника.", expectedRange: "Ожидаемый диапазон", observed: "Наблюдаемое значение", difference: "Отклонение" },
  uk: { none: "За цей період аномалій не виявлено.", explanation: "Спостережуваний запас виходить за очікуваний діапазон вибраного джерела.", expectedRange: "Очікуваний діапазон", observed: "Спостережуване значення", difference: "Відхилення" },
  el: { none: "Δεν εντοπίστηκαν ανωμαλίες για αυτήν την περίοδο.", explanation: "Το παρατηρούμενο απόθεμα βρίσκεται εκτός του αναμενόμενου εύρους της επιλεγμένης πηγής.", expectedRange: "Αναμενόμενο εύρος", observed: "Παρατηρήθηκε", difference: "Διαφορά" },
  sv: { none: "Inga avvikelser upptäcktes under perioden.", explanation: "Det observerade lagret ligger utanför det förväntade intervallet för den valda källan.", expectedRange: "Förväntat intervall", observed: "Observerat", difference: "Skillnad" },
  tr: { none: "Bu dönem için anomali tespit edilmedi.", explanation: "Gözlemlenen stok, seçilen kaynağın beklenen aralığının dışında.", expectedRange: "Beklenen aralık", observed: "Gözlemlenen", difference: "Fark" },
  cs: { none: "Pro toto období nebyly zjištěny žádné anomálie.", explanation: "Pozorovaná zásoba je mimo očekávaný rozsah vybraného zdroje.", expectedRange: "Očekávaný rozsah", observed: "Pozorováno", difference: "Rozdíl" },
  ar: { none: "لم يتم اكتشاف أي حالات شاذة خلال هذه الفترة.", explanation: "المخزون المرصود خارج النطاق المتوقع للمصدر المحدد.", expectedRange: "النطاق المتوقع", observed: "القيمة المرصودة", difference: "الفرق" },
  "ar-EG": { none: "لم يتم اكتشاف أي حالات شاذة خلال هذه الفترة.", explanation: "المخزون المرصود خارج النطاق المتوقع للمصدر المحدد.", expectedRange: "النطاق المتوقع", observed: "القيمة المرصودة", difference: "الفرق" },
  he: { none: "לא זוהו חריגות בתקופה זו.", explanation: "המלאי שנצפה נמצא מחוץ לטווח הצפוי של המקור שנבחר.", expectedRange: "טווח צפוי", observed: "ערך שנצפה", difference: "הפרש" },
  fa: { none: "در این بازه ناهنجاری‌ای شناسایی نشد.", explanation: "موجودی مشاهده‌شده خارج از محدوده مورد انتظار منبع انتخاب‌شده است.", expectedRange: "محدوده مورد انتظار", observed: "مقدار مشاهده‌شده", difference: "اختلاف" },
  ja: { none: "この期間に異常は検出されませんでした。", explanation: "観測された在庫が選択したソースの想定範囲を外れています。", expectedRange: "想定範囲", observed: "観測値", difference: "差分" },
  ko: { none: "이 기간에는 이상 징후가 감지되지 않았습니다.", explanation: "관측된 재고가 선택한 소스의 예상 범위를 벗어났습니다.", expectedRange: "예상 범위", observed: "관측값", difference: "차이" },
  zh: { none: "此期间未检测到异常。", explanation: "观测库存超出所选数据源的预期范围。", expectedRange: "预期范围", observed: "观测值", difference: "差值" },
  ka: { none: "ამ პერიოდში ანომალია არ გამოვლენილა.", explanation: "დაკვირვებული მარაგი არჩეული წყაროს მოსალოდნელ დიაპაზონს სცდება.", expectedRange: "მოსალოდნელი დიაპაზონი", observed: "დაკვირვებული მნიშვნელობა", difference: "სხვაობა" },
  hy: { none: "Այս ժամանակահատվածում շեղումներ չեն հայտնաբերվել։", explanation: "Դիտարկված պաշարը ընտրված աղբյուրի ակնկալվող միջակայքից դուրս է։", expectedRange: "Ակնկալվող միջակայք", observed: "Դիտարկված արժեք", difference: "Տարբերություն" },
  sw: { none: "Hakuna hitilafu zilizogunduliwa katika kipindi hiki.", explanation: "Hisa iliyozingatiwa iko nje ya kiwango kinachotarajiwa cha chanzo kilichochaguliwa.", expectedRange: "Kiwango kinachotarajiwa", observed: "Kilichozingatiwa", difference: "Tofauti" },
  am: { none: "በዚህ ጊዜ ምንም ያልተለመደ ሁኔታ አልተገኘም።", explanation: "የታየው ክምችት ከተመረጠው ምንጭ የሚጠበቀው ክልል ውጭ ነው።", expectedRange: "የሚጠበቅ ክልል", observed: "የታየ እሴት", difference: "ልዩነት" },
  af: { none: "Geen afwykings is vir hierdie tydperk opgespoor nie.", explanation: "Die waargenome voorraad val buite die verwagte omvang van die gekose bron.", expectedRange: "Verwagte omvang", observed: "Waargeneem", difference: "Verskil" },
  ha: { none: "Ba a gano wata matsala ba a wannan lokaci.", explanation: "Hajojin da aka lura sun wuce iyakar da ake tsammani daga tushen da aka zaɓa.", expectedRange: "Iyakar da ake tsammani", observed: "Abin da aka lura", difference: "Bambanci" },
  hi: { none: "इस अवधि के लिए कोई विसंगति नहीं मिली।", explanation: "देखा गया स्टॉक चुने गए स्रोत की अपेक्षित सीमा से बाहर है।", expectedRange: "अपेक्षित सीमा", observed: "देखा गया मान", difference: "अंतर" },
  bn: { none: "এই সময়ের জন্য কোনো অসংগতি শনাক্ত হয়নি।", explanation: "পর্যবেক্ষিত মজুত নির্বাচিত উৎসের প্রত্যাশিত সীমার বাইরে।", expectedRange: "প্রত্যাশিত সীমা", observed: "পর্যবেক্ষিত মান", difference: "পার্থক্য" },
  ur: { none: "اس مدت کے لیے کوئی بے قاعدگی نہیں ملی۔", explanation: "مشاہدہ شدہ اسٹاک منتخب ماخذ کی متوقع حد سے باہر ہے۔", expectedRange: "متوقع حد", observed: "مشاہدہ شدہ قدر", difference: "فرق" },
  ta: { none: "இந்தக் காலத்திற்கு முரண்பாடுகள் எதுவும் கண்டறியப்படவில்லை.", explanation: "கவனிக்கப்பட்ட இருப்பு தேர்ந்தெடுக்கப்பட்ட மூலத்தின் எதிர்பார்க்கப்பட்ட வரம்பிற்கு வெளியே உள்ளது.", expectedRange: "எதிர்பார்க்கப்பட்ட வரம்பு", observed: "கவனிக்கப்பட்ட மதிப்பு", difference: "வேறுபாடு" },
  pa: { none: "ਇਸ ਮਿਆਦ ਲਈ ਕੋਈ ਅਸੰਗਤੀ ਨਹੀਂ ਮਿਲੀ।", explanation: "ਦੇਖਿਆ ਗਿਆ ਸਟਾਕ ਚੁਣੇ ਸਰੋਤ ਦੀ ਉਮੀਦ ਕੀਤੀ ਹੱਦ ਤੋਂ ਬਾਹਰ ਹੈ।", expectedRange: "ਉਮੀਦ ਕੀਤੀ ਹੱਦ", observed: "ਦੇਖਿਆ ਮੁੱਲ", difference: "ਫ਼ਰਕ" },
  ne: { none: "यस अवधिका लागि कुनै असामान्यता भेटिएन।", explanation: "अवलोकन गरिएको मौज्दात चयन गरिएको स्रोतको अपेक्षित दायराभन्दा बाहिर छ।", expectedRange: "अपेक्षित दायरा", observed: "अवलोकन गरिएको मान", difference: "अन्तर" },
  vi: { none: "Không phát hiện bất thường trong giai đoạn này.", explanation: "Tồn kho quan sát được nằm ngoài phạm vi dự kiến của nguồn đã chọn.", expectedRange: "Phạm vi dự kiến", observed: "Giá trị quan sát", difference: "Chênh lệch" },
  th: { none: "ไม่พบความผิดปกติในช่วงเวลานี้", explanation: "สินค้าคงคลังที่สังเกตได้อยู่นอกช่วงที่คาดไว้ของแหล่งข้อมูลที่เลือก", expectedRange: "ช่วงที่คาดไว้", observed: "ค่าที่สังเกตได้", difference: "ความแตกต่าง" },
  id: { none: "Tidak ada anomali yang terdeteksi untuk periode ini.", explanation: "Stok yang diamati berada di luar rentang yang diharapkan dari sumber yang dipilih.", expectedRange: "Rentang yang diharapkan", observed: "Nilai teramati", difference: "Selisih" },
  ms: { none: "Tiada anomali dikesan untuk tempoh ini.", explanation: "Stok yang diperhatikan berada di luar julat jangkaan bagi sumber yang dipilih.", expectedRange: "Julat jangkaan", observed: "Nilai diperhatikan", difference: "Perbezaan" },
  tl: { none: "Walang natukoy na anomalya para sa panahong ito.", explanation: "Ang naobserbahang stock ay nasa labas ng inaasahang saklaw ng napiling source.", expectedRange: "Inaasahang saklaw", observed: "Naobserbahang halaga", difference: "Pagkakaiba" },
  my: { none: "ဤကာလအတွက် မူမမှန်မှု မတွေ့ရှိပါ။", explanation: "တွေ့ရှိထားသော လက်ကျန်သည် ရွေးချယ်ထားသော ရင်းမြစ်၏ မျှော်မှန်းအတိုင်းအတာပြင်ပတွင် ရှိသည်။", expectedRange: "မျှော်မှန်းအတိုင်းအတာ", observed: "တွေ့ရှိတန်ဖိုး", difference: "ကွာခြားချက်" },
  km: { none: "មិនបានរកឃើញភាពមិនប្រក្រតីសម្រាប់រយៈពេលនេះទេ។", explanation: "ស្តុកដែលបានសង្កេតឃើញនៅក្រៅជួរដែលរំពឹងទុករបស់ប្រភពដែលបានជ្រើស។", expectedRange: "ជួរដែលរំពឹងទុក", observed: "តម្លៃដែលបានសង្កេត", difference: "ភាពខុសគ្នា" },
  mn: { none: "Энэ хугацаанд хэвийн бус зүйл илрээгүй.", explanation: "Ажиглагдсан нөөц сонгосон эх сурвалжийн хүлээгдэж буй хязгаараас гадуур байна.", expectedRange: "Хүлээгдэж буй хязгаар", observed: "Ажиглагдсан утга", difference: "Зөрүү" },
};