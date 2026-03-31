# RealtimeVoiceChat Setup Guide for NVIDIA Blackwell RTX 5070 Ti

This document details the complete setup process for running RealtimeVoiceChat on Windows with an NVIDIA RTX 5070 Ti (Blackwell architecture) GPU.

---

## System Requirements

- **OS:** Windows 10/11
- **GPU:** NVIDIA RTX 5070 Ti (Blackwell architecture)
- **CUDA:** 12.8+ (Blackwell requires CUDA 12.8+)
- **Python:** 3.12

---

## Step 1: Install Python 3.12

Download and install Python 3.12 from [python.org](https://www.python.org/downloads/). Ensure you check "Add Python to PATH" during installation.

---

## Step 2: Modify Installation Script for Blackwell GPU

The original `install.bat` was designed for older CUDA versions (12.1) and included DeepSpeed which is notoriously difficult to compile on Windows. We modified it for Blackwell compatibility.

### Original `install.bat` (lines 22-24):
```batch
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install %~dp0wheels\deepspeed-0.16.1+unknown-cp310-cp310-win_amd64.whl
```

### Modified `install.bat` (lines 22-24):
```batch
REM Install PyTorch nightly with CUDA 12.8 support for Blackwell (RTX 5070 Ti)
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128
REM Skip DeepSpeed - Kokoro TTS doesn't require it and it's problematic on Windows
```

**Why this change:**
- Blackwell GPUs require CUDA 12.8+ which is only available in PyTorch nightly builds
- DeepSpeed is complex to compile on Windows and not needed for Kokoro TTS engine
- The `--pre` flag enables pre-release/nightly versions

---

## Step 3: Modify Server to Use Kokoro TTS

DeepSpeed is required for Coqui TTS but Kokoro works without it. We changed the default TTS engine.

### Original `code/server.py` (lines 31-33):
```python
START_TTS_ENGINE = "coqui"
START_LLM_PROVIDER = "ollama"
```

### Modified `code/server.py` (lines 31-33):
```python
START_TTS_ENGINE = "kokoro"  # Kokoro doesn't require DeepSpeed
START_LLM_PROVIDER = "ollama"
```

**Why this change:**
- Coqui TTS requires DeepSpeed for optimal performance
- Kokoro TTS provides good quality without DeepSpeed dependency
- Avoids complex DeepSpeed compilation on Windows

---

## Step 4: Run Installation

Execute the modified installation script:

```powershell
cd d:\backup\Work\pioneerxity\platform\RealtimeVoiceChat
.\install.bat
```

This will:
1. Create a virtual environment in `venv\`
2. Upgrade pip
3. Install PyTorch nightly with CUDA 12.8 support
4. Install all other dependencies from `requirements.txt`

---

## Step 5: Fix Silero VAD Trust Prompt Issue

### The Problem

When starting the server, the recorder initialization failed with:

```
EOFError: EOF when reading a line
```

The traceback showed:
```python
File "...\torch\hub.py", line 376, in _check_repo_is_trusted
    response = input(
               ^^^^^^
EOFError: EOF when reading a line
```

### Root Cause

RealtimeSTT uses Silero VAD (Voice Activity Detection) model loaded via `torch.hub.load()`. In newer PyTorch versions, this requires user confirmation to trust the repository. When running as a background process or without stdin, this causes an EOF error.

### The Fix

Pre-cache the Silero VAD model with `trust_repo=True` before starting the server:

```powershell
d:\backup\Work\pioneerxity\platform\RealtimeVoiceChat\venv\Scripts\python.exe -c "import torch; torch.hub.load('snakers4/silero-vad', 'silero_vad', force_reload=False, trust_repo=True)"
```

This downloads and caches the model, accepting the trust prompt programmatically. The model is cached at:
```
C:\Users\<username>\.cache\torch\hub\master.zip
```

---

## Step 6: Fix Unicode Encoding Crash

### The Problem

TTS synthesis would crash with:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u26a1' in position 0: character maps to <undefined>
```

The error occurred in RealtimeTTS when it tried to print emoji characters (⚡) to the Windows console.

### Root Cause

Windows console defaults to `cp1252` encoding which cannot handle Unicode emoji characters. RealtimeTTS's `text_to_stream.py` line 509 prints:

```python
print(f"\033[96m\033[1m\u26a1 synthesizing\033[0m ...")
```

The ⚡ emoji causes a crash on Windows.

### The Fix

Set the `PYTHONIOENCODING` environment variable to `utf-8` before running the server:

```powershell
$env:PYTHONIOENCODING='utf-8'
```

---

## Step 7: Start the Server

With all fixes applied, start the server:

```powershell
cd d:\backup\Work\pioneerxity\platform\RealtimeVoiceChat\code
$env:PYTHONIOENCODING='utf-8'
d:\backup\Work\pioneerxity\platform\RealtimeVoiceChat\venv\Scripts\python.exe server.py
```

---

## Complete Startup Script

Create a `start.ps1` file for easy launching:

```powershell
# start.ps1 - Startup script for RealtimeVoiceChat on Blackwell GPU

$env:PYTHONIOENCODING = 'utf-8'
Set-Location "d:\backup\Work\pioneerxity\platform\RealtimeVoiceChat\code"
& "d:\backup\Work\pioneerxity\platform\RealtimeVoiceChat\venv\Scripts\python.exe" server.py
```

Run with:
```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

---

## Verification

When running correctly, you should see logs like:

```
INFO  🗣️📄 System prompt loaded from file.
INFO  Initializing faster_whisper main transcription model base.en
INFO  🗣️🚀 SpeechPipelineManager initialized and workers started.
INFO  👂✅ AudioToTextRecorder instance created successfully.
INFO  Application startup complete.
```

Open `http://localhost:8000` in your browser and test voice interaction.

---

## Troubleshooting Summary

| Issue | Symptom | Solution |
|-------|---------|----------|
| PyTorch CUDA mismatch | GPU not detected | Use PyTorch nightly with cu128 index |
| DeepSpeed compilation failure | Install errors | Skip DeepSpeed, use Kokoro TTS |
| Silero VAD trust prompt | `EOFError` on startup | Pre-cache model with `trust_repo=True` |
| Unicode encoding crash | `UnicodeEncodeError` | Set `PYTHONIOENCODING='utf-8'` |

---

## Files Modified

1. **`install.bat`** (lines 22-24)
   - Changed PyTorch source to nightly cu128
   - Removed DeepSpeed wheel installation

2. **`code/server.py`** (lines 31-33)
   - Changed default TTS engine from "coqui" to "kokoro"

---

## Hardware Configuration Used

- **GPU:** NVIDIA GeForce RTX 5070 Ti (Blackwell architecture)
- **CUDA Version:** 12.8
- **Driver:** Latest NVIDIA Game Ready Driver
- **VRAM:** 16GB GDDR7

---

## Notes

- The Blackwell architecture (RTX 50-series) requires CUDA 12.8 or higher
- PyTorch stable releases may not yet support Blackwell; nightly builds are recommended
- Kokoro TTS quality is good but Coqui XTTS may offer better quality if you can get DeepSpeed working
- Consider using a virtual environment to avoid conflicts with other Python projects

---

*Document created: March 31, 2026*
*GPU: NVIDIA RTX 5070 Ti (Blackwell)*
