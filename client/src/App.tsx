import React from 'react';

const { useState, useEffect, useCallback, useRef } = React;
import { useWebSocket, useAudioCapture, useTTSPlayback } from './hooks';
import { BackendPanel, ChatMessage, ControlPanel, Header, SettingsModal } from './components';
import type { ChatMessage as ChatMessageType, WebSocketMessage, HealthData } from './types';
import type { BackendUpdate } from './components';
import './App.css';

const API_URL = import.meta.env.VITE_BACKEND_URL
  ? import.meta.env.VITE_BACKEND_URL.replace(/^ws/, 'http')
  : 'http://localhost:8000';

const App: React.FC = () => {
  const [chatHistory, setChatHistory] = useState<ChatMessageType[]>([]);
  const [typingUser, setTypingUser] = useState('');
  const [typingAssistant, setTypingAssistant] = useState('');
  const [healthData, setHealthData] = useState<HealthData | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [speed, setSpeed] = useState(0);
  const [ignoreIncomingTTS, setIgnoreIncomingTTS] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [backendUpdates, setBackendUpdates] = useState<BackendUpdate[]>([]);

  const ignoreTTSRef = useRef(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const {
    isConnected,
    connect,
    disconnect,
    sendMessage,
    sendBinary,
    onMessage,
  } = useWebSocket();

  const handleTTSPlaybackStart = useCallback((): void => {
    sendMessage({ type: 'tts_start' });
  }, [sendMessage]);

  const handleTTSPlaybackStop = useCallback((): void => {
    sendMessage({ type: 'tts_stop' });
  }, [sendMessage]);

  const handleAudioLevel = useCallback((level: number): void => {
    setAudioLevel(level);
  }, []);

  const {
    isRecording,
    startRecording,
    stopRecording,
    setTTSPlaying,
  } = useAudioCapture(sendBinary, handleAudioLevel);

  const {
    isPlaying: isTTSPlaying,
    startPlayback,
    stopPlayback,
    playChunk,
    clearBuffer,
  } = useTTSPlayback({
    onPlaybackStart: handleTTSPlaybackStart,
    onPlaybackStop: handleTTSPlaybackStop,
  });

  useEffect(() => {
    ignoreTTSRef.current = ignoreIncomingTTS;
  }, [ignoreIncomingTTS]);

  const handleMessage = useCallback((msg: WebSocketMessage): void => {
    const { type, content } = msg;

    switch (type) {
      case 'partial_user_request':
        setTypingUser(content?.trim() || '');
        break;

      case 'final_user_request':
        if (content?.trim()) {
          setChatHistory(prev => [...prev, { role: 'user', content, type: 'final' }]);
        }
        setTypingUser('');
        break;

      case 'partial_assistant_answer':
        setTypingAssistant(content?.trim() || '');
        break;

      case 'final_assistant_answer':
        if (content?.trim()) {
          setChatHistory(prev => [...prev, { role: 'assistant', content, type: 'final' }]);
        }
        setTypingAssistant('');
        break;

      case 'tts_chunk':
        if (!ignoreTTSRef.current && content) {
          playChunk(content);
        }
        break;

      case 'tts_interruption':
        clearBuffer();
        setIgnoreIncomingTTS(false);
        break;

      case 'stop_tts':
        clearBuffer();
        setIgnoreIncomingTTS(true);
        sendMessage({ type: 'tts_stop' });
        break;

      case 'ui_update':
        if (content && typeof content === 'object') {
          setBackendUpdates(prev => [...prev, content as unknown as BackendUpdate]);
        }
        break;

      default:
        break;
    }
  }, [playChunk, clearBuffer, sendMessage]);

  useEffect(() => {
    const unsubscribe = onMessage(handleMessage);
    return () => unsubscribe();
  }, [onMessage, handleMessage]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, typingUser, typingAssistant]);

  useEffect(() => {
    setTTSPlaying(isTTSPlaying);
  }, [isTTSPlaying, setTTSPlaying]);

  const checkHealth = useCallback(async (): Promise<void> => {
    try {
      const response = await fetch(`${API_URL}/api/health`, {
        headers: { 'ngrok-skip-browser-warning': 'true' },
        signal: AbortSignal.timeout(5000),
      });

      if (response.ok) {
        const data = await response.json() as HealthData;
        setHealthData(data);
      }
    } catch (err) {
      console.error('Health check failed:', err);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  const handleStart = async (): Promise<void> => {
    if (isConnected) return;

    connect();
    await startRecording();
    await startPlayback();
  };

  const handleStop = (): void => {
    disconnect();
    stopRecording();
    stopPlayback();
    setAudioLevel(0);
  };

  const handleClear = (): void => {
    setChatHistory([]);
    setTypingUser('');
    setTypingAssistant('');
    setBackendUpdates([]);
    sendMessage({ type: 'clear_history' });
  };

  const handleSpeedChange = (value: number): void => {
    setSpeed(value);
    sendMessage({ type: 'set_speed', speed: value });
  };

  return (
    <div className="app">
      <div className="app-container">
        <Header isConnected={isConnected} healthData={healthData} />

        <div className="main-content">
          <BackendPanel updates={backendUpdates} />

          <div className="messages-container">
          <div className="messages">
            {chatHistory.length === 0 && !typingUser && !typingAssistant && (
              <div className="empty-state">
                <div className="empty-icon">
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
                  </svg>
                </div>
                <p>Press Start to begin voice chat</p>
                <span>Speak naturally and the AI will respond</span>
              </div>
            )}

            {chatHistory.map((msg, idx) => (
              <ChatMessage
                key={idx}
                role={msg.role}
                content={msg.content}
              />
            ))}
            {typingUser && (
              <ChatMessage role="user" content={typingUser} isTyping />
            )}
            {typingAssistant && (
              <ChatMessage role="assistant" content={typingAssistant} isTyping />
            )}
            <div ref={chatEndRef} />
          </div>
        </div>
        </div>

        <ControlPanel
          isConnected={isConnected}
          isRecording={isRecording}
          isTTSPlaying={isTTSPlaying}
          speed={speed}
          audioLevel={audioLevel}
          onStart={handleStart}
          onStop={handleStop}
          onClear={handleClear}
          onSettings={() => setIsSettingsOpen(true)}
          onSpeedChange={handleSpeedChange}
        />
      </div>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  );
};

export default App;
