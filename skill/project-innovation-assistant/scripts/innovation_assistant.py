#!/usr/bin/env python3
"""Deterministic helpers for the project-innovation-assistant skill.

The script intentionally does not generate ideas.  It creates an exact candidate
schema, validates model/user supplied ideas, ranks them reproducibly, and keeps a
small evaluation ledger.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1.0"
GROUPS = ("G1", "G2", "G3", "G4")
DEFAULT_WEIGHTS: dict[str, float] = {
    "desirability": 0.25,
    "feasibility": 0.20,
    "viability": 0.15,
    "innovation": 0.15,
    "strategic_fit": 0.15,
    "testability": 0.10,
}
DEFAULT_EVALUATION: dict[str, Any] = {
    "max_iterations": 3,
    "minimum_rank_score": 60.0,
    "pivot_threshold": 0.5,
    "stop_on_target": True,
}
SIMILARITY_THRESHOLD = 0.65
SIMILARITY_PENALTY_SCALE = 20.0
DUPLICATE_PENALTY = 15.0
RISK_PENALTY_SCALE = 1.5


class AssistantError(ValueError):
    """A user-correctable input or validation error."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if not _is_number(value) or not math.isfinite(float(value)):
        raise AssistantError(f"{label} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise AssistantError(f"{label} must be >= {minimum:g}")
    if maximum is not None and result > maximum:
        raise AssistantError(f"{label} must be <= {maximum:g}")
    return result


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssistantError(f"{label} must be a non-empty string")
    return value.strip()


def _identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _round(value: float) -> float:
    return round(float(value), 4)


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AssistantError(f"cannot read {label} '{path}': {exc}") from exc


def _read_json(path: Path, label: str) -> Any:
    text = _read_text(path, label)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssistantError(
            f"invalid JSON in {label} '{path}' at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 atomically, including on Windows."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
            os.replace(temporary_name, path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise AssistantError(f"cannot write '{path}': {exc}") from exc


def _write_json(path: Path, data: Any) -> None:
    _write_text(path, _json_text(data))


def _validate_weights(value: Any) -> dict[str, float]:
    if value is None:
        value = DEFAULT_WEIGHTS
    if not isinstance(value, Mapping) or not value:
        raise AssistantError("brief.weights must be a non-empty object")

    raw: dict[str, float] = {}
    for key, weight in value.items():
        criterion = _nonempty_text(key, "brief.weights key")
        if criterion in raw:
            raise AssistantError(f"duplicate weight criterion: {criterion}")
        raw[criterion] = _number(
            weight, f"brief.weights.{criterion}", minimum=0.0
        )
        if raw[criterion] == 0:
            raise AssistantError(f"brief.weights.{criterion} must be > 0")

    total = sum(raw.values())
    return {key: raw[key] / total for key in sorted(raw)}


def _validate_hard_constraints(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AssistantError("brief.hard_constraints must be a list")

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            constraint_id = _nonempty_text(
                item, f"brief.hard_constraints[{index - 1}]"
            )
            description = constraint_id
        elif isinstance(item, Mapping):
            constraint_id = _nonempty_text(
                item.get("id"), f"brief.hard_constraints[{index - 1}].id"
            )
            description = _nonempty_text(
                item.get("description", constraint_id),
                f"brief.hard_constraints[{index - 1}].description",
            )
        else:
            raise AssistantError(
                f"brief.hard_constraints[{index - 1}] must be a string or object"
            )
        identity = _identity(constraint_id)
        if identity in seen:
            raise AssistantError(f"duplicate hard constraint id: {constraint_id}")
        seen.add(identity)
        result.append({"id": constraint_id, "description": description})
    return result


def _validate_evaluation(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise AssistantError("brief.evaluation must be an object")

    merged = {**DEFAULT_EVALUATION, **value}
    maximum = merged["max_iterations"]
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        raise AssistantError("brief.evaluation.max_iterations must be an integer >= 1")
    minimum_score = _number(
        merged["minimum_rank_score"],
        "brief.evaluation.minimum_rank_score",
        minimum=0,
        maximum=100,
    )
    pivot_threshold = _number(
        merged["pivot_threshold"],
        "brief.evaluation.pivot_threshold",
        minimum=0,
        maximum=1,
    )
    stop_on_target = merged["stop_on_target"]
    if not isinstance(stop_on_target, bool):
        raise AssistantError("brief.evaluation.stop_on_target must be a boolean")
    return {
        "max_iterations": maximum,
        "minimum_rank_score": minimum_score,
        "pivot_threshold": pivot_threshold,
        "stop_on_target": stop_on_target,
    }


def validate_brief(value: Any) -> dict[str, Any]:
    """Return a normalized, JSON-compatible brief."""

    if not isinstance(value, Mapping):
        raise AssistantError("brief must be a JSON object")
    result = copy.deepcopy(dict(value))
    if "requirement" in result:
        result["requirement"] = _nonempty_text(
            result["requirement"], "brief.requirement"
        )
    else:
        result["requirement"] = ""
    result["weights"] = _validate_weights(result.get("weights"))
    result["hard_constraints"] = _validate_hard_constraints(
        result.get("hard_constraints")
    )
    result["evaluation"] = _validate_evaluation(result.get("evaluation"))
    return result


def _candidate_template(weights: Mapping[str, float]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for group in GROUPS:
        for slot in range(1, 6):
            candidates.append(
                {
                    "confidence": 0.0,
                    "constraint_checks": {},
                    "evidence": [],
                    "group": group,
                    "hypothesis": "",
                    "id": f"{group}-{slot:02d}",
                    "implementation_outline": [],
                    "lineage": [],
                    "name": "",
                    "risk": 0.0,
                    "round": 0,
                    "scores": {criterion: 0.0 for criterion in weights},
                    "summary": "",
                    "target_user": "",
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "instructions": (
            "Fill every slot. Keep exactly five unique candidates in each of "
            "G1, G2, G3, and G4; do not add or remove slots."
        ),
        "candidates": candidates,
    }


def _generation_prompt(brief: Mapping[str, Any]) -> str:
    criteria = ", ".join(brief["weights"])
    constraints = brief["hard_constraints"]
    constraint_text = (
        "none declared; use an empty constraint_checks object"
        if not constraints
        else ", ".join(
            f"{item['id']} ({item['description']})" for item in constraints
        )
    )
    requirement = brief.get("requirement", "")
    return f"""# Generate 20 project candidates

Requirement:

<requirement>
{requirement}
</requirement>

Return JSON only by filling `candidates.template.json`. Preserve exactly 20 slots
and the existing IDs: five candidates per group.

- G1: direct, low-assumption solutions to the stated need.
- G2: adjacent or workflow-level solutions that remove root friction.
- G3: ambitious, cross-domain, or technically differentiated solutions.
- G4: constraint-reframed, low-cost, or unexpectedly simple solutions.

Every candidate requires these fields:

- `id`: existing unique slot ID; `group`: one of G1..G4.
- `name` and `summary`: non-empty and genuinely distinct.
- `hypothesis`, `target_user`, `implementation_outline`: implementation context.
- `scores`: numeric 0..10 for exactly the weighted criteria needed by ranking:
  {criteria}.
- `confidence`: numeric 0..1; `evidence`: a JSON list of distinct evidence items.
- `risk`: numeric 0..10 (10 is highest risk).
- `constraint_checks`: boolean result for every hard-constraint ID.
- `lineage` and `round`: optional traceability fields; keep them when present.

Hard constraints: {constraint_text}.

Do not use markdown fences and do not change the outer JSON shape.
"""


def initialize(
    requirements: str,
    output_dir: Path,
    *,
    name: str = "Project Innovation Brief",
    force: bool = False,
) -> tuple[Path, Path, Path]:
    requirement = _nonempty_text(requirements, "requirements")
    project_name = _nonempty_text(name, "name")
    brief_path = output_dir / "brief.json"
    candidates_path = output_dir / "candidates.template.json"
    prompt_path = output_dir / "generation-prompt.md"
    paths = (brief_path, candidates_path, prompt_path)
    existing = [str(path) for path in paths if path.exists()]
    if existing and not force:
        raise AssistantError(
            "refusing to overwrite existing file(s) without --force: "
            + ", ".join(existing)
        )

    brief = {
        "evaluation": copy.deepcopy(DEFAULT_EVALUATION),
        "hard_constraints": [],
        "objectives": [],
        "project_name": project_name,
        "requirement": requirement,
        "schema_version": SCHEMA_VERSION,
        "target_users": [],
        "weights": copy.deepcopy(DEFAULT_WEIGHTS),
    }
    normalized_brief = validate_brief(brief)
    _write_json(brief_path, normalized_brief)
    _write_json(candidates_path, _candidate_template(normalized_brief["weights"]))
    _write_text(prompt_path, _generation_prompt(normalized_brief))
    return paths


def _extract_candidates(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        candidates = value.get("candidates")
        if isinstance(candidates, list):
            return candidates
        raise AssistantError("candidates JSON object must contain a candidates list")
    raise AssistantError("candidates JSON must be a list or an object with candidates")


def _validate_candidates(
    value: Any,
    weights: Mapping[str, float],
) -> list[dict[str, Any]]:
    candidates = _extract_candidates(value)
    if len(candidates) != 20:
        raise AssistantError(
            f"candidates must contain exactly 20 items; found {len(candidates)}"
        )

    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    group_counts = {group: 0 for group in GROUPS}

    for index, raw in enumerate(candidates):
        label = f"candidates[{index}]"
        if not isinstance(raw, Mapping):
            raise AssistantError(f"{label} must be an object")
        candidate = copy.deepcopy(dict(raw))
        candidate_id = _nonempty_text(candidate.get("id"), f"{label}.id")
        id_identity = _identity(candidate_id)
        if id_identity in seen_ids:
            raise AssistantError(f"candidate id must be unique: {candidate_id}")
        seen_ids.add(id_identity)
        candidate["id"] = candidate_id

        group = candidate.get("group")
        if group not in GROUPS:
            raise AssistantError(f"{label}.group must be one of {', '.join(GROUPS)}")
        group_counts[group] += 1

        name = _nonempty_text(candidate.get("name"), f"{label}.name")
        name_identity = _identity(name)
        if name_identity in seen_names:
            raise AssistantError(f"candidate name must be unique: {name}")
        seen_names.add(name_identity)
        candidate["name"] = name
        candidate["summary"] = _nonempty_text(
            candidate.get("summary"), f"{label}.summary"
        )

        scores = candidate.get("scores")
        if not isinstance(scores, Mapping):
            raise AssistantError(f"{label}.scores must be an object")
        normalized_scores: dict[str, float] = {}
        for criterion, score in scores.items():
            key = _nonempty_text(criterion, f"{label}.scores key")
            normalized_scores[key] = _number(
                score, f"{label}.scores.{key}", minimum=0, maximum=10
            )
        missing = sorted(set(weights) - set(normalized_scores))
        if missing:
            raise AssistantError(
                f"{label}.scores is missing weighted criteria: {', '.join(missing)}"
            )
        candidate["scores"] = normalized_scores

        candidate["confidence"] = _number(
            candidate.get("confidence"),
            f"{label}.confidence",
            minimum=0,
            maximum=1,
        )
        candidate["risk"] = _number(
            candidate.get("risk"), f"{label}.risk", minimum=0, maximum=10
        )
        evidence = candidate.get("evidence")
        if not isinstance(evidence, list):
            raise AssistantError(f"{label}.evidence must be a list")
        for evidence_index, item in enumerate(evidence):
            if isinstance(item, str):
                if not item.strip():
                    raise AssistantError(
                        f"{label}.evidence[{evidence_index}] must not be empty"
                    )
            elif isinstance(item, Mapping):
                if not item:
                    raise AssistantError(
                        f"{label}.evidence[{evidence_index}] must not be empty"
                    )
            else:
                raise AssistantError(
                    f"{label}.evidence[{evidence_index}] must be a string or object"
                )

        checks = candidate.get("constraint_checks")
        if not isinstance(checks, Mapping):
            raise AssistantError(f"{label}.constraint_checks must be an object")
        normalized_checks: dict[str, bool] = {}
        for key, passed in checks.items():
            check_id = _nonempty_text(key, f"{label}.constraint_checks key")
            if not isinstance(passed, bool):
                raise AssistantError(
                    f"{label}.constraint_checks.{check_id} must be a boolean"
                )
            normalized_checks[check_id] = passed
        candidate["constraint_checks"] = normalized_checks

        if "round" in candidate:
            round_number = candidate["round"]
            if (
                isinstance(round_number, bool)
                or not isinstance(round_number, int)
                or round_number < 0
            ):
                raise AssistantError(f"{label}.round must be an integer >= 0")
        result.append(candidate)

    wrong_groups = [
        f"{group}={group_counts[group]}" for group in GROUPS if group_counts[group] != 5
    ]
    if wrong_groups:
        raise AssistantError(
            "candidates must contain exactly 5 items in each group; found "
            + ", ".join(wrong_groups)
        )
    return result


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for sequence in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", normalized):
        if len(sequence) == 1:
            tokens.add(sequence)
        else:
            tokens.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return tokens


def _candidate_tokens(candidate: Mapping[str, Any]) -> set[str]:
    parts = [candidate.get("name", ""), candidate.get("summary", "")]
    if isinstance(candidate.get("hypothesis"), str):
        parts.append(candidate["hypothesis"])
    return _tokens(" ".join(parts))


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _unique_evidence_count(evidence: Sequence[Any]) -> int:
    fingerprints: set[str] = set()
    for item in evidence:
        if isinstance(item, str):
            fingerprint = unicodedata.normalize("NFKC", item).strip().casefold()
        else:
            fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True)
        fingerprints.add(fingerprint)
    return len(fingerprints)


def rank_candidates(brief_value: Any, candidates_value: Any) -> dict[str, Any]:
    """Validate and rank exactly 20 candidates deterministically."""

    brief = validate_brief(brief_value)
    weights: dict[str, float] = brief["weights"]
    constraints: list[dict[str, str]] = brief["hard_constraints"]
    candidates = _validate_candidates(candidates_value, weights)

    token_sets = [_candidate_tokens(candidate) for candidate in candidates]
    similarities: list[tuple[float, str | None]] = []
    duplicate_matches: list[str | None] = []
    summaries = [_identity(candidate["summary"]) for candidate in candidates]
    for index, candidate in enumerate(candidates):
        comparisons: list[tuple[float, str]] = []
        exact_duplicates: list[str] = []
        for other_index, other in enumerate(candidates):
            if index == other_index:
                continue
            comparisons.append(
                (_jaccard(token_sets[index], token_sets[other_index]), other["id"])
            )
            if summaries[index] and summaries[index] == summaries[other_index]:
                exact_duplicates.append(other["id"])
        comparisons.sort(key=lambda item: (-item[0], _identity(item[1]), item[1]))
        similarities.append(comparisons[0] if comparisons else (0.0, None))
        duplicate_matches.append(
            sorted(exact_duplicates, key=lambda item: (_identity(item), item))[0]
            if exact_duplicates
            else None
        )

    ranking: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        weighted_components: dict[str, dict[str, float]] = {}
        base_score = 0.0
        for criterion in sorted(weights):
            score = candidate["scores"][criterion]
            contribution = score * weights[criterion] * 10.0
            base_score += contribution
            weighted_components[criterion] = {
                "contribution": _round(contribution),
                "score": _round(score),
                "weight": _round(weights[criterion]),
            }

        confidence_adjustment = (candidate["confidence"] - 0.5) * 10.0
        evidence_count = _unique_evidence_count(candidate["evidence"])
        evidence_adjustment = -1.0 if evidence_count == 0 else min(evidence_count, 3) * 0.75
        risk_penalty = candidate["risk"] * RISK_PENALTY_SCALE
        maximum_similarity, similar_candidate_id = similarities[index]
        similarity_penalty = max(
            0.0,
            (maximum_similarity - SIMILARITY_THRESHOLD) * SIMILARITY_PENALTY_SCALE,
        )
        duplicate_candidate_id = duplicate_matches[index]
        duplicate_penalty = DUPLICATE_PENALTY if duplicate_candidate_id else 0.0
        raw_score = (
            base_score
            + confidence_adjustment
            + evidence_adjustment
            - risk_penalty
            - similarity_penalty
            - duplicate_penalty
        )
        final_score = min(100.0, max(0.0, raw_score))

        checks = candidate["constraint_checks"]
        normalized_check_lookup = {_identity(key): value for key, value in checks.items()}
        elimination_reasons: list[str] = []
        for constraint in constraints:
            identity = _identity(constraint["id"])
            if identity not in normalized_check_lookup:
                elimination_reasons.append(
                    f"hard_constraint_unverified:{constraint['id']}"
                )
            elif not normalized_check_lookup[identity]:
                elimination_reasons.append(f"hard_constraint_failed:{constraint['id']}")

        item = copy.deepcopy(candidate)
        item.update(
            {
                "eligible": not elimination_reasons,
                "elimination_reasons": elimination_reasons,
                "score_breakdown": {
                    "base_score": _round(base_score),
                    "confidence_adjustment": _round(confidence_adjustment),
                    "duplicate_penalty": _round(duplicate_penalty),
                    "evidence_adjustment": _round(evidence_adjustment),
                    "evidence_count": evidence_count,
                    "final_score": _round(final_score),
                    "raw_score": _round(raw_score),
                    "risk_penalty": _round(risk_penalty),
                    "similarity_penalty": _round(similarity_penalty),
                    "weighted_components": weighted_components,
                },
                "similarity": {
                    "duplicate_of": duplicate_candidate_id,
                    "max_jaccard": _round(maximum_similarity),
                    "most_similar_candidate_id": similar_candidate_id,
                },
            }
        )
        ranking.append(item)

    ranking.sort(
        key=lambda item: (
            0 if item["eligible"] else 1,
            -item["score_breakdown"]["final_score"],
            -item["score_breakdown"]["base_score"],
            _identity(item["name"]),
            _identity(item["id"]),
            item["id"],
        )
    )
    for rank, item in enumerate(ranking, start=1):
        item["rank"] = rank

    eligible = [item for item in ranking if item["eligible"]]
    minimum_score = brief["evaluation"]["minimum_rank_score"]
    selectable = [
        item
        for item in eligible
        if item["score_breakdown"]["final_score"] >= minimum_score
    ]
    for item in ranking:
        item["selection_eligible"] = (
            item["eligible"]
            and item["score_breakdown"]["final_score"] >= minimum_score
        )
    top5 = copy.deepcopy(eligible[:5])
    winner = copy.deepcopy(selectable[0]) if selectable else None
    if winner:
        status = "winner_selected"
    elif eligible:
        status = "no_candidate_above_minimum_score"
    else:
        status = "no_eligible_candidate"
    return {
        "brief": brief,
        "ranking": ranking,
        "ranking_rules": {
            "duplicate_penalty": DUPLICATE_PENALTY,
            "formula": (
                "clamp(base_score + confidence_adjustment + evidence_adjustment "
                "- risk_penalty - similarity_penalty - duplicate_penalty, 0, 100)"
            ),
            "groups": {group: 5 for group in GROUPS},
            "risk_penalty_scale": RISK_PENALTY_SCALE,
            "selection_minimum_score": minimum_score,
            "similarity_penalty_scale": SIMILARITY_PENALTY_SCALE,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "weights": weights,
        },
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "top5": top5,
        "winner": winner,
    }


def _markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_decision_markdown(decision: Mapping[str, Any]) -> str:
    winner = decision.get("winner")
    lines = ["# Project Innovation Decision", ""]
    if isinstance(winner, Mapping):
        lines.extend(
            [
                f"Winner: **{_markdown_escape(winner['name'])}** "
                f"(`{_markdown_escape(winner['id'])}`, "
                f"{winner['score_breakdown']['final_score']:.2f}/100).",
                "",
            ]
        )
    elif decision.get("status") == "no_candidate_above_minimum_score":
        minimum = decision["ranking_rules"]["selection_minimum_score"]
        lines.extend(
            [
                "Candidates passed the hard constraints, but none reached the "
                f"minimum selection score ({minimum:.2f}/100).",
                "",
            ]
        )
    else:
        lines.extend(["No candidate passed all hard constraints.", ""])
    lines.extend(
        [
            "## Full ranking",
            "",
            "| Rank | ID | Group | Candidate | Eligible | Base | Final | Reason |",
            "|---:|---|---|---|:---:|---:|---:|---|",
        ]
    )
    for item in decision["ranking"]:
        reasons = ", ".join(item["elimination_reasons"]) or "-"
        lines.append(
            f"| {item['rank']} | {_markdown_escape(item['id'])} | "
            f"{_markdown_escape(item['group'])} | {_markdown_escape(item['name'])} | "
            f"{'yes' if item['eligible'] else 'no'} | "
            f"{item['score_breakdown']['base_score']:.2f} | "
            f"{item['score_breakdown']['final_score']:.2f} | "
            f"{_markdown_escape(reasons)} |"
        )
    lines.extend(
        [
            "",
            "Formula: `"
            + decision["ranking_rules"]["formula"]
            + "`.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_metrics(value: Any) -> tuple[int | None, list[dict[str, Any]], list[str], list[Any]]:
    if isinstance(value, list):
        iteration = None
        metrics = value
        blocking_failures: list[Any] = []
        notes: list[Any] = []
    elif isinstance(value, Mapping):
        iteration = value.get("iteration")
        metrics = value.get("metrics")
        blocking_failures = value.get("blocking_failures", [])
        notes = value.get("notes", [])
    else:
        raise AssistantError("metrics JSON must be a list or an object with metrics")

    if iteration is not None and (
        isinstance(iteration, bool) or not isinstance(iteration, int) or iteration < 1
    ):
        raise AssistantError("metrics.iteration must be an integer >= 1")
    if not isinstance(metrics, list) or not metrics:
        raise AssistantError("metrics must be a non-empty list")
    if not isinstance(blocking_failures, list):
        raise AssistantError("metrics.blocking_failures must be a list")
    normalized_failures = [
        _nonempty_text(item, f"metrics.blocking_failures[{index}]")
        for index, item in enumerate(blocking_failures)
    ]
    if not isinstance(notes, list):
        raise AssistantError("metrics.notes must be a list")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(metrics):
        label = f"metrics[{index}]"
        if not isinstance(raw, Mapping):
            raise AssistantError(f"{label} must be an object")
        item = copy.deepcopy(dict(raw))
        name = _nonempty_text(item.get("name"), f"{label}.name")
        identity = _identity(name)
        if identity in seen:
            raise AssistantError(f"metric name must be unique: {name}")
        seen.add(identity)
        item["name"] = name
        item["value"] = _number(item.get("value"), f"{label}.value")
        has_target = "target" in item
        has_threshold = "threshold" in item
        if not has_target and not has_threshold:
            raise AssistantError(f"{label} requires target (or threshold)")
        target = _number(
            item.get("target", item.get("threshold")), f"{label}.target"
        )
        if has_target and has_threshold:
            threshold = _number(item["threshold"], f"{label}.threshold")
            if threshold != target:
                raise AssistantError(f"{label}.target and threshold must match")
        item["target"] = target
        item.pop("threshold", None)
        direction = item.get("direction")
        if direction not in {"maximize", "minimize"}:
            raise AssistantError(
                f"{label}.direction must be 'maximize' or 'minimize'"
            )
        item["weight"] = _number(
            item.get("weight", 1.0), f"{label}.weight", minimum=0
        )
        if item["weight"] == 0:
            raise AssistantError(f"{label}.weight must be > 0")
        item["tolerance"] = _number(
            item.get("tolerance", 0.0), f"{label}.tolerance", minimum=0
        )
        if "baseline" in item:
            item["baseline"] = _number(item["baseline"], f"{label}.baseline")
        normalized.append(item)
    return iteration, normalized, normalized_failures, copy.deepcopy(notes)


def _history_records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Mapping) or not isinstance(value.get("iterations"), list):
        raise AssistantError("history must be an iteration JSON object with iterations")
    records = copy.deepcopy(value["iterations"])
    previous = 0
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise AssistantError(f"history.iterations[{index}] must be an object")
        iteration = record.get("iteration")
        if (
            isinstance(iteration, bool)
            or not isinstance(iteration, int)
            or iteration <= previous
        ):
            raise AssistantError("history iteration numbers must be strictly increasing")
        previous = iteration
    if records and records[-1].get("should_stop") is True:
        raise AssistantError("history is already terminal; no further iteration is allowed")
    return records


def evaluate_iteration(
    decision: Any,
    metrics_value: Any,
    history_value: Any = None,
) -> dict[str, Any]:
    """Evaluate one implementation round and append it to an iteration ledger."""

    if not isinstance(decision, Mapping):
        raise AssistantError("decision must be a JSON object")
    brief = decision.get("brief", {})
    evaluation_value = brief.get("evaluation") if isinstance(brief, Mapping) else None
    if evaluation_value is None:
        evaluation_value = decision.get("evaluation")
    evaluation = _validate_evaluation(evaluation_value)
    requested_iteration, metrics, failures, notes = _validate_metrics(metrics_value)
    records = _history_records(history_value)
    previous_iteration = records[-1]["iteration"] if records else 0
    iteration = requested_iteration if requested_iteration is not None else previous_iteration + 1
    if iteration <= previous_iteration:
        raise AssistantError(
            f"metrics.iteration must be greater than history iteration {previous_iteration}"
        )
    if iteration > evaluation["max_iterations"]:
        raise AssistantError(
            f"iteration {iteration} exceeds max_iterations={evaluation['max_iterations']}"
        )

    evaluated_metrics: list[dict[str, Any]] = []
    met_weight = 0.0
    total_weight = 0.0
    for item in metrics:
        if item["direction"] == "maximize":
            met = item["value"] + item["tolerance"] >= item["target"]
            gap = max(0.0, item["target"] - item["value"])
            improved = (
                item["value"] > item["baseline"] if "baseline" in item else None
            )
        else:
            met = item["value"] - item["tolerance"] <= item["target"]
            gap = max(0.0, item["value"] - item["target"])
            improved = (
                item["value"] < item["baseline"] if "baseline" in item else None
            )
        total_weight += item["weight"]
        if met:
            met_weight += item["weight"]
        evaluated = copy.deepcopy(item)
        evaluated.update({"gap": _round(gap), "met": met})
        if improved is not None:
            evaluated["improved_from_baseline"] = improved
        evaluated_metrics.append(evaluated)

    attainment = met_weight / total_weight
    all_targets_met = all(item["met"] for item in evaluated_metrics)
    winner = decision.get("winner")
    winner_score: float | None = None
    winner_id: str | None = None
    if isinstance(winner, Mapping):
        winner_id_value = winner.get("id")
        if isinstance(winner_id_value, str):
            winner_id = winner_id_value
        breakdown = winner.get("score_breakdown")
        if isinstance(breakdown, Mapping) and _is_number(breakdown.get("final_score")):
            winner_score = float(breakdown["final_score"])

    reasons: list[str] = []
    if winner is None:
        status = decision.get("status")
        if (
            status == "no_candidate_above_minimum_score"
            and iteration < evaluation["max_iterations"]
        ):
            recommendation = "pivot"
            reasons.append("no_candidate_above_minimum_score")
        else:
            recommendation = "stop"
            reasons.append("no_eligible_winner")
    elif all_targets_met:
        recommendation = "keep"
        reasons.append("all_targets_met")
    elif iteration >= evaluation["max_iterations"]:
        recommendation = "stop"
        reasons.append("max_iterations_reached")
    elif failures:
        recommendation = "pivot"
        reasons.append("blocking_failure")
    elif winner_score is not None and winner_score < evaluation["minimum_rank_score"]:
        recommendation = "pivot"
        reasons.append("winner_score_below_minimum")
    elif attainment < evaluation["pivot_threshold"]:
        recommendation = "pivot"
        reasons.append("target_attainment_below_pivot_threshold")
    else:
        recommendation = "iterate"
        reasons.append("targets_partially_met")

    should_stop = recommendation == "stop" or (
        recommendation == "keep" and evaluation["stop_on_target"]
    )
    next_actions = {
        "keep": "Keep the selected solution and document the validated learning.",
        "iterate": "Retain the solution, improve unmet metrics, and run the next round.",
        "pivot": "Revise the core hypothesis or implementation before the next round.",
        "stop": "Stop this solution path and record the stopping evidence.",
    }
    record = {
        "blocking_failures": failures,
        "iteration": iteration,
        "metrics": evaluated_metrics,
        "notes": notes,
        "reason_codes": reasons,
        "recommendation": recommendation,
        "should_stop": should_stop,
        "summary": {
            "all_targets_met": all_targets_met,
            "target_attainment_ratio": _round(attainment),
            "winner_id": winner_id,
            "winner_score": _round(winner_score) if winner_score is not None else None,
        },
    }
    records.append(record)
    return {
        "current_iteration": iteration,
        "iterations": records,
        "max_iterations": evaluation["max_iterations"],
        "next_action": next_actions[recommendation],
        "recommendation": recommendation,
        "schema_version": SCHEMA_VERSION,
        "should_stop": should_stop,
        "stop_reason": reasons[0] if should_stop else None,
    }


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="innovation_assistant.py",
        description=(
            "Create, validate, rank, and evaluate project-innovation candidates "
            "using deterministic JSON workflows."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run '<command> --help' for its JSON schema and options.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="create brief.json, a 20-slot template, and a generation prompt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Outputs:
  brief.json: requirement, objectives[], target_users[], hard_constraints[],
              weights{}, evaluation{max_iterations, minimum_rank_score,
              pivot_threshold, stop_on_target}.
  candidates.template.json: candidates[20], exactly five each in G1..G4.
  generation-prompt.md: prompt that states the complete candidate schema.
""",
    )
    requirement_group = init_parser.add_mutually_exclusive_group(required=True)
    requirement_group.add_argument(
        "--requirements", "--requirement", dest="requirements", help="requirement text"
    )
    requirement_group.add_argument(
        "--requirements-file", help="UTF-8 text file containing the requirement"
    )
    init_parser.add_argument("--name", default="Project Innovation Brief")
    init_parser.add_argument("--output-dir", default=".")
    init_parser.add_argument(
        "--force", action="store_true", help="replace the three init outputs"
    )

    rank_parser = subparsers.add_parser(
        "rank",
        help="strictly validate and rank exactly 20 candidates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Candidate schema (exactly 20; exactly five per G1, G2, G3, G4):
  {id, group, name, summary, scores, confidence, evidence, risk,
   constraint_checks, lineage?, round?, ...}
  id/name are unique. Every weighted score is 0..10; confidence is 0..1;
  risk is 0..10; evidence is a list; constraint_checks values are booleans.
  Extra JSON fields, including lineage and round, are retained in decision.json.

Score:
  clamp(base + (confidence-0.5)*10 + evidence_adjustment
        - risk*1.5 - similarity_penalty - duplicate_penalty, 0, 100)
  base = 10 * sum(normalized_weight * criterion_score)
  evidence_adjustment = -1 with no evidence, otherwise 0.75*min(unique_count, 3)
  similarity_penalty = 20*max(0, max_jaccard-0.65); duplicate_penalty = 15
  winner must also reach brief.evaluation.minimum_rank_score (default 60)
""",
    )
    rank_parser.add_argument("--brief", default="brief.json")
    rank_parser.add_argument("--candidates", default="candidates.json")
    rank_parser.add_argument("--output", default="decision.json")
    rank_parser.add_argument(
        "--markdown",
        nargs="?",
        const="decision.md",
        help="optionally write a Markdown report (default: decision.md)",
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="evaluate measured metrics and append an iteration record",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Metrics JSON:
  {iteration?: 1, metrics: [{name, value, target (or threshold),
   direction: maximize|minimize, baseline?, weight?, tolerance?}],
   blocking_failures?: [string], notes?: []}

Output iteration JSON contains iterations[], current_iteration, recommendation
(keep|iterate|pivot|stop), should_stop, stop_reason, and next_action. Pass a
previous output with --history to append. Default max_iterations is 3 and can be
changed in brief.evaluation.
""",
    )
    evaluate_parser.add_argument("--decision", default="decision.json")
    evaluate_parser.add_argument("--metrics", required=True)
    evaluate_parser.add_argument("--history")
    evaluate_parser.add_argument("--output", default="iteration.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            if args.requirements_file:
                requirements = _read_text(
                    _path(args.requirements_file), "requirements file"
                ).strip()
            else:
                requirements = args.requirements
            paths = initialize(
                requirements,
                _path(args.output_dir),
                name=args.name,
                force=args.force,
            )
            print("Created " + ", ".join(str(path) for path in paths))
            return 0

        if args.command == "rank":
            brief = _read_json(_path(args.brief), "brief")
            candidates = _read_json(_path(args.candidates), "candidates")
            decision = rank_candidates(brief, candidates)
            output = _path(args.output)
            if args.output == "-":
                sys.stdout.write(_json_text(decision))
            else:
                _write_json(output, decision)
            if args.markdown:
                _write_text(_path(args.markdown), render_decision_markdown(decision))
            if args.output != "-":
                winner = decision["winner"]
                summary = (
                    f"winner={winner['id']} score={winner['score_breakdown']['final_score']:.4f}"
                    if winner
                    else "no eligible winner"
                )
                print(f"Wrote {output} ({summary})")
            return 0

        if args.command == "evaluate":
            decision = _read_json(_path(args.decision), "decision")
            metrics = _read_json(_path(args.metrics), "metrics")
            history = (
                _read_json(_path(args.history), "history") if args.history else None
            )
            result = evaluate_iteration(decision, metrics, history)
            output = _path(args.output)
            if args.output == "-":
                sys.stdout.write(_json_text(result))
            else:
                _write_json(output, result)
                print(
                    f"Wrote {output} (iteration={result['current_iteration']} "
                    f"recommendation={result['recommendation']})"
                )
            return 0
    except AssistantError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
