#!/usr/bin/env python3
"""BBP self-check: every MUST invariant, computed. Exit 0 = pass, 1 = fail.

This is the machine's health test. It answers, without trusting any session's memory:
does the firm's plumbing still satisfy the properties it claims? Designed to be run by
GitHub Actions (a scheduler and verifier independent of Claude's scheduler), so the
principal verifies BBP by looking at a green or red check on GitHub — not by believing
a report written by the thing being reported on.

Every check here is BINARY. Judgment calls do not belong in this file.
"""
import json, sys, datetime, pathlib, subprocess, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS, PASSES, WARNS = [], [], []

def check(name, ok, detail=""):
    (PASSES if ok else FAILS).append(f"{name}: {detail}" if detail else name)

def warn(name, detail):
    WARNS.append(f"{name}: {detail}")

def jsonl(p):
    rows, bad = [], []
    for i, l in enumerate(p.read_text().splitlines(), 1) if p.exists() else []:
        if l.strip():
            try: rows.append(json.loads(l))
            except json.JSONDecodeError: bad.append(i)
    return rows, bad

# --- I1 ledger integrity: every journal line parses -------------------------------
j, bad = jsonl(ROOT / "JOURNAL.jsonl")
check("I1 journal parses", not bad, f"{len(bad)} malformed line(s) {bad}" if bad else f"{len(j)} events")

# --- I2 journal is append-only in git history --------------------------------------
try:
    out = subprocess.run(["git", "log", "--follow", "--numstat", "--format=%H", "--", "JOURNAL.jsonl"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    deletions = [int(m.group(2)) for m in re.finditer(r"^(\d+)\t(\d+)\tJOURNAL", out, re.M)]
    check("I2 journal append-only", all(d == 0 for d in deletions),
          f"{sum(1 for d in deletions if d)} commit(s) deleted journal lines" if any(deletions) else
          f"{len(deletions)} commits, zero deletions")
except Exception as e:
    warn("I2 journal append-only", f"could not verify: {e}")

# --- I3 every forecast is machine-decidable ----------------------------------------
f, fbad = jsonl(ROOT / "FORECASTS.jsonl")
KEYS = {"source", "subject_id", "metric", "comparator", "threshold", "on_missing_data"}
fc = [r for r in f if r.get("type") == "forecast"]
badspec = [r["id"] for r in fc if not KEYS <= set(r.get("criterion_spec") or {})]
check("I3 forecasts machine-decidable", not badspec and not fbad,
      f"{len(badspec)} incomplete spec(s) {badspec[:5]}" if badspec else f"{len(fc)} forecasts, all specs complete")

# --- I4 no forecast graded by its own author ---------------------------------------
byid = {r["id"]: r for r in fc}
selfgraded = [g["forecast_id"] for g in f if g.get("type") == "grade"
              and g.get("forecast_id") in byid and byid[g["forecast_id"]]["author"] == g["grader"]]
check("I4 no self-grading", not selfgraded, f"{selfgraded[:5]}" if selfgraded else "0 violations")

# --- I5 no grade of non-occurrence before its deadline ------------------------------
early = []
for g in f:
    if g.get("type") == "grade" and g.get("outcome") == 0 and g.get("forecast_id") in byid:
        if g["ts"] < byid[g["forecast_id"]]["deadline"]:
            early.append(g["forecast_id"])
check("I5 no premature outcome=0", not early, f"{early[:5]}" if early else "0 violations")

# --- I6 one forecast per subject per class ------------------------------------------
seen, dupes = set(), []
for r in fc:
    k = (r.get("class"), str((r.get("criterion_spec") or {}).get("subject_id", "")).lower())
    dupes.append(k) if k in seen else seen.add(k)
check("I6 no n-padding duplicates", not dupes, f"{len(dupes)} duplicate(s)" if dupes else f"{len(seen)} unique subjects")

# --- I7 wallet allowance is zero until an H1 pass event exists ----------------------
caps = json.loads((ROOT / "config" / "caps.json").read_text())
h1pass = any(e["type"] == "h1_result" and "PASS" in e["body"].upper() for e in j)
check("I7 capital gate", caps["total_capital_allowance_usd"] == 0 or h1pass,
      f"allowance ${caps['total_capital_allowance_usd']} without an h1_result PASS event"
      if not h1pass and caps["total_capital_allowance_usd"] else
      f"allowance ${caps['total_capital_allowance_usd']}, h1_pass={h1pass}")

# --- I8 no non-computable wording in operational claims -----------------------------
lint = subprocess.run([sys.executable, str(ROOT / "tools" / "lint.py")], capture_output=True, text=True)
check("I8 lint clean", lint.returncode == 0, lint.stdout.strip().splitlines()[0] if lint.returncode else "")

# --- I9 sampling heartbeat: a cohort committed within the last 12h -------------------
now = datetime.datetime.now(datetime.timezone.utc)
cohorts = sorted((ROOT / "data" / "cohorts").glob("cohort_*.json"))
if cohorts:
    last = datetime.datetime.strptime(cohorts[-1].name[7:22], "%Y%m%dT%H%M%S").replace(tzinfo=datetime.timezone.utc)
    age = (now - last).total_seconds() / 3600
    survey_over = now >= datetime.datetime(2026, 9, 7, tzinfo=datetime.timezone.utc)
    check("I9 sampler heartbeat", age <= 12 or survey_over,
          f"newest cohort {age:.1f}h old (>12h: the sampler is silent and nothing else would have told you)")
else:
    check("I9 sampler heartbeat", False, "no cohorts at all")

# --- I10 the board is not stale relative to the journal ------------------------------
st = ROOT / "STATUS.md"
if st.exists():
    # Was a string comparison of the board's DATE against the newest journal timestamp. Both
    # sides were date-only, so it could only ever fire across a midnight boundary and read any
    # same-day staleness as fresh (found 2026-08-21). Now: regenerate and diff. No clock.
    _r10 = subprocess.run([sys.executable, str(ROOT / "tools" / "status.py"), "--check"],
                          cwd=ROOT, capture_output=True, text=True)
    check("I10 board matches journal", _r10.returncode == 0,
          (_r10.stdout + _r10.stderr).strip().splitlines()[-1] if _r10.returncode else
          "regenerating status.py produces the committed board")
else:
    check("I10 board matches journal", False, "STATUS.md missing")

# --- I11 every open principal_pending item is visible on the board -------------------
resolved = {e["body"].split("|", 1)[0].strip() for e in j if e["type"] == "principal_resolved"}
openp = [e["body"].split("|", 1)[0].strip() for e in j
         if e["type"] == "principal_pending" and e["body"].split("|", 1)[0].strip() not in resolved]
board = st.read_text() if st.exists() else ""
missing = [k for k in openp if k not in board]
check("I11 pending items surfaced", not missing, f"{missing}" if missing else f"{len(openp)} open, all on board")

# --- I12 compiled docs match machine state ------------------------------------------
r = subprocess.run([sys.executable, str(ROOT / "tools" / "render.py"), "--check"], capture_output=True, text=True)
check("I12 docs match config", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.returncode else "")

# --- I13 survey weights sum to 1 -----------------------------------------------------
sv = json.loads((ROOT / "config" / "survey.json").read_text())
wsum = sum(sv["criteria_weights"].values())
check("I13 weights sum to 1", abs(wsum - 1.0) < 1e-9, f"weights sum to {wsum}")

# --- I14 tools read config, not duplicated constants ---------------------------------
smp = (ROOT / "tools" / "sample.py").read_text()
_ok14 = "survey.json" in smp and "datetime.datetime(2026" not in smp
check("I14 no duplicated survey constants", _ok14,
      "sample.py hardcodes a date instead of reading config/survey.json" if not _ok14
      else "sample.py reads config/survey.json")

# --- I15 boot path is executable, not a reading list ---------------------------------
rm = (ROOT / "README.md").read_text()
lines = [l for l in rm.splitlines() if l.strip() and not l.strip().startswith("<!--")]
check("I15 README is a boot sector", "python3 tools/boot.py" in rm and len(lines) <= 20,
      f"{len(lines)} content lines (max 20) / boot command present: {'python3 tools/boot.py' in rm}")

# --- I16 wake prompts are invocations, not procedures ---------------------------------
wp_path = ROOT / "data" / "wake_prompts.json"
if wp_path.exists():
    wakes = json.loads(wp_path.read_text()).get("wakes", {})
    # Every wake must EXECUTE the machine before anything else. Judgment may follow the
    # invocation, but the mechanical part is run by the runner, never narrated to a model
    # (principal, 2026-08-21: an instruction a model must follow is where hallucination lives).
    prose = [v["name"] for v in wakes.values() if "tools/boot.py" not in v.get("prompt", "")]
    check("I16 wakes invoke boot", not prose,
          f"{len(prose)} wake(s) never invoke tools/boot.py: {[p[:30] for p in prose]}")
else:
    warn("I16 wakes are invocations", "no wake mirror to check")

# --- I17 no orphan receipts -----------------------------------------------------------
# A receipt on disk that git does not track is evidence nobody outside this container can
# see. The run may have happened; it is unevidenced, which for a ledger is the same thing.
rdir = ROOT / "data" / "runs"
orphans = []
if rdir.exists():
    for f in sorted(rdir.glob("run_*.json")):
        rel = str(f.relative_to(ROOT))
        if subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT,
                          capture_output=True).returncode != 0:
            orphans.append(rel)
check("I17 no untracked receipts", not orphans,
      f"{len(orphans)} receipt(s) exist on disk but are not committed: {orphans[:3]}")

# --- I18 receipts measure their commit steps ------------------------------------------
# Until 2026-08-21 the runner hardcoded exit 0 for every commit step and wrote the literal
# tail "(commit may be empty)". git commit exits 1 on nothing-to-commit and on real failures
# alike, so a receipt could report success for a commit that never happened. A receipt
# containing a constant is not a receipt; this is the regression guard.
_bt = (ROOT / "tools" / "boot.py").read_text()
_i18 = "(commit may be empty)" not in _bt and "raw_exit" in _bt and "head_after" in _bt
check("I18 commit steps are measured", _i18,
      "boot.py hardcodes a commit exit code instead of recording git's" if not _i18
      else "boot.py records raw_exit + head_before/head_after per commit step")

# --- I19 no known defect class reintroduced -------------------------------------------
# tools/audit.py holds one detector per defect class that has actually reached main. The
# principal observed 2026-08-21 that every "check this" surfaced a new defect; the detectors
# exist so the SECOND instance of a class is caught here rather than by their attention.
_r19 = subprocess.run([sys.executable, str(ROOT / "tools" / "audit.py")], cwd=ROOT,
                      capture_output=True, text=True)
check("I19 no known defect class present", _r19.returncode == 0,
      (_r19.stdout.strip().splitlines() or ["?"])[0])

# --- I20 tier-1 refusals still hold ---------------------------------------------------
# Tier-2 (CI blocks the commit) was confirmed by an outside machine on 2026-08-21. Tier-1 is
# the TOOL refusing the write, and its only prior evidence was a prose instruction in the G0
# wake telling a model to try five things - which proves nothing, because a model can report
# "all refused" without attempting anything. tools/tier1drill.py attempts them against a
# throwaway copy of the repo, so a wrongly-accepted write lands in /tmp, never in the ledger.
_r20 = subprocess.run([sys.executable, str(ROOT / "tools" / "tier1drill.py")], cwd=ROOT,
                      capture_output=True, text=True)
check("I20 tier-1 refusals hold", _r20.returncode == 0,
      (_r20.stdout + _r20.stderr).strip().splitlines()[-1])

# --- report --------------------------------------------------------------------------
print(f"BBP SELF-CHECK  {now:%Y-%m-%d %H:%M UTC}")
for p in PASSES: print(f"  PASS  {p}")
for w in WARNS:  print(f"  WARN  {w}")
for x in FAILS:  print(f"  FAIL  {x}")
print(f"\n{len(PASSES)} passed, {len(WARNS)} warnings, {len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
