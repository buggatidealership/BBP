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
    """Tolerate corrupt lines but NEVER silently skip them: one malformed line used to kill
    every reader (red-team A4, 2026-08-20). Bad lines are reported loudly to stderr."""
    if not path.exists():
        return []
    rows, bad = [], []
    for i, l in enumerate(path.read_text().splitlines(), 1):
        if not l.strip():
            continue
        try:
            rows.append(json.loads(l))
        except json.JSONDecodeError:
            bad.append(i)
    if bad:
        print(f"WARNING: {path.name} has {len(bad)} malformed line(s) at {bad} — "
              "read continued without them; fix the file before trusting any count.", file=sys.stderr)
    return rows


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
    # The source must be OUTSIDE the firm. F00001/F00002 (2026-08-21) were registered against
    # JOURNAL.jsonl - the firm forecasting its own ledger, with the author able to satisfy one
    # of them by choosing to. A Brier score computed over self-authored outcomes measures
    # nothing. This is the ruler-measuring-itself problem inside the forecast register.
    _bad = source_violation(spec.get("source", ""))
    if _bad:
        die(_bad)
    rows = read_jsonl(FORECASTS)
    # n-padding block (red-team A2, 2026-08-20): the same subject forecast repeatedly in the
    # same class would inflate n toward H1's >=100 without adding evidence.
    key = (a.fclass, str(spec["subject_id"]).lower())
    if any((r.get("class"), str(r.get("criterion_spec", {}).get("subject_id", "")).lower()) == key
           for r in rows if r.get("type") == "forecast"):
        die(f"{a.fclass}/{spec['subject_id']} already forecast — one forecast per subject per class; "
            "repeats pad n without adding evidence")
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
    # Asymmetric deadline rule (red-team A1, 2026-08-20): an event OCCURRING is observable early,
    # but "it never happened" is only knowable once the window closes.
    deadline = datetime.datetime.fromisoformat(fc["deadline"].replace("Z", "+00:00"))
    if a.outcome == "0" and utcnow() < deadline:
        die(f"cannot grade outcome=0 before the deadline ({fc['deadline']}) — non-occurrence is not "
            "observable until the window closes; outcome=1 may be graded as soon as the event occurs")
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


def source_violation(src):
    """Return a rejection message if this criterion source is not an approved external one,
    else None. Shared by registration and by withdrawal, which is what makes withdrawal safe:
    a forecast may only be retracted if the CURRENT gates would refuse to register it."""
    fs = json.loads((ROOT / "config" / "forecast_sources.json").read_text())
    src = str(src).strip()
    bad = [t for t in fs["forbidden_substrings"] if t.lower() in src.lower()]
    if bad:
        return (f"criterion source {src!r} names the firm's own artifacts ({bad}) — a forecast "
                "whose outcome the firm writes is not a forecast. Source must be external.")
    if src not in fs["external_sources"]:
        return (f"criterion source {src!r} is not an approved external source. Approved: "
                f"{fs['external_sources']}. Add it to config/forecast_sources.json first, "
                "as a deliberate act, before forecasting against it.")
    return None


def cmd_withdraw(a):
    """Retract a forecast that the CURRENT gates would refuse to register.

    Withdrawal is otherwise the perfect calibration cheat: retract every prediction that starts
    to look wrong and the Brier score becomes a record of the ones that went well. So the only
    admissible reason is structural - a gate added after registration now rejects this forecast's
    own stored spec. That is computable, and it is checked here rather than argued."""
    rows = read_jsonl(FORECASTS)
    fc = next((r for r in rows if r.get("type") == "forecast" and r.get("id") == a.id), None)
    if fc is None:
        die(f"no forecast {a.id}")
    if any(r.get("type") == "grade" and r.get("forecast_id") == a.id for r in rows):
        die(f"{a.id} is already graded — a graded forecast stays in the record permanently")
    if any(r.get("type") == "withdrawal" and r.get("forecast_id") == a.id for r in rows):
        die(f"{a.id} already withdrawn")
    why = source_violation(fc.get("criterion_spec", {}).get("source", ""))
    if why is None:
        die(f"{a.id} still passes every current registration gate. A live forecast may not be "
            "retracted: withdrawing predictions that look like losing is how a calibration "
            "record becomes a highlight reel.")
    append(FORECASTS, {"type": "withdrawal", "forecast_id": a.id,
                       "ts": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "gate_that_refuses_it": why, "reason": a.reason.strip(),
                       "session": a.session})
    print(f"withdrawn: {a.id} — excluded from calibration, record retained")


def cmd_calibration(a):
    rows = read_jsonl(FORECASTS)
    gone = {r["forecast_id"] for r in rows if r.get("type") == "withdrawal"}
    fcs = {r["id"]: r for r in rows if r.get("type") == "forecast" and r["id"] not in gone}
    pairs = [(fcs[g["forecast_id"]]["probability"], g["outcome"])
             for g in rows if g.get("type") == "grade" and g.get("forecast_id") in fcs]
    classes = {}
    for g in rows:
        if g.get("type") == "grade" and g.get("forecast_id") in fcs:
            classes.setdefault(fcs[g["forecast_id"]].get("class", "?"), []).append(
                (fcs[g["forecast_id"]]["probability"], g["outcome"]))
    n = len(pairs)
    print(f"graded forecasts: n={n} (H1 requires >=100)")
    if len(classes) > 1:
        print(f"NOTE: {len(classes)} forecast classes present {dict((k, len(v)) for k, v in classes.items())} — "
              "pooling classes with different base rates makes the pooled figure uninterpretable "
              "(red-team A3, 2026-08-20). Per-class results below are the ones H1 is judged on.")
        for cname, cp in sorted(classes.items()):
            cb = sum(o for _, o in cp) / len(cp)
            bm = sum((pr - o) ** 2 for pr, o in cp) / len(cp)
            bb = sum((cb - o) ** 2 for _, o in cp) / len(cp)
            print(f"  [{cname}] n={len(cp)} base={cb:.4f} brier={bm:.4f} vs base_brier={bb:.4f} "
                  f"improvement={bb - bm:+.4f}")
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
    wd = sub.add_parser("forecast-withdraw")
    wd.add_argument("--id", required=True); wd.add_argument("--reason", required=True)
    c = sub.add_parser("calibration"); c.add_argument("--seed", type=int, default=17)
    a = ap.parse_args()
    {"journal": cmd_journal, "forecast-register": cmd_register, "forecast-grade": cmd_grade,
     "promote": cmd_promote, "calibration": cmd_calibration,
     "forecast-withdraw": cmd_withdraw}[a.cmd](a)


if __name__ == "__main__":
    main()
