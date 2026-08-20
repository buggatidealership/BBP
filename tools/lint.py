#!/usr/bin/env python3
"""Non-computable-claim linter: find hope wearing the costume of verification.

Rule 12 (2026-08-20, principal): in an operating system, any non-binary wording in an
OPERATIONAL claim — a trigger, threshold, cadence, or guarantee — is hope, not verification.
This tool is the mechanical enforcer for that rule.

It flags hedge terms in .md docs and in scheduled-wake prompts, because a wake instruction
that says "a large shortfall" cannot be executed identically by two different sessions.

Exit 1 if any BLOCKING hit is found. Descriptive prose (journal narration, rationale,
correction records) is allowed to hedge; operational lines are not.
"""
import re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Terms with no computable meaning when they gate an action.
HEDGES = ["meaningful", "appropriate", "as needed", "as appropriate", "regularly", "periodically",
          "sufficient", "sufficiently", "reasonable", "significant", "promptly", "when necessary",
          "best effort", "large shortfall", "small shortfall", "soon", "frequently", "adequate",
          "a few", "several", "many", "some point", "if needed", "where possible", "try to"]
# FAIL-CLOSED (hardened 2026-08-20 after a drill caught this tool missing "republished by
# shifts on meaningful change" — an imperative-verb whitelist has false negatives, and a
# false negative in an integrity tool is worse than an annotation burden). Every hedge in a
# doc line is a hit unless the line is explicitly marked as narration.
# Prose that merely explains is exempt; mark such lines with this token.
EXEMPT = "lint-exempt"

def scan(path, text, source):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if EXEMPT in low or low.strip().startswith(("*correction", "*(", ">")):
            continue
        for h in HEDGES:
            if re.search(rf"\b{re.escape(h)}\b", low):
                hits.append((source, path, i, h, line.strip()[:100]))
    return hits

def main():
    all_hits = []
    for p in sorted(ROOT.glob("*.md")):
        all_hits += scan(p.name, p.read_text(), "doc")
    snap = ROOT / "data" / "triggers_snapshot.json"
    if snap.exists():
        all_hits += scan(snap.name, snap.read_text(), "wake")
    if not all_hits:
        print("LINT PASS: no non-computable terms in operational claims")
        return 0
    print(f"LINT FAIL: {len(all_hits)} non-computable term(s) in operational claims\n")
    for source, path, i, term, line in all_hits:
        print(f"  [{source}] {path}:{i}  «{term}»\n      {line}")
    print("\nFix: replace each with a number, a date, a comparator, or a named artifact — "
          "or append 'lint-exempt' if the line is explanation, not instruction.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
