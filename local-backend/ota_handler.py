import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from . import config

logger = logging.getLogger("OTAHandler")

class OTARequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default terminal logs to prevent clutter
        pass

    def do_GET(self):
        if self.path in ("/ota", "/ota/"):
            self.send_ota_response()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Local AI Chatbot OTA Server is running!\n")

    def do_POST(self):
        if self.path in ("/ota", "/ota/"):
            # Read content length and safely read payload to allow standard HTTP post requests
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                _ = self.rfile.read(content_length)
            except Exception as e:
                logger.debug(f"Error reading POST body: {e}")
            self.send_ota_response()
        else:
            self.send_response(404)
            self.end_headers()

    def send_ota_response(self):
        """
        Builds and sends the dynamic JSON configuration back to the ESP32.
        Dynamically extracts your PC's IP to avoid manual routing configuration.
        """
        host_header = self.headers.get("Host", f"127.0.0.1:{config.WEBSOCKET_PORT}")
        host_ip = host_header.split(":")[0]
        
        # Build the dynamic websocket URL
        websocket_url = f"ws://{host_ip}:{config.WEBSOCKET_PORT}"
        
        config_payload = {
            "websocket": {
                "url": websocket_url,
                "token": "local_trust_token",
                "version": 1
            }
        }
        
        body = json.dumps(config_payload).encode("utf-8")
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        logger.info(f"Served OTA config response (WebSocket URL: {websocket_url})")


def start_ota_server():
    """
    Starts the HTTP OTA server in a daemon thread so it doesn't block the main event loop.
    """
    try:
        server = HTTPServer((config.HOST, config.OTA_PORT), OTARequestHandler)
        logger.info(f"OTA HTTP Server successfully started on http://{config.HOST}:{config.OTA_PORT}")
        
        # Start serving in a background thread
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    except Exception as e:
        logger.error(f"Failed to start OTA HTTP Server: {e}")
        return None
