import React, { useState, useEffect } from 'react';
import './SettingsModal.css';
import type { SystemPromptResponse, TTSEngineResponse, APIResponse } from '../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const API_URL = import.meta.env.VITE_BACKEND_URL
  ? import.meta.env.VITE_BACKEND_URL.replace(/^ws/, 'http')
  : 'http://localhost:8000';

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const [systemPrompt, setSystemPrompt] = useState('');
  const [ttsEngine, setTtsEngine] = useState('openai');
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (isOpen) {
      loadSettings();
    }
  }, [isOpen]);

  const loadSettings = async (): Promise<void> => {
    setIsLoading(true);
    try {
      const [promptRes, ttsRes] = await Promise.all([
        fetch(`${API_URL}/api/system-prompt`, {
          headers: { 'ngrok-skip-browser-warning': 'true' }
        }),
        fetch(`${API_URL}/api/tts-engine`, {
          headers: { 'ngrok-skip-browser-warning': 'true' }
        }),
      ]);

      const promptData = await promptRes.json() as SystemPromptResponse;
      const ttsData = await ttsRes.json() as TTSEngineResponse;

      setSystemPrompt(promptData.system_prompt || '');
      setTtsEngine(ttsData.tts_engine || 'openai');
    } catch (err) {
      console.error('Failed to load settings:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async (): Promise<void> => {
    if (!systemPrompt.trim()) {
      alert('System prompt cannot be empty');
      return;
    }

    setIsSaving(true);
    try {
      const [promptRes, ttsRes] = await Promise.all([
        fetch(`${API_URL}/api/system-prompt`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true',
          },
          body: JSON.stringify({ system_prompt: systemPrompt }),
        }),
        fetch(`${API_URL}/api/tts-engine`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true',
          },
          body: JSON.stringify({ tts_engine: ttsEngine }),
        }),
      ]);

      const promptData = await promptRes.json() as APIResponse;
      const ttsData = await ttsRes.json() as APIResponse;

      if (!promptData.success || !ttsData.success) {
        alert('Failed to save settings');
        return;
      }

      onClose();
    } catch (err) {
      console.error('Failed to save settings:', err);
      alert('Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-container">
        <div className="modal-header">
          <h2>Settings</h2>
          <button className="modal-close" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
        </div>

        <div className="modal-content">
          {isLoading ? (
            <div className="modal-loading">Loading...</div>
          ) : (
            <>
              <div className="form-group">
                <label htmlFor="system-prompt">System Prompt</label>
                <textarea
                  id="system-prompt"
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  placeholder="Enter system prompt..."
                  rows={6}
                />
              </div>

              <div className="form-group">
                <label htmlFor="tts-engine">TTS Engine</label>
                <select
                  id="tts-engine"
                  value={ttsEngine}
                  onChange={(e) => setTtsEngine(e.target.value)}
                >
                  <option value="openai">OpenAI</option>
                  <option value="kokoro">Kokoro</option>
                </select>
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={isSaving}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={isSaving || isLoading}
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
};
