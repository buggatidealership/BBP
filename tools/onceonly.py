#!/usr/bin/env python3
"""Duplicate-fire guard: exit non-zero if an event of the given type already exists.

Wakes fire more than once - manual test fires, scheduler retries, a session re-run by hand.
A wake that performs a one-time act needs the guard in CODE, because a guard that lives in the
wake's prompt cannot be enforced from anywhere else (red-team 2026-08-20).

    python3 tools/onceonly.py venue_decision
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) != 2:
        print("usage: onceonly.py <event_type>", file=sys.stderr)
        return 2
    want = sys.argv[1]
    hits = []
    for line in (ROOT / "JOURNAL.jsonl").read_text().splitlines():
        if line.strip():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") == want:
                hits.append(r)
    if hits:
        print(f"STOP: {len(hits)} {want} event(s) already in the journal (newest "
              f"{hits[-1]['ts']}). This firing is a duplicate; change nothing.", file=sys.stderr)
        return 3
    print(f"no {want} event yet — this firing is the first")
    return 0


if __name__ == "__main__":
    sys.exit(main())
