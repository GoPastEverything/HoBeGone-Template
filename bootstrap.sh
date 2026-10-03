#!/usr/bin/env bash
# Ho Be Gone bootstrap: one deterministic command for first run and every later run.
#
#   bash bootstrap.sh --x-account @handle
#   curl -fsSL https://raw.githubusercontent.com/GoPastEverything/HoBeGone-Template/main/bootstrap.sh | bash -s -- --x-account @handle
#
# 1. Clones this repo into $HOBEGONE_HOME/HoBeGone-Template (default ~/hobegone/HoBeGone-Template), or fast-forwards it.
# 2. Checks Python 3.10+.
# 3. Runs the test suite whenever the checked-out commit hasn't passed it yet (--smoke: self-check only).
# 4. Picks the owner's instance and refuses one that belongs to another X account.
# 5. Runs `python3 -m fis start --x-account @handle` (new owner: fresh neutral instance; returning owner: resume).
# 6. Records the commit/version in the instance (deploy_log.jsonl) and prints machine-readable HOBEGONE_* lines.
# --locate: steps 1-4 only (self-check, no tests); prints where this owner would run and starts nothing.
#
# It never copies, imports or migrates data from anywhere. The only data it ever runs on is the owner's own instance.
# If an earlier install on this computer already holds an instance for this exact X account, it runs that install
# instead of creating an empty duplicate (it still never copies anything between installs).
#
# Exit codes: 0 ok · 2 repo unreachable · 3 Python missing/too old · 4 tests or self-check failed ·
#             5 refused (another owner's instance, or the target folder isn't this repo) · 6 usage
set -euo pipefail

REPO_URL="${HOBEGONE_REPO_URL:-https://github.com/GoPastEverything/HoBeGone-Template}"
BRANCH="${HOBEGONE_BRANCH:-main}"
BASE="${HOBEGONE_HOME:-$HOME/hobegone}"
DEST="$BASE/HoBeGone-Template"
HANDLE=""; SMOKE=0; FORCE_TESTS=0; SCAN_EXISTING=1; NEW_RUN=0; LOCATE=0

usage() { sed -n '2,6p' "$0" 2>/dev/null; echo "options: --x-account @handle [--smoke] [--force-tests] [--no-existing-scan] [--new] [--locate]"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --x-account) HANDLE="${2:-}"; shift 2 ;;
    --x-account=*) HANDLE="${1#*=}"; shift ;;
    --smoke) SMOKE=1; shift ;;
    --force-tests) FORCE_TESTS=1; shift ;;
    --no-existing-scan) SCAN_EXISTING=0; shift ;;
    --new) NEW_RUN=1; shift ;;
    --locate) LOCATE=1; SMOKE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 6 ;;
  esac
done
HANDLE="${HANDLE#@}"
if ! [[ "$HANDLE" =~ ^[A-Za-z0-9_]{1,15}$ ]]; then
  echo "HOBEGONE_ERROR=usage: pass the signed-in X handle, e.g. --x-account @yourhandle" >&2; exit 6
fi
SLUG="$(printf '%s' "$HANDLE" | tr 'A-Z' 'a-z')"

say() { printf '[hobegone] %s\n' "$*" >&2; }
fail() { local code="$1"; shift; printf 'HOBEGONE_ERROR=%s\n' "$*"; exit "$code"; }
norm_url() { local u="${1%/}"; u="${u%.git}"; u="${u#https://}"; u="${u#http://}"; u="${u#git@}"; u="${u/://}"; printf '%s' "${u,,}"; }

# ---- 2. Python 3.10+
PY="$(command -v python3 || true)"
[ -n "$PY" ] || fail 3 "python3 not found; install Python 3.10 or newer"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail 3 "Python 3.10+ needed, found $("$PY" -c 'import sys; print(sys.version.split()[0])')"
command -v git >/dev/null || fail 2 "git not found; the engine source can't be fetched"

mkdir -p "$BASE"
exec 9>"$BASE/.bootstrap.lock"
if command -v flock >/dev/null; then flock -w 600 9 || fail 6 "another bootstrap is still running"; fi

# ---- 1. clone or fast-forward (never anywhere but $DEST)
export GIT_TERMINAL_PROMPT=0
UPDATE="NONE"
if [ -d "$DEST/.git" ]; then
  have="$(git -C "$DEST" remote get-url origin 2>/dev/null || true)"
  # The repo moved (2026-10-03); a clone made from its old address is the same repo: re-point it, don't refuse it.
  if [ "$(norm_url "$have")" = "github.com/theretardedelon/hobegone-template" ] && [ -z "${HOBEGONE_REPO_URL:-}" ]; then
    git -C "$DEST" remote set-url origin "$REPO_URL" && say "repo moved: origin re-pointed to $REPO_URL"; have="$REPO_URL"
  fi
  [ "$(norm_url "$have")" = "$(norm_url "$REPO_URL")" ] \
    || fail 5 "$DEST is a clone of '$have', not $REPO_URL; refusing to use it"
  before="$(git -C "$DEST" rev-parse HEAD)"
  if git -C "$DEST" fetch -q origin "$BRANCH" 2>/dev/null; then
    if git -C "$DEST" merge -q --ff-only "origin/$BRANCH" 2>/dev/null; then
      [ "$before" = "$(git -C "$DEST" rev-parse HEAD)" ] && UPDATE="UP_TO_DATE" || UPDATE="UPDATED"
    else
      UPDATE="NOT_FAST_FORWARD"; say "local copy has changes that can't be fast-forwarded; staying on $before"
    fi
  else
    UPDATE="OFFLINE"; say "couldn't reach $REPO_URL; using the copy already here ($before)"
  fi
elif [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  fail 5 "$DEST exists but is not a clone of $REPO_URL; refusing to overwrite it"
else
  if git clone -q --branch "$BRANCH" "$REPO_URL" "$DEST" 2>/dev/null; then
    UPDATE="CLONED"
  elif command -v gh >/dev/null && gh auth status >/dev/null 2>&1 \
       && gh repo clone "$(norm_url "$REPO_URL" | sed 's#^github.com/##')" "$DEST" -- -q --branch "$BRANCH" >/dev/null 2>&1; then
    UPDATE="CLONED"
  else
    rm -rf "$DEST" 2>/dev/null || true
    fail 2 "engine source not reachable at $REPO_URL"
  fi
fi
COMMIT="$(git -C "$DEST" rev-parse HEAD)"
cd "$DEST"
VERSION="$("$PY" -c 'from fis.versions import HO_BE_GONE_DISPLAY as d; print(d)')"
say "engine $VERSION at $COMMIT ($UPDATE)"

# ---- 3. tests (once per commit) or smoke self-check
mkdir -p "$DEST/.hobegone"
TESTED="$(cat "$DEST/.hobegone/tested_commit" 2>/dev/null || true)"
"$PY" -m fis doctor >/dev/null || fail 4 "engine self-check failed (python3 -m fis doctor) at $COMMIT"
TESTS="SKIPPED_ALREADY_PASSED"
if [ "$SMOKE" = 1 ]; then
  TESTS="SMOKE_ONLY"
elif [ "$FORCE_TESTS" = 1 ] || [ "$TESTED" != "$COMMIT" ]; then
  if "$PY" -m unittest discover -s tests -q >"$DEST/.hobegone/last_test.log" 2>&1; then
    echo "$COMMIT" >"$DEST/.hobegone/tested_commit"; TESTS="PASSED"
  else
    fail 4 "test suite failed at $COMMIT (see $DEST/.hobegone/last_test.log); not starting"
  fi
fi
say "tests: $TESTS"

# ---- 4. pick the engine + instance for this owner
ENGINE="$DEST"; STATUS=""
owner_of() { "$PY" - "$1" <<'PYEOF'
import json, sys
try: print(str(json.load(open(sys.argv[1], encoding="utf-8")).get("X_ACCOUNT") or "").lstrip("@").lower())
except Exception: print("")
PYEOF
}
OWN_META="$DEST/instances/$SLUG/instance.json"
if [ -f "$OWN_META" ]; then
  [ "$(owner_of "$OWN_META")" = "$SLUG" ] || fail 5 "instances/$SLUG belongs to another X account; refusing to reuse it"
  STATUS="RESUMED"
elif [ "$SCAN_EXISTING" = 1 ]; then
  # An earlier install (a folder directly under $HOME or /workspace, or listed in $HOBEGONE_EXISTING_INSTALLS) that
  # already holds an instance created for this exact X account. Read-only scan of instance.json files.
  hits=()
  IFS=':' read -r -a extra <<<"${HOBEGONE_EXISTING_INSTALLS:-}"
  for d in "${extra[@]}" "$HOME"/*/ /workspace/*/; do
    d="${d%/}"; [ -n "$d" ] && [ -f "$d/fis/__main__.py" ] || continue
    [ "$(cd "$d" && pwd -P)" = "$(cd "$DEST" && pwd -P)" ] && continue
    for m in "$d"/instances/*/instance.json; do
      [ -f "$m" ] || continue
      case "$(basename "$(dirname "$m")")" in _*) continue ;; esac
      if [ "$(owner_of "$m")" = "$SLUG" ]; then hits+=("$(cd "$d" && pwd -P)"); break; fi
    done
  done
  if [ "${#hits[@]}" -gt 0 ]; then
    mapfile -t hits < <(printf '%s\n' "${hits[@]}" | sort -u)
    [ "${#hits[@]}" -eq 1 ] || fail 5 "@$SLUG has instances in several installs (${hits[*]}); set HOBEGONE_EXISTING_INSTALLS to the one to use"
    ENGINE="${hits[0]}"; STATUS="EXISTING_INSTALL"; say "using the existing install that already holds @$SLUG: $ENGINE"
  fi
fi
[ -n "$STATUS" ] || STATUS="NEW"

cd "$ENGINE"
INSTANCE="$("$PY" -m fis select-instance --x-account "@$HANDLE" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["INSTANCE"])')"
if [ -f "$INSTANCE/instance.json" ] && [ "$(owner_of "$INSTANCE/instance.json")" != "$SLUG" ]; then
  fail 5 "$INSTANCE belongs to another X account; refusing to reuse it"
fi

if [ "$LOCATE" = 1 ]; then  # report only: which engine/instance this owner would use; nothing is started or written
  echo "HOBEGONE_ENGINE=$ENGINE"; echo "HOBEGONE_INSTANCE=$INSTANCE"; echo "HOBEGONE_COMMIT=$COMMIT"; echo "HOBEGONE_STATUS=$STATUS"
  exit 0
fi

# ---- 5. start (resume by default; --new only on the owner's words)
START_ARGS=(--x-account "@$HANDLE"); [ "$NEW_RUN" = 1 ] && START_ARGS+=(--new)
"$PY" -m fis start "${START_ARGS[@]}" || fail 5 "start refused for @$HANDLE (see message above)"

# ---- 6. record what ran (only in an instance this bootstrap manages)
if [ "$ENGINE" = "$DEST" ]; then
  "$PY" - "$INSTANCE/deploy_log.jsonl" "$COMMIT" "$VERSION" "$UPDATE" "$TESTS" "$STATUS" "$REPO_URL" <<'PYEOF'
import json, sys, datetime
f, commit, version, update, tests, status, repo = sys.argv[1:]
row = {"AT": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "COMMIT": commit, "VERSION": version,
       "REPO": repo, "UPDATE": update, "TESTS": tests, "STATUS": status}
open(f, "a", encoding="utf-8").write(json.dumps(row) + "\n")
PYEOF
fi

echo "HOBEGONE_ENGINE=$ENGINE"
echo "HOBEGONE_INSTANCE=$INSTANCE"
echo "HOBEGONE_COMMIT=$COMMIT"
echo "HOBEGONE_VERSION=$VERSION"
echo "HOBEGONE_UPDATE=$UPDATE"
echo "HOBEGONE_TESTS=$TESTS"
echo "HOBEGONE_STATUS=$STATUS"
