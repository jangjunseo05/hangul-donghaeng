"""Secret-free local receiver: distinguishes proxy rejection from service rejection."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

COUNTS = {"GET_health": 0, "POST_health": 0, "POST_reservations": 0}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            COUNTS["GET_health"] += 1
            self.reply(200, {"status": "security-test-receiver"})
        elif self.path == "/counts":
            self.reply(200, COUNTS)
        else:
            self.reply(404, {})

    def do_POST(self):
        if self.path == "/reservations":
            COUNTS["POST_reservations"] += 1
            self.reply(200, {"unexpected_reservation_reached_receiver": True})
            return
        if self.path == "/api/health":
            COUNTS["POST_health"] += 1
            self.reply(200, {"unexpected_write_reached_receiver": True})
        else:
            self.reply(404, {})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8009)
    args = parser.parse_args()
    print("Controlled security receiver listening; no credentials or product jobs.", flush=True)
    HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
