import os
import sqlite3
import json
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
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
OLLAMA_BASE_URL = "http://127.0.0.1:11434"

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
    return datetime.utcnow().isoformat() + "Z"

async def ollama_available() -> bool:
    """Check if Ollama is reachable by querying /api/tags."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False

async def get_ollama_models() -> List[str]:
    """Return list of model names installed in Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Ollama returned an error")
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return models
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unexpected error while fetching models: {str(e)}")

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
    title: Optional[str] = "New Conversation"

class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    model: str

class SettingsUpdate(BaseModel):
    system_prompt: Optional[str] = None
    default_model: Optional[str] = None

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
    allow_origins=["*"],  # For local dev; tighten in production
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
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=ollama_payload)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Ollama error: {resp.text}")
            result = resp.json()
            assistant_content = result.get("message", {}).get("content", "")
            
            # Save user and assistant messages
            save_message(request.conversation_id, "user", request.message)
            save_message(request.conversation_id, "assistant", assistant_content)
            
            return {
                "conversation_id": request.conversation_id,
                "model": request.model,
                "assistant_response": assistant_content
            }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat response from Ollama and save the exchange."""
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
    
    # Save user message
    save_message(request.conversation_id, "user", request.message)
    
    # Prepare Ollama streaming request
    ollama_payload = {
        "model": request.model,
        "messages": messages,
        "stream": True
    }
    
    async def generate():
        assistant_content = ""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=ollama_payload) as resp:
                    if resp.status_code != 200:
                        error_detail = await resp.aread()
                        yield f"data: {json.dumps({'error': f'Ollama error: {error_detail.decode()}'})}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            if "message" in chunk and "content" in chunk["message"]:
                                content = chunk["message"]["content"]
                                assistant_content += content
                                yield f"data: {json.dumps({'content': content})}\n\n"
                            elif "error" in chunk:
                                yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                                return
                        except json.JSONDecodeError:
                            continue
            # Save assistant message after full response
            if assistant_content:
                save_message(request.conversation_id, "assistant", assistant_content)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except httpx.HTTPError as e:
            yield f"data: {json.dumps({'error': f'Ollama streaming failed: {str(e)}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Unexpected error: {str(e)}'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# -----------------------------------------------------------------------------
# Main entry point (if run directly)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)