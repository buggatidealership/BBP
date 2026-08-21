#!/usr/bin/env python3
"""Static audit for the defect CLASSES this firm has actually shipped.

Every detector here exists because the corresponding bug reached main and was found by a
human saying "check that". A detector is added the same day its class is found; the point is
that the second instance of a class is caught by the machine, not by the principal's attention.

Findings are binary: any unwaived finding exits 1. A finding that is a false positive is
waived by id in config/audit_waivers.json with a written reason - waiving is a recorded act,
not a silent suppression.

    python3 tools/audit.py
"""
import ast, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = sorted((ROOT / "tools").glob("*.py"))
# Keys present on 120/120 journal rows as of 2026-08-21. Anything else varies by event type
# and must be read with .get - status.py crashed the sampler wake for exactly this reason.
GUARANTEED = {"ts", "type", "body", "source"}
ROWISH = {"e", "r", "row", "ev", "rec", "entry", "x"}
OUTISH = {"out", "body", "tail", "stdout", "stderr", "txt", "output", "res"}


def findings_for(path):
    src = path.read_text()
    rel = str(path.relative_to(ROOT))
    tree = ast.parse(src)
    out = []

    for node in ast.walk(tree):
        # D1: a subprocess.run whose result is thrown away. boot.py discarded git commit's
        # returncode here and hardcoded exit 0 into the receipt (2026-08-21).
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name == "run":
                out.append(("D1-discarded-exit", node.lineno,
                            "subprocess.run result discarded: exit code never read"))

        # D2: deciding control flow by searching a tool's English. Two separate bugs today
        # ("nothing to commit" vs "no changes added to commit"); prose is not an interface.
        if isinstance(node, ast.Compare) and node.ops and isinstance(node.ops[0], ast.In):
            left, right = node.left, node.comparators[0]
            rname = right.attr if isinstance(right, ast.Attribute) else getattr(right, "id", "")
            if isinstance(left, ast.Constant) and isinstance(left.value, str) and rname in OUTISH:
                out.append(("D2-prose-match", node.lineno,
                            f"control flow keyed to substring {left.value!r} in process output"))

        pass

    # D3: reading a journal key that is not guaranteed, without .get. Scoped by DERIVATION,
    # not by variable name: v1 keyed off a guessed name list ("e", "r", "x") and produced 12
    # false positives on config and forecast iteration in its first run. Trace which names
    # actually hold journal rows instead.
    jvars = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
           and isinstance(node.targets[0], ast.Name):
            rhs = ast.get_source_segment(src, node.value) or ""
            if "JOURNAL" in rhs or "jrows" in rhs:
                jvars.add(node.targets[0].id)
    rowvars = set()
    for node in ast.walk(tree):
        gens = ([node] if isinstance(node, ast.For) else
                list(getattr(node, "generators", [])))
        for g in gens:
            it = getattr(g, "iter", None)
            base = it
            while isinstance(base, ast.Subscript):
                base = base.value
            if isinstance(base, ast.Name) and base.id in jvars \
               and isinstance(g.target, ast.Name):
                rowvars.add(g.target.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
           and node.value.id in rowvars and isinstance(node.slice, ast.Constant) \
           and isinstance(node.slice.value, str) and node.slice.value not in GUARANTEED:
            out.append(("D3-unguarded-key", node.lineno,
                        f"{node.value.id}[{node.slice.value!r}] on a journal row - key is not "
                        "on every event; use .get"))

    # D4: a date restated in code that already lives in config. Four gate dates were duplicated
    # into status.py while I14 watched only sample.py (2026-08-21).
    cfg_text = " ".join((p).read_text() for p in sorted((ROOT / "config").glob("*.json")))
    cfg_dates = set(re.findall(r"20\d{2}-\d{2}-\d{2}", cfg_text))
    for m in re.finditer(r"[\"'](20\d{2}-\d{2}-\d{2})[\"']", src):
        if m.group(1) in cfg_dates:
            line = src[:m.start()].count("\n") + 1
            out.append(("D4-duplicated-date", line,
                        f"{m.group(1)} is already in config/; read it, do not restate it"))
    return [{"id": f"{rel}:{ln}:{code}", "file": rel, "line": ln, "code": code, "why": why}
            for code, ln, why in out]


def main():
    wpath = ROOT / "config" / "audit_waivers.json"
    waivers = json.loads(wpath.read_text()) if wpath.exists() else {}
    all_f = [f for p in TOOLS for f in findings_for(p)]
    live = [f for f in all_f if f["id"] not in waivers]
    print(f"AUDIT {len(TOOLS)} tools — {len(all_f)} finding(s), {len(all_f) - len(live)} waived")
    for f in live:
        print(f"  {f['code']:22} {f['file']}:{f['line']}  {f['why']}")
    if live:
        print(f"\nIT FAILED: {len(live)} unwaived finding(s). Fix, or waive by id in "
              "config/audit_waivers.json with a reason.", file=sys.stderr)
        return 1
    print("clean: no unwaived findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
