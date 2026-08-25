# -*- coding: utf-8 -*-
"""Translation data for Group C: sw (Swahili), am (Amharic), af (Afrikaans), ha (Hausa).
Covers modulesSection, pricing, common overrides, finalCta.tryFree, assistant.suggestions."""

MODULES_HEADER = {
    "sw": {"kicker": "Moduli za Avenqo", "title": "Jukwaa moja la moduli, linalokua kulingana na mahitaji",
           "subtitle": "Washa moduli unazohitaji leo, na uongeze baadaye bila kubadilisha zana.",
           "discover": "Gundua", "availableNow": "Inapatikana sasa", "comingSoon": "Inakuja hivi karibuni"},
    "am": {"kicker": "የAvenqo ሞጁሎች", "title": "እንደ ፍላጎትዎ የሚያድግ አንድ ሞጁላር መድረክ",
           "subtitle": "ዛሬ የሚያስፈልጉዎትን ሞጁሎች ያንቁ፣ እና መሳሪያዎችን ሳይቀይሩ በኋላ ያስፉ።",
           "discover": "ተጨማሪ ይወቁ", "availableNow": "አሁን ይገኛል", "comingSoon": "በቅርቡ"},
    "af": {"kicker": "Avenqo-modules", "title": "Een modulêre platform, wat groei soos nodig",
           "subtitle": "Aktiveer die modules wat jy vandag nodig het, en brei later uit sonder om gereedskap te verander.",
           "discover": "Ontdek meer", "availableNow": "Nou beskikbaar", "comingSoon": "Binnekort"},
    "ha": {"kicker": "Modules na Avenqo", "title": "Dandamali ɗaya na modular, yana girma yadda ake bukata",
           "subtitle": "Kunna modules ɗin da kake bukata yau, kuma ka faɗaɗa daga baya ba tare da canza kayan aiki ba.",
           "discover": "Gano ƙari", "availableNow": "Akwai yanzu", "comingSoon": "Nan gaba kadan"},
}

MODULE_NAMES = ["Retail Intelligence", "CRM AI", "OCR AI", "Voice AI", "Media AI", "Accounting AI", "Legal AI"]

MODULE_DESCRIPTIONS = {
    "sw": ["Uchambuzi wa mauzo na hisa kwa wakati halisi kwa biashara ya rejareja.",
           "Usimamizi wa uhusiano na wateja unaotumia AI kwa mauzo bora zaidi.",
           "Uchimbaji wa data kiotomatiki kutoka kwa ankara na hati zilizochanganuliwa.",
           "Msaidizi wa sauti kwa kunakili na kufuatilia simu za wateja.",
           "Uundaji na uchambuzi wa maudhui ya kuona na ya uuzaji.",
           "Uendeshaji kiotomatiki wa uhasibu na upatanisho wa kifedha.",
           "Ukaguzi na muhtasari wa mikataba kwa msaada wa AI."],
    "am": ["ለችርቻሮ ንግድ በእውነተኛ ጊዜ የሽያጭ እና የክምችት ትንተና።",
           "ለተሻለ የሽያጭ ሂደት በAI የተጎለበተ የደንበኞች ግንኙነት አስተዳደር።",
           "ከደረሰኞች እና ከተቃኙ ሰነዶች ራስ-ሰር የመረጃ ማውጣት።",
           "ከደንበኞች ጋር የሚደረጉ ጥሪዎችን ለመመዝገብ እና ለመከታተል የድምጽ ረዳት።",
           "የእይታ እና የግብይት ይዘት መፍጠር እና መተንተን።",
           "የሂሳብ አያያዝ እና የፋይናንስ ማስታረቅ አውቶሜሽን።",
           "በAI እርዳታ ውሎችን መገምገም እና ማጠቃለል።"],
    "af": ["Intydse verkope- en voorraadanalise vir kleinhandel.",
           "AI-gedrewe kliëntverhoudingbestuur vir 'n slimmer verkoopspyplyn.",
           "Outomatiese data-onttrekking uit fakture en geskandeerde dokumente.",
           "Stemassistent vir transkripsie en opvolging van klante-oproepe.",
           "Skepping en analise van visuele en bemarkingsinhoud.",
           "Outomatisering van rekeningkunde en finansiële versoening.",
           "Hersiening en opsomming van kontrakte met AI-hulp."],
    "ha": ["Bincike na tallace-tallace da kayayyaki a ainihin lokaci don kasuwancin dillanci.",
           "Sarrafa alaƙar abokan ciniki wanda AI ke tuƙi don ingantaccen tallace-tallace.",
           "Cirewa bayanai ta atomatik daga takardun kuɗi da takardun da aka bincika.",
           "Mataimaki na murya don rubutawa da bin diddigin kiran abokan ciniki.",
           "Ƙirƙira da nazarin abun ciki na gani da tallace-tallace.",
           "Sarrafa kansa na lissafin kuɗi da daidaita kuɗi.",
           "Bita da taƙaita kwangiloli tare da taimakon AI."],
}

PRICING = {
    "sw": {
        "kicker": "Bei", "title": "Mpango kwa kila hatua ya ukuaji wako", "subtitle": "Anza na onyesho, kisha chagua mpango unaofaa ukubwa wa kampuni yako.",
        "popular": "Maarufu zaidi", "priceLabel": "Bei kwa ombi",
        "plans": [
            {"tier": "Demo", "title": "Jaribu Avenqo na data yako", "priceLabel": "Bure", "items": ["Ufikiaji wa muda mfupi", "Data ya onyesho au yako mwenyewe", "Msaada kwa barua pepe"], "action": "Omba onyesho"},
            {"tier": "Professional", "title": "Kwa makampuni yanayotaka kukua", "priceLabel": "Bei kwa ombi", "items": ["Moduli zote za msingi", "Idadi ya watumiaji inayoweza kupanuka", "Msaada wa kipaumbele"], "action": "Wasiliana nasi"},
            {"tier": "Enterprise", "title": "Kwa mashirika yenye mahitaji ya kina", "priceLabel": "Bei kwa ombi", "items": ["Ushirikiano maalum", "Meneja wa akaunti maalum", "Mkataba wa kiwango cha huduma"], "action": "Wasiliana na mauzo"},
        ],
    },
    "am": {
        "kicker": "ዋጋ አሰጣጥ", "title": "ለእያንዳንዱ የእድገት ደረጃዎ የሚስማማ እቅድ", "subtitle": "በማሳያ ይጀምሩ፣ ከዚያም ለኩባንያዎ መጠን የሚስማማውን እቅድ ይምረጡ።",
        "popular": "በጣም ተወዳጅ", "priceLabel": "ዋጋ በጥያቄ",
        "plans": [
            {"tier": "Demo", "title": "Avenqo ን በእርስዎ መረጃ ይሞክሩ", "priceLabel": "ነጻ", "items": ["በጊዜ የተገደበ መዳረሻ", "የማሳያ ወይም የራስዎ መረጃ", "በኢሜይል ድጋፍ"], "action": "ማሳያ ይጠይቁ"},
            {"tier": "Professional", "title": "ለማደግ ለሚፈልጉ ኩባንያዎች", "priceLabel": "ዋጋ በጥያቄ", "items": ["ሁሉም ዋና ሞጁሎች", "ሊሰፋ የሚችል የተጠቃሚዎች ብዛት", "ቅድሚያ ድጋፍ"], "action": "አግኙን"},
            {"tier": "Enterprise", "title": "ለላቁ ፍላጎቶች ላላቸው ድርጅቶች", "priceLabel": "ዋጋ በጥያቄ", "items": ["ብጁ ውህደት", "የተወሰነ የመለያ አስተዳዳሪ", "የአገልግሎት ደረጃ ስምምነት"], "action": "ከሽያጭ ጋር ይገናኙ"},
        ],
    },
    "af": {
        "kicker": "Pryse", "title": "'n Plan vir elke fase van jou groei", "subtitle": "Begin met 'n demo, kies dan die plan wat by jou maatskappy se grootte pas.",
        "popular": "Gewildste", "priceLabel": "Prys op aanvraag",
        "plans": [
            {"tier": "Demo", "title": "Probeer Avenqo met jou data", "priceLabel": "Gratis", "items": ["Tydsbeperkte toegang", "Demo- of eie data", "Ondersteuning per e-pos"], "action": "Vra 'n demo aan"},
            {"tier": "Professional", "title": "Vir maatskappye wat wil groei", "priceLabel": "Prys op aanvraag", "items": ["Alle kernmodules", "Skaalbare aantal gebruikers", "Prioriteitsondersteuning"], "action": "Kontak ons"},
            {"tier": "Enterprise", "title": "Vir organisasies met gevorderde behoeftes", "priceLabel": "Prys op aanvraag", "items": ["Pasgemaakte integrasie", "Toegewyde rekeningbestuurder", "Diensvlakooreenkoms"], "action": "Kontak verkope"},
        ],
    },
    "ha": {
        "kicker": "Farashi", "title": "Tsari don kowane matakin ci gaban ku", "subtitle": "Fara da nunin gwaji, sannan zaɓi tsarin da ya dace da girman kamfaninku.",
        "popular": "Mafi shahara", "priceLabel": "Farashi bisa buƙata",
        "plans": [
            {"tier": "Demo", "title": "Gwada Avenqo tare da bayananku", "priceLabel": "Kyauta", "items": ["Shiga na ɗan lokaci", "Bayanan gwaji ko naku", "Taimako ta imel"], "action": "Nemi nunin gwaji"},
            {"tier": "Professional", "title": "Don kamfanonin da suke son girma", "priceLabel": "Farashi bisa buƙata", "items": ["Duk manyan modules", "Adadin masu amfani mai iya girma", "Taimako mai fifiko"], "action": "Tuntube mu"},
            {"tier": "Enterprise", "title": "Don ƙungiyoyi masu buƙatu na ci gaba", "priceLabel": "Farashi bisa buƙata", "items": ["Haɗin kai na musamman", "Manajan asusun keɓantacce", "Yarjejeniyar matakin sabis"], "action": "Tuntuɓi tallace-tallace"},
        ],
    },
}

COMMON_OVERRIDES = {
    "sw": {"tryFree": "Jaribu Avenqo", "noCreditCard": "Uwekaji wa kibinafsi"},
    "am": {"tryFree": "Avenqo ይሞክሩ", "noCreditCard": "ግላዊነት የተላበሰ ማዋቀር"},
    "af": {"tryFree": "Probeer Avenqo", "noCreditCard": "Gepersonaliseerde opstelling"},
    "ha": {"tryFree": "Gwada Avenqo", "noCreditCard": "Saitin keɓaɓɓen"},
}

FINALCTA_TRYFREE = {code: v["tryFree"] for code, v in COMMON_OVERRIDES.items()}

ASSISTANT_SUGGESTIONS = {
    "sw": ["Ni bidhaa zipi zinazouzwa zaidi mwezi huu?", "Ni wateja gani walio hatarini kuacha kununua?",
           "Fanya muhtasari wa utendaji wa biashara yangu wiki hii.", "Ni fursa zipi za kipaumbele cha juu zaidi sasa?"],
    "am": ["በዚህ ወር በጣም የተሸጡ ምርቶቼ የትኞቹ ናቸው?", "መግዛት ሊያቆሙ የሚችሉ ደንበኞች የትኞቹ ናቸው?",
           "የዚህን ሳምንት የንግድ አፈጻጸሜን ያጠቃልሉ።", "አሁን በጣም ቅድሚያ የሚሰጣቸው እድሎች የትኞቹ ናቸው?"],
    "af": ["Wat is my topverkoperprodukte hierdie maand?", "Watter kliënte is in gevaar om op te hou koop?",
           "Som my besigheidsprestasie hierdie week op.", "Wat is die hoogste prioriteit-geleenthede nou?"],
    "ha": ["Waɗanne kayayyaki ne mafi kyawun sayarwa a wannan watan?", "Waɗanne abokan ciniki ne cikin haɗarin dainawa siyayya?",
           "Taƙaita aikin kasuwancina na wannan makon.", "Waɗanne dama ne mafi muhimmanci a yanzu?"],
}
