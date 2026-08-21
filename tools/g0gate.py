#!/usr/bin/env python3
"""Run the G0 gate and RECORD its verdict as the event the watchdogs look for.

G0's pass condition in config/gates.json is: tools/selfcheck.py exits 0 AND a g0_gate_result
event with verdict PASS exists. The second half is produced here, from the first half - the
verdict is the subprocess exit code, not a judgement, so the gate cannot be talked into passing.
"""
import json, pathlib, subprocess, sys, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    g0 = next(g for g in json.loads((ROOT / "config" / "gates.json").read_text())["gates"]
              if g["id"] == "G0")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "selfcheck.py")],
                       cwd=ROOT, capture_output=True, text=True)
    verdict = "PASS" if r.returncode == 0 else "FAIL"
    tail = (r.stdout.strip().splitlines() or ["no output"])[-1]
    ev = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "type": g0["result_event_type"], "provenance": "EARNED",
          "body": f"G0 gate check: verdict {verdict}. tools/selfcheck.py exited {r.returncode}. "
                  f"{tail}", "source": "wake-g0_gate", "verdict": verdict}
    with (ROOT / "JOURNAL.jsonl").open("a") as f:
        f.write(json.dumps(ev, separators=(",", ":")) + "\n")
    st = subprocess.run([sys.executable, str(ROOT / "tools" / "status.py")],
                        capture_output=True, text=True)
    if st.returncode != 0:
        print(f"IT FAILED: the G0 verdict was journaled but status.py exited {st.returncode}, so "
              f"the board is stale and I10 will fail.\n{(st.stdout + st.stderr)[-400:]}",
              file=sys.stderr)
        return 1
    print(f"G0 verdict {verdict} recorded as a {g0['result_event_type']} event")
    if verdict == "FAIL":
        print(f"IT FAILED: {g0['kill_condition']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
