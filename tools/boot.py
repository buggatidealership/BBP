#!/usr/bin/env python3
"""BOOT. Run this first. It does not tell you what to do; it computes it and gates it.

    python3 tools/boot.py

Exit 0 = the machine is sound and the printed work is yours to do.
Exit 1 = DO NOT PROCEED. An invariant is broken; fixing it is the only work.

Nothing in this output is recalled. Goal comes from config/gates.json, phase and thresholds
from config/survey.json, prohibitions from config/boot.json, due work from the journal and
the scheduler mirror, soundness from tools/selfcheck.py.
"""
import hashlib, json, os, subprocess, sys, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = lambda p: json.loads((ROOT / p).read_text())

def jrows():
    rows = []
    for l in (ROOT / "JOURNAL.jsonl").read_text().splitlines():
        if l.strip():
            try: rows.append(json.loads(l))
            except json.JSONDecodeError: pass
    return rows

def _selfhash():
    return hashlib.sha256(pathlib.Path(__file__).resolve().read_bytes()).hexdigest()


def _head():
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "UNRESOLVED"


def run_wake(wake_id):
    """EXECUTE a wake's sequence. The model's only act is invoking this; every step is run by
    the runner, in order, halting on failure. A receipt is written by the RUNNER with each
    step's exit code, so a session that claims work it did not do produces no receipt and the
    claim is detectable (principal, 2026-08-21: instructions are where hallucination lives)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cfg = R("config/wakes.json")["wakes"]
    if wake_id not in cfg:
        print(f"UNKNOWN WAKE '{wake_id}'. Known: {sorted(cfg)}")
        return 2
    seq = cfg[wake_id]
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    selfhash = _selfhash()
    receipt = {"wake": wake_id, "started": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "runner_sha256": selfhash[:16],
               "reexeced": bool(os.environ.get("BBP_BOOT_REEXEC")), "steps": []}
    print(f"RUN WAKE '{wake_id}' — {len(seq['steps'])} steps, executed not interpreted")
    failed = None
    for i, step in enumerate(seq["steps"], 1):
        if step[0] == "__commit__":
            # NEVER hardcode this exit code. It was 0-by-literal until 2026-08-21, which meant
            # the receipt asserted a commit it had not measured: git commit exits 1 on
            # nothing-to-commit AND on real failures (no identity, hook rejection, index lock),
            # and both were being recorded as success. A receipt containing a constant is not
            # a receipt. Nothing-to-commit is a legitimate no-op and is labelled as one; every
            # other non-zero halts the sequence.
            before = _head()
            # Whether this is a benign no-op is decided by MEASURING the index, not by
            # matching git's English. The first version of this fix looked for the phrase
            # "nothing to commit" and missed "no changes added to commit" on the very first
            # drill: a detector keyed to prose is the same defect as a hardcoded exit code,
            # one layer up. Empty index before the call == nothing to commit, full stop.
            staged_empty = subprocess.run(["git", "diff", "--cached", "--quiet"],
                                          cwd=ROOT, capture_output=True).returncode == 0
            r = subprocess.run(["git", "commit", "-m", f"{step[1]} {stamp} (wake: {wake_id})"],
                               cwd=ROOT, capture_output=True, text=True)
            body = (r.stdout + r.stderr)
            after = _head()
            noop = r.returncode != 0 and staged_empty and after == before
            cmd = f"git commit -m '{step[1]} {stamp}'"
            rc = 0 if (r.returncode == 0 or noop) else r.returncode
            out = (f"NO-OP: index empty, HEAD unchanged at {before[:12]}") if noop else body[-300:]
            extra = {"head_before": before, "head_after": after, "staged_before": not staged_empty,
                     "committed": bool(after != before), "raw_exit": r.returncode}
        elif step[0] == "__push__":
            r = subprocess.run(["git", "push", "origin", step[1]], cwd=ROOT, capture_output=True, text=True)
            cmd, rc, out = f"git push origin {step[1]}", r.returncode, (r.stdout + r.stderr)[-300:]
            extra = {"head_after": _head()}
        else:
            r = subprocess.run(step, cwd=ROOT, capture_output=True, text=True)
            cmd, rc, out = " ".join(step), r.returncode, (r.stdout + r.stderr)[-300:]
            extra = {}
        entry = {"n": i, "cmd": cmd, "exit": rc, "tail": out.strip()[-200:]}
        entry.update(extra)
        receipt["steps"].append(entry)
        print(f"  [{i}/{len(seq['steps'])}] exit={rc}  {cmd}")
        if rc != 0:
            failed = i
            break
        # THE RUNNER IS PART OF WHAT IT PULLS. Python reads this file once, at startup, so a
        # `git pull` step that updates tools/boot.py does NOT change the code still executing:
        # the rest of the sequence runs the old runner, and the receipt it writes is in the old
        # format. Observed 2026-08-21 on the 16:15Z scheduled sampler run, whose step 7 carried
        # the retired '(commit may be empty)' placeholder hours after that was fixed and pushed.
        # Subprocess steps are unaffected - they load from disk - which is why the same receipt
        # shows the NEW selfcheck's I19. Re-exec once, restarting from step 1; steps before a
        # pull are checkout/pull and idempotent.
        if _selfhash() != selfhash and not os.environ.get("BBP_BOOT_REEXEC"):
            print(f"  RUNNER UPDATED by step {i}: tools/boot.py changed on disk. Re-executing "
                  "so the rest of this wake runs the pulled code, not the code that started.")
            os.environ["BBP_BOOT_REEXEC"] = "1"
            os.execv(sys.executable, [sys.executable] + sys.argv)
    receipt["ended"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    receipt["result"] = "OK" if failed is None else f"HALTED at step {failed}"
    rdir = ROOT / "data" / "runs"; rdir.mkdir(parents=True, exist_ok=True)
    rpath = rdir / f"run_{stamp}_{wake_id}.json"
    rpath.write_text(json.dumps(receipt, indent=1) + "\n")
    # The receipt is written AFTER the sequence, so the sequence's own commit cannot contain it.
    # Committing it here, in code, means the evidence lands without any session choosing to do
    # it (found by the sampler session 2026-08-21: it had to commit the receipt by hand, which
    # made the record depend on a model's initiative — exactly what receipts exist to avoid).
    rel = str(rpath.relative_to(ROOT))
    ga = subprocess.run(["git", "add", rel], cwd=ROOT, capture_output=True, text=True)
    gc = subprocess.run(["git", "commit", "-q", "-m",
                         f"Receipt: {wake_id} run {stamp} ({receipt['result']})"],
                        cwd=ROOT, capture_output=True, text=True)
    pr = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, capture_output=True, text=True)
    # "Landed" is two facts, each measured, neither inferred from an exit code: the receipt is
    # in HEAD's tree, and HEAD is what origin/main points at. `git ls-files` was used here for
    # one drill and returned success for a merely STAGED receipt (2026-08-21) - staged is not
    # committed, and committed is not pushed.
    in_head = subprocess.run(["git", "cat-file", "-e", f"HEAD:{rel}"],
                             cwd=ROOT, capture_output=True).returncode == 0
    local = _head()
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    landed = in_head and local == remote and remote != ""
    print(f"RECEIPT {rel} — {receipt['result']} (add={ga.returncode} commit={gc.returncode} "
          f"push={pr.returncode} in_head={in_head} head=={remote[:8]}: {local == remote})")
    if not landed:
        # An unpushed receipt is an invisible receipt: the work may have happened and no
        # external party can see that it did. That is a failed run whatever the steps said.
        print("IT FAILED: the receipt did not reach origin. The run is UNEVIDENCED. "
              "Report this verbatim.", file=sys.stderr)
        print((pr.stdout + pr.stderr)[-400:], file=sys.stderr)
    if failed:
        print("IT FAILED: the sequence halted. Report this verbatim; do not continue past it.")
    return 0 if (failed is None and landed) else 1


def main():
    if "--run" in sys.argv:
        return run_wake(sys.argv[sys.argv.index("--run") + 1])
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
