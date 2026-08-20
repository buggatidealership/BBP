#!/usr/bin/env python3
"""H1.0 survey sampler: snapshot new DEX pools across candidate networks.

Pulls the newest pools per network from GeckoTerminal's free public API and
stores the raw snapshot under data/cohorts/. Raw data is kept verbatim so any
later session can re-derive conclusions; summaries are computed, never recalled.
Failures print loudly and exit non-zero — a silent sampler is a dead sampler.
"""
import json, sys, time, datetime, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
NETWORKS = ["solana", "base", "eth", "bsc"]
PAGES = 3  # 20 pools/page

def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": "bbp-survey/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 — journaled, not swallowed
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {url}: {last}")

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    outdir = ROOT / "data" / "cohorts"
    outdir.mkdir(parents=True, exist_ok=True)
    snapshot = {"ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "geckoterminal new_pools",
                "networks": {}}
    failures = []
    for net in NETWORKS:
        pools = []
        for page in range(1, PAGES + 1):
            try:
                d = fetch(f"https://api.geckoterminal.com/api/v2/networks/{net}/new_pools?page={page}")
                pools.extend(d.get("data", []))
                time.sleep(2.5)  # 429s observed 2026-08-18T00:11Z at 1s spacing; slower is cheaper than partial cohorts
            except RuntimeError as e:
                failures.append(f"{net} p{page}: {e}")
        snapshot["networks"][net] = pools
    if failures:
        snapshot["failures"] = failures
    # Completeness stamp (red-team A6, 2026-08-20): a census that counts FILES can be satisfied
    # by empty or partial cohorts. Every cohort now carries the numbers a counter needs.
    per_net = {n: len(snapshot["networks"][n]) for n in NETWORKS}
    uniq = {n: len({p.get("id") for p in snapshot["networks"][n]}) for n in NETWORKS}
    snapshot["completeness"] = {"pools_per_network": per_net, "unique_pools_per_network": uniq,
                                "expected_per_network": PAGES * 20, "failed_fetches": len(failures),
                                "complete": len(failures) == 0 and all(v >= PAGES * 20 for v in per_net.values())}
    out = outdir / f"cohort_{stamp}.json"
    out.write_text(json.dumps(snapshot, separators=(",", ":")))
    for net in NETWORKS:
        ps = snapshot["networks"][net]
        ages = []
        for p in ps:
            c = p.get("attributes", {}).get("pool_created_at")
            if c:
                created = datetime.datetime.fromisoformat(c.replace("Z", "+00:00"))
                ages.append((now - created).total_seconds() / 60)
        newest = f"newest {min(ages):.0f}m, oldest {max(ages):.0f}m" if ages else "no timestamps"
        print(f"{net}: {len(ps)} pools ({newest})")
    if failures:
        print(f"IT PARTIALLY FAILED: {len(failures)} fetch failures: {failures}", file=sys.stderr)
        sys.exit(2)
    print(f"wrote {out.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
