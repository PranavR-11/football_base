'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Send, Loader2, ZoomIn, ZoomOut, Maximize2, X, Minimize2 } from 'lucide-react'

// Proper TypeScript interfaces for WebSocket messages
interface BaseMessage {
  type: string
  content?: string
}

interface TextMessage extends BaseMessage {
  type: 'text'
  content: string
}

interface ImageMessage extends BaseMessage {
  type: 'image'
  data: string
  filename?: string
}

interface CompleteMessage extends BaseMessage {
  type: 'complete'
}

interface AckMessage extends BaseMessage {
  type: 'ack'
  content?: string
}

interface ErrorMessage extends BaseMessage {
  type: 'error'
  content: string
}

type WebSocketMessage = TextMessage | ImageMessage | CompleteMessage | AckMessage | ErrorMessage

// UI Message type
type UIMessage = {
  id: string
  type: 'user' | 'assistant' | 'image'
  content: string
  imageData?: string
  timestamp: Date
}

// Generate unique IDs with better collision resistance
const generateMessageId = (): string => {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

// Validate WebSocket message structure
const isValidWebSocketMessage = (data: any): data is WebSocketMessage => {
  return (
    typeof data === 'object' &&
    data !== null &&
    typeof data.type === 'string' &&
    ['text', 'image', 'complete', 'ack', 'error'].includes(data.type)
  )
}

// Simple markdown formatter for basic formatting
const formatMarkdownText = (text: string): string => {
  // First escape HTML to prevent XSS
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;')

  // Then apply formatting
  return escaped
    // Bold: **text** -> <strong>text</strong>
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Newlines to <br> tags
    .replace(/\n/g, '<br>')
}

export default function Home() {
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [currentImage, setCurrentImage] = useState<string | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const [imageZoom, setImageZoom] = useState(100)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)

  // Refs for WebSocket lifecycle
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const currentMessageIdRef = useRef<string | null>(null)
  const accumulatedTextRef = useRef<string>('')

  // Scroll to bottom with layout stability
  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current) {
      // Use requestAnimationFrame to ensure DOM updates are complete
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ 
          behavior: 'smooth',
          block: 'end'
        })
      })
    }
  }, [])

  // Scroll when messages change
  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // Build WebSocket URL with proper validation
  const buildWebSocketUrl = useCallback((): string => {
    // Check for explicit override
    const envUrl = process.env.NEXT_PUBLIC_WS_URL
    if (envUrl && envUrl.length > 0) {
      return envUrl
    }

    // For local development
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      return 'ws://localhost:8000/ws/chat'
    }

    // For production
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    
    // Check for host override
    const envHost = process.env.NEXT_PUBLIC_WS_HOST
    if (envHost && envHost.length > 0) {
      return `${protocol}://${envHost.replace(/\/$/, '')}/ws/chat`
    }

    return `${protocol}://${window.location.host}/ws/chat`
  }, [])

  // Handle WebSocket messages with proper validation
  const handleWebSocketMessage = useCallback((event: MessageEvent) => {
    console.log('[WS] Received message:', event.data)
    let data: any
    try {
      data = JSON.parse(event.data)
      console.log('[WS] Parsed data:', data)
    } catch (err) {
      console.warn('[WS] Received invalid JSON:', err)
      return
    }

    if (!isValidWebSocketMessage(data)) {
      console.warn('[WS] Received invalid message structure:', data)
      return
    }
    console.log('[WS] Processing message type:', data.type)

    switch (data.type) {
      case 'text':
        if (!currentMessageIdRef.current) {
          // Start new message
          const newMessageId = generateMessageId()
          currentMessageIdRef.current = newMessageId
          accumulatedTextRef.current = data.content || ''

          const newMsg: UIMessage = {
            id: newMessageId,
            type: 'assistant',
            content: accumulatedTextRef.current,
            timestamp: new Date()
          }

          setMessages(prev => [...prev, newMsg])
        } else {
          // Update existing message - add newline to preserve formatting
          accumulatedTextRef.current += '\n' + (data.content || '')
          setMessages(prev => prev.map(m =>
            m.id === currentMessageIdRef.current
              ? { ...m, content: accumulatedTextRef.current }
              : m
          ))
        }
        break

      case 'image':
        // Batch state updates to prevent multiple renders
        setImageLoading(false)
        setCurrentImage(data.data)
        
        const imgMsg: UIMessage = {
          id: generateMessageId(),
          type: 'image',
          content: data.filename || 'Generated Chart',
          imageData: data.data,
          timestamp: new Date()
        }
        setMessages(prev => [...prev, imgMsg])
        break

      case 'complete':
        // Reset streaming state
        currentMessageIdRef.current = null
        accumulatedTextRef.current = ''
        setIsLoading(false)
        setImageLoading(false)
        break

      case 'ack':
        // Use explicit field instead of string matching
        if (data.content?.includes('comparison') || data.content?.includes('chart')) {
          setImageLoading(true)
        }
        break

      case 'error':
        console.error('[WS] Server error:', data.content)
        setIsLoading(false)
        setImageLoading(false)
        break

      default:
        console.debug('[WS] Unknown message type:', (data as any).type)
    }
  }, [])

  // WebSocket connection with proper cleanup and reconnection
  const connectWebSocket = useCallback(() => {
    // Clear any existing reconnection timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    // Don't create new connection if one exists and is connecting/open
    if (wsRef.current &&
        (wsRef.current.readyState === WebSocket.CONNECTING ||
         wsRef.current.readyState === WebSocket.OPEN)) {
      console.log('[WS] connectWebSocket: Connection already exists, skipping')
      return
    }

    console.log('[WS] connectWebSocket: Creating new WebSocket connection')

    try {
      const wsUrl = buildWebSocketUrl()
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[WS] Connection opened successfully')
        setIsConnected(true)
        setConnectionError(null)
      }

      ws.onmessage = handleWebSocketMessage

      ws.onerror = (error) => {
        console.error('[WS] Connection error:', error)
        setIsConnected(false)
        setConnectionError('Connection failed')
      }

      ws.onclose = (event) => {
        console.log('[WS] Connection closed. Code:', event.code, 'Reason:', event.reason, 'Clean:', event.wasClean)
        setIsConnected(false)

        // Only attempt reconnection for unexpected closures
        if (event.code !== 1000 && event.code !== 1001) {
          setConnectionError('Connection lost - attempting to reconnect...')

          // Exponential backoff reconnection
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('[WS] Attempting reconnection...')
            connectWebSocket()
          }, 3000)
        } else {
          console.log('[WS] Clean close, not reconnecting')
        }
      }

    } catch (error) {
      console.error('[WS] Failed to create WebSocket:', error)
      setConnectionError('Failed to connect')
    }
  }, [buildWebSocketUrl, handleWebSocketMessage])

  // Initialize WebSocket connection - runs once on mount
  useEffect(() => {
    console.log('[WS] useEffect: Initializing WebSocket connection')
    let mounted = true

    // Create connection
    const initConnection = () => {
      if (!mounted) return

      // Clear any existing reconnection timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }

      // Don't create new connection if one exists and is connecting/open
      if (wsRef.current &&
          (wsRef.current.readyState === WebSocket.CONNECTING ||
           wsRef.current.readyState === WebSocket.OPEN)) {
        console.log('[WS] Connection already exists, skipping')
        return
      }

      console.log('[WS] Creating new WebSocket connection')

      try {
        const wsUrl = buildWebSocketUrl()
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          if (!mounted) return
          console.log('[WS] Connection opened successfully')
          setIsConnected(true)
          setConnectionError(null)
        }

        ws.onmessage = (event: MessageEvent) => {
          if (!mounted) return
          handleWebSocketMessage(event)
        }

        ws.onerror = (error) => {
          if (!mounted) return
          console.error('[WS] Connection error:', error)
          setIsConnected(false)
          setConnectionError('Connection failed')
        }

        ws.onclose = (event) => {
          if (!mounted) return
          console.log('[WS] Connection closed. Code:', event.code, 'Reason:', event.reason)
          setIsConnected(false)

          // Only attempt reconnection for unexpected closures
          if (event.code !== 1000 && event.code !== 1001 && mounted) {
            setConnectionError('Connection lost - attempting to reconnect...')
            reconnectTimeoutRef.current = setTimeout(() => {
              if (mounted) {
                console.log('[WS] Attempting reconnection...')
                initConnection()
              }
            }, 3000)
          }
        }
      } catch (error) {
        console.error('[WS] Failed to create WebSocket:', error)
        if (mounted) {
          setConnectionError('Failed to connect')
        }
      }
    }

    initConnection()

    // Cleanup only runs on true unmount
    return () => {
      console.log('[WS] useEffect: Cleanup called - component unmounting')
      mounted = false

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }

      if (wsRef.current) {
        console.log('[WS] Cleaning up WebSocket, readyState:', wsRef.current.readyState)
        const ws = wsRef.current
        ws.onopen = null
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null

        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          console.log('[WS] Closing WebSocket connection')
          ws.close(1000, 'Component unmounting')
        }

        wsRef.current = null
      }
    }
  }, []) // Empty deps - only run once on mount

  // Send message with proper validation
  const sendMessage = useCallback(() => {
    console.log('[DEBUG] sendMessage called, input:', input)
    const trimmedInput = input.trim()
    console.log('[DEBUG] trimmedInput:', trimmedInput)

    if (!trimmedInput) {
      console.log('[DEBUG] No trimmed input, returning')
      return
    }

    const ws = wsRef.current
    console.log('[DEBUG] WebSocket ref:', ws, 'readyState:', ws?.readyState)

    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.log('[DEBUG] WebSocket not open')
      setConnectionError('Not connected - please wait for reconnection')
      return
    }

    // Clear previous image when starting a new query
    setCurrentImage(null)
    setImageLoading(false)

    const userMsg: UIMessage = {
      id: generateMessageId(),
      type: 'user',
      content: trimmedInput,
      timestamp: new Date()
    }

    console.log('[DEBUG] Adding user message to UI:', userMsg)
    setMessages(prev => [...prev, userMsg])

    try {
      const payload = JSON.stringify({ query: trimmedInput })
      console.log('[DEBUG] Sending to WebSocket:', payload)
      ws.send(payload)
      console.log('[DEBUG] Message sent successfully')
      setInput('')
      setIsLoading(true)
      setConnectionError(null)
    } catch (error) {
      console.error('[WS] Failed to send message:', error)
      setConnectionError('Failed to send message')
      setIsLoading(false)
    }
  }, [input])

  // Handle Enter key with proper event handling
  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendMessage()
    }
  }, [sendMessage])

  // Image zoom controls with bounds checking
  const handleZoomIn = useCallback(() => {
    setImageZoom(prev => Math.min(prev + 20, 200))
  }, [])

  const handleZoomOut = useCallback(() => {
    setImageZoom(prev => Math.max(prev - 20, 50))
  }, [])

  // Fullscreen toggle with proper event handling
  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev)
  }, [])

  // Close fullscreen modal (separate from toggle to prevent bubbling issues)
  const closeFullscreen = useCallback((event: React.MouseEvent) => {
    event.stopPropagation()
    setIsFullscreen(false)
  }, [])

  // Close image panel
  const closeImagePanel = useCallback(() => {
    setCurrentImage(null)
    setImageLoading(false)
    setImageZoom(100)
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-green-950 to-gray-900 relative overflow-hidden">
      {/* Background elements */}
      <div className="absolute inset-0" style={{
        background: `
          radial-gradient(circle at 50% 120%, rgba(34, 197, 94, 0.15) 0%, transparent 50%),
          radial-gradient(circle at 50% -20%, rgba(34, 197, 94, 0.1) 0%, transparent 50%),
          linear-gradient(180deg,
            rgba(6, 78, 59, 0.4) 0%,
            rgba(5, 46, 22, 0.6) 20%,
            rgba(4, 47, 46, 0.5) 40%,
            rgba(5, 46, 22, 0.6) 60%,
            rgba(6, 78, 59, 0.4) 100%
          )
        `
      }} />

      {/* Pitch markings */}
      <div className="absolute inset-0 opacity-[0.03]" style={{
        backgroundImage: `
          linear-gradient(0deg, transparent 48%, rgba(255, 255, 255, 0.4) 49%, rgba(255, 255, 255, 0.4) 51%, transparent 52%),
          linear-gradient(90deg, transparent 48%, rgba(255, 255, 255, 0.4) 49%, rgba(255, 255, 255, 0.4) 51%, transparent 52%)
        `,
        backgroundSize: '200px 200px',
        backgroundPosition: 'center center'
      }} />

      {/* Center circle */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full border-2 border-white/5" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white/5" />

      {/* Vignette effects */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/40" />
      <div className="absolute inset-0 bg-gradient-to-r from-black/20 via-transparent to-black/20" />

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
                {connectionError && (
                  <span className="text-red-400 ml-2">• {connectionError}</span>
                )}
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
                    <p className="text-sm">💬 "Compare Haaland and Mbappe"</p>
                    <p className="text-sm">📊 "Who's the best striker?"</p>
                    <p className="text-sm">🔍 "Tell me about Kevin De Bruyne"</p>
                  </div>
                </div>
              </div>
            )}

            {messages.map(msg => (
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
                      : msg.type === 'image'
                      ? 'bg-gradient-to-br from-blue-800/90 to-blue-900/60 text-white backdrop-blur-sm border border-blue-500/20'
                      : 'bg-gradient-to-br from-gray-800/90 to-green-900/60 text-white backdrop-blur-sm border border-green-500/20'
                  }`}
                >
                  {msg.type === 'image' ? (
                    <div className="text-center">
                      <p className="text-blue-300 font-semibold">📊 {msg.content}</p>
                      <p className="text-blue-200/60 text-sm mt-1">Chart generated - view in side panel</p>
                    </div>
                  ) : (
                    <div
                      dangerouslySetInnerHTML={{
                        __html: formatMarkdownText(msg.content)
                      }}
                    />
                  )}
                </div>
              </div>
            ))}

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
                onKeyDown={handleKeyDown}
                placeholder={
                  !isConnected 
                    ? "Connecting..." 
                    : "⚽ Ask about players, stats, comparisons..."
                }
                className="flex-1 bg-gray-900/80 border-2 border-green-500/30 rounded-xl px-6 py-4 text-white placeholder-green-400/40 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-400 backdrop-blur-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={!isConnected || isLoading}
                title={!isConnected ? "Waiting for connection..." : ""}
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
                onClick={closeImagePanel}
                className="text-white/60 hover:text-white transition-colors"
                aria-label="Close image panel"
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

                {/* Image Container with proper scaling */}
                <div className="flex-1 bg-gradient-to-br from-black/50 to-green-950/30 rounded-xl overflow-hidden relative border border-green-500/20">
                  <div 
                    className="w-full h-full overflow-auto"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      minHeight: '400px'
                    }}
                  >
                    <img
                      src={`data:image/png;base64,${currentImage}`}
                      alt="Analytics chart"
                      className="cursor-zoom-in"
                      style={{
                        transform: `scale(${imageZoom / 100})`,
                        transformOrigin: 'center',
                        transition: 'transform 0.2s ease-out',
                        maxWidth: imageZoom <= 100 ? '100%' : 'none',
                        height: 'auto'
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

      {/* Fullscreen Modal with proper event handling */}
      {isFullscreen && currentImage && (
        <div className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center p-8">
          <button
            onClick={closeFullscreen}
            className="absolute top-4 right-4 text-white/80 hover:text-white z-10"
            aria-label="Close fullscreen"
          >
            <X className="w-8 h-8" />
          </button>
          <img
            src={`data:image/png;base64,${currentImage}`}
            alt="Analytics chart"
            className="max-w-full max-h-full object-contain cursor-pointer"
            onClick={closeFullscreen}
          />
        </div>
      )}
    </div>
  )
}