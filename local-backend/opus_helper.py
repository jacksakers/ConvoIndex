import logging
import sys
from . import config

logger = logging.getLogger("OpusHelper")

# Try to import opuslib
try:
    import opuslib
except ImportError:
    opuslib = None

class OpusDecoder:
    def __init__(self, sample_rate=config.SAMPLE_RATE, channels=config.CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.decoder = None
        
        if opuslib is not None:
            try:
                self.decoder = opuslib.Decoder(self.sample_rate, self.channels)
                logger.info(f"OpusDecoder initialized at {self.sample_rate}Hz, {self.channels} channel(s).")
            except Exception as e:
                logger.error(f"Failed to initialize opuslib Decoder: {e}")
        else:
            logger.warning("Using mock OpusDecoder because 'opuslib' is not installed.")

    def decode(self, opus_data):
        """
        Decodes an Opus packet to 16-bit PCM.
        """
        if self.decoder is not None:
            try:
                # Calculate expected sample count
                # 60ms of 16kHz audio = 960 samples
                samples = config.SAMPLES_PER_FRAME
                pcm_data = self.decoder.decode(opus_data, samples)
                return pcm_data
            except Exception as e:
                logger.error(f"Opus decode error: {e}")
                return b""
        else:
            # Fallback mock: just return empty pcm or print info
            return b""


class OpusEncoder:
    def __init__(self, sample_rate=config.SAMPLE_RATE, channels=config.CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.encoder = None
        
        if opuslib is not None:
            try:
                # APPLICATION_AUDIO (2049) is standard for generic audio
                self.encoder = opuslib.Encoder(self.sample_rate, self.channels, opuslib.APPLICATION_AUDIO)
                logger.info(f"OpusEncoder initialized at {self.sample_rate}Hz, {self.channels} channel(s).")
            except Exception as e:
                logger.error(f"Failed to initialize opuslib Encoder: {e}")
        else:
            logger.warning("Using mock OpusEncoder because 'opuslib' is not installed.")

    def encode(self, pcm_data):
        """
        Encodes 16-bit PCM (must match frame size) to an Opus packet.
        pcm_data should be SAMPLES_PER_FRAME * BYTES_PER_SAMPLE bytes.
        """
        if self.encoder is not None:
            try:
                samples = config.SAMPLES_PER_FRAME
                # Ensure the input length matches what the encoder expects
                expected_len = samples * config.BYTES_PER_SAMPLE
                if len(pcm_data) < expected_len:
                    # Pad with silence
                    pcm_data = pcm_data + b"\x00" * (expected_len - len(pcm_data))
                elif len(pcm_data) > expected_len:
                    # Truncate
                    pcm_data = pcm_data[:expected_len]

                opus_packet = self.encoder.encode(pcm_data, samples)
                return opus_packet
            except Exception as e:
                logger.error(f"Opus encode error: {e}")
                return b""
        else:
            # Mock fallback: return empty
            return b""
