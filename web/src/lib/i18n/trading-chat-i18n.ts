import type { LocaleCode } from "./types";

export interface TradingChatStrings {
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
}

const CHAT_DICTIONARY: Record<string, TradingChatStrings> = {
  fr: {
    title: "Assistant Trading AI",
    badge: "Gemini Pro Live",
    subtitle: "Dialogue fluide & analyse technique quantifiée",
    welcome: (symbol, interval) =>
      `Bonjour ! Je suis l'analyste de marché Avenqo Trading AI propulsé par Google Gemini. Je suis spécialisé dans l'analyse quantitative en temps réel (Price Action, RSI 14, histogramme MACD, Bandes de Bollinger, moyennes mobiles et invalidations) pour **${symbol}** (${interval}).\n\nPosez-moi vos questions techniques ou choisissez une question spécialisée ci-dessous pour démarrer une conversation fluide.`,
    reset: (symbol, interval) =>
      `Conversation réinitialisée. Prêt pour une nouvelle analyse technique de **${symbol}** sur l'intervalle ${interval}. Que souhaitez-vous analyser ?`,
    loading: (symbol) => `Gemini analyse les indicateurs et la structure de ${symbol}...`,
    error: "Désolé, impossible d'effectuer l'analyse en direct actuellement. Vérifiez la connexion aux flux de marché.",
    voicePrompt: (symbol, interval) =>
      `Analyse le ${symbol} et résume les confluences techniques majeures sur l'intervalle ${interval}.`,
    specializedQuestionsLabel: "Questions spécialisées :",
    shuffleQuestionsLabel: "Nouvelles questions",
    inputPlaceholder: "Posez votre question technique à Gemini...",
    clearChatTooltip: "Effacer la conversation",
    voiceTooltip: "Activer le mode vocal",
    questions: [
      "Détectes-tu une divergence haussière ou baissière sur le RSI 14 et les dernières clôtures ?",
      "L'histogramme MACD montre-t-il une décélération ou un renforcement du momentum ?",
      "Le RSI 14 actuel signale-t-il un risque d'essoufflement ou une zone de surchauffe ?",
      "Observe-t-on une divergence cachée de continuation sur le momentum court terme ?",
      "Comment se positionne le RSI par rapport au niveau neutre des 50 sur cet intervalle ?",
      "L'écartement des lignes MACD confirme-t-il la force de l'impulsion en cours ?",
      "Quels sont les niveaux majeurs de support et de résistance calculés d'après les récents extrêmes ?",
      "Où se situe le niveau d'invalidation critique si l'on prend un biais acheteur sur cet intervalle ?",
      "Y a-t-il un risque de fausse cassure (bull trap ou bear trap) sur la dernière bougie ?",
      "La structure récente forme-t-elle des sommets plus hauts (Higher Highs) ou une compression ?",
      "À quel niveau de cours un retournement de tendance court terme serait-il confirmé ?",
      "Que révèle la contraction actuelle des bandes de Bollinger sur l'imminence d'un breakout ?",
      "Le cours évolue-t-il en sur-extension par rapport aux bandes de Bollinger ?",
      "La volatilité récente est-elle en phase de compression (Squeeze) ou d'expansion directionnelle ?",
      "Quel est l'alignement entre l'EMA 12, la SMA 20 et la moyenne 26 périodes ?",
      "Quelles sont les confluences techniques (RSI + MACD + MA) observables sur cet intervalle ?",
    ],
  },
  en: {
    title: "Trading AI Assistant",
    badge: "Gemini Pro Live",
    subtitle: "Fluent conversation & quantitative technical analysis",
    welcome: (symbol, interval) =>
      `Hello! I am the Avenqo Trading AI market analyst powered by Google Gemini. I specialize in real-time quantitative analysis (Price Action, RSI 14, MACD histogram, Bollinger Bands, moving averages, and invalidation levels) for **${symbol}** (${interval}).\n\nAsk me any technical analysis question or select a specialized prompt below to begin.`,
    reset: (symbol, interval) =>
      `Conversation reset. Ready for a new technical analysis of **${symbol}** on the ${interval} timeframe. What would you like to explore?`,
    loading: (symbol) => `Gemini is analyzing technical indicators and structure for ${symbol}...`,
    error: "Sorry, live analysis is temporarily unavailable. Please verify market feed connectivity.",
    voicePrompt: (symbol, interval) =>
      `Analyze ${symbol} and summarize the key technical confluences on the ${interval} timeframe.`,
    specializedQuestionsLabel: "Specialized questions:",
    shuffleQuestionsLabel: "New questions",
    inputPlaceholder: "Ask Gemini your technical analysis question...",
    clearChatTooltip: "Clear conversation",
    voiceTooltip: "Toggle voice mode",
    questions: [
      "Do you detect a bullish or bearish divergence between RSI 14 and recent price closes?",
      "Does the MACD histogram indicate momentum deceleration or accelerating impulse?",
      "Does current RSI 14 signal exhaustion risk or an overbought condition?",
      "Is there a hidden continuation divergence on short-term momentum?",
      "How is RSI positioned relative to the neutral 50 level on this timeframe?",
      "Does the widening of the MACD lines confirm the strength of the current impulse?",
      "What are the major support and resistance levels based on recent swing extremes?",
      "Where is the critical invalidation level for a bullish bias on this timeframe?",
      "Is there a risk of a fake breakout (bull trap or bear trap) on the latest candle?",
      "Does the recent structure form Higher Highs or a tightening price compression?",
      "At what price level would a short-term trend reversal be confirmed?",
      "What does the current Bollinger Bands squeeze indicate about an imminent breakout?",
      "Is price trading at an over-extended level relative to the outer Bollinger Bands?",
      "Is recent volatility in a compression (Squeeze) or directional expansion phase?",
      "What is the alignment between EMA 12, SMA 20, and the 26-period moving average?",
      "What technical confluences (RSI + MACD + MA) do you observe right now?",
    ],
  },
  es: {
    title: "Asistente Trading AI",
    badge: "Gemini Pro Live",
    subtitle: "Diálogo fluido y análisis técnico cuantitativo",
    welcome: (symbol, interval) =>
      `¡Hola! Soy el analista de mercado Avenqo Trading AI impulsado por Google Gemini. Me especializo en análisis cuantitativo en tiempo real (Price Action, RSI 14, histograma MACD, bandas de Bollinger, medias móviles y niveles de invalidación) para **${symbol}** (${interval}).\n\nHazme tus preguntas técnicas o selecciona una pregunta especializada abajo para comenzar.`,
    reset: (symbol, interval) =>
      `Conversación reiniciada. Listo para un nuevo análisis técnico de **${symbol}** en el marco temporal ${interval}. ¿Qué deseas analizar?`,
    loading: (symbol) => `Gemini está analizando los indicadores y la estructura de ${symbol}...`,
    error: "Disculpa, el análisis en directo no está disponible actualmente. Verifica la conexión a los datos de mercado.",
    voicePrompt: (symbol, interval) =>
      `Analiza ${symbol} y resume las principales confluencias técnicas en el marco ${interval}.`,
    specializedQuestionsLabel: "Preguntas especializadas:",
    shuffleQuestionsLabel: "Nuevas preguntas",
    inputPlaceholder: "Hazle tu pregunta técnica a Gemini...",
    clearChatTooltip: "Borrar conversación",
    voiceTooltip: "Activar modo de voz",
    questions: [
      "¿Detectas alguna divergencia alcista o bajista entre el RSI 14 y los cierres recientes?",
      "¿Muestra el histograma MACD una desaceleración o un fortalecimiento del impulso?",
      "¿Señala el RSI 14 actual un riesgo de agotamiento o una zona de sobrecompra?",
      "¿Se observa una divergencia oculta de continuación en el impulso a corto plazo?",
      "¿Cómo se sitúa el RSI respecto al nivel neutral de 50 en este marco temporal?",
      "¿Confirma la separación de las líneas del MACD la fuerza del movimiento actual?",
      "¿Cuáles son los niveles clave de soporte y resistencia según los extremos recientes?",
      "¿Dónde se ubica el nivel de invalidación crítico para una postura compradora?",
      "¿Existe riesgo de una falsa ruptura (bull trap o bear trap) en la última vela?",
      "¿La estructura reciente forma máximos más altos (Higher Highs) o una compresión?",
      "¿A qué nivel de precio se confirmaría un cambio de tendencia a corto plazo?",
      "¿Qué revela la contracción de las bandas de Bollinger sobre una inminente ruptura?",
      "¿El precio cotiza en sobre-extensión respecto a las bandas de Bollinger?",
      "¿La volatilidad reciente está en fase de compresión (Squeeze) o de expansión?",
      "¿Cuál es la alineación entre la EMA 12, la SMA 20 y el promedio de 26 períodos?",
      "¿Qué confluencias técnicas (RSI + MACD + medias móviles) observas actualmente?",
    ],
  },
  ro: {
    title: "Asistent Trading AI",
    badge: "Gemini Pro Live",
    subtitle: "Dialog fluent și analiză tehnică cantitativă",
    welcome: (symbol, interval) =>
      `Bună ziua! Sunt analistul de piață Avenqo Trading AI propulsat de Google Gemini. Sunt specializat în analiza cantitativă în timp real (Price Action, RSI 14, histograma MACD, benzile Bollinger, medii mobile și invalidări) pentru **${symbol}** (${interval}).\n\nAdresați-mi întrebările dvs. tehnice sau alegeți o întrebare specializată de mai jos pentru a începe un dialog fluent.`,
    reset: (symbol, interval) =>
      `Conversație resetată. Gata pentru o nouă analiză tehnică a activului **${symbol}** pe intervalul ${interval}. Ce doriți să analizăm?`,
    loading: (symbol) => `Gemini analizează indicatorii tehnici și structura pentru ${symbol}...`,
    error: "Ne pare rău, analiza în direct nu este disponibilă în acest moment. Verificați conexiunea la fluxurile de piață.",
    voicePrompt: (symbol, interval) =>
      `Analizează ${symbol} și sintetizează confluențele tehnice majore pe intervalul ${interval}.`,
    specializedQuestionsLabel: "Întrebări specializate:",
    shuffleQuestionsLabel: "Întrebări noi",
    inputPlaceholder: "Adresează întrebarea ta tehnică către Gemini...",
    clearChatTooltip: "Șterge conversația",
    voiceTooltip: "Activează modul vocal",
    questions: [
      "Detectezi o divergență bullish sau bearish între RSI 14 și ultimele prețuri de închidere?",
      "Arată histograma MACD o decelerare sau o accelerare a impulsului de piață?",
      "Indică valoarea curentă a RSI 14 un risc de epuizare sau o zonă de supracumpărare?",
      "Există vreo divergență ascunsă de continuare pe momentum-ul pe termen scurt?",
      "Cum este poziționat RSI față de nivelul neutru de 50 pe acest interval de timp?",
      "Confirmă distanțarea liniilor MACD forța impulsului în derulare?",
      "Care sunt nivelurile majore de suport și rezistență bazate pe ultimele extreme locale?",
      "Unde se află nivelul critic de invalidare pentru o perspectivă cumpărătoare?",
      "Există un risc de spargere falsă (bull trap sau bear trap) pe ultima lumânare?",
      "Formează structura recentă maxime mai înalte (Higher Highs) sau o comprimare a prețului?",
      "La ce nivel de preț ar fi confirmată o inversare a trendului pe termen scurt?",
      "Ce dezvăluie comprimarea benzilor Bollinger despre iminența unei spargeri de volatilitate?",
      "Se tranzacționează prețul în supra-extindere față de benzile Bollinger superioare sau inferioare?",
      "Este volatilitatea recentă într-o fază de contracție (Squeeze) sau de expansiune direcțională?",
      "Care este alinierea dintre EMA 12, SMA 20 și media mobilă de 26 de perioade?",
      "Ce confluențe tehnice (RSI + MACD + medii mobile) observi pe acest interval?",
    ],
  },
  de: {
    title: "Trading AI Assistent",
    badge: "Gemini Pro Live",
    subtitle: "Flüssiger Dialog & quantitative technische Analyse",
    welcome: (symbol, interval) =>
      `Guten Tag! Ich bin der Avenqo Trading AI Marktanalyst powered by Google Gemini. Ich bin spezialisiert auf quantitative Echtzeitanalyse (Price Action, RSI 14, MACD-Histogramm, Bollinger-Bänder, gleitende Durchschnitte und Invalidierungsmarken) für **${symbol}** (${interval}).\n\nStellen Sie mir Ihre technischen Fragen oder wählen Sie eine spezialisierte Frage unten aus, um zu beginnen.`,
    reset: (symbol, interval) =>
      `Konversation zurückgesetzt. Bereit für eine neue technische Analyse von **${symbol}** im Zeitfenster ${interval}. Was möchten Sie analysieren?`,
    loading: (symbol) => `Gemini analysiert die technischen Indikatoren und die Struktur von ${symbol}...`,
    error: "Die Live-Analyse ist derzeit nicht verfügbar. Bitte überprüfen Sie die Marktdatenverbindung.",
    voicePrompt: (symbol, interval) =>
      `Analysiere ${symbol} und fasse die wichtigsten technischen Konfluenzen im Zeitfenster ${interval} zusammen.`,
    specializedQuestionsLabel: "Spezialisierte Fragen:",
    shuffleQuestionsLabel: "Neue Fragen",
    inputPlaceholder: "Stellen Sie Ihre technische Frage an Gemini...",
    clearChatTooltip: "Konversation löschen",
    voiceTooltip: "Sprachmodus umschalten",
    questions: [
      "Erkennst du eine bullische oder bärische Divergenz zwischen dem RSI 14 und den Schlusskursen?",
      "Zeigt das MACD-Histogramm eine Verlangsamung oder Beschleunigung des Momentums?",
      "Signalisiert der aktuelle RSI 14 ein Erschöpfungsrisiko oder einen überkauften Bereich?",
      "Gibt es eine versteckte Fortsetzungsdivergenz beim kurzfristigen Momentum?",
      "Wie positioniert sich der RSI im Vergleich zur neutralen 50er-Linie in diesem Zeitfenster?",
      "Bestätigt die Aufweitung der MACD-Linien die Stärke des laufenden Impulses?",
      "Was sind die wichtigsten Unterstützungs- und Widerstandsniveaus basierend auf den jüngsten Extrempunkten?",
      "Wo liegt das kritische Invalidierungsniveau für eine Kaufposition in diesem Intervall?",
      "Besteht das Risiko eines Fehlausbruchs (Bull-Trap oder Bear-Trap) bei der letzten Kerze?",
      "Bildet die jüngste Marktstruktur höhere Hochs (Higher Highs) oder eine Preisverengung?",
      "Bei welchem Kursniveau wäre eine kurzfristige Trendumkehr bestätigt?",
      "Was verrät der aktuelle Bollinger-Bänder-Squeeze über einen bevorstehenden Ausbruch?",
      "Bewegt sich der Kurs in einer Überextension bezüglich der äußeren Bollinger-Bänder?",
      "Befindet sich die Volatilität in einer Kompressions- (Squeeze) oder Expansionsphase?",
      "Wie sieht die Ausrichtung zwischen EMA 12, SMA 20 und dem 26-Perioden-Durchschnitt aus?",
      "Welche technischen Konfluenzen (RSI + MACD + gleitende Durchschnitte) beobachtest du aktuell?",
    ],
  },
  ja: {
    title: "Trading AI アシスタント",
    badge: "Gemini Pro Live",
    subtitle: "スムーズな対話とリアルタイム定量テクニカル分析",
    welcome: (symbol, interval) =>
      `こんにちは！Google Geminiを搭載したAvenqo Trading AIマーケットアナリストです。**${symbol}**（${interval}）のリアルタイム定量分析（プライスアクション、RSI 14、MACDヒストグラム、ボリンジャーバンド、移動平均線、無効化水準）を専門としています。\n\nテクニカルな質問を入力するか、下の専門的なプロンプトを選択して分析を開始してください。`,
    reset: (symbol, interval) =>
      `会話をリセットしました。**${symbol}**（${interval}）の新しいテクニカル分析の準備が整いました。何を分析しますか？`,
    loading: (symbol) => `Geminiが${symbol}のテクニカル指標と市場構造を分析中...`,
    error: "申し訳ありません。リアルタイム分析は現在利用できません。市場データ接続を確認してください。",
    voicePrompt: (symbol, interval) =>
      `${symbol}を分析し、${interval}時間枠における主要なテクニカル合致を要約してください。`,
    specializedQuestionsLabel: "専門的な質問：",
    shuffleQuestionsLabel: "新しい質問",
    inputPlaceholder: "Geminiにテクニカル分析の質問をする...",
    clearChatTooltip: "会話を消去",
    voiceTooltip: "音声モード切替",
    questions: [
      "RSI 14と直近の終値の間に強気または弱気のダイバージェンスが確認できますか？",
      "MACDヒストグラムはモメンタムの減速または加速を示していますか？",
      "現在のRSI 14は過熱感やモメンタムの枯渇リスクを示唆していますか？",
      "短期モメンタムにおいてヒドゥン・コンティニュエーション・ダイバージェンスは見られますか？",
      "この時間枠におけるRSIは中立レベルの50に対してどのように位置していますか？",
      "MACDラインの拡大は現在の推進波の強さを裏付けていますか？",
      "直近のスイング高値・安値に基づく主要なサポートおよびレジスタンスはどこですか？",
      "この時間枠で買い目線を取る場合の重要な無効化（損切り）水準はどこですか？",
      "最新のローソク足でダマシ（ブルトラップまたはベアトラップ）のリスクはありますか？",
      "直近の価格構造は高値更新（Higher Highs）と値幅収縮のどちらを示していますか？",
      "短期トレンドの反転が確定する価格水準はどこですか？",
      "ボリンジャーバンドのスクイーズ（収縮）はブレイクアウトの切迫性について何を示していますか？",
      "現在価格はボリンジャーバンドの外側に対して過度な乖離を示していますか？",
      "最近のボラティリティは圧縮（スクイーズ）局面ですか、それとも拡散局面ですか？",
      "EMA 12、SMA 20、および26期間移動平均線の並び順（アライメント）はどうですか？",
      "現在観測されるテクニカルな合致（RSI + MACD + 移動平均線）は何ですか？",
    ],
  },
  ar: {
    title: "مساعد التداول بالذكاء الاصطناعي",
    badge: "Gemini Pro Live",
    subtitle: "حوار سلس وتحليل فني كمي فوري",
    welcome: (symbol, interval) =>
      `مرحباً! أنا محلل السوق Avenqo Trading AI المدعوم بتقنية Google Gemini. متخصص في التحليل الفني الكمي الفوري (حركة السعر، مؤشر RSI 14، مدرج MACD، نطاقات بولينجر، المتوسطات المتحركة ومستويات الإلغاء) لزوج **${symbol}** (${interval}).\n\nاطرح أسئلتك الفنية أو اختر سؤالاً متخصصاً أدناه لبدء المحادثة.`,
    reset: (symbol, interval) =>
      `تمت إعادة تعيين المحادثة. جاهز لتحليل فني جديد لزوج **${symbol}** على الإطار الزمني ${interval}. ماذا تود أن نحلل؟`,
    loading: (symbol) => `جيميني يحلل المؤشرات الفنية وهيكل السوق لـ ${symbol}...`,
    error: "عذراً، التحليل المباشر غير متاح حالياً. يرجى التحقق من اتصال بيانات السوق.",
    voicePrompt: (symbol, interval) =>
      `حلل ${symbol} ولخص التوافقات الفنية الرئيسية على الإطار الزمني ${interval}.`,
    specializedQuestionsLabel: "أسئلة فنية متخصصة:",
    shuffleQuestionsLabel: "أسئلة جديدة",
    inputPlaceholder: "اطرح سؤالك الفني على جيميني...",
    clearChatTooltip: "مسح المحادثة",
    voiceTooltip: "تبديل الوضع الصوتي",
    questions: [
      "هل تلاحظ وجود تباعد إيجابي أو سلبي بين مؤشر RSI 14 والإغلاقات السعرية الأخيرة؟",
      "هل يظهر مدرج MACD تباطؤاً في الزخم أم تسارعاً في القوة السعرية؟",
      "هل يشير مؤشر RSI 14 الحالي إلى تشبع شرائي أو خطر استنزاف الاتجاه؟",
      "هل هناك أي تباعد خفي استمراري في الزخم على المدى القصير؟",
      "أين يتمركز مؤشر RSI مقارنة بمستوى 50 المحايد على هذا الإطار الزمني؟",
      "هل يؤكد اتساع خطوط MACD قوة الحركة الاندفاعية الحالية؟",
      "ما هي مستويات الدعم والمقاومة الرئيسية المستندة إلى القمم والقيعان الأخيرة؟",
      "أين يقع مستوى إلغاء السيناريو الصاعد الحرج على هذا الإطار الزمني؟",
      "هل هناك خطر حدوث كسر وهمي (فخ صاعد أو فخ هابط) على الشمعة الأخيرة؟",
      "هل يشكل الهيكل السعري الأخير قمم أعلى أم مرحلة ضغط سعري؟",
      "عند أي مستوى سعري سيتم تأكيد انعكاس الاتجاه على المدى القصير؟",
      "ماذا يكشف انضغاط نطاقات بولينجر عن اقتراب انفجار سعري؟",
      "هل يتحرك السعر في منطقة تمدد مفرط مقارنة بنطاقات بولينجر الخارجية؟",
      "هل التقلبات السعرية في مرحلة انضغاط أم توسع اتجاهي؟",
      "كيف هو ترتيب المتوسطات المتحركة EMA 12 و SMA 20 ومتوسط 26 فترة؟",
      "ما هي التوافقات الفنية الحالية بين RSI و MACD والمتوسطات المتحركة؟",
    ],
  },
  it: {
    title: "Assistente Trading AI",
    badge: "Gemini Pro Live",
    subtitle: "Dialogo fluido e analisi tecnica quantitativa",
    welcome: (symbol, interval) =>
      `Buongiorno! Sono l'analista di mercato Avenqo Trading AI supportato da Google Gemini. Sono specializzato nell'analisi quantitativa in tempo reale (Price Action, RSI 14, istogramma MACD, bande di Bollinger, medie mobili e invalidazioni) per **${symbol}** (${interval}).\n\nPoni le tue domande tecniche o scegli una domanda specializzata qui sotto per iniziare una conversazione fluida.`,
    reset: (symbol, interval) =>
      `Conversazione reimpostata. Pronto per una nuova analisi tecnica di **${symbol}** sul timeframe ${interval}. Cosa desideri analizzare?`,
    loading: (symbol) => `Gemini sta analizzando gli indicatori e la struttura di ${symbol}...`,
    error: "L'analisi in tempo reale non è attualmente disponibile. Verifica la connessione ai dati di mercato.",
    voicePrompt: (symbol, interval) =>
      `Analizza ${symbol} e riassumi le principali confluenze tecniche sul timeframe ${interval}.`,
    specializedQuestionsLabel: "Domande specializzate:",
    shuffleQuestionsLabel: "Nuove domande",
    inputPlaceholder: "Fai la tua domanda tecnica a Gemini...",
    clearChatTooltip: "Cancella conversazione",
    voiceTooltip: "Attiva modalità vocale",
    questions: [
      "Rilevi una divergenza rialzista o ribassista sull'RSI 14 e le ultime chiusure?",
      "L'istogramma MACD mostra una decelerazione o un rafforzamento del momentum?",
      "L'RSI 14 attuale segnala un rischio di esaurimento o un'area di ipercomprato?",
      "Si osserva una divergenza nascosta di continuazione sul momentum di breve termine?",
      "Come si posiziona l'RSI rispetto al livello neutro di 50 su questo timeframe?",
      "Il distanziamento delle linee MACD conferma la forza dell'impulso attuale?",
      "Quali sono i livelli chiave di supporto e resistenza basati sui recenti estremi?",
      "Dove si trova il livello critico di invalidazione per un bias rialzista?",
      "C'è il rischio di una falsa rottura (bull trap o bear trap) sull'ultima candela?",
      "La struttura recente forma massimi crescenti (Higher Highs) o una compressione?",
      "A quale livello di prezzo verrebbe confermata un'inversione di trend a breve termine?",
      "Cosa rivela la contrazione delle bande di Bollinger sull'imminenza di un breakout?",
      "Il prezzo si muove in sovra-estensione rispetto alle bande di Bollinger?",
      "La volatilità recente è in fase di compressione (Squeeze) o di espansione?",
      "Qual è l'allineamento tra EMA 12, SMA 20 e la media mobile a 26 periodi?",
      "Quali confluenze tecniche (RSI + MACD + medie mobili) osservi attualmente?",
    ],
  },
  pt: {
    title: "Assistente Trading AI",
    badge: "Gemini Pro Live",
    subtitle: "Diálogo fluido e análise técnica quantitativa",
    welcome: (symbol, interval) =>
      `Olá! Sou o analista de mercado Avenqo Trading AI desenvolvido com Google Gemini. Sou especializado em análise quantitativa em tempo real (Price Action, RSI 14, histograma MACD, bandas de Bollinger, médias móveis e invalidações) para **${symbol}** (${interval}).\n\nFaça suas perguntas técnicas ou escolha uma pergunta especializada abaixo para iniciar.`,
    reset: (symbol, interval) =>
      `Conversa reiniciada. Pronto para uma nova análise técnica de **${symbol}** no período ${interval}. O que gostaria de analisar?`,
    loading: (symbol) => `Gemini está analisando os indicadores técnicos e a estrutura de ${symbol}...`,
    error: "A análise em tempo real está temporariamente indisponível. Verifique a conexão com os fluxos de mercado.",
    voicePrompt: (symbol, interval) =>
      `Analise ${symbol} e resuma as principais confluências técnicas no intervalo ${interval}.`,
    specializedQuestionsLabel: "Perguntas especializadas:",
    shuffleQuestionsLabel: "Novas perguntas",
    inputPlaceholder: "Faça sua pergunta técnica ao Gemini...",
    clearChatTooltip: "Limpar conversa",
    voiceTooltip: "Ativar modo de voz",
    questions: [
      "Detecta alguma divergência de alta ou de baixa entre o RSI 14 e os últimos fechamentos?",
      "O histograma MACD mostra desaceleração ou fortalecimento do momentum?",
      "O RSI 14 atual sinaliza risco de esgotamento ou uma zona de sobrecompra?",
      "Observa-se uma divergência oculta de continuação no momentum de curto prazo?",
      "Como o RSI está posicionado em relação ao nível neutro de 50 neste período?",
      "O afastamento das linhas do MACD confirma a força do impulso atual?",
      "Quais são os principais níveis de suporte e resistência com base nas máximas e mínimas recentes?",
      "Onde fica o nível crítico de invalidação para uma perspectiva compradora?",
      "Existe risco de rompimento falso (bull trap ou bear trap) no último candle?",
      "A estrutura recente forma topos mais altos (Higher Highs) ou uma compressão?",
      "Em qual nível de preço uma reversão de tendência de curto prazo seria confirmada?",
      "O que a contração das bandas de Bollinger revela sobre um rompimento iminente?",
      "O preço está sendo negociado em sobre-extensão em relação às bandas de Bollinger?",
      "A volatilidade recente está em fase de compressão (Squeeze) ou expansão direcional?",
      "Qual é o alinhamento entre a EMA 12, a SMA 20 e a média de 26 períodos?",
      "Quais confluências técnicas (RSI + MACD + médias móveis) você observa atualmente?",
    ],
  },
};

export function getTradingChatStrings(locale: LocaleCode | string): TradingChatStrings {
  const code = (locale || "fr").toLowerCase();
  if (CHAT_DICTIONARY[code]) {
    return CHAT_DICTIONARY[code];
  }
  const prefix = code.split("-")[0];
  if (CHAT_DICTIONARY[prefix]) {
    return CHAT_DICTIONARY[prefix];
  }
  return CHAT_DICTIONARY.en || CHAT_DICTIONARY.fr;
}

export function pickRandomTradingQuestions(locale: LocaleCode | string, count: number = 3): string[] {
  const strings = getTradingChatStrings(locale);
  const pool = strings.questions && strings.questions.length > 0 ? strings.questions : CHAT_DICTIONARY.en.questions;
  const shuffled = [...pool].sort(() => 0.5 - Math.random());
  return shuffled.slice(0, count);
}
