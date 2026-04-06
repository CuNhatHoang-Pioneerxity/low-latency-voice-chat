// Backend URL configuration - change this to point to your backend server
const BACKEND_URL = window.BACKEND_URL || 'ws://localhost:8000';

(function() {
  const originalLog = console.log.bind(console);
  console.log = (...args) => {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    const ms = String(now.getMilliseconds()).padStart(3, '0');
    originalLog(
      `[${hh}:${mm}:${ss}.${ms}]`,
      ...args
    );
  };
})();

const statusDiv = document.getElementById("status");
const messagesDiv = document.getElementById("messages");
const speedSlider = document.getElementById("speedSlider");
speedSlider.disabled = true;  // start disabled

let socket = null;
let audioContext = null;
let mediaStream = null;
let micWorkletNode = null;
let ttsWorkletNode = null;

let isTTSPlaying = false;
let ignoreIncomingTTS = false;

let chatHistory = [];
let typingUser = "";
let typingAssistant = "";

// --- batching + fixed 8‑byte header setup ---
const BATCH_SAMPLES = 2048;
const HEADER_BYTES  = 8;
const FRAME_BYTES   = BATCH_SAMPLES * 2;
const MESSAGE_BYTES = HEADER_BYTES + FRAME_BYTES;

const bufferPool = [];
let batchBuffer = null;
let batchView = null;
let batchInt16 = null;
let batchOffset = 0;

function initBatch() {
  if (!batchBuffer) {
    batchBuffer = bufferPool.pop() || new ArrayBuffer(MESSAGE_BYTES);
    batchView   = new DataView(batchBuffer);
    batchInt16  = new Int16Array(batchBuffer, HEADER_BYTES);
    batchOffset = 0;
  }
}

function flushBatch() {
  const ts = Date.now() & 0xFFFFFFFF;
  batchView.setUint32(0, ts, false);
  const flags = isTTSPlaying ? 1 : 0;
  batchView.setUint32(4, flags, false);

  socket.send(batchBuffer);

  bufferPool.push(batchBuffer);
  batchBuffer = null;
}

function flushRemainder() {
  if (batchOffset > 0) {
    for (let i = batchOffset; i < BATCH_SAMPLES; i++) {
      batchInt16[i] = 0;
    }
    flushBatch();
  }
}

function initAudioContext() {
  if (!audioContext) {
    audioContext = new AudioContext();
  }
}

function base64ToInt16Array(b64) {
  const raw = atob(b64);
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) {
    view[i] = raw.charCodeAt(i);
  }
  return new Int16Array(buf);
}

async function startRawPcmCapture() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: { ideal: 24000 },
        channelCount: 1,
        echoCancellation: true,
        // autoGainControl: true,
        noiseSuppression: true
      }
    });
    mediaStream = stream;
    initAudioContext();
    await audioContext.audioWorklet.addModule('./pcmWorkletProcessor.js');
    micWorkletNode = new AudioWorkletNode(audioContext, 'pcm-worklet-processor');

    micWorkletNode.port.onmessage = ({ data }) => {
      const incoming = new Int16Array(data);
      let read = 0;
      while (read < incoming.length) {
        initBatch();
        const toCopy = Math.min(
          incoming.length - read,
          BATCH_SAMPLES - batchOffset
        );
        batchInt16.set(
          incoming.subarray(read, read + toCopy),
          batchOffset
        );
        batchOffset += toCopy;
        read       += toCopy;
        if (batchOffset === BATCH_SAMPLES) {
          flushBatch();
        }
      }
    };

    const source = audioContext.createMediaStreamSource(stream);
    source.connect(micWorkletNode);
    statusDiv.textContent = "Recording...";
  } catch (err) {
    statusDiv.textContent = "Mic access denied.";
    console.error(err);
  }
}

async function setupTTSPlayback() {
  await audioContext.audioWorklet.addModule('./ttsPlaybackProcessor.js');
  ttsWorkletNode = new AudioWorkletNode(
    audioContext,
    'tts-playback-processor'
  );

  ttsWorkletNode.port.onmessage = (event) => {
    const { type } = event.data;
    if (type === 'ttsPlaybackStarted') {
      if (!isTTSPlaying && socket && socket.readyState === WebSocket.OPEN) {
        isTTSPlaying = true;
        console.log(
          "TTS playback started. Reason: ttsWorkletNode Event ttsPlaybackStarted."
        );
        socket.send(JSON.stringify({ type: 'tts_start' }));
      }
    } else if (type === 'ttsPlaybackStopped') {
      if (isTTSPlaying && socket && socket.readyState === WebSocket.OPEN) {
        isTTSPlaying = false;
        console.log(
          "TTS playback stopped. Reason: ttsWorkletNode Event ttsPlaybackStopped."
        );
        socket.send(JSON.stringify({ type: 'tts_stop' }));
      }
    }
  };
  ttsWorkletNode.connect(audioContext.destination);
}

function cleanupAudio() {
  if (micWorkletNode) {
    micWorkletNode.disconnect();
    micWorkletNode = null;
  }
  if (ttsWorkletNode) {
    ttsWorkletNode.disconnect();
    ttsWorkletNode = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  if (mediaStream) {
    mediaStream.getAudioTracks().forEach(track => track.stop());
    mediaStream = null;
  }
}

function renderMessages() {
  messagesDiv.innerHTML = "";
  chatHistory.forEach(msg => {
    const bubble = document.createElement("div");
    bubble.className = `bubble ${msg.role}`;
    bubble.textContent = msg.content;
    messagesDiv.appendChild(bubble);
  });
  if (typingUser) {
    const typing = document.createElement("div");
    typing.className = "bubble user typing";
    typing.innerHTML = typingUser + '<span style="opacity:.6;">✏️</span>';
    messagesDiv.appendChild(typing);
  }
  if (typingAssistant) {
    const typing = document.createElement("div");
    typing.className = "bubble assistant typing";
    typing.innerHTML = typingAssistant + '<span style="opacity:.6;">✏️</span>';
    messagesDiv.appendChild(typing);
  }
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function handleJSONMessage({ type, content }) {
  if (type === "partial_user_request") {
    typingUser = content?.trim() ? escapeHtml(content) : "";
    renderMessages();
    return;
  }
  if (type === "final_user_request") {
    if (content?.trim()) {
      chatHistory.push({ role: "user", content, type: "final" });
    }
    typingUser = "";
    renderMessages();
    return;
  }
  if (type === "partial_assistant_answer") {
    typingAssistant = content?.trim() ? escapeHtml(content) : "";
    renderMessages();
    return;
  }
  if (type === "final_assistant_answer") {
    if (content?.trim()) {
      chatHistory.push({ role: "assistant", content, type: "final" });
    }
    typingAssistant = "";
    renderMessages();
    return;
  }
  if (type === "tts_chunk") {
    if (ignoreIncomingTTS) return;
    const int16Data = base64ToInt16Array(content);
    if (ttsWorkletNode) {
      ttsWorkletNode.port.postMessage(int16Data);
    }
    return;
  }
  if (type === "tts_interruption") {
    if (ttsWorkletNode) {
      ttsWorkletNode.port.postMessage({ type: "clear" });
    }
    isTTSPlaying = false;
    ignoreIncomingTTS = false;
    return;
  }
  if (type === "stop_tts") {
    if (ttsWorkletNode) {
      ttsWorkletNode.port.postMessage({ type: "clear" });
    }
    isTTSPlaying = false;
    ignoreIncomingTTS = true;
    console.log("TTS playback stopped. Reason: tts_interruption.");
    socket.send(JSON.stringify({ type: 'tts_stop' }));
    return;
  }
}

function escapeHtml(str) {
  return (str ?? '')
    .replace(/&/g, "&amp;")
    .replace(/</g, "<")
    .replace(/>/g, ">")
    .replace(/"/g, "&quot;");
}

// UI Controls

document.getElementById("clearBtn").onclick = () => {
  chatHistory = [];
  typingUser = typingAssistant = "";
  renderMessages();
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'clear_history' }));
  }
};

speedSlider.addEventListener("input", (e) => {
  const speedValue = parseInt(e.target.value);
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      type: 'set_speed',
      speed: speedValue
    }));
  }
  console.log("Speed setting changed to:", speedValue);
});

document.getElementById("startBtn").onclick = async () => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    statusDiv.textContent = "Already recording.";
    return;
  }
  statusDiv.textContent = "Initializing connection...";

  // Build WebSocket URL from BACKEND_URL
  let wsUrl;
  if (BACKEND_URL.startsWith('wss://') || BACKEND_URL.startsWith('ws://')) {
    wsUrl = BACKEND_URL;
  } else if (BACKEND_URL.startsWith('https://')) {
    wsUrl = BACKEND_URL.replace('https://', 'wss://');
  } else if (BACKEND_URL.startsWith('http://')) {
    wsUrl = BACKEND_URL.replace('http://', 'ws://');
  } else {
    wsUrl = 'ws://' + BACKEND_URL;
  }
  socket = new WebSocket(`${wsUrl}/ws`);

  socket.onopen = async () => {
    statusDiv.textContent = "Connected. Activating mic and TTS…";
    await startRawPcmCapture();
    await setupTTSPlayback();
    speedSlider.disabled = false; 
  };

  socket.onmessage = (evt) => {
    if (typeof evt.data === "string") {
      try {
        const msg = JSON.parse(evt.data);
        handleJSONMessage(msg);
      } catch (e) {
        console.error("Error parsing message:", e);
      }
    }
  };

  socket.onclose = () => {
    statusDiv.textContent = "Connection closed.";
    flushRemainder();
    cleanupAudio();
    speedSlider.disabled = true;
  };

  socket.onerror = (err) => {
    statusDiv.textContent = "Connection error.";
    cleanupAudio();
    console.error(err);
    speedSlider.disabled = true; 
  };
};

document.getElementById("stopBtn").onclick = () => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    flushRemainder();
    socket.close();
  }
  cleanupAudio();
  statusDiv.textContent = "Stopped.";
};

// Copy button (if exists in HTML)
const copyBtn = document.getElementById("copyBtn");
if (copyBtn) {
  copyBtn.onclick = () => {
    const text = chatHistory
      .map(msg => `${msg.role.charAt(0).toUpperCase() + msg.role.slice(1)}: ${msg.content}`)
      .join('\n');
    
    navigator.clipboard.writeText(text)
      .then(() => console.log("Conversation copied to clipboard"))
      .catch(err => console.error("Copy failed:", err));
  };
}

// First render
renderMessages();

// --------------------------------------------------------------------
// System Prompt Configuration
// --------------------------------------------------------------------
const settingsBtn = document.getElementById("settingsBtn");
const settingsModal = document.getElementById("settingsModal");
const systemPromptInput = document.getElementById("systemPromptInput");
const ttsEngineSelect = document.getElementById("ttsEngineSelect");
const cancelSettingsBtn = document.getElementById("cancelSettingsBtn");
const saveSettingsBtn = document.getElementById("saveSettingsBtn");

// Build API URL from BACKEND_URL
function getApiUrl() {
  if (BACKEND_URL.startsWith('http://') || BACKEND_URL.startsWith('https://')) {
    return BACKEND_URL;
  }
  return 'http://' + BACKEND_URL.replace(/^wss?:\/\//, '');
}

// Open settings modal
if (settingsBtn) {
  settingsBtn.onclick = async () => {
    try {
      // Load system prompt
      const promptResponse = await fetch(`${getApiUrl()}/api/system-prompt`, {
        headers: { "ngrok-skip-browser-warning": "true" }
      });
      const promptData = await promptResponse.json();
      systemPromptInput.value = promptData.system_prompt || "";

      // Load TTS engine
      const ttsResponse = await fetch(`${getApiUrl()}/api/tts-engine`, {
        headers: { "ngrok-skip-browser-warning": "true" }
      });
      const ttsData = await ttsResponse.json();
      ttsEngineSelect.value = ttsData.tts_engine || "openai";
    } catch (err) {
      console.error("Failed to load settings:", err);
      systemPromptInput.value = "";
      ttsEngineSelect.value = "openai";
    }
    settingsModal.style.display = "flex";
  };
}

// Close modal
if (cancelSettingsBtn) {
  cancelSettingsBtn.onclick = () => {
    settingsModal.style.display = "none";
  };
}

// Save settings
if (saveSettingsBtn) {
  saveSettingsBtn.onclick = async () => {
    const newPrompt = systemPromptInput.value.trim();
    const newTtsEngine = ttsEngineSelect.value;

    if (!newPrompt) {
      alert("System prompt cannot be empty.");
      return;
    }

    try {
      // Save system prompt
      const promptResponse = await fetch(`${getApiUrl()}/api/system-prompt`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "true"
        },
        body: JSON.stringify({ system_prompt: newPrompt })
      });
      const promptData = await promptResponse.json();

      if (!promptData.success) {
        alert("Failed to save system prompt: " + (promptData.error || "Unknown error"));
        return;
      }

      // Save TTS engine
      const ttsResponse = await fetch(`${getApiUrl()}/api/tts-engine`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "true"
        },
        body: JSON.stringify({ tts_engine: newTtsEngine })
      });
      const ttsData = await ttsResponse.json();

      if (!ttsData.success) {
        alert("Failed to save TTS engine: " + (ttsData.error || "Unknown error"));
        return;
      }

      console.log("Settings updated successfully");
      settingsModal.style.display = "none";
    } catch (err) {
      console.error("Failed to save settings:", err);
      alert("Failed to save settings. Check console for details.");
    }
  };
}

// Close modal on background click
if (settingsModal) {
  settingsModal.onclick = (e) => {
    if (e.target === settingsModal) {
      settingsModal.style.display = "none";
    }
  };
}

// --------------------------------------------------------------------
// Health Check
// --------------------------------------------------------------------
let healthCheckInterval = null;
let serverHealthy = false;

async function checkServerHealth() {
  try {
    const response = await fetch(`${getApiUrl()}/api/health`, {
      method: "GET",
      headers: {
        "ngrok-skip-browser-warning": "true"  // Bypass ngrok browser warning
      },
      signal: AbortSignal.timeout(5000) // 5 second timeout
    });
    
    if (response.ok) {
      const data = await response.json();
      serverHealthy = true;
      
      // Update status indicator
      const statusEl = document.getElementById("status");
      if (statusEl && !socket) {
        statusEl.textContent = `Ready (${data.llm_provider}/${data.tts_engine})`;
        statusEl.style.color = "#4caf50";
      }
      
      return data;
    } else {
      throw new Error("Health check failed");
    }
  } catch (err) {
    serverHealthy = false;
    const statusEl = document.getElementById("status");
    if (statusEl && !socket) {
      statusEl.textContent = "Server unreachable";
      statusEl.style.color = "#f44336";
    }
    console.error("Health check error:", err);
    return null;
  }
}

// Start health check polling
function startHealthCheck() {
  // Initial check
  checkServerHealth();
  
  // Poll every 10 seconds
  healthCheckInterval = setInterval(checkServerHealth, 10000);
}

// Stop health check polling
function stopHealthCheck() {
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval);
    healthCheckInterval = null;
  }
}

// Start health check on page load
startHealthCheck();
