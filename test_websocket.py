#!/usr/bin/env python3
"""
Test WebSocket connection to the FastAPI backend
"""
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/chat"
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connected successfully!")
            
            # Send a test message
            test_message = {"query": "hello"}
            await websocket.send(json.dumps(test_message))
            print("📤 Sent test message")
            
            # Wait for response
            response = await asyncio.wait_for(websocket.recv(), timeout=10)
            print(f"📥 Received: {response}")
            
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())