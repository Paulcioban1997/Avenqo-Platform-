# coding: utf-8
"""
Native suggested capabilities for Middle Eastern languages:
- tr (Turkish)
- he (Hebrew)
- fa (Persian)
"""

CAPS_MIDDLE_EAST = {
    "auto": {
        "tr": ["Şasi numarası (VIN) veya modele göre parça uyumluluk kontrolü", "Stok durumu ve güncel fiyat bilgisi", "Periyodik bakım ve servis onarım randevusu", "Araç servis ve atölye aşama takibi"],
        "he": ["בדיקת תאימות חלפים לפי מספר שלדה (VIN) או דגם", "זמינות מלאי ומחירון מנחה", "תיאום תורים לטיפולים ותיקוני מוסך", "מעקב אחר סטטוס התקדמות הרכב במוסך"],
        "fa": ["بررسی سازگاری قطعات بر اساس شماره شاسی (VIN) یا مدل", "موجودی انبار و استعلام قیمت‌های مصوب", "رزرو نوبت تعمیر و سرویس‌های دوره‌ای در تعمیرگاه", "پیگیری وضعیت پیشرفت کار خودرو در تعمیرگاه"],
    },
    "medical": {
        "tr": ["Muayene randevusu alma ve randevu güncelleme", "İdari prosedürler ve gerekli belgeler hakkında bilgi", "Hekim çalışma saatleri ve online randevu seçenekleri", "Yetkili sağlık personeline öncelikli aktarım"],
        "he": ["קביעה ועדכון של תורים רפואיים", "מידע מנהלי והנחיות לגבי מסמכים דרושים", "לוחות זמנים של רופאים ואפשרויות ייעוץ מרחוק", "העברה בעדיפות לצוות אחיות מוסמך"],
        "fa": ["رزرو و تغییر نوبت‌های پزشکی و درمانی", "راهنمایی اداری و مدارک و پرونده‌های مورد نیاز", "برنامه حضور پزشکان و نوبت‌دهی مشاوره آنلاین", "انتقال اولویت‌دار تماس به کادر پرستاری مجرب"],
    },
    "restaurant": {
        "tr": ["Anında SMS onaylı masa rezervasyonu", "Günün menüsü ve özel lezzetlerin tanıtımı", "Doğrulanmış içeriklerle alerjen bilgilendirmesi", "Paket servis siparişleri ve özel grup etkinlikleri"],
        "he": ["הזמנת שולחנות עם אישור מיידי ב-SMS", "מנות היום והצגת התפריט העדכני", "מענה בנושא אלרגנים על בסיס נתונים מאומתים", "הזמנות לקחת ואירועים לקבוצות פרטיות"],
        "fa": ["رزرو میز به همراه تایید فوری پیامکی", "معرفی غذاهای روز و ارائه منوی جاری رستوران", "پاسخ به سوالات حساسیت غذایی بر اساس ترکیبات دقیق", "سفارش‌های بیرون‌بر و رزرو مراسم و گروه‌ها"],
    },
    "retail": {
        "tr": ["Mağaza stoklarının anlık olarak sorgulanması", "Kargo takip numarası ve teslimat durumu", "İade şartları ve şube çalışma saatleri", "Uyumlu ürün ve tamamlayıcı aksesuar önerileri"],
        "he": ["בדיקת מלאי בסניפים בזמן אמת", "מעקב משלוחים וסטטוס חבילות", "מדיניות החזרות ושעות פעילות הסניפים", "הצעות לפריטים משלימים ומוצרים מתאימים"],
        "fa": ["استعلام موجودی کالا در شعب به صورت لحظه‌ای", "پیگیری مرسولات پستی و وضعیت ارسال سفارش", "شرایط بازگشت کالا و ساعات کاری شعب", "پیشنهاد محصولات مکمل و متناسب با خرید"],
    },
    "transport": {
        "tr": ["Konşimento (BOL) numarasıyla yük takibi", "Tahmini varış zamanı (ETA) ve rampa saatleri", "PIN ile doğrulanan sürücülere özel destek", "Depo çalışma saatleri ve giriş güvenlik kuralları"],
        "he": ["מעקב אחר מטענים לפי שטר מטען (BOL)", "זמן הגעה משוער (ETA) וחלונות זמן ברציף", "תמיכה והנחיות לנהגים מאומתים בקוד PIN", "שעות פעילות מחסנים ונוהלי כניסה בשער"],
        "fa": ["رهگیری بار بر اساس شماره بارنامه (BOL)", "زمان تخمینی رسیدن بار (ETA) و نوبت‌دهی سکوی تخلیه", "پشتیبانی رانندگان احراز هویت شده با کد PIN", "ساعات کاری انبارها و ضوابط تردد گیت ورودی"],
    },
    "real_estate": {
        "tr": ["Satılık ve kiralık portföy detayları", "Müşteri arama kriterleri ve bütçe analizi", "Yetkili gayrimenkul danışmanlarıyla randevu", "Ön ekspertiz ve piyasa değeri talepleri"],
        "he": ["מידע על נכסים למכירה או להשכרה", "בירור קריטריונים ותקציב של רוכשים ושוכרים", "תיאום סיורים בנכס עם סוכנים מורשים", "בקשה להערכת שווי שוק ראשונית לנכס"],
        "fa": ["اطلاعات املاک فروشی و رهن و اجاره", "بررسی معیارهای جستجو و بودجه متقاضیان", "هماهنگی بازدید حضوری ملک با مشاوران مجاز", "درخواست ارزیابی اولیه و کارشناسی قیمت روز"],
    },
    "hospitality": {
        "tr": ["Oda rezervasyonu ve konaklama tarihi güncelleme", "Giriş/çıkış kuralları ve otopark bilgisi", "Konsiyerj desteği ve yerel çevre tavsiyeleri", "Oda servisi ve ek hizmet talepleri"],
        "he": ["הזמנת חדרים ושינוי מועדי שהייה", "הנחיות צ'ק-אין וצ'ק-אאוט ומידע על חניה", "שירותי קונסיירז' והמלצות על אטרקציות מקומיות", "בקשות לשירות חדרים ומענה לצרכי אורחים"],
        "fa": ["رزرو اتاق و تغییر تاریخ‌های اقامت", "راهنمای پذیرش و خروج و مشخصات پارکینگ", "خدمات راهنمای مهمان و معرفی مراکز دیدنی اطراف", "درخواست سرویس اتاق و خدمات رفاهی اقامتی"],
    },
    "beauty": {
        "tr": ["Güzellik, kuaför ve masaj randevuları", "İşlem fiyat listesi ve bakım paketleri", "Otomatik randevu hatırlatma ve erteleme", "İşlem öncesi bakım ve hazırlık yönergeleri"],
        "he": ["תיאום תורים לספא, מספרות וטיפולי עיסוי", "מחירון טיפולים וחבילות מיוחדות", "תזכורות תורים אוטומטיות ואפשרויות לשינוי מועד", "הנחיות הכנה מקצועיות לקראת טיפול"],
        "fa": ["رزرو نوبت سالن زیبایی، آرایشگاه و ماساژ", "تعرفه خدمات و پکیج‌های تخفیفی مراقبت پوست و مو", "یادآوری خودکار نوبت‌ها و امکان جابجایی زمان", "توصیه‌های بهداشتی و آمادگی قبل از انجام خدمات"],
    },
    "construction": {
        "tr": ["İnşaat ve tadilat teklif taleplerinin alınması", "Tesisat, elektrik ve çatı acil durum çağrıları", "Yerinde keşif ve metraj randevusu", "Yetkili alt yüklenici ve usta yönlendirmesi"],
        "he": ["איסוף דרישות להצעות מחיר לשיפוץ או בנייה", "קריאות חירום לאינסטלציה, חשמל או גגות", "תיאום סיור מדידה והערכה בשטח", "תיאום מול קבלני משנה מורשים"],
        "fa": ["ثبت درخواست استعلام قیمت بازسازی و ساخت‌وساز", "اعلام فوریت‌های تاسیسات لوله‌کشی، برق یا سقف", "رزرو بازدید و کارشناسی در محل پروژه", "هماهنگی و تخصیص پیمانکاران جزء مجاز"],
    },
    "finance": {
        "tr": ["Finansal danışmanla görüşme planlama", "Şube konumları ve vezne çalışma saatleri", "Güvenli ön kredi uygunluk değerlendirmesi", "Varlık yönetimi ve yatırım birimlerine yönlendirme"],
        "he": ["קביעת פגישה עם יועץ פיננסי", "איתור סניפים ושעות קבלת קהל", "בדיקת זכאות ראשונית ומאובטחת להלוואות", "ניתוב למחלקות ניהול עושר והשקעות"],
        "fa": ["هماهنگی جلسه با مشاوران امور مالی و سرمایه‌گذاری", "نشانی شعب و ساعات کاری باجه‌های خدمات بانکی", "ارزیابی اولیه و ایمن شرایط درخواست وام", "اتصال به بخش‌های مدیریت دارایی و ثروت"],
    },
    "insurance": {
        "tr": ["İlk hasar ihbarı ve dosya açma işlemleri", "Tazminat dosya takip ve sonuç sorgulama", "Poliçe teminat kapsamı ve muafiyet detayları", "Yol yardım, çekici ve acil hasar desteği"],
        "he": ["פתיחת תביעת ביטוח ראשונית", "מעקב אחר סטטוס הטיפול בתביעה", "הסבר על היקף הכיסוי בפוליסה וגובה ההשתתפות העצמית", "סיוע חירום בדרכים ופינוי תאונות"],
        "fa": ["ثبت اولیه و تشکیل پرونده اعلام خسارت بیمه", "پیگیری وضعیت پرداخت و روند رسیدگی به خسارت", "توضیح پوشش‌های بیمه‌نامه و میزان فرانشیز", "امداد خودرو و پشتیبانی حوادث اضطراری"],
    },
    "legal": {
        "tr": ["Avukatla ön görüşme ve danışmanlık randevusu", "Dava uzmanlık alanı ayrımı (ceza, iş, ticaret)", "Danışmanlık ücretleri ve vekalet süreçleri", "Zamanaşımı süreleri ve gerekli delil listesi"],
        "he": ["תיאום פגישת ייעוץ משפטי ראשונית", "סיווג תחום התיק (אזרחי, פלילי, דיני עבודה)", "מידע על שכר טרחה ותהליך ייפוי כוח", "בדיקת מועדי התיישנות ורשימת מסמכים וראיות"],
        "fa": ["رزرو نوبت مشاوره حقوقی اولیه با وکیل پایه یک", "دسته‌بندی موضوع پرونده (حقوقی، کیفری، خانواده، کار)", "هزینه‌های حق‌الوکاله و مراحل عقد قرارداد وکالت", "بررسی مواعد قانونی و چک‌لیست مدارک اثبات دعوی"],
    },
    "education": {
        "tr": ["Eğitim programları, dönem takvimi ve ders saatleri", "Ön kayıt başvurusu ve kabul şartları kontrolü", "Öğrenim ücretleri, burslar ve taksit imkanları", "Akademik danışmanla bire bir görüşme randevusu"],
        "he": ["מידע על תוכניות לימוד, מועדי סמסטרים ומערכת שעות", "רישום מקוון ובדיקת תנאי קבלה", "גובה שכר לימוד, מלגות ואפשרויות פריסה", "תיאום פגישה אישית עם יועץ לימודים"],
        "fa": ["معرفی دوره‌های آموزشی، تقویم ترمی و سرفصل دروس", "ثبت‌نام آنلاین و بررسی اولیه مدارک پذیرش", "شهریه دوره‌ها، بورسیه‌ها و شرایط پرداخت اقساطی", "رزرو وقت مشاوره فردی با اساتید و مشاوران تحصیلی"],
    },
    "hr_recruitment": {
        "tr": ["Açık pozisyon kriterleri ve görev tanımları", "Gelen özgeçmişlerin ön elemesi", "İşe alım mülakatlarının takvimlendirilmesi", "İşe başlama evrakları ve oryantasyon bilgisi"],
        "he": ["דרישות תפקיד ותחומי אחריות למשרות פתוחות", "סינון ראשוני של קורות חיים", "תיאום מועדי ראיונות עם המגייסים", "הנחיות לטפסי קליטה ותחילת עבודה"],
        "fa": ["شرایط احراز و شرح وظایف فرصت‌های شغلی فعال", "بررسی و غربالگری اولیه رزومه‌های ارسال‌شده", "زمان‌بندی و هماهنگی مصاحبه‌های استخدامی", "مدارک لازم جهت تشکیل پرونده و شروع به کار پرسنل"],
    },
    "it_services": {
        "tr": ["Teknik destek talebi oluşturma ve önceliklendirme", "Ağ ve yazılım sorunları için ilk teşhis", "Yerinde servis veya uzaktan destek randevusu", "Bulut servis durumu ve bakım duyuruları"],
        "he": ["פתיחת קריאות שירות ותיעדוף תקלות IT", "אבחון ראשוני לתקלות רשת ותוכנה", "תיאום ביקור טכנאי בשטח או תמיכה מרחוק", "בדיקת סטטוס שרתי ענן והודעות השבתה"],
        "fa": ["ثبت تیکت پشتیبانی فنی و اولویت‌بندی اشکالات نرم‌افزاری", "عیب‌یابی اولیه قطعی شبکه و خطاهای سیستمی", "هماهنگی حضور تکنسین در محل یا اتصال از راه دور", "اطلاع‌رسانی وضعیت سرورهای ابری و نگهداری دوره‌ای"],
    },
    "manufacturing": {
        "tr": ["Sanayi makineleri teknik özellikleri ve kapasiteleri", "Üretim termin süreleri ve sevkiyat takvimi", "Yedek parça siparişi ve teknik çizim temini", "Kalite sertifikasyonları ve test standartları"],
        "he": ["מפרטים טכניים של ציוד ומכונות תעשייה", "לוחות זמנים לייצור ומועדי אספקת משלוחים", "הזמנת חלקי חילוף ושרטוטים הנדסיים", "תקני בקרת איכות ואישורי מעבדה"],
        "fa": ["مشخصات فنی و استانداردهای تجهیزات صنعتی", "مدت زمان دوره تولید و زمان‌بندی تحویل بار", "سفارش قطعات یدکی و نقشه‌های فنی تولید", "گواهینامه‌های استاندارد کیفیت و تاییدیه‌های بازرسی"],
    },
    "agriculture": {
        "tr": ["Tohum, gübre ve zirai ilaç stok durumu", "Toptan mahsul alımı ve güncel borsa fiyatları", "Ziraat mühendisi danışmanlığı ve teknik destek", "Hasat planlaması ve soğuk zincir lojistiği"],
        "he": ["בדיקת מלאי זרעים, דשנים וחומרי הדברה", "רכש סיטונאי של תוצרת חקלאית ומחירי שוק עדכניים", "ייעוץ אגרונומי וליווי מקצועי", "תכנון עונות קטיף ולוגיסטיקת שרשרת קירור"],
        "fa": ["موجودی بذر، کودهای شیمیایی و سموم دفع آفات", "خرید عمده محصولات کشاورزی و قیمت روز بازار", "مشاوره با مهندسان کشاورزی و راهنمایی فنی کشت", "زمان‌بندی برداشت محصول و زنجیره سرمایش حمل بار"],
    },
    "wholesale": {
        "tr": ["Miktara göre kademeli toptan satış fiyatları", "Minimum sipariş tutarı (MOQ) ve teslim süresi", "Ticari kredi limiti ve kurumsal vade başvurusu", "Paletli sevkiyat ve konteyner nakliye takibi"],
        "he": ["מחירוני סיטונאות מדורגים לפי כמויות", "כמויות מינימום להזמנה (MOQ) וזמני אספקה", "בקשות לאשראי עסקי ותנאי תשלום שוטף פלוס", "מעקב אחר משלוחי משטחים ומכולות"],
        "fa": ["لیست قیمت‌های عمده‌فروشی پلکانی بر اساس تیراژ", "حداقل میزان سفارش (MOQ) و دوره تحویل بار", "ثبت درخواست اعتبار تجاری B2B و تسویه مدت‌دار", "رهگیری محموله‌های پالت و کانتینرهای باربری"],
    },
    "pharmacy": {
        "tr": ["Reçeteli ilaç hazırlık durumu ve teslim saati", "Reçetesiz ürünler ve vitamin stok kontrolü", "Eczacı kullanım talimatları ve etkileşim uyarısı", "Nöbetçi eczane bilgisi ve acil kurye teslimatı"],
        "he": ["בירור מוכנות תרופות מרשם לאיסוף", "זמינות מוצרי מדף, תוספי תזונה וויטמינים", "הנחיות רוקח לנטילה נכונה ומניעת התנגשויות", "שעות פעילות בתי מרקחת תורנים ומשלוח מהיר"],
        "fa": ["پیگیری آماده شدن نسخه و زمان تحویل دارو", "موجودی داروهای بدون نسخه و مکمل‌های تغذیه‌ای", "دستورات داروساز در مورد مصرف و تداخل دارویی", "ساعات کاری داروخانه شبانه‌روزی و پیک فوری"],
    },
    "veterinary": {
        "tr": ["Aşı ve genel sağlık kontrolü randevuları", "Evcil hayvan acil durum yönlendirmesi", "Kısırlaştırma, mikroçip ve parazit tedavisi", "Tıbbi geçmiş kaydı ve sorumlu veteriner hekim görüşmesi"],
        "he": ["תיאום תורים לחיסונים ובדיקות שגרתיות לחיות מחמד", "טיפול ומענה מיידי במצבי חירום ופציעות", "מידע על עיקור, סירוס, שבב וטיפולים מונעים", "שליפת תיק רפואי ושיחה עם הווטרינר המטפל"],
        "fa": ["رزرو نوبت واکسیناسیون و معاینات دوره‌ای حیوانات", "تریاژ و اقدامات اولیه در فوریت‌های حاد دامپزشکی", "مشاوره عقیم‌سازی، میکروچیپ و مراقبت‌های بهداشتی", "بررسی پرونده درمانی و هماهنگی با دامپزشک معالج"],
    },
    "consulting": {
        "tr": ["Yönetim danışmanlığı proje kapsamının belirlenmesi", "Kıdemli danışmanlarla keşif toplantısı planlama", "Sektörel vaka analizleri ve uzmanlık alanları", "Teklif talebi ve tanıtım sunumu temini"],
        "he": ["אפיון צרכים והגדרת יעדי פרויקט ייעוץ", "תיאום פגישת היכרות עם יועצים בכירים", "הצגת מקרי בוחן והתמחויות בענף", "בקשת הצעות מחיר ומצגות פתיחה"],
        "fa": ["تعیین اهداف و حوزه پروژه مشاوره مدیریت", "هماهنگی جلسه معارفه با مشاوران ارشد سازمانی", "ارائه نمونه پروژه‌ها و متدولوژی‌های اجرایی", "درخواست پیشنهاد همکاری (پروپوزال) و مستندات"],
    },
    "public_services": {
        "tr": ["Çöp toplama günleri ve geri dönüşüm merkezleri", "Bozuk yol, kaldırım ve aydınlatma arıza kaydı", "Belediye hizmet binası çalışma saatleri ve evraklar", "İlgili idari birimlere doğru yönlendirme"],
        "he": ["לוחות זמנים לפינוי אשפה ומרכזי מחזור", "דיווח על מפגעי דרך, בורות ותאורת רחוב", "שעות קבלת קהל בעירייה והנחיות להוצאת אישורים", "ניתוב מדויק למחלקות העירייה השונות"],
        "fa": ["زمان‌بندی جمع‌آوری زباله و ایستگاه‌های بازیافت", "ثبت گزارش خرابی آسفالت معابر و روشنایی شهری", "ساعات اداری شهرداری و مدارک صدور مجوزها", "هدایت مستقیم به ادارات و دوایر مرتبط شهری"],
    },
    "telecom": {
        "tr": ["Adrese göre fiber ve internet altyapı sorgulama", "Otomatik şebeke arıza tespiti ve kesinti durumu", "Kurulum ve teknik servis randevusu alma", "Tarife detayları, internet paketleri ve ek servisler"],
        "he": ["בדיקת היתכנות וכיסוי סיבים אופטיים לפי כתובת", "אבחון תקלות רשת אוטומטי וסטטוס שיבושים", "תיאום מועד להתקנה וביקור טכנאי", "מידע על חבילות גלישה, שדרוגים ותוספות"],
        "fa": ["بررسی پوشش فیبر نوری و اینترنت پرسرعت در آدرس", "تست خودکار و پایش قطعی و اختلالات شبکه", "رزرو نوبت نصب مودم و اعزام کارشناس فنی", "جزئیات بسته‌های اینترنت و طرح‌های مشترکین"],
    },
    "commercial_real_estate": {
        "tr": ["Kiralık ticari ofis ve mağaza alanları", "Ticari kira sözleşmesi şartları ve imar durumu", "Şirket yöneticileri için yerinde inceleme randevusu", "Bina teknik özellikleri (metrekare, rampa, otopark)"],
        "he": ["זמינות שטחי מסחר ומשרדים פנויים להשכרה", "תנאי חוזי שכירות מסחריים וייעודי קרקע", "תיאום סיורים בנכס להנהלת חברות", "מפרט טכני של המבנה (שטח, רמפות פריקה, חניה)"],
        "fa": ["واحدهای اداری و تجاری آماده رهن و اجاره", "شرایط قراردادهای اجاره تجاری و کاربری‌های مجاز", "تنظیم وقت بازدید اختصاصی برای مدیران شرکت‌ها", "مشخصات سازه‌ای (متراژ مفید، بارانداز، پارکینگ)"],
    },
    "property_management": {
        "tr": ["Sakinlerin bakım ve onarım taleplerinin kaydı", "Acil teknik arıza müdahalesi (su baskını, kombi arızası)", "Tadilat duyuruları ve su-elektrik kesinti takvimi", "Aidat ödemeleri ve ortak gider bilgilendirmesi"],
        "he": ["קליטת קריאות תחזוקה ותיקונים מדיירים", "מענה מהיר לתקלות דחופות (נזילות, כשל בהסקה)", "הודעות על עבודות שיפוץ וניתוקי מים", "הנחיות לתשלומי ועד בית ודמי ניהול"],
        "fa": ["ثبت درخواست‌های تعمیرات و تاسیسات ساکنان", "رسیدگی فوری به حوادث (ترکیدگی لوله، خرابی شوفاژ)", "اطلاع‌رسانی زمان‌بندی تعمیرات و قطعی آب و برق", "پرداخت شارژ ساختمان و هزینه‌های نگهداری مشاعات"],
    },
    "fitness_gym": {
        "tr": ["Grup ders programı ve ders kontenjan rezervasyonu", "Üyelik ücretleri, günlük girişler ve kampanya bilgisi", "Antrenör eşliğinde vücut analizi randevusu", "Tesis kuralları ve yoğun saatler tavsiyesi"],
        "he": ["לוח שיעורים קבוצתיים ושריון מקומות", "מחירי מנויים, כרטיסיות יומיות ומבצעים", "תיאום אימון היכרות והערכה עם מאמן אישי", "כללי שימוש במתקנים ושעות עומס"],
        "fa": ["برنامه کلاس‌های گروهی ورزشی و رزرو ظرفیت", "تعرفه عضویت، بلیت‌های تک‌جلسه‌ای و تخفیف‌ها", "رزرو وقت ارزیابی آمادگی جسمانی با مربی اختصاصی", "قوانین استفاده از تجهیزات باشگاه و ساعات اوج شلوغی"],
    },
    "events": {
        "tr": ["Etkinlik takvimi, sanatçı kadrosu ve bilet satışı", "Ulaşım güzergahları, otopark ve erişilebilirlik", "Katılımcı ve konuşmacı özel çağrı desteği", "VIP alanları ve kurumsal loca kiralama"],
        "he": ["לוח אירועים, רשימת אמנים ורכישת כרטיסים", "דרכי הגעה, חניה ונגישות", "שירות ותמיכה למציגים ומרצים", "שריון מתחמי VIP וחדרי אירוח עסקיים"],
        "fa": ["تقویم همایش‌ها، لیست سخنرانان و اطلاعات بلیت", "مسیرهای دسترسی، پارکینگ و امکانات رفاهی معلولان", "پشتیبانی تلفنی غرفه‌داران و سخنرانان رویداد", "رزرو جایگاه‌های تشریفات VIP و سوئیت‌های تجاری"],
    },
    "delivery_courier": {
        "tr": ["Kargo takip koduyla anlık gönderi sorgulama", "Teslimat adresi veya şubeden teslim değişikliği", "Kuryeye güvenli teslimat noktası talimatı", "Adreste bulunamayan paketler için yeniden dağıtım"],
        "he": ["מעקב משלוחים מהיר לפי מספר מעקב", "שינוי כתובת למסירה או העברה לנקודת איסוף", "הוראות מסירה במקום בטוח עבור השליח", "פתרון מקרים של אי-המצאות ותיאום מסירה חוזרת"],
        "fa": ["رهگیری لحظه‌ای مرسوله با کد پیگیری پستی", "تغییر نشانی تحویل یا تغییر به باجه تحویل حضوری", "ثبت دستور تحویل در محل امن به مامور توزیع", "رسیدگی به بسته‌های تحویل‌نشده و توزیع مجدد"],
    },
    "cleaning_services": {
        "tr": ["Metrekareye veya oda sayısına göre anında fiyat teklifi", "Düzenli veya detaylı temizlik randevusu", "Kullanılan hijyen protokolleri ve çevre dostu kimyasallar", "Müşteri memnuniyet takibi ve telafi hizmeti"],
        "he": ["הצעת מחיר מהירה לפי שטח במ\"ר או מספר חדרים", "תיאום שירותי ניקיון שוטפים או ניקיון יסודי", "תקני חיטוי ושימוש בחומרי ניקוי ירוקים", "משוב איכות ואחריות לתיקון במידת הצורך"],
        "fa": ["استعلام سریع قیمت نظافت بر اساس متراژ یا تعداد اتاق", "تنظیم برنامه نظافت دوره‌ای اداری یا خانه‌تکانی کامل", "رعایت پروتکل‌های بهداشتی و مواد شوینده استاندارد", "پیگیری کیفیت خدمات و ضمانت نظافت مجدد در صورت لزوم"],
    },
    "custom": {
        "tr": ["İşletmenize ve sektörünüze özel terminoloji eğitimi", "Yalnızca resmi şirket belgelerinize dayanan yanıtlar", "Dahili kurallarınıza göre kişiselleştirilmiş çağrı yönlendirme", "Güvenli API'lar üzerinden şirket içi sistem entegrasyonu"],
        "he": ["הטמעת מונחים ייחודיים לתחום העיסוק של העסק", "תשובות הנסמכות אך ורק על מסמכי חברה מאומתים", "ניתוב שיחות מותאם אישית לפי נהלי הארגון", "שילוב מערכות פנים-ארגוניות דרך ממשקי API מאובטחים"],
        "fa": ["یادگیری اصطلاحات تخصصی و سازمانی ویژه کسب‌وکار شما", "پاسخ‌دهی دقیق و انحصاری بر پایه اسناد تاییدشده شرکت", "هدایت هوشمند تماس‌ها طبق دستورالعمل‌های داخلی شما", "اتصال امن به نرم‌افزارهای داخلی از طریق وب‌سرویس و API"],
    },
}
