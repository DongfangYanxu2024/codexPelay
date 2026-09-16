# Data contracts and CLI

Read this reference before writing JSON for the helper. Run `python scripts/innovation_assistant.py <command> --help` when the installed script and this reference differ; the script is the executable authority. Files are UTF-8 JSON. The helper preserves extra candidate fields, so semantic critique and experiment data may travel with a candidate even when the ranker does not interpret them.

## Commands

```text
python scripts/innovation_assistant.py init --requirements TEXT [--name NAME] [--output-dir DIR] [--force]
python scripts/innovation_assistant.py init --requirements-file PATH [--name NAME] [--output-dir DIR] [--force]
python scripts/innovation_assistant.py rank [--brief brief.json] [--candidates candidates.json] [--output decision.json] [--markdown [decision.md]]
python scripts/innovation_assistant.py evaluate [--decision decision.json] --metrics metrics.json [--history iteration.json] [--output iteration.json]
```

`init` creates `brief.json`, `candidates.template.json`, and `generation-prompt.md`. It refuses to overwrite any of them unless `--force` is explicitly used. The model must fill the template; `init` does not generate or validate ideas. Success exits 0. CLI, file, JSON, and validation errors exit 2 with a corrective message on stderr.

## `brief.json`

The initialized shape is:

```json
{
  "schema_version": "1.0",
  "project_name": "Project Innovation Brief",
  "requirement": "the user's requirement",
  "objectives": ["measurable outcome"],
  "target_users": ["specific user"],
  "hard_constraints": [
    {"id": "local_only", "description": "Core data stays local"}
  ],
  "weights": {
    "desirability": 0.25,
    "feasibility": 0.20,
    "viability": 0.15,
    "innovation": 0.15,
    "strategic_fit": 0.15,
    "testability": 0.10
  },
  "evaluation": {
    "max_iterations": 3,
    "minimum_rank_score": 60.0,
    "pivot_threshold": 0.5,
    "stop_on_target": true
  }
}
```

`hard_constraints` accepts unique non-empty strings or `{id, description}` objects and normalizes both forms to objects. Use stable short IDs because candidate checks refer to them. `weights` is a non-empty object of positive finite values; the helper normalizes its sum to 1. Every weight key must exist in every candidate's `scores`. Keep the six defaults unless the brief justifies another configured dimension or weighting.

`evaluation.max_iterations` is an integer of at least 1 and governs implementation measurement rounds, not the two concept-optimization rounds. `minimum_rank_score` is 0–100, `pivot_threshold` is 0–1, and `stop_on_target` is boolean. Additional brief fields may record assumptions, soft preferences, assets, budgets, metrics, and audit metadata.

## `candidates.json`

The ranker accepts either an array or an object containing `candidates`. Prefer the initialized object. It requires exactly 20 candidates and exactly five in each of `G1`, `G2`, `G3`, and `G4`.

```json
{
  "schema_version": "1.0",
  "candidates": [
    {
      "id": "G1-01",
      "group": "G1",
      "name": "distinct non-empty name",
      "summary": "specific user, problem, mechanism, and deliverable",
      "hypothesis": "falsifiable core assumption",
      "target_user": "specific user",
      "implementation_outline": ["smallest testable slice"],
      "scores": {
        "desirability": 8.0,
        "feasibility": 7.0,
        "viability": 6.0,
        "innovation": 7.0,
        "strategic_fit": 8.0,
        "testability": 9.0
      },
      "confidence": 0.6,
      "evidence": [
        "observed: traceable project measurement",
        {"type": "derived", "claim": "reasoned claim", "source": "source or derivation"}
      ],
      "risk": 4.0,
      "constraint_checks": {
        "local_only": true
      },
      "constraint_check_rationales": {
        "local_only": "The MVP stores and processes core data on-device"
      },
      "round": 2,
      "lineage": [
        {"parent_id": "G1-01@round1", "change_reason": "made the test falsifiable"}
      ]
    }
  ]
}
```

Required interpreted fields are `id`, `group`, `name`, `summary`, `scores`, `confidence`, `evidence`, `risk`, and `constraint_checks`.

- IDs and names must be non-empty and unique after Unicode/case normalization.
- Each score must be finite and in 0–10. Scores must cover all brief weight keys; extra score keys are retained but do not contribute unless weighted.
- `confidence` is 0–1 and `risk` is 0–10, with higher risk worse.
- `evidence` is a list. Items are non-empty strings or non-empty objects; an empty list is valid but receives the no-evidence adjustment. Evidence count is not evidence quality, so use traceable claims and the `observed`/`derived`/`assumed` discipline.
- `constraint_checks` maps each hard-constraint ID to a boolean. `true` encodes pass, `false` fail, and a missing ID encodes unknown/unverified; both false and missing make the candidate ineligible.
- Preserve human-readable reasons in an extra field such as `constraint_check_rationales`; the helper retains it but interprets only the boolean map.
- If `round` is present, it is an integer of at least 0 (`0` baseline, `1` challenge, `2` experiment/delivery stress). The helper preserves `hypothesis`, `target_user`, `implementation_outline`, `lineage`, critiques, experiments, and other extra fields without interpreting them.

Run semantic diversity review before `rank`. The script's lexical similarity calculation is a deterministic warning and penalty, not a substitute for the model's structural duplicate judgment.

## `decision.json`

`rank` writes:

```json
{
  "schema_version": "1.0",
  "status": "winner_selected",
  "brief": {},
  "ranking": [],
  "top5": [],
  "winner": {},
  "ranking_rules": {}
}
```

`ranking` contains all 20 candidates in sorted order. Each item retains the complete candidate and adds:

- `eligible` and `elimination_reasons` (`hard_constraint_failed:<id>` or `hard_constraint_unverified:<id>`);
- `selection_eligible`, which also requires `final_score >= brief.evaluation.minimum_rank_score`;
- `rank`;
- `score_breakdown`: `base_score`, `weighted_components`, `confidence_adjustment`, `evidence_adjustment`, `evidence_count`, `risk_penalty`, `similarity_penalty`, `duplicate_penalty`, `raw_score`, and clamped `final_score`;
- `similarity`: `max_jaccard`, `most_similar_candidate_id`, and `duplicate_of` for exact normalized-summary duplicates.

`top5` contains the five highest hard-constraint-eligible ranking objects, not just IDs; it may include concepts below the selection threshold so they can be optimized. `winner` is the highest `selection_eligible` object or `null`. Status is `winner_selected`, `no_candidate_above_minimum_score`, or `no_eligible_candidate`. `ranking_rules` records weights, formula, group invariant, minimum score, similarity threshold, and penalty constants. The model still checks successful Round 1/2 completion, semantic diversity, and evidence sufficiency before presenting the script winner as the project decision.

## `metrics.json`

The evaluator accepts a non-empty metric array or this preferred object:

```json
{
  "iteration": 1,
  "metrics": [
    {
      "name": "weekly_completion_rate",
      "value": 0.61,
      "baseline": 0.38,
      "target": 0.60,
      "direction": "maximize",
      "weight": 1.0,
      "tolerance": 0.0
    }
  ],
  "blocking_failures": [],
  "notes": []
}
```

`iteration` is optional and must be an integer of at least 1. Metric names are unique. `value` and `target` are required finite numbers; `threshold` is accepted as an alias for `target`. `direction` is `maximize` or `minimize`. `baseline` is optional; `weight` defaults to 1 and must be positive; `tolerance` defaults to 0 and must be non-negative. `blocking_failures` is a list of non-empty strings. Supply only observed values and put provenance/window/limitations in retained metric fields or `notes`.

## `iteration.json`

`evaluate` writes `schema_version`, `current_iteration`, `max_iterations`, `recommendation`, `should_stop`, `stop_reason`, `next_action`, and append-only `iterations`. Each iteration contains its number, evaluated metrics with `met`, `gap`, and optional `improved_from_baseline`, blocking failures, notes, reason codes, recommendation, stop flag, and a summary of target attainment and winner.

Pass the prior iteration output with `--history`; iteration numbers must increase. A terminal history cannot be extended, and the evaluator refuses rounds above `max_iterations`. Recommendations are exactly `keep`, `iterate`, `pivot`, or `stop`. The helper compares thresholds deterministically; the model judges provenance, causal meaning, safety, and whether a further action is authorized.
