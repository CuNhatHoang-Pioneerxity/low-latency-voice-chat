import asyncio
import logging
import os
import struct
import threading
import time
from collections import namedtuple
from queue import Queue
from typing import Callable, Generator, Optional, Any

import numpy as np
from huggingface_hub import hf_hub_download

# RealtimeTTS imports
from RealtimeTTS import (
    CoquiEngine, KokoroEngine, OpenAIEngine,
    OrpheusEngine, OrpheusVoice, TextToAudioStream
)

# Your xAI engine
from xai_tts import XAITTSEngine

logger = logging.getLogger(__name__)

# Default configuration constants
START_ENGINE = "kokoro"

Silence = namedtuple("Silence", ("comma", "sentence", "default"))
ENGINE_SILENCES = {
    "coqui":   Silence(comma=0.3, sentence=0.6, default=0.3),
    "kokoro":  Silence(comma=0.3, sentence=0.6, default=0.3),
    "orpheus": Silence(comma=0.3, sentence=0.6, default=0.3),
    "openai":  Silence(comma=0.3, sentence=0.6, default=0.3),
    "xai":     Silence(comma=0.3, sentence=0.6, default=0.3),
}

QUICK_ANSWER_STREAM_CHUNK_SIZE = 8
FINAL_ANSWER_STREAM_CHUNK_SIZE = 30


def create_directory(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def ensure_lasinya_models(models_root: str = "models", model_name: str = "Lasinya") -> None:
    base = os.path.join(models_root, model_name)
    create_directory(base)
    files = ["config.json", "vocab.json", "speakers_xtts.pth", "model.pth"]
    for fn in files:
        local_file = os.path.join(base, fn)
        if not os.path.exists(local_file):
            print(f"👄⏬ Downloading {fn} to {base}")
            hf_hub_download(
                repo_id="KoljaB/XTTS_Lasinya",
                filename=fn,
                local_dir=base
            )


class AudioProcessor:
    def __init__(
            self,
            engine: str = START_ENGINE,
            orpheus_model: str = "orpheus-3b-0.1-ft-Q8_0-GGUF/orpheus-3b-0.1-ft-q8_0.gguf",
    ) -> None:
        self.engine_name = engine.lower()
        self.stop_event = threading.Event()
        self.finished_event = threading.Event()
        self.audio_chunks: Queue[bytes] = Queue(maxsize=100)  # Fixed: thread-safe Queue
        self.orpheus_model = orpheus_model

        self.silence = ENGINE_SILENCES.get(self.engine_name, ENGINE_SILENCES["kokoro"])
        self.current_stream_chunk_size = QUICK_ANSWER_STREAM_CHUNK_SIZE

        # === Engine Initialization ===
        if self.engine_name == "coqui":
            ensure_lasinya_models()
            self.engine = CoquiEngine(
                specific_model="Lasinya",
                local_models_path="./models",
                voice="reference_audio.wav",
                speed=1.1,
                use_deepspeed=True,
                thread_count=6,
                stream_chunk_size=self.current_stream_chunk_size,
                overlap_wav_len=1024,
                load_balancing=True,
                load_balancing_buffer_length=0.5,
                load_balancing_cut_off=0.1,
                add_sentence_filter=True,
            )
        elif self.engine_name == "kokoro":
            self.engine = KokoroEngine(
                voice="af_heart",
                default_speed=1.26,
                trim_silence=True,
                silence_threshold=0.01,
                extra_start_ms=25,
                extra_end_ms=15,
                fade_in_ms=15,
                fade_out_ms=10,
            )
        elif self.engine_name == "orpheus":
            self.engine = OrpheusEngine(
                model=self.orpheus_model,
                temperature=0.8,
                top_p=0.95,
                repetition_penalty=1.1,
                max_tokens=1200,
            )
            self.engine.set_voice(OrpheusVoice("tara"))
        elif self.engine_name == "openai":
            self.engine = OpenAIEngine(
                model="gpt-4o-mini-tts",
                voice="echo",
                speed=1.25,
                response_format="pcm",
            )
        elif self.engine_name == "xai":
            self.engine = XAITTSEngine(
                voice="eve",
                language="vi",
                codec="pcm",
                sample_rate=24000,
            )
        else:
            raise ValueError(f"Unsupported engine: {engine}")

        # === Stream Setup (only for non-xAI engines) ===
        if self.engine_name != "xai":
            self.stream = TextToAudioStream(
                self.engine,
                muted=True,
                playout_chunk_size=4096,
                on_audio_stream_stop=self.on_audio_stream_stop,
            )

            # Prewarm + TTFA measurement (skipped for xAI)
            self._prewarm_and_measure_ttfa()
        else:
            logger.info("👄 xAI TTS engine initialized (WebSocket streaming - skipping prewarm/TTFA)")
            self.tts_inference_time = 450  # Reasonable estimate for xAI

        self.on_first_audio_chunk_synthesize: Optional[Callable[[], None]] = None

    def _prewarm_and_measure_ttfa(self):
        """Prewarm and measure TTFA - only used for local engines."""
        # Prewarm
        self.stream.feed("prewarm")
        self.stream.play(
            muted=True,
            fast_sentence_fragment=False,
            comma_silence_duration=self.silence.comma,
            sentence_silence_duration=self.silence.sentence,
            default_silence_duration=self.silence.default,
            force_first_fragment_after_words=999999,
        )
        while self.stream.is_playing():
            time.sleep(0.01)
        self.finished_event.wait(timeout=2.0)
        self.finished_event.clear()

        # TTFA measurement
        start_time = time.time()
        ttfa = None

        def on_ttfa_chunk(chunk: bytes):
            nonlocal ttfa
            if ttfa is None:
                ttfa = time.time() - start_time

        self.stream.feed("This is a test sentence to measure time to first audio.")
        self.stream.play_async(
            on_audio_chunk=on_ttfa_chunk,
            muted=True,
            fast_sentence_fragment=False,
            comma_silence_duration=self.silence.comma,
            sentence_silence_duration=self.silence.sentence,
            default_silence_duration=self.silence.default,
            force_first_fragment_after_words=999999,
        )

        while ttfa is None and (self.stream.is_playing() or not self.finished_event.is_set()):
            time.sleep(0.01)
        self.stream.stop()
        self.finished_event.wait(timeout=2.0)
        self.finished_event.clear()

        self.tts_inference_time = (ttfa * 1000) if ttfa else 600
        logger.debug(f"👄 TTFA measured: {self.tts_inference_time:.0f}ms")

    def on_audio_stream_stop(self) -> None:
        logger.info("👄🛑 Audio stream stopped.")
        self.finished_event.set()

    # ==================== Unified Buffering Helper ====================
    class _ChunkProcessor:
        """Inner class to hold mutable state for on_audio_chunk callbacks."""
        def __init__(self, engine_name: str, generation_string: str):
            self.first_call = True
            self.callback_fired = False
            self.silent_chunks_count = 0
            self.silent_chunks_time = 0.0
            self.silence_threshold = 150 if engine_name == "orpheus" else 200
            self.engine_name = engine_name
            self.generation_string = generation_string

    def _process_audio_chunk(
            self,
            chunk: bytes,
            processor: "_ChunkProcessor",
            buffer: list[bytes],
            buf_dur: float,
            good_streak: int,
            buffering: bool,
            stop_event: threading.Event,
            audio_chunks: Queue[bytes],
            is_final: bool = False,
    ):
        """Shared logic for buffering, silence skipping, and first-chunk callback."""
        if stop_event.is_set():
            return False, buffer, buf_dur, good_streak, buffering

        now = time.time()
        SR, BPS = 24000, 2  # Most engines use 24kHz 16-bit PCM

        try:
            samples = len(chunk) // BPS
            play_duration = samples / SR
        except Exception:
            play_duration = 0.04  # fallback ~40ms

        # Orpheus silence skipping
        if processor.first_call and processor.engine_name == "orpheus":
            try:
                fmt = f"{samples}h"
                pcm_data = struct.unpack(fmt, chunk)
                avg_amp = np.abs(np.array(pcm_data, dtype=np.int16)).mean()

                if avg_amp < processor.silence_threshold:
                    processor.silent_chunks_count += 1
                    processor.silent_chunks_time += play_duration
                    return True, buffer, buf_dur, good_streak, buffering  # skip

                if processor.silent_chunks_count > 0:
                    logger.info(f"👄⏭️ {processor.generation_string} Skipped {processor.silent_chunks_count} silent chunks "
                                f"({processor.silent_chunks_time*1000:.1f}ms saved)")
            except Exception as e:
                logger.warning(f"👄⚠️ Silence detection error: {e}")

        # Timing & logging
        if processor.first_call:
            processor.first_call = False
            ttfa_actual = now - time.time() + 0.001  # rough
            logger.info(f"👄🚀 {processor.generation_string} Audio started. TTFA: {ttfa_actual:.2f}s")
        else:
            gap = now - getattr(self, f"_{'final' if is_final else 'quick'}_prev_chunk_time", now)
            setattr(self, f"_{'final' if is_final else 'quick'}_prev_chunk_time", now)
            if gap <= play_duration * 1.15:
                good_streak += 1
            else:
                good_streak = 0

        # Buffering logic
        buffer.append(chunk)
        buf_dur += play_duration

        put_occurred = False
        if buffering:
            if good_streak >= 2 or buf_dur >= 0.5:
                logger.info(f"👄➡️ {processor.generation_string} Flushing buffer (streak={good_streak}, dur={buf_dur:.2f}s)")
                for c in buffer:
                    try:
                        audio_chunks.put_nowait(c)
                        put_occurred = True
                    except Exception:
                        pass  # queue full
                buffer.clear()
                buf_dur = 0.0
                buffering = False
        else:
            try:
                audio_chunks.put_nowait(chunk)
                put_occurred = True
            except Exception:
                pass

        # First chunk callback
        if put_occurred and not processor.callback_fired:
            if self.on_first_audio_chunk_synthesize:
                try:
                    self.on_first_audio_chunk_synthesize()
                except Exception as e:
                    logger.error(f"Callback error: {e}")
            processor.callback_fired = True

        return True, buffer, buf_dur, good_streak, buffering

    # ==================== Public Methods ====================
    def synthesize(
            self,
            text: str,
            audio_chunks: Queue[bytes],
            stop_event: threading.Event,
            generation_string: str = "",
    ) -> bool:
        """Synthesize complete text (quick answer)."""
        if self.engine_name == "xai":
            return self._synthesize_xai(text, audio_chunks, stop_event, generation_string, is_final=False)

        # === Non-xAI path (RealtimeTTS) ===
        if self.engine_name == "coqui" and hasattr(self.engine, 'set_stream_chunk_size'):
            self.engine.set_stream_chunk_size(QUICK_ANSWER_STREAM_CHUNK_SIZE)
            self.current_stream_chunk_size = QUICK_ANSWER_STREAM_CHUNK_SIZE

        self.stream.feed(text)
        self.finished_event.clear()

        buffer: list[bytes] = []
        good_streak = 0
        buffering = True
        buf_dur = 0.0
        processor = self._ChunkProcessor(self.engine_name, generation_string)

        setattr(self, "_quick_prev_chunk_time", 0.0)

        def on_chunk(chunk: bytes):
            nonlocal buffer, good_streak, buffering, buf_dur
            cont, buffer, buf_dur, good_streak, buffering = self._process_audio_chunk(
                chunk, processor, buffer, buf_dur, good_streak, buffering,
                stop_event, audio_chunks, is_final=False
            )
            if not cont:
                self.stream.stop()

        play_kwargs = {
            "on_audio_chunk": on_chunk,
            "muted": True,
            "fast_sentence_fragment": False,
            "comma_silence_duration": self.silence.comma,
            "sentence_silence_duration": self.silence.sentence,
            "default_silence_duration": self.silence.default,
            "force_first_fragment_after_words": 999999,
            "log_synthesized_text": True,
        }

        logger.info(f"👄▶️ {generation_string} Starting quick synthesis")
        self.stream.play_async(**play_kwargs)

        while self.stream.is_playing() or not self.finished_event.is_set():
            if stop_event.is_set():
                self.stream.stop()
                return False
            time.sleep(0.01)

        # Final flush
        if buffering and buffer:
            for c in buffer:
                try:
                    audio_chunks.put_nowait(c)
                except Exception:
                    pass
        return True

    def synthesize_generator(
            self,
            generator: Generator[str, None, None],
            audio_chunks: Queue[bytes],
            stop_event: threading.Event,
            generation_string: str = "",
    ) -> bool:
        """Synthesize from text generator (final/long answer)."""
        if self.engine_name == "xai":
            return self._synthesize_xai(generator, audio_chunks, stop_event, generation_string, is_final=True)

        # === Non-xAI path ===
        if self.engine_name == "coqui" and hasattr(self.engine, 'set_stream_chunk_size'):
            self.engine.set_stream_chunk_size(FINAL_ANSWER_STREAM_CHUNK_SIZE)
            self.current_stream_chunk_size = FINAL_ANSWER_STREAM_CHUNK_SIZE

        self.stream.feed(generator)
        self.finished_event.clear()

        buffer: list[bytes] = []
        good_streak = 0
        buffering = True
        buf_dur = 0.0
        processor = self._ChunkProcessor(self.engine_name, generation_string)

        setattr(self, "_final_prev_chunk_time", 0.0)

        def on_chunk(chunk: bytes):
            nonlocal buffer, good_streak, buffering, buf_dur
            cont, buffer, buf_dur, good_streak, buffering = self._process_audio_chunk(
                chunk, processor, buffer, buf_dur, good_streak, buffering,
                stop_event, audio_chunks, is_final=True
            )
            if not cont:
                self.stream.stop()

        play_kwargs = {
            "on_audio_chunk": on_chunk,
            "muted": True,
            "fast_sentence_fragment": False,
            "comma_silence_duration": self.silence.comma,
            "sentence_silence_duration": self.silence.sentence,
            "default_silence_duration": self.silence.default,
            "force_first_fragment_after_words": 999999,
            "log_synthesized_text": True,
        }

        if self.engine_name == "orpheus":
            play_kwargs.update({"minimum_sentence_length": 200, "minimum_first_fragment_length": 200})

        logger.info(f"👄▶️ {generation_string} Starting final synthesis from generator")
        self.stream.play_async(**play_kwargs)

        while self.stream.is_playing() or not self.finished_event.is_set():
            if stop_event.is_set():
                self.stream.stop()
                return False
            time.sleep(0.01)

        if buffering and buffer:
            for c in buffer:
                try:
                    audio_chunks.put_nowait(c)
                except Exception:
                    pass
        return True

    def _synthesize_xai(
            self,
            text_or_gen: Any,
            audio_chunks: Queue[bytes],
            stop_event: threading.Event,
            generation_string: str = "",
            is_final: bool = False,
    ) -> bool:
        """Direct generator handling for xAI engine."""
        if not self.engine.connect():
            logger.error("Failed to connect to xAI TTS")
            return False

        processor = self._ChunkProcessor("xai", generation_string)
        buffer: list[bytes] = []
        good_streak = 0
        buffering = True
        buf_dur = 0.0
        setattr(self, f"_{'final' if is_final else 'quick'}_prev_chunk_time", 0.0)

        try:
            if isinstance(text_or_gen, str):
                gen = self.engine.synthesize(text_or_gen)
            else:
                gen = self.engine.synthesize_stream(text_or_gen)

            for chunk in gen:
                if stop_event.is_set():
                    return False

                cont, buffer, buf_dur, good_streak, buffering = self._process_audio_chunk(
                    chunk, processor, buffer, buf_dur, good_streak, buffering,
                    stop_event, audio_chunks, is_final=is_final
                )
                if not cont:
                    break

            # Final flush
            if buffering and buffer:
                for c in buffer:
                    try:
                        audio_chunks.put_nowait(c)
                    except Exception:
                        pass
            return True

        except Exception as e:
            logger.error(f"xAI synthesis error: {e}")
            return False

    def shutdown(self):
        """Clean shutdown."""
        self.stop_event.set()
        if hasattr(self, 'stream'):
            self.stream.stop()
        if hasattr(self.engine, 'engine_cleanup'):
            self.engine.engine_cleanup()
        elif hasattr(self.engine, 'disconnect'):
            self.engine.disconnect()