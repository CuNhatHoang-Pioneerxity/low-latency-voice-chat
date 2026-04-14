# Voice Chat Client (Vite + React)

A modern React-based client for the Pioneerxity Voice Chat server.

## Features

- **Real-time voice chat** with WebSocket connection
- **Audio capture** using AudioWorklet for low-latency microphone input
- **TTS playback** with buffer management
- **Responsive UI** optimized for desktop and mobile
- **Configurable backend** via environment variables
- **Settings modal** for system prompt and TTS engine configuration

## Getting Started

### Prerequisites

- Node.js 18+
- The voice chat server running (see parent directory)

### Installation

```bash
cd client
npm install
```

### Development

```bash
npm run dev
```

The client will run on `http://localhost:3000` by default.

### Production Build

```bash
npm run build
```

Output will be in the `dist/` directory.

## Configuration

Create a `.env` file based on `.env.example`:

```env
VITE_BACKEND_URL=ws://localhost:8000
```

For production deployment, set the backend URL to your server:

```env
VITE_BACKEND_URL=wss://your-server.ngrok-free.app
```

## Project Structure

```
client/
├── public/
│   ├── pcmWorkletProcessor.js      # Audio capture worklet
│   └── ttsPlaybackProcessor.js     # TTS playback worklet
├── src/
│   ├── components/                 # React components
│   │   ├── ChatBubble.jsx
│   │   ├── ControlButton.jsx
│   │   ├── SettingsModal.jsx
│   │   └── StatusBar.jsx
│   ├── hooks/                      # Custom React hooks
│   │   ├── useWebSocket.js
│   │   ├── useAudioCapture.js
│   │   └── useTTSPlayback.js
│   ├── App.jsx                     # Main application
│   ├── index.css                   # Global styles
│   └── main.jsx                    # Entry point
├── index.html
├── package.json
└── vite.config.js
```

## Architecture

### Hooks

- `useWebSocket`: Manages WebSocket connection, message handling, and binary data transmission
- `useAudioCapture`: Handles microphone access, AudioWorklet integration, and audio chunk batching
- `useTTSPlayback`: Manages TTS audio playback with buffer queue and state callbacks

### Components

- `ChatBubble`: Renders user/assistant messages with typing indicators
- `ControlButton`: Styled buttons for start/stop/clear/settings actions
- `SettingsModal`: Configuration UI for system prompt and TTS engine
- `StatusBar`: Displays connection status and server health info

## WebSocket Protocol

The client communicates with the server using:

**Outgoing:**
- Binary audio chunks (with 8-byte header: timestamp + flags)
- JSON control messages: `tts_start`, `tts_stop`, `clear_history`, `set_speed`

**Incoming:**
- `partial_user_request`: Live transcription
- `final_user_request`: Confirmed user message
- `partial_assistant_answer`: Streaming assistant response
- `final_assistant_answer`: Complete assistant response
- `tts_chunk`: Base64-encoded audio data
- `tts_interruption`: Stop and clear playback
- `stop_tts`: Mute incoming TTS

## License

Same as parent project.
