"""
ConvoIndex Phase 2: "Transcription + Storage"

WebSocket server that accepts raw 16-bit PCM audio frames streamed from the
ESP32 firmware, writes each session to a timestamped WAV file, transcribes
the captured PCM with Whisper, and stores transcript rows in SQLite with
session timestamps for later indexing/search.

Run with:
    python -m local-backend.capture_server
"""

import asyncio
import logging
import os
import uuid
import wave
from datetime import datetime, timezone

import websockets

from . import config
from .stt import SpeechToText
from .transcript_store import TranscriptStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CaptureServer")

stt_engine = SpeechToText()
transcript_store = TranscriptStore(config.TRANSCRIPT_DB_PATH)


async def handle_connection(websocket):
    os.makedirs(config.CAPTURE_DIR, exist_ok=True)
    session_id = f"capture_{uuid.uuid4().hex[:8]}"
    started_at_dt = datetime.now(timezone.utc)
    filename = os.path.join(config.CAPTURE_DIR, f"{session_id}_{started_at_dt:%Y%m%d_%H%M%S}.wav")
    wav_file = wave.open(filename, "wb")
    wav_file.setnchannels(config.CAPTURE_CHANNELS)
    wav_file.setsampwidth(config.CAPTURE_SAMPLE_WIDTH)
    wav_file.setframerate(config.CAPTURE_SAMPLE_RATE)

    logger.info(f"New capture session [{session_id}] -> {filename}")
    total_bytes = 0
    pcm_buffer = bytearray()
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                wav_file.writeframes(message)
                total_bytes += len(message)
                pcm_buffer.extend(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        wav_file.close()
        ended_at_dt = datetime.now(timezone.utc)
        duration_s = total_bytes / (
            config.CAPTURE_SAMPLE_RATE * config.CAPTURE_SAMPLE_WIDTH * config.CAPTURE_CHANNELS
        )
        logger.info(f"Saved {filename} ({total_bytes} bytes, ~{duration_s:.1f}s)")

        if duration_s < config.TRANSCRIPT_MIN_DURATION_SECONDS:
            logger.info(
                "Skipping transcription for short clip [%s]: %.2fs < %.2fs",
                session_id,
                duration_s,
                config.TRANSCRIPT_MIN_DURATION_SECONDS,
            )
            return

        transcript = stt_engine.transcribe(bytes(pcm_buffer)).strip()
        if not transcript and not config.TRANSCRIPT_STORE_EMPTY:
            logger.info("No transcript text for [%s]; skipping DB insert", session_id)
            return

        transcript_store.add_transcript(
            session_id=session_id,
            wav_path=filename,
            started_at=started_at_dt.isoformat(),
            ended_at=ended_at_dt.isoformat(),
            duration_seconds=duration_s,
            sample_rate=config.CAPTURE_SAMPLE_RATE,
            channels=config.CAPTURE_CHANNELS,
            sample_width=config.CAPTURE_SAMPLE_WIDTH,
            transcript=transcript,
        )
        logger.info("Stored transcript [%s]: %s", session_id, transcript if transcript else "<empty>")


async def main():
    logger.info("=" * 60)
    logger.info("ConvoIndex Phase 2 Capture + Transcription Server")
    logger.info(f"Listening on ws://{config.HOST}:{config.CAPTURE_PORT}/capture")
    logger.info(f"Saving WAV files to ./{config.CAPTURE_DIR}/")
    logger.info(f"Storing transcripts in ./{config.TRANSCRIPT_DB_PATH}")
    logger.info("=" * 60)

    server = await websockets.serve(handle_connection, config.HOST, config.CAPTURE_PORT)
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
