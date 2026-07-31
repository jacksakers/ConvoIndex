# ConvoIndex Firmware — Phase 1 (LAFVIN AI Chatbot board)

PlatformIO project for the ESP32-S3 DevKit + LAFVIN AI Chatbot audio/screen
shield (ES8311 codec + ES7210 mic ADC, same silicon as the Espressif
ESP-BOX). This is Phase 1 of the ConvoIndex PRD ("The Dumb Pipe"): capture
I2S mic audio and stream it raw over a WebSocket so quality can be verified
before adding VAD, STT, LLM and TTS in later phases.

Pin mapping is reused verbatim from the existing ESP-IDF firmware in
`xiaozhi-esp32-main/main/boards/lafvin-aichatbot/` (`config.h` and
`lafvin-aichatbot.cc`), so no new hardware reverse-engineering was needed —
only the framework changed (ESP-IDF -> PlatformIO/Arduino).

## Why PlatformIO instead of ESP-IDF?

The full `xiaozhi-esp32-main` project is a large ESP-IDF codebase (LVGL,
MCP server, Kconfig, managed components, etc.) that's overkill for a
from-scratch ambient-listening device. This firmware is a fresh, minimal
Arduino/PlatformIO sketch that only depends on:

- [`links2004/WebSockets`](https://github.com/Links2004/arduinoWebSockets) — WebSocket client
- [`pschatzmann/arduino-audio-driver`](https://github.com/pschatzmann/arduino-audio-driver) — ES8311/ES7210 codec bring-up over I2C (the same combo driver, `AudioDriverES8311_ES7210`, used for the Espressif ESP-BOX)
- ESP-IDF's `driver/i2s_std.h` (bundled with arduino-esp32) for the actual I2S mic capture

## Setup

1. Install [PlatformIO](https://platformio.org/) (CLI or the VS Code extension).
2. Copy the WiFi/server config template and fill in your values:
   ```bash
   cp include/secrets.h.example include/secrets.h
   ```
   Edit `include/secrets.h` with your WiFi SSID/password and the IP address
   of the PC running `local-backend/capture_server.py`.
3. Build and flash (board must be in bootloader mode — hold BOOT, plug in
   USB, release BOOT):
   ```bash
   pio run -t upload
   pio device monitor
   ```

## Running the capture server

On your PC, from the repo root:

```bash
python -m local-backend.capture_server
```

This starts a WebSocket server on port 8005 (see `CAPTURE_PORT` in
`local-backend/config.py`).

Phase 1 behavior is unchanged: each streaming session is saved as a
timestamped WAV capture for playback and quality verification.

Phase 2 is now enabled in the same server:

- On WebSocket disconnect, the captured PCM is transcribed with local Whisper.
- A transcript row is inserted into SQLite at
  `captures/transcripts.db` (configurable via `TRANSCRIPT_DB_PATH`).
- Each row stores: session id, WAV path, start/end timestamps, duration,
  audio format metadata, and transcript text.

Quick check:

```bash
sqlite3 captures/transcripts.db \
  "select id, session_id, started_at, duration_seconds, substr(transcript,1,80) from transcripts order by id desc limit 5;"
```

## Behavior

- On boot, connects to WiFi and to the capture server.
- Device-side VAD is enabled: audio is only streamed while speech is
  detected (plus a short pre-roll and hangover to avoid clipped words).
- Press the BOOT button to pause/resume streaming.
- RGB LED behavior:
  - Idle: dim breathing cool tones
  - Recording: colorful speech-reactive animation
  - Paused/disconnected: distinct warning colors

## VAD + LED tuning

In `src/main.cpp` you can tune:

- `VAD_START_RMS` and `VAD_STOP_RMS`: detection sensitivity
- `VAD_HANGOVER_MS`: silence time before recording stops
- `VAD_PRE_ROLL_FRAMES`: short buffer before speech start
- `LED_GLOBAL_BRIGHTNESS`: overall LED intensity
