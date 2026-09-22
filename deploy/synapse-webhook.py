#!/usr/bin/env python3
"""
synapse-webhook.py — Forgejo push webhook receiver.

Listens for POST /hook from Forgejo, verifies the HMAC-SHA256 signature,
and spawns generate.sh asynchronously so the HTTP response returns immediately.

Configuration via environment variables (set in /etc/synapse/webhook.env):
  SYNAPSE_WEBHOOK_SECRET  — shared secret configured in the Forgejo webhook
  SYNAPSE_WEBHOOK_PORT    — TCP port the receiver binds to (default: 9000)
  SYNAPSE_GENERATE_SH     — path to generate.sh (default: /opt/synapse/generate.sh)
"""

import hashlib
import hmac
import http.server
import os
import subprocess
import sys

SECRET      = os.environ.get("SYNAPSE_WEBHOOK_SECRET", "").encode()
PORT        = int(os.environ.get("SYNAPSE_WEBHOOK_PORT", "9000"))
GENERATE_SH = os.environ.get("SYNAPSE_GENERATE_SH", "/opt/synapse/generate.sh")


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    server_version = "SynapseWebhook/1.0"

    def log_message(self, fmt, *args):  # route to stdout for journald
        print(fmt % args, flush=True)

    def do_POST(self):
        if self.path != "/hook":
            self._respond(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        if not self._verify(body):
            print("Webhook rejected: bad or missing signature", flush=True)
            self._respond(403)
            return

        self._respond(200)

        # Spawn generate.sh detached so this request returns immediately.
        subprocess.Popen(
            [GENERATE_SH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"Webhook accepted — spawned {GENERATE_SH}", flush=True)

    def _respond(self, code: int):
        self.send_response(code)
        self.end_headers()

    def _verify(self, body: bytes) -> bool:
        if not SECRET:
            return True  # No secret set → allow all (not recommended for production)
        sig_header = self.headers.get("X-Gitea-Signature", "")
        # Forgejo may send "sha256=<hex>" or bare "<hex>" — strip prefix if present.
        sig = sig_header.removeprefix("sha256=")
        expected = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)


if __name__ == "__main__":
    if not SECRET:
        print(
            "WARNING: SYNAPSE_WEBHOOK_SECRET is not set — any POST to /hook will trigger regeneration.",
            flush=True,
        )
    server = http.server.HTTPServer(("127.0.0.1", PORT), WebhookHandler)
    print(f"Synapse webhook receiver on 127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
