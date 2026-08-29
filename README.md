# NEXUS-AGENTv3
NEXUS is a private, local-first AI workstation designed to bring powerful AI directly to your computer without relying on cloud APIs or external AI services. Built around Ollama, NEXUS allows users to run locally installed language models while keeping conversations and application data on their own machine.
# NEXUS V3 ⚡

**NEXUS** is a local-first AI dashboard built around **Ollama**, designed to give you a clean, private, and responsive AI experience on your own PC.

### ✨ Features

* 🤖 Ollama local AI integration
* 💬 Streaming AI conversations
* 🗂️ Persistent chat history with SQLite
* ⚙️ Custom system prompt & default model
* 🎨 Reactive UI with multiple color themes
* ✨ Cursor-reactive lighting and motion effects
* 🔒 No API keys — everything runs locally
* 🖥️ HTML + CSS + JavaScript frontend
* 🐍 FastAPI Python backend

## 🚀 Installation

### 1. Install requirements

Make sure you have:

* Python 3.12+
* Ollama
* An Ollama model

Install Python dependencies:

```bash
cd %USERPROFILE%\Desktop\NEXUS
python -m pip install fastapi uvicorn httpx
```

Install/run an Ollama model:

```bash
ollama pull qwen2.5:3b
```

### 2. Start Ollama

Make sure Ollama is running.

### 3. Start NEXUS

From the **NEXUS** folder:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 4. Open NEXUS

Go to:

```text
http://127.0.0.1:8000
```

That's it. 🔥

**NEXUS V3 — Local AI. Your machine. Your data.**
