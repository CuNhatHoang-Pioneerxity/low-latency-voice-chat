import React from 'react';

const { useEffect, useRef } = React;
import './VoiceVisualizer.css';

interface VoiceVisualizerProps {
  isActive: boolean;
  isRecording: boolean;
  audioLevel?: number;
}

export const VoiceVisualizer: React.FC<VoiceVisualizerProps> = ({ isActive, isRecording, audioLevel = 0 }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const barsRef = useRef<number[]>(new Array(20).fill(0));
  const levelRef = useRef<number>(0);

  useEffect(() => {
    levelRef.current = audioLevel;
  }, [audioLevel]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = canvas.width / barsRef.current.length;
      const centerY = canvas.height / 2;
      const level = levelRef.current;

      barsRef.current.forEach((height, i) => {
        const baseHeight = level * canvas.height * 0.9;
        const variance = Math.sin(Date.now() * 0.01 + i * 0.5) * 0.3 + 1;
        const targetHeight = isActive && isRecording
          ? baseHeight * variance + canvas.height * 0.05
          : isActive
            ? level * canvas.height * 0.3 + 2
            : 2;

        barsRef.current[i] += (targetHeight - height) * 0.3;

        const x = i * barWidth + barWidth * 0.1;
        const barHeight = Math.max(2, barsRef.current[i]);
        const y = centerY - barHeight / 2;

        const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
        gradient.addColorStop(0, '#667eea');
        gradient.addColorStop(0.5, '#764ba2');
        gradient.addColorStop(1, '#667eea');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth * 0.8, barHeight, 4);
        ctx.fill();
      });

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isActive, isRecording]);

  return (
    <div className={`voice-visualizer ${isActive ? 'active' : ''} ${isRecording ? 'recording' : ''}`}>
      <canvas ref={canvasRef} width={200} height={60} />
    </div>
  );
};
