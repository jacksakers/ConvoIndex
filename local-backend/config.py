# Configuration for the Local AI Chatbot Backend

# Server connection settings
HOST = "0.0.0.0"
# Port for the WebSocket real-time audio connection
WEBSOCKET_PORT = 8004
# Port for the HTTP OTA check-in server (handles GET and POST requests cleanly)
OTA_PORT = 8003

# ConvoIndex Phase 1: raw-audio capture WebSocket server (see capture_server.py)
CAPTURE_PORT = 8005
CAPTURE_SAMPLE_RATE = 16000
CAPTURE_CHANNELS = 1
CAPTURE_SAMPLE_WIDTH = 2  # bytes (16-bit PCM)
CAPTURE_DIR = "captures"

# Ollama settings (Local LLM)
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:0.5b"  # Change to any fast local model you have installed, e.g. "qwen2.5:0.5b" or "phi3"
# HTTP connect timeout (seconds) for reaching the Ollama server
OLLAMA_CONNECT_TIMEOUT = 5
# HTTP read timeout (seconds) for waiting on model generation output
OLLAMA_READ_TIMEOUT = 60
# Number of retries for transient network or timeout failures
OLLAMA_MAX_RETRIES = 2
# Delay (seconds) between retry attempts
OLLAMA_RETRY_BACKOFF_SECONDS = 1.5
# Keep model loaded in memory to reduce cold-start latency; examples: "5m", "30m", "1h"
OLLAMA_KEEP_ALIVE = "30m"

# Speech-to-Text (STT) Settings
# Choose "local_whisper" for on-device whisper, or "api" if using external APIs.
STT_PROVIDER = "local_whisper" 
WHISPER_MODEL_SIZE = "tiny"  # Choose from 'tiny', 'base', 'small', etc. 'tiny' is extremely fast on CPU.

# Text-to-Speech (TTS) Settings
# Provider can be "edge_tts" (Microsoft Edge, high quality, free but requires internet) or "pyttsx3" (fully offline, lower quality)
TTS_PROVIDER = "edge_tts"
TTS_VOICE = "en-US-GuyNeural"  # e.g., "en-US-GuyNeural" or "zh-CN-XiaoxiaoNeural"

# Voice Activity Detection (VAD) Settings
# Energy threshold for speaking. Adjust based on mic sensitivity and noise level.
VAD_THRESHOLD = 400
# Silence duration in seconds to trigger end-of-speech detection
VAD_SILENCE_SECONDS = 3
# Minimum speech duration to prevent accidental triggers (coughing, clicks)
VAD_MIN_SPEECH_SECONDS = 0.3

# Audio Parameters (Matches ESP32 S3 hardware config)
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION_MS = 60
SAMPLES_PER_FRAME = int(SAMPLE_RATE * (FRAME_DURATION_MS / 1000.0))  # 960 samples for 60ms
BYTES_PER_SAMPLE = 2  # 16-bit audio
FRAME_BYTES = SAMPLES_PER_FRAME * BYTES_PER_SAMPLE  # 1920 bytes
