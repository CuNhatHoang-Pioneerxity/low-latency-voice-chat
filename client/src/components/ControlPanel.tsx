import React from 'react';
import './ControlPanel.css';
import { VoiceVisualizer } from './VoiceVisualizer';

interface ControlPanelProps {
  isConnected: boolean;
  isRecording: boolean;
  isTTSPlaying: boolean;
  speed: number;
  audioLevel?: number;
  onStart: () => void;
  onStop: () => void;
  onClear: () => void;
  onSettings: () => void;
  onSpeedChange: (speed: number) => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  isConnected,
  isRecording,
  isTTSPlaying,
  speed,
  audioLevel = 0,
  onStart,
  onStop,
  onClear,
  onSettings,
  onSpeedChange,
}) => {
  return (
    <div className="control-panel">
      <VoiceVisualizer isActive={isConnected} isRecording={isRecording} audioLevel={audioLevel} />

      <div className="controls-row">
        <div className="speed-control">
          <label>Response Speed</label>
          <div className="speed-slider-container">
            <span className="speed-label">Fast</span>
            <input
              type="range"
              min="0"
              max="100"
              value={speed}
              onChange={(e) => onSpeedChange(Number(e.target.value))}
              disabled={!isConnected}
              className="speed-slider"
            />
            <span className="speed-label">Slow</span>
          </div>
        </div>

        <div className="action-buttons">
          {!isConnected ? (
            <button
              className="btn btn-primary btn-large"
              onClick={onStart}
              title="Start voice chat"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
                <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
              </svg>
              <span>Start</span>
            </button>
          ) : (
            <button
              className="btn btn-danger btn-large"
              onClick={onStop}
              title="Stop voice chat"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M6 6h12v12H6z"/>
              </svg>
              <span>Stop</span>
            </button>
          )}

          <button
            className="btn btn-secondary"
            onClick={onClear}
            disabled={!isConnected}
            title="Clear conversation"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>

          <button
            className="btn btn-secondary"
            onClick={onSettings}
            title="Settings"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L3.16 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
            </svg>
          </button>
        </div>
      </div>

      <div className="status-indicators">
        {isRecording && (
          <div className="status-badge recording">
            <span className="status-dot"></span>
            Recording
          </div>
        )}
        {isTTSPlaying && (
          <div className="status-badge playing">
            <span className="status-dot"></span>
            Playing
          </div>
        )}
      </div>
    </div>
  );
};
