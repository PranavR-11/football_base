'use client'

import { useState, useEffect, useRef } from 'react'
import { Send, Loader2, ZoomIn, ZoomOut, Maximize2, X, Minimize2 } from 'lucide-react'

type Message = {
  id: string
  type: 'user' | 'assistant' | 'image'
  content: string
  imageData?: string
  timestamp: Date
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [currentImage, setCurrentImage] = useState<string | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const [imageZoom, setImageZoom] = useState(100)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/chat'
    const ws = new WebSocket(wsUrl)
    let currentMessageId: string | null = null
    let accumulatedText = ''

    ws.onopen = () => {
      console.log('Connected to server')
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'text') {
        // Accumulate text lines into a single message
        if (!currentMessageId) {
          // Start a new message
          const newMessageId = Date.now().toString()
          currentMessageId = newMessageId
          accumulatedText = data.content
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
          accumulatedText += '\n' + data.content
          const msgId = currentMessageId  // Capture for closure
          setMessages(prev => prev.map(msg =>
            msg.id === msgId
              ? { ...msg, content: accumulatedText }
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
        currentMessageId = null
        accumulatedText = ''
        setIsLoading(false)
        setImageLoading(false)
      } else if (data.type === 'ack') {
        // Start fresh for new query
        currentMessageId = null
        accumulatedText = ''
        // Check if this looks like a comparison query
        if (input.toLowerCase().includes('compar')) {
          setImageLoading(true)
        }
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setIsConnected(false)
    }

    ws.onclose = () => {
      console.log('Disconnected from server')
      setIsConnected(false)
    }

    wsRef.current = ws

    return () => {
      ws.close()
    }
  }, [])

  const sendMessage = () => {
    if (!input.trim() || !wsRef.current || !isConnected) return

    // Add user message
    setMessages(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        type: 'user',
        content: input,
        timestamp: new Date()
      }
    ])

    // Send to server
    wsRef.current.send(JSON.stringify({ query: input }))
    setInput('')
    setIsLoading(true)
  }

  const handleZoomIn = () => {
    setImageZoom(prev => Math.min(prev + 20, 200))
  }

  const handleZoomOut = () => {
    setImageZoom(prev => Math.max(prev - 20, 50))
  }

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-950 via-green-900 to-teal-950 relative overflow-hidden">
      {/* Football pitch pattern overlay */}
      <div className="absolute inset-0 opacity-10" style={{
        backgroundImage: `
          linear-gradient(0deg, transparent 24%, rgba(255, 255, 255, .05) 25%, rgba(255, 255, 255, .05) 26%, transparent 27%, transparent 74%, rgba(255, 255, 255, .05) 75%, rgba(255, 255, 255, .05) 76%, transparent 77%, transparent),
          linear-gradient(90deg, transparent 24%, rgba(255, 255, 255, .05) 25%, rgba(255, 255, 255, .05) 26%, transparent 27%, transparent 74%, rgba(255, 255, 255, .05) 75%, rgba(255, 255, 255, .05) 76%, transparent 77%, transparent)
        `,
        backgroundSize: '50px 50px'
      }}></div>

      {/* Animated football icons */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 text-6xl opacity-5 animate-pulse">⚽</div>
        <div className="absolute top-40 right-20 text-5xl opacity-5 animate-pulse" style={{animationDelay: '1s'}}>🏆</div>
        <div className="absolute bottom-32 left-1/4 text-4xl opacity-5 animate-pulse" style={{animationDelay: '2s'}}>⚽</div>
        <div className="absolute bottom-20 right-1/3 text-5xl opacity-5 animate-pulse" style={{animationDelay: '0.5s'}}>🥅</div>
      </div>

      {/* Header */}
      <header className="bg-gradient-to-r from-green-950/80 via-emerald-900/80 to-green-950/80 backdrop-blur-md border-b-2 border-yellow-500/30 shadow-2xl relative z-10">
        <div className="max-w-full mx-auto px-6 py-6">
          <div className="flex items-center gap-4">
            <div className="text-5xl">⚽</div>
            <div>
              <h1 className="text-4xl font-bold bg-gradient-to-r from-green-400 via-emerald-300 to-teal-400 bg-clip-text text-transparent flex items-center gap-3">
                Football Analytics AI
              </h1>
              <p className="text-emerald-400 mt-1 text-sm font-semibold tracking-wide">
                {isConnected ? '🟢 LIVE • Powered by Advanced Stats' : '🔴 DISCONNECTED'}
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-full mx-auto px-4 py-8 flex gap-4 relative z-10">
        {/* Chat Container */}
        <div className={`bg-gradient-to-br from-gray-900/90 via-green-950/90 to-gray-900/90 backdrop-blur-lg rounded-3xl shadow-2xl border-2 border-green-500/30 overflow-hidden transition-all ${
          currentImage || imageLoading ? 'w-1/2' : 'w-full max-w-6xl mx-auto'
        }`}>
          {/* Messages */}
          <div className="h-[600px] overflow-y-auto p-6 space-y-4 bg-gradient-to-b from-black/20 to-transparent">
            {messages.length === 0 && (
              <div className="text-center text-white/70 mt-32">
                <div className="text-6xl mb-6 animate-bounce">⚽</div>
                <h2 className="text-3xl font-bold mb-4 bg-gradient-to-r from-green-400 to-emerald-300 bg-clip-text text-transparent">
                  Welcome to the Pitch!
                </h2>
                <p className="text-xl mb-6 text-green-300/90">
                  Your AI-Powered Football Intelligence Hub
                </p>
                <div className="mt-8 space-y-3 text-white/60">
                  <div className="bg-green-900/30 border border-green-500/30 rounded-xl p-4 max-w-md mx-auto">
                    <p className="text-sm font-semibold text-green-400 mb-2">🎯 Try These:</p>
                    <p className="text-sm">💬 &quot;Compare Haaland and Mbappe&quot;</p>
                    <p className="text-sm">📊 &quot;Top 5 goal scorers in 2023&quot;</p>
                    <p className="text-sm">🔍 &quot;Who is Pedri?&quot;</p>
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
                      msg.type === 'user' ? 'max-w-lg' : 'max-w-4xl'
                    } px-6 py-4 rounded-2xl shadow-lg ${
                      msg.type === 'user'
                        ? 'bg-gradient-to-br from-green-600 to-emerald-700 text-white border border-green-400/30'
                        : 'bg-gradient-to-br from-gray-800/90 to-green-900/60 text-white backdrop-blur-sm border border-green-500/20'
                    }`}
                  >
                    {msg.type === 'user' ? (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <div className="prose prose-invert max-w-none">
                        {msg.content.includes('###') ? (
                          // Format markdown-style analysis
                          <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
                            {msg.content.split('###').map((section, idx) => {
                              if (idx === 0) return null // Skip empty first section
                              const [title, ...contentLines] = section.trim().split('\n')
                              return (
                                <div key={idx} className="border-l-2 border-blue-400 pl-4">
                                  <h3 className="font-bold text-blue-300 mb-1">{title}</h3>
                                  <p className="text-sm text-white/90 leading-relaxed">
                                    {contentLines.join('\n').trim()}
                                  </p>
                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <p className="whitespace-pre-wrap">{msg.content}</p>
                        )}
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
                  <span className="text-green-300 text-sm font-semibold">Analyzing...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t-2 border-green-500/30 p-6 bg-gradient-to-r from-black/40 via-green-950/40 to-black/40 backdrop-blur-md">
            <div className="flex gap-4">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                placeholder="⚽ Ask about players, stats, comparisons..."
                className="flex-1 bg-gray-900/80 border-2 border-green-500/30 rounded-xl px-6 py-4 text-white placeholder-green-400/40 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-400 backdrop-blur-sm transition-all"
                disabled={!isConnected || isLoading}
              />
              <button
                onClick={sendMessage}
                disabled={!isConnected || isLoading || !input.trim()}
                className="bg-gradient-to-r from-green-600 to-emerald-700 hover:from-green-500 hover:to-emerald-600 disabled:from-gray-600 disabled:to-gray-700 disabled:cursor-not-allowed text-white px-8 py-4 rounded-xl font-bold transition-all shadow-lg flex items-center gap-2 border border-green-400/30"
              >
                <Send className="w-5 h-5" />
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Image Viewer Panel */}
        {(currentImage || imageLoading) && (
          <div className="w-1/2 bg-gradient-to-br from-gray-900/90 via-green-950/90 to-gray-900/90 backdrop-blur-lg rounded-3xl shadow-2xl border-2 border-green-500/30 p-6 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold bg-gradient-to-r from-green-400 to-emerald-300 bg-clip-text text-transparent">📊 Match Analytics</h2>
              <button
                onClick={() => {
                  setCurrentImage(null)
                  setImageLoading(false)
                  setImageZoom(100)
                }}
                className="text-white/60 hover:text-white transition-colors"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            {imageLoading && !currentImage && (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-6xl mb-4 animate-bounce">⚽</div>
                  <Loader2 className="w-12 h-12 text-green-400 animate-spin mx-auto mb-4" />
                  <p className="text-green-300 font-semibold">Analyzing the match data...</p>
                  <p className="text-green-500/60 text-sm mt-2">Crunching the numbers 📊</p>
                </div>
              </div>
            )}

            {currentImage && (
              <>
                {/* Zoom Controls */}
                <div className="flex gap-2 mb-4">
                  <button
                    onClick={handleZoomOut}
                    disabled={imageZoom <= 50}
                    className="bg-green-900/50 hover:bg-green-800/60 disabled:opacity-50 disabled:cursor-not-allowed text-green-300 px-4 py-2 rounded-lg transition-colors flex items-center gap-2 border border-green-500/30"
                  >
                    <ZoomOut className="w-4 h-4" />
                    Zoom Out
                  </button>
                  <button
                    onClick={handleZoomIn}
                    disabled={imageZoom >= 200}
                    className="bg-green-900/50 hover:bg-green-800/60 disabled:opacity-50 disabled:cursor-not-allowed text-green-300 px-4 py-2 rounded-lg transition-colors flex items-center gap-2 border border-green-500/30"
                  >
                    <ZoomIn className="w-4 h-4" />
                    Zoom In
                  </button>
                  <button
                    onClick={toggleFullscreen}
                    className="bg-green-900/50 hover:bg-green-800/60 text-green-300 px-4 py-2 rounded-lg transition-colors flex items-center gap-2 border border-green-500/30"
                  >
                    {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                    {isFullscreen ? 'Exit' : 'Fullscreen'}
                  </button>
                  <span className="bg-gradient-to-r from-green-900/60 to-emerald-900/60 text-green-300 font-bold px-4 py-2 rounded-lg ml-auto border border-green-500/30">
                    {imageZoom}%
                  </span>
                </div>

                {/* Image Container */}
                <div className="flex-1 bg-gradient-to-br from-black/50 to-green-950/30 rounded-xl overflow-auto relative border border-green-500/20">
                  <div className="min-h-full flex items-center justify-center p-4">
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
        <div
          className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center p-8"
          onClick={toggleFullscreen}
        >
          <button
            onClick={toggleFullscreen}
            className="absolute top-4 right-4 text-white/80 hover:text-white"
          >
            <X className="w-8 h-8" />
          </button>
          <img
            src={`data:image/png;base64,${currentImage}`}
            alt="Comparison chart"
            className="max-w-full max-h-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  )
}
