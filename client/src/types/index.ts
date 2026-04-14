export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  type?: 'final' | 'partial';
}

export interface WebSocketMessage {
  type: string;
  content?: string;
  speed?: number;
}

export interface HealthData {
  status: string;
  tts_engine: string;
  llm_provider: string;
  llm_model: string;
}

export interface SystemPromptResponse {
  system_prompt: string;
}

export interface TTSEngineResponse {
  tts_engine: string;
}

export interface APIResponse {
  success?: boolean;
  error?: string;
  [key: string]: unknown;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface AudioChunk {
  timestamp: number;
  flags: number;
  pcm: ArrayBuffer;
}
