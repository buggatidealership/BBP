#!/usr/bin/env python3
"""BOOT. Run this first. It does not tell you what to do; it computes it and gates it.

    python3 tools/boot.py

Exit 0 = the machine is sound and the printed work is yours to do.
Exit 1 = DO NOT PROCEED. An invariant is broken; fixing it is the only work.

Nothing in this output is recalled. Goal comes from config/gates.json, phase and thresholds
from config/survey.json, prohibitions from config/boot.json, due work from the journal and
the scheduler mirror, soundness from tools/selfcheck.py.
"""
import json, os, subprocess, sys, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = lambda p: json.loads((ROOT / p).read_text())

def jrows():
    rows = []
    for l in (ROOT / "JOURNAL.jsonl").read_text().splitlines():
        if l.strip():
            try: rows.append(json.loads(l))
            except json.JSONDecodeError: pass
    return rows

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    g, s, b = R("config/gates.json"), R("config/survey.json"), R("config/boot.json")
    j = jrows()
    print("=" * 78)
    print(f"BBP BOOT  {now:%Y-%m-%d %H:%M UTC}")
    print("=" * 78)
    print(f"\nGOAL: {g['goal_one_line']}\n")

    # 1. soundness gate — nothing else matters if this fails
    sc = subprocess.run([sys.executable, str(ROOT / "tools" / "selfcheck.py")], capture_output=True, text=True)
    tail = [l for l in sc.stdout.splitlines() if l.strip()][-1]
    print(f"MACHINE STATE: {tail}")
    if sc.returncode != 0:
        print("\n" + "!" * 78)
        print("DO NOT PROCEED. Broken invariants:")
        for l in sc.stdout.splitlines():
            if "FAIL" in l: print(f"  {l.strip()}")
        print("Fixing these is the only authorised work. Re-run this boot when they pass.")
        print("!" * 78)
        return 1

    # 2. where the firm is — computed, not remembered
    cohorts = sorted((ROOT / "data" / "cohorts").glob("cohort_*.json"))
    ct = s["census_thresholds"]
    nxt = next((x for x in g["gates"] if x["status"] == "pending"), None)
    print(f"PHASE: {s['phase']} — {len(cohorts)} cohorts collected "
          f"(gap incident below {ct['gap_incident_below']}, survey stops below {ct['stop_survey_below']}); "
          f"decision {s['decision_utc']}")
    if nxt:
        print(f"NEXT GATE: {nxt['id']} {nxt['title']} due {nxt['due']} — passes when: {nxt['pass_condition']}")

    # 3. what is due — from the scheduler mirror and the journal
    try:
        wp = R("data/wake_prompts.json")["wakes"]
        due = sorted(((v.get("next_run_at") or "", v["name"]) for v in wp.values()))
        print("\nSCHEDULED (mirror; the scheduler is authoritative):")
        for t, n in due[:4]: print(f"  {t[:16]:18} {n}")
    except Exception as e:
        print(f"\nSCHEDULED: mirror unreadable ({e})")

    resolved = {e["body"].split("|", 1)[0].strip() for e in j if e["type"] == "principal_resolved"}
    pend = [e["body"] for e in j if e["type"] == "principal_pending"
            and e["body"].split("|", 1)[0].strip() not in resolved]
    print(f"\nBLOCKED ON THE PRINCIPAL ({len(pend)}):")
    for p in pend: print(f"  - {p.split('|')[0].strip()}")

    # 4. prohibitions, each with its enforcer named
    print("\nFORBIDDEN (enforcer named; if it says UNENFORCED, you are the enforcer):")
    for x in b["forbidden"]:
        mark = "UNENFORCED" if "UNENFORCED" in x["enforced_by"] else "enforced"
        print(f"  [{mark}] {x['rule']}\n              via {x['enforced_by']}")
    print("\nHUMAN-ONLY (no session may do these):")
    for h in b["human_only"]: print(f"  - {h}")

    print("\n" + "=" * 78)
    print("Boot complete. The machine is sound. Your work is whatever the wake that woke you")
    print("specifies, constrained by the above. If no wake woke you, there is no work: the")
    print("schedule is the work list, and unscheduled work is not the firm's work.")
    print("=" * 78)
    return 0

if __name__ == "__main__":
    try:
        code = main()
    except BrokenPipeError:
        # A boot tool that dies when its output is piped is a boot tool that dies.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        code = 0
    sys.exit(code)
