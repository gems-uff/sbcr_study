#!/usr/bin/env python3
"""Runs the two steps of the RQ4 automatic annotator, description and labeling, one call per case.

The annotator is Claude Fable 5.1 (`claude-fable-5-1`) at effort `high`, called through the
Messages API with the official Python SDK (`anthropic`). The prompt and the JSON schema come from
the instructions file (`--instructions`, by default `docs/annotator-instructions-v1.md`): the prompt
of the step is the system prompt of the call, and the package of the case is the message. Each
call:

- sends no tool, so the model cannot run code, read files or reach the web, and cannot compute the
  similarities the package hides;
- asks for the answer as one JSON object constrained by the schema of the step
  (`output_config.format`), and checks it again against the schema;
- fixes the model, by its full name, and the effort, and refuses an answer from another model. It
  sends no `fallbacks`, so a refusal stops the run, or with `--keep-going` the case;
- sends no `thinking` field and no sampling parameter: thinking is always on in Claude Fable 5.1,
  and the model accepts no temperature, so the outputs vary between runs;
- marks the system prompt for caching, and gives each request a time limit (`--timeout`) and
  retries (`--max-retries`).

The key goes to the SDK through `ANTHROPIC_API_KEY`, never on the command line; paste it with
`read -rs`, as below. The script refuses to start without it.

Inputs: `<draw>/packages/<case>.md` and `<draw>/coding_sheet.csv`; a `--draw` folder that holds the
sealed or reveal files is refused. The labeling step (`--step labeling`) also reads the description
of each case (`--descriptions`, run `--description-run`) and the frozen scheme (`--scheme`): the line
`{{SCHEME}}` of the prompt of part 2 is replaced by the scheme, the message is the description, as
a JSON object, followed by the package, and the JSON schema of the answer allows only the codes of
each dimension. A description written from another package than the one in `--draw` is refused.

Outputs, in `--out`, per case and run: `<case>/run<k>.json` (the output and the record of the call:
model asked for and model that answered, effort, SDK version, message and request ids, stop reason,
token counts with the cache, dates, hashes of the package, of the instructions and, in labeling, of
the scheme, the description and the prompt, the version of the instructions, and the failed calls
before it) and `<case>/run<k>.response.json`, the raw response. A run already written is skipped.
Each failed call is logged in `<case>/run<k>.failures.jsonl`, and a response the script does not
accept is kept as `<case>/run<k>.failed<n>.response.json`. A failure of the connection or of the
service stops the run even with `--keep-going`; a refused key (401) or permission (403) exits with
status 3.

    read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY
    python analysis/rq4/annotator/run_annotator.py --draw <sample folder> --cases 1 \
        --model claude-fable-5-1 --effort high --out <dir>/block1-description
    python analysis/rq4/annotator/run_annotator.py --step labeling --draw <sample folder> \
        --scheme analysis/rq4/scheme/coding-scheme.json --descriptions <dir>/block1-description \
        --cases 1 --model claude-fable-5-1 --effort high --out <dir>/block1-labeling
"""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

import anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
INSTRUCTIONS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "docs", "annotator-instructions-v1.md"))
sys.path.insert(0, os.path.join(HERE, ".."))
from packages import check_draw_folder, check_scheme  # noqa: E402
BEGIN, END = "--- begin prompt ---", "--- end prompt ---"
# aliases name whatever model they point to on the day, so only full names are accepted
FULL_MODEL = re.compile(r"^claude-[a-z]+-\d+(-\d+)*$")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# answers that say nothing about the case: the key, the permissions or the rate limit, which the
# SDK has already retried, and, with any status of 500 or more, the service itself
SERVICE_STATUS = (401, 403, 429)


class ServiceFailure(SystemExit):
    """A failure of the connection or of the service, which would fail the next case too."""


# the key itself, or its permissions: no call succeeds until the author gives another key, so the
# script exits with a status of its own, which run_scale.sh reads to stop every shard at once
KEY_STATUS = (401, 403)
KEY_EXIT = 3


class KeyFailure(ServiceFailure):
    """The API refused the key (401) or its permissions (403)."""


def read_failures(path):
    """The failed calls logged for a case and run, oldest first."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def part1(instructions):
    """The prompt of part 1 and the JSON schema of its output, from the instructions file."""
    # the markers are lines of their own; the explanation at the top of the file also quotes them
    m = re.search(rf"^{re.escape(BEGIN)}$(.*?)^{re.escape(END)}$", instructions, re.S | re.M)
    prompt = m.group(1).strip() + "\n"
    schemas = instructions[instructions.index("## JSON schemas of the outputs"):]
    schema = json.loads(re.search(r"```json\n(.*?)```", schemas, re.S).group(1))
    return prompt, schema


def part2(instructions):
    """The prompt of part 2, with the line {{SCHEME}} where the scheme goes."""
    blocks = re.findall(rf"^{re.escape(BEGIN)}$(.*?)^{re.escape(END)}$", instructions, re.S | re.M)
    prompt = blocks[1].strip() + "\n"
    if prompt.count("{{SCHEME}}") != 1:
        raise SystemExit("the prompt of part 2 must hold the line {{SCHEME}} once")
    return prompt


def labeling_message(description, package):
    """The message of part 2: the case's description, as a JSON object, then its package, unchanged."""
    return ("# Your description of the case\n\n```json\n" + json.dumps(description, ensure_ascii=False, indent=1)
            + "\n```\n\n# Package of the case\n\n" + package)


def code_field(scheme, dim):
    return "code" if len(scheme["dimensions"]) == 1 else f"code_{dim['id']}"


def render_scheme(scheme):
    """The scheme as the prompt of part 2 shows it, every text as the scheme file has it."""
    parts = []
    for dim in scheme["dimensions"]:
        lines = [f"Dimension `{dim['id']}`: {dim['name']}. Answer field: `{code_field(scheme, dim)}`."]
        if dim.get("rules"):
            lines += ["", dim["rules"].strip()]
        lines.append("")
        for c in dim["categories"]:
            tag = " (predefined)" if c.get("predefined") else " (residual)" if c.get("residual") else ""
            lines.append(f"- `{c['code']}` {c['name']}{tag}: {c['definition'].strip()}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def labeling_prompt(template, scheme):
    return template.replace("{{SCHEME}}", render_scheme(scheme))


def labeling_schema(scheme):
    """The JSON schema of the answer of part 2, with the codes of each dimension as the only values."""
    fields = {code_field(scheme, d): {"type": "string", "enum": [c["code"] for c in d["categories"]]}
              for d in scheme["dimensions"]}
    props = {"case": {"type": "string"}, **fields, "secondary": {"type": "string"},
             "residual_description": {"type": "string"}, "justification": {"type": "string"}}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def residual_problems(output, scheme):
    """A residual category without its description, or a description without a residual category."""
    chosen = [output.get(code_field(scheme, d)) in {c["code"] for c in d["categories"] if c.get("residual")}
              for d in scheme["dimensions"]]
    described = bool((output.get("residual_description") or "").strip())
    if any(chosen) and not described:
        return ["a residual category was chosen with no residual_description"]
    if described and not any(chosen):
        return ["residual_description is given, but no residual category was chosen"]
    return []


def check(value, schema):
    """The problems of an output against the part 1 schema: an object of strings, some with an enum."""
    if not isinstance(value, dict):
        return ["the output is not a JSON object"]
    props = schema["properties"]
    problems = [f"missing field {k}" for k in schema["required"] if k not in value]
    problems += [f"unexpected field {k}" for k in value if k not in props]
    for k, v in value.items():
        if k not in props:
            continue
        if not isinstance(v, str):
            problems.append(f"{k} is not a string")
        elif "enum" in props[k] and v not in props[k]["enum"]:
            problems.append(f"{k} is {v!r}, not one of {props[k]['enum']}")
    return problems


def instructions_version(path):
    """The published version of the instructions file (`v0`, `v1`), from its name, and whether the
    file differs from the commit of the checkout that holds it (None outside Git)."""
    m = re.search(r"-(v\d+)\.md$", path)
    version = m.group(1) if m else os.path.basename(path)
    r = subprocess.run(["git", "-C", os.path.dirname(path), "status", "--porcelain", "--", path],
                       capture_output=True, text=True)
    return version, (bool(r.stdout.strip()) if r.returncode == 0 else None)


def call(client, model, effort, max_tokens, prompt, schema, message):
    """One request to the Messages API with no tool, the step's prompt as the system prompt and
    the case as the only message. Returns the response."""
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        # the same in every call of a step, so it is cached after the first call
        system=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": message}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )


def read_response(msg, schema, model):
    """What the record keeps of a response, and the reason it failed, or None."""
    rec = {"model": msg.model, "message_id": msg.id, "request_id": getattr(msg, "_request_id", None),
           "stop_reason": msg.stop_reason, "usage": msg.usage.to_dict() if msg.usage else None,
           "content_types": [b.type for b in msg.content]}
    details = getattr(msg, "stop_details", None)
    if details is not None:
        rec["stop_details"] = details.to_dict() if hasattr(details, "to_dict") else details
    if msg.model != model:
        return rec, f"the answer came from model {msg.model}, not {model}"
    if msg.stop_reason == "refusal":
        return rec, f"the model refused: {rec.get('stop_details')}"
    if msg.stop_reason != "end_turn":
        return rec, f"the call stopped with {msg.stop_reason}" + (
            "; raise --max-tokens" if msg.stop_reason == "max_tokens" else "")
    if any(b.type == "tool_use" for b in msg.content):
        return rec, "the answer asked for a tool, and the call has none"
    text = next((b.text for b in msg.content if b.type == "text"), None)
    try:
        output = json.loads(text) if text is not None else None
    except json.JSONDecodeError as e:
        return rec, f"the answer is not JSON: {e}"
    problems = check(output, schema)
    if problems:
        return rec, "output does not match the schema: " + "; ".join(problems)
    rec["output"] = output
    return rec, None


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--instructions", default=INSTRUCTIONS, help="instructions file (default: v1)")
    p.add_argument("--draw", required=True, help="folder with packages/ and coding_sheet.csv")
    p.add_argument("--cases", required=True, help="pilot, all, or a comma-separated list of cases")
    p.add_argument("--runs", type=int, default=1, help="calls per case (the pilot test uses more than one)")
    p.add_argument("--model", required=True, help="full model name, claude-fable-5-1 for the annotator")
    p.add_argument("--effort", required=True, choices=EFFORTS, help="effort of the model, the same in every run")
    p.add_argument("--timeout", type=int, default=900, help="seconds a request may take (default 900)")
    p.add_argument("--max-retries", type=int, default=2,
                   help="retries of a failed connection, rate limit or server error (default 2)")
    p.add_argument("--max-tokens", type=int, default=16000, help="output tokens of a call, thinking included (default 16000)")
    p.add_argument("--out", required=True, help="folder for the outputs")
    p.add_argument("--step", choices=("description", "labeling"), default="description",
                   help="part 1 of the instructions (default) or part 2")
    p.add_argument("--scheme", help="labeling: the frozen scheme")
    p.add_argument("--descriptions", help="labeling: the --out folder of the description step")
    p.add_argument("--description-run", type=int, default=1, help="labeling: the run of the description to label (default 1)")
    p.add_argument("--keep-going", action="store_true",
                   help="after a failed case, go on with the next one, and stop with an error at the end")
    args = p.parse_args()
    labeling = args.step == "labeling"
    if labeling and not (args.scheme and args.descriptions):
        raise SystemExit("--step labeling needs --scheme and --descriptions")

    if not FULL_MODEL.match(args.model):
        raise SystemExit(f"--model {args.model}: give the full name of the model, such as claude-fable-5-1, not an alias")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("set ANTHROPIC_API_KEY, the key of the API credits, with read -rs")
    draw, out = os.path.expanduser(args.draw), os.path.expanduser(args.out)
    check_draw_folder(draw)
    with open(os.path.join(draw, "coding_sheet.csv"), encoding="utf-8", newline="") as fh:
        sheet = list(csv.DictReader(fh))
    if args.cases == "pilot":
        cases = [r["case"] for r in sheet if r["role"] == "pilot"]
    elif args.cases == "all":
        cases = [r["case"] for r in sheet]
    else:
        cases = args.cases.split(",")
        unknown = sorted(set(cases) - {r["case"] for r in sheet})
        if unknown:
            raise SystemExit(f"cases not in the coding sheet: {unknown}")

    with open(args.instructions, encoding="utf-8") as fh:
        instructions = fh.read()
    prompt, schema = part1(instructions)
    if labeling:
        with open(os.path.expanduser(args.scheme), encoding="utf-8") as fh:
            scheme_text = fh.read()
        scheme = json.loads(scheme_text)
        problems = check_scheme(scheme)
        if problems:
            raise SystemExit(f"{args.scheme}: " + "; ".join(problems))
        prompt, schema = labeling_prompt(part2(instructions), scheme), labeling_schema(scheme)
    commit, dirty = instructions_version(os.path.abspath(args.instructions))
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=args.timeout,
                                 max_retries=args.max_retries)
    version = anthropic.__version__
    print(f"anthropic {version}, model {args.model}, effort {args.effort}, "
          f"instructions {commit}{' with local changes' if dirty else ''}")

    def run_case(case):
        with open(os.path.join(draw, "packages", f"{case}.md"), encoding="utf-8") as fh:
            package = fh.read()
        package_sha = sha256(package)
        if labeling:
            desc_path = os.path.join(os.path.expanduser(args.descriptions), case, f"run{args.description_run}.json")
            try:
                with open(desc_path, encoding="utf-8") as fh:
                    desc_text = fh.read()
            except FileNotFoundError:
                raise SystemExit(f"{case}: no description at {desc_path}; run the description step first") from None
            desc = json.loads(desc_text)
            if desc.get("step") != "description" or desc.get("case") != case or "output" not in desc:
                raise SystemExit(f"{desc_path}: not a description of {case}")
            # the answer has to name the case as the description does, so a description that names
            # another case would stop the run at its first call
            if desc["output"].get("case") != case:
                raise SystemExit(f"{desc_path}: the description names case {desc['output'].get('case')!r}, "
                                 f"not {case}; fix it or describe the case again")
            # the model reads the package beside its description, so both must be of the same package
            if desc.get("package_sha256") != package_sha:
                raise SystemExit(f"{desc_path}: the description was written from another package than "
                                 f"{draw}/packages/{case}.md; describe the case again")
            # the description, then the package
            message = labeling_message(desc["output"], package)
        else:
            message = package
        os.makedirs(os.path.join(out, case), exist_ok=True)
        for k in range(1, args.runs + 1):
            path = os.path.join(out, case, f"run{k}.json")
            if os.path.exists(path):
                continue
            started = now()
            raw = os.path.join(out, case, f"run{k}.response.json")
            failures = os.path.join(out, case, f"run{k}.failures.jsonl")

            def failed(error, kind=SystemExit, response=False):
                """Logs a failed call in run<k>.failures.jsonl, keeps its raw response, and returns the error to raise."""
                n = len(read_failures(failures)) + 1
                kept = f"run{k}.failed{n}.response.json" if response else None
                if kept:
                    os.replace(raw, os.path.join(out, case, kept))
                with open(failures, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"failure": n, "started": started, "finished": now(), "error": error,
                                         "service": issubclass(kind, ServiceFailure), "response": kept}, ensure_ascii=False) + "\n")
                return kind(f"{case}, run {k}: {error}. No record was written for this run; the failure is logged in "
                            f"{case}/run{k}.failures.jsonl" + (f", and the raw response is in {case}/{kept}" if kept else ""))

            try:
                msg = call(client, args.model, args.effort, args.max_tokens, prompt, schema, message)
            except anthropic.APITimeoutError:
                raise failed(f"the request took more than {args.timeout} s, also after {args.max_retries} retries")
            except anthropic.APIConnectionError as e:
                raise failed(f"no connection to the API ({e})", ServiceFailure)
            except anthropic.APIStatusError as e:
                raise failed(f"the API answered {e.status_code} (request {e.request_id}): {e.message}",
                             KeyFailure if e.status_code in KEY_STATUS
                             else ServiceFailure if e.status_code in SERVICE_STATUS or e.status_code >= 500 else SystemExit)
            with open(raw, "w", encoding="utf-8") as fh:
                fh.write(msg.to_json())
            rec, error = read_response(msg, schema, args.model)
            if error:
                raise failed(error, response=True)
            if labeling and rec["output"]["case"] != case:
                raise failed(f"the answer names case {rec['output']['case']!r}", response=True)
            earlier = read_failures(failures)
            head = {"case": case, "run": k, "step": args.step, "started": started, "finished": now(),
                    "model_requested": args.model, "effort": args.effort, "anthropic_sdk": version,
                    "instructions_commit": commit, "instructions_local_changes": dirty,
                    "instructions_sha256": sha256(instructions), "package_sha256": package_sha,
                    # the failed calls of this run before the one recorded, logged in run<k>.failures.jsonl
                    "failed_calls": sum(not f["service"] for f in earlier),
                    "failed_service_calls": sum(f["service"] for f in earlier)}
            if labeling:
                head.update({"scheme_version": scheme.get("version"), "scheme_sha256": sha256(scheme_text),
                             "description_run": args.description_run, "description_sha256": sha256(desc_text),
                             "description_instructions_sha256": desc.get("instructions_sha256"),
                             "prompt_sha256": sha256(prompt), "problems": residual_problems(rec["output"], scheme)})
            rec = {**head, **rec}
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=1)
            if labeling:
                codes = ", ".join(f"{code_field(scheme, d)} {rec['output'][code_field(scheme, d)]}" for d in scheme["dimensions"])
                print(f"{case} run {k}: {codes}" + "".join(f"; problem: {x}" for x in rec["problems"]))
            else:
                print(f"{case} run {k}: closer {rec['output']['closer']}, empty candidates {rec['output']['empty_candidates']}")

    failed = []
    for case in cases:
        try:
            run_case(case)
        except ServiceFailure:
            raise
        except SystemExit as e:
            if not args.keep_going:
                raise
            # the failure is printed and the next case is run; the failed case has no record
            print(f"FAILED {e}", file=sys.stderr, flush=True)
            failed.append(case)
    if failed:
        raise SystemExit(f"{len(failed)} of {len(cases)} cases failed and have no record: {','.join(failed)}")


if __name__ == "__main__":
    try:
        main()
    except KeyFailure as e:
        print(e, file=sys.stderr)
        sys.exit(KEY_EXIT)
