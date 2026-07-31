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
import json
import logging
import os
import struct
import uuid
import wave
from collections import deque
from datetime import datetime, timezone

import websockets

from . import config
from .stt import SpeechToText
from .transcript_store import TranscriptStore
from .transcript_api import start_transcript_api_server_in_thread
from .vad import EnergyVAD

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("CaptureServer")

stt_engine = SpeechToText()
transcript_store = TranscriptStore(config.TRANSCRIPT_DB_PATH)


def _compute_audio_metrics(pcm_data):
    sample_count = len(pcm_data) // 2
    if sample_count <= 0:
        return 0.0, 0

    samples = struct.unpack(f"<{sample_count}h", pcm_data)
    sum_squares = 0
    peak_abs = 0
    for sample in samples:
        abs_sample = abs(sample)
        if abs_sample > peak_abs:
            peak_abs = abs_sample
        sum_squares += sample * sample
    avg_rms = (sum_squares / sample_count) ** 0.5
    return float(avg_rms), int(peak_abs)


async def _persist_segment(
    session_id,
    wav_path,
    started_at_iso,
    ended_at_iso,
    segment_index,
    segment_started_at_iso,
    segment_ended_at_iso,
    pcm_bytes,
):
    duration_s = len(pcm_bytes) / (
        config.CAPTURE_SAMPLE_RATE * config.CAPTURE_SAMPLE_WIDTH * config.CAPTURE_CHANNELS
    )
    if duration_s < config.TRANSCRIPT_MIN_DURATION_SECONDS:
        logger.info(
            "Skipping short segment [%s#%s]: %.2fs < %.2fs",
            session_id,
            segment_index,
            duration_s,
            config.TRANSCRIPT_MIN_DURATION_SECONDS,
        )
        return False

    transcript = (await asyncio.to_thread(stt_engine.transcribe, pcm_bytes)).strip()
    if not transcript and not config.TRANSCRIPT_STORE_EMPTY:
        logger.info("No transcript text for [%s#%s]; skipping DB insert", session_id, segment_index)
        return False

    avg_rms, peak_abs = _compute_audio_metrics(pcm_bytes)
    word_count = len(transcript.split()) if transcript else 0
    char_count = len(transcript)

    await asyncio.to_thread(
        transcript_store.add_transcript,
        session_id,
        wav_path,
        started_at_iso,
        ended_at_iso,
        duration_s,
        config.CAPTURE_SAMPLE_RATE,
        config.CAPTURE_CHANNELS,
        config.CAPTURE_SAMPLE_WIDTH,
        segment_index,
        segment_started_at_iso,
        segment_ended_at_iso,
        word_count,
        char_count,
        avg_rms,
        peak_abs,
        stt_engine.model_size,
        stt_engine.input_gain,
        transcript,
    )
    logger.info("Stored transcript [%s#%s]: %s", session_id, segment_index, transcript if transcript else "<empty>")
    return True


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
    session_pcm = bytearray()

    segment_on_silence = bool(getattr(config, "SEGMENT_ON_SILENCE", True))
    device_vad_mode = False
    vad = EnergyVAD()
    max_pre_roll_bytes = int(
        max(0.0, float(getattr(config, "SEGMENT_PRE_ROLL_SECONDS", 0.25)))
        * config.CAPTURE_SAMPLE_RATE
        * config.CAPTURE_SAMPLE_WIDTH
        * config.CAPTURE_CHANNELS
    )
    pre_roll_chunks = deque()
    pre_roll_size = 0
    segment_buffer = bytearray()
    segment_started_at_dt = None
    speaking_active = False
    segment_index = 0
    stored_segments = 0

    def _append_pre_roll(chunk):
        nonlocal pre_roll_size
        if max_pre_roll_bytes <= 0:
            return
        pre_roll_chunks.append(chunk)
        pre_roll_size += len(chunk)
        while pre_roll_chunks and pre_roll_size > max_pre_roll_bytes:
            pre_roll_size -= len(pre_roll_chunks.popleft())

    async def _finalize_segment(segment_ended_at_dt, session_ended_at_dt=None):
        nonlocal segment_buffer, segment_started_at_dt, speaking_active, segment_index, stored_segments
        if not segment_buffer:
            speaking_active = False
            segment_started_at_dt = None
            return

        effective_session_end = session_ended_at_dt or segment_ended_at_dt

        segment_index += 1
        was_stored = await _persist_segment(
            session_id=session_id,
            wav_path=filename,
            started_at_iso=started_at_dt.isoformat(),
            ended_at_iso=effective_session_end.isoformat(),
            segment_index=segment_index,
            segment_started_at_iso=(segment_started_at_dt or started_at_dt).isoformat(),
            segment_ended_at_iso=segment_ended_at_dt.isoformat(),
            pcm_bytes=bytes(segment_buffer),
        )
        if was_stored:
            stored_segments += 1

        segment_buffer = bytearray()
        segment_started_at_dt = None
        speaking_active = False
    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    logger.debug("Ignoring non-JSON text message for [%s]: %s", session_id, message)
                    continue

                if payload.get("type") == "vad":
                    device_vad_mode = True
                    vad_state = payload.get("state")
                    now_dt = datetime.now(timezone.utc)

                    if vad_state == "start":
                        if speaking_active and segment_buffer:
                            await _finalize_segment(now_dt)
                        speaking_active = True
                        segment_started_at_dt = now_dt
                        segment_buffer = bytearray()
                        pre_roll_chunks.clear()
                        pre_roll_size = 0
                        logger.info("Device VAD start [%s]", session_id)
                    elif vad_state == "stop":
                        if speaking_active and segment_buffer:
                            await _finalize_segment(now_dt)
                        speaking_active = False
                        segment_started_at_dt = None
                        segment_buffer = bytearray()
                        pre_roll_chunks.clear()
                        pre_roll_size = 0
                        logger.info("Device VAD stop [%s]", session_id)
                continue

            if isinstance(message, bytes):
                wav_file.writeframes(message)
                total_bytes += len(message)
                session_pcm.extend(message)

                if not segment_on_silence:
                    continue

                if device_vad_mode:
                    if speaking_active:
                        segment_buffer.extend(message)
                    continue

                _append_pre_roll(message)
                vad_result = vad.process_frame(message)
                now_dt = datetime.now(timezone.utc)

                if vad_result == "start" and not speaking_active:
                    speaking_active = True
                    segment_started_at_dt = now_dt
                    segment_buffer = bytearray()
                    for chunk in pre_roll_chunks:
                        segment_buffer.extend(chunk)

                if speaking_active and vad_result != "start":
                    segment_buffer.extend(message)

                if vad_result == "stop":
                    await _finalize_segment(now_dt)
                    pre_roll_chunks.clear()
                    pre_roll_size = 0
                elif vad_result == "noise":
                    segment_buffer = bytearray()
                    segment_started_at_dt = None
                    speaking_active = False
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        wav_file.close()
        ended_at_dt = datetime.now(timezone.utc)
        duration_s = total_bytes / (
            config.CAPTURE_SAMPLE_RATE * config.CAPTURE_SAMPLE_WIDTH * config.CAPTURE_CHANNELS
        )
        logger.info(f"Saved {filename} ({total_bytes} bytes, ~{duration_s:.1f}s)")

        if segment_on_silence and speaking_active and segment_buffer:
            await _finalize_segment(ended_at_dt, session_ended_at_dt=ended_at_dt)

        if segment_on_silence:
            if stored_segments == 0 and duration_s >= config.TRANSCRIPT_MIN_DURATION_SECONDS:
                logger.info("No VAD segments stored for [%s]; falling back to full-session transcription", session_id)
                await _persist_segment(
                    session_id=session_id,
                    wav_path=filename,
                    started_at_iso=started_at_dt.isoformat(),
                    ended_at_iso=ended_at_dt.isoformat(),
                    segment_index=1,
                    segment_started_at_iso=started_at_dt.isoformat(),
                    segment_ended_at_iso=ended_at_dt.isoformat(),
                    pcm_bytes=bytes(session_pcm),
                )
            logger.info("Session [%s] complete. Stored segments: %s", session_id, stored_segments)
            return

        await _persist_segment(
            session_id=session_id,
            wav_path=filename,
            started_at_iso=started_at_dt.isoformat(),
            ended_at_iso=ended_at_dt.isoformat(),
            segment_index=1,
            segment_started_at_iso=started_at_dt.isoformat(),
            segment_ended_at_iso=ended_at_dt.isoformat(),
            pcm_bytes=bytes(session_pcm),
        )


async def main():
    logger.info("=" * 60)
    logger.info("ConvoIndex Phase 2 Capture + Transcription Server")
    logger.info(f"Listening on ws://{config.HOST}:{config.CAPTURE_PORT}/capture")
    logger.info(f"Saving WAV files to ./{config.CAPTURE_DIR}/")
    logger.info(f"Storing transcripts in ./{config.TRANSCRIPT_DB_PATH}")
    logger.info(f"Transcript API: http://{config.TRANSCRIPT_API_HOST}:{config.TRANSCRIPT_API_PORT}")
    logger.info("=" * 60)

    start_transcript_api_server_in_thread()

    server = await websockets.serve(
        handle_connection,
        config.HOST,
        config.CAPTURE_PORT,
        ping_interval=None,
    )
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
