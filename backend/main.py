import os
import sqlite3
import json
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # NEXUS/backend -> NEXUS
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "nexus.db")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "10"))
OLLAMA_REQUEST_TIMEOUT = float(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "600"))
OLLAMA_STREAM_READ_TIMEOUT = float(os.getenv("OLLAMA_STREAM_READ_TIMEOUT_SECONDS", "1800"))

def ollama_timeout(*, streaming: bool = False) -> httpx.Timeout:
    """Use a short connection timeout and a longer generation/read timeout."""
    return httpx.Timeout(
        connect=OLLAMA_CONNECT_TIMEOUT,
        read=OLLAMA_STREAM_READ_TIMEOUT if streaming else OLLAMA_REQUEST_TIMEOUT,
        write=30.0,
        pool=10.0,
    )

DEFAULT_SYSTEM_PROMPT = "You are NEXUS, a helpful local AI assistant. Be accurate, concise, and transparent when you are uncertain."

# -----------------------------------------------------------------------------
# Database initialization
# -----------------------------------------------------------------------------
def init_db():
    """Create data directory and tables if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Existing tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Conversation',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    """)
    # New settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
def get_db_connection():
    """Return a new SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def generate_id() -> str:
    """Generate a simple unique ID (UUID4 hex)."""
    import uuid
    return uuid.uuid4().hex

def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

async def ollama_available() -> bool:
    """Check whether the Ollama API responds within a short health-check window."""
    try:
        timeout = httpx.Timeout(connect=2.0, read=4.0, write=4.0, pool=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return response.status_code == 200
    except httpx.HTTPError:
        return False

async def get_ollama_models() -> List[str]:
    """Return installed model names, with connection failures reported clearly."""
    try:
        timeout = httpx.Timeout(connect=OLLAMA_CONNECT_TIMEOUT, read=15.0, write=15.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama model discovery failed (HTTP {response.status_code}).",
                )
            data = response.json()
            models = data.get("models", [])
            if not isinstance(models, list):
                raise HTTPException(status_code=502, detail="Ollama returned an invalid model list.")
            return [
                model["name"] for model in models
                if isinstance(model, dict) and isinstance(model.get("name"), str)
            ]
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach Ollama at {OLLAMA_BASE_URL}. Check that Ollama is running.",
        ) from e
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=502, detail="Ollama returned invalid JSON while listing models.") from e

async def validate_model(model: str) -> None:
    """Check if the given model exists in Ollama."""
    models = await get_ollama_models()
    if model not in models:
        raise HTTPException(status_code=400, detail=f"Model '{model}' is not installed. Available models: {', '.join(models)}")

def load_conversation_history(conversation_id: str) -> List[Dict[str, str]]:
    """Load all messages for a conversation ordered by creation time."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        )
        rows = cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

def save_message(conversation_id: str, role: str, content: str) -> str:
    """Insert a new message and return its ID."""
    msg_id = generate_id()
    created = now_iso()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, conversation_id, role, content, created)
        )
        # Update conversation's updated_at
        cursor.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (created, conversation_id)
        )
        conn.commit()
        return msg_id
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

def create_conversation_record(title: str = "New Conversation") -> Dict[str, str]:
    """Create a new conversation row and return its data."""
    conv_id = generate_id()
    created = now_iso()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, created, created)
        )
        conn.commit()
        return {"id": conv_id, "title": title, "created_at": created, "updated_at": created}
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

def update_conversation_title(conversation_id: str, title: str) -> None:
    """Update conversation title."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conversation_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# Settings helper functions
def get_setting(key: str, default: str = "") -> str:
    """Retrieve a setting value from SQLite."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

def set_setting(key: str, value: str) -> None:
    """Insert or update a setting in SQLite."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------
class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default="New Conversation", max_length=120)

class ChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1, max_length=200)

class SettingsUpdate(BaseModel):
    system_prompt: Optional[str] = Field(default=None, max_length=12000)
    default_model: Optional[str] = Field(default=None, max_length=200)

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database
    init_db()
    yield
    # Shutdown: nothing special

app = FastAPI(title="NEXUS Backend", lifespan=lifespan)

# CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000,"
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Serve frontend
# -----------------------------------------------------------------------------
@app.get("/")
async def serve_frontend():
    frontend_path = os.path.join(BASE_DIR, "frontend", "index.html")
    return FileResponse(frontend_path)

# -----------------------------------------------------------------------------
# Settings endpoints
# -----------------------------------------------------------------------------
@app.get("/api/settings")
async def get_settings():
    """Return current settings."""
    system_prompt = get_setting("system_prompt", DEFAULT_SYSTEM_PROMPT)
    default_model = get_setting("default_model", "")
    return {
        "system_prompt": system_prompt,
        "default_model": default_model
    }

@app.put("/api/settings")
async def update_settings(settings: SettingsUpdate):
    """Update settings (only provided fields)."""
    if settings.system_prompt is not None:
        set_setting("system_prompt", settings.system_prompt)
    if settings.default_model is not None:
        set_setting("default_model", settings.default_model)
    # Return updated settings
    return await get_settings()

# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    """Check backend and Ollama status."""
    ollama_up = await ollama_available()
    return {
        "backend": "running",
        "ollama": "reachable" if ollama_up else "unreachable"
    }

@app.get("/api/models")
async def list_models():
    """Return list of installed Ollama models."""
    try:
        models = await get_ollama_models()
        return {"models": models}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.post("/api/conversations", status_code=201)
async def create_conversation(request: ConversationCreate):
    """Create a new conversation."""
    title = request.title.strip() if request.title else "New Conversation"
    conv = create_conversation_record(title)
    return conv

@app.get("/api/conversations")
async def list_conversations():
    """Return all conversations ordered by updated_at descending."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
            for row in rows
        ]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Return messages for a specific conversation."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Check if conversation exists
        cursor.execute("SELECT id, title FROM conversations WHERE id = ?", (conversation_id,))
        conv = cursor.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Get messages
        cursor.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        )
        rows = cursor.fetchall()
        messages = [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]
        return {
            "id": conv["id"],
            "title": conv["title"],
            "messages": messages
        }
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conn.commit()
        return {"detail": "Conversation deleted"}
    except sqlite3.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Send a chat message to Ollama and save the exchange."""
    # Validate model
    await validate_model(request.model)
    
    # Check conversation exists
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM conversations WHERE id = ?", (request.conversation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()
    
    # Load conversation history
    history = load_conversation_history(request.conversation_id)
    
    # Build final messages with system prompt
    system_prompt = get_setting("system_prompt", DEFAULT_SYSTEM_PROMPT).strip()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    messages.append({"role": "user", "content": request.message})
    
    # Prepare Ollama request
    ollama_payload = {
        "model": request.model,
        "messages": messages,
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient(timeout=ollama_timeout()) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=ollama_payload)
            if resp.status_code != 200:
                detail = resp.text[:1000]
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama chat failed (HTTP {resp.status_code}): {detail}",
                )
            result = resp.json()
            assistant_content = result.get("message", {}).get("content", "")
            if not isinstance(assistant_content, str) or not assistant_content.strip():
                raise HTTPException(status_code=502, detail="Ollama returned an empty response.")
            
            # Save user and assistant messages
            save_message(request.conversation_id, "user", request.message)
            save_message(request.conversation_id, "assistant", assistant_content)
            
            return {
                "conversation_id": request.conversation_id,
                "model": request.model,
                "assistant_response": assistant_content
            }
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=504,
            detail="Ollama timed out generating a response. Try again or increase OLLAMA_REQUEST_TIMEOUT_SECONDS.",
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {str(e)}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail="Ollama returned invalid JSON for the chat response.") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}") from e

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream an Ollama response and persist only completed exchanges."""
    await validate_model(request.model)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM conversations WHERE id = ?", (request.conversation_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}") from e
    finally:
        conn.close()

    history = load_conversation_history(request.conversation_id)
    system_prompt = get_setting("system_prompt", DEFAULT_SYSTEM_PROMPT).strip()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    messages.append({"role": "user", "content": request.message})

    ollama_payload = {
        "model": request.model,
        "messages": messages,
        "stream": True,
    }

    async def generate():
        assistant_content = ""
        completed = False
        try:
            async with httpx.AsyncClient(timeout=ollama_timeout(streaming=True)) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=ollama_payload) as response:
                    if response.status_code != 200:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                        yield f"data: {json.dumps({'error': f'Ollama chat failed (HTTP {response.status_code}): {detail}'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            yield f"data: {json.dumps({'error': 'Ollama returned an invalid streaming chunk.'})}\n\n"
                            return

                        if isinstance(chunk.get("error"), str):
                            yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                            return

                        message = chunk.get("message")
                        if isinstance(message, dict):
                            content = message.get("content", "")
                            if isinstance(content, str) and content:
                                assistant_content += content
                                yield f"data: {json.dumps({'content': content})}\n\n"

                        if chunk.get("done") is True:
                            completed = True
                            break

            if not completed:
                yield f"data: {json.dumps({'error': 'Ollama closed the stream before generation completed. Please retry.'})}\n\n"
                return
            if not assistant_content.strip():
                yield f"data: {json.dumps({'error': 'Ollama completed without returning any text. Please retry or choose another model.'})}\n\n"
                return

            # Avoid saving a user-only message if Ollama fails or the stream is cut short.
            save_message(request.conversation_id, "user", request.message)
            save_message(request.conversation_id, "assistant", assistant_content)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except httpx.TimeoutException:
            yield f"data: {json.dumps({'error': 'Ollama timed out while generating a response. Try again, or increase OLLAMA_STREAM_READ_TIMEOUT_SECONDS.'})}\n\n"
        except httpx.HTTPError:
            yield f"data: {json.dumps({'error': 'Lost connection to Ollama during generation. Check that Ollama is running, then retry.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Could not finish the Ollama response: {str(e)}'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# -----------------------------------------------------------------------------
# Main entry point (if run directly)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)