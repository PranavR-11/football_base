#!/bin/bash

# Football Analytics AI - Startup Script
# This script helps you start all components in the correct order

echo "🏈 Football Analytics AI - Starting All Components"
echo "=================================================="

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "📋 Please copy .env.example to .env and add your API keys"
    exit 1
fi

# Check if OPENAI_API_KEY is set
if ! grep -q "OPENAI_API_KEY=sk-" .env; then
    echo "❌ OPENAI_API_KEY not properly set in .env file!"
    echo "📋 Please add your real OpenAI API key to .env file"
    exit 1
fi

echo "✅ Environment check passed"
echo ""

echo "🚀 Starting components..."
echo ""

echo "📋 To start all components, open 3 separate terminals and run:"
echo ""
echo "Terminal 1 - MCP Server:"
echo "  python3 -m uvicorn mcp.mcp_server:app --reload --host 0.0.0.0 --port 8080"
echo ""
echo "Terminal 2 - FastAPI Backend:"
echo "  python3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Terminal 3 - Next.js Frontend:"
echo "  cd web && npm run dev"
echo ""
echo "🌐 Once all are running, open: http://localhost:3000"
echo ""
echo "📊 API Documentation: http://localhost:8000/docs"
echo "🔧 MCP Health Check: http://localhost:8080/.well-known/mcp/health"