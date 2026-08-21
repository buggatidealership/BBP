#!/usr/bin/env python3
"""Tier-1 drill: attempt known-bad writes and confirm the tool REFUSES every one.

Tier-2 enforcement (CI blocks a bad commit) has been confirmed by an outside machine. Tier-1
is the tool refusing the write in the first place, and until now the only evidence for it was
a prose instruction in the G0 wake's prompt telling a model to try five things - which is not
evidence, because a model can report "all refused" without attempting anything.

This runs against a THROWAWAY COPY of the repo: a violation that is wrongly ACCEPTED writes to
the copy, never to the real ledger. Exit 0 means every attempt was refused. Exit 1 names the
attempts that got through, and each of those is a G0 FAIL.
"""
import json, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Each entry: (name, argv-after-`forecast-register`/`forecast-grade`, why it must be refused)
ATTEMPTS = [
    ("prose criterion", ["forecast-register", "--fclass", "d", "--subject", "s",
                         "--probability", "0.5", "--deadline", "2027-01-01T00:00:00Z",
                         "--criterion-spec", '{"source":"geckoterminal:pools","subject_id":"a",'
                         '"metric":"it goes up a lot","comparator":"vibes","threshold":"high",'
                         '"on_missing_data":"resolve_0"}'],
     "comparator is not a comparator; criteria must be machine-decidable"),
    ("probability 1.0", ["forecast-register", "--fclass", "d", "--subject", "s",
                         "--probability", "1.0", "--deadline", "2027-01-01T00:00:00Z",
                         "--criterion-spec", '{"source":"geckoterminal:pools","subject_id":"b",'
                         '"metric":"reserve_usd","comparator":">=","threshold":1,'
                         '"on_missing_data":"resolve_0"}'],
     "certainty is not a forecast; p is clamped to [0.01, 0.99]"),
    ("past deadline", ["forecast-register", "--fclass", "d", "--subject", "s",
                       "--probability", "0.5", "--deadline", "2020-01-01T00:00:00Z",
                       "--criterion-spec", '{"source":"geckoterminal:pools","subject_id":"c",'
                       '"metric":"reserve_usd","comparator":">=","threshold":1,'
                       '"on_missing_data":"resolve_0"}'],
     "a deadline in the past pre-registers nothing"),
    ("self-referential source", ["forecast-register", "--fclass", "d", "--subject", "s",
                                 "--probability", "0.5", "--deadline", "2027-01-01T00:00:00Z",
                                 "--criterion-spec", '{"source":"JOURNAL.jsonl","subject_id":"d",'
                                 '"metric":"count","comparator":">=","threshold":1,'
                                 '"on_missing_data":"resolve_0"}'],
     "the firm may not forecast a file it writes itself"),
    ("unapproved source", ["forecast-register", "--fclass", "d", "--subject", "s",
                           "--probability", "0.5", "--deadline", "2027-01-01T00:00:00Z",
                           "--criterion-spec", '{"source":"whatever_api","subject_id":"e",'
                           '"metric":"reserve_usd","comparator":">=","threshold":1,'
                           '"on_missing_data":"resolve_0"}'],
     "sources are added to config as a deliberate act, not inline at registration"),
]


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="bbp-tier1-"))
    try:
        shutil.copytree(ROOT / "tools", tmp / "tools")
        shutil.copytree(ROOT / "config", tmp / "config")
        (tmp / "JOURNAL.jsonl").write_text("")
        (tmp / "FORECASTS.jsonl").write_text("")
        bbp = str(tmp / "tools" / "bbp.py")
        accepted = []
        print(f"TIER-1 DRILL — {len(ATTEMPTS) + 3} attempts against a throwaway copy")
        for name, argv, why in ATTEMPTS:
            r = subprocess.run([sys.executable, bbp, "--session", "drill"] + argv,
                               capture_output=True, text=True)
            ok = r.returncode != 0
            print(f"  [{'REFUSED' if ok else 'ACCEPTED'}] {name}")
            if not ok:
                accepted.append((name, why))

        # Duplicate subject+class: register one valid forecast, then the same subject again.
        valid = ["forecast-register", "--fclass", "vs", "--subject", "s", "--probability", "0.5",
                 "--deadline", "2027-01-01T00:00:00Z", "--criterion-spec",
                 '{"source":"geckoterminal:pools","subject_id":"dup","metric":"reserve_usd",'
                 '"comparator":">=","threshold":1,"on_missing_data":"resolve_0"}']
        first = subprocess.run([sys.executable, bbp, "--session", "drill"] + valid,
                               capture_output=True, text=True)
        if first.returncode != 0:
            print("  [BROKEN] a VALID forecast was refused — the drill cannot test duplicates")
            print(f"           {(first.stdout + first.stderr).strip()[:200]}")
            accepted.append(("valid registration refused", "the gate rejects legitimate writes"))
        else:
            r = subprocess.run([sys.executable, bbp, "--session", "drill"] + valid,
                               capture_output=True, text=True)
            ok = r.returncode != 0
            print(f"  [{'REFUSED' if ok else 'ACCEPTED'}] duplicate subject+class")
            if not ok:
                accepted.append(("duplicate subject+class", "repeats pad n without evidence"))

            # Self-grading: author session grading its own forecast.
            fid = json.loads((tmp / "FORECASTS.jsonl").read_text().splitlines()[0])["id"]
            r = subprocess.run([sys.executable, bbp, "--session", "drill", "forecast-grade",
                                "--id", fid, "--outcome", "1", "--receipt", "x"],
                               capture_output=True, text=True)
            ok = r.returncode != 0
            print(f"  [{'REFUSED' if ok else 'ACCEPTED'}] author grading own forecast")
            if not ok:
                accepted.append(("self-grading", "constructor never grades own work"))

            # Early outcome=0: a different session, before the deadline.
            r = subprocess.run([sys.executable, bbp, "--session", "other", "forecast-grade",
                                "--id", fid, "--outcome", "0", "--receipt", "x"],
                               capture_output=True, text=True)
            ok = r.returncode != 0
            print(f"  [{'REFUSED' if ok else 'ACCEPTED'}] outcome=0 before deadline")
            if not ok:
                accepted.append(("early outcome=0", "non-occurrence is not knowable early"))

        if accepted:
            print(f"\nIT FAILED: {len(accepted)} known-bad write(s) were ACCEPTED:", file=sys.stderr)
            for n, why in accepted:
                print(f"  - {n}: {why}", file=sys.stderr)
            return 1
        print("\nall attempts refused: tier-1 enforcement holds")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
