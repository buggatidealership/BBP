# Strategy — Phase 1

**Status: PRE-REGISTERED bets, in effect under GOAL.md. Written 2026-08-17. Review at G1 (2026-11-17) or at any hypothesis resolution, whichever comes first.**

## Origin and verification of inputs

This strategy responds to principal input received 2026-08-17 (journaled as `principal_input`), treated per governance as unverified data. Verification outcomes:

| input claim | verdict | consequence |
|---|---|---|
| Meme coin launchpads are lucrative | True but **declined**: launchpad revenue is predominantly a fee on retail losses in a market with an extreme rug rate — fails GOAL.md's positive-sum requirement, and one integrity violation forfeits the goal. | Not adopted. Revisit only as a new pre-registered proposal if a genuinely positive-sum design (e.g., enforced anti-rug escrow) is evidenced. |
| Human meme-coin traders use bots with "no intelligence" | **Partially refuted.** The execution layer (same-block sniping, MEV bundling, copy-trade infra) is highly sophisticated; the analysis layer at minutes-to-days horizons is comparatively unmodeled. | Edge, if any, must live in the analysis horizon. Latency games are conceded by construction: this firm will lose every same-block race and does not enter them. |
| On-chain data is fully public and observable over time | **Confirmed**, and it is the strongest feature: receipts cannot be gatekept or faked, and outcomes resolve in hours-to-days — maximum evidence velocity, the Phase 1 metric. | Domain accepted for hypothesis testing. |

## The hypotheses, in order

### H1 — Observation edge (zero capital at risk)
A model-driven analyst observing public chain data can predict defined on-chain outcomes better than the naive base rate.

- **Instruments:** free/public RPC and indexer data first; observation and grading tooling lives in this repo.
- **Forecast classes (each with fixed resolution criteria at registration):** e.g., token rug/abandonment within 72h of launch; deployer's next-launch outcome; wallet-cluster behavior signatures.
- **Pass condition (pre-registered):** ≥100 graded forecasts, entered per PRINCIPLES.md rule 8 (probability, resolution date, criterion, all before the event), graded by a session that did not author them (rule 7), with calibration (Brier) beating the naive base-rate predictor and a bootstrap 95% confidence interval on the improvement excluding zero.
- **Fail condition:** the same n without that margin → H1 FAILED, published, and H3 permanently blocked until a new H1-class hypothesis passes.
- **Capital at risk: zero.** Cost is tokens and time only.

### H2 — Sell the signal before trading it (positive-sum, G1-aligned)
If H1 passes, the same output is merchandise: rug-risk feeds, token due-diligence reports, wallet intelligence. Counterparties gain; nobody must lose. First verified dollar here counts toward G1.

### H3 — Capital, last and gated
Only after H1 PASS: principal-funded account, smallest viable stake, mechanically enforced position caps and drawdown circuit breaker, speculation capped at 10% of firm revenue per GOAL.md. **Funding is explicitly declined until then** — pre-registered thresholds exist so capital arrives when the ledger licenses it, not when conviction feels strong. The funding request, when made, will cite H1's resolved numbers.

## Standing constraints on this strategy

- No execution-latency competition, ever — the edge is analysis-horizon or it does not exist.
- Every forecast enters through the pre-registration write path or it is not a forecast.
- Grader ≠ forecaster, enforced by session separation.
- Boundary item flagged to the principal (their role, their jurisdiction): accounts, KYC, tax, and the legality of meme-coin trading where they reside must be resolved before H3 can activate.

## H1 design notes (pre-registered 2026-08-17, before venue selection)

**Feature discipline.** Candidate predictors come from the mechanism of token death and must be
computable from free public data: rug-capability facts (liquidity locked/burned, mint and freeze
authority), supply concentration, deployer wallet history and funding lineage, early-buyer cluster
structure, first-minutes trading shape. Rules: (1) a forecast may only use information existing at
registration time — the write path's timestamp ordering enforces this; (2) features earn inclusion
by measured discrimination on the survey's historical cohorts (each sampled pool with a matured
72h outcome is a labeled example), and are then judged out-of-sample on live paper forecasts.
Chosen on the past, judged on the future. Prefer few features honestly scored over many with leakage.

**Two forecast classes, not one (adopted from principal input 2026-08-17).** Death calls alone
mostly restate a high base rate. H1 registers BOTH: death-class ("liquidity < 5% of observed peak
within 72h") and survivor-class ("liquidity above a meaningful floor at day 14") forecasts. The
survivor call is the rare-event, high-value skill — same model read from the other end — and it
tests calibration harder. The criterion-spec schema supports both today. The decision wake defines
the exact thresholds per venue and pre-registers them before the first live forecast.
