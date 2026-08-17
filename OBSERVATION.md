# H1.0 — The Survey: how the firm decides where to look first

**Status: PRE-REGISTERED 2026-08-17. Decision wake: 2026-08-24T12:00:00Z. Governed by STRATEGY.md (H1) and GOAL.md.**

## The question this answers

"Where do you look first?" has no honest a-priori answer — any confident one would be
conviction without a ledger. So the firm does not pick a venue; it buys the answer with a
one-week, near-zero-cost survey, scored by pre-registered criteria. The principle underneath:
**look first where the base rate is cheapest to measure, because the base rate is the
opponent.** H1 passes only by beating the naive base rate; until the firm owns the base rate
for a venue, it cannot even lose properly there.

## Candidates

New DEX pools on: `solana`, `base`, `eth`, `bsc` — sampled uniformly so the data, not the
narrative, ranks them. (First snapshot 2026-08-17: the 60 newest pools span ~4 minutes on
Solana, ~17m on BSC, ~53m on Base, ~6h on ETH — volume differs by orders of magnitude.)

## Instruments

- `tools/sample.py` — snapshots the newest pools per network from GeckoTerminal's free API
  every 8 hours (scheduler-registered, fresh session per run), raw JSON kept verbatim under
  `data/cohorts/`.
- Outcome grading at the decision wake: for sampled pools old enough, re-query current state
  and compute the 72h liquidity-collapse base rate per network (criterion: pool liquidity
  below 5% of observed peak, or pool delisted/unqueryable).

## Pre-registered scoring criteria (weights fixed now, before the data)

| criterion | weight | computed as |
|---|---|---|
| Event volume | 30% | new pools per hour, log-scaled |
| Base-rate measurability | 30% | fraction of sampled pools whose 72h outcome is computable from free APIs |
| Resolution speed | 20% | median time for outcome criterion to become decidable |
| Data reliability | 20% | sampler fetch success rate per network over the week |

Excluded by construction, whatever the scores: execution-latency strategies (conceded
permanently) and any venue requiring paid data before H1 has passed.

## Decision rule

At the 2026-08-24 wake: compute the four criteria per network from `data/cohorts/`, rank,
journal the scores and the pick, then begin H1 proper — pre-registered forecasts on the
winning venue through `tools/bbp.py forecast-register`, graded by a non-author session.
If the data is insufficient to score (sampler failures, API changes), that is journaled as
the outcome and the survey extends one week — visibly, never silently.

## Known limits, stated now

- 3 pages × 20 pools per 8h snapshot is a thin sample of a firehose (Solana especially);
  adequate for base rates and volume ranking, not for exhaustive coverage. No silent caps:
  what is dropped is everything between snapshots.
- Sampler sessions and the decision wake share one scheduler; the decision wake doubles as
  the sampler's dead-man's check (missing cohorts = journaled incident).
- GeckoTerminal's free tier is an unverified dependency: rate limits or schema changes are
  survey findings, not surprises — the sampler fails loudly by design.
- Diurnal bias (added 2026-08-17 after principal challenge): 8 divides 24, so every sample
  lands at the same three clock times. This largely cancels for cross-network *ranking* (all
  networks sampled at identical times) but not for absolute base rates — the H1 cadence on
  the winning venue must correct for it (offset or denser sampling). Only ~12 of 21 wakes
  are 72h-mature by decision day (~720 gradeable pools/network, SE ~1–2pp — at the
  diminishing-returns knee); the final 3 days' samples mature during H1 week one and get
  graded then at zero additional sampling cost.
