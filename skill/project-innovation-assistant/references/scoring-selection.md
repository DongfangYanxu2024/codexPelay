# Scoring and selection

Read this reference when ranking candidates, challenging a shortlist, or explaining a selection. Scoring organizes judgment; it does not turn unsupported claims into evidence.

## Eligibility before arithmetic

A candidate is eligible only when every hard constraint has a recorded `pass`. Treat `fail` and `unknown` as ineligible. Keep excluded candidates and reasons in the record. If a constraint is ambiguous, clarify it or label the interpretation as an assumption instead of silently weakening it.

## Dimensions and weights

Score each dimension from 0 to 10: 0 is unacceptable, 5 is plausible but weakly supported, and 10 is exceptional with strong relevant evidence.

| Dimension | Decision question | Default weight |
|---|---|---:|
| `desirability` | Does it solve an important problem for the intended user? | 0.25 |
| `feasibility` | Can the team build and operate it within the brief? | 0.20 |
| `viability` | Can its adoption, cost, and value model be sustained? | 0.15 |
| `innovation` | Is its advantage more than a cosmetic variation? | 0.15 |
| `strategic_fit` | Does it advance the goal and leverage relevant assets? | 0.15 |
| `testability` | Can its important uncertainty be tested quickly and credibly? | 0.10 |

Weights must be positive; the helper normalizes them to total 1.0. Brief-specific weights override defaults; record the override and rationale before inspecting scores when practical. Do not tune weights merely to make a preferred concept win.

For eligible candidate `c`:

```text
base_score(c) = 10 * sum(normalized_weight[d] * score[c,d])
```

This produces a 0–100 base. The helper then calculates:

```text
confidence_adjustment = (confidence - 0.5) * 10
evidence_adjustment   = -1 if evidence is empty, otherwise 0.75 * min(unique_items, 3)
risk_penalty          = risk * 1.5
similarity_penalty    = max(0, (max_jaccard - 0.65) * 20)
duplicate_penalty     = 15 for an exact normalized-summary duplicate, otherwise 0
final_score           = clamp(base_score + confidence_adjustment + evidence_adjustment
                              - risk_penalty - similarity_penalty - duplicate_penalty,
                              0, 100)
```

Lexical Jaccard uses normalized tokens from `name`, `summary`, and string `hypothesis`. Keep `confidence` (0–1), `risk` (0–10), and evidence visible; do not hide them inside raw scores. Evidence count affects deterministic arithmetic, but the model must judge relevance and truth. Use the helper's component breakdown for arithmetic and the model's rationale for semantic judgment.

## Evidence discipline

Classify important evidence as:

- `observed`: measured in this project or supplied with traceable provenance;
- `derived`: reasoned from known facts or a cited outside source, with the derivation or source stated;
- `assumed`: deliberately unverified and awaiting a test.

Evidence quality affects confidence. Never invent users, measurements, citations, test outcomes, or competitor behavior. If fresh or high-stakes facts could change the rank, verify them through an authorized source or mark them unknown.

Sort eligible candidates before ineligible ones, then by final score, base score, and stable normalized name/ID as implemented by the helper. `brief.evaluation.minimum_rank_score` is a decision quality gate on the 0–100 final score: do not present a below-threshold arithmetic leader as the final winner.

## Structural deduplication

Create a semantic fingerprint from target job, core mechanism, workflow change, delivery channel, required asset, value model, and critical assumption. The model assigns these fields; deterministic code may compare normalized fields or tokens.

Cluster candidates as near-duplicates when they solve the same job through substantially the same mechanism and differ mainly in naming, audience wording, interface, or packaging. Text similarity is a review signal, not proof of semantic identity; low wording overlap likewise does not make identical mechanisms diverse.

Preserve all 20 candidates and identify one representative per cluster. A lower-ranked member of the same cluster cannot take another Top 5 slot. Resolve uncertain collisions through semantic review, not wording changes designed to evade a duplicate check.

## Top 5 adversarial review

For each distinct finalist, record:

1. strongest plausible failure theory;
2. critical assumption and current evidence status;
3. most consequential harm, hidden cost, or second-order effect;
4. concrete kill condition;
5. cheapest mitigation or discriminating test;
6. any score change and its reason.

Try to disconfirm the concept. Re-rank all 20 after justified revisions while preserving Round 0 and Round 1 breakdowns and replacement lineage.

## Top 3 experiments and final choice

In Round 2, define for each distinct Top 3 candidate one experiment with a falsifiable hypothesis, method, artifact/sample, primary and guardrail metrics, target/failure thresholds, observation window, cost ceiling, dependencies, rollback, permission/ethics needs, and interpretation rule. Prefer a test that distinguishes finalists over one that merely shows each is possible. Stress MVP scope and feasibility, then re-rank all 20 and re-check Top 5 diversity. Wording-only revision is not a successful round.

If no experiment has run, choose one **provisional** winner based on current evidence and expected learning value. Use **validated** only after observed evidence meets the predeclared threshold. If no candidate is eligible, do not force a winner; disposition is `pivot` and the output identifies the blocked constraints.
