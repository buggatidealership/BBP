#!/usr/bin/env python3
"""BBP firm tooling: journal, forecast pre-registration write path, grading, promotion.

Enforcement lives here, not in prose. A forecast that does not clear validation
does not exist. A grade by the forecast's author does not exist. A promotion
without a receipt or from the claim's own source does not exist.
Every command requires an explicit --session identity: sources are named, never implied.
"""
import argparse, json, math, random, sys, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
JOURNAL = ROOT / "JOURNAL.jsonl"
FORECASTS = ROOT / "FORECASTS.jsonl"
STATUSES = {"act", "fact", "claim"}


def die(msg):
    print(f"REJECTED: {msg}", file=sys.stderr)
    sys.exit(1)


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def append(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def cmd_journal(a):
    if a.status not in STATUSES:
        die(f"status must be one of {sorted(STATUSES)}")
    if len(a.body.strip()) < 10:
        die("journal body under 10 chars — write what happened")
    ev = {"ts": utcnow().strftime("%Y-%m-%d"), "type": a.type, "body": a.body.strip(),
          "source": a.session, "status": a.status}
    if a.ref:
        ev["ref"] = a.ref
    append(JOURNAL, ev)
    print(f"journaled: {a.type} ({a.status})")


COMPARATORS = {"<", "<=", ">", ">=", "=="}
MISSING_POLICIES = {"resolve_0", "resolve_1", "void"}
SPEC_KEYS = {"source", "subject_id", "metric", "comparator", "threshold", "on_missing_data"}


def cmd_register(a):
    try:
        p = float(a.probability)
    except ValueError:
        die("probability is not a number")
    if not 0.01 <= p <= 0.99:
        die("probability must be in [0.01, 0.99] — certainty is not a forecast")
    try:
        spec = json.loads(a.criterion_spec)
    except json.JSONDecodeError:
        die("criterion-spec is not valid JSON — prose criteria are vague by definition; "
            "a criterion is a machine-decidable spec or it is not a criterion")
    if not isinstance(spec, dict):
        die("criterion-spec must be a JSON object")
    missing = SPEC_KEYS - set(spec)
    if missing:
        die(f"criterion-spec missing keys {sorted(missing)} — every field is required; "
            "on_missing_data especially: discretion at grade time is forbidden, so the "
            "missing-data outcome is declared at registration")
    if spec["comparator"] not in COMPARATORS:
        die(f"comparator must be one of {sorted(COMPARATORS)}")
    try:
        float(spec["threshold"])
    except (TypeError, ValueError):
        die("threshold must be numeric — a non-numeric threshold is a vibe, not a criterion")
    if spec["on_missing_data"] not in MISSING_POLICIES:
        die(f"on_missing_data must be one of {sorted(MISSING_POLICIES)}")
    for k in ("source", "subject_id", "metric"):
        if not str(spec[k]).strip():
            die(f"criterion-spec key '{k}' is empty")
    try:
        deadline = datetime.datetime.fromisoformat(a.deadline.replace("Z", "+00:00"))
    except ValueError:
        die("deadline is not an ISO timestamp")
    if deadline <= utcnow():
        die("deadline is not in the future — nothing to pre-register")
    if not a.subject.strip():
        die("empty subject")
    rows = read_jsonl(FORECASTS)
    fid = f"F{sum(1 for r in rows if r.get('type') == 'forecast') + 1:05d}"
    append(FORECASTS, {"type": "forecast", "id": fid,
                       "ts_registered": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "class": a.fclass, "subject": a.subject.strip(), "probability": p,
                       "criterion_spec": spec,
                       "criterion_text": (a.criterion_text or "").strip(),
                       "deadline": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "stake": a.stake, "author": a.session, "status": "open"})
    print(f"registered: {fid} p={p} deadline={a.deadline}")


def cmd_grade(a):
    rows = read_jsonl(FORECASTS)
    fc = next((r for r in rows if r.get("type") == "forecast" and r.get("id") == a.id), None)
    if fc is None:
        die(f"no forecast {a.id}")
    if any(r.get("type") == "grade" and r.get("forecast_id") == a.id for r in rows):
        die(f"{a.id} already graded — grades are never overwritten")
    if fc["author"] == a.session:
        die(f"grader session equals author session ({a.session}) — constructor never grades own work")
    if a.outcome not in ("0", "1"):
        die("outcome must be 0 or 1")
    if len(a.receipt.strip()) < 20:
        die("receipt under 20 chars — a grade without evidence is a claim")
    append(FORECASTS, {"type": "grade", "forecast_id": a.id, "outcome": int(a.outcome),
                       "receipt": a.receipt.strip(), "grader": a.session,
                       "ts": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")})
    print(f"graded: {a.id} outcome={a.outcome}")


def cmd_promote(a):
    if a.claim_source == a.session:
        die("promoting session equals claim source — promotion requires a second pair of eyes")
    if len(a.receipt.strip()) < 20:
        die("receipt under 20 chars — promotion without evidence is forbidden")
    append(JOURNAL, {"ts": utcnow().strftime("%Y-%m-%d"), "type": "promotion",
                     "body": f"Claim promoted to fact: {a.claim.strip()} | receipt: {a.receipt.strip()}",
                     "claim_source": a.claim_source, "source": a.session, "status": "fact"})
    print("promoted")


def cmd_calibration(a):
    rows = read_jsonl(FORECASTS)
    fcs = {r["id"]: r for r in rows if r.get("type") == "forecast"}
    pairs = [(fcs[g["forecast_id"]]["probability"], g["outcome"])
             for g in rows if g.get("type") == "grade" and g.get("forecast_id") in fcs]
    n = len(pairs)
    print(f"graded forecasts: n={n} (H1 requires >=100)")
    if n == 0:
        return
    base = sum(o for _, o in pairs) / n
    brier_model = sum((p - o) ** 2 for p, o in pairs) / n
    brier_base = sum((base - o) ** 2 for _, o in pairs) / n
    diffs = [(base - o) ** 2 - (p - o) ** 2 for p, o in pairs]
    rng = random.Random(a.seed)
    boots = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(10000))
    lo, hi = boots[249], boots[9749]
    print(f"base rate: {base:.4f}  brier(model): {brier_model:.4f}  brier(base): {brier_base:.4f}")
    print(f"improvement (base - model): {brier_base - brier_model:+.4f}  bootstrap 95% CI: [{lo:+.4f}, {hi:+.4f}]")
    verdict = "PASS" if (n >= 100 and lo > 0) else "NOT PASSED"
    print(f"H1 verdict at current ledger: {verdict}")


def main():
    ap = argparse.ArgumentParser(prog="bbp")
    ap.add_argument("--session", required=True, help="explicit session identity, e.g. session-2026-08-17")
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("journal"); j.add_argument("type"); j.add_argument("status"); j.add_argument("body"); j.add_argument("--ref")
    r = sub.add_parser("forecast-register")
    for arg in ("--fclass", "--subject", "--probability", "--criterion-spec", "--deadline"):
        r.add_argument(arg, required=True)
    r.add_argument("--criterion-text", help="optional human-readable summary; never used for grading")
    r.add_argument("--stake", default="paper")
    g = sub.add_parser("forecast-grade")
    g.add_argument("--id", required=True); g.add_argument("--outcome", required=True); g.add_argument("--receipt", required=True)
    p = sub.add_parser("promote")
    p.add_argument("--claim", required=True); p.add_argument("--claim-source", required=True); p.add_argument("--receipt", required=True)
    c = sub.add_parser("calibration"); c.add_argument("--seed", type=int, default=17)
    a = ap.parse_args()
    {"journal": cmd_journal, "forecast-register": cmd_register, "forecast-grade": cmd_grade,
     "promote": cmd_promote, "calibration": cmd_calibration}[a.cmd](a)


if __name__ == "__main__":
    main()
