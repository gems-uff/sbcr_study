#!/usr/bin/env python3
"""Tests of run_annotator.py with a stand-in for the Messages API, so no call reaches a model.

The stand-in is a local HTTP server that the script reaches through `ANTHROPIC_BASE_URL`. It
answers `POST /v1/messages` with a response in the shape the API gives, built from the spec of
each test, and keeps the body and headers of each request. Needs the `anthropic` package
(environment `sbcr-analise`).

    python analysis/rq4/annotator/test_run_annotator.py
"""
import csv
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_annotator as ra  # noqa: E402

OUTPUT = {"case": "P01", "conflict": "c", "conflict_shape": "s", "version_1": "v1", "version_2": "v2",
          "resolution": "r", "candidate_a": "a", "candidate_b": "b", "empty_candidates": "none", "empty_versions": "none", "identical_candidates": "no",
          "closer": "A", "explanation": "e", "reading_notes": ""}
PACKAGE = "# Case P01\n"
MODEL = "claude-fable-5-1"


class Stand(http.server.BaseHTTPRequestHandler):
    """The Messages API as the tests need it: the answer comes from `server.spec`."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        spec = self.server.spec
        self.server.requests.append({"path": self.path, "body": body,
                                     "headers": {k.lower(): v for k, v in self.headers.items()}})
        time.sleep(spec.get("sleep", 0))
        if "status" in spec:
            reply, status = {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}, spec["status"]
        else:
            content = [{"type": "thinking", "thinking": "", "signature": "sig"}]
            if "tool_use" in spec:
                content.append({"type": "tool_use", "id": "t1", "name": "x", "input": {}})
            content.append({"type": "text", "text": json.dumps(spec.get("output"))})
            reply, status = {"id": "msg_1", "type": "message", "role": "assistant", "model": spec.get("model", MODEL),
                             "content": content, "stop_reason": spec.get("stop_reason", "end_turn"),
                             "stop_sequence": None, "stop_details": spec.get("stop_details"),
                             "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0,
                                       "cache_read_input_tokens": 7}}, 200
        data = json.dumps(reply).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("request-id", "req_1")
        self.end_headers()
        self.wfile.write(data)


class Instructions(unittest.TestCase):
    def test_labeling_prompt_and_schema(self):
        with open(ra.INSTRUCTIONS, encoding="utf-8") as fh:
            template = ra.part2(fh.read())
        self.assertTrue(template.startswith("You will receive one merge conflict case"))
        prompt = ra.labeling_prompt(template, SCHEME)
        for text in ("RULES-CONF: apply the first that fits.", "`C1` Adjacent: DEF-C1", "`FN` No candidate (predefined)",
                     "`FR` Other failure (residual)", "Answer field: `code_fail`"):
            self.assertIn(text, prompt)
        self.assertNotIn("{{SCHEME}}", prompt)
        schema = ra.labeling_schema(SCHEME)
        self.assertEqual(ra.check(LABEL, schema), [])
        self.assertTrue(ra.check(dict(LABEL, code_fail="F9"), schema))
        self.assertEqual(schema["properties"]["code_fail"]["enum"], ["FN", "F1", "FR"])
        one = {"version": "t", "dimensions": [SCHEME["dimensions"][0]]}
        self.assertIn("code", ra.labeling_schema(one)["required"])

    def test_residual_problems(self):
        self.assertEqual(ra.residual_problems(LABEL, SCHEME), [])
        self.assertTrue(ra.residual_problems(dict(LABEL, code_conf="CR"), SCHEME))
        self.assertEqual(ra.residual_problems(dict(LABEL, code_conf="CR", residual_description="d"), SCHEME), [])
        self.assertTrue(ra.residual_problems(dict(LABEL, residual_description="d"), SCHEME))

    def test_prompt_and_schema(self):
        with open(ra.INSTRUCTIONS, encoding="utf-8") as fh:
            prompt, schema = ra.part1(fh.read())
        self.assertTrue(prompt.startswith("You will read a package"))
        self.assertNotIn("--- end prompt ---", prompt)
        self.assertNotIn("## Part 2", prompt)
        self.assertTrue(prompt.rstrip().endswith("An empty string if none."))
        self.assertEqual(sorted(schema["required"]), sorted(OUTPUT))

    def test_check(self):
        with open(ra.INSTRUCTIONS, encoding="utf-8") as fh:
            _, schema = ra.part1(fh.read())
        self.assertEqual(ra.check(OUTPUT, schema), [])
        self.assertTrue(ra.check(dict(OUTPUT, closer="maybe"), schema))
        self.assertTrue(ra.check({k: v for k, v in OUTPUT.items() if k != "closer"}, schema))
        self.assertTrue(ra.check(dict(OUTPUT, extra="x"), schema))
        self.assertTrue(ra.check(None, schema))


SCHEME = {"version": "test", "dimensions": [
    {"id": "conf", "name": "Characteristic of the conflict", "rules": "RULES-CONF: apply the first that fits.",
     "categories": [{"code": "C1", "name": "Adjacent", "definition": "DEF-C1"},
                    {"code": "CR", "name": "Other conflict", "definition": "DEF-CR", "residual": True}]},
    {"id": "fail", "name": "Failure", "categories": [
        {"code": "FN", "name": "No candidate", "definition": "DEF-FN", "predefined": True},
        {"code": "F1", "name": "Takes one version", "definition": "DEF-F1"},
        {"code": "FR", "name": "Other failure", "definition": "DEF-FR", "residual": True}]}]}
LABEL = {"case": "P01", "code_conf": "C1", "code_fail": "F1", "secondary": "", "residual_description": "",
         "justification": "j"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stand)
        self.server.spec, self.server.requests = {}, []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.draw = os.path.join(self.tmp, "draw")
        os.makedirs(os.path.join(self.draw, "packages"))
        with open(os.path.join(self.draw, "coding_sheet.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["case", "role", "block", "position", "dataset", "chunk_id", "seed", "draw_date"])
            w.writerow(["P01", "pilot", 0, 1, "dataset1", "42", 1, "2026-09-28"])
        with open(os.path.join(self.draw, "packages", "P01.md"), "w") as fh:
            fh.write(PACKAGE)
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp)

    def run_script(self, spec, *extra, model=MODEL, key="test-key"):
        self.server.spec = spec
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{self.server.server_address[1]}"
        if key:
            env["ANTHROPIC_API_KEY"] = key
        return subprocess.run([sys.executable, os.path.join(HERE, "run_annotator.py"), "--draw", self.draw,
                               "--cases", "P01", "--model", model, "--effort", "high", "--out", self.out,
                               "--max-retries", "0", *extra], capture_output=True, text=True, env=env)

    def record(self, k=1):
        with open(os.path.join(self.out, "P01", f"run{k}.json")) as fh:
            return json.load(fh)


class Run(Base):
    def test_records_a_run(self):
        r = self.run_script({"output": OUTPUT}, "--runs", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.record(2)
        self.assertEqual(rec["output"], OUTPUT)
        self.assertEqual((rec["model"], rec["model_requested"], rec["effort"], rec["stop_reason"], rec["request_id"]),
                         (MODEL, MODEL, "high", "end_turn", "req_1"))
        self.assertEqual(rec["usage"]["cache_read_input_tokens"], 7)
        self.assertTrue(os.path.exists(os.path.join(self.out, "P01", "run2.response.json")))
        self.assertEqual(len(self.server.requests), 2)
        req = self.server.requests[-1]
        self.assertEqual(req["path"], "/v1/messages")
        self.assertEqual(req["headers"].get("x-api-key"), "test-key")
        body = req["body"]
        self.assertEqual((body["model"], body["output_config"]["effort"]), (MODEL, "high"))
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(sorted(body["output_config"]["format"]["schema"]["required"]), sorted(OUTPUT))
        # no tool, no fallback to another model, no thinking or sampling setting
        for key in ("tools", "tool_choice", "fallbacks", "thinking", "temperature", "top_p", "top_k"):
            self.assertNotIn(key, body)
        self.assertEqual(body["messages"], [{"role": "user", "content": PACKAGE}])
        self.assertEqual(body["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertTrue(body["system"][0]["text"].startswith("You will read a package"))

    def test_skips_a_run_already_written(self):
        self.assertEqual(self.run_script({"output": OUTPUT}).returncode, 0)
        r = self.run_script({"output": dict(OUTPUT, closer="B")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.record()["output"]["closer"], "A")

    def test_refuses_an_answer_that_asks_for_a_tool(self):
        r = self.run_script({"output": OUTPUT, "tool_use": True})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("asked for a tool", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.json")))

    def test_refuses_an_output_off_the_schema(self):
        r = self.run_script({"output": dict(OUTPUT, closer="maybe")})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not match the schema", r.stderr)

    def test_refuses_an_alias(self):
        r = self.run_script({"output": OUTPUT}, model="fable")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("full name", r.stderr)

    def test_refuses_an_answer_from_another_model(self):
        r = self.run_script({"output": OUTPUT, "model": "claude-opus-5-5"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("came from model claude-opus-5-5", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.json")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.response.json")))
        self.assertTrue(os.path.exists(os.path.join(self.out, "P01", "run1.failed1.response.json")))

    def failures(self):
        return ra.read_failures(os.path.join(self.out, "P01", "run1.failures.jsonl"))

    def test_a_run_tried_again_keeps_and_counts_the_failed_calls(self):
        self.run_script({"output": OUTPUT, "stop_reason": "max_tokens"})
        self.run_script({"output": None, "stop_reason": "refusal",
                         "stop_details": {"type": "refusal", "category": "cyber", "explanation": "x"}})
        self.run_script({"status": 529})
        r = self.run_script({"output": OUTPUT})
        self.assertEqual(r.returncode, 0, r.stderr)
        failures = self.failures()
        self.assertEqual([f["failure"] for f in failures], [1, 2, 3])
        self.assertEqual([f["service"] for f in failures], [False, False, True])
        self.assertEqual([f["response"] for f in failures],
                         ["run1.failed1.response.json", "run1.failed2.response.json", None])
        self.assertIn("max_tokens", failures[0]["error"])
        self.assertIn("the model refused", failures[1]["error"])
        self.assertIn("the API answered 529", failures[2]["error"])
        with open(os.path.join(self.out, "P01", "run1.failed1.response.json")) as fh:
            self.assertEqual(json.load(fh)["stop_reason"], "max_tokens")
        with open(os.path.join(self.out, "P01", "run1.failed2.response.json")) as fh:
            self.assertEqual(json.load(fh)["stop_reason"], "refusal")
        rec = self.record()
        self.assertEqual((rec["failed_calls"], rec["failed_service_calls"]), (2, 1))
        self.assertEqual(rec["stop_reason"], "end_turn")

    def test_a_run_with_no_failed_call_counts_none(self):
        self.run_script({"output": OUTPUT})
        self.assertEqual((self.record()["failed_calls"], self.record()["failed_service_calls"]), (0, 0))
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.failures.jsonl")))

    def test_stops_on_a_refusal(self):
        r = self.run_script({"output": None, "stop_reason": "refusal",
                             "stop_details": {"type": "refusal", "category": "cyber", "explanation": "x"}})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the model refused", r.stderr)
        self.assertIn("cyber", r.stderr)

    def test_stops_on_max_tokens(self):
        r = self.run_script({"output": OUTPUT, "stop_reason": "max_tokens"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("raise --max-tokens", r.stderr)

    def test_stops_a_call_that_takes_too_long(self):
        r = self.run_script({"output": OUTPUT, "sleep": 3}, "--timeout", "1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("took more than 1 s", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.json")))

    def test_stops_on_a_failed_call(self):
        r = self.run_script({"status": 400})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the API answered 400", r.stderr)

    def test_needs_the_api_key(self):
        r = self.run_script({"output": OUTPUT}, key=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ANTHROPIC_API_KEY", r.stderr)
        self.assertEqual(self.server.requests, [])

    def test_refuses_a_draw_folder_with_the_sealed_file(self):
        open(os.path.join(self.draw, "sealed_sample.csv"), "w").close()
        r = self.run_script({"output": OUTPUT})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sealed_sample.csv", r.stderr)


class Labeling(Base):
    def setUp(self):
        super().setUp()
        self.scheme = os.path.join(self.tmp, "scheme.json")
        with open(self.scheme, "w") as fh:
            json.dump(SCHEME, fh)
        self.desc = os.path.join(self.tmp, "desc")
        os.makedirs(os.path.join(self.desc, "P01"))
        with open(os.path.join(self.desc, "P01", "run1.json"), "w") as fh:
            json.dump({"case": "P01", "run": 1, "step": "description", "instructions_sha256": "abc",
                       "package_sha256": ra.sha256(PACKAGE), "output": OUTPUT}, fh)

    def label(self, spec, *extra):
        return self.run_script(spec, "--step", "labeling", "--scheme", self.scheme, "--descriptions", self.desc, *extra)

    def test_records_a_label(self):
        r = self.label({"output": LABEL})
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.out, "P01", "run1.json")) as fh:
            rec = json.load(fh)
        self.assertEqual((rec["step"], rec["output"], rec["problems"], rec["description_run"]), ("labeling", LABEL, [], 1))
        for key in ("instructions_sha256", "instructions_commit", "model_requested", "effort", "scheme_sha256",
                    "description_sha256"):
            self.assertIn(key, rec)
        self.assertEqual(rec["package_sha256"], ra.sha256(PACKAGE))
        body = self.server.requests[-1]["body"]
        # the message is the description, then the package (revision of 2026-10-19)
        message = body["messages"][0]["content"]
        self.assertEqual(message, ra.labeling_message(OUTPUT, PACKAGE))
        description, package = message.split("\n# Package of the case\n\n")
        self.assertEqual(json.loads(description.split("```json\n")[1].split("\n```")[0]), OUTPUT)
        self.assertEqual(package, PACKAGE)
        self.assertIn("RULES-CONF", body["system"][0]["text"])
        schema = body["output_config"]["format"]["schema"]
        self.assertEqual(schema["properties"]["code_conf"]["enum"], ["C1", "CR"])
        self.assertIn("code_conf C1, code_fail F1", r.stdout)

    def test_a_residual_without_description_is_kept_and_reported(self):
        r = self.label({"output": dict(LABEL, code_fail="FR")})
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.out, "P01", "run1.json")) as fh:
            self.assertTrue(json.load(fh)["problems"])
        self.assertIn("problem:", r.stdout)

    def test_refuses_an_answer_about_another_case(self):
        r = self.label({"output": dict(LABEL, case="P02")})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("names case", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.json")))

    def test_refuses_a_description_that_names_another_case(self):
        with open(os.path.join(self.desc, "P01", "run1.json"), "w") as fh:
            json.dump({"case": "P01", "run": 1, "step": "description", "instructions_sha256": "abc",
                       "output": dict(OUTPUT, case="P1")}, fh)
        r = self.label({"output": LABEL})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the description names case 'P1'", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.response.json")))

    def test_refuses_a_description_of_another_package(self):
        with open(os.path.join(self.draw, "packages", "P01.md"), "w") as fh:
            fh.write(PACKAGE + "changed\n")
        r = self.label({"output": LABEL})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("written from another package", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.response.json")))

    def test_refuses_a_code_outside_the_scheme(self):
        r = self.label({"output": dict(LABEL, code_fail="F9")})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not match the schema", r.stderr)

    def test_needs_the_description(self):
        r = self.label({"output": LABEL}, "--description-run", "2")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no description", r.stderr)

    def test_refuses_a_scheme_the_application_refuses(self):
        bad = json.loads(json.dumps(SCHEME))
        bad["dimensions"][0]["categories"][1]["residual"] = False
        with open(self.scheme, "w") as fh:
            json.dump(bad, fh)
        r = self.label({"output": LABEL})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("residual", r.stderr)

    def add_case_without_description(self):
        with open(os.path.join(self.draw, "coding_sheet.csv"), "a", newline="") as fh:
            csv.writer(fh).writerow(["P02", "pilot", 0, 2, "dataset1", "43", 1, "2026-09-28"])
        with open(os.path.join(self.draw, "packages", "P02.md"), "w") as fh:
            fh.write("# Case P02\n")

    def test_stops_at_the_first_failed_case(self):
        self.add_case_without_description()
        r = self.label({"output": LABEL}, "--cases", "P02,P01")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P01", "run1.json")))

    def test_keep_going_runs_the_cases_after_a_failed_one(self):
        self.add_case_without_description()
        r = self.label({"output": LABEL}, "--cases", "P02,P01", "--keep-going")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAILED P02", r.stderr)
        self.assertIn("1 of 2 cases failed and have no record: P02", r.stderr)
        self.assertEqual(self.record()["output"], LABEL)
        self.assertFalse(os.path.exists(os.path.join(self.out, "P02", "run1.json")))

    def test_keep_going_goes_on_after_an_error_of_the_case(self):
        self.add_case_without_description()
        r = self.label({"status": 400}, "--cases", "P01,P02", "--keep-going")
        self.assertIn("2 of 2 cases failed", r.stderr)
        self.assertEqual(len(self.server.requests), 1)

    def test_keep_going_stops_on_a_failure_of_the_service(self):
        self.add_case_without_description()
        for status in (401, 429, 529):
            r = self.label({"status": status}, "--cases", "P01,P02", "--keep-going")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(f"the API answered {status}", r.stderr)
            self.assertNotIn("cases failed", r.stderr)

    def test_a_refused_key_exits_with_its_own_status(self):
        self.add_case_without_description()
        for status, code in ((401, ra.KEY_EXIT), (403, ra.KEY_EXIT), (429, 1), (529, 1), (400, 1)):
            r = self.label({"status": status}, "--cases", "P01", "--keep-going")
            self.assertEqual(r.returncode, code, (status, r.stderr))
            self.assertIn(f"the API answered {status}", r.stderr)


if __name__ == "__main__":
    unittest.main()
