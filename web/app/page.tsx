'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Send, Loader2, ZoomIn, ZoomOut, Maximize2, X, Minimize2, Download, Globe } from 'lucide-react'

type Message = {
  id: string
  type: 'user' | 'assistant' | 'image'
  content: string
  imageData?: string
  timestamp: Date
}

type Language = 'en' | 'es' | 'fr' | 'ar' | 'pt' | 'ru' | 'ja' | 'de' | 'hi' | 'zh'

const translations: Record<Language, {
  title: string
  subtitle: string
  connected: string
  disconnected: string
  welcome: string
  welcomeSubtitle: string
  tryThese: string
  example1: string
  example2: string
  example3: string
  placeholder: string
  send: string
  analyzing: string
  matchAnalytics: string
  zoomOut: string
  zoomIn: string
  fullscreen: string
  exit: string
  download: string
  analyzingData: string
  crunchingNumbers: string
}> = {
  en: {
    title: "Football Analytics AI",
    subtitle: "Powered by Advanced Stats",
    connected: "LIVE",
    disconnected: "DISCONNECTED",
    welcome: "Welcome to the Pitch!",
    welcomeSubtitle: "Your AI-Powered Football Intelligence Hub",
    tryThese: "Try These:",
    example1: '"Compare Haaland and Kylian Mbappe"',
    example2: '"Top 5 goal scorers in 2023"',
    example3: '"Who is Pedri?"',
    placeholder: "Ask about players, stats, comparisons...",
    send: "Send",
    analyzing: "Analyzing...",
    matchAnalytics: "Match Analytics",
    zoomOut: "Zoom Out",
    zoomIn: "Zoom In",
    fullscreen: "Fullscreen",
    exit: "Exit",
    download: "Download",
    analyzingData: "Analyzing the match data...",
    crunchingNumbers: "Crunching the numbers"
  },
  es: {
    title: "IA de Análisis de Fútbol",
    subtitle: "Impulsado por Estadísticas Avanzadas",
    connected: "EN VIVO",
    disconnected: "DESCONECTADO",
    welcome: "¡Bienvenido al Campo!",
    welcomeSubtitle: "Tu Centro de Inteligencia de Fútbol con IA",
    tryThese: "Prueba Estos:",
    example1: '"Compara Haaland y Kylian Mbappé"',
    example2: '"Top 5 goleadores en 2023"',
    example3: '"¿Quién es Pedri?"',
    placeholder: "Pregunta sobre jugadores, estadísticas, comparaciones...",
    send: "Enviar",
    analyzing: "Analizando...",
    matchAnalytics: "Análisis del Partido",
    zoomOut: "Alejar",
    zoomIn: "Acercar",
    fullscreen: "Pantalla Completa",
    exit: "Salir",
    download: "Descargar",
    analyzingData: "Analizando los datos del partido...",
    crunchingNumbers: "Procesando los números"
  },
  fr: {
    title: "IA d'Analyse de Football",
    subtitle: "Propulsé par des Statistiques Avancées",
    connected: "EN DIRECT",
    disconnected: "DÉCONNECTÉ",
    welcome: "Bienvenue sur le Terrain!",
    welcomeSubtitle: "Votre Hub d'Intelligence Football avec IA",
    tryThese: "Essayez Ceci:",
    example1: '"Comparez Haaland et Kylian Mbappé"',
    example2: '"Top 5 buteurs en 2023"',
    example3: '"Qui est Pedri?"',
    placeholder: "Demandez sur les joueurs, stats, comparaisons...",
    send: "Envoyer",
    analyzing: "Analyse...",
    matchAnalytics: "Analyse du Match",
    zoomOut: "Dézoomer",
    zoomIn: "Zoomer",
    fullscreen: "Plein Écran",
    exit: "Quitter",
    download: "Télécharger",
    analyzingData: "Analyse des données du match...",
    crunchingNumbers: "Traitement des chiffres"
  },
  ar: {
    title: "الذكاء الاصطناعي لتحليل كرة القدم",
    subtitle: "مدعوم بإحصائيات متقدمة",
    connected: "مباشر",
    disconnected: "غير متصل",
    welcome: "!مرحباً بك في الملعب",
    welcomeSubtitle: "مركز معلومات كرة القدم المدعوم بالذكاء الاصطناعي",
    tryThese: ":جرب هذه",
    example1: '"قارن Haaland و Kylian Mbappe"',
    example2: '"أفضل 5 هدافين في 2023"',
    example3: '"من هو Pedri؟"',
    placeholder: "...اسأل عن اللاعبين، الإحصائيات، المقارنات",
    send: "إرسال",
    analyzing: "...جاري التحليل",
    matchAnalytics: "تحليل المباراة",
    zoomOut: "تصغير",
    zoomIn: "تكبير",
    fullscreen: "ملء الشاشة",
    exit: "خروج",
    download: "تحميل",
    analyzingData: "...تحليل بيانات المباراة",
    crunchingNumbers: "معالجة الأرقام"
  },
  pt: {
    title: "IA de Análise de Futebol",
    subtitle: "Alimentado por Estatísticas Avançadas",
    connected: "AO VIVO",
    disconnected: "DESCONECTADO",
    welcome: "Bem-vindo ao Campo!",
    welcomeSubtitle: "Seu Hub de Inteligência de Futebol com IA",
    tryThese: "Experimente:",
    example1: '"Compare Haaland e Kylian Mbappé"',
    example2: '"Top 5 artilheiros em 2023"',
    example3: '"Quem é Pedri?"',
    placeholder: "Pergunte sobre jogadores, estatísticas, comparações...",
    send: "Enviar",
    analyzing: "Analisando...",
    matchAnalytics: "Análise da Partida",
    zoomOut: "Diminuir Zoom",
    zoomIn: "Aumentar Zoom",
    fullscreen: "Tela Cheia",
    exit: "Sair",
    download: "Baixar",
    analyzingData: "Analisando os dados da partida...",
    crunchingNumbers: "Processando os números"
  },
  ru: {
    title: "ИИ для Анализа Футбола",
    subtitle: "На основе продвинутой статистики",
    connected: "В ЭФИРЕ",
    disconnected: "ОТКЛЮЧЕНО",
    welcome: "Добро пожаловать на поле!",
    welcomeSubtitle: "Ваш футбольный центр на базе ИИ",
    tryThese: "Попробуйте:",
    example1: '"Сравните Холанда и Мбаппе"',
    example2: '"Топ-5 бомбардиров 2023"',
    example3: '"Кто такой Педри?"',
    placeholder: "Спросите об игроках, статистике, сравнениях...",
    send: "Отправить",
    analyzing: "Анализ...",
    matchAnalytics: "Анализ Матча",
    zoomOut: "Уменьшить",
    zoomIn: "Увеличить",
    fullscreen: "Полный Экран",
    exit: "Выход",
    download: "Скачать",
    analyzingData: "Анализ данных матча...",
    crunchingNumbers: "Обработка чисел"
  },
  ja: {
    title: "サッカー分析AI",
    subtitle: "高度な統計により駆動",
    connected: "ライブ",
    disconnected: "切断",
    welcome: "ピッチへようこそ！",
    welcomeSubtitle: "AIを活用したサッカーインテリジェンスハブ",
    tryThese: "試してみてください：",
    example1: '"ハーランドとムバッペを比較"',
    example2: '"2023年のトップ5得点者"',
    example3: '"ペドリとは誰ですか？"',
    placeholder: "選手、統計、比較について質問...",
    send: "送信",
    analyzing: "分析中...",
    matchAnalytics: "試合分析",
    zoomOut: "ズームアウト",
    zoomIn: "ズームイン",
    fullscreen: "全画面表示",
    exit: "終了",
    download: "ダウンロード",
    analyzingData: "試合データを分析中...",
    crunchingNumbers: "数字を処理中"
  },
  de: {
    title: "Fußball-Analyse KI",
    subtitle: "Angetrieben von erweiterten Statistiken",
    connected: "LIVE",
    disconnected: "GETRENNT",
    welcome: "Willkommen auf dem Platz!",
    welcomeSubtitle: "Ihr KI-gestütztes Fußball-Intelligence-Hub",
    tryThese: "Versuchen Sie:",
    example1: '"Vergleichen Sie Haaland und Kylian Mbappé"',
    example2: '"Top 5 Torschützen 2023"',
    example3: '"Wer ist Pedri?"',
    placeholder: "Fragen Sie nach Spielern, Statistiken, Vergleichen...",
    send: "Senden",
    analyzing: "Analysieren...",
    matchAnalytics: "Spielanalyse",
    zoomOut: "Verkleinern",
    zoomIn: "Vergrößern",
    fullscreen: "Vollbild",
    exit: "Beenden",
    download: "Herunterladen",
    analyzingData: "Spieldaten werden analysiert...",
    crunchingNumbers: "Zahlen werden verarbeitet"
  },
  hi: {
    title: "फुटबॉल विश्लेषण AI",
    subtitle: "उन्नत आंकड़ों द्वारा संचालित",
    connected: "लाइव",
    disconnected: "डिस्कनेक्ट",
    welcome: "मैदान में आपका स्वागत है!",
    welcomeSubtitle: "आपका AI-संचालित फुटबॉल इंटेलिजेंस हब",
    tryThese: "ये आज़माएं:",
    example1: '"हालैंड और म्बाप्पे की तुलना करें"',
    example2: '"2023 में शीर्ष 5 गोल स्कोरर"',
    example3: '"पेड्री कौन है?"',
    placeholder: "खिलाड़ियों, आंकड़ों, तुलनाओं के बारे में पूछें...",
    send: "भेजें",
    analyzing: "विश्लेषण...",
    matchAnalytics: "मैच विश्लेषण",
    zoomOut: "ज़ूम आउट",
    zoomIn: "ज़ूम इन",
    fullscreen: "पूर्ण स्क्रीन",
    exit: "बाहर निकलें",
    download: "डाउनलोड",
    analyzingData: "मैच डेटा का विश्लेषण...",
    crunchingNumbers: "संख्याओं को संसाधित करना"
  },
  zh: {
    title: "足球分析人工智能",
    subtitle: "由高级统计数据驱动",
    connected: "直播",
    disconnected: "已断开",
    welcome: "欢迎来到球场！",
    welcomeSubtitle: "您的AI驱动的足球智能中心",
    tryThese: "试试这些：",
    example1: '"比较哈兰德和姆巴佩"',
    example2: '"2023年前5名射手"',
    example3: '"佩德里是谁？"',
    placeholder: "询问球员、统计数据、比较...",
    send: "发送",
    analyzing: "分析中...",
    matchAnalytics: "比赛分析",
    zoomOut: "缩小",
    zoomIn: "放大",
    fullscreen: "全屏",
    exit: "退出",
    download: "下载",
    analyzingData: "分析比赛数据...",
    crunchingNumbers: "处理数字中"
  }
}

const languageNames: Record<Language, string> = {
  en: 'English',
  es: 'Español',
  fr: 'Français',
  ar: 'العربية',
  pt: 'Português',
  ru: 'Русский',
  ja: '日本語',
  de: 'Deutsch',
  hi: 'हिन्दी',
  zh: '中文'
}

// Map language codes to backend language names
const languageToBackend: Record<Language, string> = {
  en: 'English',
  es: 'Spanish',
  fr: 'French',
  ar: 'Arabic',
  pt: 'Portuguese',
  ru: 'Russian',
  ja: 'Japanese',
  de: 'German',
  hi: 'Hindi',
  zh: 'Chinese'
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [currentImage, setCurrentImage] = useState<string | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const [imageZoom, setImageZoom] = useState(80)  // Default to 80% for better radar chart visibility
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [language, setLanguage] = useState<Language>('en')
  const [videoStartTime, setVideoStartTime] = useState(0)
  const videoRef = useRef<HTMLVideoElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const currentMessageIdRef = useRef<string | null>(null)
  const accumulatedTextRef = useRef<string>('')
  const lastQueryRef = useRef<string>('')
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)

  const t = translations[language]

  // Set random start time when component mounts and handle video loading
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const handleLoadedMetadata = () => {
      // Random start between 0 and video duration (or 60 seconds max)
      const maxStart = Math.min(video.duration - 5, 60) // Leave 5 seconds at end
      const randomStart = Math.random() * maxStart
      video.currentTime = randomStart
      console.log(`Video starting at random time: ${randomStart.toFixed(2)}s`)
    }

    // Set random time when video metadata is loaded
    if (video.readyState >= 1) {
      // Metadata already loaded
      handleLoadedMetadata()
    } else {
      // Wait for metadata to load
      video.addEventListener('loadedmetadata', handleLoadedMetadata)
    }

    return () => {
      video.removeEventListener('loadedmetadata', handleLoadedMetadata)
    }
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    const connectWebSocket = () => {
      // Guard: if socket already exists and is open/connecting, skip creation
      if (wsRef.current &&
          (wsRef.current.readyState === WebSocket.OPEN ||
           wsRef.current.readyState === WebSocket.CONNECTING)) {
        console.debug('⚠️ WebSocket already exists — skipping duplicate creation')
        return
      }

      console.count('ws-effect-run')

      // Dynamic protocol selection for production
      const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws'
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || `${proto}://localhost:8000/ws/chat`

      console.log('Creating WebSocket connection to:', wsUrl)
      const ws = new WebSocket(wsUrl)

      // Set ref immediately to prevent race conditions
      wsRef.current = ws

      ws.onopen = () => {
        console.log('✅ WebSocket connected')
        setIsConnected(true)
        reconnectAttemptsRef.current = 0 // Reset reconnect attempts on successful connection
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          // Ignore keepalive pings
          if (data.type === 'ping') {
            return
          }

          if (data.type === 'text') {
            // Accumulate text lines into a single message
            if (!currentMessageIdRef.current) {
              // Start a new message
              const newMessageId = Date.now().toString()
              currentMessageIdRef.current = newMessageId
              accumulatedTextRef.current = data.content
              setMessages(prev => [
                ...prev,
                {
                  id: newMessageId,
                  type: 'assistant',
                  content: data.content,
                  timestamp: new Date()
                }
              ])
            } else {
              // Append to existing message
              accumulatedTextRef.current += '\n' + data.content
              const msgId = currentMessageIdRef.current
              const accumulated = accumulatedTextRef.current
              setMessages(prev => prev.map(msg =>
                msg.id === msgId
                  ? { ...msg, content: accumulated }
                  : msg
              ))
            }
          } else if (data.type === 'image') {
            setImageLoading(false)
            setCurrentImage(data.data)
            setMessages(prev => [
              ...prev,
              {
                id: Date.now().toString(),
                type: 'image',
                content: data.filename,
                imageData: data.data,
                timestamp: new Date()
              }
            ])
          } else if (data.type === 'complete') {
            // Finalize the current message
            currentMessageIdRef.current = null
            accumulatedTextRef.current = ''
            setIsLoading(false)
            setImageLoading(false)
          } else if (data.type === 'ack') {
            // Start fresh for new query
            currentMessageIdRef.current = null
            accumulatedTextRef.current = ''
            // Check if this looks like a comparison query using ref
            if (lastQueryRef.current.toLowerCase().includes('compar')) {
              setImageLoading(true)
            }
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error)
        setIsConnected(false)
      }

      ws.onclose = (event) => {
        console.log('🔌 WebSocket closed:', event.code, event.reason)
        setIsConnected(false)
        // Clear ref only if this is the current socket
        if (wsRef.current === ws) {
          wsRef.current = null
        }

        // Attempt to reconnect with exponential backoff
        const maxAttempts = 5
        const attempt = reconnectAttemptsRef.current

        if (attempt < maxAttempts) {
          // Exponential backoff: 1s, 2s, 4s, 8s, 16s
          const delay = Math.min(1000 * Math.pow(2, attempt), 16000)
          console.log(`🔄 Reconnecting in ${delay}ms (attempt ${attempt + 1}/${maxAttempts})...`)

          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1
            connectWebSocket()
          }, delay)
        } else {
          console.error('❌ Max reconnection attempts reached. Please refresh the page.')
        }
      }
    }

    // Initial connection new update
    connectWebSocket()

    return () => {
      console.log('Cleaning up WebSocket connection')

      // Clear reconnection timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }

      try {
        const ws = wsRef.current
        if (ws) {
          ws.onopen = null
          ws.onmessage = null
          ws.onerror = null
          ws.onclose = null
          // Only close if this is still the active socket
          if (wsRef.current === ws) {
            ws.close()
            wsRef.current = null
          }
        }
      } catch (e) {
        console.warn('Error during WebSocket cleanup:', e)
      }
    }
  }, []) // Empty dependency array - run once on mount

  const sendMessage = useCallback((customQuery?: string) => {
    const ws = wsRef.current
    const query = (customQuery || input).trim()

    if (!query || !ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('Cannot send message:', {
        hasQuery: !!query,
        hasWs: !!ws,
        readyState: ws?.readyState
      })
      return
    }

    // Store query in ref for comparison check
    lastQueryRef.current = query

    // Add user message (optimistic UI update)
    setMessages(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        type: 'user',
        content: query,
        timestamp: new Date()
      }
    ])

    // Send to server with UI language
    console.log('Sending message:', query, 'Language:', languageToBackend[language])
    ws.send(JSON.stringify({
      query,
      language: languageToBackend[language]
    }))
    setInput('')
    setIsLoading(true)
  }, [input, language])

  const handleZoomIn = () => {
    setImageZoom(prev => Math.min(prev + 20, 200))
  }

  const handleZoomOut = () => {
    setImageZoom(prev => Math.max(prev - 20, 50))
  }

  const toggleFullscreen = () => {
    setIsFullscreen(prev => !prev)
  }

  const downloadImage = () => {
    if (!currentImage) return

    const link = document.createElement('a')
    link.href = `data:image/png;base64,${currentImage}`
    link.download = `football-analytics-${Date.now()}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  useEffect(() => {
    if (typeof document === 'undefined') return

    if (isFullscreen) {
      document.body.classList.add('fullscreen-open')
    } else {
      document.body.classList.remove('fullscreen-open')
    }

    return () => {
      document.body.classList.remove('fullscreen-open')
    }
  }, [isFullscreen])

  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Full-Screen Background Video - Always playing */}
      <div className="absolute inset-0" style={{ zIndex: 0 }}>
        <video
          ref={videoRef}
          autoPlay
          loop
          muted
          playsInline
          className="absolute inset-0 w-full h-full object-cover"
          style={{
            filter: 'brightness(0.8) saturate(1.0)',
          }}
        >
          <source src="/videos/video.mp4" type="video/mp4" />
        </video>

        {/* Subtle green tint overlay */}
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-900/20 via-green-950/25 to-teal-900/20"></div>

        {/* Edge vignette - keeps edges darker */}
        <div className="absolute inset-0 bg-gradient-radial from-transparent via-transparent to-black/50"></div>
      </div>

      {/* Light green gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-950/30 via-green-900/25 to-teal-950/30" style={{ zIndex: 1 }}></div>

      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
        .bg-gradient-radial {
          background: radial-gradient(circle at center, transparent 0%, rgba(0,0,0,0.2) 50%, rgba(0,0,0,0.6) 100%);
        }
      `}</style>

      {/* Animated football icons */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {/* <div className="absolute top-20 left-10 text-6xl opacity-5 animate-pulse">⚽</div>
        <div className="absolute top-40 right-20 text-5xl opacity-5 animate-pulse" style={{animationDelay: '1s'}}>🏆</div>
        <div className="absolute bottom-32 left-1/4 text-4xl opacity-5 animate-pulse" style={{animationDelay: '2s'}}>⚽</div>
        <div className="absolute bottom-20 right-1/3 text-5xl opacity-5 animate-pulse" style={{animationDelay: '0.5s'}}>🥅</div> */}
      </div>

      {/* Header */}
      <header className="bg-gradient-to-r from-green-950/80 via-emerald-900/80 to-green-950/80 backdrop-blur-md border-b-2 border-yellow-500/30 shadow-2xl relative z-10">
        <div className="max-w-full mx-auto px-3 sm:px-6 py-3 sm:py-6">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 sm:gap-4 flex-1 min-w-0">
              <div className="text-3xl sm:text-5xl">⚽</div>
              <div className="min-w-0">
                <h1 className="text-xl sm:text-2xl md:text-3xl lg:text-4xl font-bold bg-gradient-to-r from-green-400 via-emerald-300 to-teal-400 bg-clip-text text-transparent truncate">
                  {t.title}
                </h1>
                <p className="text-emerald-400 mt-1 text-xs sm:text-sm font-semibold tracking-wide truncate">
                  {isConnected ? `🟢 ${t.connected} • ${t.subtitle}` : `🔴 ${t.disconnected}`}
                </p>
              </div>
            </div>

            {/* Language Selector */}
            <div className="relative flex-shrink-0">
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as Language)}
                className="bg-green-900/50 border-2 border-green-500/30 rounded-lg px-2 sm:px-4 py-2 text-white text-sm sm:text-base font-semibold cursor-pointer hover:bg-green-800/60 focus:outline-none focus:ring-2 focus:ring-green-500 transition-all appearance-none pr-8 sm:pr-10 backdrop-blur-sm"
              >
                {(Object.keys(languageNames) as Language[]).map((lang) => (
                  <option key={lang} value={lang} className="bg-gray-900">
                    {languageNames[lang]}
                  </option>
                ))}
              </select>
              <Globe className="absolute right-2 sm:right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 sm:w-5 sm:h-5 text-green-400 pointer-events-none" />
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-full mx-auto px-2 sm:px-4 py-4 sm:py-8 flex flex-col lg:flex-row gap-4 relative z-10 h-[calc(100vh-80px)] sm:h-[calc(100vh-100px)] lg:h-[calc(100vh-140px)]">
        {/* Chat Container - Always full width on mobile, split on desktop when image present */}
        <div className={`bg-gradient-to-br from-gray-900/40 via-green-950/50 to-gray-900/40 backdrop-blur-xl rounded-2xl sm:rounded-3xl shadow-2xl border-2 border-green-400/40 overflow-hidden transition-all duration-500 flex flex-col ${
          currentImage || imageLoading
            ? 'w-full lg:w-1/2'
            : messages.length === 0
              ? 'w-full max-w-3xl mx-auto'
              : 'w-full max-w-5xl mx-auto'
        }`} style={{ backdropFilter: 'blur(20px) saturate(180%)' }}>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 sm:p-6 space-y-4 bg-gradient-to-b from-black/20 to-transparent relative">
            {messages.length === 0 && (
              <div className="text-center text-white/70 mt-8 sm:mt-16 lg:mt-32 relative z-10">
                <div className="text-4xl sm:text-6xl mb-4 sm:mb-6 animate-bounce">⚽</div>
                <h2 className="text-2xl sm:text-3xl font-bold mb-3 sm:mb-4 bg-gradient-to-r from-green-400 to-emerald-300 bg-clip-text text-transparent px-4">
                  {t.welcome}
                </h2>
                <p className="text-base sm:text-xl mb-4 sm:mb-6 text-green-300/90 px-4">
                  {t.welcomeSubtitle}
                </p>
                <div className="mt-6 sm:mt-8">
                  <p className="text-xs sm:text-sm font-semibold text-green-400 mb-4 sm:mb-6 tracking-wide">✨ {t.tryThese}</p>
                  <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 max-w-5xl mx-auto justify-center px-4">
                    <button
                      onClick={() => sendMessage(t.example1.replace(/"/g, ''))}
                      disabled={!isConnected}
                      className="bg-gradient-to-br from-green-900/30 to-emerald-900/30 hover:from-green-800/50 hover:to-emerald-800/50 backdrop-blur-md border border-green-400/30 hover:border-green-300/60 rounded-xl sm:rounded-2xl px-4 sm:px-6 py-4 sm:py-5 transition-all duration-300 hover:scale-105 hover:-translate-y-1 hover:shadow-lg hover:shadow-green-500/30 disabled:opacity-50 disabled:cursor-not-allowed group flex-1 max-w-xs"
                      style={{ backdropFilter: 'blur(12px)' }}
                    >
                      <div className="flex flex-col items-center gap-2 text-center">
                        <span className="text-2xl sm:text-3xl group-hover:scale-110 transition-transform duration-300">💬</span>
                        <span className="text-white font-medium text-xs sm:text-sm group-hover:text-green-300 transition-colors">
                          {t.example1.replace(/"/g, '')}
                        </span>
                      </div>
                    </button>
                    <button
                      onClick={() => sendMessage(t.example2.replace(/"/g, ''))}
                      disabled={!isConnected}
                      className="bg-gradient-to-br from-green-900/30 to-emerald-900/30 hover:from-green-800/50 hover:to-emerald-800/50 backdrop-blur-md border border-green-400/30 hover:border-green-300/60 rounded-xl sm:rounded-2xl px-4 sm:px-6 py-4 sm:py-5 transition-all duration-300 hover:scale-105 hover:-translate-y-1 hover:shadow-lg hover:shadow-green-500/30 disabled:opacity-50 disabled:cursor-not-allowed group flex-1 max-w-xs"
                      style={{ backdropFilter: 'blur(12px)' }}
                    >
                      <div className="flex flex-col items-center gap-2 text-center">
                        <span className="text-2xl sm:text-3xl group-hover:scale-110 transition-transform duration-300">📊</span>
                        <span className="text-white font-medium text-xs sm:text-sm group-hover:text-green-300 transition-colors">
                          {t.example2.replace(/"/g, '')}
                        </span>
                      </div>
                    </button>
                    <button
                      onClick={() => sendMessage(t.example3.replace(/"/g, ''))}
                      disabled={!isConnected}
                      className="bg-gradient-to-br from-green-900/30 to-emerald-900/30 hover:from-green-800/50 hover:to-emerald-800/50 backdrop-blur-md border border-green-400/30 hover:border-green-300/60 rounded-xl sm:rounded-2xl px-4 sm:px-6 py-4 sm:py-5 transition-all duration-300 hover:scale-105 hover:-translate-y-1 hover:shadow-lg hover:shadow-green-500/30 disabled:opacity-50 disabled:cursor-not-allowed group flex-1 max-w-xs"
                      style={{ backdropFilter: 'blur(12px)' }}
                    >
                      <div className="flex flex-col items-center gap-2 text-center">
                        <span className="text-2xl sm:text-3xl group-hover:scale-110 transition-transform duration-300">🔍</span>
                        <span className="text-white font-medium text-xs sm:text-sm group-hover:text-green-300 transition-colors">
                          {t.example3.replace(/"/g, '')}
                        </span>
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {messages.map(msg => {
              if (msg.type === 'image') return null // Don't show images inline anymore

              return (
                <div
                  key={msg.id}
                  className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`${
                      msg.type === 'user' ? 'max-w-[85%] sm:max-w-lg' : 'max-w-[95%] sm:max-w-4xl'
                    } px-4 sm:px-6 py-3 sm:py-4 rounded-xl sm:rounded-2xl shadow-lg ${
                      msg.type === 'user'
                        ? 'bg-gradient-to-br from-green-600 to-emerald-700 text-white border border-green-400/30'
                        : 'bg-gradient-to-br from-gray-800/90 to-green-900/60 text-white backdrop-blur-sm border border-green-500/20'
                    }`}
                  >
                    {msg.type === 'user' ? (
                      <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                    ) : (
                      <div className="prose prose-invert max-w-none">
                        <div className="space-y-2 overflow-y-auto pr-2 scrollbar-thin">
                          {msg.content.split('\n').map((line, i) => {
                            // Check if line is all caps (headings like OVERVIEW, GOAL SCORING VS PLAYMAKING)
                            const isHeading = /^[A-Z\s&]+$/.test(line.trim()) && line.trim().length > 2

                            if (line.startsWith('###')) {
                              return (
                                <h3 key={i} className="text-emerald-400 font-bold text-base sm:text-lg mt-4 first:mt-0 break-words">
                                  {line.replace('###', '').trim()}
                                </h3>
                              )
                            } else if (isHeading) {
                              return (
                                <h3 key={i} className="text-emerald-400 font-bold text-base sm:text-lg mt-4 mb-2 first:mt-0 break-words">
                                  {line.trim()}
                                </h3>
                              )
                            }
                            return line ? <p key={i} className="text-gray-100 text-sm sm:text-base leading-relaxed break-words">{line}</p> : <br key={i} />
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gradient-to-br from-gray-800/90 to-green-900/60 backdrop-blur-sm px-6 py-4 rounded-2xl border border-green-500/20 flex items-center gap-3">
                  <Loader2 className="w-6 h-6 text-green-400 animate-spin" />
                  <span className="text-green-300 text-sm font-semibold">{t.analyzing}</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="flex-shrink-0 border-t-2 border-green-500/30 p-3 sm:p-6 bg-gradient-to-r from-black/40 via-green-950/40 to-black/40 backdrop-blur-md">
            {/* Data coverage disclaimer */}
            <div className="text-[10px] sm:text-xs text-green-300/70 mb-2 sm:mb-3 text-center">
              Data: Europe Top-5 leagues (2021–mid-2025, domestic seasons only)
            </div>
            <div className="flex gap-2 sm:gap-4">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                placeholder={`⚽ ${t.placeholder}`}
                className="flex-1 bg-gray-900/80 border-2 border-green-500/30 rounded-lg sm:rounded-xl px-3 sm:px-6 py-3 sm:py-4 text-sm sm:text-base text-white placeholder-green-400/40 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-400 backdrop-blur-sm transition-all"
                disabled={!isConnected || isLoading}
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck="false"
              />
              <button
                onClick={() => sendMessage()}
                disabled={!isConnected || isLoading || !input.trim()}
                className="bg-gradient-to-r from-green-600 to-emerald-700 hover:from-green-500 hover:to-emerald-600 disabled:from-gray-600 disabled:to-gray-700 disabled:cursor-not-allowed text-white px-4 sm:px-8 py-3 sm:py-4 rounded-lg sm:rounded-xl text-sm sm:text-base font-bold transition-all shadow-lg flex items-center gap-1 sm:gap-2 border border-green-400/30"
              >
                <Send className="w-4 h-4 sm:w-5 sm:h-5" />
                <span className="hidden sm:inline">{t.send}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Floating Chart Button (Mobile Only) */}
        {(currentImage || imageLoading) && (
          <button
            onClick={() => setIsFullscreen(true)}
            className="lg:hidden fixed bottom-24 right-4 z-30 bg-gradient-to-r from-green-600 to-emerald-700 hover:from-green-500 hover:to-emerald-600 text-white p-4 rounded-full shadow-2xl border-2 border-green-400/50 flex items-center gap-2 animate-pulse"
          >
            <span className="text-2xl">📊</span>
            <span className="font-bold text-sm">{t.matchAnalytics}</span>
          </button>
        )}

        {/* Image Viewer Panel (Desktop Only) */}
        {(currentImage || imageLoading) && (
          <div className="hidden lg:flex w-full lg:w-1/2 bg-gradient-to-br from-gray-900/40 via-green-950/50 to-gray-900/40 backdrop-blur-xl rounded-2xl sm:rounded-3xl shadow-2xl border-2 border-green-400/40 p-3 sm:p-6 flex-col" style={{ backdropFilter: 'blur(20px) saturate(180%)' }}>
            <div className="flex items-center justify-between mb-3 sm:mb-4">
              <h2 className="text-base sm:text-xl font-bold bg-gradient-to-r from-green-400 to-emerald-300 bg-clip-text text-transparent">📊 {t.matchAnalytics}</h2>
              <button
                onClick={() => {
                  setCurrentImage(null)
                  setImageLoading(false)
                  setImageZoom(80)
                }}
                className="text-white/60 hover:text-white transition-colors"
              >
                <X className="w-5 h-5 sm:w-6 sm:h-6" />
              </button>
            </div>

            {imageLoading && !currentImage && (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-4xl sm:text-6xl mb-4 animate-bounce">⚽</div>
                  <Loader2 className="w-8 h-8 sm:w-12 sm:h-12 text-green-400 animate-spin mx-auto mb-4" />
                  <p className="text-sm sm:text-base text-green-300 font-semibold">{t.analyzingData}</p>
                  <p className="text-green-500/60 text-xs sm:text-sm mt-2">{t.crunchingNumbers} 📊</p>
                </div>
              </div>
            )}

            {currentImage && (
              <>
                {/* Zoom Controls */}
                <div className="flex flex-wrap gap-1 sm:gap-2 mb-3 sm:mb-4">
                  <button
                    onClick={handleZoomOut}
                    disabled={imageZoom <= 50}
                    className="bg-green-900/50 hover:bg-green-800/60 disabled:opacity-50 disabled:cursor-not-allowed text-green-300 px-2 sm:px-4 py-1.5 sm:py-2 rounded-lg transition-colors flex items-center gap-1 sm:gap-2 border border-green-500/30 text-xs sm:text-sm"
                  >
                    <ZoomOut className="w-3 h-3 sm:w-4 sm:h-4" />
                    <span className="hidden sm:inline">{t.zoomOut}</span>
                  </button>
                  <button
                    onClick={handleZoomIn}
                    disabled={imageZoom >= 200}
                    className="bg-green-900/50 hover:bg-green-800/60 disabled:opacity-50 disabled:cursor-not-allowed text-green-300 px-2 sm:px-4 py-1.5 sm:py-2 rounded-lg transition-colors flex items-center gap-1 sm:gap-2 border border-green-500/30 text-xs sm:text-sm"
                  >
                    <ZoomIn className="w-3 h-3 sm:w-4 sm:h-4" />
                    <span className="hidden sm:inline">{t.zoomIn}</span>
                  </button>
                  <button
                    onClick={toggleFullscreen}
                    className="bg-green-900/50 hover:bg-green-800/60 text-green-300 px-2 sm:px-4 py-1.5 sm:py-2 rounded-lg transition-colors flex items-center gap-1 sm:gap-2 border border-green-500/30 text-xs sm:text-sm"
                  >
                    {isFullscreen ? <Minimize2 className="w-3 h-3 sm:w-4 sm:h-4" /> : <Maximize2 className="w-3 h-3 sm:w-4 sm:h-4" />}
                    <span className="hidden sm:inline">{isFullscreen ? t.exit : t.fullscreen}</span>
                  </button>
                  <button
                    onClick={downloadImage}
                    className="bg-gradient-to-r from-green-700/60 to-emerald-700/60 hover:from-green-600/70 hover:to-emerald-600/70 text-white px-2 sm:px-4 py-1.5 sm:py-2 rounded-lg transition-colors flex items-center gap-1 sm:gap-2 border border-green-400/40 font-semibold text-xs sm:text-sm"
                  >
                    <Download className="w-3 h-3 sm:w-4 sm:h-4" />
                    <span className="hidden sm:inline">{t.download}</span>
                  </button>
                  <span className="bg-gradient-to-r from-green-900/60 to-emerald-900/60 text-green-300 font-bold px-2 sm:px-4 py-1.5 sm:py-2 rounded-lg ml-auto border border-green-500/30 text-xs sm:text-sm">
                    {imageZoom}%
                  </span>
                </div>

                {/* Image Container */}
                <div className="flex-1 bg-gradient-to-br from-black/50 to-green-950/30 rounded-xl overflow-auto relative border border-green-500/20">
                  <div className="min-h-full flex items-center justify-center p-2 sm:p-4">
                    <img
                      src={`data:image/png;base64,${currentImage}`}
                      alt="Comparison chart"
                      style={{
                        transform: `scale(${imageZoom / 100})`,
                        transformOrigin: 'center',
                        transition: 'transform 0.2s ease-out',
                        maxWidth: '100%',
                        height: 'auto',
                        cursor: 'zoom-in'
                      }}
                      onClick={toggleFullscreen}
                    />
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </main>

      {/* Fullscreen Modal */}
      {isFullscreen && currentImage && (
        <div className="fullscreen-modal" onClick={toggleFullscreen}>
          <div
            className="chart-wrapper flex flex-col bg-gradient-to-b from-gray-900/90 via-gray-900/95 to-black/95 border border-emerald-500/30 text-white"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header with controls */}
            <div className="flex items-center justify-between gap-3 p-4 border-b border-emerald-500/20 bg-black/40 backdrop-blur">
              <h2 className="text-lg sm:text-xl font-bold text-green-200 flex items-center gap-2">
                <span className="text-2xl">📊</span>
                {t.matchAnalytics}
              </h2>
              <div className="flex items-center gap-2">
                <button
                  aria-label={t.download}
                  onClick={(e) => {
                    e.stopPropagation()
                    downloadImage()
                  }}
                  className="bg-emerald-600/70 hover:bg-emerald-500/80 text-white p-2 rounded-lg transition-colors"
                >
                  <Download className="w-5 h-5" />
                </button>
                <button
                  aria-label={t.exit}
                  onClick={toggleFullscreen}
                  className="bg-red-600/70 hover:bg-red-500/80 text-white p-2 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Image container */}
            <div className="chart-canvas flex-1 flex items-center justify-center">
              <div className="flex h-full w-full items-center justify-center overflow-auto p-4">
                <img
                  src={`data:image/png;base64,${currentImage}`}
                  alt="Comparison chart"
                  className="max-h-full max-w-full object-contain"
                  style={{
                    transform: `scale(${imageZoom / 100})`,
                    transformOrigin: 'center',
                    transition: 'transform 0.2s ease-out'
                  }}
                />
              </div>
            </div>

            {/* Zoom controls */}
            <div className="flex flex-wrap items-center justify-center gap-2 p-4 border-t border-emerald-500/20 bg-black/40 backdrop-blur">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleZoomOut()
                }}
                disabled={imageZoom <= 50}
                className="bg-emerald-700/70 hover:bg-emerald-600/70 disabled:opacity-40 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
              >
                <ZoomOut className="w-4 h-4" />
                <span className="text-sm">{t.zoomOut}</span>
              </button>
              <span className="text-emerald-200 font-bold px-4 py-2 rounded-lg bg-emerald-950/60 border border-emerald-500/30 min-w-[80px] text-center">
                {imageZoom}%
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleZoomIn()
                }}
                disabled={imageZoom >= 200}
                className="bg-emerald-700/70 hover:bg-emerald-600/70 disabled:opacity-40 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
              >
                <ZoomIn className="w-4 h-4" />
                <span className="text-sm">{t.zoomIn}</span>
              </button>
            </div>
            <p className="text-center text-emerald-50/70 text-xs pb-2 pt-1">{t.placeholder.includes('Tap') ? 'Tap outside to close' : 'Tap anywhere to close'}</p>
          </div>
        </div>
      )}
    </div>
  )
}
