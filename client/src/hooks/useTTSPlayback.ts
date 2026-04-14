import { useRef, useCallback, useState } from 'react';

interface TTSPlaybackCallbacks {
  onPlaybackStart?: () => void;
  onPlaybackStop?: () => void;
}

export function useTTSPlayback({ onPlaybackStart, onPlaybackStop }: TTSPlaybackCallbacks) {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);

  const base64ToInt16Array = useCallback((b64: string): Int16Array => {
    const raw = atob(b64);
    const buf = new ArrayBuffer(raw.length);
    const view = new Uint8Array(buf);
    for (let i = 0; i < raw.length; i++) {
      view[i] = raw.charCodeAt(i);
    }
    return new Int16Array(buf);
  }, []);

  const startPlayback = useCallback(async (): Promise<void> => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext();
    }

    await audioContextRef.current.audioWorklet.addModule('/ttsPlaybackProcessor.js');

    workletNodeRef.current = new AudioWorkletNode(
      audioContextRef.current,
      'tts-playback-processor'
    );

    workletNodeRef.current.port.onmessage = (event: MessageEvent) => {
      const { type } = event.data as { type: string };
      if (type === 'ttsPlaybackStarted') {
        setIsPlaying(true);
        onPlaybackStart?.();
      } else if (type === 'ttsPlaybackStopped') {
        setIsPlaying(false);
        onPlaybackStop?.();
      }
    };

    workletNodeRef.current.connect(audioContextRef.current.destination);
  }, [onPlaybackStart, onPlaybackStop]);

  const stopPlayback = useCallback((): void => {
    if (workletNodeRef.current) {
      workletNodeRef.current.port.postMessage({ type: 'clear' });
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  const clearBuffer = useCallback((): void => {
    if (workletNodeRef.current) {
      workletNodeRef.current.port.postMessage({ type: 'clear' });
    }
  }, []);

  const playChunk = useCallback((base64Chunk: string): void => {
    if (workletNodeRef.current) {
      const int16Data = base64ToInt16Array(base64Chunk);
      workletNodeRef.current.port.postMessage(int16Data);
    }
  }, [base64ToInt16Array]);

  return {
    isPlaying,
    startPlayback,
    stopPlayback,
    playChunk,
    clearBuffer,
  };
}
