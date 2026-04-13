# deepgram_stt.py
import asyncio
import json
import logging
import os
import threading
import time
from typing import Optional, Callable, Any, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import deepgram SDK (v3+)
try:
    from deepgram import DeepgramClient
    from deepgram.core.events import EventType
    from deepgram.listen.v1.types import ListenV1Results, ListenV1UtteranceEnd
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False
    logger.warning("deepgram-sdk not installed. Deepgram STT will not be available.")

# Try to import numpy for audio processing
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


@dataclass
class DeepgramConfig:
    """Configuration for Deepgram STT."""
    api_key: Optional[str] = None
    model: str = "nova-2"
    language: str = "en"
    encoding: str = "linear16"
    sample_rate: int = 16000
    channels: int = 1
    smart_format: bool = True
    interim_results: bool = True
    endpointing: int = 300  # ms of silence to trigger endpoint
    utterance_end_ms: int = 1000  # ms for utterance end detection (for noisy audio)


class DeepgramSTT:
    """
    Real-time Speech-to-Text using Deepgram's streaming API (v6+).
    
    Provides a drop-in replacement for RealtimeSTT with similar callback patterns
    but uses Deepgram's cloud API instead of local inference.
    """
    
    def __init__(
        self,
        config: Optional[DeepgramConfig] = None,
        realtime_transcription_callback: Optional[Callable[[str], None]] = None,
        full_transcription_callback: Optional[Callable[[str], None]] = None,
        on_recording_start_callback: Optional[Callable[[], None]] = None,
        silence_active_callback: Optional[Callable[[bool], None]] = None,
        pipeline_latency: float = 0.5,
    ):
        if not DEEPGRAM_AVAILABLE:
            raise ImportError("deepgram-sdk is required for Deepgram STT but not installed.")
        
        self.config = config or DeepgramConfig()
        
        # Check for API key in config or environment
        # DeepgramClient() reads DEEPGRAM_API_KEY from env automatically
        if not self.config.api_key and not os.getenv("DEEPGRAM_API_KEY"):
            raise ValueError("Deepgram API key required. Set DEEPGRAM_API_KEY env var or pass in config.")
        
        # Callbacks
        self.realtime_transcription_callback = realtime_transcription_callback
        self.full_transcription_callback = full_transcription_callback
        self.on_recording_start_callback = on_recording_start_callback
        self.silence_active_callback = silence_active_callback
        self.pipeline_latency = pipeline_latency
        
        # State
        self.is_connected = False
        self.is_recording = False
        self.shutdown_requested = False
        self.current_transcript = ""
        self._accumulated_transcript = ""  # For speech_final handling
        self._speech_final_fired = False  # Guard for UtteranceEnd double-emit
        self.final_transcript = ""
        self.last_speech_time = 0.0
        self.silence_active = False
        self._recording_start_fired = False
        self._reconnect_count = 0
        self._max_reconnect_attempts = 4
        
        # Deepgram client and connection
        self._client: Optional[Any] = None
        self._connection: Optional[Any] = None
        self._lock = threading.Lock()
        self._connection_ready = threading.Event()
        self._connection_thread: Optional[threading.Thread] = None
        self._keepalive_thread: Optional[threading.Thread] = None
        self._silence_detector_thread: Optional[threading.Thread] = None
        self._last_audio_time: float = 0.0
        
        # Audio buffer for frames access (compatibility with existing code)
        self.frames: List[bytes] = []
        self.frames_lock = threading.Lock()
        
        # Silence monitoring
        self._silence_threshold_ms = self.config.endpointing
        
        # Initialize client
        self._init_client()
        
        logger.info(f"Deepgram STT initialized with model: {self.config.model}")
    
    def _init_client(self):
        """Initialize Deepgram client."""
        try:
            # DeepgramClient() reads DEEPGRAM_API_KEY from environment automatically
            self._client = DeepgramClient()
            logger.info("Deepgram client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Deepgram client: {e}")
            raise
    
    def _on_message(self, message):
        """Handle incoming transcription results from Deepgram."""
        try:
            logger.debug(f"Received message from Deepgram: type={type(message).__name__}")
            
            # Handle UtteranceEnd events (for noisy audio scenarios)
            if isinstance(message, ListenV1UtteranceEnd):
                logger.info("Utterance end detected")
                # Only use UtteranceEnd if speech_final hasn't already fired
                if self._accumulated_transcript and not self._speech_final_fired:
                    self.final_transcript = self._accumulated_transcript.strip()
                    self.current_transcript = ""
                    self._accumulated_transcript = ""
                    if self.full_transcription_callback:
                        self.full_transcription_callback(self.final_transcript)
                self._speech_final_fired = False  # Reset for next utterance
                return
            
            
            # Handle transcription results
            if not isinstance(message, ListenV1Results):
                logger.debug(f"Ignoring non-Results message: {type(message)}")
                return
            
            transcript = message.channel.alternatives[0].transcript
            if not transcript:
                logger.debug("Empty transcript, skipping")
                return
            
            is_final = getattr(message, 'is_final', False)
            speech_final = getattr(message, 'speech_final', False)
            
            logger.debug(f"Transcript: '{transcript}', is_final={is_final}, speech_final={speech_final}")
            
            if is_final:
                # Accumulate final results until speech_final
                self._accumulated_transcript += transcript + " "
                self.current_transcript = ""
                
                if speech_final:
                    # Complete utterance - emit the full transcript
                    self._speech_final_fired = True
                    self.final_transcript = self._accumulated_transcript.strip()
                    self._accumulated_transcript = ""
                    logger.info(f"Final transcription (speech_final): {self.final_transcript}")
                    
                    if self.full_transcription_callback:
                        self.full_transcription_callback(self.final_transcript)
                else:
                    logger.debug(f"Final partial: {transcript} (waiting for speech_final)")
            else:
                # Interim transcription
                self.current_transcript = transcript
                self._update_speech_time()
                
                # Fire recording start callback on first speech
                if not self._recording_start_fired:
                    self._recording_start_fired = True
                    if self.on_recording_start_callback:
                        self.on_recording_start_callback()
                
                if self.realtime_transcription_callback:
                    self.realtime_transcription_callback(transcript)
                
                logger.debug(f"Interim transcription: {transcript}")
                
        except Exception as e:
            logger.error(f"Error processing Deepgram message: {e}")
    
    def _on_open(self, *args, **kwargs):
        """Handle connection open event."""
        logger.info("Deepgram connection opened")
        self.is_connected = True
        self._connection_ready.set()  # Signal that connection is truly ready
        self._last_audio_time = time.time()
        self._reconnect_count = 0  # Reset reconnect counter on successful connection
        
        # Start keepalive thread now that connection is open
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()
        logger.info("Keepalive thread started")
        
        # Start silence detector
        self._start_silence_detector()
        
        # Send a small silence chunk immediately to prevent timeout
        try:
            silence = bytes(3200)  # 100ms of silence at 16kHz 16-bit mono
            self._connection.send_media(silence)
            logger.debug("Sent initial silence to prevent timeout")
        except Exception as e:
            logger.warning(f"Failed to send initial silence: {e}")
    
    def _keepalive_loop(self):
        """Send KeepAlive messages to keep connection alive without charges.
        
        Deepgram auto-closes if no audio/data received within ~12 seconds.
        We send KeepAlive (free) every 3 seconds to prevent timeout.
        """
        logger.info("Keepalive loop started")
        last_keepalive = 0.0
        
        while not self.shutdown_requested:
            try:
                if not self._connection:
                    time.sleep(0.1)
                    continue
                
                now = time.time()
                
                # Send KeepAlive message every 3 seconds (free, no charges)
                if (now - last_keepalive) > 3.0:
                    try:
                        self._connection.send_keep_alive()
                        last_keepalive = now
                        logger.info("Sent KeepAlive message")
                    except Exception as e:
                        logger.warning(f"Failed to send KeepAlive: {e}")
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Keepalive loop error (continuing): {e}")
                time.sleep(0.5)
    
    def _on_close(self, *args, **kwargs):
        """Handle connection close event."""
        logger.info("Deepgram connection closed")
        was_connected = self.is_connected
        self.is_connected = False
        
        # Attempt reconnection if it was previously connected and not shutting down
        if was_connected and self._reconnect_count < self._max_reconnect_attempts:
            self._reconnect_count += 1
            logger.info(f"Attempting reconnection {self._reconnect_count}/{self._max_reconnect_attempts} in 2s...")
            time.sleep(2.0)
            
            # Trigger reconnection by starting a new connection thread
            self._connection_ready.clear()
            self._connection_thread = threading.Thread(target=self._run_connection, daemon=True)
            self._connection_thread.start()
            
            # Wait for reconnection to complete
            if self._connection_ready.wait(timeout=5.0):
                logger.info("Reconnection successful")
            else:
                logger.warning("Reconnection timed out")
        else:
            # Only set shutdown_requested if we're not going to reconnect
            self.shutdown_requested = True
            logger.warning("Max reconnection attempts reached or shutdown requested")
    
    def _on_error(self, error, *args, **kwargs):
        """Handle error events."""
        logger.error(f"Deepgram error: {error}")
    
    def _update_speech_time(self):
        """Update the last speech time."""
        self.last_speech_time = time.time()
        if self.silence_active:
            self._set_silence_state(False)
    
    def _set_silence_state(self, is_silent: bool):
        """Update and broadcast silence state."""
        if self.silence_active != is_silent:
            self.silence_active = is_silent
            if self.silence_active_callback:
                self.silence_active_callback(is_silent)
            logger.info(f"Silence state changed: {'ACTIVE' if is_silent else 'INACTIVE'}")
    
    def _start_silence_detector(self):
        """Start background thread to detect silence based on speech timeout."""
        # Don't start if already running
        if self._silence_detector_thread and self._silence_detector_thread.is_alive():
            logger.debug("Silence detector already running")
            return
        
        def detect_silence():
            silence_threshold = self._silence_threshold_ms / 1000.0  # Convert to seconds
            while not self.shutdown_requested:
                try:
                    if self.last_speech_time > 0:
                        time_since_speech = time.time() - self.last_speech_time
                        if time_since_speech > silence_threshold and not self.silence_active:
                            self._set_silence_state(True)
                    time.sleep(0.05)
                except Exception as e:
                    logger.error(f"Error in silence detector: {e}")
                    time.sleep(0.1)
        
        self._silence_detector_thread = threading.Thread(target=detect_silence, daemon=True)
        self._silence_detector_thread.start()
        logger.info("Silence detector thread started")
    
    def _run_connection(self):
        """Run the Deepgram connection in a background thread using context manager."""
        # Reset shutdown flag for new connection
        self.shutdown_requested = False
        
        # Stop any existing keepalive thread before starting new connection
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            logger.debug("Stopping existing keepalive thread before new connection")
        
        try:
            # Build connection parameters - ALWAYS include required params
            params = {
                "model": self.config.model,
                "encoding": self.config.encoding,
                "sample_rate": self.config.sample_rate,
                "channels": self.config.channels,
            }
            
            # Add optional parameters
            if self.config.language != "en":
                params["language"] = self.config.language
            if self.config.smart_format:
                params["smart_format"] = "true"
            if self.config.interim_results:
                params["interim_results"] = "true"
            if self.config.endpointing:
                params["endpointing"] = str(self.config.endpointing)
            if self.config.utterance_end_ms:
                params["utterance_end_ms"] = str(self.config.utterance_end_ms)
            
            logger.info(f"Connecting to Deepgram with params: {params}")
            
            with self._client.listen.v1.connect(**params) as connection:
                # Store connection reference for feed_audio
                self._connection = connection
                
                # Register event handlers
                connection.on(EventType.OPEN, self._on_open)
                connection.on(EventType.CLOSE, self._on_close)
                connection.on(EventType.ERROR, self._on_error)
                connection.on(EventType.MESSAGE, self._on_message)
                
                # Start listening for messages (blocks until connection closes)
                # send_close_stream() from disconnect() will unblock this
                # OPEN event fires after start_listening() is called
                connection.start_listening()
                    
        except Exception as e:
            logger.error(f"Error in Deepgram connection thread: {e}")
        finally:
            self._connection = None
            self.is_connected = False
            self._connection_ready.clear()
    
    def connect(self):
        """Establish connection to Deepgram and start transcription session."""
        if self.is_connected:
            logger.warning("Already connected to Deepgram")
            return True
        
        # Reset state for fresh connection
        self.shutdown_requested = False
        self._reconnect_count = 0
        
        try:
            # Start connection in background thread (uses context manager)
            self._connection_thread = threading.Thread(target=self._run_connection, daemon=True)
            self._connection_thread.start()
            
            # Wait for connection to be ready (with timeout)
            if self._connection_ready.wait(timeout=5.0):
                self.is_connected = True
                self.is_recording = True
                self._recording_start_fired = False
                logger.info("Connected to Deepgram and started transcription session")
                return True
            else:
                logger.error("Timeout waiting for Deepgram connection")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to Deepgram: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Disconnect from Deepgram."""
        if self.is_connected:
            self.shutdown_requested = True
            self._reconnect_count = self._max_reconnect_attempts  # Prevent auto-reconnect
            if self._connection:
                try:
                    self._connection.send_close_stream()
                    logger.info("Disconnected from Deepgram")
                except Exception as e:
                    logger.error(f"Error disconnecting from Deepgram: {e}")
            self.is_connected = False
            self.is_recording = False
            self._connection = None
            self._connection_ready.clear()
    
    def feed_audio(self, audio_data: bytes):
        """Feed audio data to Deepgram for transcription."""
        if not self.is_connected or not self._connection:
            logger.warning("Cannot feed audio: not connected to Deepgram")
            return
        
        try:
            # Update last audio time for keepalive
            self._last_audio_time = time.time()
            
            # Store in frames buffer for compatibility
            with self.frames_lock:
                self.frames.append(audio_data)
                # Keep only last ~10 seconds of audio
                max_frames = int(10 * self.config.sample_rate * 2 / 1024)
                if len(self.frames) > max_frames:
                    self.frames = self.frames[-max_frames:]
            
            # Send to Deepgram
            self._connection.send_media(audio_data)
            logger.debug(f"Sent audio chunk: {len(audio_data)} bytes")
            
        except Exception as e:
            logger.error(f"Error sending audio to Deepgram: {e}")
    
    def text(self, callback: Callable[[str], None]):
        """Register callback for final transcription results (compatibility)."""
        self.full_transcription_callback = callback
    
    def abort_generation(self):
        """Abort current generation/transcription."""
        logger.info("Aborting Deepgram transcription")
        self.current_transcript = ""
        self._accumulated_transcript = ""
        self._speech_final_fired = False
        self._recording_start_fired = False
    
    def shutdown(self):
        """Shutdown the Deepgram STT instance."""
        logger.info("Shutting down Deepgram STT")
        self.shutdown_requested = True
        self.disconnect()
        
        # Clear buffers
        with self.frames_lock:
            self.frames.clear()
    
    @property
    def speech_end_silence_start(self) -> float:
        """Return the timestamp when silence started (for compatibility)."""
        if self.silence_active:
            return self.last_speech_time
        return 0.0
    
    @property
    def post_speech_silence_duration(self) -> float:
        """Return the configured silence duration threshold (for compatibility)."""
        return self._silence_threshold_ms / 1000.0
    
    @post_speech_silence_duration.setter
    def post_speech_silence_duration(self, value: float):
        """Set the silence duration threshold."""
        self._silence_threshold_ms = int(value * 1000)


class DeepgramTranscriptionProcessor:
    """
    High-level transcription processor using Deepgram.
    
    Provides similar interface to TranscriptionProcessor for drop-in replacement.
    """
    
    def __init__(
        self,
        source_language: str = "en",
        realtime_transcription_callback: Optional[Callable[[str], None]] = None,
        full_transcription_callback: Optional[Callable[[str], None]] = None,
        potential_full_transcription_callback: Optional[Callable[[str], None]] = None,
        potential_full_transcription_abort_callback: Optional[Callable[[], None]] = None,
        potential_sentence_end: Optional[Callable[[str], None]] = None,
        silence_active_callback: Optional[Callable[[bool], None]] = None,
        on_recording_start_callback: Optional[Callable[[], None]] = None,
        pipeline_latency: float = 0.5,
        **kwargs,
    ):
        if not DEEPGRAM_AVAILABLE:
            raise ImportError("deepgram-sdk is required but not installed. Install with: pip install deepgram-sdk")
        
        self.source_language = source_language
        self.realtime_transcription_callback = realtime_transcription_callback
        self.full_transcription_callback = full_transcription_callback
        self.potential_full_transcription_callback = potential_full_transcription_callback
        self.potential_full_transcription_abort_callback = potential_full_transcription_abort_callback
        self.potential_sentence_end = potential_sentence_end
        self.silence_active_callback = silence_active_callback
        self.on_recording_start_callback = on_recording_start_callback
        self.pipeline_latency = pipeline_latency
        
        # Additional callbacks set by server after initialization
        self.before_final_sentence: Optional[Callable[[Optional[Any], Optional[str]], bool]] = None
        self.on_tts_allowed_to_synthesize: Optional[Callable[[], None]] = None
        
        self.shutdown_performed = False
        self.realtime_text: Optional[str] = None
        self.final_transcription: Optional[str] = None
        self.silence_active = False
        self.silence_time = 0.0
        
        # Deepgram STT instance
        config = DeepgramConfig(language=source_language)
        self.recorder = DeepgramSTT(
            config=config,
            realtime_transcription_callback=self._on_interim,
            full_transcription_callback=self._on_final,
            on_recording_start_callback=self._on_recording_start,
            silence_active_callback=self._on_silence_change,
            pipeline_latency=pipeline_latency,
        )
        
        # Auto-connect to Deepgram
        if not self.recorder.connect():
            logger.warning("Failed to connect to Deepgram during initialization")
        
        # Start silence monitor for potential sentence detection
        self._start_silence_monitor()
        
        logger.info("DeepgramTranscriptionProcessor initialized and connected")
    
    def _on_interim(self, text: str):
        """Handle interim transcription."""
        self.realtime_text = text
        if self.realtime_transcription_callback:
            self.realtime_transcription_callback(text)
    
    def _on_final(self, text: str):
        """Handle final transcription."""
        # Call before_final_sentence callback first (critical for triggering response)
        audio_copy = self.get_audio_copy()
        if self.before_final_sentence:
            try:
                self.before_final_sentence(audio_copy, text)
            except Exception as e:
                logger.error(f"Error in before_final_sentence callback: {e}")
        
        self.final_transcription = text
        if self.full_transcription_callback:
            self.full_transcription_callback(text)
    
    def _on_recording_start(self):
        """Handle recording start event."""
        if self.on_recording_start_callback:
            self.on_recording_start_callback()
    
    def _on_silence_change(self, is_silent: bool):
        """Handle silence state change."""
        self.silence_active = is_silent
        if is_silent:
            self.silence_time = time.time()
        if self.silence_active_callback:
            self.silence_active_callback(is_silent)
    
    def _start_silence_monitor(self):
        """Start background thread for silence monitoring."""
        def monitor():
            hot = False
            while not self.shutdown_performed:
                try:
                    if self.recorder.silence_active and self.realtime_text:
                        silence_duration = time.time() - self.recorder.last_speech_time
                        
                        # Hot state detection
                        if silence_duration > 0.3 and not hot:
                            hot = True
                            if self.potential_full_transcription_callback:
                                self.potential_full_transcription_callback(self.realtime_text)
                        
                        # Potential sentence end
                        if silence_duration > 0.5:
                            if self.potential_sentence_end and self.realtime_text:
                                self.potential_sentence_end(self.realtime_text)
                    
                    elif hot and not self.recorder.silence_active:
                        # Transition from hot to cold
                        hot = False
                        if self.potential_full_transcription_abort_callback:
                            self.potential_full_transcription_abort_callback()
                    
                    time.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"Error in silence monitor: {e}")
                    time.sleep(0.1)
        
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
    
    def transcribe_loop(self):
        """Main transcription loop (for compatibility with existing API)."""
        if not self.recorder.is_connected:
            self.recorder.connect()
        
        # Keep connection alive, handle reconnections
        while not self.shutdown_performed:
            if not self.recorder.is_connected:
                logger.info("Connection lost, attempting to reconnect...")
                self.recorder.connect()
            time.sleep(0.1)
        
        logger.info("Transcription loop ended")
    
    def feed_audio(self, chunk: bytes, audio_meta_data: Optional[Dict[str, Any]] = None):
        """Feed audio chunk to the transcriber."""
        if not self.shutdown_performed:
            self.recorder.feed_audio(chunk)
    
    def text(self, callback: Callable[[str], None]):
        """Register callback for final transcription results (compatibility)."""
        self.recorder.text(callback)
    
    def abort_generation(self):
        """Abort current generation."""
        self.recorder.abort_generation()
        self.realtime_text = None
    
    def perform_final(self, audio_bytes: Optional[bytes] = None):
        """Force final transcription with current text."""
        if self.realtime_text:
            self.final_transcription = self.realtime_text
            if self.full_transcription_callback:
                self.full_transcription_callback(self.realtime_text)
    
    def shutdown(self):
        """Shutdown the processor."""
        logger.info("Shutting down DeepgramTranscriptionProcessor")
        self.shutdown_performed = True
        self.recorder.shutdown()
    
    def get_audio_copy(self):
        """Get copy of audio buffer (for compatibility)."""
        with self.recorder.frames_lock:
            if self.recorder.frames:
                data = b''.join(self.recorder.frames)
                if NUMPY_AVAILABLE:
                    arr = np.frombuffer(data, dtype=np.int16)
                    return arr.astype(np.float32) / 32768.0
        return None
    
    def get_last_audio_copy(self):
        """Get last audio copy (for compatibility)."""
        return self.get_audio_copy()
