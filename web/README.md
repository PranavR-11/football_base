# Football Analytics Web Application

Beautiful football-themed web interface for the Football Analytics AI agent.

## 🚀 Quick Start (Local Development)

### 1. Install Dependencies

```bash
cd web
npm install
```

### 2. Start the Backend API

In a separate terminal, from the project root:

```bash
# Make sure you're in the project root, not the web directory
cd api
uvicorn main:app --reload
```

The backend will run on `http://localhost:8000`

### 3. Start the Frontend

Back in the web directory:

```bash
npm run dev
```

The frontend will run on `http://localhost:3000`

### 4. Open Your Browser

Visit [http://localhost:3000](http://localhost:3000) and start chatting with your Football Analytics AI!

## 📁 Project Structure

```
web/
├── app/
│   ├── layout.tsx       # Root layout with metadata
│   ├── page.tsx         # Main chat interface
│   └── globals.css      # Global styles with Tailwind
├── package.json         # Dependencies
├── tsconfig.json        # TypeScript config
├── tailwind.config.ts   # Tailwind CSS config
├── postcss.config.js    # PostCSS config
├── next.config.js       # Next.js config
└── .env.local          # Environment variables
```

## 🎨 Features

- ⚡ Real-time WebSocket communication
- 🖼️ Automatic image display for generated charts
- 🎯 Beautiful football-themed gradient UI
- 📱 Fully responsive design
- 🔄 Streaming responses
- ⚽ Football-themed color scheme (green/blue gradients)

## 🌐 Deployment

See the main [WEB_DEPLOYMENT_GUIDE.md](../WEB_DEPLOYMENT_GUIDE.md) for complete deployment instructions to Netlify and Railway.

## 🛠️ Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **Real-time**: WebSocket
- **Backend**: FastAPI (in `../api/`)

## 📝 Environment Variables

Create a `.env.local` file (already created) with:

```env
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/chat
```

For production, update to your Railway backend URL:

```env
NEXT_PUBLIC_WS_URL=wss://your-app.railway.app/ws/chat
```

## 🐛 Troubleshooting

**Can't connect to backend?**
- Ensure the FastAPI backend is running on port 8000
- Check that `.env.local` has the correct WebSocket URL

**Images not showing?**
- The backend automatically detects and encodes images as base64
- Check browser console for any errors

**Build errors?**
- Try deleting `node_modules` and `.next` folders
- Run `npm install` again
- Ensure you're using Node.js 18+

## 🎯 Example Queries

Try these in the chat:

- "Compare Haaland and Mbappe"
- "Top 5 goal scorers in 2023"
- "Show me Neymar's stats"
- "Who is the best midfielder right now?"

Enjoy your Football Analytics AI! ⚽🌍
