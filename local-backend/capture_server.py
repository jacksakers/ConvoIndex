"""
ConvoIndex Phase 1: "The Dumb Pipe"

Minimal WebSocket server that accepts raw 16-bit PCM audio frames streamed
from the ESP32 firmware (firmware/convoindex) and writes each connected
session to a timestamped WAV file, so mic capture quality can be verified
by ear before any VAD/STT/LLM processing is added in later phases.

Run with:
    python -m local-backend.capture_server
"""

import asyncio
import logging
import os
import wave
from datetime import datetime

import websockets

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CaptureServer")


async def handle_connection(websocket):
    os.makedirs(config.CAPTURE_DIR, exist_ok=True)
    filename = os.path.join(
        config.CAPTURE_DIR, f"capture_{datetime.now():%Y%m%d_%H%M%S}.wav"
    )
    wav_file = wave.open(filename, "wb")
    wav_file.setnchannels(config.CAPTURE_CHANNELS)
    wav_file.setsampwidth(config.CAPTURE_SAMPLE_WIDTH)
    wav_file.setframerate(config.CAPTURE_SAMPLE_RATE)

    logger.info(f"New capture session -> {filename}")
    total_bytes = 0
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                wav_file.writeframes(message)
                total_bytes += len(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        wav_file.close()
        duration_s = total_bytes / (config.CAPTURE_SAMPLE_RATE * config.CAPTURE_SAMPLE_WIDTH * config.CAPTURE_CHANNELS)
        logger.info(f"Saved {filename} ({total_bytes} bytes, ~{duration_s:.1f}s)")


async def main():
    logger.info("=" * 60)
    logger.info("ConvoIndex Phase 1 Capture Server")
    logger.info(f"Listening on ws://{config.HOST}:{config.CAPTURE_PORT}/capture")
    logger.info(f"Saving WAV files to ./{config.CAPTURE_DIR}/")
    logger.info("=" * 60)

    server = await websockets.serve(handle_connection, config.HOST, config.CAPTURE_PORT)
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
