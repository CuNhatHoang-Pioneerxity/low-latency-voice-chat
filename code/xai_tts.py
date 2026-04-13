# xai_tts.py
"""
xAI TTS Engine for RealtimeTTS integration.

Uses xAI's WebSocket streaming TTS API for real-time audio generation.
"""
import asyncio
import base64
import json
import logging
import os
import queue
import threading
import time
from typing import Callable, Optional, Any, Generator

logger = logging.getLogger(__name__)

# Check for websockets library
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets library not installed. xAI TTS will not be available. Install with: pip install websockets")


class XAITTSEngine:
    """
    xAI TTS Engine that implements RealtimeTTS engine interface.
    
    Uses xAI's WebSocket streaming API for real-time text-to-speech.
    """
    
    # Available voices
    VOICES = ["eve", "ara", "rex", "sal", "leo"]
    
    # Supported languages (BCP-47 codes)
    LANGUAGES = [
        "auto", "en", "ar-EG", "ar-SA", "ar-AE", "bn", "zh", "fr", "de",
        "hi", "id", "it", "ja", "ko", "pt-BR", "pt-PT", "ru", "es-MX", "es-ES", "tr", "vi"
    ]
    
    def __init__(
        self,
        voice: str = "eve",
        language: str = "en",
        codec: str = "pcm",
        sample_rate: int = 24000,
        api_key: Optional[str] = None,
    ):
        """
        Initialize xAI TTS Engine.
        
        Args:
            voice: Voice ID (eve, ara, rex, sal, leo)
            language: BCP-47 language code or "auto" for detection
            codec: Audio codec (mp3, wav, pcm, mulaw, alaw)
            sample_rate: Sample rate (8000, 16000, 22050, 24000, 44100, 48000)
            api_key: xAI API key (defaults to XAI_API_KEY env var)
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets library required. Install with: pip install websockets")
        
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise ValueError("xAI API key required. Set XAI_API_KEY env var or pass api_key parameter.")
        
        self.voice = voice.lower()
        if self.voice not in self.VOICES:
            logger.warning(f"Unknown voice '{voice}', defaulting to 'eve'")
            self.voice = "eve"
        
        self.language = language
        self.codec = codec
        self.sample_rate = sample_rate
        
        # WebSocket connection
        self._ws = None
        self._ws_loop = None
        self._ws_thread = None
        self._connected = threading.Event()
        self._audio_queue = queue.Queue()
        self._text_queue = queue.Queue()
        self._stop_event = threading.Event()
        
        # Synthesis state
        self._is_synthesizing = False
        self._synthesis_complete = threading.Event()
        
        # RealtimeTTS required attributes
        self.queue = self._audio_queue  # Reference for RealtimeTTS
        self.thread = None
        self.engines = []
        self.timings = queue.Queue()  # Must be a Queue for RealtimeTTS
        self.engine_name = "xAI TTS"  # Engine name for RealtimeTTS
        self.can_consume_generators = False  # RealtimeTTS compatibility
        
        logger.info(f"xAI TTS Engine initialized: voice={voice}, language={language}, codec={codec}, sample_rate={sample_rate}")
    
    def _get_ws_url(self) -> str:
        """Build WebSocket URL with parameters."""
        params = {
            "voice": self.voice,
            "language": self.language,
            "codec": self.codec,
            "sample_rate": self.sample_rate,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"wss://api.x.ai/v1/tts?{query}"
    
    def _run_websocket_loop(self):
        """Run WebSocket event loop in background thread."""
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)
        
        try:
            self._ws_loop.run_until_complete(self._websocket_handler())
        except Exception as e:
            logger.error(f"WebSocket loop error: {e}")
        finally:
            self._ws_loop.close()
    
    async def _websocket_handler(self):
        """Handle WebSocket connection and message processing."""
        url = self._get_ws_url()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                self._ws = ws
                self._connected.set()
                logger.info("xAI TTS WebSocket connected")
                
                # Process messages
                while not self._stop_event.is_set():
                    try:
                        # Check for outgoing text
                        try:
                            msg = self._text_queue.get_nowait()
                            await ws.send(json.dumps(msg))
                        except queue.Empty:
                            pass
                        
                        # Check for incoming audio (with timeout)
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=0.05)
                            event = json.loads(message)
                            
                            if event["type"] == "audio.delta":
                                # Decode base64 audio and put in queue
                                audio_bytes = base64.b64decode(event["delta"])
                                self._audio_queue.put(audio_bytes)
                            elif event["type"] == "audio.done":
                                logger.debug("xAI TTS audio done")
                                self._synthesis_complete.set()
                            elif event["type"] == "error":
                                logger.error(f"xAI TTS error: {event.get('message')}")
                                self._synthesis_complete.set()
                        except asyncio.TimeoutError:
                            pass
                        
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {e}")
                        break
                
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
        finally:
            self._ws = None
            self._connected.clear()
    
    def connect(self, timeout: float = 5.0) -> bool:
        """
        Establish WebSocket connection.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected successfully
        """
        if self._connected.is_set():
            return True
        
        self._stop_event.clear()
        self._ws_thread = threading.Thread(target=self._run_websocket_loop, daemon=True)
        self._ws_thread.start()
        
        return self._connected.wait(timeout=timeout)
    
    def disconnect(self):
        """Close WebSocket connection."""
        self._stop_event.set()
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2.0)
        self._ws = None
        self._connected.clear()
    
    def synthesize(self, text: str) -> Generator[bytes, None, None]:
        """
        Synthesize text to audio chunks.
        
        This is a generator that yields audio chunks as they become available.
        Implements the RealtimeTTS engine interface.
        
        Args:
            text: Text to synthesize
            
        Yields:
            Audio chunks (bytes)
        """
        if not self.connect():
            logger.error("Failed to connect to xAI TTS")
            return
        
        # Clear previous state
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        
        self._synthesis_complete.clear()
        
        # Send text
        self._text_queue.put({"type": "text.delta", "delta": text})
        self._text_queue.put({"type": "text.done"})
        
        logger.debug(f"xAI TTS synthesizing: {text[:50]}...")
        
        # Yield audio chunks
        while not self._synthesis_complete.is_set() or not self._audio_queue.empty():
            try:
                chunk = self._audio_queue.get(timeout=0.1)
                yield chunk
            except queue.Empty:
                if self._synthesis_complete.is_set():
                    break
                continue
    
    def synthesize_stream(self, text_stream: Generator[str, None, None]) -> Generator[bytes, None, None]:
        """
        Synthesize from a stream of text chunks.
        
        Args:
            text_stream: Generator yielding text chunks
            
        Yields:
            Audio chunks (bytes)
        """
        if not self.connect():
            logger.error("Failed to connect to xAI TTS")
            return
        
        # Clear previous state
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        
        self._synthesis_complete.clear()
        
        # Start text sender thread
        def send_text():
            for chunk in text_stream:
                self._text_queue.put({"type": "text.delta", "delta": chunk})
            self._text_queue.put({"type": "text.done"})
        
        sender_thread = threading.Thread(target=send_text, daemon=True)
        sender_thread.start()
        
        # Yield audio chunks
        while not self._synthesis_complete.is_set() or not self._audio_queue.empty():
            try:
                chunk = self._audio_queue.get(timeout=0.1)
                yield chunk
            except queue.Empty:
                if self._synthesis_complete.is_set():
                    break
                continue
        
        sender_thread.join(timeout=1.0)
    
    def set_voice(self, voice: str):
        """Set the voice for synthesis."""
        voice = voice.lower()
        if voice in self.VOICES:
            self.voice = voice
            logger.info(f"xAI TTS voice set to: {voice}")
        else:
            logger.warning(f"Unknown voice '{voice}', keeping current voice: {self.voice}")
    
    def get_stream_info(self):
        """
        Return audio stream info required by RealtimeTTS.
        
        Returns:
            Tuple of (format, channels, rate)
            - format: pyaudio format constant (8 = paInt16)
            - channels: number of audio channels (1 for mono)
            - rate: sample rate in Hz
        """
        # pyaudio.paInt16 = 8 (16-bit signed integer)
        # For PCM 16-bit mono at sample_rate
        return (8, 1, self.sample_rate)
    
    def reset_audio_duration(self):
        """
        Reset audio duration tracking. Required by RealtimeTTS.
        """
        # Clear the queue
        while not self.timings.empty():
            try:
                self.timings.get_nowait()
            except queue.Empty:
                break
    
    def set_language(self, language: str):
        """Set the language for synthesis."""
        self.language = language
        logger.info(f"xAI TTS language set to: {language}")
    
    def get_voices(self) -> list:
        """Get list of available voices."""
        return self.VOICES.copy()
    
    def stop(self):
        """Stop current synthesis. Required by RealtimeTTS."""
        self._stop_event.set()
        self._synthesis_complete.set()
        logger.debug("xAI TTS stop requested")
    
    def shutdown(self):
        """Shutdown the engine. Required by RealtimeTTS."""
        self.disconnect()
        logger.info("xAI TTS engine shutdown")
    
    def is_installed(self) -> bool:
        """Check if the engine is properly installed. Required by RealtimeTTS."""
        return WEBSOCKETS_AVAILABLE and self.api_key is not None
    
    def set_speed(self, speed: float):
        """Set speech speed. Not supported by xAI TTS API."""
        logger.warning("xAI TTS does not support speed adjustment")
    
    def set_voice_parameters(self, **kwargs):
        """Set voice parameters. Not supported by xAI TTS API."""
        logger.debug(f"xAI TTS set_voice_parameters called with: {kwargs}")
    
    def verify_sample_rate(self, sample_rate: int) -> bool:
        """Verify if sample rate is supported."""
        supported = [8000, 16000, 22050, 24000, 44100, 48000]
        return sample_rate in supported
    
    def apply_fade_in(self, audio: bytes, fade_samples: int = 0) -> bytes:
        """Apply fade in to audio. No-op for xAI TTS."""
        return audio
    
    def apply_fade_out(self, audio: bytes, fade_samples: int = 0) -> bytes:
        """Apply fade out to audio. No-op for xAI TTS."""
        return audio
    
    def trim_silence_start(self, audio: bytes, threshold: int = 0) -> bytes:
        """Trim silence from start. No-op for xAI TTS."""
        return audio
    
    def trim_silence_end(self, audio: bytes, threshold: int = 0) -> bytes:
        """Trim silence from end. No-op for xAI TTS."""
        return audio
    
    # RealtimeTTS engine interface methods
    def engine_synthesize(self, text: str) -> Generator[bytes, None, None]:
        """RealtimeTTS engine interface method."""
        yield from self.synthesize(text)
    
    def engine_stream(self, text_stream: Generator[str, None, None]) -> Generator[bytes, None, None]:
        """RealtimeTTS engine interface method for streaming."""
        yield from self.synthesize_stream(text_stream)
    
    def engine_cleanup(self):
        """RealtimeTTS engine cleanup method."""
        self.disconnect()
    
    def __del__(self):
        """Cleanup on destruction."""
        self.disconnect()


class XAITTSProcessor:
    """
    Standalone xAI TTS Processor for direct use without RealtimeTTS.
    
    Provides a simpler interface for streaming TTS with callbacks.
    """
    
    def __init__(
        self,
        voice: str = "eve",
        language: str = "en",
        codec: str = "pcm",
        sample_rate: int = 24000,
        api_key: Optional[str] = None,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        on_synthesis_complete: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize xAI TTS Processor.
        
        Args:
            voice: Voice ID (eve, ara, rex, sal, leo)
            language: BCP-47 language code
            codec: Audio codec (pcm recommended for real-time)
            sample_rate: Sample rate (24000 recommended)
            api_key: xAI API key
            on_audio_chunk: Callback for each audio chunk
            on_synthesis_complete: Callback when synthesis completes
        """
        self.engine = XAITTSEngine(
            voice=voice,
            language=language,
            codec=codec,
            sample_rate=sample_rate,
            api_key=api_key,
        )
        self.on_audio_chunk = on_audio_chunk
        self.on_synthesis_complete = on_synthesis_complete
        self._stop_event = threading.Event()
    
    def synthesize(
        self,
        text: str,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        """
        Synthesize text to audio, calling on_audio_chunk for each chunk.
        
        Args:
            text: Text to synthesize
            stop_event: Event to signal stop
            
        Returns:
            True if completed, False if stopped
        """
        stop = stop_event or self._stop_event
        
        for chunk in self.engine.synthesize(text):
            if stop.is_set():
                return False
            if self.on_audio_chunk:
                self.on_audio_chunk(chunk)
        
        if self.on_synthesis_complete:
            self.on_synthesis_complete()
        
        return True
    
    def synthesize_generator(
        self,
        text_generator: Generator[str, None, None],
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        """
        Synthesize from text generator.
        
        Args:
            text_generator: Generator yielding text chunks
            stop_event: Event to signal stop
            
        Returns:
            True if completed, False if stopped
        """
        stop = stop_event or self._stop_event
        
        for chunk in self.engine.synthesize_stream(text_generator):
            if stop.is_set():
                return False
            if self.on_audio_chunk:
                self.on_audio_chunk(chunk)
        
        if self.on_synthesis_complete:
            self.on_synthesis_complete()
        
        return True
    
    def stop(self):
        """Stop current synthesis."""
        self._stop_event.set()
    
    def shutdown(self):
        """Shutdown the processor."""
        self.stop()
        self.engine.disconnect()


# Convenience function for quick testing
def test_xai_tts(text: str = "Hello! This is a test of xAI text to speech.", voice: str = "eve"):
    """Test xAI TTS synthesis."""
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if not os.getenv("XAI_API_KEY"):
        print("Error: XAI_API_KEY environment variable not set")
        return
    
    engine = XAITTSEngine(voice=voice)
    
    print(f"Synthesizing: {text}")
    audio_data = bytearray()
    
    for chunk in engine.synthesize(text):
        audio_data.extend(chunk)
        print(f"Received chunk: {len(chunk)} bytes")
    
    print(f"Total audio: {len(audio_data)} bytes")
    
    # Save to file if we got audio
    if audio_data:
        output_file = "xai_test_output.raw"
        with open(output_file, "wb") as f:
            f.write(audio_data)
        print(f"Saved to {output_file}")
    
    engine.disconnect()


if __name__ == "__main__":
    test_xai_tts()
