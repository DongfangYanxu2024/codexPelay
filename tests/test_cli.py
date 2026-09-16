from pathlib import Path
import io
import subprocess
import sys

from codepp.cli import main
from codepp.core.task import list_tasks, load_task


PATCH = """diff --git a/app.py b/app.py
index d43e89d..7f8a624 100644
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("old")
+print("new")
"""


def test_init_is_idempotent(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    config = tmp_path / ".codepp" / "config.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n# keep\n", encoding="utf-8")
    assert main(["init"]) == 0
    assert "# keep" in config.read_text(encoding="utf-8")
    assert "Existing configuration was preserved" in capsys.readouterr().out


def test_init_adds_local_git_exclude(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    exclude = (git_repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert "/.codepp/" in exclude.splitlines()
    assert main(["init"]) == 0
    exclude = (git_repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert exclude.splitlines().count("/.codepp/") == 1


def test_export_without_clipboard(git_repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    assert main(["export", "Review app", "--files", "app.py", "--no-copy"]) == 0
    task = list_tasks(git_repo)[0]
    assert task.status == "WAITING_FOR_RESPONSE"
    request = (git_repo / task.request_file).read_text(encoding="utf-8")
    assert "Review app" in request
    assert "### app.py" in request
    assert task.task_id in capsys.readouterr().out


def test_import_validate_apply_integration(git_repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    assert main(["export", "Change output", "--files", "app.py", "--no-copy"]) == 0
    task = list_tasks(git_repo)[0]
    response = git_repo / "response.md"
    response.write_text(
        f"""# CODEPP RESPONSE

Protocol: CODEPP/1
Task-ID: {task.task_id}

## Diagnosis

Output needs updating.

## Plan

Change one line.

## Patch

```diff
{PATCH}```

## Verification

```bash
python app.py
```
""",
        encoding="utf-8",
    )
    assert main(["import", "--file", str(response)]) == 0
    imported = load_task(git_repo, task.task_id)
    assert imported.status == "READY_TO_APPLY"
    assert imported.patch_validation == "VALID"
    assert main(["validate", task.task_id]) == 0
    assert main(["apply", task.task_id, "--yes"]) == 0
    assert (git_repo / "app.py").read_text(encoding="utf-8") == 'print("new")\n'
    assert load_task(git_repo, task.task_id).status == "APPLIED"
    assert main(["finish", task.task_id, "--note", "python app.py passed"]) == 0
    finished = load_task(git_repo, task.task_id)
    assert finished.status == "DONE"
    assert finished.completion_mode == "applied"
    output = capsys.readouterr().out
    assert "Ready to apply" in output
    assert "Patch applied" in output


def test_import_rejects_wrong_task(git_repo: Path, monkeypatch, tmp_path: Path):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    response = tmp_path / "wrong.md"
    response.write_text("Protocol: CODEPP/1\nTask-ID: missing\n", encoding="utf-8")
    assert main(["import", "--file", str(response)]) == 2


def test_export_with_memory_staged_diff_and_diagnostics(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    memory = git_repo / ".codepp" / "memory"
    (memory / "architecture.md").write_text("Keep the CLI thin.\n", encoding="utf-8")
    (git_repo / "app.py").write_text('print("staged")\n', encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=git_repo, check=True)
    assert main([
        "export", "Review staged change", "--files", "app.py", "--memory",
        "--staged", "--diagnostics", "Authorization: Bearer abcdef123", "--no-copy",
    ]) == 0
    task = list_tasks(git_repo)[0]
    request = (git_repo / task.request_file).read_text(encoding="utf-8")
    assert "## Repository Memory" in request
    assert "Keep the CLI thin." in request
    assert "## Staged Diff" in request
    assert '+print("staged")' in request
    assert "abcdef123" not in request
    assert task.memory_files == ["memory/architecture.md"]


def test_import_from_stdin(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    assert main(["export", "Analyze only", "--no-copy"]) == 0
    task = list_tasks(git_repo)[0]
    response = f"Protocol: CODEPP/1\nTask-ID: {task.task_id}\n\n## Plan\n\nReview locally.\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(response))
    assert main(["import", "--stdin"]) == 0
    assert load_task(git_repo, task.task_id).status == "VALIDATED"


def test_import_can_defer_patch_validation(git_repo: Path, monkeypatch, tmp_path: Path):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    config_path = git_repo / ".codepp" / "config.toml"
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("auto_validate = true", "auto_validate = false"), encoding="utf-8")
    assert main(["export", "Change output", "--no-copy"]) == 0
    task = list_tasks(git_repo)[0]
    response = tmp_path / "deferred.md"
    response.write_text(
        f"Protocol: CODEPP/1\nTask-ID: {task.task_id}\n\n## Patch\n\n```diff\n{PATCH}```\n",
        encoding="utf-8",
    )
    assert main(["import", "--file", str(response)]) == 0
    imported = load_task(git_repo, task.task_id)
    assert imported.status == "RESPONSE_RECEIVED"
    assert imported.patch_validation == "NOT_RUN"
    assert main(["validate", task.task_id]) == 0
    assert load_task(git_repo, task.task_id).status == "READY_TO_APPLY"


def test_latest_alias_and_finish_workflow(git_repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    assert main(["export", "Plan only", "--no-copy"]) == 0
    task = list_tasks(git_repo)[0]
    response = git_repo / "plan.md"
    response.write_text(
        f"Protocol: CODEPP/1\nTask-ID: {task.task_id}\n\n## Plan\n\nImplement locally.\n",
        encoding="utf-8",
    )
    assert main(["import", "--file", str(response)]) == 0
    assert main(["show", "latest"]) == 0
    assert main([
        "finish", "latest", "--manual", "--yes", "--note", "Verified manually"
    ]) == 0
    finished = load_task(git_repo, task.task_id)
    assert finished.status == "DONE"
    assert finished.completion_note == "Verified manually"
    assert finished.completion_mode == "manual"
    assert finished.completed_at
    assert "marked DONE" in capsys.readouterr().out


def test_finish_can_record_failure_but_not_unverified_success(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    assert main(["export", "Waiting", "--no-copy"]) == 0
    task = list_tasks(git_repo)[0]
    assert main(["finish", task.task_id]) == 2
    assert main(["finish", task.task_id, "--failed", "--note", "Planner unavailable"]) == 0
    failed = load_task(git_repo, task.task_id)
    assert failed.status == "FAILED"
    assert failed.completion_note == "Planner unavailable"


def test_list_rejects_non_positive_limit(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    assert main(["list", "--limit", "0"]) == 2


def test_export_discovers_bounded_related_context(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    (git_repo / "app.py").write_text("import helper\nprint(helper.value)\n", encoding="utf-8")
    (git_repo / "helper.py").write_text("value = 42\n", encoding="utf-8")
    (git_repo / "test_app.py").write_text("def test_app():\n    assert True\n", encoding="utf-8")
    assert main([
        "export", "Review imports", "--files", "app.py", "--related-limit", "2", "--no-copy"
    ]) == 0
    task = list_tasks(git_repo)[0]
    assert task.related_files == ["helper.py", "test_app.py"]
    request = (git_repo / task.request_file).read_text(encoding="utf-8")
    assert "### helper.py" in request
    assert "### test_app.py" in request
    assert main([
        "export", "Invalid limit", "--files", "app.py", "--related-limit", "0", "--no-copy"
    ]) == 2


def test_memory_crud_commands(git_repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["memory", "add", "architecture.md", "--text", "token = secret-value"]) == 0
    captured = capsys.readouterr()
    assert "potential secret" in captured.err
    assert main(["memory", "list"]) == 0
    assert "architecture.md" in capsys.readouterr().out
    assert main(["memory", "show", "architecture.md"]) == 0
    assert capsys.readouterr().out == "token = secret-value"
    assert main(["memory", "update", "architecture.md", "--text", "Keep the CLI thin.\n"]) == 0
    capsys.readouterr()
    assert main(["memory", "show", "architecture.md"]) == 0
    assert capsys.readouterr().out == "Keep the CLI thin.\n"
    assert main(["memory", "remove", "architecture.md", "--yes"]) == 0
    assert not (git_repo / ".codepp" / "memory" / "architecture.md").exists()


def test_stdout_is_a_pure_request_stream_and_skips_clipboard(
    git_repo: Path, monkeypatch, capsys
):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    capsys.readouterr()

    def unexpected_clipboard(*_args, **_kwargs):
        raise AssertionError("clipboard should not be used by --stdout")

    monkeypatch.setattr("codepp.cli.ClipboardProvider.send", unexpected_clipboard)
    assert main(["export", "password = very secret", "--stdout"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("# CODEPP REQUEST\n")
    assert "Code++ request created" not in captured.out
    assert "very secret" not in captured.out
    assert "Security: redacted" in captured.err


def test_output_copy_is_exact_and_requires_force(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    output = git_repo / "artifacts" / "request.md"
    assert main([
        "export", "Plan work", "--no-copy", "--output", "artifacts/request.md"
    ]) == 0
    task = list_tasks(git_repo)[0]
    assert output.read_bytes() == (git_repo / task.request_file).read_bytes()
    assert main([
        "export", "Plan again", "--no-copy", "--output", "artifacts/request.md"
    ]) == 2
    assert main([
        "export", "Plan again", "--no-copy", "--output", "artifacts/request.md", "--force-output"
    ]) == 0


def test_response_size_limit_is_enforced(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert main(["init"]) == 0
    assert main(["export", "Analyze", "--no-copy"]) == 0
    config = git_repo / ".codepp" / "config.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "max_response_bytes = 2000000", "max_response_bytes = 10"
        ),
        encoding="utf-8",
    )
    response = git_repo / "oversized.md"
    response.write_text("Protocol: CODEPP/1\nTask-ID: too-large\n", encoding="utf-8")
    assert main(["import", "--file", str(response)]) == 2


def test_repository_drift_requires_explicit_rebaseline(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    (git_repo / "unrelated.py").write_text("value = 0\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.py"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add unrelated"], cwd=git_repo, check=True)
    assert main(["init"]) == 0
    assert main(["export", "Change output", "--files", "app.py", "--no-copy"]) == 0
    task = list_tasks(git_repo)[0]
    (git_repo / "unrelated.py").write_text("value = 1\n", encoding="utf-8")
    response = git_repo / "drift-response.md"
    response.write_text(
        f"Protocol: CODEPP/1\nTask-ID: {task.task_id}\n\n## Patch\n\n```diff\n{PATCH}```\n",
        encoding="utf-8",
    )
    assert main(["import", "--file", str(response)]) == 0
    imported = load_task(git_repo, task.task_id)
    assert imported.status == "RESPONSE_RECEIVED"
    assert imported.patch_validation == "STALE"
    assert main(["validate", task.task_id]) == 2
    assert main(["validate", task.task_id, "--allow-drift"]) == 0
    assert load_task(git_repo, task.task_id).status == "READY_TO_APPLY"
    (git_repo / "unrelated.py").write_text("value = 2\n", encoding="utf-8")
    assert main(["apply", task.task_id, "--yes"]) == 2
