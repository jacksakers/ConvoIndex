import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config
from .transcript_store import TranscriptStore

logger = logging.getLogger("TranscriptAPI")
store = TranscriptStore(config.TRANSCRIPT_DB_PATH)


class TranscriptApiHandler(BaseHTTPRequestHandler):
    server_version = "ConvoIndexTranscriptAPI/0.1"

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"ok": True})
            return

        if parsed.path == "/api/transcripts":
            params = parse_qs(parsed.query)
            search = (params.get("q", [""])[0] or "").strip()
            limit_raw = params.get("limit", ["50"])[0]
            offset_raw = params.get("offset", ["0"])[0]

            try:
                limit = int(limit_raw)
                offset = int(offset_raw)
            except ValueError:
                self._send_json(400, {"error": "limit and offset must be integers"})
                return

            rows, total = store.list_transcripts(
                search=search if search else None,
                limit=limit,
                offset=offset,
            )
            self._send_json(
                200,
                {
                    "items": rows,
                    "total": total,
                    "limit": max(1, min(limit, 200)),
                    "offset": max(0, offset),
                    "query": search,
                },
            )
            return

        self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)


def start_transcript_api_server():
    server = ThreadingHTTPServer((config.TRANSCRIPT_API_HOST, config.TRANSCRIPT_API_PORT), TranscriptApiHandler)
    logger.info(
        "Transcript API listening on http://%s:%s",
        config.TRANSCRIPT_API_HOST,
        config.TRANSCRIPT_API_PORT,
    )
    server.serve_forever()


def start_transcript_api_server_in_thread():
    thread = threading.Thread(target=start_transcript_api_server, daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    start_transcript_api_server()
