import asyncio
import json
import logging
import uuid
import websockets
from . import config
from .opus_helper import OpusDecoder, OpusEncoder
from .stt import SpeechToText
from .llm import LocalLLM
from .tts import TextToSpeech
from .vad import EnergyVAD
from .ota_handler import start_ota_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Server")

# Initialize engines
stt_engine = SpeechToText()
llm_engine = LocalLLM()
tts_engine = TextToSpeech()

class ChatbotConnection:
    def __init__(self, websocket):
        self.websocket = websocket
        self.session_id = f"local_{uuid.uuid4().hex[:8]}"
        self.state = "idle"  # idle, listening, processing, speaking
        
        # Audio buffer and VAD helper
        self.audio_buffer = bytearray()
        self.vad = EnergyVAD()
        
        # Audio codecs
        self.decoder = OpusDecoder()
        self.encoder = OpusEncoder()

    async def run(self):
        logger.info(f"New connection. Assigned Session ID: {self.session_id}")
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    await self.handle_text_message(message)
                elif isinstance(message, bytes):
                    await self.handle_binary_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection closed: {self.session_id}")
        except Exception as e:
            logger.error(f"Error in session {self.session_id}: {e}", exc_info=True)
        finally:
            self.state = "idle"

    async def handle_text_message(self, message_str):
        try:
            data = json.loads(message_str)
            msg_type = data.get("type")
            logger.info(f"[{self.session_id}] Received Text: {data}")
            
            if msg_type == "hello":
                hello_response = {
                    "type": "hello",
                    "transport": "websocket",
                    "session_id": self.session_id,
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": config.SAMPLE_RATE,
                        "channels": config.CHANNELS,
                        "frame_duration": config.FRAME_DURATION_MS
                    }
                }
                await self.websocket.send(json.dumps(hello_response))
                logger.info(f"[{self.session_id}] Handshake complete.")
                
            elif msg_type == "listen":
                state = data.get("state")
                if state == "start":
                    self.state = "listening"
                    self.audio_buffer.clear()
                    self.vad.reset()
                    logger.info(f"[{self.session_id}] Device listening...")
                elif state == "stop":
                    if self.state == "listening":
                        await self.process_user_audio()
                        
            elif msg_type == "abort":
                logger.info(f"[{self.session_id}] Abort request. Resetting.")
                self.state = "idle"
                
        except json.JSONDecodeError:
            logger.error(f"JSON decode failed for: {message_str}")

    async def handle_binary_message(self, message_bytes):
        if self.state != "listening":
            return
        
        pcm_frame = self.decoder.decode(message_bytes)
        if not pcm_frame:
            return
        
        self.audio_buffer.extend(pcm_frame)
        
        # Process frame through VAD
        vad_result = self.vad.process_frame(pcm_frame)
        if vad_result == "start":
            logger.info(f"[{self.session_id}] Speech began...")
        elif vad_result == "stop":
            logger.info(f"[{self.session_id}] Speech ended. Processing audio...")
            await self.process_user_audio()
        elif vad_result == "noise":
            logger.info(f"[{self.session_id}] Silence timeout / noise. Clearing buffer.")
            self.audio_buffer.clear()

    async def process_user_audio(self):
        self.state = "processing"
        
        pcm_data = bytes(self.audio_buffer)
        self.audio_buffer.clear()
        
        # 1. Speech-to-Text (STT)
        transcribed_text = stt_engine.transcribe(pcm_data)
        if not transcribed_text:
            logger.info(f"[{self.session_id}] Speech was silent/empty.")
            self.state = "idle"
            return
            
        await self.websocket.send(json.dumps({
            "session_id": self.session_id,
            "type": "stt",
            "text": transcribed_text
        }))
        
        # 2. Local LLM (Ollama)
        reply_text = llm_engine.generate_response(self.session_id, transcribed_text)
        if not reply_text:
            self.state = "idle"
            return
            
        await self.websocket.send(json.dumps({
            "session_id": self.session_id,
            "type": "tts",
            "state": "sentence_start",
            "text": reply_text
        }))
        
        # 3. Text-to-Speech (TTS)
        tts_pcm = await tts_engine.generate_tts_pcm(reply_text)
        if not tts_pcm:
            self.state = "idle"
            return
            
        # 4. Stream Audio packets back as Opus
        self.state = "speaking"
        await self.websocket.send(json.dumps({
            "session_id": self.session_id,
            "type": "tts",
            "state": "start"
        }))
        
        logger.info(f"[{self.session_id}] Streaming TTS audio response...")
        pre_buffer_frames = 5
        frame_bytes = config.FRAME_BYTES
        sleep_time = config.FRAME_DURATION_MS / 1000.0
        
        for idx, i in enumerate(range(0, len(tts_pcm), frame_bytes)):
            if self.state != "speaking":
                break  # Aborted
                
            chunk = tts_pcm[i:i+frame_bytes]
            if len(chunk) < frame_bytes:
                chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
                
            opus_packet = self.encoder.encode(chunk)
            if opus_packet:
                await self.websocket.send(opus_packet)
                
            if idx >= pre_buffer_frames:
                await asyncio.sleep(sleep_time)
                
        await self.websocket.send(json.dumps({
            "session_id": self.session_id,
            "type": "tts",
            "state": "stop"
        }))
        logger.info(f"[{self.session_id}] Speaking complete.")
        self.state = "idle"

async def main():
    logger.info("=" * 60)
    logger.info("Starting Local AI Chatbot WebSocket & OTA Server")
    logger.info(f"WebSocket Address: ws://{config.HOST}:{config.WEBSOCKET_PORT}")
    logger.info(f"Ollama Target URL: {config.OLLAMA_URL} ({config.OLLAMA_MODEL})")
    logger.info("=" * 60)
    
    # Start the standard-library HTTP OTA Server in a background daemon thread
    start_ota_server()
    
    async def ws_handler(websocket):
        conn = ChatbotConnection(websocket)
        await conn.run()
        
    server = await websockets.serve(
        ws_handler, 
        config.HOST, 
        config.WEBSOCKET_PORT
    )
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
