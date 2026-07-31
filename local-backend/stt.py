import logging
import io
import wave
from . import config

logger = logging.getLogger("STT")

# Try to import numpy and whisper
try:
    import numpy as np
    import whisper
except ImportError:
    np = None
    whisper = None

class SpeechToText:
    def __init__(self, provider=config.STT_PROVIDER, model_size=config.WHISPER_MODEL_SIZE):
        self.provider = provider
        self.model_size = model_size
        self.input_gain = max(0.1, float(getattr(config, "STT_INPUT_GAIN", 1.0)))
        self.model = None
        
        if self.provider == "local_whisper" and whisper is not None:
            logger.info(f"Loading local Whisper model '{self.model_size}' (this may take a moment)...")
            try:
                self.model = whisper.load_model(self.model_size)
                logger.info("Whisper model loaded successfully!")
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}")
        elif whisper is None:
            logger.warning("Whisper or NumPy is not installed. STT will fall back to mock mode.")

    def transcribe(self, pcm_data):
        """
        Transcribe 16kHz mono 16-bit PCM data.
        Returns the transcribed text as a string.
        """
        if not pcm_data:
            return ""

        if self.provider == "local_whisper" and self.model is not None and np is not None:
            try:
                # Convert PCM bytes to float32 NumPy array normalized to [-1.0, 1.0]
                audio_np = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
                if self.input_gain != 1.0:
                    audio_np = np.clip(audio_np * self.input_gain, -1.0, 1.0)
                
                # Run Whisper transcription
                logger.info("Transcribing audio with Whisper...")
                result = self.model.transcribe(audio_np, fp16=False)
                text = result.get("text", "").strip()
                logger.info(f"Transcription result: '{text}'")
                return text
            except Exception as e:
                logger.error(f"Whisper transcription failed: {e}")
                return "[Error transcribing audio]"
        else:
            logger.info("STT Mock Mode: Whisper not loaded. Returning fallback text.")
            return "hello world"
