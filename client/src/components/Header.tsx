import React from 'react';
import './Header.css';
import type { HealthData } from '../types';

interface HeaderProps {
  isConnected: boolean;
  healthData: HealthData | null;
}

export const Header: React.FC<HeaderProps> = ({ isConnected, healthData }) => {
  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="logo">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
          </svg>
        </div>
        <div className="brand-text">
          <h1>Voice Chat</h1>
          {healthData && (
            <span className="model-info">
              {healthData.llm_provider} / {healthData.tts_engine}
            </span>
          )}
        </div>
      </div>

      <div className="header-status">
        <div className={`server-indicator ${healthData ? 'up' : 'down'}`}>
          <span className="indicator-dot"></span>
          <span className="indicator-text">
            {healthData ? 'Server Up' : 'Server Down'}
          </span>
        </div>
        {isConnected && (
          <div className="connection-indicator connected">
            <span className="indicator-dot"></span>
            <span className="indicator-text">In Call</span>
          </div>
        )}
      </div>
    </header>
  );
};
