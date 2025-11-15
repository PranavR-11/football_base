"""
FastAPI backend that wraps the langchain football agent.
This serves as the API layer between the web frontend and your Python agent.
Version: 1.2 - Language translation support
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import os
import sys
import base64
from pathlib import Path
from typing import AsyncGenerator
import asyncio

# Add parent directory to path to import agent
sys.path.insert(0, str(Path(__file__).parent.parent))

app = FastAPI(title="Football Analytics API")

# CORS middleware - configure for your frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your Netlify domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active websocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # Store conversation context per WebSocket session
        self.session_contexts: dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Initialize empty context for this session
        self.session_contexts[websocket] = {
            "last_players": [],
            "last_intent": None,
            "last_hits": None,
            "history": [],
            "pending_disambig": None,
            "detected_language": "English"
        }

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        # Clean up session context
        if websocket in self.session_contexts:
            del self.session_contexts[websocket]

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    def get_context(self, websocket: WebSocket) -> dict:
        """Get the conversation context for this WebSocket session."""
        return self.session_contexts.get(websocket, {
            "last_players": [],
            "last_intent": None,
            "last_hits": None,
            "history": [],
            "pending_disambig": None,
            "detected_language": "English"
        })

manager = ConnectionManager()


async def run_agent_query(query: str, session_context: dict) -> AsyncGenerator[dict, None]:
    """
    Run the agent directly (in-process) with session-specific context.
    """
    import re
    import io
    import glob
    import time
    import sys
    from contextlib import redirect_stdout

    # Import the agent module and its CONTEXT
    from scripts import langchain_agent

    # DEBUG: Print to stderr so it goes to docker logs (not captured by redirect_stdout)
    print(f"[API] Language being set: {session_context.get('detected_language')}", file=sys.stderr, flush=True)

    # Restore this session's context into the agent's global CONTEXT
    langchain_agent.CONTEXT.update(session_context)

    print(f"[API] CONTEXT after update: {langchain_agent.CONTEXT.get('detected_language')}", file=sys.stderr, flush=True)

    # Track existing images before running agent
    existing_images = set(glob.glob('*.png'))

    # Capture stdout to intercept agent output
    output_buffer = io.StringIO()

    # Reset latest radar payload for this run
    langchain_agent.CONTEXT.pop("latest_radar_payload", None)

    try:
        with redirect_stdout(output_buffer):
            # Call the agent (now with restored session context)
            langchain_agent.handle_input(query)

        # Save updated context back to session
        session_context.update(langchain_agent.CONTEXT)

        # Get all output
        output_text = output_buffer.getvalue()

        # Parse output line by line and send text updates
        for line in output_text.split('\n'):
            # Send text updates (remove DEBUG lines for cleaner output)
            if not line.startswith('[') and not line.startswith('DEBUG'):
                clean_line = line.strip()
                if clean_line:
                    yield {
                        "type": "text",
                        "content": clean_line
                    }

        radar_payload = langchain_agent.CONTEXT.pop("latest_radar_payload", None)
        if radar_payload:
            yield {
                "type": "radar_data",
                "payload": radar_payload
            }

        # Find newly created images
        current_images = set(glob.glob('*.png'))
        new_images = current_images - existing_images

        # Send all newly created images
        for image_path in new_images:
            if os.path.exists(image_path):
                try:
                    # Read and encode image as base64
                    with open(image_path, 'rb') as img_file:
                        img_data = base64.b64encode(img_file.read()).decode('utf-8')
                        yield {
                            "type": "image",
                            "filename": image_path,
                            "data": img_data
                        }
                except Exception as e:
                    print(f"Error reading image {image_path}: {e}")

    except Exception as e:
        yield {
            "type": "error",
            "content": f"Error running agent: {str(e)}"
        }

    # Send completion message
    yield {
        "type": "complete",
        "content": "Query completed"
    }


@app.get("/")
async def root():
    return {"message": "Football Analytics API", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat with the agent.
    Includes keepalive pings to prevent idle disconnections.
    """
    await manager.connect(websocket)

    # Create keepalive task to send pings every 30 seconds
    async def keepalive():
        try:
            while True:
                await asyncio.sleep(30)
                if websocket.client_state.value == 1:  # CONNECTED
                    try:
                        await websocket.send_json({"type": "ping"})
                    except:
                        break
        except asyncio.CancelledError:
            pass

    keepalive_task = asyncio.create_task(keepalive())

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            query = data.get("query", "")
            ui_language = data.get("language", "English")  # Get UI language from frontend

            if not query:
                continue

            # Send acknowledgment
            await manager.send_message({
                "type": "ack",
                "content": "Processing your query..."
            }, websocket)

            # Get session context for this WebSocket connection
            session_context = manager.get_context(websocket)

            # Override detected language with UI language selection
            session_context["detected_language"] = ui_language
            print(f"[API] Setting language to: {ui_language} for query: {query[:50]}")

            # Stream responses with session-specific context
            async for response in run_agent_query(query, session_context):
                await manager.send_message(response, websocket)

    except WebSocketDisconnect:
        keepalive_task.cancel()
        manager.disconnect(websocket)
    except Exception as e:
        keepalive_task.cancel()
        await manager.send_message({
            "type": "error",
            "content": f"Error: {str(e)}"
        }, websocket)
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
