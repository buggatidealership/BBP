#!/usr/bin/env python3
"""Grade survey cohorts: which sampled pools died?

Operational definitions (fixed here, before any official grading — the decision
wake runs this tool, it does not define these):
- A pool's PEAK is the maximum reserve_in_usd observed across all snapshots of it.
- DEAD at grading time = current reserve_in_usd < 5% of peak, OR the pool is no
  longer returned by the API (delisted/unindexed counts as dead — a token whose
  pool vanished did not survive).
- UNMEASURABLE = the fetch errored/timed out. Unmeasurable is a data-reliability fact,
  never silently folded into either outcome.
- ABSENT FROM A BATCH RESPONSE IS NOT PROOF OF DEATH (red-team, 2026-08-20). Any pool the
  batch omits is re-queried individually: HTTP 404 confirms delisting (dead); any other
  error marks it unmeasurable. Address matching is case-insensitive — EVM checksum casing
  differing between our snapshot and the API would otherwise manufacture false deaths.
- KNOWN BIAS: peak is the max WE observed across 8-hourly snapshots, so a spike between
  snapshots is invisible and peak is an underestimate; that makes the 5% threshold easier
  to stay above, i.e. this tool UNDER-counts deaths rather than inflating them.
- Only pools first seen >= --min-age-hours ago are graded (default 72).

Usage: python3 tools/outcomes.py [--min-age-hours 72] [--max-pools-per-network 0=all]
Writes data/outcomes/outcome_<ts>.json and prints the per-network summary.
"""
import argparse, json, time, datetime, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BATCH = 25          # multi-pool endpoint accepts up to ~30 addresses
SPACING = 2.5       # seconds between requests; 429s observed at 1s on 2026-08-18


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": "bbp-survey/0.1"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def confirm_absent(net, addr):
    """A pool missing from a batch response is re-queried alone. 404 = delisted = dead;
    anything else = unmeasurable. Never infer death from an absence (red-team 2026-08-20)."""
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}",
            headers={"Accept": "application/json", "User-Agent": "bbp-survey/0.1"}), timeout=20)
        return "unmeasurable"
    except urllib.error.HTTPError as e:
        return "dead" if e.code == 404 else "unmeasurable"
    except Exception:
        return "unmeasurable"


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-age-hours", type=float, default=72.0)
    ap.add_argument("--max-pools-per-network", type=int, default=0)
    a = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc)

    # first pass: peak reserve and first-seen time per pool, across all cohorts
    pools = {}  # (net, address) -> {"peak": float, "first_seen": dt}
    for c in sorted((ROOT / "data" / "cohorts").glob("cohort_*.json")):
        snap = json.loads(c.read_text())
        seen = datetime.datetime.fromisoformat(snap["ts"].replace("Z", "+00:00"))
        for net, plist in snap["networks"].items():
            for p in plist:
                addr = p["id"].split("_", 1)[1] if "_" in p["id"] else p["id"]
                res = to_float(p.get("attributes", {}).get("reserve_in_usd"))
                if res is None:
                    continue
                k = (net, addr)
                if k not in pools:
                    pools[k] = {"peak": res, "first_seen": seen}
                else:
                    pools[k]["peak"] = max(pools[k]["peak"], res)
                    pools[k]["first_seen"] = min(pools[k]["first_seen"], seen)

    cutoff = now - datetime.timedelta(hours=a.min_age_hours)
    report = {"ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "min_age_hours": a.min_age_hours,
              "criterion": "dead = current reserve < 5% of observed peak, or pool no longer returned",
              "networks": {}}
    for net in sorted({k[0] for k in pools}):
        mature = [(addr, v) for (n, addr), v in pools.items()
                  if n == net and v["first_seen"] <= cutoff]
        if a.max_pools_per_network:
            mature = mature[: a.max_pools_per_network]
        dead = alive = 0
        unmeasurable = []
        for i in range(0, len(mature), BATCH):
            chunk = mature[i:i + BATCH]
            addrs = ",".join(addr for addr, _ in chunk)
            try:
                d = fetch(f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/multi/{addrs}")
                current = {}
                for item in d.get("data", []):
                    ad = item["id"].split("_", 1)[1] if "_" in item["id"] else item["id"]
                    current[ad.lower()] = to_float(item.get("attributes", {}).get("reserve_in_usd"))
                for addr, v in chunk:
                    cur = current.get(addr.lower())
                    if addr.lower() not in current:
                        verdict = confirm_absent(net, addr)
                        if verdict == "dead":
                            dead += 1
                        else:
                            unmeasurable.append(addr)
                        time.sleep(SPACING)
                    elif cur is not None and cur < 0.05 * v["peak"]:
                        dead += 1
                    else:
                        alive += 1
            except RuntimeError as e:
                unmeasurable.extend(addr for addr, _ in chunk)
                print(f"IT PARTIALLY FAILED: {net} batch {i//BATCH}: {e}")
            time.sleep(SPACING)
        n_meas = dead + alive
        report["networks"][net] = {
            "mature_pools": len(mature), "measurable": n_meas, "dead": dead, "alive": alive,
            "death_rate": round(dead / n_meas, 4) if n_meas else None,
            "unmeasurable": len(unmeasurable)}
        print(f"{net}: mature {len(mature)}, measurable {n_meas}, dead {dead}, alive {alive}, "
              f"death_rate {report['networks'][net]['death_rate']}, unmeasurable {len(unmeasurable)}")
    outdir = ROOT / "data" / "outcomes"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"outcome_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, separators=(",", ":")) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
