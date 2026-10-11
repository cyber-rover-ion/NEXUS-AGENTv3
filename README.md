# NEXUS-AGENTv3

A local-first AI assistant built with Ollama, FastAPI, and SQLite.

## Overview

NEXUS connects a browser-based interface to language models running through a local Ollama instance. A FastAPI backend handles application requests, while SQLite stores conversation history locally.

## Features

- Local Ollama model integration
- Streaming assistant responses
- Persistent conversation history
- SQLite-backed local storage
- Configurable default model and system prompt
- Browser-based interface
- FastAPI application backend
- Interface and theme customization

## Architecture

```text
Browser Interface
       |
       v
   FastAPI API
    /       \
   v         v
SQLite     Ollama
             |
             v
        Local Model
```

## Requirements

- Python 3.12 or later
- Ollama installed and running
- At least one model available in Ollama

## Setup

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Pull a model supported by your system, for example:

```bash
ollama pull qwen2.5:3b
```

Start Ollama, then launch the backend:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

## Configuration

The backend uses environment variables for deployment-specific settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Base URL for the Ollama API |
| `CORS_ORIGINS` | Localhost ports 8000 and 5173 | Comma-separated list of trusted browser origins |

Example (PowerShell):

```powershell
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:CORS_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Only add origins you control to `CORS_ORIGINS`. Keep the backend bound to loopback for a single-machine setup unless you have deliberately configured network access and appropriate protections.

Chat inputs and settings are validated with length limits before processing. Ollama connection and API failures are returned as gateway errors rather than being unintentionally converted into generic server errors.

## Local Data and Privacy

NEXUS is designed for local model interaction and local conversation storage. Your actual privacy depends on the models, configuration, and any external services you choose to use.

## Maintainer

**JebinTech**
