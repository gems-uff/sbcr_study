#!/usr/bin/env python3
"""A stand-in for the Messages API, for testing run_scale.sh with no call to a model.

Answers `POST /v1/messages` on 127.0.0.1 with a response in the shape the API gives: model
`claude-fable-5-1`, stop reason `end_turn`, and a JSON object built from the schema the request
sends (`output_config.format.schema`), with the first value of each enum, `x` in every other
string, and in `case` the identifier of the case, read from the line `# Case <id>` of the
message. The answer says nothing about the case, so the outputs serve only to test the runner.
With `--fail`, the cases listed get stop reason `max_tokens`, which run_annotator.py refuses, so
that the runner can be tested on a case that fails every time. Each request is logged to
`--log` as one line, `<case> <step>`.

    python analysis/rq4/annotator/stand_in_api.py --port 8765 --log requests.txt --fail S0005
    ANTHROPIC_BASE_URL=http://127.0.0.1:8765 ANTHROPIC_API_KEY=test ... run_scale.sh
"""
import argparse
import http.server
import json
import re
import threading

MODEL = "claude-fable-5-1"


def output(schema, case):
    return {k: case if k == "case" else (p["enum"][0] if "enum" in p else "x")
            for k, p in schema["properties"].items()}


class Stand(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        message = body["messages"][0]["content"]
        m = re.search(r"^# Case (\S+)$", message, re.M)
        case = m.group(1) if m else "?"
        step = "labeling" if message.startswith("# Your description") else "description"
        with self.server.lock, open(self.server.log, "a") as fh:
            fh.write(f"{case} {step}\n")
        schema = body["output_config"]["format"]["schema"]
        reply = {"id": "msg_stand_in", "type": "message", "role": "assistant", "model": MODEL,
                 "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                             {"type": "text", "text": json.dumps(output(schema, case))}],
                 "stop_reason": "max_tokens" if case in self.server.fail else "end_turn",
                 "stop_sequence": None, "stop_details": None,
                 "usage": {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 0,
                           "cache_read_input_tokens": 5000}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("request-id", "req_stand_in")
        self.end_headers()
        self.wfile.write(data)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--log", required=True, help="file that gets one line per request")
    p.add_argument("--fail", default="", help="comma-separated cases answered with stop reason max_tokens")
    args = p.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Stand)
    server.log, server.fail, server.lock = args.log, set(filter(None, args.fail.split(","))), threading.Lock()
    server.serve_forever()


if __name__ == "__main__":
    main()
