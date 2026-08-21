#!/usr/bin/env python3
"""G0 watchdog: exit non-zero if the G0 gate never produced its result event.

This is the firm's cross-session independence layer. It runs in a session that is NOT the
orchestrator, so an orchestrator that died, hallucinated a gate check, or simply never ran
one is detectable without asking the orchestrator anything.

The alarm IS the non-zero exit: tools/boot.py halts the wake sequence on it and writes a
HALTED receipt, so the failure is recorded in the repository rather than in a model's summary.
"""
import datetime, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    gates = json.loads((ROOT / "config" / "gates.json").read_text())["gates"]
    g0 = next((g for g in gates if g["id"] == "G0"), None)
    if g0 is None:
        print("IT FAILED: no G0 gate defined in config/gates.json", file=sys.stderr)
        return 1
    want = g0["result_event_type"]
    due = datetime.datetime.fromisoformat(g0["due"] + "T00:00:00+00:00")
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = []
    for line in (ROOT / "JOURNAL.jsonl").read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    hits = [r for r in rows if r.get("type") == want]
    if hits:
        print(f"G0 OK: {len(hits)} {want} event(s) in the journal; newest {hits[-1]['ts']}")
        return 0
    if now < due:
        print(f"G0 not yet due ({g0['due']}); no {want} event expected. Watchdog silent.")
        return 0
    print(f"IT FAILED: G0 was due {g0['due']} and NO {want} event exists in JOURNAL.jsonl. "
          "The gate did not run, or ran and did not record. Per config/gates.json the kill "
          f"condition is: {g0['kill_condition']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
