# 🎙️ Local AI Chatbot (ESP32 S3 + Local PC Backend)

This is a fully private, offline-capable AI Chatbot setup that runs entirely on your own local hardware. It replaces the original remote Chinese servers with a local Python backend running on your PC, integrating **Ollama** (for local LLMs) and **Whisper** (for local Speech-to-Text). 

No audio, prompts, or device telemetry are ever sent to external cloud servers.

---

## 🌟 How It Works

1. **Wake/Trigger**: You speak to the ESP32 S3 device.
2. **Streaming (Opus)**: The ESP32 streams your voice in real-time as **Opus-encoded** audio packets over WebSockets to your local PC.
3. **Voice Activity Detection (VAD)**: The local server dynamically decodes and monitors the audio volume (RMS). When you stop speaking, it automatically triggers processing.
4. **Speech-to-Text (STT)**: The local server runs a Whisper model to transcribe your voice to text.
5. **Local Brain (LLM)**: The transcribed text is sent to your running **Ollama** server (e.g., using `llama3` or `qwen2.5`).
6. **Text-to-Speech (TTS)**: The LLM's response is converted to audio (using Microsoft Edge's high-quality free voice service or fully offline TTS) and encoded back to Opus packets.
7. **Paced Audio Playback**: The server streams the Opus packets back to the ESP32 S3 in real-time. The ESP32 decodes and speaks the response through its speaker.

---

## 💻 1. Local PC Server Setup

### Prerequisite: Install FFmpeg
Your local PC must have `ffmpeg` installed and added to the system PATH.
*   **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
*   **macOS**: `brew install ffmpeg`
*   **Windows**: Download from gyan.dev and add the `bin` folder to your environment PATH.

### Step 1: Install Dependencies
Run the following commands to install dependencies, including the optional but highly recommended standard **Opus codec** bindings:

```bash
# Ubuntu/Debian:
sudo apt-get install libopus0
pip install -r local-backend/requirements.txt --extra-index-url https://pypi.python.org/simple
pip install opuslib

# macOS:
brew install opus
pip install -r local-backend/requirements.txt
pip install opuslib

# Windows:
pip install -r local-backend/requirements.txt
# (Note: Windows may require placing libopus.dll in your Python or system directory to use opuslib)
```

### Step 2: Set up Ollama
1. Download and install [Ollama](https://ollama.com).
2. Start Ollama and download a fast conversational model of your choice:
   ```bash
   ollama run llama3
   # or a smaller, faster model:
   ollama pull qwen2.5:0.5b
   ```

### Step 3: Run the Local Server
Start the unified Python server. It runs both the **WebSocket Audio service** (port 8000) and the **OTA Config service** (on the same port!):

```bash
python -m local-backend.server
```

---

## ⚡ 2. Connecting the ESP32 S3 (No-Flash & Flashing Guide)

### Method A: No Re-flashing Required (DNS Redirection)
If you already have their working firmware running on your ESP32 S3:
1. The firmware periodically checks `https://api.tenclass.net/xiaozhi/ota/` via HTTP.
2. You can hijack/redirect `api.tenclass.net` in your router's DNS settings, Pi-hole, or local `/etc/hosts` file to point to your PC's IP address.
3. Our Python server automatically catches these OTA calls and dynamically returns your local WebSocket URL. The ESP32 S3 will connect to your local PC automatically!

### Method B: Building and Flashing via ESP-IDF
If you want to compile and flash the firmware from source yourself:
1. Open the project inside the `xiaozhi-esp32-main` folder.
2. Edit `main/Kconfig.projbuild` or use menuconfig to configure `CONFIG_OTA_URL` to point to your local PC:
   ```text
   CONFIG_OTA_URL="http://<your_pc_ip>:8000/ota/"
   ```
3. Set up ESP-IDF command line environment.
4. Build and flash the target board using:
   ```bash
   idf.py set-target esp32s3
   # Run menuconfig to select your audio codec, screen type, and board type
   idf.py menuconfig
   # Compile and flash
   idf.py build flash monitor
   ```

---

## ⚙️ Configuration Tuning
You can open `local-backend/config.py` to change settings like:
*   `OLLAMA_MODEL`: Set your preferred local model.
*   `VAD_THRESHOLD`: Increase if your mic is in a noisy room to prevent false speaking triggers.
*   `STT_PROVIDER`: Swap between local whisper and cloud engines.
*   `TTS_VOICE`: Swap between English, Chinese, or multi-lingual speaking voices.

---

## 📚 ConvoIndex Phase 3 (Transcript Index UI)

Phase 3 adds a local web dashboard for viewing and searching transcripts stored in SQLite.

### What was added

1. **Utterance segmentation inside long capture sessions**
   - `local-backend/capture_server.py` now uses VAD to cut a single long connection into segment-level transcript rows.
2. **Transcript metadata for quality/debugging**
   - Each row stores `word_count`, `char_count`, `avg_rms`, `peak_abs`, `stt_model`, and `stt_input_gain`.
3. **Local Transcript API**
   - `GET /api/transcripts?q=&limit=&offset=` on `http://<host>:8010`
4. **React/Vite timeline/search UI**
   - Located in `web-indexer/`

### Run Phase 3

1. Start capture/transcription + API backend:

```bash
python -m local-backend.capture_server
```

2. Start the web UI:

```bash
cd web-indexer
npm install
npm run dev
```

3. Open:

```text
http://localhost:5173
```

### API quick check

```bash
curl "http://127.0.0.1:8010/api/transcripts?limit=5"
```
