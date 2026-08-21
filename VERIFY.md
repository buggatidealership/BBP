# How to verify this machine without trusting it

*Written 2026-08-20 for the principal. The question this answers: which parts of the firm are
mechanical (they cannot fail silently, and no session's memory is involved), which are judgment
(a session decides, so the decision must be graded), and which only a human can do.*

The rule that sorts them: **if a step depends on a session remembering an instruction, it is not
mechanical — it is a wish with good intentions.** Wishes get promoted to mechanisms by moving the
check into code that something else runs.

## The flow, node by node

| # | Step | Type | What actually enforces it | How YOU verify it |
|---|---|---|---|---|
| 1 | Sample new pools every 8h | **MECHANICAL** | Scheduler fires the cron; `tools/sample.py` refuses duplicate runs (<60 min) and refuses to run past 2026-09-07 without a `survey_extended` event | GitHub commit list: a `Sample survey cohort` commit ~3×/day. If it stops, check **I9** goes red within 12h |
| 2 | Sampled data is complete | **MECHANICAL** | `sample.py` stamps `completeness` (pools per network, duplicates, failed fetches) into every cohort file | Open any `data/cohorts/*.json`, read the `completeness` block |
| 3 | Hostile token names are contained | **MECHANICAL** | `sample.py` scans names at ingestion, writes `suspicious_names`, prints an UNTRUSTED-INPUT FLAG | Search the repo for `suspicious_names`; empty = none seen |
| 4 | Nothing is silently forgotten | **MECHANICAL** | Journal is append-only; **I2** proves zero deletions across all commits in git history | GitHub Actions check **I2**, or `git log --numstat -- JOURNAL.jsonl` |
| 5 | Forecasts are falsifiable | **MECHANICAL** | `bbp.py` rejects prose criteria, certainty probabilities, past deadlines; **I3** re-proves it over the whole ledger | Check **I3**; try running the rejected examples yourself |
| 6 | Maker never grades the made | **MECHANICAL (against error), ADVISORY (against dishonesty)** | `bbp.py` blocks author==grader; **I4** re-proves it. Session identity is self-asserted, so a determined session could impersonate — the honest limit | Check **I4**; and the deeper defence is #12 |
| 7 | No grading a non-event early, no padding n | **MECHANICAL** | `bbp.py` blocks outcome=0 before deadline and duplicate subject+class; **I5**, **I6** re-prove | Checks **I5**, **I6** |
| 8 | Outcomes are read from the chain, not asserted | **MECHANICAL** | `outcomes.py` computes from archived snapshots; absence is re-queried before it counts as death | Re-run `python3 tools/outcomes.py` yourself — same data, same answer |
| 9 | Money cannot move without you | **MECHANICAL** | Allowance is $0 in `config/caps.json`; **I7** fails the build if it is non-zero without an `h1_result PASS` event; no component holds keys | Check **I7**; the wallet does not exist until you create it |
| 10 | Operational language stays computable | **MECHANICAL** | `tools/lint.py` fail-closed; **I8** runs it in CI | Check **I8** |
| 11 | The board never lies by staleness | **MECHANICAL** | `status.py` stamps generation time; **I10** fails if the board is older than the journal | Check **I10**; compare the timestamp on `STATUS.md` |
| 12 | Claims match reality | **JUDGMENT — graded** | A session writes it; the calibration ledger scores it; reality resolves it | Read `FORECASTS.jsonl`: every claim carries a probability, a deadline, and a machine-decidable criterion. Replay any grade against the chain |
| 13 | Which venue to forecast on | **JUDGMENT — pre-registered** | Weights fixed before data (`OBSERVATION.md`); the wake computes and journals every score | Recompute the four scores yourself from `data/cohorts/` — the inputs are all committed |
| 14 | Which features predict death | **JUDGMENT — graded out-of-sample** | Chosen on history, judged on live forecasts the model never saw | Watch calibration per class in `bbp.py calibration` |
| 15 | Whether a wake did its job | **MECHANICAL + JUDGMENT** | Idempotency guards and dead-man's switches are mechanical; the *quality* of what a wake wrote is judgment | The wakes' own outputs are journaled; **I9/I10/I11** catch silence and staleness |
| 16 | The gate cascade continues | **MECHANICAL, with one hole** | Each gate wake registers the next; a dead-man's switch and a **cross-session watchdog** (different session) catch failure | Your Sep 17 calendar reminder is the only check outside all of it — keep it |
| 17 | Funding, KYC, identity, jurisdiction | **HUMAN ONLY** | Nothing in the firm can do these | You do them, or they do not happen |
| 18 | Whether the goal is still worth pursuing | **HUMAN ONLY** | Kill conditions are pre-registered but you hold the veto | Read the gate table; withhold action and the firm stops |

## The three things only you can do

1. **Read the GitHub check.** Every push, and every 6 hours, GitHub runs `tools/selfcheck.py`. Green
   means all 11 MUST invariants hold. Red means a specific named invariant broke. That verdict comes
   from GitHub's machine on GitHub's schedule — no Claude session participates.
2. **Hold the money and identity boundaries.** No mechanism substitutes for this.
3. **Be the check on total infrastructure failure.** If Claude's scheduler dies, its wakes die with
   it; GitHub's 6-hourly job still runs, and your calendar reminder still fires.

## Honest limits of this page

- **I2** proves no journal line was ever *deleted* in git history; it cannot prove a line was true
  when written.
- **I4** enforces separation against error, not against a session that lies about which session it is.
- Every check above verifies the firm against its own rules. Whether those rules are the right ones
  is a judgment — and that one is yours.

The wake must alarm if there is a large shortfall in cohorts.
