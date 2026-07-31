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
`local-backend/config.py`) that writes each streaming session to a
timestamped WAV file under `local-backend/captures/` for playback and
quality verification.

## Behavior

- On boot, connects to WiFi and to the capture server, then streams mono
  16 kHz / 16-bit PCM continuously.
- Press the BOOT button to pause/resume streaming (useful for isolating
  clips during testing).
- The speaker amp (PA) stays disabled — this phase is capture-only.
