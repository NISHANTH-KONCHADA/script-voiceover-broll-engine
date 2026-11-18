"""Live proof of HMAC-SHA256 webhook delivery and cryptographic signature validation."""

import asyncio
import hashlib
import hmac
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx

RECEIVED_CALLBACK = {}
SECRET_KEY = "incubrix_assessment_hmac_secret_proof_2027"


class WebhookReceiverHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len)

        sig_header = self.headers.get("X-IncuBrix-Signature", "")
        event_header = self.headers.get("X-IncuBrix-Event", "")
        received_hash = sig_header.split("sha256=")[-1].strip() if sig_header.startswith("sha256=") else ""

        computed_hash = hmac.new(SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        is_valid = hmac.compare_digest(received_hash, computed_hash)

        try:
            parsed_json = json.loads(raw_body.decode("utf-8"))
        except Exception:
            parsed_json = {}

        RECEIVED_CALLBACK["headers"] = dict(self.headers)
        RECEIVED_CALLBACK["raw_body_len"] = len(raw_body)
        RECEIVED_CALLBACK["raw_signature_header"] = sig_header
        RECEIVED_CALLBACK["received_hash"] = received_hash
        RECEIVED_CALLBACK["computed_hash"] = computed_hash
        RECEIVED_CALLBACK["signature_matches"] = is_valid
        RECEIVED_CALLBACK["event"] = event_header
        RECEIVED_CALLBACK["payload"] = parsed_json
        RECEIVED_CALLBACK["received_at"] = time.time()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "verified", "accepted": true}')

    def log_message(self, format, *args):
        # Silence default stderr logging
        pass


def run_receiver_server(port: int = 8055):
    server = HTTPServer(("0.0.0.0", port), WebhookReceiverHandler)
    server.serve_forever()


async def main():
    port = 8055
    server_thread = threading.Thread(target=run_receiver_server, args=(port,), daemon=True)
    server_thread.start()
    print(f"Started local HMAC Webhook Receiver listening on 0.0.0.0:{port}/webhook")

    async with httpx.AsyncClient(timeout=45.0) as client:
        # Submit job to the engine with callback_url pointing to host.docker.internal:8055/webhook
        callback_url = f"http://host.docker.internal:{port}/webhook"
        payload = {
            "script": "Solar farms and wind turbines supply reliable carbon-neutral electricity.",
            "voice": "en-IN-female",
            "aspect_ratios": ["16:9"],
            "callback_url": callback_url,
            "webhook_secret": SECRET_KEY,
        }

        print(f"Submitting job to engine with callback_url={callback_url}...")
        resp = await client.post("http://localhost:8000/api/v1/broll/jobs", json=payload)
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
        data = resp.json()
        job_id = data["job_id"]
        status_url = f"http://localhost:8000{data['check_status_url']}"
        print(f"Job enqueued: {job_id}. Awaiting completion and callback...")

        for i in range(30):
            await asyncio.sleep(1.0)
            st = await client.get(status_url)
            st_data = st.json()
            if st_data["status"] in ("succeeded", "failed"):
                print(f"Job finished with status: {st_data['status']}")
                break

        # Allow brief moment for webhook dispatch
        for _ in range(10):
            if RECEIVED_CALLBACK:
                break
            await asyncio.sleep(0.5)

        if not RECEIVED_CALLBACK:
            print("ERROR: Webhook was not received!")
            return

        print("\n=======================================================")
        print("          CRYPTOGRAPHIC WEBHOOK VERIFICATION PROOF     ")
        print("=======================================================")
        print(f"Event Received: {RECEIVED_CALLBACK.get('event')}")
        print(f"Header 'X-IncuBrix-Signature': {RECEIVED_CALLBACK.get('raw_signature_header')}")
        print(f"Received Hash (Client):  {RECEIVED_CALLBACK.get('received_hash')}")
        print(f"Computed Hash (Secret):  {RECEIVED_CALLBACK.get('computed_hash')}")
        print(f"Cryptographic Match:     {RECEIVED_CALLBACK.get('signature_matches')}")
        print("Payload Job ID:         ", RECEIVED_CALLBACK.get("payload", {}).get("job_id"))
        print("Payload Status:         ", RECEIVED_CALLBACK.get("payload", {}).get("status"))
        print("Payload Outputs:")
        print(json.dumps(RECEIVED_CALLBACK.get("payload", {}).get("outputs", {}), indent=2))
        print("=======================================================")


if __name__ == "__main__":
    asyncio.run(main())
