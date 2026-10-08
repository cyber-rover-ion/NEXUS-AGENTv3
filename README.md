# NEXUS-AGENTv3

NEXUS is a local-first AI assistant built around Ollama, with a FastAPI backend, browser-based frontend, and local SQLite storage.

## Overview

NEXUS is designed to run language models directly on the user's computer instead of depending on hosted AI APIs. The application connects to a locally running Ollama instance, provides streaming conversations, and stores application data locally.

## Features

- Local Ollama model integration
- Streaming AI responses
- Persistent conversation history
- SQLite-based local storage
- Configurable system prompt
- Configurable default model
- Browser-based interface
- FastAPI backend
- Theme and interface customization

## Architecture

```text
Browser Frontend
      |
      v
FastAPI Backend
      |
      +----> SQLite
      |
      +----> Ollama
                |
                v
          Local AI Model
```

The repository is organized around separate frontend and backend components, with application data stored under the local data directory.

## Requirements

- Python 3.12+
- Ollama
- An Ollama model

Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Install an Ollama model, for example:

```bash
ollama pull qwen2.5:3b
```

Start Ollama, then run the NEXUS server:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Project Direction

NEXUS is focused on private, local AI interaction and practical assistant tooling. The architecture is intended to remain lightweight while allowing the interface and local model support to evolve.

## Creator

Made by **JebinTech**.
