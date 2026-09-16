from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skill"
    / "project-innovation-assistant"
    / "scripts"
    / "innovation_assistant.py"
)
SPEC = importlib.util.spec_from_file_location("innovation_assistant", SCRIPT)
assert SPEC and SPEC.loader
innovation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(innovation)


def run_cli(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(value) for value in arguments)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepared_inputs(tmp_path: Path):
    result = run_cli(
        "init",
        "--requirements",
        "Build a local project innovation assistant",
        "--name",
        "Innovation Lab",
        "--output-dir",
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    brief_path = tmp_path / "brief.json"
    candidate_path = tmp_path / "candidates.json"
    brief = read_json(brief_path)
    template = read_json(tmp_path / "candidates.template.json")
    for index, candidate in enumerate(template["candidates"]):
        candidate.update(
            {
                "name": f"Distinct idea {index + 1}",
                "summary": (
                    f"Serve audience-{index + 1} using mechanism-{index + 101} "
                    f"for outcome-{index + 201}."
                ),
                "hypothesis": f"Hypothesis token-{index + 301}",
                "scores": {key: 5.0 for key in brief["weights"]},
                "confidence": 0.6,
                "evidence": [f"evidence-{index + 1}"],
                "risk": 2.0,
                "constraint_checks": {},
                "lineage": [f"seed-{index + 1}"],
                "round": 2,
            }
        )
    candidate_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return brief_path, candidate_path, brief, template


def test_init_creates_exact_four_by_five_template_and_refuses_overwrite(tmp_path):
    result = run_cli(
        "init",
        "--requirements",
        "为校园团队建立创新助手",
        "--output-dir",
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert {path.name for path in tmp_path.iterdir()} == {
        "brief.json",
        "candidates.template.json",
        "generation-prompt.md",
    }
    brief = read_json(tmp_path / "brief.json")
    template = read_json(tmp_path / "candidates.template.json")
    assert brief["requirement"] == "为校园团队建立创新助手"
    assert brief["evaluation"]["max_iterations"] == 3
    assert len(template["candidates"]) == 20
    assert {item["round"] for item in template["candidates"]} == {0}
    assert {
        group: sum(item["group"] == group for item in template["candidates"])
        for group in innovation.GROUPS
    } == {"G1": 5, "G2": 5, "G3": 5, "G4": 5}
    assert "constraint_checks" in template["candidates"][0]
    assert "lineage" in template["candidates"][0]
    assert "exactly 20 slots" in (tmp_path / "generation-prompt.md").read_text(
        encoding="utf-8"
    )

    again = run_cli(
        "init",
        "--requirements",
        "different",
        "--output-dir",
        tmp_path,
    )
    assert again.returncode == 2
    assert "without --force" in again.stderr
    assert read_json(tmp_path / "brief.json")["requirement"] == "为校园团队建立创新助手"


def test_rank_is_deterministic_explainable_and_preserves_traceability(tmp_path):
    brief_path, candidates_path, brief, template = prepared_inputs(tmp_path)
    brief["hard_constraints"] = [
        {"id": "offline", "description": "Must work offline"}
    ]
    brief_path.write_text(json.dumps(brief), encoding="utf-8")
    candidates = template["candidates"]
    for item in candidates:
        item["constraint_checks"] = {"offline": True}
    candidates[0].update(
        {
            "scores": {key: 10 for key in brief["weights"]},
            "confidence": 1,
            "evidence": ["test A", "test B", "test C"],
            "risk": 0,
            "constraint_checks": {"offline": False},
        }
    )
    candidates[1].update(
        {
            "scores": {key: 9 for key in brief["weights"]},
            "confidence": 1,
            "evidence": ["test A", "test B", "test C"],
            "risk": 0,
        }
    )
    candidates_path.write_text(json.dumps(template), encoding="utf-8")
    first_path = tmp_path / "decision-1.json"
    second_path = tmp_path / "decision-2.json"
    report_path = tmp_path / "decision.md"

    first = run_cli(
        "rank",
        "--brief",
        brief_path,
        "--candidates",
        candidates_path,
        "--output",
        first_path,
        "--markdown",
        report_path,
    )
    second = run_cli(
        "rank",
        "--brief",
        brief_path,
        "--candidates",
        candidates_path,
        "--output",
        second_path,
    )

    assert first.returncode == second.returncode == 0
    assert first_path.read_bytes() == second_path.read_bytes()
    decision = read_json(first_path)
    assert len(decision["ranking"]) == 20
    assert len(decision["top5"]) == 5
    assert decision["winner"]["id"] == candidates[1]["id"]
    assert decision["winner"]["lineage"] == ["seed-2"]
    assert decision["winner"]["round"] == 2
    eliminated = next(item for item in decision["ranking"] if item["id"] == "G1-01")
    assert not eliminated["eligible"]
    assert eliminated["elimination_reasons"] == ["hard_constraint_failed:offline"]
    assert set(eliminated["score_breakdown"]) >= {
        "base_score",
        "confidence_adjustment",
        "evidence_adjustment",
        "risk_penalty",
        "similarity_penalty",
        "duplicate_penalty",
        "final_score",
        "weighted_components",
    }
    assert "Full ranking" in report_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["candidates"].pop(), "exactly 20"),
        (
            lambda data: data["candidates"][1].update(
                {"name": data["candidates"][0]["name"]}
            ),
            "name must be unique",
        ),
        (
            lambda data: data["candidates"][0]["scores"].update(
                {"desirability": 11}
            ),
            "must be <= 10",
        ),
        (
            lambda data: data["candidates"][0].update({"group": "G2"}),
            "exactly 5 items in each group",
        ),
    ],
)
def test_rank_rejects_invalid_portfolios(tmp_path, mutation, message):
    brief_path, candidates_path, _, template = prepared_inputs(tmp_path)
    mutation(template)
    candidates_path.write_text(json.dumps(template), encoding="utf-8")

    result = run_cli(
        "rank", "--brief", brief_path, "--candidates", candidates_path
    )

    assert result.returncode == 2
    assert message in result.stderr


def test_rank_applies_custom_weights_and_duplicate_penalty(tmp_path):
    _, _, brief, template = prepared_inputs(tmp_path)
    brief["weights"] = {"impact": 3, "feasibility": 1}
    for index, candidate in enumerate(template["candidates"]):
        candidate["scores"] = {
            "impact": 9 if index == 0 else 5,
            "feasibility": 1 if index == 0 else 5,
        }
    template["candidates"][1]["summary"] = template["candidates"][0]["summary"]

    decision = innovation.rank_candidates(brief, template)

    first = next(item for item in decision["ranking"] if item["id"] == "G1-01")
    second = next(item for item in decision["ranking"] if item["id"] == "G1-02")
    assert first["score_breakdown"]["base_score"] == pytest.approx(70)
    assert first["score_breakdown"]["duplicate_penalty"] == 15
    assert second["score_breakdown"]["duplicate_penalty"] == 15
    assert first["similarity"]["duplicate_of"] == "G1-02"
    assert decision["ranking_rules"]["weights"] == {
        "feasibility": 0.25,
        "impact": 0.75,
    }


def test_rank_withholds_winner_below_configured_minimum(tmp_path):
    _, _, brief, template = prepared_inputs(tmp_path)
    brief["evaluation"]["minimum_rank_score"] = 99

    decision = innovation.rank_candidates(brief, template)

    assert decision["winner"] is None
    assert decision["status"] == "no_candidate_above_minimum_score"
    assert len(decision["top5"]) == 5
    assert not any(item["selection_eligible"] for item in decision["ranking"])
    markdown = innovation.render_decision_markdown(decision)
    assert "none reached the minimum selection score" in markdown
    assert "No candidate passed all hard constraints" not in markdown

    metrics = {
        "metrics": [
            {"name": "quality", "value": 1, "target": 2, "direction": "maximize"}
        ]
    }
    evaluation = innovation.evaluate_iteration(decision, metrics)
    assert evaluation["recommendation"] == "pivot"
    assert evaluation["stop_reason"] is None


def minimal_decision(*, score=80.0, winner=True, max_iterations=3):
    return {
        "brief": {
            "evaluation": {
                "max_iterations": max_iterations,
                "minimum_rank_score": 60,
                "pivot_threshold": 0.5,
                "stop_on_target": True,
            }
        },
        "winner": (
            {"id": "G1-01", "score_breakdown": {"final_score": score}}
            if winner
            else None
        ),
    }


def test_evaluate_returns_keep_when_all_targets_are_met():
    metrics = {
        "metrics": [
            {
                "name": "task_success",
                "value": 0.85,
                "threshold": 0.8,
                "direction": "maximize",
            },
            {
                "name": "latency_ms",
                "value": 90,
                "target": 100,
                "direction": "minimize",
            },
        ]
    }

    result = innovation.evaluate_iteration(minimal_decision(), metrics)

    assert result["recommendation"] == "keep"
    assert result["should_stop"] is True
    assert result["stop_reason"] == "all_targets_met"
    assert result["iterations"][0]["summary"]["target_attainment_ratio"] == 1


def test_evaluate_appends_history_and_recommends_iterate_pivot_then_stop():
    decision = minimal_decision()
    half_met = {
        "iteration": 1,
        "metrics": [
            {"name": "quality", "value": 8, "target": 8, "direction": "maximize"},
            {"name": "cost", "value": 12, "target": 10, "direction": "minimize"},
        ],
    }
    none_met = {
        "iteration": 2,
        "metrics": [
            {"name": "quality", "value": 2, "target": 8, "direction": "maximize"},
            {"name": "cost", "value": 20, "target": 10, "direction": "minimize"},
        ],
    }
    still_unmet = {
        "iteration": 3,
        "metrics": [
            {"name": "quality", "value": 7, "target": 8, "direction": "maximize"},
            {"name": "cost", "value": 11, "target": 10, "direction": "minimize"},
        ],
    }

    round_one = innovation.evaluate_iteration(decision, half_met)
    round_two = innovation.evaluate_iteration(decision, none_met, round_one)
    round_three = innovation.evaluate_iteration(decision, still_unmet, round_two)

    assert round_one["recommendation"] == "iterate"
    assert round_two["recommendation"] == "pivot"
    assert round_three["recommendation"] == "stop"
    assert round_three["stop_reason"] == "max_iterations_reached"
    assert [item["iteration"] for item in round_three["iterations"]] == [1, 2, 3]
    with pytest.raises(innovation.AssistantError, match="already terminal"):
        innovation.evaluate_iteration(decision, none_met, round_three)


def test_evaluate_cli_reports_bad_metric_direction_without_traceback(tmp_path):
    decision_path = tmp_path / "decision.json"
    metrics_path = tmp_path / "metrics.json"
    decision_path.write_text(json.dumps(minimal_decision()), encoding="utf-8")
    metrics_path.write_text(
        json.dumps(
            {
                "metrics": [
                    {"name": "quality", "value": 1, "target": 2, "direction": "up"}
                ]
            }
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "evaluate", "--decision", decision_path, "--metrics", metrics_path
    )

    assert result.returncode == 2
    assert "maximize" in result.stderr
    assert "Traceback" not in result.stderr
