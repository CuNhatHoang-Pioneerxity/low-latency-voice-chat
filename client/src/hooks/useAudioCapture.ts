import { useRef, useCallback, useState } from 'react';

export type AudioLevelCallback = (level: number) => void;

const BATCH_SAMPLES = 2048;
const HEADER_BYTES = 8;
const FRAME_BYTES = BATCH_SAMPLES * 2;
const MESSAGE_BYTES = HEADER_BYTES + FRAME_BYTES;

export function useAudioCapture(
  onAudioChunk: (data: ArrayBuffer) => void,
  onAudioLevel?: AudioLevelCallback
) {
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const batchBufferRef = useRef<ArrayBuffer | null>(null);
  const batchViewRef = useRef<DataView | null>(null);
  const batchInt16Ref = useRef<Int16Array | null>(null);
  const batchOffsetRef = useRef<number>(0);
  const isTTSPlayingRef = useRef<boolean>(false);

  const initBatch = useCallback((): void => {
    if (!batchBufferRef.current) {
      batchBufferRef.current = new ArrayBuffer(MESSAGE_BYTES);
      batchViewRef.current = new DataView(batchBufferRef.current);
      batchInt16Ref.current = new Int16Array(batchBufferRef.current, HEADER_BYTES);
      batchOffsetRef.current = 0;
    }
  }, []);

  const flushBatch = useCallback((): void => {
    if (!batchViewRef.current || !batchBufferRef.current) return;
    
    const ts = Date.now() & 0xFFFFFFFF;
    batchViewRef.current.setUint32(0, ts, false);
    const flags = isTTSPlayingRef.current ? 1 : 0;
    batchViewRef.current.setUint32(4, flags, false);

    onAudioChunk(batchBufferRef.current);

    batchBufferRef.current = null;
    batchViewRef.current = null;
    batchInt16Ref.current = null;
  }, [onAudioChunk]);

  const flushRemainder = useCallback((): void => {
    if (batchOffsetRef.current > 0) {
      initBatch();
      if (batchInt16Ref.current) {
        for (let i = batchOffsetRef.current; i < BATCH_SAMPLES; i++) {
          batchInt16Ref.current[i] = 0;
        }
      }
      flushBatch();
    }
  }, [initBatch, flushBatch]);

  const startRecording = useCallback(async (): Promise<void> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: { ideal: 24000 },
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      mediaStreamRef.current = stream;
      audioContextRef.current = new AudioContext();

      await audioContextRef.current.audioWorklet.addModule('/pcmWorkletProcessor.js');

      workletNodeRef.current = new AudioWorkletNode(
        audioContextRef.current,
        'pcm-worklet-processor'
      );

      workletNodeRef.current.port.onmessage = ({ data }: MessageEvent) => {
        const incoming = new Int16Array(data);
        let read = 0;

        while (read < incoming.length) {
          initBatch();
          const toCopy = Math.min(
            incoming.length - read,
            BATCH_SAMPLES - batchOffsetRef.current
          );
          
          if (batchInt16Ref.current) {
            batchInt16Ref.current.set(
              incoming.subarray(read, read + toCopy),
              batchOffsetRef.current
            );
          }
          batchOffsetRef.current += toCopy;
          read += toCopy;

          if (batchOffsetRef.current === BATCH_SAMPLES) {
            flushBatch();
          }
        }
      };

      const source = audioContextRef.current.createMediaStreamSource(stream);
      
      // Create analyser for audio levels
      if (onAudioLevel) {
        analyserRef.current = audioContextRef.current.createAnalyser();
        analyserRef.current.fftSize = 256;
        source.connect(analyserRef.current);

        const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
        const updateLevel = () => {
          if (analyserRef.current) {
            analyserRef.current.getByteFrequencyData(dataArray);
            const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
            onAudioLevel(avg / 255);
          }
          animationFrameRef.current = requestAnimationFrame(updateLevel);
        };
        animationFrameRef.current = requestAnimationFrame(updateLevel);
      }
      
      source.connect(workletNodeRef.current);

      setIsRecording(true);
    } catch (err) {
      console.error('Failed to start recording:', err);
      throw err;
    }
  }, [initBatch, flushBatch]);

  const stopRecording = useCallback((): void => {
    flushRemainder();

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    if (analyserRef.current) {
      analyserRef.current.disconnect();
      analyserRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getAudioTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }

    setIsRecording(false);
  }, [flushRemainder]);

  const setTTSPlaying = useCallback((playing: boolean): void => {
    isTTSPlayingRef.current = playing;
  }, []);

  return {
    isRecording,
    startRecording,
    stopRecording,
    setTTSPlaying,
  };
}
