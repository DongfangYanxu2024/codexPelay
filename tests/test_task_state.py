from pathlib import Path
import json

import pytest

from codepp.config import initialize_config
from codepp.core.task import Task, list_tasks, load_task


def test_task_creation_transition_and_persistence(tmp_path: Path):
    initialize_config(tmp_path)
    task = Task.create("Fix bug", ["app.py"])
    task.transition("PACKED")
    task.save(tmp_path)
    loaded = load_task(tmp_path, task.task_id)
    assert loaded.status == "PACKED"
    assert loaded.files == ["app.py"]
    assert list_tasks(tmp_path)[0].task_id == task.task_id


def test_invalid_transition_is_rejected():
    task = Task.create("Fix bug", [])
    with pytest.raises(ValueError, match="invalid task transition"):
        task.transition("APPLIED")


def test_missing_task_is_friendly(tmp_path: Path):
    initialize_config(tmp_path)
    with pytest.raises(ValueError, match="task does not exist"):
        load_task(tmp_path, "missing")


def test_loads_v01_task_without_new_metadata(tmp_path: Path):
    initialize_config(tmp_path)
    data = {
        "task_id": "legacy-task",
        "status": "VALIDATED",
        "title": "Legacy",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "files": ["app.py"],
    }
    path = tmp_path / ".codepp" / "tasks" / "legacy-task.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    task = load_task(tmp_path, "legacy-task")
    assert task.related_files == []
    assert task.memory_files == []
    assert task.completed_at is None


def test_terminal_transition_sets_completion_time():
    task = Task.create("Finish", [])
    task.transition("PACKED")
    task.transition("RESPONSE_RECEIVED")
    task.transition("VALIDATED")
    task.transition("DONE")
    assert task.completed_at == task.updated_at


def task_data(task_id: str = "task-one", *, created_at: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "task_id": task_id,
        "status": "NEW",
        "title": "Test task",
        "created_at": created_at,
        "updated_at": created_at,
        "files": ["app.py"],
    }


@pytest.mark.parametrize(
    "update,error",
    [
        ({"task_id": "../escape"}, "invalid task_id"),
        ({"status": "UNKNOWN"}, "invalid status"),
        ({"files": "app.py"}, "files must be a list of strings"),
        ({"related_files": [1]}, "related_files must be a list of strings"),
        ({"memory_files": [None]}, "memory_files must be a list of strings"),
        ({"response_sections": {"Plan": 1}}, "response_sections must contain text values"),
        ({"context_hashes": {"app.py": 123}}, "context_hashes must contain text values"),
        ({"repository_fingerprint": 123}, "repository_fingerprint must be text or null"),
        ({"patch_validation": "MAYBE"}, "invalid patch_validation"),
        ({"completion_mode": "automatic"}, "invalid completion_mode"),
    ],
)
def test_task_schema_rejects_invalid_core_fields(update: dict, error: str):
    data = task_data()
    data.update(update)
    with pytest.raises(ValueError, match=error):
        Task.from_dict(data)


def test_task_schema_requires_an_object_and_required_fields():
    with pytest.raises(ValueError, match="JSON object"):
        Task.from_dict([])  # type: ignore[arg-type]
    incomplete = task_data()
    del incomplete["title"]
    with pytest.raises(ValueError, match="incomplete"):
        Task.from_dict(incomplete)


@pytest.mark.parametrize("task_id", ["../outside", "task/name", r"C:\\outside", "", "task.json"])
def test_load_task_rejects_unsafe_ids_before_path_lookup(tmp_path: Path, task_id: str):
    initialize_config(tmp_path)
    with pytest.raises(ValueError, match="invalid task ID"):
        load_task(tmp_path, task_id)


@pytest.mark.parametrize(
    "reference",
    [
        "request.md",
        "../request.md",
        ".codepp/../outside.md",
        ".codepp/outbox/../../../outside.md",
        "C:/outside/request.md",
        r"C:\\outside\\request.md",
    ],
)
def test_load_task_rejects_unsafe_artifact_references(tmp_path: Path, reference: str):
    initialize_config(tmp_path)
    data = task_data()
    data["request_file"] = reference
    path = tmp_path / ".codepp" / "tasks" / "task-one.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact reference"):
        load_task(tmp_path, "task-one")


def test_load_task_rejects_metadata_id_that_does_not_match_filename(tmp_path: Path):
    initialize_config(tmp_path)
    path = tmp_path / ".codepp" / "tasks" / "task-one.json"
    path.write_text(json.dumps(task_data("task-two")), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match filename"):
        load_task(tmp_path, "task-one")


def test_list_tasks_skips_unsafe_metadata_and_orders_ties_deterministically(tmp_path: Path):
    initialize_config(tmp_path)
    tasks = tmp_path / ".codepp" / "tasks"
    timestamp = "2026-02-01T12:00:00+00:00"
    for task_id in ("task-a", "task-c", "task-b"):
        (tasks / f"{task_id}.json").write_text(
            json.dumps(task_data(task_id, created_at=timestamp)),
            encoding="utf-8",
        )
    unsafe = task_data("unsafe")
    unsafe["request_file"] = "../../outside.md"
    (tasks / "unsafe.json").write_text(json.dumps(unsafe), encoding="utf-8")
    (tasks / "mismatch.json").write_text(json.dumps(task_data("different")), encoding="utf-8")

    expected = ["task-c", "task-b", "task-a"]
    assert [task.task_id for task in list_tasks(tmp_path)] == expected
    assert [task.task_id for task in list_tasks(tmp_path)] == expected
