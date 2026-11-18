#!/usr/bin/env bash
# Runs the automatic annotator of the RQ4 coding on one block of the sample, the description step and
# the labeling step, and then the agreement report of that block.
#
#   DRAW=<sample folder> SHEET=<coding sheet> OUTROOT=<dir> bash analysis/rq4/annotator/run_block.sh 1
#   DRAW=... SHEET=... OUTROOT=... bash analysis/rq4/annotator/run_block.sh 1 --check   # no call to the API
#
# Before any call it checks that the instructions are the frozen v1, that the scheme is the frozen one,
# that every case of the block has its consensus labels in the coding sheet, and that the block has no
# agreement report yet. It then asks for the key of the API with read -rs (not shown, not saved) and
# goes on in the background. Everything is written to a log under $OUTROOT/logs, and the last line of
# the status file says DONE or FAILED. run_annotator.py skips a run already recorded, so a step that
# fails is tried again, up to ATTEMPTS times; it counts as done when every case of the block has its
# run1.json. Outputs: $OUTROOT/block<n>-description, $OUTROOT/block<n>-labeling and $OUTROOT/agreement/block<n>.
set -euo pipefail

SELF="$(readlink -f "$0")"
BLOCK="${1:?usage: run_block.sh <block number> [--check]}"
MODE="${2:-}"
REPO="$(cd "$(dirname "$SELF")/../../.." && pwd)"
DRAW="${DRAW:?set DRAW, the folder of the sample (coding_sheet.csv and packages/)}"
SHEET="${SHEET:?set SHEET, the coding sheet with the consensus of the authors}"
OUTROOT="${OUTROOT:?set OUTROOT, the folder of the outputs}"
export DRAW SHEET OUTROOT
SCHEME="$REPO/analysis/rq4/scheme/coding-scheme.json"
INSTR="$REPO/docs/annotator-instructions-v1.md"
INSTR_SHA="51ea9e4991a343c83960909f29980edb999db25022d41497a1a02bf65fd2c6f7"
SCHEME_SHA="38f1ae6b1bcd8774c7545149c0f7b3868b3748bf6e778d9e3bb304f7030863a6"
MODEL="claude-fable-5-1"
EFFORT="high"
ATTEMPTS="${ATTEMPTS:-3}"
PAUSE="${PAUSE:-120}"
DESC="$OUTROOT/block${BLOCK}-description"
LAB="$OUTROOT/block${BLOCK}-labeling"
KAPPA="$OUTROOT/agreement/block${BLOCK}"
LOGDIR="$OUTROOT/logs"
STATUS="$LOGDIR/block${BLOCK}.status"

say() { echo "[$(date -u +%FT%TZ)] $*"; }
WRITE_STATUS=0  # the status file is written only by a real run, not by --check
fail() { say "STOP: $*"; [ "$WRITE_STATUS" = 1 ] && echo "FAILED $(date -u +%FT%TZ): $*" >> "$STATUS"; exit 1; }

# shellcheck disable=SC1091
set +u  # the activation scripts of conda read unset variables
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sbcr-analysis
set -u
cd "$REPO"

# the cases of the block, in the order of the coding sheet of the draw
CASES="$(python - "$DRAW/coding_sheet.csv" "$BLOCK" <<'EOF'
import csv, sys
rows = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")) if r["block"] == sys.argv[2] and r["role"] == "sample"]
print(",".join(r["case"] for r in rows))
EOF
)"
N="$(echo "$CASES" | tr ',' '\n' | grep -c . || true)"

checks() {
    [ "$N" -gt 0 ] || fail "block $BLOCK has no sample case in $DRAW/coding_sheet.csv"
    [ "$(sha256sum "$INSTR" | cut -d' ' -f1)" = "$INSTR_SHA" ] || fail "$INSTR is not the frozen instructions v1 $INSTR_SHA"
    [ -z "$(git status --porcelain -- "$INSTR" 2>/dev/null)" ] || fail "$INSTR has local changes"
    [ "$(sha256sum "$SCHEME" | cut -d' ' -f1)" = "$SCHEME_SHA" ] || fail "$SCHEME is not the frozen scheme $SCHEME_SHA"
    [ ! -e "$KAPPA/kappa_report.md" ] || fail "$KAPPA already holds a kappa report"
    # the annotator runs only after the authors' labels of the block are recorded
    python - "$SHEET" "$BLOCK" "$N" <<'EOF' || fail "the coding sheet lacks consensus labels of block $BLOCK"
import csv, sys
rows = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")) if r["block"] == sys.argv[2]]
dims = sorted(k[len("dominant_code_"):] for k in rows[0] if k.startswith("dominant_code_")) if rows else []
missing = [r["case"] for r in rows for d in dims
           if not r[f"dominant_code_{d}"] and r.get(f"no_consensus_{d}", "").lower() not in ("true", "1", "yes")]
if len(rows) != int(sys.argv[3]) or not dims or missing:
    print(f"rows {len(rows)}, dimensions {dims}, without a label: {sorted(set(missing))}")
    sys.exit(1)
EOF
    say "checks passed: block $BLOCK, $N cases, instructions v1 $INSTR_SHA, scheme $SCHEME_SHA"
}

complete() {  # every case of the block has run1.json in the folder $1
    local n; n="$(echo "$CASES" | tr ',' '\n' | while read -r c; do [ -f "$1/$c/run1.json" ] && echo "$c"; done | grep -c . || true)"
    say "$1: $n of $N cases recorded"
    [ "$n" -eq "$N" ]
}

step() {  # step <name> <folder> <arguments of run_annotator.py>
    local name="$1" out="$2"; shift 2
    for attempt in $(seq 1 "$ATTEMPTS"); do
        say "$name, attempt $attempt of $ATTEMPTS"
        python -u analysis/rq4/annotator/run_annotator.py "$@" --out "$out" || say "$name: run_annotator.py stopped with an error"
        complete "$out" && return 0
        if [ "$attempt" -lt "$ATTEMPTS" ]; then say "waiting $PAUSE s before the next attempt"; sleep "$PAUSE"; fi
    done
    fail "$name did not record every case after $ATTEMPTS attempts; see the messages above"
}

worker() {
    [ -n "${ANTHROPIC_API_KEY:-}" ] || fail "ANTHROPIC_API_KEY is not set"
    say "block $BLOCK: start"
    checks
    step "description" "$DESC" --instructions "$INSTR" --draw "$DRAW" --cases "$CASES" --model "$MODEL" --effort "$EFFORT"
    step "labeling" "$LAB" --instructions "$INSTR" --step labeling --draw "$DRAW" --scheme "$SCHEME" --descriptions "$DESC" \
        --cases "$CASES" --model "$MODEL" --effort "$EFFORT"
    unset ANTHROPIC_API_KEY
    say "kappa report"
    python -u analysis/rq4/agreement/kappa_report.py --draw "$DRAW" --scheme "$SCHEME" --sheet "$SHEET" \
        --annotator "$LAB" --blocks "$BLOCK" --out "$KAPPA" || fail "kappa_report.py stopped with an error"
    echo "DONE $(date -u +%FT%TZ): $KAPPA/kappa_report.md" >> "$STATUS"
    say "block $BLOCK: done. Report in $KAPPA/kappa_report.md"
}

mkdir -p "$LOGDIR"
case "$MODE" in
    --check)
        checks ;;
    --worker)
        WRITE_STATUS=1
        worker ;;
    "")
        checks
        WRITE_STATUS=1
        if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
            read -rsp "Key of the API (not shown): " ANTHROPIC_API_KEY; echo
        fi
        [ -n "$ANTHROPIC_API_KEY" ] || fail "no key given"
        export ANTHROPIC_API_KEY
        LOG="$LOGDIR/block${BLOCK}-$(date -u +%Y%m%dT%H%M%SZ).log"
        echo "STARTED $(date -u +%FT%TZ): log $LOG" >> "$STATUS"
        setsid nohup bash "$SELF" "$BLOCK" --worker > "$LOG" 2>&1 < /dev/null &
        echo "Running in the background (process $!). The terminal can be closed."
        echo "Log:    $LOG"
        echo "Status: $STATUS"
        echo "To follow it: tail -f $LOG" ;;
    *)
        echo "usage: run_block.sh <block number> [--check]"; exit 2 ;;
esac
