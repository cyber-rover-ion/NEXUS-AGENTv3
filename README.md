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
| `OLLAMA_CONNECT_TIMEOUT_SECONDS` | `10` | Maximum time to establish an Ollama connection |
| `OLLAMA_REQUEST_TIMEOUT_SECONDS` | `600` | Read timeout for non-streaming generation |
| `OLLAMA_STREAM_READ_TIMEOUT_SECONDS` | `1800` | Maximum idle wait for streamed generation chunks |

Example (PowerShell):

```powershell
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_CONNECT_TIMEOUT_SECONDS = "10"
$env:OLLAMA_REQUEST_TIMEOUT_SECONDS = "600"
$env:OLLAMA_STREAM_READ_TIMEOUT_SECONDS = "1800"
$env:CORS_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

These variables must be set in the same terminal session used to launch the backend. Increase generation timeouts for slower hardware or large models; keep the connection timeout relatively short so a stopped Ollama service fails quickly.

Only add origins you control to `CORS_ORIGINS`. Keep the backend bound to loopback for a single-machine setup unless you have deliberately configured network access and appropriate protections.

## Ollama Troubleshooting

1. Check the backend health endpoint at `http://127.0.0.1:8000/api/health`.
2. Check model discovery at `http://127.0.0.1:8000/api/models`.
3. If Ollama is unreachable, start the Ollama application/service and confirm `http://127.0.0.1:11434/api/tags` responds.
4. Confirm the selected model is installed with `ollama list`; install a missing model with `ollama pull MODEL_NAME`.
5. If generation times out on slower hardware, increase `OLLAMA_REQUEST_TIMEOUT_SECONDS` and `OLLAMA_STREAM_READ_TIMEOUT_SECONDS`, then restart the backend.

NEXUS now keeps previously discovered models during a temporary Ollama outage, refreshes model discovery when Ollama reconnects, uses separate connection and generation timeouts, and reports interrupted streams instead of treating them as successful responses. Failed or incomplete streamed exchanges are not written to conversation history.

Chat inputs and settings are validated with length limits before processing. Ollama connection and API failures are reported with actionable error messages and appropriate gateway/timeout status codes.

## Local Data and Privacy

NEXUS is designed for local model interaction and local conversation storage. Your actual privacy depends on the models, configuration, and any external services you choose to use.

## Maintainer

**JebinTech**
