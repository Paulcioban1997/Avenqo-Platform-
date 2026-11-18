# coding: utf-8
"""
Native suggested capabilities for African languages:
- sw (Swahili)
- am (Amharic)
- af (Afrikaans)
- ha (Hausa)
across all 30 industries.
"""

CAPS_AFRICA = {
    "auto": {
        "sw": ["Uthibitishaji wa vipuri kwa nambari ya VIN au mfano wa gari", "Upatikanaji wa hisa na makadirio ya bei", "Kuweka miadi ya matengenezo na huduma za karakana", "Kufuatilia maendeleo ya matengenezo ya gari"],
        "am": ["የመለዋወጫ ክፍሎች ተኳሃኝነት በVIN ወይም በተሽከርካሪ ሞዴል ማረጋገጥ", "የዕቃ ክምችት መኖር እና አመላካች የዋጋ ዝርዝር", "የጥገና እና የጋራዥ አገልግሎት ቀጠሮ ማስያዝ", "የተሽከርካሪውን የጥገና ሂደት ደረጃ መከታተል"],
        "af": ["Onderdeleversoenbaarheid volgens VIN of voertuigmodel", "Voorraadbeskikbaarheid en riglynpryse", "Bespreking van instandhouding en werkswinkeldienste", "Monitering van voertuigherstelvordering in die werkswinkel"],
        "ha": ["Duba dacewar kayan gyara ta lambar VIN ko samfurin mota", "Samuwar kaya a rumbun ajiya da kiyasin farashi", "Yin alƙawarin gyara da kulawa a gareji", "Bibiyar matakin gyaran mota a gareji"],
    },
    "medical": {
        "sw": ["Kupanga na kurekebisha miadi ya daktari", "Mwongozo wa kiutawala na nyaraka zinazohitajika", "Ratiba za madaktari na chaguzi za mashauriano ya mbali", "Uhamisho wa kipaumbele kwa wauguzi wa zamu"],
        "am": ["የህክምና ቀጠሮ ማስያዝ እና የጊዜ ሰሌዳ መቀየር", "የአስተዳደር መመሪያ እና አስፈላጊ የሰነዶች ዝርዝር", "የሃኪሞች የስራ ሰዓት እና የቴሌሄልዝ አማራጮች", "ለተረኛ ነርሶች ቅድሚያ የሚሰጠው የስልክ ማስተላለፍ"],
        "af": ["Bespreek en herskeduleer mediese afsprake", "Administratiewe leiding en vereiste dokumente", "Dokterskedules en telemedisyne-opsies", "Prioriteitsoorplasing na verpleegpersoneel aan diens"],
        "ha": ["Yin alƙawarin ganin likita da sauya lokaci", "Jagorancin gudanarwa da takardun da ake buƙata", "Jadawalin likitoci da zaɓuɓɓukan shawarar likita ta waya", "Tura kiran gaggawa ga ma'aikatan jinya"],
    },
    "restaurant": {
        "sw": ["Kuhifadhi meza na uthibitisho wa papo hapo kupitia SMS", "Vyakula maalum vya siku na uwasilishaji wa menyu", "Maswali kuhusu vizio vya chakula kulingana na viungo vilivyothibitishwa", "Maagizo ya kuchukua na uhifadhi wa vikundi binafsi"],
        "am": ["ፈጣን የSMS ማረጋገጫ ያለው የጠረጴዛ ማስያዣ", "የዕለቱ ልዩ ምግቦች እና የሜኑ ገለጻ", "የአለርጂ ጥያቄዎች በተረጋገጡ ንጥረ ነገሮች መረጃ መሰረት", "የመውሰጃ ትዕዛዞች እና የግል ቡድን ቦታ ማስያዣ"],
        "af": ["Tafelbespreking met onmiddellike SMS-bevestiging", "Daaglikse spesiale aanbiedinge en spyskaartvoorligting", "Navrae oor allergene beantwoord uit geverifieerde bestanddele", "Wegneemetes en privaat groepbesprekings"],
        "ha": ["Yin ajiyar tebura tare da tabbatarwa nan take ta SMS", "Abubuwan yau da kullun na musamman da gabatar da menu", "Tambayoyi kan abubuwan da ke haifar da rashin lafiyan jiki", "Odar abinci a tafi da shi da ajiyar rukuni"],
    },
    "retail": {
        "sw": ["Uhakiki wa hisa dukani kwa wakati halisi", "Ufuatiliaji wa vifurushi na hali ya usafirishaji", "Sera za kurejesha bidhaa na saa za kufungua matawi", "Mapendekezo ya bidhaa zinazosaidiana na vifaa"],
        "am": ["የመደብር ዕቃዎች ክምችት በቅጽበት መከታተያ", "የእሽግ መከታተያ እና የመላኪያ ሁኔታ", "የዕቃ መመለሻ ፖሊሲዎች እና የቅርንጫፍ የስራ ሰዓታት", "ተዛማጅ ተጨማሪ ምርቶች እና መለዋወጫዎች ጥቆማ"],
        "af": ["Intydse voorraadkontrole in die winkel", "Pakketopsporing en afleweringsvordering", "Terugstuurbeleid en takopeningstye", "Voorstelle vir bykomende produkte en bykomstighede"],
        "ha": ["Duba kayan shago a ainihin lokacin da ake ciki", "Bibiyar fakiti da matsayin isarwa", "Ka'idojin mayar da kaya da lokutan buɗe rassa", "Shawarwarin ƙarin kayayyaki da suka dace"],
    },
    "transport": {
        "sw": ["Kufuatilia mizigo kwa nambari ya Bill of Lading (BOL)", "Wakati uliokadiriwa wa kuwasili (ETA) na madirisha ya kizimbani", "Msaada na maagizo kwa madereva waliothibitishwa kwa PIN", "Masaa ya ghala na itifaki za usalama za getini"],
        "am": ["የጭነት መከታተያ በቢል ኦፍ ሌዲንግ (BOL) ቁጥር", "የሚገመተው የመድረሻ ሰዓት (ETA) እና የመጫኛ መድረክ ሰዓታት", "በPIN በተረጋገጠ ማንነት ለአሽከርካሪዎች የሚሰጥ ድጋፍ", "የመጋዘን የስራ ሰዓት እና የበሩ የደህንነት ደንቦች"],
        "af": ["Skeepsvragopsporing volgens vragbriefnommer (BOL)", "Geskatte aankomstyd (ETA) en laaikaaivensters", "PIN-geverifieerde bestuurderondersteuning en -instruksies", "Pakhuisure en hektoegangsprotokolle"],
        "ha": ["Bibiyar jigilar kaya ta lambar Bill of Lading (BOL)", "Kiyasin lokacin isowa (ETA) da lokacin sauke kaya", "Tallafin direbobi da aka tabbatar da lambar PIN", "Lokutan buɗe rumbun ajiya da ka'idojin tsaron ƙofa"],
    },
    "real_estate": {
        "sw": ["Habari kuhusu mali zinazouzwa au kukodishwa", "Vigezo vya utafutaji na uhalali wa bajeti ya wanunuzi", "Kupanga ziara za kutazama na mawakala wenye leseni", "Ombi la tathmini ya awali ya thamani ya soko"],
        "am": ["የሚሸጡ ወይም የሚከራዩ ቤቶች እና ይዞታዎች መረጃ", "የገዢዎች የፍለጋ መስፈርቶች እና የበጀት ሁኔታ ግምገማ", "ፈቃድ ካላቸው ደላሎች ጋር የቦታው ጉብኝት ቀጠሮ", "የቅድመ ገበያ ዋጋ ግምገማ ጥያቄ ማቅረቢያ"],
        "af": ["Inligting oor eiendomme te koop of te huur", "Soekkriteria en koperbegrotingskwalifikasie", "Besigtigingsbesprekings met gelisensieerde makelaars", "Versoeke vir voorlopige markwaardasies"],
        "ha": ["Bayanai kan gidaje ko filaye na sayarwa ko haya", "Ka'idojin bincike da kiyasin kuɗin mai saye", "Yin alƙawarin duba gida tare da dillalai masu lasisi", "Neman kiyasin farashin kasuwa na farko"],
    },
    "hospitality": {
        "sw": ["Kuhifadhi vyumba na kurekebisha muda wa kukaa", "Miongozo ya kuingia/kutoka na maelekezo ya maegesho", "Msaada wa wahudumu na mapendekezo ya maeneo ya karibu", "Maombi ya huduma za chumbani na vifaa vya wageni"],
        "am": ["የክፍል ማስያዣ እና የመቆያ ቀናት ለውጥ", "የቼክ-ኢን እና ቼክ-አውት መመሪያዎች እና የመኪና ማቆሚያ መረጃ", "የኮንሲየርጅ እገዛ እና የአካባቢው መስህቦች ጥቆማ", "የክፍል አገልግሎት እና የሆቴል መገልገያዎች ጥያቄ"],
        "af": ["Kamerbespreking en wysiging van verblyfdatums", "Inklok- en uitklokbeleid en parkeerinligting", "Portierbystand en plaaslike aanbevelings", "Gastedienste en versoeke vir kamergeriewe"],
        "ha": ["Yin ajiyar ɗaki da sauya kwanakin zama", "Ka'idojin shiga/fita da jagorancin ajiye motoci", "Tallafin mai kula da baki da shawarwarin wuraren gani", "Neman hidimar ɗaki da kayan more rayuwa"],
    },
    "beauty": {
        "sw": ["Kuhifadhi huduma za spa, saluni ya nywele na masaji", "Bei za huduma na maelezo ya vifurushi", "Vikumbusho vya miadi kiotomatiki na kupanga upya", "Miongozo ya maandalizi kabla ya matibabu"],
        "am": ["የስፓ፣ የጸጉር ቤት እና የማሳጅ ቀጠሮ ማስያዣ", "የአገልግሎቶች ዋጋ እና የጥቅል ቅናሾች ዝርዝር", "የቀጠሮ ማስታወሻዎች እና የጊዜ ሰሌዳ ለውጥ", "ከህክምና እና እንክብካቤ በፊት የሚደረጉ ቅድመ ዝግጅቶች"],
        "af": ["Spa-, haarsalon- en masseerbesprekings", "Behandelingspryse en pakketbesonderhede", "Outomatiese afspraakherinneringe en herskedulering", "Voorbereidingsriglyne voor behandeling"],
        "ha": ["Yin alƙawarin zuwa spa, salon gyaran gashi da tausa", "Farashin ayyuka da cikakkun bayanan fakiti", "Tunasar da alƙawura kai tsaye da sauya lokaci", "Jagorancin shiri kafin a fara kula da jiki"],
    },
    "construction": {
        "sw": ["Ukusanyaji wa mahitaji ya mradi kwa nukuu za mkandarasi", "Simu za dharura za mabomba, umeme au kuezeka paa", "Kupanga makadirio ya gharama kwenye eneo la ujenzi", "Uratibu wa wakandarasi wadogo walioidhinishwa"],
        "am": ["የኮንትራክተር የዋጋ ማቅረቢያ ለመስራት የፕሮጀክት ፍላጎት ማሰባሰብ", "የቧንቧ፣ የኤሌክትሪክ ወይም የጣሪያ ድንገተኛ ጥገና ጥሪዎች", "በቦታው ላይ የሚደረግ የዋጋ ግምት እና የልኬት ቀጠሮ", "ፈቃድ ካላቸው ንዑስ ኮንትራክተሮች ጋር የሚደረግ ቅንጅት"],
        "af": ["Projekvereistes vir kontrakteurskwotasies", "Noodoproepe vir loodgieterswerk, elektrisiteit of dakke", "Skedulering van ramings en metings op die perseel", "Koördinering van gemagtigde subkontrakteurs"],
        "ha": ["Tattara buƙatun aiki don samun ƙididdigar ɗan kwangila", "Kiran gaggawa na bututun ruwa, wutar lantarki ko rufin asiri", "Tsara lokacin duba aiki da auna wurin", "Daidaita ayyukan ƙananan 'yan kwangila masu izini"],
    },
    "finance": {
        "sw": ["Kupanga mkutano na mshauri wa fedha", "Maeneo ya matawi na masaa ya huduma", "Uhakiki salama wa awali wa maombi ya mkopo", "Kuelekeza kwa idara za usimamizi wa mali na utajiri"],
        "am": ["ከፋይናንስ አማካሪ ጋር የመገናኛ ቀጠሮ ማስያዝ", "የቅርንጫፍ አድራሻዎች እና የባንክ አገልግሎት ሰዓታት", "አስተማማኝ የብድር ማመልከቻ የቅድመ ብቃት ማረጋገጫ", "ወደ ሀብት አስተዳደር እና ኢንቨስትመንት ክፍሎች ማስተላለፍ"],
        "af": ["Finansiële raadgewersvergaderingskedulering", "Takliggings en kantoorure", "Veilige voorafkwalifikasie vir leningsaansoeke", "Verwysing na departemente vir welvaartbestuur"],
        "ha": ["Tsara ganawa da mai ba da shawara kan harkokin kuɗi", "Wuraren rassa da lokutan aiki", "Tabbatar da cancantar neman rance cikin aminci", "Tura kira zuwa sashen sarrafa dukiya"],
    },
    "insurance": {
        "sw": ["Taarifa ya awali ya madai ya bima na usajili", "Kufuatilia maendeleo ya madai ya fidia mtandaoni", "Ufafanuzi wa bima na kiwango cha makato", "Msaada wa dharura barabarani na uokoaji wa ajali"],
        "am": ["የመጀመሪያ የኢንሹራንስ ካሳ ጥያቄ ማሳወቂያ እና ምዝገባ", "የካሳ ክፍያ ሂደት ሁኔታን በኦንላይን መከታተል", "የፖሊሲው የሽፋን መጠን እና የቅናሽ ክፍያ ማብራሪያ", "የድንገተኛ የመንገድ ላይ እና የአደጋ ጊዜ እርዳታ"],
        "af": ["Aanvanklike eisinname en -registrasie", "Aanlyn opsporing van eisuitbetalings", "Polisdekking en bybetalingsbesonderhede", "Noodpadbystand en ongeluksberging"],
        "ha": ["Shigar da ƙorafin neman biyan diyya na inshora", "Bibiyar matakin biyan diyya ta yanar gizo", "Bayani kan abubuwan da inshora ya shafa da ragin kuɗi", "Taimakon gaggawa a kan hanya da hatsari"],
    },
    "legal": {
        "sw": ["Kuweka miadi ya mashauriano ya awali ya kisheria", "Uainishaji wa kesi (madai, jinai, ajira)", "Viwango vya ada na taratibu za uwakilishi", "Muda wa ukomo na orodha ya ushahidi unaohitajika"],
        "am": ["የመጀመሪያ የህግ ማማከር ቀጠሮ ከጠበቃ ጋር ማስያዝ", "የጉዳይ ምድብ መለየት (ፍትሐብሔር፣ ወንጀል፣ የሰራተኛ መብት)", "የአገልግሎት ክፍያ እና የውክልና ስምምነት ሂደቶች", "የይርጋ ጊዜያት እና አስፈላጊ የማስረጃ ሰነዶች ዝርዝር"],
        "af": ["Bespreek inleidende regskonsultasies", "Saakklassifikasie (siviel, krimineel, arbeidsreg)", "Fooie en prosedures vir verteenwoordigingsooreenkomste", "Verjaringstydperke en lys van vereiste bewyse"],
        "ha": ["Yin alƙawarin neman shawarar lauya ta farko", "Raba nau'in shari'a (na gida, laifi, aiki)", "Farashin aiki da hanyoyin ba da wakilci", "Iyakokin lokaci da jerin hujjojin da ake buƙata"],
    },
    "education": {
        "sw": ["Maelezo ya kozi, tarehe za muhula na ratiba", "Usajili wa mtandaoni na uhakiki wa vigezo vya kujiunga", "Ada za masomo, ufadhili na mipango ya malipo", "Kuweka miadi ya mazungumzo na washauri wa masomo"],
        "am": ["የትምህርት ፕሮግራሞች፣ የሴሚስተር ቀናት እና የክፍል ሰዓታት", "የኦንላይን ምዝገባ እና የመግቢያ መስፈርቶች ቅድመ-ግምገማ", "የማስተማሪያ ክፍያ፣ የነፃ ትምህርት እና የክፍያ አማራጮች", "ከአካዳሚክ አማካሪዎች ጋር የሚደረግ ቀጠሮ"],
        "af": ["Kursusbesonderhede, semesterdatums en roosters", "Aanlyn registrasie en toelatingsvereistekontrole", "Klasgelde, beurse en paaiementsopsies", "Afsprake met akademiese adviseurs"],
        "ha": ["Bayanai kan kwasa-kwasai, kwanakin zangon karatu da jadawali", "Rijista ta yanar gizo da duba cancantar shiga", "Kuɗin makaranta, tallafin karatu da zaɓin biya a hankali", "Yin alƙawari tare da masu ba da shawara kan ilimi"],
    },
    "hr_recruitment": {
        "sw": ["Vigezo vya kazi na maelezo ya majukumu ya nafasi", "Uchambuzi wa awali wa wasifu wa waombaji", "Kupanga ratiba ya mahojiano na timu ya uajiri", "Miongozo ya hati za kuanza kazi kwa wafanyakazi wapya"],
        "am": ["የስራ መደብ መስፈርቶች እና የስራ ዝርዝር መግለጫዎች", "የአመልካቾች የሲቪ (CV) የመጀመሪያ ደረጃ ማጣሪያ", "ከቅጥር ኃላፊዎች ጋር የቃለ መጠይቅ ቀጠሮ ማመቻቸት", "ለአዳዲስ ሰራተኞች የመግቢያ ሰነዶች መመሪያ"],
        "af": ["Posvereistes en rolbeskrywings", "Aanvanklike keuring van aansoekers se CV's", "Onderhoudskedulering met werwers", "Aanstellingsriglyne en dokumentasie vir nuwe personeel"],
        "ha": ["Bukatun aiki da bayanin nauyin da ke kan mutum", "Tantance takardun neman aiki (CV) na farko", "Tsara lokacin yin hira da masu ɗaukar ma'aikata", "Takardun shiga aiki da jagoranci ga sabbin ma'aikata"],
    },
    "it_services": {
        "sw": ["Kufungua tiketi ya msaada wa TEHAMA na kuweka kipaumbele", "Uchunguzi wa awali wa matatizo ya mtandao na programu", "Kupanga huduma ya fundi kwenye eneo au msaada wa mbali", "Hali ya huduma za wingu na arifa za matengenezo"],
        "am": ["የአይቲ (IT) ድጋፍ ጥያቄ መመዝገብ እና ቅድሚያ መስጠት", "የኔትወርክ እና የሶፍትዌር ችግሮች የመጀመሪያ ደረጃ ምርመራ", "የባለሙያ የቦታው ጉብኝት ወይም የርቀት ድጋፍ ቀጠሮ", "የክላውድ አገልግሎት ሁኔታ እና የጥገና ማሳወቂያዎች"],
        "af": ["Skep en prioritiseer IT-hulpkaartjies", "Diagnose van netwerk- en sagtewareprobleme", "Bespreek tegnikusbesoeke of afstandbystand", "Wolkdiensstatus en instandhoudingskennisgewings"],
        "ha": ["Bude tikitin neman taimakon IT da ba da fifiko", "Binciken matsalolin hanyar sadarwa da manhaja na farko", "Yin alƙawari da masanin fasaha a wurin ko ta nesa", "Matsayin sabis na gajimare da sanarwar gyare-gyare"],
    },
    "manufacturing": {
        "sw": ["Uainishaji wa kiufundi na uwezo wa mashine za viwandani", "Muda wa uzalishaji na ratiba za uwasilishaji", "Kuagiza vipuri na michoro ya kiufundi", "Viwango vya udhibiti wa ubora na vyeti vya viwanda"],
        "am": ["የኢንዱስትሪ ማሽነሪዎች ቴክኒካዊ ዝርዝር መግለጫ እና አቅም", "የምርት ማጠናቀቂያ ጊዜ እና የማድረሻ መርሃ ግብር", "መለዋወጫ ዕቃዎችን ማዘዝ እና ቴክኒካዊ ስዕሎች ጥያቄ", "የጥራት ቁጥጥር ደረጃዎች እና የኢንዱስትሪ የምስክር ወረቀቶች"],
        "af": ["Masjineriespesifikasies en tegniese vermoëns", "Produksietye en afleweringskedules", "Onderdelebestellings en tegniese tekeninge", "Gehaltebeheerstandaarde en industriële sertifisering"],
        "ha": ["Bayanin fasaha da ƙarfin injunan masana'antu", "Lokacin kammala kera kaya da jadawalin isarwa", "Odar kayan gyara da zane-zanen fasaha", "Ka'idojin kula da inganci da takaddun shaida"],
    },
    "agriculture": {
        "sw": ["Upatikanaji wa mbegu, mbolea na viuatilifu", "Ununuzi wa mazao kwa jumla na bei za soko", "Ushauri wa kilimo na msaada wa wataalamu", "Ratiba ya uvunaji na usafirishaji wa jokofu"],
        "am": ["የዘር፣ የማዳበሪያ እና የፀረ-ተባይ ኬሚካሎች አቅርቦት ሁኔታ", "የሰብል ምርቶች በጅምላ ግዢ እና የወቅቱ የገበያ ዋጋ", "የግብርና ባለሙያዎች የምክር አገልግሎት እና ድጋፍ", "የምርት አሰባሰብ ወቅት እና የቀዝቃዛ ሰንሰለት ሎጂስቲክስ"],
        "af": ["Beskikbaarheid van saad, kunsmis en plaagdoders", "Grootmaataankoop van oeste en heersende markpryse", "Landboukundige advies en tegniese kundigheid", "Oesskedules en kouekettinglogistiek"],
        "ha": ["Samuwar irin shuka, takin zamani da maganin ƙwari", "Sayan amfanin gona da yawa da farashin kasuwa", "Shawarar masana aikin gona da tallafin fasaha", "Jadawalin girbi da jigilar kayan sanyi"],
    },
    "wholesale": {
        "sw": ["Orodha ya bei za jumla kulingana na kiasi cha oda", "Kiwango cha chini cha oda (MOQ) na muda wa kupokea", "Maombi ya akaunti ya mkopo wa kibiashara na masharti ya malipo", "Kufuatilia usafirishaji wa mizigo ya makontena"],
        "am": ["እንደ ትዕዛዙ ብዛት የተደረደረ የጅምላ ሽያጭ ዋጋ ዝርዝር", "ዝቅተኛው የትዕዛዝ መጠን (MOQ) እና የማስረከቢያ ጊዜ", "የንግድ ብድር አካውንት ጥያቄ እና የክፍያ ውሎች", "የፓሌት እና የኮንቴይነር ጭነት መከታተያ"],
        "af": ["Grootmaatpryslyste volgens ordervolume", "Minimum bestelhoeveelhede (MOQ) en leitye", "Aansoeke om handelskediet en betalingsvoorwaardes", "Opsporing van palet- en houervragte"],
        "ha": ["Jerin farashin sari dangane da yawan kaya", "Mafi ƙarancin adadin oda (MOQ) da lokacin kawowa", "Neman asusun bashi na kasuwanci da sharuɗɗan biya", "Bibiyar jigilar kaya a kan fale-fale da kwantena"],
    },
    "pharmacy": {
        "sw": ["Uhakiki wa dawa za maagizo kuwa tayari kuchukuliwa", "Hisa ya dawa zisizo na maagizo na virutubisho", "Mwongozo wa mfamasia kuhusu dozi na tahadhari", "Saa za duka la dawa la zamu na uwasilishaji wa dharura"],
        "am": ["የታዘዙ መድሃኒቶች ተዘጋጅተው ለመወሰድ ዝግጁ መሆናቸውን ማረጋገጥ", "ያለ ማዘዣ የሚሸጡ መድሃኒቶች እና የቫይታሚን ክምችት", "የፋርማሲስቶች የአወሳሰድ መመሪያ እና የጥንቃቄ ምክር", "የተረኛ ፋርማሲ የስራ ሰዓት እና የአስቸኳይ ጊዜ መድሃኒት አቅርቦት"],
        "af": ["Voorskrifmedikasiegereedheid vir afhaling", "Voorraad van oor-die-toonbank medisyne en vitamiene", "Apteker se doseringsvoorligting en wisselwerkings", "Diensdoenende apteekure en spoedaflewering"],
        "ha": ["Duba shirye-shiryen magungunan da likita ya rubuta don ɗauka", "Samuwar magunguna marasa buƙatar takardar likita da bitamin", "Jagorancin masanin magani kan yawa da gargaɗi", "Lokutan buɗe kantin magani na dare da isar da gaggawa"],
    },
    "veterinary": {
        "sw": ["Kupanga chanjo na uchunguzi wa kawaida wa mifugo", "Huduma ya kwanza na tathmini ya dharura ya wanyama", "Ushauri wa kuhasi, kuweka microchip na utunzaji wa kinga", "Historia ya matibabu na mazungumzo na daktari wa mifugo"],
        "am": ["የቤት እንስሳት ክትባት እና መደበኛ የጤና ምርመራ ቀጠሮ", "የእንስሳት ድንገተኛ አደጋ የመጀመሪያ እርዳታ እና ምዘና", "የማኮላሸት፣ ማይክሮቺፕ መግጠም እና የመከላከያ እንክብካቤ ምክር", "የህክምና ታሪክ መመልከት እና ከህክምና ባለሙያው ጋር መነጋገር"],
        "af": ["Troeteldierinentings en roetineondersoeke", "Noodhulp en noodbeoordeling vir diere", "Sterilisasie-, mikroskyfie- en voorkomende sorg", "Mediese rekords en kontak met die veearts"],
        "ha": ["Yin alƙawarin allurar riga-kafi da gwajin dabbobi na yau da kullun", "Taimakon gaggawa da duba dabbobin da ke cikin haɗari", "Shawarar cire haihuwa, saka microchip da rigakafi", "Duba tarihin magani da tattaunawa da likitan dabbobi"],
    },
    "consulting": {
        "sw": ["Kufafanua malengo na upeo wa mradi wa ushauri", "Kupanga mkutano wa utangulizi na washauri wakuu", "Uwasilishaji wa mifano ya mafanikio na maeneo ya utaalamu", "Maombi ya mapendekezo na vifaa vya kuanzisha mradi"],
        "am": ["የማማከር ፕሮጀክት ግቦች እና ወሰን መለየት", "ከከፍተኛ አማካሪዎች ጋር የመተዋወቂያ ስብሰባ ቀጠሮ", "የተሳኩ የቀድሞ ስራዎች እና የሙያ ዘርፎች ገለጻ", "የፕሮጀክት ፕሮፖዛል እና የማስተዋወቂያ ሰነዶች ጥያቄ"],
        "af": ["Projekomvang en behoeftebepaling", "Inleidende vergaderings met senior konsultante", "Konsultasiepraktyke en gevallestudies", "Voorstelle en inleidende inligtingsversoeke"],
        "ha": ["Bayanin manufofi da iyakokin aikin ba da shawara", "Tsara taron gabatarwa tare da manyan masu ba da shawara", "Nuna misalan nasarorin da suka gabata da fannonin ƙwarewa", "Neman shawarwarin aiki da takardun gabatarwa"],
    },
    "public_services": {
        "sw": ["Ratiba za ukusanyaji wa taka na vituo vya kuchakata", "Ripoti za uharibifu wa barabara, mashimo na taa za mitaani", "Masaa ya ofisi ya manispaa na miongozo ya vibali", "Kuelekeza kwa idara husika za serikali za mitaa"],
        "am": ["የቆሻሻ አሰባሰብ መርሃ ግብር እና የድጋሚ ጥቅም ላይ ማዋያ ማዕከላት", "የመንገድ ብልሽቶች፣ ጉድጓዶች እና የመንገድ መብራቶች ጥቆማ", "የከተማ አስተዳደር የስራ ሰዓት እና የፈቃድ መመሪያዎች", "ወደሚመለከታቸው የማዘጋጃ ቤት የስራ ክፍሎች ማስተላለፍ"],
        "af": ["Vullisverwyderingskedules en herwinningsentrums", "Aanmelding van padskade, slaggate en munisipale kwessies", "Munisipale kantoorure en permitriglyne", "Verwysing na relevante munisipale departemente"],
        "ha": ["Jadawalin kwashe shara da cibiyoyin sake amfani da kaya", "Bayar da rahoton lalacewar hanyoyi, ramuka da fitilun titi", "Lokutan ofishin ƙaramar hukuma da ka'idojin samun izini", "Tura kira kai tsaye zuwa sassan da suka dace"],
    },
    "telecom": {
        "sw": ["Kuangalia upatikanaji wa intaneti ya fiber kulingana na anwani", "Uchunguzi wa kiotomatiki wa hitilafu za mtandao", "Kuweka miadi ya ufungaji na ziara ya fundi", "Maelezo ya vifurushi vya intaneti na ofa za ziada"],
        "am": ["እንደ አድራሻው የፋይበር እና የብሮድባንድ ዝርጋታ መኖርን ማረጋገጥ", "የኔትወርክ መቆራረጥ እና የአገልግሎት ሁኔታ በራስ-ሰር መመርመር", "የኢንተርኔት ተከላ እና የቴክኒሻን የጉብኝት ቀጠሮ", "የኢንተርኔት እና የሞባይል ፓኬጆች ዝርዝር መረጃ"],
        "af": ["Adresgebaseerde breëband- en veselbeskikbaarheid", "Outomatiese diensonderbrekings- en netwerktoets", "Installasie- en tegnikusafsprake", "Pakketbesonderhede en bykomende opsies"],
        "ha": ["Duba samuwar layin intanet na fiber dangane da adireshi", "Binciken matsalar hanyar sadarwa kai tsaye", "Yin alƙawarin saka intanet da ziyarar masanin fasaha", "Bayanai kan tsare-tsaren intanet da ƙarin fakiti"],
    },
    "commercial_real_estate": {
        "sw": ["Upatikanaji wa nafasi za ofisi na majengo ya kibiashara", "Masharti ya upangishaji wa kibiashara na vibali vya eneo", "Kupanga ziara za ukaguzi kwa viongozi wa kampuni", "Maelezo ya jengo (eneo la sakafu, sehemu za kupakia, maegesho)"],
        "am": ["ክፍት የቢሮ እና የንግድ ቦታዎች ኪራይ መረጃ", "የንግድ ኪራይ ውል ስምምነቶች እና የዞን ክፍፍል ደንቦች", "ለድርጅት ስራ አስፈፃሚዎች የሚደረግ የቦታው ጉብኝት ቀጠሮ", "የህንፃው ቴክኒካዊ መረጃ (የወለል ስፋት፣ የመጫኛ መድረክ፣ ፓርኪንግ)"],
        "af": ["Kantoor- en kleinhandelruimtebeskikbaarheid", "Kommersiële huurvoorwaardes en soneringsbesonderhede", "Perseelbesigtiging vir korporatiewe bestuurders", "Gebouspesifikasies (oppervlakte, laaikaaie, parkering)"],
        "ha": ["Samuwar wuraren ofis da shagunan kasuwanci na haya", "Sharuɗɗan hayar kasuwanci da ka'idojin shiyya", "Tsara ziyarar duba wuri ga shugabannin kamfanoni", "Bayanin gini (faɗin fili, wurin sauke kaya, ajiye motoci)"],
    },
    "property_management": {
        "sw": ["Kupokea maombi ya ukarabati na matengenezo kutoka kwa wakazi", "Ushughulikiaji wa dharura za kiufundi (uvujaji wa maji, hitilafu ya hita)", "Taarifa za matengenezo na kukatizwa kwa huduma za maji", "Mwongozo wa malipo ya kodi na ada za usimamizi"],
        "am": ["የነዋሪዎች የጥገና እና የእድሳት ጥያቄዎች መቀበያ", "አስቸኳይ ቴክኒካዊ ችግሮችን መፍታት (የውሃ መፍሰስ፣ የማሞቂያ ብልሽት)", "የጥገና ስራዎች እና የውሃ መቋረጥ ማሳወቂያዎች", "የቤት ኪራይ እና የኮንዶሚኒየም አስተዳደር ክፍያ መመሪያ"],
        "af": ["Instandhoudingsversoeke van inwoners en huurders", "Noodintervensies (waterlekkasies, verwarmingsfoute)", "Instandhoudingskennisgewings en onderbrekingswaarskuwings", "Betalingsriglyne vir huur en bestuursfooie"],
        "ha": ["Karɓar buƙatun gyara da kulawa daga mazauna", "Kula da matsalolin gaggawa (yoyon ruwa, lalacewar na'urar ɗumama)", "Sanarwar gyare-gyare da katsewar ruwa", "Jagorancin biyan kuɗin haya da na kula da muhalli"],
    },
    "fitness_gym": {
        "sw": ["Ratiba ya madarasa ya mazoezi ya kikundi na kuhifadhi nafasi", "Bei za uanachama, pasi za siku na ofa za majaribio", "Kuweka miadi ya tathmini ya siha na mkufunzi binafsi", "Kanuni za ukumbi na ushauri wa masaa ya msongamano"],
        "am": ["የቡድን ስፖርት ክፍሎች የጊዜ ሰሌዳ እና የቦታ ማስያዣ", "የአባልነት ዋጋዎች፣ የቀን መግቢያ እና የሙከራ ቅናሾች", "ከግል አሰልጣኝ ጋር የሚደረግ የሰውነት ብቃት ምዘና ቀጠሮ", "የስፖርት ማዕከሉ ደንቦች እና ከፍተኛ የሰው መጨናነቅ ሰዓታት ጥቆማ"],
        "af": ["Groepfiksheidsklasroosters en besprekings", "Lidmaatskapstariewe, dagpasse en proefaanbiedinge", "Persoonlike afrigter-assesseringsbesprekings", "Fasiliteitsriglyne en spitsuuradvies"],
        "ha": ["Jadawalin azuzuwan motsa jiki na rukuni da ajiye wuri", "Farashin zama memba, shiga na rana ɗaya da tayin gwaji", "Yin alƙawarin duba lafiyar jiki tare da mai horarwa na musamman", "Ka'idojin wurin motsa jiki da shawarar lokutan cunkoso"],
    },
    "events": {
        "sw": ["Ratiba ya matukio, orodha ya wasanii na habari za tiketi", "Maelekezo ya ukumbi, maegesho na ufikiaji wa walemavu", "Msaada kwa waonyeshaji na wazungumzaji waalikwa", "Uhifadhi wa vyumba vya VIP na maeneo ya ushirika"],
        "am": ["የዝግጅት መርሃ ግብር፣ የአርቲስቶች ዝርዝር እና የቲኬት መረጃ", "የቦታው አቅጣጫዎች፣ የመኪና ማቆሚያ እና የተደራሽነት መመሪያ", "ለተሳታፊዎች እና ለተናጋሪዎች የሚደረግ ድጋፍ", "የቪአይፒ (VIP) ክፍሎች እና የድርጅት ሎጆች ማስያዣ"],
        "af": ["Gebeurteniskedules, kunstenaarslyste en kaartjie-inligting", "Aanwysings na die lokaal, parkering en toeganklikheid", "Ondersteuning vir uitstallers en sprekers", "VIP- en korporatiewe suitebesprekings"],
        "ha": ["Jadawalin taro, jerin masu baje koli da bayanan tikiti", "Hanyar zuwa wurin taro, ajiye motoci da sauƙin shiga", "Tallafi ga masu baje koli da masu magana a wurin taro", "Ajiyar ɗakunan VIP da wuraren zama na kamfanoni"],
    },
    "delivery_courier": {
        "sw": ["Kufuatilia kifurushi papo hapo kwa nambari ya ufuatiliaji", "Kubadilisha anwani ya uwasilishaji au kuhamishia kituo cha karibu", "Maagizo salama ya kuweka kifurushi kwa dereva", "Kutatua uwasilishaji uliokosa na kupanga upya muda"],
        "am": ["በመከታተያ ቁጥሩ አማካኝነት እሽጉን በቅጽበት መከታተል", "የመላኪያ አድራሻ መቀየር ወይም ወደ መውሰጃ ጣቢያ ማዞር", "ለአሽከርካሪው የሚሰጥ እሽጉን ደህንነቱ በተጠበቀ ቦታ የማስቀመጥ መመሪያ", "ያልተሳኩ አቅርቦቶችን ማስተካከል እና በድጋሚ ለማድረስ ቀጠሮ መያዝ"],
        "af": ["Intydse pakketopsporing volgens spoornommer", "Afleweringsadresveranderings of herleiding na afhaalpunte", "Veilige aflaai-instruksies vir die koerier", "Hantering van gemiste aflewerings en herskedulering"],
        "ha": ["Bibiyar saƙo nan take ta lambar bibiya", "Sauya adireshin isarwa ko tura shi zuwa wurin karɓa", "Umarnin ajiye kaya a wuri mai aminci ga direba", "Magance saƙon da ba a samu mai karɓa ba da sake tsara lokaci"],
    },
    "cleaning_services": {
        "sw": ["Nukuu ya haraka kulingana na ukubwa wa eneo au idadi ya vyumba", "Kupanga usafi wa mara kwa mara au usafi wa kina", "Miongozo ya usafi na bidhaa rafiki kwa mazingira", "Maoni ya ubora na dhamana ya kurudia kusafisha bila malipo"],
        "am": ["እንደ ስኩዌር ሜትር ስፋት ወይም የክፍሎች ብዛት የሚሰጥ ፈጣን የዋጋ ግምት", "መደበኛ ጽዳት ወይም ጥልቅ አጠቃላይ ጽዳት ቀጠሮ ማስያዝ", "የንፅህና አጠባበቅ ደንቦች እና ለአካባቢ ተስማሚ የሆኑ የጽዳት ምርቶች", "የጥራት አስተያየት መቀበል እና በነፃ ድጋሚ የማጽዳት ዋስትና"],
        "af": ["Onmiddellike kwotasies volgens vierkante meter of vertrekke", "Gereelde en diepskoonmaakskedulering", "Sanitasieprotokolle en omgewingsvriendelike produkte", "Gehalteterugvoer en gratis herskoonmaakwaarborg"],
        "ha": ["Kiyasin farashi nan take gwargwadon faɗin wuri ko yawan ɗakuna", "Tsara aikin share-share na yau da kullun ko tsaftacewa mai zurfi", "Ka'idojin tsafta da kayan aiki marasa lahani ga muhalli", "Tattara ra'ayoyin inganci da garantin sake sharewa kyauta"],
    },
    "custom": {
        "sw": ["Kufundisha msamiati maalum wa sekta ya biashara yako", "Majibu yanayotegemea nyaraka rasmi za kampuni yako pekee", "Kuelekeza simu kulingana na kanuni zako za ndani", "Kuunganisha zana za ndani kupitia API salama"],
        "am": ["ለድርጅትዎ የስራ ዘርፍ ልዩ የሆኑ ቴክኒካዊ ቃላትን ማስተማር", "በተረጋገጡ የኩባንያዎ ሰነዶች ላይ ብቻ የተመሰረቱ መልሶች", "በውስጣዊ መመሪያዎችዎ መሰረት የሚደረግ ብጁ የስልክ ጥሪ ማስተላለፍ", "ደህንነታቸው በተጠበቁ ኤፒአይ (APIs) አማካኝነት የውስጥ ስርዓቶች ውህደት"],
        "af": ["Opleiding in u besigheid se spesifieke vakterme", "Antwoorde uitsluitlik gegrond op u amptelike maatskappydokumente", "Pasgemaakte oproepsturing volgens u interne reëls", "Integrasie van interne stelsels via veilige API's"],
        "ha": ["Koyar da ƙamus na musamman na fannin kasuwancinku", "Amsoshi da suka dogara kawai kan takardun kamfaninku da aka amince da su", "Tura kiran waya bisa tsarin ƙa'idojin kamfaninku na cikin gida", "Haɗa kayan aikin cikin gida ta hanyar amintattun API"],
    },
}
