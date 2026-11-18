#!/usr/bin/env bash
# Runs the automatic annotator of the RQ4 coding on every packaged conflict of the three bands, the
# description step and then the labeling step, in PROCS processes side by side.
#
#   DRAW=<scale folder> OUTROOT=<dir> bash analysis/rq4/annotator/run_scale.sh            # asks for the key, runs in the background
#   DRAW=<scale folder> OUTROOT=<dir> bash analysis/rq4/annotator/run_scale.sh --check    # only the checks
#   DRAW=<scale folder> OUTROOT=<dir> bash analysis/rq4/annotator/run_scale.sh --status   # cases recorded, failed calls, cost so far
#
# Before any call it checks that the instructions are the frozen v1, that the scheme is the frozen one,
# and that the coding sheet and the packages are those build_scale.py wrote (SHEET_SHA, PACKAGES_SHA,
# CASES). It then asks for the key of the API with read -rs (not shown, not saved) and goes on in the
# background. Everything is written to logs under $OUTROOT/logs, and the last line of the status file
# says DONE, INCOMPLETE or FAILED.
#
# The cases are split into PROCS shards, case i of the coding sheet going to shard i mod PROCS, and
# each shard runs both steps in a process of its own, into the same two folders. run_annotator.py runs
# with --keep-going: a case that fails is left without a record and the shard goes on, and a step is
# tried again, up to ATTEMPTS times with PAUSE seconds between them, while cases of the shard lack a
# record. When the API refuses the key or its permissions (exit status 3 of run_annotator.py), no
# shard tries again. The labeling step of a shard runs on the cases that have a description. The run
# can be stopped and started again, and goes on from where it stopped. ANTHROPIC_BASE_URL sends the
# calls elsewhere, as to stand_in_api.py for a test with no model.
set -euo pipefail

SELF="$(readlink -f "$0")"
MODE="${1:-}"
export REPO="$(cd "$(dirname "$SELF")/../../.." && pwd)"
export DRAW="${DRAW:?set DRAW, the folder of the coding at scale (coding_sheet.csv and packages/)}"
SCHEME="$REPO/analysis/rq4/scheme/coding-scheme.json"
export INSTR="$REPO/docs/annotator-instructions-v1.md"
INSTR_SHA="51ea9e4991a343c83960909f29980edb999db25022d41497a1a02bf65fd2c6f7"
SCHEME_SHA="38f1ae6b1bcd8774c7545149c0f7b3868b3748bf6e778d9e3bb304f7030863a6"
# the coding sheet and packages build_scale.py wrote
CASES=1979
SHEET_SHA="334de2355b07a990e51fb6ab3f9fefc299f5240a4642f419e0adfa888d9680b1"
PACKAGES_SHA="c65dfe9d956c268931732e4a43b303026560b9430ff48c45defbebd67bfce9c8"
MODEL="claude-fable-5-1"
EFFORT="high"
export PROCS="${PROCS:-4}"
export ATTEMPTS="${ATTEMPTS:-3}"
export PAUSE="${PAUSE:-300}"
export OUTROOT="${OUTROOT:?set OUTROOT, the folder of the outputs}"
DESC="$OUTROOT/scale-description"
LAB="$OUTROOT/scale-labeling"
LOGDIR="$OUTROOT/logs"
STATUS="$LOGDIR/scale.status"
# written by the first shard that finds the key refused, so that the other shards stop too
KEYFAIL="$LOGDIR/scale.key-refused"
LOCK="$LOGDIR/scale.lock"

say() { echo "[$(date -u +%FT%TZ)] $*"; }
WRITE_STATUS=0  # the status file is written only by a real run, not by --check or --status
fail() { say "STOP: $*"; [ "$WRITE_STATUS" = 1 ] && echo "FAILED $(date -u +%FT%TZ): $*" >> "$STATUS"; exit 1; }

# shellcheck disable=SC1091
set +u  # the activation scripts of conda read unset variables
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sbcr-analysis
set -u
cd "$REPO"

# the cases of shard $1 (0 to PROCS-1), or every case with "all", in the order of the coding sheet
cases_of() {
    python - "$DRAW/coding_sheet.csv" "$1" "$PROCS" <<'EOF'
import csv, sys
cases = [r["case"] for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))]
print(",".join(cases if sys.argv[2] == "all" else cases[int(sys.argv[2])::int(sys.argv[3])]))
EOF
}

# the cases of the list $2 that have run1.json in the folder $1
recorded() {
    echo "$2" | tr ',' '\n' | while read -r c; do if [ -n "$c" ] && [ -f "$1/$c/run1.json" ]; then echo "$c"; fi; done \
        | paste -sd, -
}

# the cases of the list $2 that have no run1.json in the folder $1
missing() {
    echo "$2" | tr ',' '\n' | while read -r c; do if [ -n "$c" ] && [ ! -f "$1/$c/run1.json" ]; then echo "$c"; fi; done \
        | paste -sd, -
}

count() { echo "$1" | tr ',' '\n' | grep -c . || true; }

checks() {
    [ "$(sha256sum "$INSTR" | cut -d' ' -f1)" = "$INSTR_SHA" ] || fail "$INSTR is not the frozen instructions v1 $INSTR_SHA"
    [ -z "$(git status --porcelain -- "$INSTR" 2>/dev/null)" ] || fail "$INSTR has local changes"
    [ "$(sha256sum "$SCHEME" | cut -d' ' -f1)" = "$SCHEME_SHA" ] || fail "$SCHEME is not the frozen scheme $SCHEME_SHA"
    [ "$(sha256sum "$DRAW/coding_sheet.csv" | cut -d' ' -f1)" = "$SHEET_SHA" ] \
        || fail "$DRAW/coding_sheet.csv is not the coding sheet of the coding at scale"
    # the same list as packages_sha256 of build_scale.py: "<sha256>  <case>.md", one line per package
    local got; got="$(cd "$DRAW/packages" && find . -maxdepth 1 -name '*.md' -printf '%f\n' | LC_ALL=C sort \
        | xargs sha256sum | sha256sum | cut -d' ' -f1)"
    [ "$got" = "$PACKAGES_SHA" ] || fail "the packages in $DRAW/packages are not those of the coding at scale"
    local n; n="$(count "$(cases_of all)")"
    [ "$n" -eq "$CASES" ] || fail "the coding sheet has $n cases, not $CASES"
    local free; free="$(df -Pk "$OUTROOT" 2>/dev/null | awk 'NR==2 {print int($4/1048576)}')"
    [ "${free:-0}" -ge 2 ] || fail "less than 2 GB free for $OUTROOT"
    python -c "import anthropic" || fail "the environment sbcr-analysis has no anthropic package"
    say "checks passed: $CASES cases in $PROCS processes, instructions v1 $INSTR_SHA," \
        "scheme $SCHEME_SHA, coding sheet and packages of the coding at scale," \
        "API address ${ANTHROPIC_BASE_URL:-default}, outputs in $OUTROOT"
}

status() {  # cases recorded per step, failed calls, and the cost at list prices (USD per million tokens)
    python - "$DESC" "$LAB" "$CASES" <<'EOF'
import glob, json, os, sys
def usd(f):
    u = json.load(open(f, encoding="utf-8")).get("usage") or {}
    return (10 * u.get("input_tokens", 0) + 50 * u.get("output_tokens", 0)
            + 0.25 * (u.get("cache_read_input_tokens") or 0) + 12.5 * (u.get("cache_creation_input_tokens") or 0)) / 1e6
for name, folder in (("description", sys.argv[1]), ("labeling", sys.argv[2])):
    recorded = glob.glob(os.path.join(folder, "*", "run1.json"))
    # the responses run_annotator.py did not accept, kept so that the cost of every call is counted
    kept = glob.glob(os.path.join(folder, "*", "run1.failed*.response.json"))
    failures = [json.loads(line) for f in glob.glob(os.path.join(folder, "*", "run1.failures.jsonl"))
                for line in open(f, encoding="utf-8") if line.strip()]
    of_case = sum(not x["service"] for x in failures)
    cases = len({os.path.dirname(f) for f in glob.glob(os.path.join(folder, "*", "run1.failures.jsonl"))})
    print(f"{name}: {len(recorded)} of {sys.argv[3]} cases recorded, USD {sum(map(usd, recorded)):.2f} at list prices; "
          f"{of_case} failed calls of a case and {len(failures) - of_case} of the service, in {cases} cases, "
          f"USD {sum(map(usd, kept)):.2f} for the responses not accepted")
EOF
}

step() {  # step <shard> <name> <folder> <cases> <arguments of run_annotator.py>
    local shard="$1" name="$2" out="$3" cases="$4"; shift 4
    local left attempt rc
    for attempt in $(seq 1 "$ATTEMPTS"); do
        left="$(missing "$out" "$cases")"
        if [ -z "$left" ]; then say "shard $shard, $name: all $(count "$cases") cases recorded"; return 0; fi
        if [ "$attempt" -gt 1 ]; then say "shard $shard, $name: waiting $PAUSE s before the next attempt"; sleep "$PAUSE"; fi
        if [ -f "$KEYFAIL" ]; then say "shard $shard, $name: the API refused the key in another shard; stopping"; return 1; fi
        say "shard $shard, $name, attempt $attempt of $ATTEMPTS: $(count "$left") cases to run"
        rc=0
        python -u analysis/rq4/annotator/run_annotator.py "$@" --cases "$left" --out "$out" --keep-going \
            --model "$MODEL" --effort "$EFFORT" --max-retries 4 || rc=$?
        if [ "$rc" -eq 3 ]; then
            # 401 or 403: the same key fails again, so no shard tries again
            touch "$KEYFAIL"
            say "shard $shard, $name: the API refused the key or its permissions; stopping every shard"
            return 1
        fi
        if [ "$rc" -ne 0 ]; then say "shard $shard, $name: run_annotator.py stopped with an error"; fi
    done
    left="$(missing "$out" "$cases")"
    if [ -z "$left" ]; then say "shard $shard, $name: all $(count "$cases") cases recorded"; return 0; fi
    say "shard $shard, $name: $(count "$left") cases without a record after $ATTEMPTS attempts, the first ones" \
        "$(echo "$left" | cut -d, -f1-20)"
    return 1
}

shard() {  # both steps on one shard; the labeling step runs on the cases that have a description
    local k="$1" cases described rc=0
    cases="$(cases_of "$k")"
    say "shard $k: $(count "$cases") cases"
    step "$k" description "$DESC" "$cases" --instructions "$INSTR" --draw "$DRAW" || rc=1
    described="$(recorded "$DESC" "$cases")"
    if [ -n "$described" ] && [ ! -f "$KEYFAIL" ]; then
        step "$k" labeling "$LAB" "$described" --instructions "$INSTR" --step labeling --draw "$DRAW" --scheme "$SCHEME" \
            --descriptions "$DESC" || rc=1
    fi
    say "shard $k: done"
    return "$rc"
}

worker() {
    exec 9>"$LOCK"
    flock -n 9 || fail "another run of run_scale.sh holds $LOCK"
    [ -n "${ANTHROPIC_API_KEY:-}" ] || fail "ANTHROPIC_API_KEY is not set"
    say "labeling at scale: start"
    checks
    rm -f "$KEYFAIL"
    local stamp; stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    local pids=() k
    for k in $(seq 0 $((PROCS - 1))); do
        shard "$k" > "$LOGDIR/scale-$stamp-shard$k.log" 2>&1 &
        pids+=("$!")
        say "shard $k: process $!, log $LOGDIR/scale-$stamp-shard$k.log"
    done
    local rc=0 p
    for p in "${pids[@]}"; do wait "$p" || rc=1; done
    unset ANTHROPIC_API_KEY
    status
    local all d l; all="$(cases_of all)"
    d="$(count "$(recorded "$DESC" "$all")")"; l="$(count "$(recorded "$LAB" "$all")")"
    if [ -f "$KEYFAIL" ]; then
        echo "FAILED $(date -u +%FT%TZ): the API refused the key or its permissions (401 or 403);" \
            "$d described, $l labeled of $CASES; run again with another key" >> "$STATUS"
        say "labeling at scale: stopped, the API refused the key; see the shard logs, and run again with another key"
    elif [ "$rc" -eq 0 ] && [ "$d" -eq "$CASES" ] && [ "$l" -eq "$CASES" ]; then
        echo "DONE $(date -u +%FT%TZ): $CASES cases described and labeled in $LAB" >> "$STATUS"
        say "labeling at scale: done"
    else
        echo "INCOMPLETE $(date -u +%FT%TZ): $d described, $l labeled of $CASES; run again to go on" >> "$STATUS"
        say "labeling at scale: incomplete, $d described and $l labeled of $CASES; see the shard logs, and run again to go on"
    fi
}

mkdir -p "$LOGDIR"
case "$MODE" in
    --check)
        checks ;;
    --status)
        status
        if [ -f "$STATUS" ]; then tail -1 "$STATUS"; fi ;;
    --worker)
        WRITE_STATUS=1
        worker ;;
    "")
        checks
        ( flock -n 9 ) 9>"$LOCK" || fail "another run of run_scale.sh holds $LOCK"
        WRITE_STATUS=1
        if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
            read -rsp "Key of the API (not shown): " ANTHROPIC_API_KEY; echo
        fi
        [ -n "$ANTHROPIC_API_KEY" ] || fail "no key given"
        export ANTHROPIC_API_KEY
        LOG="$LOGDIR/scale-$(date -u +%Y%m%dT%H%M%SZ).log"
        echo "STARTED $(date -u +%FT%TZ): log $LOG" >> "$STATUS"
        setsid nohup bash "$SELF" --worker > "$LOG" 2>&1 < /dev/null &
        echo "Running in the background (process group $!). The terminal can be closed."
        echo "Log:    $LOG (one more log per shard, named in it)"
        echo "Status: $STATUS"
        echo "To follow it: tail -f $LOG"
        echo "Progress and cost: bash $SELF --status"
        echo "To stop it: kill -- -$!" ;;
    *)
        echo "usage: run_scale.sh [--check | --status]"; exit 2 ;;
esac
