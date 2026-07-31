import logging
import asyncio
import subprocess
import os
import tempfile
from . import config

logger = logging.getLogger("TTS")

# Try to import edge_tts
try:
    import edge_tts
except ImportError:
    edge_tts = None

class TextToSpeech:
    def __init__(self, provider=config.TTS_PROVIDER, voice=config.TTS_VOICE):
        self.provider = provider
        self.voice = voice
        
        if self.provider == "edge_tts" and edge_tts is None:
            logger.warning("edge-tts is not installed. TTS will fall back to offline/mock mode.")

    async def generate_tts_pcm(self, text):
        """
        Generates TTS for the given text and returns 16kHz mono 16-bit PCM bytes.
        """
        if not text:
            return b""

        if self.provider == "edge_tts" and edge_tts is not None:
            try:
                logger.info(f"Generating TTS using edge-tts (Voice: {self.voice})...")
                # Create a temp file for edge-tts output (which is MP3)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
                    tmp_mp3_name = tmp_mp3.name
                
                try:
                    communicate = edge_tts.Communicate(text, self.voice)
                    await communicate.save(tmp_mp3_name)
                    
                    # Read the generated MP3 file
                    with open(tmp_mp3_name, "rb") as f:
                        mp3_bytes = f.read()
                finally:
                    # Clean up the temp file
                    if os.path.exists(tmp_mp3_name):
                        os.remove(tmp_mp3_name)

                # Convert MP3 bytes to 16kHz Mono 16-bit PCM using FFmpeg
                logger.info("Converting TTS MP3 to 16kHz PCM via FFmpeg...")
                pcm_bytes = self._mp3_to_pcm(mp3_bytes)
                logger.info(f"Generated {len(pcm_bytes)} bytes of PCM audio.")
                return pcm_bytes
            except Exception as e:
                logger.error(f"edge-tts generation or conversion failed: {e}")
                return b""
        else:
            logger.warning("TTS falling back to generate silent PCM (mock mode).")
            # Return 2 seconds of silence
            return b"\x00" * (config.SAMPLE_RATE * config.BYTES_PER_SAMPLE * 2)

    def _mp3_to_pcm(self, mp3_bytes):
        """
        Uses FFmpeg via subprocess to convert MP3 to 16000Hz mono s16le PCM.
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", "pipe:0",
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", str(config.SAMPLE_RATE),
            "-ac", str(config.CHANNELS),
            "pipe:1"
        ]
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            pcm_data, stderr = process.communicate(input=mp3_bytes)
            if process.returncode != 0:
                logger.error(f"FFmpeg returned error code {process.returncode}: {stderr.decode('utf-8', errors='ignore')}")
                return b""
            return pcm_data
        except FileNotFoundError:
            logger.error("FFmpeg was not found on your system! Please install FFmpeg and make sure it is in your PATH.")
            return b""
        except Exception as e:
            logger.error(f"FFmpeg execution failed: {e}")
            return b""
