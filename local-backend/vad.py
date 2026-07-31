import struct
import math
import time
from . import config

class EnergyVAD:
    """
    A simple, lightweight energy-based Voice Activity Detector (VAD).
    Uses root-mean-square (RMS) of PCM audio frames to detect speech onset and offset.
    """
    def __init__(self, threshold=config.VAD_THRESHOLD, silence_seconds=config.VAD_SILENCE_SECONDS, min_speech_seconds=config.VAD_MIN_SPEECH_SECONDS):
        self.threshold = threshold
        self.silence_seconds = silence_seconds
        self.min_speech_seconds = min_speech_seconds
        
        self.is_speaking_detected = False
        self.last_speech_time = 0.0
        self.silence_start_time = None
        self.speech_start_time = None

    def reset(self):
        self.is_speaking_detected = False
        self.last_speech_time = 0.0
        self.silence_start_time = None
        self.speech_start_time = None

    def calculate_rms(self, pcm_frame):
        sample_count = len(pcm_frame) // 2
        if sample_count == 0:
            return 0.0
        shorts = struct.unpack(f"<{sample_count}h", pcm_frame)
        sum_squares = sum(s * s for s in shorts)
        return math.sqrt(sum_squares / sample_count)

    def process_frame(self, pcm_frame):
        """
        Process a PCM frame and return:
        - "start": when speech has just been detected
        - "stop": when end-of-speech has been detected
        - "continue": speech is ongoing or silence is ongoing
        - None: no speech detected
        """
        rms = self.calculate_rms(pcm_frame)
        current_time = time.time()
        
        if rms > self.threshold:
            self.last_speech_time = current_time
            self.silence_start_time = None
            
            if not self.is_speaking_detected:
                self.is_speaking_detected = True
                self.speech_start_time = current_time
                return "start"
            return "continue"
        else:
            if self.is_speaking_detected:
                if self.silence_start_time is None:
                    self.silence_start_time = current_time
                
                silence_dur = current_time - self.silence_start_time
                if silence_dur >= self.silence_seconds:
                    speech_dur = current_time - self.speech_start_time - silence_dur
                    if speech_dur >= self.min_speech_seconds:
                        self.reset()
                        return "stop"
                    else:
                        # Too short (noise), reset
                        self.reset()
                        return "noise"
                return "continue"
            return None
