import logging
import time
import requests
from . import config

logger = logging.getLogger("LLM")

class LocalLLM:
    def __init__(self, ollama_url=config.OLLAMA_URL, model=config.OLLAMA_MODEL):
        self.ollama_url = ollama_url
        self.model = model
        self.connect_timeout = config.OLLAMA_CONNECT_TIMEOUT
        self.read_timeout = config.OLLAMA_READ_TIMEOUT
        self.max_retries = config.OLLAMA_MAX_RETRIES
        self.retry_backoff_seconds = config.OLLAMA_RETRY_BACKOFF_SECONDS
        self.keep_alive = config.OLLAMA_KEEP_ALIVE
        self.http = requests.Session()
        # session_id -> list of messages
        self.history = {}
        
        # System prompt to keep responses concise for voice output
        self.system_prompt = (
            "You are a helpful, friendly, and concise local AI voice assistant. "
            "Keep your responses relatively brief (1-3 sentences maximum) and suitable for being read aloud. "
            "Do not include any Markdown, bullet points, asterisks, or special emojis that cannot be spoken."
        )

    def clear_history(self, session_id):
        if session_id in self.history:
            del self.history[session_id]
            logger.info(f"Cleared history for session {session_id}")

    def generate_response(self, session_id, user_text):
        """
        Send user text to Ollama and return the assistant's reply.
        Maintains conversational history per session_id.
        """
        if not user_text:
            return ""

        # Initialize history if not exists
        if session_id not in self.history:
            self.history[session_id] = [
                {"role": "system", "content": self.system_prompt}
            ]

        # Append user message
        self.history[session_id].append({"role": "user", "content": user_text})

        # Limit history to prevent massive contexts (keep last 10 turns + system prompt)
        if len(self.history[session_id]) > 11:
            # Keep the system prompt at index 0, and the last 10 messages
            self.history[session_id] = [self.history[session_id][0]] + self.history[session_id][-10:]

        url = f"{self.ollama_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": self.history[session_id],
            "stream": False,
            "keep_alive": self.keep_alive,
        }

        total_attempts = max(1, self.max_retries + 1)
        logger.info(
            "Sending request to Ollama (%s) [timeout=%ss/%ss, attempts=%s]...",
            self.model,
            self.connect_timeout,
            self.read_timeout,
            total_attempts,
        )

        last_error = None
        for attempt in range(1, total_attempts + 1):
            try:
                response = self.http.post(
                    url,
                    json=payload,
                    timeout=(self.connect_timeout, self.read_timeout),
                )
                if response.status_code == 200:
                    result = response.json()
                    assistant_message = result.get("message", {})
                    reply = assistant_message.get("content", "").strip()

                    # Append assistant reply to history
                    self.history[session_id].append({"role": "assistant", "content": reply})

                    logger.info(f"Ollama reply: '{reply}'")
                    return reply

                logger.error(
                    "Ollama returned status code %s on attempt %s/%s: %s",
                    response.status_code,
                    attempt,
                    total_attempts,
                    response.text,
                )
                # Retry only on 5xx server errors.
                if response.status_code < 500 or attempt == total_attempts:
                    return "Sorry, I encountered an error communicating with my local brain."
            except requests.exceptions.Timeout as exc:
                last_error = exc
                logger.warning(
                    "Ollama request timed out on attempt %s/%s (connect=%ss, read=%ss): %s",
                    attempt,
                    total_attempts,
                    self.connect_timeout,
                    self.read_timeout,
                    exc,
                )
                if attempt == total_attempts:
                    return (
                        "My local model is taking longer than expected to respond. "
                        "Please try again, or increase OLLAMA_READ_TIMEOUT in config.py."
                    )
            except requests.exceptions.RequestException as exc:
                last_error = exc
                logger.error(
                    "Ollama connection error on attempt %s/%s: %s",
                    attempt,
                    total_attempts,
                    exc,
                )
                if attempt == total_attempts:
                    return "I cannot connect to my local Ollama server. Please make sure Ollama is running."

            if attempt < total_attempts:
                time.sleep(self.retry_backoff_seconds)

        logger.error("Unexpected Ollama failure state: %s", last_error)
        return "Sorry, I encountered an unexpected local model error."
