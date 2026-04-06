"""
Quick test script for OpenAI gpt-4o-mini-tts integration.
Run from the code directory: python test_openai_tts.py
"""
import os
import sys
import time
import wave

# Suppress pydub warnings
import warnings
warnings.filterwarnings("ignore")

# Ensure OPENAI_API_KEY is set
if not os.environ.get("OPENAI_API_KEY"):
    print("ERROR: Set OPENAI_API_KEY environment variable first")
    exit(1)

from RealtimeTTS import OpenAIEngine, TextToAudioStream

def test_openai_tts():
    print("Initializing OpenAI TTS engine (gpt-4o-mini-tts, voice=echo, speed=1.25)...")
    
    try:
        engine = OpenAIEngine(
            model="gpt-4o-mini-tts",
            voice="echo",
            speed=1.25,
            response_format="pcm",
            instructions="",  # Explicitly set to empty string to avoid null error
        )

        stream = TextToAudioStream(engine, muted=True)
        
        # Test text
        test_text = "Hello! This is a test of the GPT-4o mini TTS integration."
        
        print(f"Synthesizing: '{test_text}'")
        
        # Collect audio chunks
        audio_chunks = []
        first_chunk_time = None
        start = time.time()
        
        def on_chunk(chunk: bytes):
            nonlocal first_chunk_time
            if first_chunk_time is None:
                first_chunk_time = time.time() - start
                print(f"First chunk received ({len(chunk)} bytes) after {first_chunk_time:.2f}s")
            audio_chunks.append(chunk)
        
        stream.feed(test_text)
        stream.play(on_audio_chunk=on_chunk, muted=True)
        
        elapsed = time.time() - start
        total_bytes = sum(len(c) for c in audio_chunks)
        
        print(f"\nDone in {elapsed:.2f}s")
        print(f"Total chunks: {len(audio_chunks)}")
        print(f"Total audio: {total_bytes} bytes ({total_bytes / 24000 / 2:.2f}s at 24kHz 16-bit)")
        
        if not audio_chunks:
            print("ERROR: No audio chunks received!")
            return
        
        # Save to wav file for playback
        output_file = "test_output.wav"
        with wave.open(output_file, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(24000)
            wf.writeframes(b"".join(audio_chunks))
        
        print(f"Saved to {output_file}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_openai_tts()
