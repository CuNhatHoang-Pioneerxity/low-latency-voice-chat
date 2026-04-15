# Docker Setup for xAI + Deepgram Voice Chat

This Docker Compose setup runs the voice chat application with:
- **Server**: FastAPI backend with xAI (LLM + TTS) and Deepgram (STT)
- **Client**: Vite + React frontend served by nginx

## Prerequisites

- Docker and Docker Compose installed
- Deepgram API key
- xAI API key

## Quick Start

1. **Set API keys**:
```bash
cp .env.docker .env
# Edit .env and add your API keys:
# DEEPGRAM_API_KEY=your_key
# XAI_API_KEY=your_key
```

2. **Build and run**:
```bash
docker-compose up --build
```

3. **Access the application**:
- Client: http://localhost:80
- Server API: http://localhost:8000
- Health check: http://localhost:8000/api/health

## Architecture

```
┌─────────────────┐
│   Browser       │
│   (localhost:80)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  nginx (client) │
│  Port 80        │
└────────┬────────┘
         │
         │ Proxy /api/, /ws/, /static/
         ▼
┌─────────────────┐
│  Server (code)  │
│  Port 8000      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  xAI API        │
│  Deepgram API   │
└─────────────────┘
```

## Services

### Server (Port 8000)
- FastAPI backend
- xAI for LLM and TTS
- Deepgram for STT
- No GPU required (cloud-based APIs)

### Client (Port 80)
- Vite + React frontend
- nginx for static file serving
- Proxies API/WebSocket requests to backend

## Development Mode

To mount code for live development, uncomment the volume in docker-compose.yml:
```yaml
volumes:
  - ./code:/app/code
```

Then rebuild:
```bash
docker-compose up --build
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DEEPGRAM_API_KEY | - | Deepgram API key (required) |
| XAI_API_KEY | - | xAI API key (required) |
| LOG_LEVEL | INFO | Logging level |
| MAX_AUDIO_QUEUE_SIZE | 50 | Max audio queue size |
| TTS_START_ENGINE | xai | TTS engine |
| LLM_START_PROVIDER | xai | LLM provider |
| LLM_START_MODEL | grok-3 | xAI model |

## Stopping the Services

```bash
docker-compose down
```

## Rebuilding

```bash
docker-compose build --no-cache
docker-compose up
```
