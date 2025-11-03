"""
FastAPI backend that wraps the langchain football agent.
This serves as the API layer between the web frontend and your Python agent.
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

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

manager = ConnectionManager()


async def run_agent_query(query: str) -> AsyncGenerator[dict, None]:
    """
    Run the agent directly (in-process) to maintain conversation state.
    """
    import re
    import io
    import glob
    import time
    from contextlib import redirect_stdout

    # Import the agent module (use safe wrapper to prevent crashes)
    from scripts.langchain_agent import handle_input_safe

    # Get project root directory (where PNG files are created)
    project_root = Path(__file__).parent.parent
    png_pattern = str(project_root / "*.png")

    # Track existing images before running agent
    existing_images = set(glob.glob(png_pattern))
    print(f"[DEBUG] Project root: {project_root}")
    print(f"[DEBUG] PNG pattern: {png_pattern}")
    print(f"[DEBUG] Existing images before query: {existing_images}")

    # Capture stdout to intercept agent output
    output_buffer = io.StringIO()

    try:
        with redirect_stdout(output_buffer):
            # Call the agent with safe wrapper (catches exceptions to prevent crashes)
            handle_input_safe(query)

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

        # Find newly created images
        current_images = set(glob.glob(png_pattern))
        new_images = current_images - existing_images

        print(f"[DEBUG] Current images after query: {current_images}")
        print(f"[DEBUG] New images detected: {new_images}")

        # Send all newly created images
        for image_path in new_images:
            print(f"[DEBUG] Processing image: {image_path}")
            if os.path.exists(image_path):
                try:
                    # Read and encode image as base64
                    with open(image_path, 'rb') as img_file:
                        img_data = base64.b64encode(img_file.read()).decode('utf-8')
                        print(f"[DEBUG] Successfully encoded image {image_path} ({len(img_data)} bytes base64)")
                        yield {
                            "type": "image",
                            "filename": os.path.basename(image_path),
                            "data": img_data
                        }
                except Exception as e:
                    print(f"[DEBUG] Error reading image {image_path}: {e}")

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
    """
    await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            query = data.get("query", "")

            if not query:
                continue

            # Send acknowledgment
            await manager.send_message({
                "type": "ack",
                "content": "Processing your query..."
            }, websocket)

            # Stream responses
            async for response in run_agent_query(query):
                await manager.send_message(response, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        await manager.send_message({
            "type": "error",
            "content": f"Error: {str(e)}"
        }, websocket)
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
