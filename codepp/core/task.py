from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from ..utils.encoding import write_text
from ..utils.ids import new_task_id
from .paths import safe_codepp_path, safe_codepp_reference


STATUSES = (
    "NEW", "PACKED", "WAITING_FOR_RESPONSE", "RESPONSE_RECEIVED", "VALIDATED",
    "READY_TO_APPLY", "APPLIED", "VERIFYING", "DONE", "FAILED",
)
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

ALLOWED_TRANSITIONS = {
    "NEW": {"PACKED", "FAILED"},
    "PACKED": {"WAITING_FOR_RESPONSE", "RESPONSE_RECEIVED", "FAILED"},
    "WAITING_FOR_RESPONSE": {"RESPONSE_RECEIVED", "FAILED"},
    "RESPONSE_RECEIVED": {"VALIDATED", "READY_TO_APPLY", "FAILED"},
    "VALIDATED": {"READY_TO_APPLY", "DONE", "FAILED"},
    "READY_TO_APPLY": {"APPLIED", "DONE", "FAILED"},
    "APPLIED": {"VERIFYING", "DONE", "FAILED"},
    "VERIFYING": {"DONE", "FAILED"},
    "DONE": set(),
    "FAILED": set(),
}


@dataclass
class Task:
    task_id: str
    status: str
    title: str
    created_at: str
    updated_at: str
    files: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    memory_files: list[str] = field(default_factory=list)
    request_file: str | None = None
    response_file: str | None = None
    patch_file: str | None = None
    patch_validation: str | None = None
    patch_error: str | None = None
    response_sections: dict[str, str] = field(default_factory=dict)
    completion_note: str | None = None
    completion_mode: str | None = None
    completed_at: str | None = None
    repository_head: str | None = None
    repository_fingerprint: str | None = None
    context_hashes: dict[str, str] = field(default_factory=dict)
    drift_accepted_at: str | None = None

    @classmethod
    def create(cls, title: str, files: list[str]) -> "Task":
        now = datetime.now().astimezone().isoformat(timespec="microseconds")
        return cls(new_task_id(), "NEW", title, now, now, files)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        if not isinstance(data, dict):
            raise ValueError("task metadata must be a JSON object")
        known = cls.__dataclass_fields__
        try:
            task = cls(**{key: value for key, value in data.items() if key in known})
        except TypeError as exc:
            raise ValueError(f"task metadata is incomplete: {exc}") from exc
        if not isinstance(task.task_id, str) or not TASK_ID_PATTERN.fullmatch(task.task_id):
            raise ValueError("task metadata contains an invalid task_id")
        if task.status not in STATUSES:
            raise ValueError(f"task metadata contains an invalid status: {task.status}")
        if not all(isinstance(value, str) for value in (task.title, task.created_at, task.updated_at)):
            raise ValueError("task metadata title and timestamps must be strings")
        for name in ("files", "related_files", "memory_files"):
            value = getattr(task, name)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"task metadata {name} must be a list of strings")
        if not isinstance(task.response_sections, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in task.response_sections.items()
        ):
            raise ValueError("task metadata response_sections must contain text values")
        if not isinstance(task.context_hashes, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in task.context_hashes.items()
        ):
            raise ValueError("task metadata context_hashes must contain text values")
        optional_text = (
            "request_file",
            "response_file",
            "patch_file",
            "patch_validation",
            "patch_error",
            "completion_note",
            "completion_mode",
            "completed_at",
            "repository_head",
            "repository_fingerprint",
            "drift_accepted_at",
        )
        for name in optional_text:
            value = getattr(task, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"task metadata {name} must be text or null")
        if task.patch_validation not in {None, "VALID", "INVALID", "NOT_RUN", "NONE", "STALE"}:
            raise ValueError("task metadata contains an invalid patch_validation")
        if task.completion_mode not in {None, "manual", "applied", "failed"}:
            raise ValueError("task metadata contains an invalid completion_mode")
        return task

    def transition(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown task status: {status}")
        if status != self.status and status not in ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"invalid task transition: {self.status} -> {status}")
        self.status = status
        self.updated_at = datetime.now().astimezone().isoformat(timespec="microseconds")
        if status in {"DONE", "FAILED"}:
            self.completed_at = self.updated_at

    def save(self, root: Path) -> None:
        if not TASK_ID_PATTERN.fullmatch(self.task_id):
            raise ValueError("cannot save task with an invalid task_id")
        path = safe_codepp_path(root, "tasks", f"{self.task_id}.json")
        write_text(path, json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n")


def load_task(root: Path, task_id: str) -> Task:
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError(f"invalid task ID: {task_id}")
    path = safe_codepp_path(root, "tasks", f"{task_id}.json")
    if not path.is_file():
        raise ValueError(f"task does not exist: {task_id}")
    try:
        task = Task.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if task.task_id != task_id:
            raise ValueError(f"task metadata ID does not match filename: {task_id}")
        for reference in (task.request_file, task.response_file, task.patch_file):
            if reference is not None:
                safe_codepp_reference(root, reference)
        return task
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"task metadata is invalid: {task_id}") from exc


def list_tasks(root: Path) -> list[Task]:
    tasks: list[Task] = []
    for path in safe_codepp_path(root, "tasks").glob("*.json"):
        try:
            task = Task.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if task.task_id != path.stem:
                continue
            for reference in (task.request_file, task.response_file, task.patch_file):
                if reference is not None:
                    safe_codepp_reference(root, reference)
            tasks.append(task)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return sorted(tasks, key=lambda task: (task.created_at, task.task_id), reverse=True)
