---
name: project-innovation-assistant
description: Turn an open-ended need into differentiated project concepts, compare them with explicit constraints and evidence, design validation experiments, and optionally implement and iterate the selected concept. Use for project ideation, concept selection, innovation proposals, or an explicitly requested end-to-end innovation cycle; do not use for straightforward implementation of an already chosen design.
---

# Project Innovation Assistant

Convert a need into one defensible project direction. Keep invention, evidence judgment, and trade-off reasoning with the model; use scripts only for deterministic templating, validation, arithmetic, ranking, duplicate penalties, and iteration rules. Respond in the user's language.

## Choose the authorized scope

- **Discover and select** is the default: build a brief, compare concepts, design experiments, and recommend one concept.
- **Validate** only through actions the user requested. Designing an experiment is not permission to contact people, publish, purchase, deploy, or use paid services.
- **Implement** only when the user explicitly asks to build or modify the project. A request for ideas, a proposal, or an evaluation does not authorize code changes.
- **Iterate** from observed results or user-supplied measurements. Never present planned, simulated, or inferred results as observed evidence.

Ask a concise question only when the missing answer materially changes safety, feasibility, or the decision. Otherwise state a reversible assumption and continue. Obtain authorization immediately before high-cost work, destructive actions, external communication, account changes, production changes, or other consequential mutations.

## Run the discovery funnel

1. **Build the brief.** Capture the outcome, target users, jobs and pains, context, available assets, limits, hard constraints, success metrics, unknowns, and assumptions. Separate facts from hypotheses and cite available evidence.

2. **Generate exactly 20 candidates by default:** five per exploration group: `G1` direct, low-assumption solutions; `G2` adjacent or end-to-end workflow solutions that remove root friction; `G3` ambitious or technically differentiated solutions, including useful cross-domain combinations; and `G4` constraint-reframed, low-cost, or unexpectedly simple solutions. Make each candidate concrete: user and job, mechanism, deliverable, differentiation, assets, assumptions, outcome, risk, and smallest test. Names or surface features do not establish diversity; candidates must differ structurally in at least two of mechanism, workflow, delivery channel, resource model, value model, or critical assumption. If the user explicitly requests another count, honor it, but note that the bundled rank command requires exactly 20.

3. **Apply hard constraints first.** Record each check as `pass`, `fail`, or `unknown`, with a reason. Only all-pass candidates are eligible. Never relax a constraint silently or convert missing evidence into a pass. If none is eligible, return a no-go/pivot and identify the smallest brief change that could reopen the search.

4. **Round 0 - establish the baseline.** Populate required scores for all 20, but allow only all-pass candidates to compete. Use brief weights or documented defaults; keep scores, evidence, confidence, risk, and arithmetic separate. Save this 4x5 snapshot and do not select a winner yet. Read [references/scoring-selection.md](references/scoring-selection.md) before ranking.

5. **Optimization Round 1 - coverage and challenge.** Cluster structural near-duplicates, replace them one-for-one while preserving lineage and 4x5 balance, and repair only legitimately repairable constraint failures. Red-team a distinct Top 5: state each one's strongest failure case, critical assumption, evidence gap, likely harm/hidden cost, kill condition, and cheapest mitigation. Re-score all 20 and record reasons.

6. **Optimization Round 2 - experiments and delivery stress.** For each Top 3, define a falsifiable hypothesis, smallest experiment, artifact/sample, primary and guardrail metrics, threshold, window, time/cost, dependencies, rollback, permission/ethics needs, and invalidating result. Re-check feasibility, hard constraints, and Top 5 diversity, then re-score all 20. A planned experiment has no result. Wording-only edits do not count as optimization.

7. **Select one only after exactly two successful optimization rounds by default.** It must pass every hard constraint and meet `brief.evaluation.minimum_rank_score`; otherwise return no winner and an explicit pivot/blocker. Mark the choice `provisional` until decisive tests run, or `validated` only when real evidence clears thresholds. Explain why it wins, why the other finalists do not, confidence, unresolved risks, and next authorized action. Do not open an extra optimization round merely because the result is unsatisfying.

## Use the deterministic helper

Read [references/data-contracts.md](references/data-contracts.md) before preparing JSON or calling the helper.

```text
python scripts/innovation_assistant.py init --requirements "..."
python scripts/innovation_assistant.py rank --brief brief.json --candidates candidates.json --output decision.json --markdown report.md
python scripts/innovation_assistant.py evaluate --decision decision.json --metrics metrics.json --output iteration.json
```

The model authors the brief, concepts, evidence assessments, critiques, and experiments. The helper is not an idea generator or evidence source. Inspect its outputs and surface validation errors rather than bypassing them.

## Implement and learn only when requested

When implementation is in scope, read [references/implementation-loop.md](references/implementation-loop.md). Inspect the real workspace first, preserve unrelated changes, implement the smallest testable slice, and verify it with proportionate tests. Establish baseline and target metrics before judging results.

After each measured round, state exactly one disposition: `stop`, `keep`, `iterate`, or `pivot`. Run at most three implementation iterations unless the user authorizes more. Stop early when success or a kill condition is met, evidence cannot distinguish alternatives, required access is unavailable, marginal learning no longer justifies cost, or the next action needs new authorization.

## Deliver an auditable result

Keep the brief, all candidates, exclusions, score breakdown, duplicate clusters, Top 5 challenges, Top 3 experiments, selection, evidence status, implementation changes, metrics, and iteration disposition distinguishable. For the exact report contract, read [references/delivery-contract.md](references/delivery-contract.md). Never omit a failed constraint, unknown evidence, or authorization boundary.
