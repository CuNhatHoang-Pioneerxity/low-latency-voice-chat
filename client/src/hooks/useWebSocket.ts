import React from 'react';
import type { WebSocketMessage } from '../types';

const { useState, useEffect, useRef, useCallback } = React;

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'ws://localhost:8000';

function getWsUrl(): string {
  if (BACKEND_URL.startsWith('wss://') || BACKEND_URL.startsWith('ws://')) {
    return BACKEND_URL;
  }
  if (BACKEND_URL.startsWith('https://')) {
    return BACKEND_URL.replace('https://', 'wss://');
  }
  if (BACKEND_URL.startsWith('http://')) {
    return BACKEND_URL.replace('http://', 'ws://');
  }
  // Handle relative paths
  if (BACKEND_URL.startsWith('/')) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}${BACKEND_URL}`;
  }
  return `ws://${BACKEND_URL}`;
}

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const messageHandlersRef = useRef<((msg: WebSocketMessage) => void)[]>([]);

  const connect = useCallback((): WebSocket => {
    const wsUrl = `${getWsUrl()}/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data) as WebSocketMessage;
          messageHandlersRef.current.forEach(handler => handler(msg));
        } catch (e) {
          console.error('Failed to parse message:', e);
        }
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    ws.onerror = () => {
      setError(new Error('WebSocket error'));
      setIsConnected(false);
    };

    return ws;
  }, []);

  const disconnect = useCallback((): void => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const sendMessage = useCallback((msg: WebSocketMessage): void => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer): void => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const onMessage = useCallback((handler: (msg: WebSocketMessage) => void): () => void => {
    messageHandlersRef.current.push(handler);
    return () => {
      messageHandlersRef.current = messageHandlersRef.current.filter(h => h !== handler);
    };
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    error,
    connect,
    disconnect,
    sendMessage,
    sendBinary,
    onMessage,
  };
}
