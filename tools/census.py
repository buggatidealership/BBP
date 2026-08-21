#!/usr/bin/env python3
"""H1.0 census: the numbers the decision wake must have, computed, never recalled.

Prints per-network cohort coverage and the census thresholds from config/survey.json, and
exits non-zero if the survey is below the stop threshold, so the decision wake HALTS rather
than proceeding on insufficient data.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    cfg = json.loads((ROOT / "config" / "survey.json").read_text())
    nets, ct = cfg["candidates"], cfg["census_thresholds"]
    cohorts = sorted((ROOT / "data" / "cohorts").glob("cohort_*.json"))
    per_net_pools, complete, unreadable = {n: 0 for n in nets}, 0, 0
    for c in cohorts:
        try:
            d = json.loads(c.read_text())
        except Exception:
            unreadable += 1
            continue
        if d.get("completeness", {}).get("complete"):
            complete += 1
        for n in nets:
            per_net_pools[n] += len(d.get("networks", {}).get(n, []))
    print(f"cohorts on disk: {len(cohorts)}  (unreadable: {unreadable}, "
          f"stamped complete: {complete})")
    for n in nets:
        print(f"  {n:8} {per_net_pools[n]:6} pool observations")
    print(f"thresholds: gap incident below {ct['gap_incident_below']}, "
          f"STOP below {ct['stop_survey_below']}")
    if len(cohorts) < ct["stop_survey_below"]:
        print(f"IT FAILED: {len(cohorts)} cohorts is below the pre-registered stop threshold "
              f"({ct['stop_survey_below']}). The decision must not proceed: journal "
              "insufficient-data and append a survey_extended event.", file=sys.stderr)
        return 1
    if len(cohorts) < ct["gap_incident_below"]:
        print(f"NOTE: {len(cohorts)} cohorts is below {ct['gap_incident_below']} — the decision "
              "wake must journal a sampling_gap incident before scoring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
