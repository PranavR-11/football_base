# 🏆 Football Analytics Web App - Deployment Guide

## Architecture Overview

```
User Browser → Next.js Frontend (Netlify) → FastAPI Backend (Railway) → Agent → MCP Server
```

## What I've Built For You

✅ **Backend API** (`api/main.py`):
- FastAPI server that wraps your langchain agent
- WebSocket support for real-time chat
- Automatic image detection and base64 encoding
- Streams responses to frontend

✅ **API Requirements** (`api/requirements.txt`):
- All dependencies for the FastAPI server

## Complete Setup Instructions

### Part 1: Set Up the Frontend (Next.js)

1. **Initialize Next.js project in the `web` directory:**
```bash
cd web
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir
```

When prompted, choose:
- ✅ TypeScript
- ✅ ESLint
- ✅ Tailwind CSS
- ✅ App Router
- ❌ No src/ directory
- ❌ No import alias customization

2. **Install additional dependencies:**
```bash
npm install lucide-react clsx tailwind-merge
```

3. **Create the chat page** (`web/app/page.tsx`):
```typescript
'use client'

import { useState, useEffect, useRef } from 'react'
import { Send, Loader2 } from 'lucide-react'

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
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // WebSocket connection
  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/chat'
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('Connected to server')
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'text') {
        setMessages(prev => [
          ...prev,
          {
            id: Date.now().toString(),
            type: 'assistant',
            content: data.content,
            timestamp: new Date()
          }
        ])
      } else if (data.type === 'image') {
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
        setIsLoading(false)
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-900 via-green-800 to-blue-900">
      {/* Header */}
      <header className="bg-black/30 backdrop-blur-sm border-b border-white/10">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <h1 className="text-4xl font-bold text-white flex items-center gap-3">
            ⚽ Football Analytics AI
          </h1>
          <p className="text-green-300 mt-2">
            {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
          </p>
        </div>
      </header>

      {/* Chat Container */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="bg-white/10 backdrop-blur-md rounded-3xl shadow-2xl border border-white/20 overflow-hidden">
          {/* Messages */}
          <div className="h-[600px] overflow-y-auto p-6 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-white/60 mt-32">
                <h2 className="text-2xl font-semibold mb-4">
                  👋 Welcome to Football Analytics!
                </h2>
                <p className="text-lg">
                  Ask me anything about player stats, comparisons, or rankings!
                </p>
                <div className="mt-6 text-sm text-white/40">
                  <p>Try: "Compare Haaland and Mbappe"</p>
                  <p>Or: "Top 5 goal scorers in 2023"</p>
                </div>
              </div>
            )}

            {messages.map(msg => (
              <div
                key={msg.id}
                className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.type === 'image' ? (
                  <div className="max-w-2xl">
                    <img
                      src={`data:image/png;base64,${msg.imageData}`}
                      alt={msg.content}
                      className="rounded-xl shadow-lg"
                    />
                    <p className="text-xs text-white/60 mt-2">{msg.content}</p>
                  </div>
                ) : (
                  <div
                    className={`max-w-lg px-6 py-3 rounded-2xl ${
                      msg.type === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white/20 text-white backdrop-blur-sm'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  </div>
                )}
              </div>
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white/20 backdrop-blur-sm px-6 py-3 rounded-2xl">
                  <Loader2 className="w-6 h-6 text-white animate-spin" />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-white/20 p-6 bg-black/20">
            <div className="flex gap-4">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                placeholder="Ask about players, stats, comparisons..."
                className="flex-1 bg-white/10 border border-white/20 rounded-xl px-6 py-4 text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-blue-500 backdrop-blur-sm"
                disabled={!isConnected || isLoading}
              />
              <button
                onClick={sendMessage}
                disabled={!isConnected || isLoading || !input.trim()}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-8 py-4 rounded-xl font-semibold transition-colors flex items-center gap-2"
              >
                <Send className="w-5 h-5" />
                Send
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
```

4. **Create environment file** (`web/.env.local`):
```env
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat
```

### Part 2: Deploy Backend to Railway

1. **Sign up at [Railway.app](https://railway.app)**

2. **Create a new project and deploy from GitHub:**
   - Connect your GitHub repository
   - Railway will auto-detect Python
   - Set the root directory to `api/`
   - Railway will automatically use `api/main.py`

3. **Add environment variables in Railway:**
   ```
   OPENAI_API_KEY=your_openai_key
   MCP_URL=http://localhost:8080/invoke
   MCP_API_KEY=your_mcp_key
   ```

4. **Note your Railway backend URL** (e.g., `your-app.railway.app`)

### Part 3: Deploy Frontend to Netlify

1. **Update WebSocket URL in `web/.env.local`:**
```env
NEXT_PUBLIC_WS_URL=wss://your-app.railway.app/ws/chat
```

2. **Build the frontend:**
```bash
cd web
npm run build
```

3. **Deploy to Netlify:**
   - Sign up at [Netlify.com](https://netlify.com)
   - Connect your GitHub repository
   - Set build settings:
     - Base directory: `web`
     - Build command: `npm run build`
     - Publish directory: `web/.next`
   - Add environment variable:
     - `NEXT_PUBLIC_WS_URL=wss://your-app.railway.app/ws/chat`

4. **Deploy!**

## Testing Locally

1. **Start MCP server:**
```bash
python mcp/server.py
```

2. **Start FastAPI backend:**
```bash
cd api
uvicorn main:app --reload
```

3. **Start Next.js frontend:**
```bash
cd web
npm run dev
```

4. **Open browser to** `http://localhost:3000`

## Architecture Features

✅ Real-time WebSocket communication
✅ Automatic image display in chat
✅ Beautiful football-themed UI
✅ Mobile responsive
✅ Streaming responses
✅ Production-ready deployment

## Cost Estimate

- **Netlify (Frontend)**: FREE (hobby tier)
- **Railway (Backend)**: ~$5-10/month
- **MCP Server**: Host on Railway or locally (free if local)

## Need Help?

Check these files:
- `api/main.py` - Backend API
- `web/app/page.tsx` - Frontend UI (to create)
- `.env` files for configuration

Your football analytics app is ready to deploy to the world! ⚽🌍
